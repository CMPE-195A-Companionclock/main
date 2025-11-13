import os, tempfile, subprocess, json, asyncio, re
from flask import Flask, request, jsonify, send_file
from faster_whisper import WhisperModel
from datetime import datetime
import edge_tts
from typing import Optional

# Optional: Gemini for NLU/post-processing
try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

try:
    import numpy as np
    import soundfile as sf
    from TTS.api import TTS as CoquiTTS   # pip install TTS soundfile
except Exception:  # pragma: no cover
    CoquiTTS = None  # type: ignore

TTS_ENGINE_DEFAULT = os.environ.get("TTS_ENGINE", "coqui").strip().lower()
COQUI_MODEL = os.environ.get("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC").strip()
_coqui = None
def _get_coqui():
    """Load Coqui once and reuse."""
    global _coqui
    if _coqui is None:
        if CoquiTTS is None:
            raise RuntimeError("Coqui TTS not installed. pip install TTS soundfile numpy")
        _coqui = CoquiTTS(model_name=COQUI_MODEL, progress_bar=False, gpu=(DEVICE=="cuda"))
    return _coqui

# ===== Load Whisper model =====
DEVICE = "cuda" if os.environ.get("FORCE_CPU","0")!="1" and \
                 os.environ.get("CUDA_VISIBLE_DEVICES","")!="" else "cpu"
# Use GPU if CUDA is available; otherwise CPU. Force CPU with FORCE_CPU=1

# Model size options: small / medium / large-v3, etc. 'small' is a safe default
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"  # GPU uses float16 (faster), CPU uses int8 (lighter)

model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

app = Flask(__name__)

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

_VIEW_WORDS = r"(clock|weather|calendar|alarm|voice)"
_RE_GOTO = re.compile(rf"\b(?:go to|show|open)\s+{_VIEW_WORDS}\b", re.I)
_RE_SET_ALARM = re.compile(
    r"\bset(?: an)? alarm (?:for|at)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I
)

def _to_24h(hour: int, minute: int, ampm: Optional[str]):
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
    return f"{hour:02d}:{minute:02d}"

def parse_intent(text: str) -> dict:
    if not text:
        return {"intent": "none"}
    m = _RE_GOTO.search(text)
    if m:
        return {"intent": "goto", "view": m.group(1).lower()}
    m = _RE_SET_ALARM.search(text)
    if m:
        h = int(m.group(1)); mm = int(m.group(2) or 0); ap = m.group(3)
        return {"intent": "set_alarm", "alarm_time": _to_24h(h, mm, ap)}
    return {"intent": "none"}

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status":"ok","device":DEVICE,"model":MODEL_SIZE, "tts_default": TTS_ENGINE_DEFAULT,  "coqui_model": COQUI_MODEL})

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
        nlu = run_gemini_nlu(text) or parse_intent(text)
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

#tts
@app.get("/voices")
def voices():
    return jsonify({
        "default": "coqui",
        "popular": [
            "en-US-JennyNeural", "en-US-GuyNeural",
            "ja-JP-NanamiNeural", "ja-JP-KeitaNeural",
            "es-MX-DaliaNeural"
        ],
        "engines": ["edge", "coqui"],
        "coqui_model": COQUI_MODEL
    })

@app.get("/tts")
def tts():
    text = (request.args.get("text") or "").strip()
    voice = (request.args.get("voice") or "en-US-JennyNeural").strip()
    rate = (request.args.get("rate") or "+0%").strip()
    engine = (request.args.get("engine") or TTS_ENGINE_DEFAULT).strip().lower()

    if not text:
        return jsonify({"error": "missing ?text"}), 400
    
    fd_wav, wav_path = tempfile.mkstemp(suffix=".wav"); os.close(fd_wav)
    if engine == "coqui":
        try:
            tts = _get_coqui()
            # Coqui outputs float PCM; sample rate depends on the model (e.g., 22050).
            y = tts.tts(text)
            sr = getattr(getattr(tts, "synthesizer", None), "output_sample_rate", None) or 22050
            # Write what Coqui produced:
            sf.write(wav_path, np.array(y), int(sr), subtype="PCM_16")
            # Resample to 16 kHz mono with ffmpeg so the Pi client is always consistent
            tmp16 = wav_path + ".tmp16.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-ac", "1", "-ar", "16000", tmp16],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True
            )
            os.replace(tmp16, wav_path)
        except Exception as e:
            try: os.remove(wav_path)
            except: pass
            return jsonify({"error": f"coqui-tts failed: {e}"}), 500

        resp = send_file(wav_path, mimetype="audio/wav", as_attachment=False, download_name="out.wav")
        try: os.remove(wav_path)
        except: pass
        return resp
    
    fd_mp3, mp3_path = tempfile.mkstemp(suffix=".mp3"); os.close(fd_mp3)
    async def synth_to_mp3():
        comm = edge_tts.Communicate(text, voice=voice, rate=rate)
        with open(mp3_path, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])

    try:
        try:
            asyncio.run(synth_to_mp3())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(synth_to_mp3())
            loop.close()
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-ac", "1", "-ar", "16000", "-f", "wav", wav_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True
        )
    except Exception as e:
        for p in (mp3_path, wav_path):
            try: os.remove(p)
            except: pass
        return jsonify({"error": f"edge-tts synth failed: {e}"}), 500
    finally:
        try: os.remove(mp3_path)
        except: pass

    resp = send_file(wav_path, mimetype="audio/wav", as_attachment=False, download_name="out.wav")
    try: os.remove(wav_path)
    except: pass
    return resp

if __name__ == "__main__":
    # Bind to 0.0.0.0 so /transcribe is reachable from your LAN
    app.run(host="0.0.0.0", port=5000, threaded=True)
