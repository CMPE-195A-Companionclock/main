1. Install Pi imager, PuTTY, WinSCP, Real VNC Viewer
2. install pi os(32 bit) to the micro SD card with WIFI setting
   Edit the Wi-Fi setting info and enable SSH in customisation
4. Connect Putty
5. Move the program file with Win SCP to the pi OS
6. Use Real VNC Viwer to controll the PI os
7. Install sox
      sudo apt install -y alsa-utils sox

CompanionClock – Overview
- Multi-page smart display for Raspberry Pi: Clock, Weather, Calendar, simple Voice UI, optional PC-side ASR server.
- Fonts unified across all pages to `font/CaviarDreams_Bold.ttf` for a consistent look.
- Weather page layout updated: labels left-aligned, values right-aligned with compact spacing.

Raspberry Pi – Software Setup
- Install Tk/Pillow and Python deps
  - `sudo apt install -y python3-tk python3-pip libjpeg-dev zlib1g-dev`
  - `pip3 install -r PIapp/requirements_PI.txt`
- Optional audio tools (already partially listed above)
  - `sudo apt install -y alsa-utils sox`

Run (Pi side)
- Default touch UI (fullscreen): `python3 main.py`
- Windowed UI: `python3 main.py ui --windowed`
- Individual pages (for testing)
  - Clock: `python3 main.py clock --windowed`
  - Weather rendering is part of the UI; no separate CLI.
  - Calendar (print data only): `python3 main.py calendar`
  - Voice recognition (wake-word → record): `python3 main.py voice`

PC-side ASR Server (optional)
- Install requirements: `pip install -r PCapp/requirements_PC.txt`
- Run: `python -m PCapp.Server` or `python main.py server`
- Environment (optional):
  - `WHISPER_MODEL=small` (default). Try `medium`/`large-v3` for accuracy vs. speed.
  - `FORCE_CPU=1` to force CPU if CUDA is present but undesired.
  - `GEMINI_API_KEY` to enable `/transcribe_nlu` intent extraction.

Environment Variables (Pi side)
- Weather
  - `WEATHERAPI_KEY` (recommended): WeatherAPI key for reliable forecasts
  - `WEATHER_LOCATION` (e.g. `Tokyo` or `35.68,139.76`) or `WEATHER_LAT`/`WEATHER_LON`
- Voice
  - `PICOVOICE_ACCESS_KEY`: Required for Porcupine wake word
  - `PVREC_DEVICE_INDEX` or `PVREC_DEVICE_NAME`: Select input device
  - `ARECORD_CARD` (default `plughw:1,0`): arecord device for fallback recording
  - `VOICE_OFFLINE=1`: Skip sending audio to server; record only
  - `VOICE_PLAYBACK=1`: Play recorded audio after capture
  - `VOICE_CMD_PATH` (default `/tmp/cc_voice_cmd.json`): IPC file for UI navigation

Notes
- Fonts: Pages use `font/CaviarDreams_Bold.ttf` uniformly.
- Weather icons are fetched over HTTP; ensure network access to `api.weatherapi.com` and icon URLs.
- If Tkinter is missing, install `python3-tk` (Debian/RPi) or ensure your Python includes Tk.

Troubleshooting
- UI doesn’t start: verify Tkinter/Pillow installation.
- Weather fails to show: set `WEATHERAPI_KEY` and check network; location can be overridden via env.
- Degree symbol: uses UTF-8 `°C`. If your terminal shows mojibake, ensure UTF-8 locale.
- Stray files: deleting `PIapp/tempCodeRunnerFile.py` and `PIapp/temperature .py` (empty) is safe.
