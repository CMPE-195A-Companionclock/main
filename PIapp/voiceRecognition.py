import os
import time
import signal
import subprocess
import requests
import json
from datetime import datetime
import audioop
import wave
from typing import List
import pvporcupine
from pvrecorder import PvRecorder
import tempfile
# Load local .env when running module directly
try:
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".pienv")
except Exception:
    pass
# Optional tiny popup UI for feedback
try:
    import tkinter as tk  # type: ignore
except Exception:
    tk = None  # type: ignore

# ====== CONFIG ======
ACCESS_KEY   = os.getenv("PICOVOICE_ACCESS_KEY")  # Set your Picovoice AccessKey via env var
# Align endpoint/device/seconds with voicePage defaults
TRANSCRIBE_EP = os.getenv("VOICE_SERVER_URL", os.getenv("SERVER_URL", "http://10.0.0.111:5000/transcribe"))
ARECORD_CARD = os.getenv("ARECORD_CARD", os.getenv("VOICE_ARECORD_DEVICE", "plughw:2,0"))  # Use plughw for resampling; override via env
DEVICE_INDEX = int(os.getenv("PVREC_DEVICE_INDEX", "-1"))  # pvrecorder input device index
# Built-in wake-words to use when no custom KEYWORD paths are available
KEYWORDS     = ["jarvis"]


_LOCAL_KWD = os.path.join(os.path.dirname(__file__), "keyword", "Companion-Clock_en_raspberry-pi_v3_0_0.ppn")
KEYWORD      = [
    os.path.expanduser("~/keyword/Companion-Clock_en_raspberry-pi_v3_0_0.ppn"),
    _LOCAL_KWD,
]


SENSITIVITY  = float(os.getenv("PORCUPINE_SENSITIVITY", "0.65"))  # 0.1..0.9 (higher = more sensitive)
RECORD_SEC   = int(os.getenv("VOICE_SEC", "10"))  # seconds to record after wake word
COOLDOWN_SEC = 1.5             # ignore new triggers for this long after each detection
SAVE_DIR     = "/tmp"          # where temp wav files are stored
# Voice command file path for UI IPC
VOICE_CMD_PATH = os.getenv("VOICE_CMD_PATH", os.path.join(tempfile.gettempdir(), "cc_voice_cmd.json"))
# Offline mode (no Flask). If set to "1", skip sending to server and optionally play back.
OFFLINE_ONLY = os.getenv("VOICE_OFFLINE", "0") == "1"

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
    """Record audio with arecord to the given path (16kHz, mono, 16-bit)."""

    chunk_ms = 100                 # analysis window size
    silence_duration = 0.8         # seconds of silence to stop
    silence_rms_threshold = 500    # adjust based on mic level

    min_duration = 0.4
    max_duration = 8.0 

    bytes_per_sample = 2
    sample_rate = 16000
    channels = 1
    samples_per_chunk = int(sample_rate * (chunk_ms / 1000.0))
    chunk_size = samples_per_chunk * bytes_per_sample

    cmd = [
        "arecord",
        "-D", ARECORD_CARD,
        "-f", "S16_LE",
        "-r", str(sample_rate),
        "-c", str(channels),
        "-t", "raw",  # raw PCM on stdout
        "-q",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    audio_chunks: List[bytes] = []
    t_start = time.time()
    last_voice_time = None
    try:
        while True:
            chunk = proc.stdout.read(chunk_size)
            if not chunk:
                break  # arecord ended unexpectedly

            audio_chunks.append(chunk)

            elapsed = time.time() - t_start
            if elapsed >= max_duration:
                # Hard stop to avoid runaway recording
                break
            # Compute loudness (RMS)
            rms = audioop.rms(chunk, bytes_per_sample)

            now = time.time()
            if rms >= silence_rms_threshold:
                last_voice_time = now
            else:
                if (
                    last_voice_time is not None
                    and (now - last_voice_time) >= silence_duration
                    and elapsed >= min_duration
                ):
                    break
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=0.5)
        except Exception:
            pass

    if not audio_chunks:
        print("[voice] No audio captured; writing short silent WAV")
        audio_chunks = [b"\x00" * chunk_size]

    # Write collected PCM to a proper WAV file
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bytes_per_sample)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(audio_chunks))

