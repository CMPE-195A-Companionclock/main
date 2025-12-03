# PCapp/Server.py
import os, tempfile, subprocess, json, asyncio, shutil
from flask import Flask, request, jsonify, send_file
from faster_whisper import WhisperModel
from typing import Optional
from PIapp.voiceRecognition import get_intent  # reuses NLU mapping
import threading
from dotenv import load_dotenv; load_dotenv()

# Config 
TTS_ENGINE_DEFAULT = os.environ.get("TTS_ENGINE", "coqui").strip().lower()
COQUI_MODEL = os.environ.get("COQUI_MODEL", "tts_models/en/vctk/vits").strip()

try:
    import numpy as np
    import soundfile as sf
    from TTS.api import TTS as CoquiTTS
except Exception:
    CoquiTTS = None

DEVICE = "cuda" if os.environ.get("FORCE_CPU","0")!="1" and os.environ.get("CUDA_VISIBLE_DEVICES","")!="" else "cpu"
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"

model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
app = Flask(__name__)

# Helpers
def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def to_mono16k(in_path: str) -> str:
    out_path = os.path.join(tempfile.gettempdir(), f"cc_{next(tempfile._get_candidate_names())}.wav")
    if not _have_ffmpeg():
        raise RuntimeError("ffmpeg not found; install ffmpeg and ensure it is on PATH")
    subprocess.run(
        ["ffmpeg","-y","-i", in_path, "-ac","1","-ar","16000","-f","wav", out_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )
    return out_path

# Coqui TTS cache
_coqui = None
def _get_coqui():
    global _coqui
    if _coqui is None:
        if CoquiTTS is None:
            raise RuntimeError("Coqui TTS not installed. pip install TTS soundfile numpy")
        _coqui = CoquiTTS(model_name=COQUI_MODEL, progress_bar=False, gpu=(DEVICE=="cuda"))
    return _coqui

# Endpoints
@app.get("/health")
def health():
    return jsonify({"status":"ok","device":DEVICE,"whisper_model":MODEL_SIZE,"tts_default":TTS_ENGINE_DEFAULT,"coqui_model":COQUI_MODEL})

@app.post("/transcribe")
def transcribe():
    f = request.files.get("audio")
    if not f or not getattr(f, "filename", ""):
        return jsonify({"error": "audio file missing (multipart/form-data, field 'audio')"}), 400

    # Save upload
    suffix = os.path.splitext(f.filename or "in.wav")[1] or ".wav"
    in_fd, in_path = tempfile.mkstemp(suffix=suffix); os.close(in_fd)
    f.save(in_path)

    try:
        if os.path.getsize(in_path) < 1024:
            return jsonify({"error": "audio file too small/invalid"}), 400

        conv_path = to_mono16k(in_path)

        # ASR
        segments, info = model.transcribe(conv_path, vad_filter=True)
        segs = [{"start": round(s.start,2), "end": round(s.end,2), "text": s.text} for s in segments]
        text = "".join(s["text"] for s in segs).strip()

        # NLU (don’t trigger UI here; Pi will)
        nlu = get_intent(text) or {"intent":"none"}

        return jsonify({
            "text": text,
            "nlu": nlu,
            "language": info.language,
            "duration": info.duration,
            "segments": segs
        })
    except Exception as e:
        return jsonify({"error": f"transcription failed: {type(e).__name__}: {e}"}), 400
    # finally:
    #     for p in (in_path, locals().get("conv_path")):
    #         try:
    #             if p and os.path.exists(p):
    #                 os.remove(p)
    #         except Exception:
    #             pass

@app.get("/tts")
def tts():
    # Minimal TTS endpoint preserved (optional for Pi client)
    import edge_tts
    text = (request.args.get("text") or "").strip()
    voice = (request.args.get("voice") or "en-US-JennyNeural").strip()
    rate  = (request.args.get("rate")  or "+0%").strip()
    engine = (request.args.get("engine") or TTS_ENGINE_DEFAULT).strip().lower()
    if not text:
        return jsonify({"error":"missing ?text"}), 400

    fd_wav, wav_path = tempfile.mkstemp(suffix=".wav"); os.close(fd_wav)

    if engine == "coqui":
        try:
            tts = _get_coqui()
            y = tts.tts(text, speaker="p326")
            sr = getattr(getattr(tts,"synthesizer",None), "output_sample_rate", None) or 22050
            sf.write(wav_path, np.array(y), int(sr), subtype="PCM_16")
            tmp16 = wav_path + ".tmp16.wav"
            subprocess.run(["ffmpeg","-y","-i", wav_path, "-ac","1","-ar","16000", tmp16],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            os.replace(tmp16, wav_path)
        except Exception as e:
            try: os.remove(wav_path)
            except: pass
            return jsonify({"error": f"coqui-tts failed: {e}"}), 500
        resp = send_file(wav_path, mimetype="audio/wav", as_attachment=False, download_name="out.wav")
        try: os.remove(wav_path)
        except: pass
        return resp

    # Edge-tts
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
            loop.run_until_complete(synth_to_mp3()); loop.close()

        subprocess.run(["ffmpeg","-y","-i", mp3_path, "-ac","1","-ar","16000","-f","wav", wav_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        resp = send_file(wav_path, mimetype="audio/wav", as_attachment=False, download_name="out.wav")
        return resp
    except Exception as e:
        return jsonify({"error": f"edge-tts synth failed: {e}"}), 500
    # finally:
    #     for p in (mp3_path, wav_path):
    #         try: os.remove(p)
    #         except: pass

def _warmup_coqui():
    try:
        if TTS_ENGINE_DEFAULT == "coqui":
            tts = _get_coqui()
            tts.tts("warmup", speaker="p326")
            print("[Warmup] Coqui TTS ready")
    except Exception as e:
        print(f"[Warmup] Coqui preload failed: {e}")

threading.Thread(target=_warmup_coqui, daemon=True).start()

if __name__ == "__main__":
    # Bind to 0.0.0.0 so Pi can reach it
    app.run(host="0.0.0.0", port=5000, threaded=True)
