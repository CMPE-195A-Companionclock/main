import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional
import threading

import requests
from dotenv import load_dotenv

from PIapp.nlu import get_intent as nlu_get_intent
from app_router import goto_view, schedule_alarm

from PIapp.calendar_service import get_calendar_service
from PIapp.calendarPage import draw_calendar_image

BASE_DIR = Path(__file__).resolve().parent / "PIapp"
load_dotenv(BASE_DIR / ".env")

VOICE_CMD_PATH = os.getenv("VOICE_CMD_PATH", os.path.join(tempfile.gettempdir(), "cc_voice_cmd.json"))
PC_SERVER = os.getenv("PC_SERVER", "http://10.0.0.111:5000")

SMART = {"COMMUTE_UPDATES": True}
COMMUTE_REPLAN_INTERVAL_MIN = 15
COMMUTE_UPDATE_THRESHOLD_MIN = 5
COMMUTE_FREEZE_WINDOW_MIN = 30


def run_clock(windowed: bool = False):
    from PIapp.clock import run
    run(fullscreen=not windowed)


def run_voice():
    from PIapp.voiceRecognition import main as voice_main
    voice_main()


def run_server():
    from PCapp.Server import app
    app.run(host="0.0.0.0", port=5000, threaded=True)

def run_calendar_ui(windowed: bool = False):
    """Open the full-screen CalendarPage UI (uses Google Calendar events)."""
    import tkinter as tk

    WINDOW_W, WINDOW_H = 1024, 600
    BASE_DIR_ABS = os.path.abspath(os.path.dirname(__file__))
    LOCAL_TMP = os.path.join(BASE_DIR_ABS, "PIapp", "tmp")
    try:
        os.makedirs(LOCAL_TMP, exist_ok=True)
    except Exception:
        pass

    root = tk.Tk()
    root.title("CompanionClock")

    if not windowed:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        WINDOW_W, WINDOW_H = screen_w, screen_h
        root.attributes("-fullscreen", True)
        root.geometry(f"{WINDOW_W}x{WINDOW_H}")
    else:
        root.geometry(f"{WINDOW_W}x{WINDOW_H}")

    root.configure(bg="black")
    
    label = tk.Label(root, bg="black")
    label.pack(fill=tk.BOTH, expand=True)

    def render():
        img = draw_calendar_image(WINDOW_W, WINDOW_H, top_margin=24)
        label.config(image=img)
        label.image = img

    render()

    def close(event=None):
        root.attributes("-fullscreen", False)
        root.destroy()

    root.bind("<Escape>", close)
    root.mainloop()

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
    
    p_cal = sub.add_parser("calendar", help="Show Calendar UI with Google events")
    p_cal.add_argument("--windowed", action="store_true",
                   help="Run calendar in a window instead of fullscreen")
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
        return run_calendar_ui(windowed=args.windowed)
    elif args.cmd == "ui":
        return run_touch_ui(fullscreen=not args.windowed)
    else:
        parser.print_help()
        return 2
    return 0


print("UI VOICE_CMD_PATH:", VOICE_CMD_PATH)


