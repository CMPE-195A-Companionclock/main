import os, tempfile, subprocess, json, asyncio, shutil, re, time, math
import datetime as dt
from typing import Optional
import threading

import requests
import os, tempfile, subprocess, json, asyncio, shutil, re, time, math
import datetime as dt
from typing import Optional
import threading

import requests
from flask import Flask, request, jsonify, send_file
from faster_whisper import WhisperModel
from typing import Optional
from PIapp.nlu import get_intent  # lightweight NLU, avoids pvporcupine dependency
import threading
from dotenv import load_dotenv; load_dotenv()

load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash").strip()
WEATHERAPI_KEY = os.environ.get("WEATHERAPI_KEY", "").strip()
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
HOME_ADDRESS   = os.environ.get("HOME_ADDRESS", "").strip()

PREP_MINUTES          = int(os.environ.get("PREP_MINUTES", "30"))
WEATHER_BUFFER_RAIN   = int(os.environ.get("WEATHER_BUFFER_RAIN", "5"))
WEATHER_BUFFER_SNOW   = int(os.environ.get("WEATHER_BUFFER_SNOW", "10"))
TRAFFIC_MODEL         = os.environ.get("TRAFFIC_MODEL", "best_guess").strip()

_tz = dt.datetime.now().astimezone().tzinfo

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

_gemini_model = None
def _get_gemini():
    global _gemini_model
    if not GEMINI_API_KEY:
        return None
    if _gemini_model is None:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(GEMINI_MODEL)
    return _gemini_model

_GEMINI_PLAN_PROMPT = """You extract commute planning parameters.
Return STRICT JSON only, fields:
- "intent": "plan_commute" if user is asking to plan morning or set a wake time for a trip; else "none".
- If planning: include "arrival_time" as "HH:MM" 24h, "destination" as a string address/place name,
  and optional "prep_minutes" as integer if user mentioned prep time; else omit.

Only output JSON. User said: {text}
"""

def gemini_nlu(text: str) -> Optional[dict]:
    if not text or not GEMINI_API_KEY:
        return None
    try:
        m = _get_gemini()
        if m is None:
            return None
        resp = m.generate_content(_GEMINI_PLAN_PROMPT.format(text=text))
        raw = (resp.text or "").strip()
        j = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not j:
            return None
        data = json.loads(j.group(0))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None

def _unix_epoch(dts: dt.datetime) -> int:
    return int(dts.timestamp())

def _google_travel_minutes(origin: str, destination: str, depart_local: dt.datetime) -> int:
    if not GOOGLE_MAPS_API_KEY:
        # Fallback: rough 30min if no key configured
        return 30
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": "driving",
        "departure_time": _unix_epoch(depart_local),
        "traffic_model": TRAFFIC_MODEL,
        "key": GOOGLE_MAPS_API_KEY,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    routes = (data.get("routes") or [])
    if not routes:  # fallback
        return 30
    leg = (routes[0].get("legs") or [{}])[0]
    dur = leg.get("duration_in_traffic") or leg.get("duration") or {}
    sec = int(dur.get("value", 1800))
    return max(1, math.ceil(sec / 60))

def _weather_buffer_minutes(at_local: dt.datetime) -> int:
    if not WEATHERAPI_KEY:
        return 0
    url = "http://api.weatherapi.com/v1/forecast.json"
    params = {"key": WEATHERAPI_KEY, "q": HOME_ADDRESS or "auto:ip", "hours": 1}
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        hlist = (((data.get("forecast") or {}).get("forecastday") or [{}])[0].get("hour") or [])
        target_hour = at_local.replace(minute=0, second=0, microsecond=0)
        code = None
        mm_rain = mm_snow = 0.0
        for h in hlist:
            t = h.get("time")
            if not t:
                continue
            if t.startswith(target_hour.strftime("%Y-%m-%d %H:")):
                code = int((h.get("condition") or {}).get("code", 0))
                mm_rain = float(h.get("precip_mm", 0.0))
                mm_snow = float(h.get("snow_cm", 0.0)) * 10.0
                break
        if code is None:
            return 0
        if mm_snow > 0.0:
            return WEATHER_BUFFER_SNOW
        if mm_rain >= 1.0:
            return WEATHER_BUFFER_RAIN
        return 0
    except Exception:
        return 0
    
def _parse_hhmm(s: str) -> dt.time | None:
    try:
        h, m = s.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return dt.time(hour=h, minute=m)
    except Exception:
        pass
    return None

