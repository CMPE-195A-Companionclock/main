import os
import time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageTk
import requests

# Weather API key (override via env var WEATHERAPI_KEY)
APIKeyForWeatherAPI = os.getenv("WEATHERAPI_KEY", "")
# Optional explicit location override (city name or "lat,lon")
WEATHER_LOCATION = os.getenv("WEATHER_LOCATION")
WEATHER_LAT = os.getenv("WEATHER_LAT")
WEATHER_LON = os.getenv("WEATHER_LON")

SESSION = requests.Session()

# Window size used across UI pages
windowWidth = 1024
windowHeight = 600

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
fontPath = os.path.join(_BASE_DIR, "font", "CaviarDreams_Bold.ttf")
_FONT_CACHE = {}
_ICON_CACHE = {}
DEG = "\u00B0"
ICON_SIZE_CURRENT = (120, 120)
TITLE_LEFT_PAD = 20
TITLE_X_NUDGE = -10  # shift Current Weather title slightly left
ICON_SIZE_FORECAST = (96, 96)


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


def _text_size(drw: ImageDraw.ImageDraw, text: str, font):
    try:
        l, t, r, b = drw.textbbox((0, 0), text, font=font)
        return (r - l, b - t)
    except Exception:
        return drw.textsize(text, font=font)


def _get_icon(url: str, size=(70, 70)):
    key = (url, size)
    img = _ICON_CACHE.get(key)
    if img is not None:
        return img
    r = SESSION.get(url, timeout=10)
    r.raise_for_status()
    # Keep alpha to preserve transparent backgrounds
    icon = Image.open(BytesIO(r.content)).convert("RGBA").resize(size, Image.BILINEAR)
    _ICON_CACHE[key] = icon
    return icon


def _ip_geolocate():
    try:
        r = SESSION.get("http://ip-api.com/json/", timeout=5)
        if r.status_code == 200:
            j = r.json()
            if j.get("status") == "success" and "lat" in j and "lon" in j:
                return (str(j["lat"]), str(j["lon"]))
    except Exception:
        pass
    return None


def _build_location_query() -> str:
    if WEATHER_LAT and WEATHER_LON:
        return f"{WEATHER_LAT},{WEATHER_LON}"
    if WEATHER_LOCATION:
        return WEATHER_LOCATION.strip()
    geo = _ip_geolocate()
    if geo:
        lat, lon = geo
        return f"{lat},{lon}"
    return "auto:ip"


def getWeatherForecast(APIKey, days):
    q = _build_location_query()
    url = f"http://api.weatherapi.com/v1/forecast.json?key={APIKey}&q={q}&days={days}"
    try:
        r = SESSION.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _draw_label_value(drw: ImageDraw.ImageDraw, left_x: int, y: int, right_x: int,
                      label: str, value: str, font, color: str):
    drw.text((left_x, y), label, font=font, fill=color)
    vw, _ = _text_size(drw, value, font)
    drw.text((right_x - vw, y), value, font=font, fill=color)


