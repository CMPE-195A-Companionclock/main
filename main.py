import argparse
import sys
import os
import time
from typing import Optional


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
    except Exception as e:
        print("Failed to import page modules (clock/weather/calendar/alarm).")
        print(f"Detail: {e}")
        return 1

    WINDOW_W, WINDOW_H = 1024, 600

    root = tk.Tk()
    root.title("CompanionClock")
    root.geometry(f"{WINDOW_W}x{WINDOW_H}")
    if fullscreen:
        root.attributes("-fullscreen", True)
    root.configure(bg="black")

    label = tk.Label(root)
    label.pack()

    # State
    mode = {"view": "clock"}  # calendar | weather | clock | alarm (default: clock)
    api_key: Optional[str] = os.getenv("WEATHERAPI_KEY")
    weather_data: Optional[dict] = None
    last_fetch = 0.0
    # Multiple alarms state
    alarms = {"items": [{"hour": 7, "minute": 0, "enabled": False}], "i": 0, "checked": set()}

    # Rendering separated from scheduling to avoid double timers
    def render():
        nonlocal weather_data
        v = mode["view"]
        if v == "calendar":
            tkimg = draw_calendar_page(WINDOW_W, WINDOW_H, top_margin=24)
        elif v == "weather":
            tkimg = weather_mod.drawCurrentWather(weather_data)
        elif v == "alarm":
            cur = alarms["items"][alarms["i"]]
            tkimg = draw_alarm_page(cur["hour"], cur["minute"], cur.get("enabled", False) if isinstance(cur, dict) else False,
                                     index=alarms["i"]+1, total=len(alarms["items"]),
                                     alarms=alarms["items"], selected=alarms["i"], checked=alarms["checked"]) 
        else:  # clock
            day_name = time.strftime("%a")
            today = time.strftime("%Y/%m/%d")
            current_time = time.strftime("%H:%M")
            current_sec = time.strftime("%S")
            tkimg = draw_clock_page(day_name, today, current_time, current_sec)
        label.config(image=tkimg)
        label.image = tkimg

    timer = {"id": None}
    weather_fetching = {"busy": False}

    def tick():
        nonlocal last_fetch, weather_data
        # Schedule weather refresh without blocking UI
        now = time.time()
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
                    render()
                root.after(0, _apply)
            threading.Thread(target=_do_fetch, daemon=True).start()

        render()
        timer["id"] = root.after(1000, tick)

    SWIPE_MIN_DIST = 80
    SWIPE_MAX_TIME = 0.8
    gesture = {"x": 0, "y": 0, "t": 0.0, "active": False}

    def next_view():
        # One-step to the right from clock -> weather; from calendar -> clock; at weather, stay.
        v = mode["view"]
        if v == "alarm":
            return
        if v == "clock":
            mode["view"] = "weather"
        elif v == "calendar":
            mode["view"] = "clock"
        else:  # weather
            mode["view"] = "weather"

    def prev_view():
        # One-step to the left from clock -> calendar; from weather -> clock; at calendar, stay.
        v = mode["view"]
        if v == "alarm":
            return
        if v == "clock":
            mode["view"] = "calendar"
        elif v == "weather":
            mode["view"] = "clock"
        else:  # calendar
            mode["view"] = "calendar"

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
                    next_view()
                else:
                    prev_view()
            else:
                # Vertical swipe: up -> alarm, down -> clock
                if dy < 0:
                    mode["view"] = "alarm"
                else:
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