def plan_alarm(arrival_hhmm: str, destination: str, prep_minutes: Optional[int]) -> dict:
    """Return {'alarm_time':'HH:MM','plan':{...}} in local time."""
    prep = PREP_MINUTES if not prep_minutes or prep_minutes <= 0 else prep_minutes
    tt = _parse_hhmm(arrival_hhmm)
    if not tt:
        return {"error": "invalid arrival_time"}
    today = dt.datetime.now(tz=_tz).date()
    arrival_dt = dt.datetime.combine(today, tt, tzinfo=_tz)
    # If arrival time already passed today, assume tomorrow
    if arrival_dt < dt.datetime.now(tz=_tz):
        arrival_dt = arrival_dt + dt.timedelta(days=1)

    # Iterate: travel depends on departure, but one or two passes is enough
    # Start with a guess: depart = arrival - fixed 45 min
    depart_guess = arrival_dt - dt.timedelta(minutes=45)
    travel_min = _google_travel_minutes(HOME_ADDRESS or "home", destination, depart_guess)
    weather_buf = _weather_buffer_minutes(depart_guess)
    depart_dt = arrival_dt - dt.timedelta(minutes=prep + travel_min + weather_buf)

    # refine once with updated depart time
    travel_min = _google_travel_minutes(HOME_ADDRESS or "home", destination, depart_dt)
    weather_buf = _weather_buffer_minutes(depart_dt)
    depart_dt = arrival_dt - dt.timedelta(minutes=prep + travel_min + weather_buf)

    alarm_dt = depart_dt  # wake == depart; if you want pre-depart buffer, add here
    hhmm = alarm_dt.strftime("%H:%M")
    return {
        "alarm_time": hhmm,
        "plan": {
            "arrival": arrival_dt.strftime("%H:%M"),
            "destination": destination,
            "prep_minutes": prep,
            "travel_minutes": travel_min,
            "weather_buffer": weather_buf,
            "traffic_model": TRAFFIC_MODEL,
        },
    }

_gemini_model = None
def _get_gemini():
    global _gemini_model
    if not GEMINI_API_KEY:
        return None
    if _gemini_model is None:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel(GEMINI_MODEL)
    return _gemini_model

_GEMINI_PLAN_PROMPT = """You extract commute planning parameters.
Return STRICT JSON only, fields:
- "intent": "plan_commute" if user is asking to plan morning or set a wake time for a trip; else "none".
- If planning: include "arrival_time" as "HH:MM" 24h, "destination" as a string address/place name,
  and optional "prep_minutes" as integer if user mentioned prep time; else omit.

Only output JSON. User said: {text}
"""

def gemini_nlu(text: str) -> Optional[dict]:
    if not text or not GEMINI_API_KEY:
        return None
    try:
        m = _get_gemini()
        if m is None:
            return None
        resp = m.generate_content(_GEMINI_PLAN_PROMPT.format(text=text))
        raw = (resp.text or "").strip()
        j = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not j:
            return None
        data = json.loads(j.group(0))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None

def _unix_epoch(dts: dt.datetime) -> int:
    return int(dts.timestamp())

def _google_travel_minutes(origin: str, destination: str, depart_local: dt.datetime) -> int:
    if not GOOGLE_MAPS_API_KEY:
        # Fallback: rough 30min if no key configured
        return 30
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": "driving",
        "departure_time": _unix_epoch(depart_local),
        "traffic_model": TRAFFIC_MODEL,
        "key": GOOGLE_MAPS_API_KEY,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    routes = (data.get("routes") or [])
    if not routes:  # fallback
        return 30
    leg = (routes[0].get("legs") or [{}])[0]
    dur = leg.get("duration_in_traffic") or leg.get("duration") or {}
    sec = int(dur.get("value", 1800))
    return max(1, math.ceil(sec / 60))

def _weather_buffer_minutes(at_local: dt.datetime) -> int:
    if not WEATHERAPI_KEY:
        return 0
    url = "http://api.weatherapi.com/v1/forecast.json"
    params = {"key": WEATHERAPI_KEY, "q": HOME_ADDRESS or "auto:ip", "hours": 1}
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        hlist = (((data.get("forecast") or {}).get("forecastday") or [{}])[0].get("hour") or [])
        target_hour = at_local.replace(minute=0, second=0, microsecond=0)
        code = None
        mm_rain = mm_snow = 0.0
        for h in hlist:
            t = h.get("time")
            if not t:
                continue
            if t.startswith(target_hour.strftime("%Y-%m-%d %H:")):
                code = int((h.get("condition") or {}).get("code", 0))
                mm_rain = float(h.get("precip_mm", 0.0))
                mm_snow = float(h.get("snow_cm", 0.0)) * 10.0
                break
        if code is None:
            return 0
        if mm_snow > 0.0:
            return WEATHER_BUFFER_SNOW
        if mm_rain >= 1.0:
            return WEATHER_BUFFER_RAIN
        return 0
    except Exception:
        return 0
    