def run_touch_ui(fullscreen: bool = True):
    from PIapp.pi_tts import speak
    from datetime import datetime, timedelta
    from PIapp.calendar_service import get_calendar_service
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

    if fullscreen:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        WINDOW_W, WINDOW_H = screen_w, screen_h
        root.attributes("-fullscreen", True)
        root.geometry(f"{WINDOW_W}x{WINDOW_H}")
    else:
        root.geometry(f"{WINDOW_W}x{WINDOW_H}")
    root.configure(bg="black")

    label = tk.Label(root)
    label.pack(fill=tk.BOTH, expand=True)
    try:
        import PIapp.clock as clock_mod
        import PIapp.Alarm as alarm_mod

        clock_mod.windowWidth = WINDOW_W
        clock_mod.windowHeight = WINDOW_H

        weather_mod.windowWidth = WINDOW_W
        weather_mod.windowHeight = WINDOW_H

        alarm_mod.WINDOW_W = WINDOW_W
        alarm_mod.WINDOW_H = WINDOW_H
    except Exception as e:
        print("Warning: failed to update page module sizes:", e)

    try:
        speak("Companion Clock is ready.")
    except Exception as e:
        try:
            msg = str(e)
        except Exception:
            msg = repr(e)
        safe_msg = msg.encode("ascii", "backslashreplace").decode("ascii")
        print("TTS startup error:", safe_msg)

    mode = {"view": "clock"}
    api_key: Optional[str] = os.getenv("WEATHERAPI_KEY")
    weather_data: Optional[dict] = None
    last_fetch = 0.0
    ALARM_STORE = os.path.join(LOCAL_TMP, "alarms.json")
    alarm_sound = {"path": None}
    commute_last_check = {"ts": 0}


    def _load_alarms():
        try:
            if os.path.exists(ALARM_STORE):
                with open(ALARM_STORE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and data:
                    cleaned = []
                    for a in data:
                        try:
                            base ={
                                 "hour": int(a.get("hour", 0)),
                                 "minute": int(a.get("minute", 0)),
                                 "enabled": bool(a.get("enabled", False)),
                            }

                            for key in [
                                "commute",
                                "destination",
                                "origin",
                                "prep_minutes",
                                "arrival_time",
                                "leave_time",
                                "plan",
                                "base_hour",
                                "base_minute",
                                "last_replan_ts",
                                "snoozed",
                            ]:
                                if key in a:
                                    base[key] = a[key]

                            cleaned.append(base)
                        except Exception:
                            continue
                    if cleaned:
                        return cleaned
        except Exception as e:
            print("Alarm load failed:", e)
        return None

    def _save_alarms():
        try:
            os.makedirs(os.path.dirname(ALARM_STORE), exist_ok=True)
            tmp = ALARM_STORE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(alarms["items"], f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, ALARM_STORE)
        except Exception as e:
            print("Alarm save failed:", e)

    alarms = {"items": [{"hour": 7, "minute": 0, "enabled": False}], "i": 0, "checked": set()}
    loaded = _load_alarms()
    if loaded:
        alarms["items"] = loaded
    RANG_RECENT = set()
    _last_date = {"d": time.strftime("%Y-%m-%d")}
    pending_commute = {}
    active_alarm = {"idx": None, "ts": 0.0}
    
    voice_cmd_state = {"last_mtime": 0.0}
    view_state = {"last": None}
    cache = {
        "weather": {"img": None, "stamp": None},
        "calendar": {"img": None, "ym": None},
        "alarm": {"img": None, "sig": None},
    }
    ui_refresh = {"dirty": False}

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
                duration = 1.0
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
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
            except Exception as e:
                print("Alarm sound playback failed (winsound):", e)
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
                tuple(
                    (
                        a.get("hour", 0),
                        a.get("minute", 0),
                        a.get("enabled", False),
                        a.get("origin"),
                        a.get("destination"),
                        a.get("prep_minutes"),
                    )
                    for a in alarms["items"]
                ),
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
                    commute_origin=cur.get("origin"),
                    commute_destination=cur.get("destination"),
                    prep_minutes=cur.get("prep_minutes"),
                    smart_commute_updates=SMART["COMMUTE_UPDATES"],
                )
                cache["alarm"]["img"], cache["alarm"]["sig"] = tkimg, sig
            else:
                tkimg = cache["alarm"]["img"]
        else:
            day_name = time.strftime("%a")
            today = time.strftime("%Y/%m/%d")
            current_time = time.strftime("%H:%M")
            current_sec = time.strftime("%S")
            tkimg = draw_clock_page(day_name, today, current_time, current_sec)
        label.config(image=tkimg)
        label.image = tkimg
        view_state["last"] = v
        ui_refresh["dirty"] = False

    timer = {"id": None}
    weather_fetching = {"busy": False}

    def speak_weather_summary(when: str = "today"):
        nonlocal weather_data
        if not isinstance(weather_data, dict) or "forecast" not in weather_data:
            try:
                if api_key:
                    weather_data = weather_mod.getWeatherForecast(api_key, 3)
            except Exception as e:
                print("[ui] weather summary fetch failed:", e, flush=True)
                try:
                    speak("Sorry, I can't get the weather right now.")
                except Exception:
                    pass
                return

        try:
            loc = weather_data["location"]["name"]
            current = weather_data["current"]
            days = weather_data["forecast"]["forecastday"]

            index = 0 if when != "tomorrow" else 1
            if index >= len(days):
                index = 0

            day = days[index]
            day_label = "Today" if index == 0 else "Tomorrow"

            cond_now = current["condition"]["text"].lower()
            temp_now = round(current["temp_c"])
            hi = round(day["day"]["maxtemp_c"])
            lo = round(day["day"]["mintemp_c"])

            msg = (
                f"{day_label} in {loc}, "
                f"it's {temp_now} degrees and {cond_now}. "
                f"The high will be about {hi} and the low about {lo}."
            )
            speak(msg)
        except Exception as e:
            print("[ui] weather summary parse failed:", e, flush=True)
            try:
                speak("Sorry, I couldn't read the weather data.")
            except Exception:
                pass

    def speak_events_summary(when: str = "today"):
        """Speak a summary of today's or tomorrow's calendar events."""
        try:
            svc = get_calendar_service()
        except Exception as e:
            print("[ui] calendar summary service error:", e, flush=True)
            try:
                speak("Sorry, I can't reach your calendar right now.")
            except Exception:
                pass
            return

        try:
            if when == "tomorrow":
                target = (datetime.now() + timedelta(days=1)).date()
                evs = svc.get_upcoming_events(max_results=50, days_ahead=2)
                events = [e for e in evs if e["start_datetime"].date() == target]
            else:
                events = svc.get_todays_events()
        except Exception as e:
            print("[ui] calendar summary fetch error:", e, flush=True)
            try:
                speak("Sorry, I couldn't fetch your calendar events.")
            except Exception:
                pass
            return

        when_word = "tomorrow" if when == "tomorrow" else "today"
        if not events:
            speak(f"You don't have any events {when_word}.")
            return

        count = len(events)
        max_list = 3
        parts = []
        for ev in events[:max_list]:
            title = ev["summary"]
            time_str = ev["start_time"]
            if time_str == "All Day":
                parts.append(f"{title} all day")
            else:
                parts.append(f"{title} at {time_str}")

        if count == 1:
            msg = f"You have one event {when_word}: {parts[0]}."
        elif count <= max_list:
            msg = f"You have {count} events {when_word}: " + "; ".join(parts) + "."
        else:
            remaining = count - max_list
            msg = (
                f"You have {count} events {when_word}. "
                + "; ".join(parts)
                + f"; and {remaining} more."
            )
        speak(msg)


    def tick():
        nonlocal last_fetch, weather_data, pending_commute, commute_last_check
        now = time.time()
        today = time.strftime("%Y-%m-%d")
        if today != _last_date["d"]:
            RANG_RECENT.clear()
            _last_date["d"] = today

        if api_key and (now - last_fetch > 600 or weather_data is None) and not weather_fetching["busy"]:
            weather_fetching["busy"] = True
            

        def _fetch_weather(idx, alarm_snapshot):
            nonlocal weather_data, last_fetch
            try:
                data = weather_mod.getWeatherForecast(api_key, 3)
            except Exception:
                data = None
            weather_data = data
            last_fetch = time.time()
            weather_fetching["busy"] = False
            ui_refresh["dirty"] = True
            threading.Thread(target=_fetch_weather, daemon=True).start()

        VOICE_POLL_EVERY = 2.0
        voice_poll_ok = now - voice_cmd_state.get("last_check", 0.0) > VOICE_POLL_EVERY
        try:
            if voice_poll_ok and os.path.exists(VOICE_CMD_PATH):
                mt = os.path.getmtime(VOICE_CMD_PATH)
                if mt > voice_cmd_state.get("last_mtime", 0):
                    import json

                    with open(VOICE_CMD_PATH, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    print("[ui] VOICE_CMD payload:", payload, flush=True)
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
                                    ui_refresh["dirty"] = True
                                    _save_alarms()
                                    try:
                                        if h == 0:
                                            h12, meridiem = 12, "AM"
                                        elif 1 <= h < 12:
                                            h12, meridiem = h, "AM"
                                        elif h == 12:
                                            h12, meridiem = 12, "PM"
                                        else:
                                            h12, meridiem = h - 12, "PM"
                                        
                                        time_phrase = f"{h12}:{m:02d} {meridiem}"
                                        speak(f"Okay, I'll set an alarm for {time_phrase}.")
                                    except Exception as e:
                                        print(
                                            "[ui] set_alarm speak failed:",
                                            repr(e),
                                            flush=True,
                                        )
                            except Exception:
                                pass

                            goto = payload.get("goto")
                            if goto in {"clock", "weather", "calendar", "alarm"}:
                                mode["view"] = goto

                        elif cmd == "delete_alarm":
                            if alarms["items"]:
                                if len(alarms["items"]) > 1:
                                    deleted = alarms["items"].pop(alarms["i"])
                                    alarms["i"] = min(
                                        alarms["i"],
                                        len(alarms["items"]) - 1,
                                    )
                                else:
                                    alarms["items"][0]["enabled"] = False

                                _save_alarms()
                                ui_refresh["dirty"] = True
                                mode["view"] = "alarm"
                                try:
                                    speak("Okay, I'll delete this alarm.")
                                except Exception as e:
                                    print(
                                        "[ui] delete_alarm speak failed:",
                                        repr(e),
                                        flush=True,
                                    )
                        
                        elif cmd == "snooze_alarm":
                            idx = active_alarm.get("idx")
                            if idx is None or idx >= len(alarms["items"]):
                                try:
                                    speak("I don't have a ringing alarm to snooze.")
                                except Exception as e:
                                    print("[ui] snooze_alarm speak failed:", repr(e), flush=True)
                            else:
                                try:
                                    minutes = payload.get("minutes")
                                    try:
                                        minutes = int(minutes)
                                    except Exception:
                                        minutes = None
                                    if minutes is None or minutes <= 0:
                                        minutes = 10

                                    now = time.time()
                                    snooze_ts = now + minutes * 60
                                    snooze_struct = time.localtime(snooze_ts)
                                    h = snooze_struct.tm_hour
                                    m = snooze_struct.tm_min

                                    alarms["items"].append(
                                        {
                                            "hour": h,
                                            "minute": m,
                                            "enabled": True,
                                            "snoozed": True,
                                        }
                                    )
                                    alarms["i"] = len(alarms["items"]) - 1
                                    _save_alarms()
                                    ui_refresh["dirty"] = True
                                    mode["view"] = "alarm"

                                    active_alarm["idx"] = None
                                    active_alarm["ts"] = 0.0

                                    try:
                                        speak(f"Okay, snoozing for {minutes} minutes.")
                                    except Exception as e:
                                        print("[ui] snooze speak failed:", repr(e), flush=True)
                                except Exception as e:
                                    print("[ui] snooze_alarm error:", repr(e), flush=True)

                        elif cmd == "stop_alarm":
                            idx = active_alarm.get("idx")
                            if idx is None or idx >= len(alarms["items"]):
                                try:
                                    speak("I don't have a ringing alarm to stop.")
                                except Exception as e:
                                    print("[ui] stop_alarm speak failed:", repr(e), flush=True)
                            else:
                                try:
                                    alarms["items"][idx]["enabled"] = False
                                    _save_alarms()
                                    ui_refresh["dirty"] = True
                                    mode["view"] = "alarm"

                                    active_alarm["idx"] = None
                                    active_alarm["ts"] = 0.0

                                    try:
                                        speak("Okay, I stopped this alarm.")
                                    except Exception as e:
                                        print("[ui] stop speak failed:", repr(e), flush=True)
                                except Exception as e:
                                    print("[ui] stop_alarm error:", repr(e), flush=True)
                                          
                        elif cmd == "disable_all_alarms":
                            changed = False
                            for a in alarms["items"]:
                                if a.get("enabled"):
                                    a["enabled"] = False
                                    changed = True

                            if changed:
                                _save_alarms()
                                ui_refresh["dirty"] = True

                            mode["view"] = "alarm"

                            try:
                                if changed:
                                    speak("Okay, I'll turn off all your alarms.")
                                else:
                                    speak("You don't have any alarms turned on.")
                            except Exception as e:
                                print(
                                    "[ui] disable_all_alarms speak failed:",
                                    repr(e),
                                    flush=True,
                                )

                        elif cmd == "enable_all_alarms":
                            changed = False
                            for a in alarms["items"]:
                                if not a.get("enabled"):
                                    a["enabled"] = True
                                    changed = True

                            if changed:
                                _save_alarms()
                                ui_refresh["dirty"] = True

                            mode["view"] = "alarm"

                            try:
                                if changed:
                                    speak("Okay, I'll turn all your alarms back on.")
                                else:
                                    speak("You don't have any alarms to turn on.")
                            except Exception as e:
                                print("[ui] enable_all_alarms speak failed:", repr(e), flush=True)

                        elif cmd == "set_commute":
                            print("[ui] entering set_commute branch:", payload, flush=True)
                            if pending_commute:
                                for key in ("destination", "arrival_time", "prep_minutes", "origin"):
                                    if key not in payload or not payload.get(key):
                                        if key in pending_commute:
                                            payload[key] = pending_commute[key]
                            hhmm = str(
                                payload.get("leave_time")
                                or payload.get("arrival_time")
                                or ""
                            ).strip()

                            alarm_time = payload.get("leave_time")  # or from alarm_proposal
                            dest = payload.get("destination")
                            try:
                                speak(f"Okay, I'll wake you at {alarm_time} so you can get to {dest} on time.")
                            except Exception as e:
                                print("[ui] set_commute speak failed:", repr(e), flush=True)

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
                                            "commute": True,
                                            "destination": payload.get("destination"),
                                            "origin": payload.get("origin"),
                                            "prep_minutes": payload.get("prep_minutes"),
                                            "arrival_time": payload.get("arrival_time"),
                                            "leave_time": payload.get("leave_time"),
                                            "plan": payload.get("plan"),
                                            "base_hour": h,
                                            "base_minute": m,
                                            "last_replan_ts": 0,
                                        })
                                        alarms["i"] = len(alarms["items"]) - 1
                                        ui_refresh["dirty"] = True
                                        _save_alarms()
                                    mode["view"] = "alarm"
                                    pending_commute.clear()
                                except Exception:
                                    print("[ui] set_commute alarm creation failed:", repr(e), flush=True)

                        elif cmd == "commute_missing":
                            missing = payload.get("missing") or []
                            dest    = payload.get("destination")
                            arrival = payload.get("arrival_time")
                            prep    = payload.get("prep_minutes")
                            origin  = payload.get("origin")

                            if dest or arrival or prep is not None or origin:
                                pending_commute.update({
                                    k: v for k, v in {
                                        "destination": dest,
                                        "arrival_time": arrival,
                                        "prep_minutes": prep,
                                        "origin": origin,
                                    }.items() if v not in (None, "", [])
                                })

                            if speak:
                                if "destination" in missing and "arrival_time" in missing:
                                    speak("I can help with your destination and arrival time. Where are you going, and what time do you need to arrive?")
                                elif "destination" in missing:
                                    speak("Where are you going?")
                                elif "arrival_time" in missing:
                                    speak("What time do you need to arrive?")
                                elif "prep_minutes" in missing:
                                    speak("How many minutes do you need to get ready?")
                                else:
                                    speak("I need a bit more information to plan your commute.")
                        
                        elif cmd == "alarm_missing":
                            missing = payload.get("missing") or []
                            hour = payload.get("hour")
                            minute = payload.get("minute")

                            try:
                                from PIapp.pi_tts import speak as _speak
                            except Exception:
                                _speak = None

                            if _speak:
                                if "meridiem" in missing and isinstance(hour, int):
                                    if minute in (0, None):
                                        time_phrase = f"{hour} o'clock"
                                    else:
                                        time_phrase = f"{hour} {minute:02d}"

                                    _speak(
                                        f"Did you mean {time_phrase} A M or {time_phrase} P M? "
                                    )
                                elif "time" in missing:
                                    _speak(
                                        "What time should I set the alarm for?"
                                    )
                                else:
                                    _speak("I need a bit more information to set the alarm.")

                        elif cmd == "toggle_commute_updates":
                            state = payload.get("state")
                            if state == "off":
                                SMART["COMMUTE_UPDATES"] = False
                                if speak:
                                    speak("Okay, I turned off automatic commute updates.")
                            elif state == "on":
                                SMART["COMMUTE_UPDATES"] = True
                                if speak:
                                    speak("Okay, I turned on commute updates.")

                        elif cmd == "network_error":
                            try:
                                speak(
                                    "I couldn't contact the server to understand that. "
                                    "Please check the network and try again."
                                )
                            except Exception as e:
                                print("[ui] network_error speak failed:", repr(e), flush=True)

                        elif cmd == "query_weather":
                            when = str(payload.get("when") or "today").lower()
                            try:
                                speak_weather_summary(when)
                            except Exception as e:
                                print("[ui] speak_weather_summary error:", e, flush=True)
                            mode["view"] = "weather"
                            ui_refresh["dirty"] = True

                        elif cmd == "query_events":
                            when = str(payload.get("when") or "today").lower()
                            try:
                                speak_events_summary(when)
                            except Exception as e:
                                print("[ui] speak_events_summary error:", e, flush=True)
                            mode["view"] = "calendar"
                            ui_refresh["dirty"] = True

                        elif cmd == "gemini_error":
                            try:
                                from PIapp.pi_tts import speak as _speak
                            except Exception:
                                _speak = None

                            err = payload.get("error") or "UnknownError"
                            msg_txt = payload.get("message") or ""
                            print("[voice] Gemini error:", err, msg_txt)

                            spoken =  (
                                "I couldn't plan your commute right now because "
                                "the AI service is unavailable. I'll fall back to the regular alarm."
                            )
                            if _speak:
                                _speak(spoken)        

                    try:
                        os.remove(VOICE_CMD_PATH)
                    except Exception:
                        pass

            if voice_poll_ok:
                voice_cmd_state["last_check"] = now
        except Exception:
            pass

        if SMART["COMMUTE_UPDATES"]:
            try:
                if now - commute_last_check["ts"] > COMMUTE_REPLAN_INTERVAL_MIN * 60:
                    commute_last_check["ts"] = now

                    for alarm in alarms["items"]:
                        if not alarm.get("commute"):
                            continue
                        if not alarm.get("enabled", True):
                            continue

                        dest = alarm.get("destination")
                        arrival = alarm.get("arrival_time")
                        prep = alarm.get("prep_minutes")
                        if not dest or not arrival:
                            continue

                        try:
                            import datetime as _dt
                            now_dt = _dt.datetime.now()
                            alarm_dt = now_dt.replace(
                                hour=int(alarm["hour"]),
                                minute=int(alarm["minute"]),
                                second=0,
                                microsecond=0,
                            )
                            if alarm_dt < now_dt:
                                alarm_dt = alarm_dt + _dt.timedelta(days=1)
                            mins_until_alarm = int((alarm_dt - now_dt).total_seconds() / 60)
                        except Exception:
                            continue

                        if mins_until_alarm <= COMMUTE_FREEZE_WINDOW_MIN:
                            continue
                        
                        try:
                            resp = requests.post(
                                PC_SERVER.rstrip("/") + "/plan_alarm",
                                json={
                                    "arrival_time": arrival,
                                    "destination": dest,
                                    "prep_minutes": prep,
                                },
                                timeout=5,
                            )
                            data = resp.json()
                        except Exception as e:
                            print("[ui] commute replan failed:", e, flush=True)
                            continue

                        new_hhmm = str(data.get("alarm_time") or "").strip()
                        if not new_hhmm or ":" not in new_hhmm:
                            continue

                        try:
                            new_h, new_m = [int(x) for x in new_hhmm.split(":", 1)]
                        except Exception:
                            continue

                        current_minutes = int(alarm["hour"]) * 60 + int(alarm["minute"])
                        new_minutes = new_h * 60 + new_m
                        delta = new_minutes - current_minutes
                        if delta >= 0:
                            continue 
                        if abs(delta) < COMMUTE_UPDATE_THRESHOLD_MIN:
                            continue

                        print(
                            f"[ui] commute alarm for {dest} adjusted from "
                            f"{alarm['hour']:02d}:{alarm['minute']:02d} to {new_hhmm}",
                            flush=True,
                        )
                        alarm["hour"] = new_h
                        alarm["minute"] = new_m
            except Exception as e:
                print("[ui] commute auto-update error:", e, flush=True)
        try:
            now_h = int(time.strftime("%H"))
            now_m = int(time.strftime("%M"))
            today = time.strftime("%Y-%m-%d")
            for idx, a in enumerate(list(alarms["items"])):
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
                    active_alarm["idx"] = idx
                    active_alarm["ts"] = time.time()
                    alarms["i"] = idx
                    mode["view"] = "alarm"
                    ui_refresh["dirty"] = True

                    RANG_RECENT.add(key)
        except Exception:
            pass

        if mode["view"] == "clock" or view_state.get("last") != mode.get("view") or ui_refresh.get("dirty"):
            render()
        timer["id"] = root.after(1000, tick)

    SWIPE_MIN_DIST = 80
    SWIPE_MAX_TIME = 0.8
    gesture = {"x": 0, "y": 0, "t": 0.0, "active": False}

    PAGES = ["calendar", "clock", "weather"]

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
                    new_item = {"hour": cur.get("hour", 7), "minute": cur.get("minute", 0), "enabled": False}
                    alarms["items"].insert(alarms["i"] + 1, new_item)
                    alarms["i"] += 1
                    _save_alarms()
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
                        _save_alarms()
                        ui_refresh["dirty"] = True
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
                    _save_alarms()
                    ui_refresh["dirty"] = True
                    render()
                    return
                if inside(layout.get("delete_btn", (0, 0, 0, 0))) and len(alarms["items"]) > 1:
                    alarms["items"].pop(alarms["i"])
                    alarms["i"] = min(alarms["i"], len(alarms["items"]) - 1)
                    _save_alarms()
                    ui_refresh["dirty"] = True
                    render()
                    return
                if inside(layout.get("ampm_btn", (0, 0, 0, 0))):
                    cur["hour"] = (cur.get("hour", 0) + 12) % 24
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
                _save_alarms()
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
