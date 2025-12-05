1. Install Pi imager, PuTTY, WinSCP, Real VNC Viewer
2. install pi os(regacy, 32 bit) to the micro SD card with WIFI setting
   Edit the Wi-Fi setting info and enable SSH in customisation
4. Connect Putty
5. Install and Enable VNC to use real VNC Viewer
      sudo apt update
      sudo apt install -y realvnc-vnc-server
      sudo raspi-config  # → Interface Options → VNC → <Yes> → Finish
      sudo reboot
6. Move the program file with Win SCP to the pi OS
7. Use Real VNC Viwer to controll the PI os
8. Install sox
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
5. Install and Enable VNC to use real VNC Viewer
      sudo apt update
      sudo apt install -y realvnc-vnc-server
      sudo raspi-config  # → Interface Options → VNC → <Yes> → Finish
      sudo reboot
6. Move the program file with Win SCP to the pi OS
7. Use Real VNC Viwer to controll the PI os
8. See https://docs.keyestudio.com/projects/KS0314/en/latest/docs/KS0314.html for installing the driver of the mic

___________________________________________________________________________________________________________________
## Google Calendar Integration Setup

1. Get GoogleCal API credentials:
   - Visit https://console.cloud.google.com
   - Create a project and enable Google Calendar API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download as `credentials.json`

2. Install dependencies:
```bash
   pip3 install --break-system-packages google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

3. Authenticate:
```bash
   python3 -c "from PIapp.calendar_service import get_calendar_service; get_calendar_service()"
```

### Environment Variables

Add to your `.env` file:
```bash
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.pickle
CALENDAR_REFRESH_INTERVAL=300
CALENDAR_DAYS_AHEAD=7
CALENDAR_MAX_EVENTS=50
```

### Usage

- View calendar in terminal: `python3 main.py calendar`
- Calendar page in UI: Navigate to Calendar in the main interface

### For AI Alarm Integration
```python
from PIapp.calendar_service import get_calendar_service

service = get_calendar_service()
next_event = service.get_next_event()

if next_event:
    event_time = next_event['start_datetime']
    location = next_event['location']
    # Feed to AI alarm logic
```