def _parse_hhmm(s: str) -> dt.time | None:
    try:
        h, m = s.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return dt.time(hour=h, minute=m)
    except Exception:
        pass
    return None

def plan_alarm(arrival_hhmm: str, destination: str, prep_minutes: Optional[int]) -> dict:
    """Return {'alarm_time':'HH:MM','plan':{...}} in local time."""
    prep = PREP_MINUTES if not prep_minutes or prep_minutes <= 0 else prep_minutes
    tt = _parse_hhmm(arrival_hhmm)
    if not tt:
        return {"error": "invalid arrival_time"}
    today = dt.datetime.now(tz=_tz).date()
    arrival_dt = dt.datetime.combine(today, tt, tzinfo=_tz)
    # If arrival time already passed today, assume tomorrow
    if arrival_dt < dt.datetime.now(tz=_tz):
        arrival_dt = arrival_dt + dt.timedelta(days=1)

    # Iterate: travel depends on departure, but one or two passes is enough
    # Start with a guess: depart = arrival - fixed 45 min
    depart_guess = arrival_dt - dt.timedelta(minutes=45)
    travel_min = _google_travel_minutes(HOME_ADDRESS or "home", destination, depart_guess)
    weather_buf = _weather_buffer_minutes(depart_guess)
    depart_dt = arrival_dt - dt.timedelta(minutes=prep + travel_min + weather_buf)

    # refine once with updated depart time
    travel_min = _google_travel_minutes(HOME_ADDRESS or "home", destination, depart_dt)
    weather_buf = _weather_buffer_minutes(depart_dt)
    depart_dt = arrival_dt - dt.timedelta(minutes=prep + travel_min + weather_buf)

    alarm_dt = depart_dt  # wake == depart; if you want pre-depart buffer, add here
    hhmm = alarm_dt.strftime("%H:%M")
    return {
        "alarm_time": hhmm,
        "plan": {
            "arrival": arrival_dt.strftime("%H:%M"),
            "destination": destination,
            "prep_minutes": prep,
            "travel_minutes": travel_min,
            "weather_buffer": weather_buf,
            "traffic_model": TRAFFIC_MODEL,
        },
    }

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
    return jsonify({
        "status":"ok",
        "device":DEVICE,
        "whisper_model":MODEL_SIZE,
        "tts_default":TTS_ENGINE_DEFAULT,
        "coqui_model":COQUI_MODEL,
        "gemini_enabled": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_MODEL if GEMINI_API_KEY else None,
        "weather_enabled": bool(WEATHERAPI_KEY),
        "maps_enabled": bool(GOOGLE_MAPS_API_KEY),
        "home_address": HOME_ADDRESS or None
    })
    return jsonify({
        "status":"ok",
        "device":DEVICE,
        "whisper_model":MODEL_SIZE,
        "tts_default":TTS_ENGINE_DEFAULT,
        "coqui_model":COQUI_MODEL,
        "gemini_enabled": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_MODEL if GEMINI_API_KEY else None,
        "weather_enabled": bool(WEATHERAPI_KEY),
        "maps_enabled": bool(GOOGLE_MAPS_API_KEY),
        "home_address": HOME_ADDRESS or None
    })

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
        print(f"[transcribe] got upload: {in_path}, size={os.path.getsize(in_path)}")
    except Exception:
        pass

    try:
        if os.path.getsize(in_path) < 1024:
            return jsonify({"error": "audio file too small/invalid"}), 400

        conv_path = to_mono16k(in_path)
        try:
            print(f"[transcribe] converted: {conv_path}, size={os.path.getsize(conv_path)}")
        except Exception:
            pass

        # ASR
        segments, info = model.transcribe(conv_path, vad_filter=True)
        segs = [{"start": round(s.start,2), "end": round(s.end,2), "text": s.text} for s in segments]
        text = "".join(s["text"] for s in segs).strip()

        # NLU (don’t trigger UI here; Pi will)
        nlu = gemini_nlu(text) or (get_intent(text) or {"intent": "none"})

        if isinstance(nlu, dict) and nlu.get("intent") == "plan_commute":
            arrival = nlu.get("arrival_time")
            dest    = nlu.get("destination") or ""
            prep_m  = nlu.get("prep_minutes")
            if arrival and dest:
                nlu["alarm_proposal"] = plan_alarm(arrival, dest, prep_m)
        nlu = gemini_nlu(text) or (get_intent(text) or {"intent": "none"})

        if isinstance(nlu, dict) and nlu.get("intent") == "plan_commute":
            arrival = nlu.get("arrival_time")
            dest    = nlu.get("destination") or ""
            prep_m  = nlu.get("prep_minutes")
            if arrival and dest:
                nlu["alarm_proposal"] = plan_alarm(arrival, dest, prep_m)

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
