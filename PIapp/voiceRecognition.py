import os
import time
import signal
import subprocess
import requests
from datetime import datetime
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
ARECORD_CARD = "hw:1,0"        # ALSA device for ReSpeaker (adjust with `arecord -l`)
DEVICE_INDEX = 0               # pvrecorder input device index (`python -m pvrecorder --show_audio_devices`)
KEYWORDS     = ["jarvis"]      # built-in keywords: "porcupine", "bumblebee", "jarvis", etc.
SENSITIVITY  = 0.65            # 0.1..0.9 (higher = more sensitive)
RECORD_SEC   = 5               # seconds to record after wake word
COOLDOWN_SEC = 1.5             # ignore new triggers for this long after each detection
SAVE_DIR     = "/tmp"          # where temp wav files are stored
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
        "-c", "2",
        "-d", str(RECORD_SEC),
        path
    ], check=True)

def send_to_server(path: str) -> str:
    """POST the recorded file to Flask server; return ASR text."""
    with open(path, "rb") as f:
        r = requests.post(SERVER_URL, files={"audio": f}, timeout=120)
    r.raise_for_status()
    data = r.json()
    text = data.get("text", "")
    print("ASR:", text)
    return text

def main():
    if not ACCESS_KEY:
        raise RuntimeError("PICOVOICE_ACCESS_KEY is not set. Export it before running.")

    # Setup signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Create Porcupine wake-word engine
    porcupine = pvporcupine.create(
        access_key=ACCESS_KEY,
        keywords=KEYWORDS,
        sensitivities=[SENSITIVITY] * len(KEYWORDS)
    )

    # PvRecorder for continuous 16k PCM frames
    recorder = PvRecorder(device_index=DEVICE_INDEX, frame_length=porcupine.frame_length)
    recorder.start()
    print(f"Listening for {KEYWORDS} on device index {DEVICE_INDEX}... (Ctrl+C to exit)")

    popup = _Popup()
    last_trigger = 0.0

    try:
        while not STOP:
            pcm = recorder.read()          # 16-bit PCM @ 16 kHz
            result = porcupine.process(pcm)
            if result >= 0:                # wake word index
                now = time.time()
                if now - last_trigger < COOLDOWN_SEC:
                    continue               # debounce
                last_trigger = now

                print("Wake word detected!")
                if popup:
                    popup.show("Listening…")
                # Free the device so 'arecord' can open it
                recorder.stop()

                # (Optional) give a short beep/feedback here if you want:
                # subprocess.run(["aplay", "-q", "/usr/share/sounds/alsa/Front_Center.wav"], check=False)

                # Record then send
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                wav_path = f"{SAVE_DIR}/wake_{ts}.wav"
                try:
                    record_wav(wav_path)
                    if popup:
                        popup.update("Recognizing…")
                    text = send_to_server(wav_path)
                    if popup:
                        popup.update(f"Heard: {text[:60]}" + ("…" if len(text) > 60 else ""))
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
                        recorder.start()
                    if popup:
                        popup.hide()
            # tiny sleep to avoid busy-looping; pvrecorder already blocks, so keep it minimal
            # time.sleep(0.001)

    finally:
        try:
            recorder.stop()
        except Exception:
            pass
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
