import os
import time
import signal
import subprocess
import requests
import json
from datetime import datetime
from typing import Optional
import pvporcupine
from pvrecorder import PvRecorder

# Optional tiny popup UI for feedback
try:
    import tkinter as tk  # type: ignore
except Exception:
    tk = None  # type: ignore

# ====== CONFIG ======
ACCESS_KEY   = os.getenv("PICOVOICE_ACCESS_KEY")  # Set your Picovoice AccessKey via env var
SERVER_URL   = "http://192.168.0.10:5000/transcribe"  # <-- change to your PC's Flask URL
ARECORD_CARD = os.getenv("ARECORD_CARD", "plughw:1,0")  # Use plughw for resampling; override via env
DEVICE_INDEX = int(os.getenv("PVREC_DEVICE_INDEX", "0"))  # pvrecorder input device index
# Built-in wake-words to use when no custom KEYWORD paths are available
KEYWORDS     = ["jarvis"]
# Optional custom Porcupine keyword model paths (.ppn).
# Try both home directory and the repo-local PIapp/keyword path by default.
_LOCAL_KWD = os.path.join(os.path.dirname(__file__), "keyword", "Companion-Clock_en_raspberry-pi_v3_0_0.ppn")
KEYWORD      = [
    os.path.expanduser("~/keyword/Companion-Clock_en_raspberry-pi_v3_0_0.ppn"),
    _LOCAL_KWD,
]
SENSITIVITY  = float(os.getenv("PORCUPINE_SENSITIVITY", "0.65"))  # 0.1..0.9 (higher = more sensitive)
RECORD_SEC   = 5               # seconds to record after wake word
COOLDOWN_SEC = 1.5             # ignore new triggers for this long after each detection
SAVE_DIR     = "/tmp"          # where temp wav files are stored
# Voice command file path for UI IPC
VOICE_CMD_PATH = os.getenv("VOICE_CMD_PATH", "/tmp/cc_voice_cmd.json")
# Offline mode (no Flask). If set to "1", skip sending to server and optionally play back.
OFFLINE_ONLY = os.getenv("VOICE_OFFLINE", "0") == "1"
PLAYBACK_AFTER_RECORD = os.getenv("VOICE_PLAYBACK", "0") == "1"
# =====================

STOP = False


class _Popup:
    def __init__(self):
        self.root = None
        self.top = None
        self.label = None
        try:
            if tk is None:
                return
            # Only initialize if a display is available
            self.root = tk.Tk()
            self.root.withdraw()
            self.top = tk.Toplevel(self.root)
            self.top.overrideredirect(True)
            self.top.attributes('-topmost', True)
            self.top.configure(bg='black')
            self.label = tk.Label(self.top, text='', fg='#FFFFFF', bg='black', font=('Arial', 18))
            self.label.pack(padx=24, pady=16)
            # Position near top-center (640x120)
            try:
                self.top.geometry("640x120+200+100")
            except Exception:
                pass
            self.hide()
        except Exception:
            self.root = None
            self.top = None
            self.label = None

    def show(self, text: str):
        if not self.top or not self.label:
            return
        self.label.config(text=text)
        self.top.deiconify()
        self._pump()

    def update(self, text: str):
        if not self.top or not self.label:
            return
        self.label.config(text=text)
        self._pump()

    def hide(self):
        if not self.top:
            return
        try:
            self.top.withdraw()
            self._pump()
        except Exception:
            pass

    def destroy(self):
        try:
            if self.top:
                self.top.destroy()
            if self.root:
                self.root.destroy()
        except Exception:
            pass

    def _pump(self):
        try:
            if self.root:
                self.root.update_idletasks()
                self.root.update()
        except Exception:
            pass

def handle_signal(sig, frame):
    # Graceful shutdown on Ctrl+C / SIGTERM
    global STOP
    STOP = True
    print("\nStopping...")

def record_wav(path: str):
    """Record audio with arecord to the given path (16kHz, 2ch, 16-bit)."""
    subprocess.run([
        "arecord",
        "-D", ARECORD_CARD,
        "-f", "S16_LE",
        "-r", "16000",
        "-c", "1",
        "-d", str(RECORD_SEC),
        path
    ], check=True)

