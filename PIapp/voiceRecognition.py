import os
import time
import signal
import subprocess
import requests
from datetime import datetime
import pvporcupine
from pvrecorder import PvRecorder

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
# =====================

STOP = False

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

def send_to_server(path: str):
    """POST the recorded file to Flask server; print ASR text."""
    with open(path, "rb") as f:
        r = requests.post(SERVER_URL, files={"audio": f}, timeout=120)
    r.raise_for_status()
    data = r.json()
    print("ASR:", data.get("text"))

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
                # Free the device so 'arecord' can open it
                recorder.stop()

                # (Optional) give a short beep/feedback here if you want:
                # subprocess.run(["aplay", "-q", "/usr/share/sounds/alsa/Front_Center.wav"], check=False)

                # Record then send
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                wav_path = f"{SAVE_DIR}/wake_{ts}.wav"
                try:
                    record_wav(wav_path)
                    send_to_server(wav_path)
                except subprocess.CalledProcessError as e:
                    print(f"arecord failed: {e}")
                except requests.RequestException as e:
                    print(f"HTTP error: {e}")
                finally:
                    # Resume wake-word listening
                    if not STOP:
                        recorder.start()
            # tiny sleep to avoid busy-looping; pvrecorder already blocks, so keep it minimal
            # time.sleep(0.001)

    finally:
        try:
            recorder.stop()
        except Exception:
            pass
        recorder.delete()
        porcupine.delete()
        print("Cleaned up. Bye!")

if __name__ == "__main__":
    main()