def send_to_server(path: str) -> str:
    if OFFLINE_ONLY:
        try:
            size = os.path.getsize(path)
        except Exception:
            size = -1
        print(f"[voice] OFFLINE: saved at {path} (size={size}). Skipping server.")
        return ""
    try:
        with open(path, "rb") as f:
            resp = requests.post(TRANSCRIBE_EP, files={"audio": f}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        text = (data.get("text") or "").strip()
        nlu  = data.get("nlu") or {"intent": "none"}

        payload = {
            "nlu": nlu,
            "text": text,
        }

        intent = (nlu.get("intent") or "").lower()

        if intent == "goto" and nlu.get("view"):
            payload.update({"cmd": "goto", "view": nlu["view"]})

        elif intent == "set_alarm":
            missing = nlu.get("missing") or []
            alarm_time = nlu.get("alarm_time")

            # Case 1: we’re missing AM/PM ask the user
            if "meridiem" in missing:
                payload.update({
                    "cmd": "alarm_missing",
                    "missing": missing,
                    "hour": nlu.get("hour"),
                    "minute": nlu.get("minute"),
                })
            elif alarm_time:
                # Fully specified time like "set alarm for 5:30 am"
                payload.update({"cmd": "set_alarm", "time": alarm_time})
                
        elif intent == "plan_commute":
            missing = nlu.get("missing") or []

            dest    = nlu.get("destination")
            arrival = nlu.get("arrival_time")
            origin  = nlu.get("origin")

            alarm_prop = nlu.get("alarm_proposal") or {}
            plan = alarm_prop.get("plan") or {}
            prep = alarm_prop.get("plan", {}).get("prep_minutes") or nlu.get("prep_minutes")

            # Always pass along what Gemini already knows
            if dest:
                payload["destination"] = dest
            if arrival:
                payload["arrival_time"] = arrival
            if prep is not None:
                payload["prep_minutes"] = prep
            if origin:
                payload["origin"] = origin
            if plan:
                payload["plan"] = plan

            payload["missing"] = missing

            leave = (
                alarm_prop.get("alarm_time")
                or nlu.get("latest_leave_time")
                or nlu.get("leave_time")
            )
            
            if leave:
                payload["leave_time"] = leave
                payload["cmd"] = "set_commute"
            elif missing:
                # Follow-up will be handled by the UI
                payload["cmd"] = "commute_missing"
            else:
                payload["cmd"] = "commute_missing"

        elif intent == "set_commute":
            dest = nlu.get("destination")
            arrival = nlu.get("arrival_time")
            leave = (
                nlu.get("latest_leave_time")
                or nlu.get("leave_time")
            )
            origin = nlu.get("origin")
            prep = nlu.get("prep_minutes")
            if dest:
                payload["destination"] = dest
            if arrival:
                payload["arrival_time"] = arrival
            if leave:
                payload["leave_time"] = leave
            if origin:
                payload["origin"] = origin
            if prep is not None:
                payload["prep_minutes"] = prep
            if dest or arrival or leave:
                payload["cmd"] = "set_commute"
        elif intent == "toggle_commute_updates":
            state = nlu.get("state")
            payload["cmd"] = "toggle_commute_updates"
            payload["state"] = state
        elif intent == "gemini_error":
            payload["cmd"] = "gemini_error"
            payload["error"] = nlu.get("error")
            payload["message"] = nlu.get("message")

        try:
            with open(VOICE_CMD_PATH, "w", encoding="utf-8") as g:
                json.dump(payload, g, ensure_ascii=False)
            print("[voice] wrote UI payload:", payload)
        except Exception as e:
            print("[voice] could not write VOICE_CMD_PATH:", e)

        try:
            os.remove(path)
        except Exception:
            pass

        return text

    except requests.RequestException as e:
        print(f"[voice] HTTP error posting audio: {e}")
        try:
            payload = {
                "cmd": "network_error",
                "error": str(e),
            }
            with open(VOICE_CMD_PATH, "w", encoding="utf-8") as g:
                json.dump(payload, g, ensure_ascii=False)
            print("[voice] wrote UI payload (network_error):", payload)
        except Exception as e2:
            print(f"[voice] could not write VOICE_CMD_PATH for network_error: {e2}")

        return ""
    except Exception as e:
        print(f"[voice] Unexpected error posting audio: {e}")
        return ""

def main():
    global STOP
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

    def _restart_recorder():
        rec = PvRecorder(device_index=sel_index, frame_length=porcupine.frame_length)
        rec.start()
        return rec

    try:
        if sel_index < 0:
            raise RuntimeError("PVREC_DEVICE_INDEX < 0 -> disable PvRecorder")

        # Allow selecting device by substring name via PVREC_DEVICE_NAME
        want_name = os.getenv("PVREC_DEVICE_NAME", "").strip().lower()
        if want_name:
            for i, name in enumerate(PvRecorder.get_available_devices()):
                if want_name in name.lower():
                    sel_index = i
                    print(f"Selected device by name match '{want_name}': index {sel_index} ({name})")
                    break
        recorder = _restart_recorder()
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
                            try:
                                arec_proc.wait(timeout=0.5)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    arec_proc = None
                    # Brief pause to let ALSA release the device before recording
                    time.sleep(0.25)
                else:
                    # Fully release the device before spawning arecord
                    try:
                        recorder.stop()
                    except Exception:
                        pass
                    try:
                        recorder.delete()
                    except Exception:
                        pass
                    recorder = None

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
                            try:
                                recorder = _restart_recorder()
                            except Exception as e:
                                print(f"Could not restart recorder: {e}")
                                STOP = True
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
                if recorder:
                    recorder.stop()
        except Exception:
            pass
        if not use_arecord_stream:
            try:
                if recorder:
                    recorder.delete()
            except Exception:
                pass
        porcupine.delete()
        try:
            if popup:
                popup.destroy()
        except Exception:
            pass
        print("Cleaned up. Bye!")

if __name__ == "__main__":
    main()