def send_to_server(path: str) -> str:
    """Offline stub: skip HTTP and just report the saved file path.

    Returns empty text to indicate no transcription performed.
    """
    try:
        size = os.path.getsize(path)
    except Exception:
        size = -1
    print(f"Offline mode: recorded file saved at {path} (size={size} bytes). Skipping server.")
    return ""


def _map_text_to_view(text: str) -> Optional[str]:
    """Very simple keyword mapping from ASR text to a target view.

    Returns one of: 'clock', 'weather', 'calendar', 'alarm', 'voice' or None.
    """
    t = text.strip().lower()
    if not t:
        return None
    # Japanese/English keywords
    pairs = [
        ("clock", ("clock", "ã‚¯ãƒ­ãƒƒã‚¯", "æ™‚è¨ˆ")),
        ("weather", ("weather", "å¤©æ°—", "ã¦ã‚“ã")),
        ("calendar", ("calendar", "ã‚«ãƒ¬ãƒ³ãƒ€ãƒ¼", "äºˆå®š")),
        ("alarm", ("alarm", "ã‚¢ãƒ©ãƒ¼ãƒ ")),
        ("voice", ("voice", "ãƒœã‚¤ã‚¹", "éŒ²éŸ³")),
    ]
    for view, keys in pairs:
        for k in keys:
            if k in t:
                return view
    return None


