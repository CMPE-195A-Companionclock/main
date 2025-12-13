CompanionClock
CompanionClock is a Raspberry Pi–based smart bedside clock with:
- Full-screen Clock, Alarm, Weather, and Calendar pages
- Smart commute alarms that plan leave times
- Voice control (wake word → speech → NLU → actions)
- PC-side server that does speech recognition (Whisper), NLU (Gemini or regex), and TTS (Coqui or Edge)
_______________________________________________
Hardware and tools
_______________________________________________
You need:
- Raspberry Pi (tested with Raspberry Pi OS “Legacy 32-bit”)
- Micro-SD card + reader
- USB microphone (Keyestudio mic is supported)
- Speaker or other audio output
- PC or laptop on the same network (for the server)
On the PC (Windows in these notes):
- Raspberry Pi Imager
- PuTTY (SSH)
- WinSCP (file transfer)
- RealVNC Viewer (remote desktop)

_______________________________________________
Flashing Pi OS and first boot (one time)
_______________________________________________

- Use Raspberry Pi Imager to flash “Raspberry Pi OS (Legacy, 32-bit)” to the SD card.

- In Imager’s advanced options:
  - Turn on Wi-Fi and enter SSID and password.
  - Turn on SSH.

- Boot the Pi with that SD card.
- From the PC, connect with PuTTY (IP address or “raspberrypi.local”).

_______________________________________________
Enable VNC and copy the project to the Pi
_______________________________________________

On the Pi (via SSH):
sudo apt update
sudo apt install -y realvnc-vnc-server
sudo raspi-config          (Interface Options → VNC → Yes → Finish)
sudo reboot

On the PC:
- Use WinSCP to copy the “Companioclock” folder onto the Pi (for example into “~/Companioclock”).
- Use RealVNC Viewer to connect to the Pi’s desktop.

_______________________________________________
Raspberry Pi software setup
_______________________________________________
On the Pi:
cd ~/Companioclock/main
sudo apt update
sudo apt install -y python3-tk python3-pip libjpeg-dev zlib1g-dev
sudo apt install -y alsa-utils sox

Create and activate a virtual environment:
python3 -m venv .venv
source .venv/bin/activate
pip install -r PIapp/requirements_PI.txt

If you use a Keyestudio mic, install its driver according to the vendor instructions.

_______________________________________________
PC-side ASR / TTS server
_______________________________________________
On the PC in the project root:
cd C:\Companioclock\main
python -m venv .venv
.\.venv\Scripts\activate
pip install -r PCapp/requirements_PC.txt

5.1 TTS engines
The server supports two text-to-speech engines:
Coqui-TTS (default, offline, outputs WAV)


Edge-TTS (online, Microsoft voices, MP3 converted to WAV)


Requirements on the PC:
Python 3.9–3.12
FFmpeg installed and on PATH
eSpeak-NG installed (needed by Coqui)


Example environment variables (Windows PowerShell):
$env:TTS_ENGINE="coqui"        # or "edge"
$env:COQUI_MODEL="tts_models/en/ljspeech/tacotron2-DDC"

Run the server:
python PCapp/Server.py
# or
python -m PCapp.Server

Example TTS calls:
Coqui:
curl -o out.wav "http://<HOST>:5000/tts?text=Hello+from+Coqui&engine=coqui"

Edge:
curl -o out.wav "http://<HOST>:5000/tts?text=Hello+from+Edge&engine=edge&voice=en-US-JennyNeural"

On the Pi you can test playback with:
aplay out.wav

5.2 NLU HTTP API
The server exposes a simple NLU endpoint:
GET /nlu?text=...
POST /nlu with JSON {"text": "..."}


Example response:
{
  "text": "set an alarm at 7:30 am",
  "engine": "gemini",
  "nlu": {
    "intent": "set_alarm",
    "alarm_time": "07:30"
  }
}

If GEMINI_API_KEY is not set, the server falls back to the built-in regex NLU instead of Gemini.

_______________________________________________
Environment variables
_______________________________________________
6.1 On the Pi
Weather:
export WEATHERAPI_KEY="your_WeatherAPI_key"

Optional overrides:
export WEATHER_LOCATION="San Jose, CA"
# or
export WEATHER_LAT="37.33"
export WEATHER_LON="-121.89"

Voice and audio:
export PICOVOICE_ACCESS_KEY="..."          # Porcupine wake word key
export ARECORD_CARD="plughw:2,0"           # ALSA device from `arecord -l`
export VOICE_SERVER_URL="http://<PC_IP>:5000/transcribe"
export PC_SERVER="http://<PC_IP>:5000"
export VOICE_CMD_PATH="/tmp/cc_voice_cmd.json"