def drawCurrentWather(weatherForecastData=None):
    image = Image.new("RGB", (windowWidth, windowHeight), "white")
    draw = ImageDraw.Draw(image)

    if weatherForecastData is None and APIKeyForWeatherAPI:
        weatherForecastData = getWeatherForecast(APIKeyForWeatherAPI, 3)

    if not weatherForecastData:
        draw.text((30, 30), "Weather unavailable (set WEATHERAPI_KEY).", font=_font(20), fill="#600000")
        return ImageTk.PhotoImage(image)

    city = weatherForecastData['location']['name']
    state = weatherForecastData['location']['region']
    country = weatherForecastData['location']['country']
    currentTime = time.strftime("%H:%M")
    currentWeatherIconURL = "http:" + weatherForecastData['current']['condition']['icon']
    currentTempInC = weatherForecastData['current']['temp_c']
    currentHumidity = weatherForecastData['current']['humidity']
    currentWindSpeed = weatherForecastData['current']['wind_kph']
    currentFeelsLike = weatherForecastData['current']['feelslike_c']
    sunriseToday = weatherForecastData['forecast']['forecastday'][0]['astro']['sunrise']
    sunsetToday = weatherForecastData['forecast']['forecastday'][0]['astro']['sunset']
    updateTime = weatherForecastData['current']['last_updated']

    # Layout constants
    header_y = 30
    current_block_top = 110 
    forecast_block_top = 320 

    header_font = _font(30)
    title_font = _font(22)
    line_font = _font(22)
    forecast_font = _font(20)

    # Header centered; updated time right-bottom aligned
    hdr = f"{city}, {state}, {country}"
    hdr_w, hdr_h = _text_size(draw, hdr, header_font)
    draw.text(
        ((windowWidth - hdr_w) // 2, header_y),
        hdr,
        font=header_font,
        fill="#600000",
    )

    upd = f"Updated: {updateTime}"
    upd_font = _font(17)
    upd_w, upd_h = _text_size(draw, upd, upd_font)
    draw.text(
        (windowWidth - upd_w - 12, windowHeight - upd_h - 10),
        upd,
        font=upd_font,
        fill="#600000",
    )

    upd = f"Updated: {updateTime}"
    upd_font = _font(17)
    upd_w, upd_h = _text_size(draw, upd, upd_font)
    draw.text(
        (windowWidth - upd_w - 12, windowHeight - upd_h - 10),
        upd,
        font=upd_font,
        fill="#600000",
    )

    # ---------------- Current conditions (centered) ----------------
    labels = ["Temp:", "Feels like:", "Wind:", "Humidity:", "Sunrise:", "Sunset:"]
    values = [
        f"{currentTempInC}{DEG}C",
        f"{currentFeelsLike}{DEG}C",
        f"{currentWindSpeed} km/h",
        f"{currentHumidity}%",
        f"{sunriseToday}",
        f"{sunsetToday}",
    ]

    lbl_w_max = max(_text_size(draw, s, line_font)[0] for s in labels)
    val_w_max = max(_text_size(draw, s, line_font)[0] for s in values)
    gap = 14
    block_width = lbl_w_max + gap + val_w_max

    # Center the text block horizontally
    x1stRowOffset = (windowWidth - block_width) // 2
    right_bound = x1stRowOffset + block_width

    # Icon to the left of the text block, also vertically aligned with it
    try:
        icon_image = _get_icon(currentWeatherIconURL, ICON_SIZE_CURRENT)
        icon_w, icon_h = icon_image.size
        icon_x = x1stRowOffset - icon_w - 30
        icon_y = current_block_top + 10
        image.paste(icon_image, (icon_x, icon_y), icon_image)
    except Exception:
        pass

    # "Current Weather" title centered over the text block
    current_title = "Current Weather"
    title_w, title_h = _text_size(draw, current_title, title_font)
    title_x = x1stRowOffset + (block_width - title_w) // 2
    title_y = current_block_top - title_h - 10
    draw.text((title_x, title_y), current_title, font=title_font, fill="#600000")

    # Draw the label/value pairs
    base_y = current_block_top + 10
    line_step = 28
    for i, (lab, val) in enumerate(zip(labels, values)):
        y = base_y + i * line_step
        _draw_label_value(
            draw,
            x1stRowOffset,
            y,
            right_bound,
            lab,
            val,
            line_font,
            "#600000",
        )

    # ---------------- 3-day forecast (centered row) ----------------
    forecastDays = weatherForecastData["forecast"]["forecastday"]
    num_days = len(forecastDays)
    if num_days > 0:
        col_width = 260
        total_width = col_width * num_days
        start_x = max(20, (windowWidth - total_width) // 2)

        for idx, day in enumerate(forecastDays):
            WeatherIconURL = day["day"]["condition"]["icon"]
            if WeatherIconURL.startswith("//"):
                WeatherIconURL = "http:" + WeatherIconURL

            col_left = start_x + idx * col_width

            # Date at top of the column
            date_txt = f"{day['date']}"
            date_w, date_h = _text_size(draw, date_txt, forecast_font)
            draw.text(
                (col_left + (col_width - date_w) // 2, forecast_block_top),
                date_txt,
                font=forecast_font,
                fill="#600000",
            )

            # Icon below date
            try:
                icon_image = _get_icon(WeatherIconURL, ICON_SIZE_FORECAST)
                icon_w, icon_h = icon_image.size
                icon_x = col_left + (col_width - icon_w) // 2
                icon_y = forecast_block_top + date_h + 10
                image.paste(icon_image, (icon_x, icon_y), icon_image)
            except Exception:
                icon_h = ICON_SIZE_FORECAST[1]

            # Label/value pairs below icon
            col_labels = ["Max:", "Min:", "Chance:", "Precip:"]
            col_values = [
                f"{day['day']['maxtemp_c']}{DEG}C",
                f"{day['day']['mintemp_c']}{DEG}C",
                f"{day['day']['daily_chance_of_rain']}%",
                f"{day['day']['totalprecip_mm']} mm",
            ]
            col_lbl_w_max = max(_text_size(draw, s, forecast_font)[0] for s in col_labels)
            col_val_w_max = max(_text_size(draw, s, forecast_font)[0] for s in col_values)
            col_gap = 10
            col_block_width = col_lbl_w_max + col_gap + col_val_w_max

            col_block_left = col_left + (col_width - col_block_width) // 2
            col_block_right = col_block_left + col_block_width

            base_y2 = forecast_block_top + date_h + 10 + icon_h + 10
            step2 = 26
            for j, (lab, val) in enumerate(zip(col_labels, col_values)):
                y2 = base_y2 + j * step2
                _draw_label_value(
                    draw,
                    col_block_left,
                    y2,
                    col_block_right,
                    lab,
                    val,
                    forecast_font,
                    "#600000",
                )

    return ImageTk.PhotoImage(image)


# Optional alias with corrected spelling
def drawCurrentWeather(weatherForecastData=None):
    return drawCurrentWather(weatherForecastData)
