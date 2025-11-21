import os
import sys
import json
import shlex
import time
import tempfile
import subprocess
from urllib.parse import urlencode
from typing import Optional

import requests


SERVER_URL = os.getenv("TTS_SERVER_URL", "http://10.0.0.111:5000").rstrip("/")
DEFAULT_VOICE = os.getenv("TTS_VOICE", "en-US-JennyNeural")
DEFAULT_RATE  = os.getenv("TTS_RATE", "+0%")
TTS_ENGINE    = os.getenv("TTS_ENGINE", "coqui").strip().lower()

def _play_with_mpg123(path: str) -> bool:
    #Return True if played successfully.
    try:
        subprocess.run(["mpg123", "-q", "--no-gap", path],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _play_with_aplay(path: str) -> bool:
    #Fallback for WAV.
    try:
        subprocess.run(["aplay", "-q", path],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _download_tts(text: str, voice: str, rate: str) -> str:
    #Call PC /tts and store audio to a temp file.
    #Returns local file path (.mp3 or .wav). Raises on error.
    params = {"text": text, "voice": voice, "engine": TTS_ENGINE}
    # Some servers ignore rate, but passing it is harmless
    if rate:
        params["rate"] = rate

    url = f"{SERVER_URL}/tts?{urlencode(params)}"
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()

        ctype = r.headers.get("Content-Type", "").lower()
        suffix = ".mp3" if "audio/mpeg" in ctype or ctype.endswith("mpeg") else ".wav"

        fd, out_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)

        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)

    # Basic guard: if server sent JSON, it’s an error message
    try:
        if os.path.getsize(out_path) < 1024:
            with open(out_path, "rb") as f:
                start = f.read(256)
            if start.strip().startswith(b"{"):
                try:
                    print("TTS server error:", json.loads(start.decode("utf-8", "ignore")))
                except Exception:
                    print("TTS server returned non-audio payload.")
                raise RuntimeError("TTS server did not return audio")
    except Exception:
        try:
            os.remove(out_path)
        except Exception:
            pass
        raise

    return out_path


def speak(text: str, voice: Optional[str] = None, rate: Optional[str] = None) -> None:
    #High-level helper: fetch audio from server, play it, and clean up.
    if not text or not text.strip():
        return

    voice = (voice or DEFAULT_VOICE).strip()
    rate  = (rate or DEFAULT_RATE).strip()

    path = None
    try:
        path = _download_tts(text.strip(), voice=voice, rate=rate)

        # Try MP3 first; if that fails and file is WAV, aplay will succeed.
        played = False
        if path.lower().endswith(".mp3"):
            played = _play_with_mpg123(path)
            if not played:
                # If mpg123 missing, user will see nothing; try aplay anyway (some builds support MP3 via plugins).
                played = _play_with_aplay(path)
        else:
            played = _play_with_aplay(path)

        if not played:
            raise RuntimeError("No audio player succeeded (mpg123/aplay).")

    finally:
        if path:
            try:
                os.remove(path)
            except Exception:
                pass


# Simple CLI test: `python3 -m Plapp.tts "Hello from the Pi"`
if __name__ == "__main__":
    txt = "Hello from the Pi."
    if len(sys.argv) > 1:
        txt = " ".join(sys.argv[1:])
    print(f"[TTS] SERVER={SERVER_URL}  VOICE={DEFAULT_VOICE}")
    try:
        speak(txt)
        print("[TTS] done.")
    except Exception as e:
        print("[TTS] error:", e)
        sys.exit(1)