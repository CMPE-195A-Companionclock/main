import os, tempfile, subprocess, json, time, uuid
from flask import Flask, request, jsonify
from faster_whisper import WhisperModel

# Optional: Gemini for NLU/post-processing
try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

# ===== Load Whisper model =====
DEVICE = "cuda" if os.environ.get("FORCE_CPU","0")!="1" and \
                 os.environ.get("CUDA_VISIBLE_DEVICES","")!="" else "cpu"
# Use GPU if CUDA is available; otherwise CPU. Force CPU with FORCE_CPU=1

# Model size options: small / medium / large-v3, etc. 'small' is a safe default
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"  # GPU uses float16 (faster), CPU uses int8 (lighter)

model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

app = Flask(__name__)
def _resolve_upload_dir():
    custom = os.environ.get("VOICE_INBOX_DIR", "").strip()
    if custom:
        return custom
    # Default to user's Downloads folder if available; otherwise temp dir.
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    return downloads if os.path.isdir(downloads) or os.access(os.path.dirname(downloads), os.W_OK) else os.path.join(tempfile.gettempdir(), "cc_uploads")

UPLOAD_DIR = _resolve_upload_dir()
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Configure Gemini (optional)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash").strip()
GEMINI_SYSTEM = os.environ.get(
    "GEMINI_SYSTEM",
    (
        "You are an NLU that returns compact JSON only. "
        "Given a user's Japanese text, decide if it requests navigating to a page. "
        "Return JSON: {\"intent\": one of [\"goto\", \"smalltalk\", \"none\"], "
        "\"view\": one of [\"clock\",\"weather\",\"calendar\",\"alarm\",\"voice\"] or null, "
        "\"reply\": optional short response}."
    ),
)

_gemini_model = None
if GEMINI_API_KEY and genai:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=GEMINI_SYSTEM)
    except Exception:
        _gemini_model = None

def run_gemini_nlu(text: str):
    if not text or not _gemini_model:
        return None
    try:
        resp = _gemini_model.generate_content(text)
        out = getattr(resp, "text", None) or ""
        if not out:
            return None
        # Try parse JSON, fallback to string
        try:
            return json.loads(out)
        except Exception:
            return {"intent": "none", "reply": out}
    except Exception:
        return None

def to_mono16k(in_path):
    """Convert to 16 kHz mono with ffmpeg. If ffmpeg is unavailable, return the original file."""
    try:
        out_fd, out_path = tempfile.mkstemp(suffix=".wav"); os.close(out_fd)
        cmd = ["ffmpeg", "-y", "-i", in_path, "-ac", "1", "-ar", "16000", out_path]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return out_path
    except Exception:
        return in_path  # Use the original file (faster-whisper can also decode many formats)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status":"ok","device":DEVICE,"model":MODEL_SIZE})

@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error":"audio file missing (multipart/form-data, field name 'audio')"}), 400

    f = request.files["audio"]
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(f.filename or "in.wav")[1] or ".wav")
    os.close(tmp_fd)
    f.save(tmp_path)

    conv_path = to_mono16k(tmp_path)
    try:
        segments, info = model.transcribe(conv_path, language="ja", vad_filter=True)
        segs = []
        text_chunks = []
        for s in segments:
            segs.append({"start": round(s.start,2), "end": round(s.end,2), "text": s.text})
            text_chunks.append(s.text)
        return jsonify({
            "language": info.language,
            "duration": info.duration,
            "text": "".join(text_chunks).strip(),
            "segments": segs
        })
    finally:
        try:
            os.remove(tmp_path)
            if conv_path != tmp_path: os.remove(conv_path)
        except Exception:
            pass

@app.route("/transcribe_nlu", methods=["POST"])
def transcribe_nlu():
    if "audio" not in request.files:
        return jsonify({"error":"audio file missing (multipart/form-data, field name 'audio')"}), 400

    f = request.files["audio"]
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(f.filename or "in.wav")[1] or ".wav")
    os.close(tmp_fd)
    f.save(tmp_path)

    conv_path = to_mono16k(tmp_path)
    try:
        segments, info = model.transcribe(conv_path, language="ja", vad_filter=True)
        text = "".join(s.text for s in segments).strip()
        nlu = run_gemini_nlu(text)
        return jsonify({
            "language": info.language,
            "duration": info.duration,
            "text": text,
            "nlu": nlu,
        })
    finally:
        try:
            os.remove(tmp_path)
            if conv_path != tmp_path: os.remove(conv_path)
        except Exception:
            pass

@app.route("/upload", methods=["POST"])
def upload_audio():
    """Simple endpoint that just saves incoming audio and returns the file path."""
    if "audio" not in request.files:
        return jsonify({"error":"audio file missing (multipart/form-data, field name 'audio')"}), 400

    f = request.files["audio"]
    ext = os.path.splitext(f.filename or "audio.wav")[1] or ".wav"
    safe_ext = ext if len(ext) <= 8 else ext[:8]
    fname = f"upload_{int(time.time())}_{uuid.uuid4().hex[:8]}{safe_ext}"
    out_path = os.path.join(UPLOAD_DIR, fname)
    f.save(out_path)
    return jsonify({"status": "saved", "path": out_path})

if __name__ == "__main__":
    # Bind to 0.0.0.0 so /transcribe is reachable from your LAN
    app.run(host="0.0.0.0", port=5000, threaded=True)
