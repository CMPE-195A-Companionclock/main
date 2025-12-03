"""PIapp package: Raspberry Pi side modules (UI, sensors, voice)."""

import os

# Backend base URL for NLU/ASR/TTS endpoints (override via env BACKEND_URL or VOICE_SERVER_URL).
BACKEND_URL = os.getenv("BACKEND_URL", os.getenv("VOICE_SERVER_URL", "http://127.0.0.1:5000"))

