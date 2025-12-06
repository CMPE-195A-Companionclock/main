import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from PIapp.nlu import get_intent as nlu_get_intent
from app_router import goto_view, schedule_alarm

BASE_DIR = Path(__file__).resolve().parent / "PIapp"
load_dotenv(BASE_DIR / ".env")

VOICE_CMD_PATH = os.getenv("VOICE_CMD_PATH", os.path.join(tempfile.gettempdir(), "cc_voice_cmd.json"))


def run_clock(windowed: bool = False):
    from PIapp.clock import run
    run(fullscreen=not windowed)


def run_voice():
    from PIapp.voiceRecognition import main as voice_main
    voice_main()


def run_server():
    # This runs the Flask ASR server locally. Intended for PC side.
    from PCapp.Server import app
    app.run(host="0.0.0.0", port=5000, threaded=True)


def show_calendar():
    from PIapp.calendarPage import main as cal_main
    cal_main()

#legacy debug
def route_intent(intent: dict):
    it = (intent or {}).get("intent")
    if it == "goto":
        view = (intent.get("view") or "").lower()
        goto_view(view if view in {"clock", "weather", "calendar", "alarm"} else "clock")
    elif it == "set_alarm":
        t = intent.get("alarm_time")
        if t:
            try:
                schedule_alarm(t)
            except Exception as e:
                print("Failed to schedule alarm:", e)

#legacy helper
def handle_recognized_text(text: str):
    intent = nlu_get_intent(text)
    print("NLU:", intent)
    route_intent(intent)


def main(argv=None):
    parser = argparse.ArgumentParser(description="CompanionClock launcher")
    sub = parser.add_subparsers(dest="cmd")

    p_clock = sub.add_parser("clock", help="Run clock UI")
    p_clock.add_argument("--windowed", action="store_true", help="Run windowed (not fullscreen)")

    sub.add_parser("voice", help="Run voice recognition (wake word -> record -> send)")
    sub.add_parser("server", help="Run PC-side ASR server (Flask + faster-whisper)")
    sub.add_parser("calendar", help="Print generated calendar DataFrame for the current month")
    p_ui = sub.add_parser("ui", help="Run touch-enabled main UI (default)")
    p_ui.add_argument("--windowed", action="store_true", help="Run windowed (not fullscreen)")

    args = parser.parse_args(argv)

    if args.cmd is None:
        return run_touch_ui(fullscreen=True)
    if args.cmd == "clock":
        run_clock(windowed=args.windowed)
    elif args.cmd == "voice":
        run_voice()
    elif args.cmd == "server":
        run_server()
    elif args.cmd == "calendar":
        show_calendar()
    elif args.cmd == "ui":
        return run_touch_ui(fullscreen=not args.windowed)
    else:
        parser.print_help()
        return 2
    return 0


print("UI VOICE_CMD_PATH:", VOICE_CMD_PATH)


