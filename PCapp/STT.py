import os, tempfile, subprocess, json
from flask import Flask, request, jsonify
from faster_whisper import WhisperModel

# ===== Load Whisper model =====
DEVICE = "cuda" if os.environ.get("FORCE_CPU","0")!="1" and \
                 os.environ.get("CUDA_VISIBLE_DEVICES","")!="" else "cpu"
# Use GPU if CUDA is available; otherwise CPU. Force CPU with FORCE_CPU=1

# Model size options: small / medium / large-v3, etc. 'small' is a safe default
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"  # GPU uses float16 (faster), CPU uses int8 (lighter)

model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

app = Flask(__name__)

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

if __name__ == "__main__":
    # Bind to 0.0.0.0 so /transcribe is reachable from your LAN
    app.run(host="0.0.0.0", port=5000, threaded=True)