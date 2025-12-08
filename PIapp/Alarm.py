import os
from PIL import Image, ImageDraw, ImageFont, ImageTk

WINDOW_W = 1024
WINDOW_H = 600
LIST_W = 260  # left sidebar width for alarm list
TIME_FONT_SIZE = 120
TIME_OFFSET_Y = -70  # lift the entire alarm block further upward
BTN_SIZE = 56

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_FONT_PATH = os.path.join(_BASE_DIR, "font", "CaviarDreams_Bold.ttf")
_COLOR = "#600000"


_FONT_CACHE = {}
def _font(size: int):
    f = _FONT_CACHE.get(size)
    if f is not None:
        return f
    try:
        f = ImageFont.truetype(_FONT_PATH, size)
    except Exception:
        f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


def get_layout(hour: int, minute: int, total: int = 1, selected: int = 0):
    """Return clickable button rectangles used by the alarm UI.

    Rect format: (x1, y1, x2, y2)
    Keys include per-digit controls:
      - 'h_ones_plus', 'h_ones_minus'  (hours tens removed)
      - 'm_tens_plus', 'm_tens_minus', 'm_ones_plus', 'm_ones_minus'
      - 'ampm' (AM/PM toggle)
      - 'back'
    """
    # Measure overall time text and per-digit widths
    time_f = _font(TIME_FONT_SIZE)
    hour12 = (hour % 12) or 12
    time_txt = f"{hour12:02d}:{minute:02d}"
    dr = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    try:
        l, t, r, b = dr.textbbox((0, 0), time_txt, font=time_f)
        total_w, total_h = r - l, b - t
    except Exception:
        total_w, total_h = dr.textsize(time_txt, font=time_f)

    # Per character widths
    chars = [f"{hour12:02d}"[0], f"{hour12:02d}"[1], ":", f"{minute:02d}"[0], f"{minute:02d}"[1]]
    widths = []
    for ch in chars:
        try:
            l, t, r, b = dr.textbbox((0, 0), ch, font=time_f)
            widths.append(r - l)
        except Exception:
            w, h = dr.textsize(ch, font=time_f)
            widths.append(w)

    content_x0 = LIST_W + 20
    content_w = WINDOW_W - content_x0 - 20
    start_x = content_x0 + (content_w - total_w) // 2
    top_y = (WINDOW_H - total_h) // 2 + TIME_OFFSET_Y
    bottom_y = top_y + total_h

    # Compute x positions for each char
    x_positions = [start_x]
    for w in widths[:-1]:
        x_positions.append(x_positions[-1] + w)

    # Map positions
    h_tens_x, h_ones_x, colon_x, m_tens_x, m_ones_x = x_positions
    h_tens_w, h_ones_w, colon_w, m_tens_w, m_ones_w = widths

    # Button geometry
    pad_up = 24   # move the plus a bit higher
    pad_dn = 8
    btn_h = BTN_SIZE

    def above_rect(x, w):
        return (x, top_y - pad_up - btn_h, x + w, top_y - pad_up)

    def below_rect(x, w):
        return (x, bottom_y + pad_dn, x + w, bottom_y + pad_dn + btn_h)

    # Per-digit +/- buttons (hours tens removed; minutes tens kept)
    layout = {
        'h_ones_plus': above_rect(h_ones_x, h_ones_w),
        'h_ones_minus': below_rect(h_ones_x, h_ones_w),
        'm_tens_plus': above_rect(m_tens_x, m_tens_w),
        'm_tens_minus': below_rect(m_tens_x, m_tens_w),
        'm_ones_plus': above_rect(m_ones_x, m_ones_w),
        'm_ones_minus': below_rect(m_ones_x, m_ones_w),
    }

    # AM/PM buttons to the right of time (two buttons)
    ampm_w, ampm_h = 60, 48  # smaller boxes
    ampm_y_offset = 22       # nudge a bit lower
    ampm_x1 = start_x + total_w + 20
    base_y = top_y + (total_h - ampm_h)//2 + ampm_y_offset
    layout['am_btn'] = (ampm_x1, base_y, ampm_x1 + ampm_w, base_y + ampm_h)
    layout['pm_btn'] = (ampm_x1 + ampm_w + 10, base_y,
                        ampm_x1 + 2*ampm_w + 10, base_y + ampm_h)

    # Bottom buttons in list area: split width into two large buttons (trash and add)
    list_pad = 16
    bottom_h = 48
    bottom_y = WINDOW_H - bottom_h - 16
    half_w = (LIST_W - 2*list_pad - 8) // 2
    layout['list_trash'] = (list_pad, bottom_y, list_pad + half_w, bottom_y + bottom_h)
    layout['list_add'] = (list_pad + half_w + 8, bottom_y, list_pad + 2*half_w + 8, bottom_y + bottom_h)

    # Bottom row: back centered
    y_buttons = WINDOW_H - 150
    legacy_btn_w, legacy_btn_h = 140, 44
    layout['back'] = (WINDOW_W//2 - legacy_btn_w//2, y_buttons, WINDOW_W//2 + legacy_btn_w//2, y_buttons + legacy_btn_h)

    # Left list items hit areas
    list_pad = 16
    hdr_h = 32
    item_h = 48
    gap_h = 8
    y0 = 20 + hdr_h + 10
    x1 = list_pad
    x2 = LIST_W - list_pad
    # Ensure items do not overlap bottom buttons
    max_items_area_h = bottom_y - y0 - 10
    max_items = max(0, int((max_items_area_h + gap_h) // (item_h + gap_h)))
    count = min(total, max_items)
    for i in range(count):
        y1 = y0 + i * (item_h + gap_h)
        y2 = y1 + item_h
        layout[f'list_{i}'] = (x1, y1, x2, y2)
        # checkbox square on left inside list item
        cb_size = 24
        layout[f'list_check_{i}'] = (x1 + 6, y1 + (item_h - cb_size)//2, x1 + 6 + cb_size, y1 + (item_h + cb_size)//2)

    return layout


def _draw_button(drw: ImageDraw.ImageDraw, rect, label: str, font):
    x1, y1, x2, y2 = rect
    drw.rectangle([x1, y1, x2, y2], outline=_COLOR, width=2)
    try:
        l, t, r, b = drw.textbbox((0, 0), label, font=font)
        tw, th = r - l, b - t
    except Exception:
        tw, th = drw.textsize(label, font=font)
    tx = x1 + (x2 - x1 - tw) // 2
    ty = y1 + (y2 - y1 - th) // 2
    drw.text((tx, ty), label, font=font, fill=_COLOR)


def _draw_text_centered(drw: ImageDraw.ImageDraw, rect, label: str, font):
    x1, y1, x2, y2 = rect
    try:
        l, t, r, b = drw.textbbox((0, 0), label, font=font)
        tw, th = r - l, b - t
    except Exception:
        tw, th = drw.textsize(label, font=font)
    tx = x1 + (x2 - x1 - tw) // 2
    ty = y1 + (y2 - y1 - th) // 2
    drw.text((tx, ty), label, font=font, fill=_COLOR)


from typing import Optional, List, Set

def draw_alarm(hour: int, minute: int, enabled: bool, index: int = 1, total: int = 1,
               alarms: Optional[List] = None, selected: int = 0, checked: Optional[Set] = None,
               commute_origin: Optional[str] = None, commute_destination: Optional[str] = None,
               prep_minutes: Optional[int] = None) -> ImageTk.PhotoImage:
    """Return an ImageTk.PhotoImage showing an alarm settings view with buttons."""
    # Solid white to align with the main clock page background
    img = Image.new("RGB", (WINDOW_W, WINDOW_H), "white")
    drw = ImageDraw.Draw(img)

    title_f = _font(40)
    time_f = _font(TIME_FONT_SIZE)
    small_f = _font(22)

    title = "Alarm"
    try:
        l, t, r, b = drw.textbbox((0, 0), title, font=title_f)
        tw, th = r - l, b - t
    except Exception:
        tw, th = drw.textsize(title, font=title_f)
    # Title centered within content area (excluding list)
    content_x0 = LIST_W + 20
    content_w = WINDOW_W - content_x0 - 20
    drw.text((content_x0 + (content_w - tw) // 2, 20), title, font=title_f, fill=_COLOR)

    # Display in 12-hour format with AM/PM
    hour12 = (hour % 12) or 12
    time_txt = f"{hour12:02d}:{minute:02d}"
    try:
        l, t, r, b = drw.textbbox((0, 0), time_txt, font=time_f)
        ww, wh = r - l, b - t
    except Exception:
        ww, wh = drw.textsize(time_txt, font=time_f)
    cx = content_x0 + (content_w - ww) // 2
    cy = (WINDOW_H - wh) // 2 + TIME_OFFSET_Y
    drw.text((cx, cy), time_txt, font=time_f, fill=_COLOR)

    # Commute info (if available)
    info_y = cy + wh + 150  # raise info block a bit (still below time)
    line_h = 44  # larger line spacing
    info_f = _font(22)
    origin_txt = (commute_origin or "Please set the current location").strip()
    dest_txt = (commute_destination or "Please set the destination").strip()
    prep_txt = f"{prep_minutes} min" if prep_minutes is not None else "Please set the preparation time"
    # Left-align the three lines under the time
    text_x = content_x0 + 30
    def _draw_label_value(y, label, value):
        # Keep all values aligned by padding past the label width
        try:
            l, t, r, b = drw.textbbox((0, 0), label, font=info_f)
            lw = r - l
        except Exception:
            lw, _ = drw.textsize(label, font=info_f)
        drw.text((text_x, y), label, font=info_f, fill=_COLOR)
        msg_x = text_x + max(lw + 12, 90)
        drw.text((msg_x, y), value, font=info_f, fill=_COLOR)

    _draw_label_value(info_y, f"From:", origin_txt)
    _draw_label_value(info_y + line_h, f"To:", dest_txt)
    _draw_label_value(info_y + 2 * line_h, f"Prep:", prep_txt)

    # Draw +/- above/below the hour and minute numbers
    layout = get_layout(hour, minute, total=total, selected=selected)
    small_f = _font(20)
    big_f = _font(56)
    # +/-: frameless and large per digit
    _draw_text_centered(drw, layout['h_ones_plus'], "+", big_f)
    _draw_text_centered(drw, layout['h_ones_minus'], "-", big_f)
    _draw_text_centered(drw, layout['m_tens_plus'], "+", big_f)
    _draw_text_centered(drw, layout['m_tens_minus'], "-", big_f)
    _draw_text_centered(drw, layout['m_ones_plus'], "+", big_f)
    _draw_text_centered(drw, layout['m_ones_minus'], "-", big_f)

    # AM/PM toggle
    # AM / PM buttons
    _draw_button(drw, layout['am_btn'], "AM", small_f)
    _draw_button(drw, layout['pm_btn'], "PM", small_f)

    # No Back button (use swipe down)

    # Left list sidebar
    drw.line([(LIST_W, 0), (LIST_W, WINDOW_H)], fill=_COLOR, width=2)
    hdr_font = _font(26)
    drw.text((16, 20), "Alarms", font=hdr_font, fill=_COLOR)
    # Bottom buttons in list area
    _draw_button(drw, layout['list_trash'], "DEL", _font(22))
    _draw_button(drw, layout['list_add'], "+", _font(28))

    if alarms:
        for i in range(total):
            rect = layout.get(f'list_{i}')
            if not rect:
                continue
            x1, y1, x2, y2 = rect
            # Highlight selected
            if i == selected:
                drw.rectangle([x1, y1, x2, y2], outline=_COLOR, width=3)
            else:
                drw.rectangle([x1, y1, x2, y2], outline=_COLOR, width=1)
            a = alarms[i]
            h12 = (a.get('hour', 0) % 12) or 12
            m = a.get('minute', 0)
            ampm = 'PM' if a.get('hour', 0) >= 12 else 'AM'
            label = f"{h12:02d}:{m:02d} {ampm}"
            # draw checkbox
            cb = layout.get(f'list_check_{i}')
            if cb:
                xcb1, ycb1, xcb2, ycb2 = cb
                drw.rectangle([xcb1, ycb1, xcb2, ycb2], outline=_COLOR, width=2)
                if checked and i in checked:
                    _draw_text_centered(drw, cb, "X", _font(20))
            # text with left padding (after checkbox)
            tx_rect = (xcb2 + 8 if cb else x1 + 8, y1, x2 - 6, y2)
            _draw_text_centered(drw, tx_rect, label, _font(22))

    return ImageTk.PhotoImage(img)
