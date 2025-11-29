import argparse
import os
import time
from typing import Optional
import json
import requests


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
        # Default: run touch-enabled main UI
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


# ================= Touch-enabled main UI =================
def run_touch_ui(fullscreen: bool = True):
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
        from PIapp.voicePage import draw_voice_page, get_layout as voice_layout
    except Exception as e:
        print("Failed to import page modules (clock/weather/calendar/alarm).")
        print(f"Detail: {e}")
        return 1

    WINDOW_W, WINDOW_H = 1024, 600
    # Resolve local tmp directory for recordings and ensure it exists
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    LOCAL_TMP = os.path.join(BASE_DIR, "PIapp", "tmp")
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

    # State
    mode = {"view": "clock"}  # calendar | weather | clock | alarm | voice (default: clock)
    api_key: Optional[str] = os.getenv("WEATHERAPI_KEY")
    weather_data: Optional[dict] = None
    last_fetch = 0.0
    # Multiple alarms state
    alarms = {"items": [{"hour": 7, "minute": 0, "enabled": False}], "i": 0, "checked": set()}
    # Voice test state (store under /tmp)
    voice = {"status": "", "wav_path": "/tmp/in.wav", "busy": False}

    # Voice command inbox (simple file-based IPC with voiceRecognition.py)
    VOICE_CMD_PATH = os.getenv("VOICE_CMD_PATH", "/tmp/cc_voice_cmd.json")
    voice_cmd_state = {"last_mtime": 0.0}
    view_state = {"last": None}
    # Simple render cache per page (avoid redrawing unchanged)
    cache = {
        "weather": {"img": None, "stamp": None},
        "calendar": {"img": None, "ym": None},
        "alarm": {"img": None, "sig": None},
        "voice": {"img": None, "status": None},
    }

    # Rendering separated from scheduling to avoid double timers
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
                tuple((a.get('hour',0), a.get('minute',0), a.get('enabled',False)) for a in alarms['items']),
                alarms['i'],
                tuple(sorted(list(alarms['checked'])))
            )
            if cache["alarm"]["img"] is None or cache["alarm"]["sig"] != sig:
                tkimg = draw_alarm_page(cur["hour"], cur["minute"], cur.get("enabled", False) if isinstance(cur, dict) else False,
                                        index=alarms["i"]+1, total=len(alarms["items"]),
                                        alarms=alarms["items"], selected=alarms["i"], checked=alarms["checked"]) 
                cache["alarm"]["img"], cache["alarm"]["sig"] = tkimg, sig
            else:
                tkimg = cache["alarm"]["img"]
        elif v == "voice":
            status = voice.get("status") or ""
            if cache["voice"]["img"] is None or cache["voice"]["status"] != status:
                tkimg = draw_voice_page(status)
                cache["voice"]["img"], cache["voice"]["status"] = tkimg, status
            else:
                tkimg = cache["voice"]["img"]
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
        # Schedule weather refresh without blocking UI
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

        # Check for incoming voice command (from voiceRecognition.py)
        # Throttle voice command polling unless on voice page
        VOICE_POLL_EVERY = 2.0
        voice_poll_ok = (mode["view"] == "voice") or (now - voice_cmd_state.get("last_check", 0.0) > VOICE_POLL_EVERY)
        try:
            if voice_poll_ok and os.path.exists(VOICE_CMD_PATH):
                mt = os.path.getmtime(VOICE_CMD_PATH)
                if mt > voice_cmd_state.get("last_mtime", 0):
                    import json
                    with open(VOICE_CMD_PATH, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    voice_cmd_state["last_mtime"] = mt
                    if isinstance(payload, dict) and payload.get("cmd") == "goto":
                        dest = str(payload.get("view", "")).lower()
                        if dest in {"clock", "weather", "calendar", "alarm", "voice"}:
                            mode["view"] = dest
                            # show transient status on voice page
                            if dest == "voice" and payload.get("text"):
                                voice["status"] = payload.get("text")[:40]
                    # delete after processing
                    try:
                        os.remove(VOICE_CMD_PATH)
                    except Exception:
                        pass
            if voice_poll_ok:
                voice_cmd_state["last_check"] = now
        except Exception:
            pass

        # Render when on clock every tick, or when view changed
        if mode["view"] == "clock" or view_state.get("last") != mode.get("view"):
            render()
        timer["id"] = root.after(1000, tick)

    SWIPE_MIN_DIST = 80
    SWIPE_MAX_TIME = 0.8
    gesture = {"x": 0, "y": 0, "t": 0.0, "active": False}

    PAGES = ["calendar", "clock", "weather", "voice"]  # left -> right order (exclude 'alarm')

    def next_view():
        v = mode["view"]
        if v == "alarm":
            return
        try:
            i = PAGES.index(v)
        except ValueError:
            i = 1  # default to 'clock'
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
                # Horizontal: left swipe moves to the right neighbor (weather),
                # right swipe moves to the left neighbor (calendar), only relative to clock.
                if dx < 0:  # swipe left
                    if mode["view"] == "clock":
                        mode["view"] = "weather"
                    elif mode["view"] == "calendar":
                        mode["view"] = "clock"
                else:  # swipe right
                    if mode["view"] == "clock":
                        mode["view"] = "calendar"
                    elif mode["view"] == "weather":
                        mode["view"] = "clock"
            else:
                # Vertical: up swipe moves to the bottom neighbor (alarm),
                # down swipe moves to the top neighbor (voice), only relative to clock.
                if dy < 0:  # swipe up
                    if mode["view"] == "clock":
                        mode["view"] = "alarm"
                    elif mode["view"] == "voice":
                        mode["view"] = "clock"
                else:  # swipe down
                    if mode["view"] == "clock":
                        mode["view"] = "voice"
                    elif mode["view"] == "alarm":
                        mode["view"] = "clock"
        else:
            # Tap gesture handling (short, small movement)
            if mode["view"] == "alarm":
                x, y = evt.x, evt.y
                def inside(rect):
                    x1, y1, x2, y2 = rect
                    return x1 <= x <= x2 and y1 <= y <= y2
                cur = alarms["items"][alarms["i"]]
                layout = alarm_layout(cur["hour"], cur["minute"], len(alarms["items"]), alarms["i"]) 
                # Header buttons: add / trash
                if inside(layout.get('list_add', (0,0,0,0))):
                    # Add a new alarm after current (copy current settings)
                    new_item = {"hour": cur.get("hour", 7), "minute": cur.get("minute", 0), "enabled": cur.get("enabled", False)}
                    alarms["items"].insert(alarms["i"] + 1, new_item)
                    alarms["i"] += 1
                    render(); return
                if inside(layout.get('list_trash', (0,0,0,0))):
                    if alarms["checked"]:
                        # Delete all checked alarms, but leave at least one
                        remaining = [a for idx, a in enumerate(alarms["items"]) if idx not in alarms["checked"]]
                        if not remaining:
                            remaining = [alarms["items"][alarms["i"]]]  # keep current if all selected
                        alarms["items"] = remaining
                        alarms["i"] = min(alarms["i"], len(alarms["items"]) - 1)
                        alarms["checked"].clear()
                    render(); return
                # List interactions: checkbox toggle or select item
                for idx in range(len(alarms["items"])):
                    if inside(layout.get(f'list_check_{idx}', (0,0,0,0))):
                        if idx in alarms["checked"]:
                            alarms["checked"].remove(idx)
                        else:
                            alarms["checked"].add(idx)
                        render(); return
                    if inside(layout.get(f'list_{idx}', (0,0,0,0))):
                        alarms["i"] = idx
                        render(); return
                if inside(layout.get('am_btn', (0,0,0,0))):
                    # Force AM
                    cur["hour"] = cur["hour"] % 12
                elif inside(layout.get('pm_btn', (0,0,0,0))):
                    # Force PM
                    h12 = (cur["hour"] % 12) or 12
                    cur["hour"] = 12 if h12 == 12 else h12 + 12
                elif inside(layout.get('h_ones_plus', (0,0,0,0))) or inside(layout.get('h_ones_minus', (0,0,0,0))):
                    # Adjust hour by +/-1 within 12h, preserve AM/PM
                    ampm_pm = cur["hour"] >= 12
                    h12 = (cur["hour"] % 12) or 12
                    if inside(layout.get('h_ones_plus', (0,0,0,0))):
                        new12 = 1 if h12 == 12 else h12 + 1
                    else:
                        new12 = 12 if h12 == 1 else h12 - 1
                    cur["hour"] = (new12 % 12) + (12 if ampm_pm else 0)
                elif inside(layout.get('m_tens_plus', (0,0,0,0))):
                    t = (cur["minute"] // 10 + 1) % 6
                    cur["minute"] = t*10 + (cur["minute"] % 10)
                elif inside(layout.get('m_tens_minus', (0,0,0,0))):
                    t = (cur["minute"] // 10 - 1) % 6
                    cur["minute"] = t*10 + (cur["minute"] % 10)
                elif inside(layout.get('m_ones_plus', (0,0,0,0))):
                    o = (cur["minute"] % 10 + 1) % 10
                    cur["minute"] = (cur["minute"] // 10) * 10 + o
                    if o == 0:
                        # carry to tens automatically
                        t = (cur["minute"] // 10 + 1) % 6
                        cur["minute"] = t*10 + o
                elif inside(layout.get('m_ones_minus', (0,0,0,0))):
                    o = (cur["minute"] % 10 - 1) % 10
                    cur["minute"] = (cur["minute"] // 10) * 10 + o
                    if o == 9:
                        # borrow from tens automatically
                        t = (cur["minute"] // 10 - 1) % 6
                        cur["minute"] = t*10 + o
                render(); return
                
            elif mode["view"] == "voice":
                x, y = evt.x, evt.y
                def inside(rect):
                    x1, y1, x2, y2 = rect
                    return x1 <= x <= x2 and y1 <= y <= y2
                layout = voice_layout()
                if inside(layout.get('rec_btn', (0,0,0,0))):
                    if not voice["busy"]:
                        voice["busy"] = True
                        secs = os.getenv("VOICE_SEC", "10")
                        voice["status"] = f"Recording… {secs}s"
                        render()
                        import threading, subprocess
                        def _rec():
                            # Record exactly as requested with configurable duration:
                            # arecord -D hw:1,0 -f S16_LE -r 16000 -c 2 -d <secs> /tmp/in.wav
                            secs_local = os.getenv("VOICE_SEC", "10")
                            arec_dev = os.getenv("ARECORD_CARD", os.getenv("VOICE_ARECORD_DEVICE", "plughw:1,0"))
                            rec_cmd = [
                                "arecord",
                                "-D", arec_dev,
                                "-f", "S16_LE",
                                "-r", "16000",
                                "-c", "1",
                                "-d", secs_local,
                                voice["wav_path"],
                            ]
                            try:
                                subprocess.run(rec_cmd, check=True)
                                # After recording, optionally send to ASR server
                                offline = os.getenv("VOICE_OFFLINE", "0") == "1"
                                if offline:
                                    voice["status"] = "Recorded (offline)"
                                else:
                                    voice["status"] = "Recognizing..."
                                    try:
                                        url = os.getenv("VOICE_SERVER_URL", os.getenv("SERVER_URL", "http://192.168.0.10:5000/transcribe"))
                                        with open(voice["wav_path"], "rb") as fh:
                                            r = requests.post(url, files={"audio": ("in.wav", fh, "audio/wav")}, timeout=30)
                                        txt = ""
                                        try:
                                            j = r.json()
                                            if isinstance(j, dict):
                                                txt = (j.get("text") or j.get("path") or j.get("status") or "")
                                                txt = (txt or "").strip()
                                                if not txt:
                                                    txt = json.dumps(j)[:80]
                                            else:
                                                txt = str(j)[:80]
                                        except Exception:
                                            txt = r.text[:80]
                                        # Map recognized text to a target view
                                        t = (txt or "").lower()
                                        target = None
                                        pairs = [
                                            ("clock", ("clock", "時計", "クロック")),
                                            ("weather", ("weather", "天気")),
                                            ("calendar", ("calendar", "カレンダー")),
                                            ("alarm", ("alarm", "アラーム")),
                                            ("voice", ("voice", "ボイス", "録音")),
                                        ]
                                        for vname, keys in pairs:
                                            for k in keys:
                                                if k in t:
                                                    target = vname
                                                    break
                                            if target:
                                                break
                                        def _apply_result():
                                            voice["status"] = txt[:40] if txt else ""
                                            if target:
                                                mode["view"] = target
                                            render()
                                        root.after(0, _apply_result)
                                    except Exception:
                                        def _apply_err():
                                            voice["status"] = "ASR error"
                                            render()
                                        root.after(0, _apply_err)
                            except Exception:
                                voice["status"] = "Record error"
                            finally:
                                voice["busy"] = False
                                root.after(0, render)
                        threading.Thread(target=_rec, daemon=True).start()
                        return
                if inside(layout.get('play_btn', (0,0,0,0))):
                    if not voice["busy"]:
                        voice["busy"] = True
                        voice["status"] = "Playing…"
                        render()
                        import threading, subprocess
                        def _play():
                            try:
                                subprocess.run(["aplay", voice["wav_path"]], check=True)
                                voice["status"] = "Played"
                            except Exception:
                                voice["status"] = "Play error"
                            finally:
                                voice["busy"] = False
                                root.after(0, render)
                        threading.Thread(target=_play, daemon=True).start()
                        return

    def close_window(event=None):
        root.attributes('-fullscreen', False)
        root.destroy()

    label.bind('<Button-1>', on_press)
    label.bind('<ButtonRelease-1>', on_release)
    root.bind('<Escape>', close_window)

    tick()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
