import calendar
import time
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageTk
from PIapp.calendar_service import get_calendar_service

# Pandas is optional and only used for the CLI helper that prints a DataFrame.
# Avoid importing it at module import time so the main UI can run without numpy/pandas.
try:
    import pandas as pd  # type: ignore
    _HAS_PANDAS = True
except Exception:
    pd = None  # type: ignore
    _HAS_PANDAS = False

thisYear = int(time.strftime("%Y"))
thisMonth = int(time.strftime("%m"))


def generateCalendar(thisYear, thisMonth):
    prevYear = thisYear
    nextYear = thisYear
    prevMonth = thisMonth - 1
    nextMonth = thisMonth + 1
    if prevMonth == 0:
        prevMonth = 12
        prevYear = thisYear - 1
        nextYear = thisYear + 1
    cal = calendar.Calendar(firstweekday = 0)
    currentMonthDays = list(cal.itermonthdays(thisYear, thisMonth))
    prevMonthDays = list(cal.itermonthdays(prevYear, prevMonth))
    nextMonthDays = list(cal.itermonthdays(nextYear, nextMonth))
    
    fullCalendar = []
    
    missingDaysFromPrev = sum(day == 0 for day in currentMonthDays[:7])
    fullCalendar.extend(day for day in prevMonthDays[-missingDaysFromPrev:] if day != 0)
    fullCalendar.extend(day for day in currentMonthDays if day != 0)
    
    missingDaysFromNext = (7 - len(fullCalendar) % 7) % 7
    if missingDaysFromNext < 7:
        fullCalendar.extend(nextMonthDays[:missingDaysFromNext])
        
    if _HAS_PANDAS:
        df = pd.DataFrame({'Day': fullCalendar})
        df['Year'] = thisYear
        df['Month'] = thisMonth
        df.loc[:missingDaysFromPrev - 1, 'Month'] = prevMonth
        df.loc[len(fullCalendar) - missingDaysFromNext:, 'Month'] = nextMonth
        if nextMonth == 13:
            nextMonth = 1
        return df
    else:
        # Fallback: return a simple dict payload when pandas is unavailable
        return {
            'year': thisYear,
            'month': thisMonth,
            'days': fullCalendar,
            'prevMonthPad': int(missingDaysFromPrev),
            'nextMonthPad': int(missingDaysFromNext),
        }

def main():
    cal = generateCalendar(thisYear, thisMonth)
    print(f"{cal}")

if __name__ == "__main__":
    main()


# =============== Drawing helper for main UI ===============
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

def _get_month_events(year: int, month: int):
    try:
        svc = get_calendar_service()
    except Exception as e:
        print("calendarPage: failed to init GoogleCalendarService:", e)
        return {}

    try:
        # You can tweak these if you like
        events = svc.get_upcoming_events(max_results=200, days_ahead=60)
    except Exception as e:
        print("calendarPage: failed to fetch events:", e)
        return {}

    by_day: dict[int, list[dict]] = {}
    for ev in events:
        dt = ev.get("start_datetime")
        if not dt:
            continue
        if dt.year == year and dt.month == month:
            d = dt.day
            by_day.setdefault(d, []).append(ev)

    return by_day

def draw_calendar_image(width: int = 1024, height: int = 600, top_margin: int = 20):
    """Return ImageTk.PhotoImage calendar for the current month.

    top_margin: extra padding from the very top to avoid overlapping UI chrome.
    """
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    drw = ImageDraw.Draw(img)

    today = datetime.now()
    year, month = today.year, today.month

    # Fetch events grouped by day for this month
    events_by_day = _get_month_events(year, month)

    cal = calendar.Calendar(firstweekday=0)
    days = list(cal.itermonthdays(year, month))

    title_font = _font(28)
    day_font = _font(18)
    hdr_font = _font(16)
    event_title_font = _font(12)  # small font for titles

    title = f"{year}/{month:02d}"
    try:
        left, top, right, bottom = drw.textbbox((0, 0), title, font=title_font)
        tw, th = right - left, bottom - top
    except Exception:
        tw, th = drw.textsize(title, font=title_font)

    # Month title
    drw.text(
        ((width - tw) // 2, 10 + top_margin),
        title,
        font=title_font,
        fill=_COLOR,
    )

    cols, rows = 7, 6
    grid_top = 110 + top_margin
    cell_w = width // cols
    cell_h = (height - grid_top) // rows

    # Weekday headers
    wd_names = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    for c, name in enumerate(wd_names):
        drw.text(
            (c * cell_w + 6, grid_top - 18),
            name,
            font=hdr_font,
            fill=_COLOR,
        )

    # Color for event markers (fits your maroon theme)
    event_color = "#AA4444"

    row = col = 0
    for d in days:
        if d == 0:
            # empty cell (padding days)
            col += 1
            if col == cols:
                col = 0
                row += 1
            continue

        x = col * cell_w
        y = grid_top + row * cell_h

        # Highlight *today* with a rectangle (as before)
        if d == today.day:
            drw.rectangle(
                [x + 2, y + 2, x + cell_w - 2, y + cell_h - 2],
                outline=_COLOR,
                width=2,
            )

        # Day number
        drw.text((x + 6, y + 4), str(d), font=day_font, fill=_COLOR)

        # ---------- Google Calendar events for this day ----------
        day_events = events_by_day.get(d, [])
        if day_events:
            # 1) Dots along the bottom of the cell
            max_markers = min(len(day_events), 3)
            radius = 4
            gap = 3

            total_width = max_markers * (2 * radius) + (max_markers - 1) * gap
            start_x = x + (cell_w - total_width) // 2
            dot_y = y + cell_h - 12

            for i in range(max_markers):
                cx = start_x + i * (2 * radius + gap)
                drw.ellipse(
                    [cx, dot_y, cx + 2 * radius, dot_y + 2 * radius],
                    fill=event_color,
                    outline=None,
                )

            # 2) Short event titles just above the dots
            max_chars = max(6, cell_w // 8)  # rough width limit
            titles = []
            for ev in day_events[:2]:  # show at most 2 titles per day
                t = (ev.get("summary") or "").strip()
                if not t:
                    continue
                if len(t) > max_chars:
                    t = t[: max_chars - 1] + "…"
                titles.append(t)

            if titles:
                title_text = " / ".join(titles)
                title_y = dot_y - 16  # a bit above the dots
                drw.text(
                    (x + 4, title_y),
                    title_text,
                    font=event_title_font,
                    fill=event_color,
                )
        # ---------------------------------------------------------

        # Move to next cell
        col += 1
        if col == cols:
            col = 0
            row += 1
            
    return ImageTk.PhotoImage(img)