def run_touch_ui(fullscreen: bool = True):
    from PIapp.pi_tts import speak
    try:
        import tkinter as tk
    except Exception as e:
        print("Tkinter is not available. Install python3-tk (Debian/RPi) or ensure Tk is included.")
        print(f"Detail: {e}")
        return 1
    try:
        from PIL import ImageTk
    except Exception as e:
        print("Pillow is not installed. Run: pip install pillow")
        print(f"Detail: {e}")
        return 1
    # Import page modules directly
    try:
        from PIapp.clock import drawClock as draw_clock_page
        import PIapp.weather as weather_mod
        from PIapp.calendarPage import draw_calendar_image as draw_calendar_page
        from PIapp.Alarm import draw_alarm as draw_alarm_page, get_layout as alarm_layout
    except Exception as e:
        print("Failed to import page modules (clock/weather/calendar/alarm).")
        print(f"Detail: {e}")
        return 1

    WINDOW_W, WINDOW_H = 1024, 600
    BASE_DIR_ABS = os.path.abspath(os.path.dirname(__file__))
    LOCAL_TMP = os.path.join(BASE_DIR_ABS, "PIapp", "tmp")
    try:
        os.makedirs(LOCAL_TMP, exist_ok=True)
    except Exception:
        pass

    root = tk.Tk()
    root.title("CompanionClock")
    root.geometry(f"{WINDOW_W}x{WINDOW_H}")
    if fullscreen:
        root.attributes("-fullscreen", True)
    root.configure(bg="black")

    label = tk.Label(root)
    label.pack()

    try:
        speak("Companion Clock is ready.")
    except Exception as e:
        print("TTS startup error:", e)

    # State
    mode = {"view": "clock"}  # calendar | weather | clock | alarm
    api_key: Optional[str] = os.getenv("WEATHERAPI_KEY")
    weather_data: Optional[dict] = None
    last_fetch = 0.0
    alarms = {"items": [{"hour": 7, "minute": 0, "enabled": False}], "i": 0, "checked": set()}
    RANG_RECENT = set()
    _last_date = {"d": time.strftime("%Y-%m-%d")}

    # Voice command inbox (simple file-based IPC with voiceRecognition.py)
    voice_cmd_state = {"last_mtime": 0.0}
    view_state = {"last": None}
    cache = {
        "weather": {"img": None, "stamp": None},
        "calendar": {"img": None, "ym": None},
        "alarm": {"img": None, "sig": None},
    }
    alarm_sound = {"path": None}

    def _ensure_alarm_sound() -> Optional[str]:
        """Create a small WAV beep for the alarm if it doesn't exist."""
        path = os.path.join(LOCAL_TMP, "alarm_beep.wav")
        if alarm_sound.get("path") and os.path.exists(alarm_sound["path"]):
            return alarm_sound["path"]
        try:
            os.makedirs(LOCAL_TMP, exist_ok=True)
        except Exception:
            pass
        try:
            if not os.path.exists(path):
                import math
                import wave
                import array

                sample_rate = 16000
                duration = 1.0  # seconds
                freq = 880.0
                volume = 0.35
                samples = array.array("h")
                total = int(sample_rate * duration)
                for i in range(total):
                    val = int(volume * 32767 * math.sin(2 * math.pi * freq * (i / sample_rate)))
                    samples.append(val)
                with wave.open(path, "w") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(samples.tobytes())
            alarm_sound["path"] = path
            return path
        except Exception as e:
            print("Alarm sound generation failed:", e)
            return None

    def play_alarm_sound() -> bool:
        """Play the generated alarm beep; returns True on success."""
        path = _ensure_alarm_sound()
        if not path:
            return False
        # Windows fallback: winsound
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
            except Exception as e:
                print("Alarm sound playback failed (winsound):", e)
        # POSIX: try aplay
        try:
            res = subprocess.run(
                ["aplay", "-q", path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if res.returncode == 0:
                return True
        except Exception as e:
            print("Alarm sound playback failed (aplay):", e)
        return False

    alarm_sound = {"path": None}

    def _ensure_alarm_sound() -> Optional[str]:
        """Create a small WAV beep for the alarm if it doesn't exist."""
        path = os.path.join(LOCAL_TMP, "alarm_beep.wav")
        if alarm_sound.get("path") and os.path.exists(alarm_sound["path"]):
            return alarm_sound["path"]
        try:
            os.makedirs(LOCAL_TMP, exist_ok=True)
        except Exception:
            pass
        try:
            if not os.path.exists(path):
                import math
                import wave
                import array

                sample_rate = 16000
                duration = 1.0  # seconds
                freq = 880.0
                volume = 0.35
                samples = array.array("h")
                total = int(sample_rate * duration)
                for i in range(total):
                    val = int(volume * 32767 * math.sin(2 * math.pi * freq * (i / sample_rate)))
                    samples.append(val)
                with wave.open(path, "w") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(samples.tobytes())
            alarm_sound["path"] = path
            return path
        except Exception as e:
            print("Alarm sound generation failed:", e)
            return None

    def play_alarm_sound() -> bool:
        """Play the generated alarm beep; returns True on success."""
        path = _ensure_alarm_sound()
        if not path:
            return False
        # Windows fallback: winsound
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
            except Exception as e:
                print("Alarm sound playback failed (winsound):", e)
        # POSIX: try aplay
        try:
            res = subprocess.run(
                ["aplay", "-q", path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if res.returncode == 0:
                return True
        except Exception as e:
            print("Alarm sound playback failed (aplay):", e)
        return False
    
    def render():
        nonlocal weather_data
        v = mode["view"]
        if v == "calendar":
            ym = time.strftime("%Y-%m")
            if cache["calendar"]["img"] is None or cache["calendar"]["ym"] != ym:
                tkimg = draw_calendar_page(WINDOW_W, WINDOW_H, top_margin=24)
                cache["calendar"]["img"], cache["calendar"]["ym"] = tkimg, ym
            else:
                tkimg = cache["calendar"]["img"]
        elif v == "weather":
            stamp = None
            try:
                if isinstance(weather_data, dict):
                    stamp = weather_data.get("current", {}).get("last_updated")
            except Exception:
                stamp = None
            if cache["weather"]["img"] is None or cache["weather"]["stamp"] != stamp:
                tkimg = weather_mod.drawCurrentWeather(weather_data)
                cache["weather"]["img"], cache["weather"]["stamp"] = tkimg, stamp
            else:
                tkimg = cache["weather"]["img"]
        elif v == "alarm":
            cur = alarms["items"][alarms["i"]]
            sig = (
                tuple((a.get('hour', 0), a.get('minute', 0), a.get('enabled', False)) for a in alarms["items"]),
                alarms["i"],
                tuple(sorted(list(alarms["checked"]))),
            )
            if cache["alarm"]["img"] is None or cache["alarm"]["sig"] != sig:
                tkimg = draw_alarm_page(
                    cur["hour"],
                    cur["minute"],
                    cur.get("enabled", False) if isinstance(cur, dict) else False,
                    index=alarms["i"] + 1,
                    total=len(alarms["items"]),
                    alarms=alarms["items"],
                    selected=alarms["i"],
                    checked=alarms["checked"],
                )
                cache["alarm"]["img"], cache["alarm"]["sig"] = tkimg, sig
            else:
                tkimg = cache["alarm"]["img"]
        else:  # clock
            day_name = time.strftime("%a")
            today = time.strftime("%Y/%m/%d")
            current_time = time.strftime("%H:%M")
            current_sec = time.strftime("%S")
            tkimg = draw_clock_page(day_name, today, current_time, current_sec)
        label.config(image=tkimg)
        label.image = tkimg
        view_state["last"] = v

    timer = {"id": None}
    weather_fetching = {"busy": False}

    def tick():
        nonlocal last_fetch, weather_data
        now = time.time()
        today = time.strftime("%Y-%m-%d")
        if today != _last_date["d"]:
            RANG_RECENT.clear()
            _last_date["d"] = today

        if api_key and (now - last_fetch > 600 or weather_data is None) and not weather_fetching["busy"]:
            weather_fetching["busy"] = True
            import threading

            def _do_fetch():
                nonlocal weather_data, last_fetch
                try:
                    data = weather_mod.getWeatherForecast(api_key, 3)
                except Exception:
                    data = None

                def _apply():
                    nonlocal weather_data, last_fetch
                    weather_data = data
                    last_fetch = time.time()
                    weather_fetching["busy"] = False
                    if mode["view"] == "weather":
                        render()

                root.after(0, _apply)

            threading.Thread(target=_do_fetch, daemon=True).start()

        VOICE_POLL_EVERY = 2.0
        voice_poll_ok = now - voice_cmd_state.get("last_check", 0.0) > VOICE_POLL_EVERY
        try:
            if voice_poll_ok and os.path.exists(VOICE_CMD_PATH):
                mt = os.path.getmtime(VOICE_CMD_PATH)
                if mt > voice_cmd_state.get("last_mtime", 0):
                    import json

                    with open(VOICE_CMD_PATH, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    voice_cmd_state["last_mtime"] = mt

                    cmds = payload if isinstance(payload, list) else [payload]
                    for payload in cmds:
                        if not isinstance(payload, dict):
                            continue
                        cmd = str(payload.get("cmd", "")).lower()

                        if cmd == "goto":
                            dest = str(payload.get("view", "")).lower()
                            if dest in {"clock", "weather", "calendar", "alarm"}:
                                mode["view"] = dest

                        elif cmd == "set_alarm":
                            hhmm = str(payload.get("time", "")).strip()
                            try:
                                h, m = [int(x) for x in hhmm.split(":", 1)]
                                key = (h, m)
                                if not any((a.get("hour"), a.get("minute")) == key for a in alarms["items"]):
                                    alarms["items"].append({"hour": h, "minute": m, "enabled": True})
                                    alarms["i"] = len(alarms["items"]) - 1
                                    mode["view"] = "alarm"
                            except Exception:
                                pass

                            goto = payload.get("goto")
                            if goto in {"clock", "weather", "calendar", "alarm"}:
                                mode["view"] = goto

                        elif cmd == "set_commute":
                            hhmm = str(
                                payload.get("leave_time")
                                or payload.get("arrival_time")
                                or ""
                            ).strip()
                            if hhmm:
                                try:
                                    h, m = [int(x) for x in hhmm.split(":", 1)]
                                    key = (h, m)
                                    if not any(
                                        (a.get("hour"), a.get("minute")) == key
                                        for a in alarms["items"]
                                    ):
                                        alarms["items"].append({
                                            "hour": h,
                                            "minute": m,
                                            "enabled": True,
                                            "destination": payload.get("destination"),
                                        })
                                        alarms["i"] = len(alarms["items"]) - 1
                                    mode["view"] = "alarm"
                                except Exception:
                                    pass
                        elif cmd == "commute_missing":
                            missing = payload.get("missing") or []
                            
                            if speak:
                                if "arrival_time" in missing and "destination" in missing:
                                    speak("I can help with your commute, but I need both your arrival time and your destination. For example, say: I need to be at the airport by 7 a.m.")
                                elif "destination" in missing:
                                    speak("Okay. Where are you going?")
                                elif "arrival_time" in missing:
                                    speak("What time do you need to arrive?")
                                elif "prep_minutes" in missing:
                                    speak("How many minutes do you need to get ready before leaving?")
                                else:
                                    speak("I need a little more information to plan your commute. Please say when and where you need to be.")
                        elif cmd == "alarm_missing":
                            missing = payload.get("missing") or []
                            hour = payload.get("hour")
                            minute = payload.get("minute")

                            try:
                                from PIapp.pi_tts import speak
                            except Exception:
                                speak = None

                            if speak:
                                if "meridiem" in missing and isinstance(hour, int):
                                    # 5 → "5 o'clock"
                                    if minute in (0, None):
                                        spoken_time = f"{hour} o'clock"
                                    else:
                                        spoken_time = f"{hour} {minute:02d}"

                                    speak(
                                        f"Did you mean {spoken_time} A M or {spoken_time} P M? "
                                        f"Please repeat and say, for example, "
                                        f"set an alarm for {hour} A M."
                                    )
                                else:
                                    speak(
                                        "Did you mean A M or P M? "
                                        "Please repeat the alarm with A M or P M."
                                    )

                    try:
                        os.remove(VOICE_CMD_PATH)
                    except Exception:
                        pass

            if voice_poll_ok:
                voice_cmd_state["last_check"] = now
        except Exception:
            pass

        try:
            now_h = int(time.strftime("%H"))
            now_m = int(time.strftime("%M"))
            today = time.strftime("%Y-%m-%d")
            for a in list(alarms["items"]):
                if not a.get("enabled"):
                    continue
                key = (today, a.get("hour", 0), a.get("minute", 0))
                if key in RANG_RECENT:
                    continue
                if a.get("hour") == now_h and a.get("minute") == now_m:
                    played = play_alarm_sound()
                    try:
                        speak("Alarm ringing.")
                    except Exception as e:
                        print("TTS alarm error:", e)
                        if not played:
                            print("No alarm sound played.")
                    RANG_RECENT.add(key)
        except Exception:
            pass

        if mode["view"] == "clock" or view_state.get("last") != mode.get("view"):
            render()
        timer["id"] = root.after(1000, tick)

    SWIPE_MIN_DIST = 80
    SWIPE_MAX_TIME = 0.8
    gesture = {"x": 0, "y": 0, "t": 0.0, "active": False}

    PAGES = ["calendar", "clock", "weather"]  # left -> right order (exclude 'alarm')

    def next_view():
        v = mode["view"]
        if v == "alarm":
            return
        try:
            i = PAGES.index(v)
        except ValueError:
            i = 1
        i = min(len(PAGES) - 1, i + 1)
        mode["view"] = PAGES[i]

    def prev_view():
        v = mode["view"]
        if v == "alarm":
            return
        try:
            i = PAGES.index(v)
        except ValueError:
            i = 1
        i = max(0, i - 1)
        mode["view"] = PAGES[i]

    def on_press(evt):
        gesture["x"] = evt.x
        gesture["y"] = evt.y
        gesture["t"] = time.time()
        gesture["active"] = True

    def on_release(evt):
        if not gesture["active"]:
            return
        dx = evt.x - gesture["x"]
        dy = evt.y - gesture["y"]
        dt = time.time() - gesture["t"]
        gesture["active"] = False

        if dt <= SWIPE_MAX_TIME and (abs(dx) >= SWIPE_MIN_DIST or abs(dy) >= SWIPE_MIN_DIST):
            if abs(dx) >= abs(dy):
                if dx < 0:
                    if mode["view"] == "clock":
                        mode["view"] = "weather"
                    elif mode["view"] == "calendar":
                        mode["view"] = "clock"
                else:
                    if mode["view"] == "clock":
                        mode["view"] = "calendar"
                    elif mode["view"] == "weather":
                        mode["view"] = "clock"
            else:
                if dy < 0:
                    if mode["view"] == "clock":
                        mode["view"] = "alarm"
                else:
                    if mode["view"] == "alarm":
                        mode["view"] = "clock"
        else:
            if mode["view"] == "alarm":
                x, y = evt.x, evt.y

                def inside(rect):
                    x1, y1, x2, y2 = rect
                    return x1 <= x <= x2 and y1 <= y <= y2

                cur = alarms["items"][alarms["i"]]
                layout = alarm_layout(cur["hour"], cur["minute"], len(alarms["items"]), alarms["i"])
                if inside(layout.get("list_add", (0, 0, 0, 0))):
                    new_item = {"hour": cur.get("hour", 7), "minute": cur.get("minute", 0), "enabled": cur.get("enabled", False)}
                    alarms["items"].insert(alarms["i"] + 1, new_item)
                    alarms["i"] += 1
                    render()
                    return
                if inside(layout.get("list_trash", (0, 0, 0, 0))):
                    if alarms["checked"]:
                        remaining = [a for idx, a in enumerate(alarms["items"]) if idx not in alarms["checked"]]
                        if not remaining:
                            remaining = [alarms["items"][alarms["i"]]]
                        alarms["items"] = remaining
                        alarms["i"] = min(alarms["i"], len(alarms["items"]) - 1)
                        alarms["checked"].clear()
                    render()
                    return
                for idx in range(len(alarms["items"])):
                    if inside(layout.get(f"list_check_{idx}", (0, 0, 0, 0))):
                        if idx in alarms["checked"]:
                            alarms["checked"].remove(idx)
                        else:
                            alarms["checked"].add(idx)
                        render()
                        return
                    if inside(layout.get(f"list_{idx}", (0, 0, 0, 0))):
                        alarms["i"] = idx
                        render()
                        return
                if inside(layout.get("toggle", (0, 0, 0, 0))):
                    cur["enabled"] = not cur.get("enabled", False)
                    render()
                    return
                if inside(layout.get("am_btn", (0, 0, 0, 0))):
                    cur["hour"] = cur["hour"] % 12
                elif inside(layout.get("pm_btn", (0, 0, 0, 0))):
                    h12 = (cur["hour"] % 12) or 12
                    cur["hour"] = 12 if h12 == 12 else h12 + 12
                elif inside(layout.get("h_ones_plus", (0, 0, 0, 0))) or inside(layout.get("h_ones_minus", (0, 0, 0, 0))):
                    ampm_pm = cur["hour"] >= 12
                    h12 = (cur["hour"] % 12) or 12
                    if inside(layout.get("h_ones_plus", (0, 0, 0, 0))):
                        new12 = 1 if h12 == 12 else h12 + 1
                    else:
                        new12 = 12 if h12 == 1 else h12 - 1
                    cur["hour"] = (new12 % 12) + (12 if ampm_pm else 0)
                elif inside(layout.get("m_tens_plus", (0, 0, 0, 0))):
                    t = (cur["minute"] // 10 + 1) % 6
                    cur["minute"] = t * 10 + (cur["minute"] % 10)
                elif inside(layout.get("m_tens_minus", (0, 0, 0, 0))):
                    t = (cur["minute"] // 10 - 1) % 6
                    cur["minute"] = t * 10 + (cur["minute"] % 10)
                elif inside(layout.get("m_ones_plus", (0, 0, 0, 0))):
                    o = (cur["minute"] % 10 + 1) % 10
                    cur["minute"] = (cur["minute"] // 10) * 10 + o
                    if o == 0:
                        t = (cur["minute"] // 10 + 1) % 6
                        cur["minute"] = t * 10 + o
                elif inside(layout.get("m_ones_minus", (0, 0, 0, 0))):
                    o = (cur["minute"] % 10 - 1) % 10
                    cur["minute"] = (cur["minute"] // 10) * 10 + o
                    if o == 9:
                        t = (cur["minute"] // 10 - 1) % 6
                        cur["minute"] = t * 10 + o
                render()
                return

    def close_window(event=None):
        root.attributes("-fullscreen", False)
        root.destroy()

    label.bind("<Button-1>", on_press)
    label.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", close_window)

    render()
    tick()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
