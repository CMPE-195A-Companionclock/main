import tkinter as tk
import time
from PIL import Image, ImageDraw, ImageFont, ImageTk

windowWidth = 1024
windowHeight = 600

fontPath = "./font/CaviarDreams_Bold.ttf"

_FONT_CACHE = {}
_BG_CACHE = {"key": None, "img": None}
_HHMM_CACHE = {"key": None, "img": None}


def _font(size: int):
    f = _FONT_CACHE.get(size)
    if f is not None:
        return f
    try:
        f = ImageFont.truetype(fontPath, size)
    except Exception:
        f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


def _build_background(date_text: str):
    img = Image.new("RGB", (windowWidth, windowHeight), "white")
    drw = ImageDraw.Draw(img)
    drw.text((170, 70), date_text, font=_font(70), fill="#600000")
    return img


def _build_hhmm_tile(hhmm: str):
    tmp = Image.new("RGB", (1, 1), "white")
    drw = ImageDraw.Draw(tmp)
    try:
        l, t, r, b = drw.textbbox((0, 0), hhmm, font=_font(300))
        w, h = r - l, b - t
        off = (-l, -t)
    except Exception:
        w, h = drw.textsize(hhmm, font=_font(300))
        off = (0, 0)
    tile = Image.new("RGB", (w, h), "white")
    d2 = ImageDraw.Draw(tile)
    d2.text(off, hhmm, font=_font(300), fill="#600000")
    return tile


def _build_sec_tile(sec: str):
    tmp = Image.new("RGB", (1, 1), "white")
    drw = ImageDraw.Draw(tmp)
    try:
        l, t, r, b = drw.textbbox((0, 0), sec, font=_font(70))
        w, h = r - l, b - t
        off = (-l, -t)
    except Exception:
        w, h = drw.textsize(sec, font=_font(70))
        off = (0, 0)
    tile = Image.new("RGB", (w, h), "white")
    d2 = ImageDraw.Draw(tile)
    d2.text(off, sec, font=_font(70), fill="#600000")
    return tile


def drawClock(dayName, today, currentTime, currentSecond):
    date_text = f"{today} | {dayName}"
    if _BG_CACHE["key"] != date_text:
        _BG_CACHE["img"] = _build_background(date_text)
        _BG_CACHE["key"] = date_text

    if _HHMM_CACHE["key"] != currentTime:
        _HHMM_CACHE["img"] = _build_hhmm_tile(currentTime)
        _HHMM_CACHE["key"] = currentTime

    base = _BG_CACHE["img"].copy()
    base.paste(_HHMM_CACHE["img"], (50, 230))
    sec_tile = _build_sec_tile(currentSecond)
    base.paste(sec_tile, (920, 410))
    return ImageTk.PhotoImage(base)


def run(fullscreen=True):
    root = tk.Tk()
    root.title("ClockPage")
    root.geometry(f"{windowWidth}x{windowHeight}")
    if fullscreen:
        root.attributes("-fullscreen", True)
    root.configure(bg="black")

    canvas = tk.Canvas(root, width=windowWidth, height=2)
    canvas.create_line(0, 0, windowWidth, 0, fill="#600000")

    clockLabel = tk.Label(root)
    clockLabel.pack()

    def updateTime():
        dayName = time.strftime("%a")
        today = time.strftime("%Y/%m/%d")
        currentTime = time.strftime("%H:%M")
        currentSecond = time.strftime("%S")

        clockImage = drawClock(dayName, today, currentTime, currentSecond)
        clockLabel.config(image=clockImage)
        clockLabel.image = clockImage
        root.after(1000, updateTime)

    def close_window(event=None):
        root.attributes('-fullscreen', False)
        root.destroy()

    root.bind('<Escape>', close_window)
    updateTime()
    root.mainloop()


if __name__ == "__main__":
    run()