Debug flags:
export VOICE_OFFLINE=1    # record but don’t call the server
export VOICE_PLAYBACK=1   # play back recorded audio

6.2 On the PC (server side)
set WHISPER_MODEL=small       # or medium, large-v3
set FORCE_CPU=1               # force CPU instead of GPU
set GEMINI_API_KEY=...        # enable Gemini NLU
set TTS_ENGINE=coqui          # or edge

_______________________________________________
Running the system
_______________________________________________

7.1 Start the server (PC)
cd C:\Companioclock\main
.\.venv\Scripts\activate
python PCapp/Server.py

7.2 Start the UI (Pi)
cd ~/Companioclock/main
source .venv/bin/activate
export VOICE_CMD_PATH=/tmp/cc_voice_cmd.json

Fullscreen:
python main.py ui
Windowed (useful over VNC):
python main.py ui --windowed

7.3 Start voice recognition (Pi)
cd ~/Companioclock/main
source .venv/bin/activate
export PICOVOICE_ACCESS_KEY="..."
export ARECORD_CARD="plughw:2,0"
export VOICE_CMD_PATH="/tmp/cc_voice_cmd.json"
export VOICE_SERVER_URL="http://<PC_IP>:5000/transcribe"

python PIapp/voiceRecognition.py

_______________________________________________
Features and voice commands
_______________________________________________
8.1 Pages
Clock:
- Big digital clock and date.
- Swipe between pages.
Alarm:
- Add and delete alarms.
- Toggle each alarm ON/OFF.
- Smart commute alarms with:
  - From / To locations,
  - Preparation time,
  - Optional smart commute auto-updates.

Weather:
- Current conditions centered (temperature, feels like, wind, humidity, sunrise, sunset).
- 3-day forecast centered across the screen.

Calendar:
_ Month view with event dots and short titles from Google Calendar.

8.2 Example voice commands
 (wake word not shown; typically you say “Companion clock, ...” first)
Alarms:
- “Set an alarm for 7 AM.”
- “Please add alarm for 8 in the morning.”
- “Set an alarm for 7:30 PM.”
- “Turn off alarms.” / “Disable all alarms.”
- “Turn on alarms.” / “Enable all alarms.”
- “Snooze alarm for 10 minutes.”
- “Stop alarm.”

Smart commute:
- “I have to get to San Jose State University by 8 AM tomorrow, plan my commute.”
- “Turn off smart commute updates.”
- “Turn on smart commute updates.”

Weather:
- “What’s the weather like today?”
- “What’s the weather tomorrow?”

Calendar:
- “What are my events today?”
- “What are my events tomorrow?”

Navigation:
- “Show alarms.”
- “Show the clock.”
- “Show the weather.”
- “Show my calendar.”
The exact phrases that work will depend on your NLU configuration (regex only vs Gemini).

_______________________________________________
Troubleshooting
_______________________________________________
UI won’t start:
- Make sure Tkinter is installed: sudo apt install -y python3-tk

- Reinstall Python dependencies: pip install -r PIapp/requirements_PI.txt

Weather page shows “unavailable”:
- Check that WEATHERAPI_KEY is set and valid.
- Make sure the Pi has internet access.

Voice doesn’t react:
- Verify PICOVOICE_ACCESS_KEY and ARECORD_CARD.
- Check that VOICE_SERVER_URL points to the right PC IP and port.
- Check PC firewall rules so the Pi can reach port 5000.

No alarms after “set alarm ...”:
- On the PC server, look for intent: "set_alarm" in the log.
- On the Pi UI log, look for [ui] VOICE_CMD payload: {'cmd': 'set_alarm', ...}.
- Make sure both UI and voice processes use the same VOICE_CMD_PATH.

No TTS:
- Test /tts from the Pi using curl and play the WAV with aplay.
- Check FFmpeg and Coqui/Edge installation on the PC.

_______________________________________________
Project layout (high level)
_______________________________________________
- main.py
  - Entry point for the UI and command-line modes.
- PIapp/
  - clock.py – clock page.
  - Alarm.py – alarm page UI and alarm logic.
  - weather.py – weather page.
  - calendarPage.py – calendar page.
  - voiceRecognition.py – wake word, recording, sending audio to server, writing cc_voice_cmd.json.
  - nlu.py – regex NLU (alarms, navigation, weather and event queries, smart commute toggles).
  - calendar_service.py – Google Calendar integration.
  - pi_tts.py – TTS client talking to the PC server.
- PCapp/
  - Server.py – Flask-based server for transcription, NLU, and TTS.
- font/
  - CaviarDreams_Bold.ttf – main UI font.
