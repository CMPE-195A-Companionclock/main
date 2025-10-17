import os
import time
from PIL import Image, ImageDraw, ImageFont, ImageTk
from typing import Optional

WINDOW_W = 1024
WINDOW_H = 600
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_FONT_PATH = os.path.join(_BASE_DIR, "font", "CaviarDreams_Bold.ttf")
_COLOR = "#600000"


def _font(size: int):
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def get_layout():
    """Clickable rects for the voice test page.

    Returns dict with keys: 'rec_btn', 'play_btn'.
    """
    btn_w, btn_h = 220, 80
    gap = 40
    total_w = 2 * btn_w + gap
    x0 = (WINDOW_W - total_w) // 2
    y = WINDOW_H // 2
    layout = {
        'rec_btn': (x0, y, x0 + btn_w, y + btn_h),
        'play_btn': (x0 + btn_w + gap, y, x0 + 2 * btn_w + gap, y + btn_h),
    }
    return layout


def _draw_button(drw: ImageDraw.ImageDraw, rect, label: str, font):
    x1, y1, x2, y2 = rect
    drw.rectangle([x1, y1, x2, y2], outline=_COLOR, width=3)
    try:
        l, t, r, b = drw.textbbox((0, 0), label, font=font)
        tw, th = r - l, b - t
    except Exception:
        tw, th = drw.textsize(label, font=font)
    tx = x1 + (x2 - x1 - tw) // 2
    ty = y1 + (y2 - y1 - th) // 2
    drw.text((tx, ty), label, font=font, fill=_COLOR)


def draw_voice_page(status_text: Optional[str] = None) -> ImageTk.PhotoImage:
    img = Image.new("RGBA", (WINDOW_W, WINDOW_H), (255, 255, 255, 0))
    drw = ImageDraw.Draw(img)

    title_f = _font(40)
    small_f = _font(24)
    drw.text(((WINDOW_W - 180) // 2, 30), "Voice Test", font=title_f, fill=_COLOR)

    layout = get_layout()
    _draw_button(drw, layout['rec_btn'], "REC", small_f)
    _draw_button(drw, layout['play_btn'], "PLAY", small_f)

    if status_text:
        try:
            l, t, r, b = drw.textbbox((0, 0), status_text, font=small_f)
            tw, th = r - l, b - t
        except Exception:
            tw, th = drw.textsize(status_text, font=small_f)
        drw.text(((WINDOW_W - tw) // 2, 140), status_text, font=small_f, fill=_COLOR)

    return ImageTk.PhotoImage(img)