def _emit_ui_command(view: str, heard_text: str = ""):
    try:
        payload = {"cmd": "goto", "view": view, "text": heard_text}
        with open(VOICE_CMD_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass

def main():
    if not ACCESS_KEY:
        raise RuntimeError("PICOVOICE_ACCESS_KEY is not set. Export it before running.")

    # Setup signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Create Porcupine wake-word engine
    # Print available devices up front for easier debugging
    try:
        devices = PvRecorder.get_available_devices()
        print("PvRecorder devices:")
        for i, name in enumerate(devices):
            print(f"  [{i}] {name}")
    except Exception as e:
        print(f"Could not list PvRecorder devices: {e}")
    # Prefer custom keyword paths (KEYWORD) when provided and files exist; otherwise use built-in keywords.
    def _flatten_paths(obj):
        if isinstance(obj, str):
            yield os.path.expanduser(obj)
        elif isinstance(obj, (list, tuple)):
            for it in obj:
                yield from _flatten_paths(it)

    custom_paths_raw = []
    try:
        if 'KEYWORD' in globals():
            custom_paths_raw = list(_flatten_paths(KEYWORD))
    except Exception:
        custom_paths_raw = []
    existing_paths = [p for p in custom_paths_raw if isinstance(p, str) and os.path.exists(p)]

    if existing_paths:
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keyword_paths=existing_paths,
            sensitivities=[SENSITIVITY] * len(existing_paths)
        )
        listen_desc = f"custom keywords x{len(existing_paths)}: {existing_paths}"
        if len(existing_paths) != len(custom_paths_raw):
            missing = [p for p in custom_paths_raw if p not in existing_paths]
            if missing:
                print(f"Warning: keyword paths not found and ignored: {missing}")
    else:
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keywords=KEYWORDS,
            sensitivities=[SENSITIVITY] * len(KEYWORDS)
        )
        listen_desc = str(KEYWORDS)

    # Try PvRecorder first. If it fails due to GLIBC or other runtime issues, fall back to arecord-based streaming.
    use_arecord_stream = False
    sel_index = DEVICE_INDEX
    try:
        # Allow selecting device by substring name via PVREC_DEVICE_NAME
        want_name = os.getenv("PVREC_DEVICE_NAME", "").strip().lower()
        if want_name:
            for i, name in enumerate(PvRecorder.get_available_devices()):
                if want_name in name.lower():
                    sel_index = i
                    print(f"Selected device by name match '{want_name}': index {sel_index} ({name})")
                    break
        recorder = PvRecorder(device_index=sel_index, frame_length=porcupine.frame_length)
        recorder.start()
        try:
            dev_name = PvRecorder.get_available_devices()[sel_index]
        except Exception:
            dev_name = "?"
        print(f"Listening for {listen_desc} on device index {sel_index} ({dev_name})... (Ctrl+C to exit)")
    except Exception as e:
        print(f"PvRecorder unavailable ({e}); falling back to arecord streaming.")
        use_arecord_stream = True

    def _start_arecord_stream():
        # 16kHz, 16-bit, mono raw stream on stdout
        card = ARECORD_CARD
        cmd = [
            "arecord",
            "-D", card,
            "-f", "S16_LE",
            "-r", "16000",
            "-c", "1",
            "-t", "raw",
            "-q",
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    arec_proc = None
    if use_arecord_stream:
        arec_proc = _start_arecord_stream()
        print(f"Listening for {listen_desc} via arecord stream on {ARECORD_CARD} (16k/mono)...")

    popup = _Popup()
    last_trigger = 0.0

    try:
        while not STOP:
            if use_arecord_stream:
                # Read raw little-endian int16 samples from arecord
                need = porcupine.frame_length * 2  # bytes
                buf = arec_proc.stdout.read(need) if arec_proc and arec_proc.stdout else b""
                if len(buf) != need:
                    # stream hiccup; try restarting
                    if arec_proc:
                        try:
                            arec_proc.terminate()
                        except Exception:
                            pass
                    arec_proc = _start_arecord_stream()
                    continue
                # convert to list of int16
                pcm = list(int.from_bytes(buf[i:i+2], byteorder='little', signed=True) for i in range(0, need, 2))
            else:
                pcm = recorder.read()          # 16-bit PCM @ 16 kHz
            result = porcupine.process(pcm)
            if result >= 0:                # wake word index
                now = time.time()
                if now - last_trigger < COOLDOWN_SEC:
                    continue               # debounce
                last_trigger = now

                print("Wake word detected!")
                if popup:
                    popup.show("Listening...")
                # Free the device so 'arecord' can open it
                if use_arecord_stream:
                    try:
                        if arec_proc:
                            arec_proc.terminate()
                    except Exception:
                        pass
                    arec_proc = None
                else:
                    recorder.stop()

                # (Optional) give a short beep/feedback here if you want:
                # subprocess.run(["aplay", "-q", "/usr/share/sounds/alsa/Front_Center.wav"], check=False)

                # Record then send
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                wav_path = f"{SAVE_DIR}/wake_{ts}.wav"
                try:
                    record_wav(wav_path)
                    if popup:
                        popup.update("Recognizing...")
                    text = send_to_server(wav_path)
                    try:
                        # Map recognized text to a UI view and emit a command file for the Tk UI
                        def _map_simple(txt: str):
                            t = (txt or "").strip().lower()
                            if not t:
                                return None
                            pairs = [
                                ("clock", ("clock", "\u6642\u8a08", "\u30af\u30ed\u30c3\u30af")),
                                ("weather", ("weather", "\u5929\u6c17")),
                                ("calendar", ("calendar", "\u30ab\u30ec\u30f3\u30c0\u30fc")),
                                ("alarm", ("alarm", "\u30a2\u30e9\u30fc\u30e0")),
                                ("voice", ("voice", "\u30dc\u30a4\u30b9", "\u9332\u97f3")),
                            ]
                            for v, keys in pairs:
                                for k in keys:
                                    if k in t:
                                        return v
                            return None
                        v = _map_simple(text)
                        if v:
                            _emit_ui_command(v, text)
                    except Exception:
                        pass
                    if popup:
                        suffix = "..." if len(text) > 60 else ""
                        popup.update(f"Heard: {text[:60]}{suffix}")
                        # Briefly show the result
                        time.sleep(1.2)
                except subprocess.CalledProcessError as e:
                    print(f"arecord failed: {e}")
                    if popup:
                        popup.update("Mic error")
                        time.sleep(0.8)
                except requests.RequestException as e:
                    print(f"HTTP error: {e}")
                    if popup:
                        popup.update("Network error")
                        time.sleep(0.8)
                finally:
                    # Resume wake-word listening
                    if not STOP:
                        if use_arecord_stream:
                            arec_proc = _start_arecord_stream()
                        else:
                            recorder.start()
                    if popup:
                        popup.hide()
            # tiny sleep to avoid busy-looping; pvrecorder already blocks, so keep it minimal
            # time.sleep(0.001)

    finally:
        try:
            if use_arecord_stream:
                if arec_proc:
                    arec_proc.terminate()
            else:
                recorder.stop()
        except Exception:
            pass
        if not use_arecord_stream:
            recorder.delete()
        porcupine.delete()
        try:
            if popup:
                popup.destroy()
        except Exception:
            pass
        print("Cleaned up. Bye!")

if __name__ == "__main__":
    main()
