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
ICON_SIZE_CURRENT = (96, 96)
TITLE_LEFT_PAD = 20
TITLE_X_NUDGE = -10  # shift Current Weather title slightly left
ICON_SIZE_FORECAST = (80, 80)


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
    y1TopMergin = 50
    y1stRowOffset = 70
    x1stRowOffset = 250
    y2TopMergin = y1stRowOffset + y1TopMergin + 210
    y2ndRowOffset = 70
    x2ndRightOffset = 100
    x2ndRowOffset = 330

    # Header centered; updated time right-bottom aligned
    hdr = f"{city}, {state}, {country}"
    hdr_w, _ = _text_size(draw, hdr, _font(26))
    draw.text(((windowWidth - hdr_w) // 2, 20), hdr, font=_font(26), fill="#600000")
    upd = f"Updated: {updateTime}"
    upd_w, _ = _text_size(draw, upd, _font(17))
    draw.text((windowWidth - upd_w - 10, 570), upd, font=_font(17), fill="#600000")

    # Current conditions title will be drawn after computing text block width
    title = "Current Weather"
    try:
        icon_image = _get_icon(currentWeatherIconURL, ICON_SIZE_CURRENT)
        # Paste with mask so alpha is respected over white background
        image.paste(icon_image, (x1stRowOffset + 50, y1TopMergin + 40), icon_image)
    except Exception:
        pass

    line_font = _font(20)
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
    gap = 12
    right_bound = x1stRowOffset + lbl_w_max + gap + val_w_max
    # Draw title centered within the text block cell with a bit of left padding
    cell_left = x1stRowOffset + TITLE_LEFT_PAD
    cell_right = right_bound
    title_w, _ = _text_size(draw, title, _font(20))
    draw.text((cell_left + (cell_right - cell_left - title_w)//2 + TITLE_X_NUDGE, y1TopMergin + 20), title, font=_font(20), fill="#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 50,  right_bound, "Temp:",       values[0], line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 75,  right_bound, "Feels like:", values[1], line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 100,  right_bound, "Wind:",       values[2], line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 125, right_bound, "Humidity:",   values[3], line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 150, right_bound, "Sunrise:",    values[4], line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 175, right_bound, "Sunset:",     values[5], line_font, "#600000")

    # 3-day forecast
    forecastDays = weatherForecastData['forecast']['forecastday']
    for counter, day in enumerate(forecastDays):
        WeatherIconURL = day['day']['condition']['icon']
        if WeatherIconURL.startswith("//"):
            WeatherIconURL = "http:" + WeatherIconURL

        margin = x2ndRowOffset * counter
        col_left  = x2ndRightOffset + margin
        # Left-align the date text within the forecast column
        date_txt = f"{day['date']}"
        draw.text((col_left + 20, y2TopMergin + 20), date_txt, font=_font(20), fill="#600000")
        try:
            icon_image = _get_icon(WeatherIconURL, ICON_SIZE_FORECAST)
            image.paste(icon_image, (x2ndRightOffset + 40 + margin, y2TopMergin + 40), icon_image)
        except Exception:
            pass
        # Column metrics
        f20 = _font(20)
        col_labels = ["Max:", "Min:", "Chance:", "Precip:"]
        col_values = [
            f"{day['day']['maxtemp_c']}{DEG}C",
            f"{day['day']['mintemp_c']}{DEG}C",
            f"{day['day']['daily_chance_of_rain']}%",
            f"{day['day']['totalprecip_mm']} mm",
        ]
        col_lbl_w_max = max(_text_size(draw, s, f20)[0] for s in col_labels)
        col_val_w_max = max(_text_size(draw, s, f20)[0] for s in col_values)
        col_gap = 10
        col_right = col_left + col_lbl_w_max + col_gap + col_val_w_max
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 45,  col_right, col_labels[0], col_values[0], f20, "#600000")
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 70,  col_right, col_labels[1], col_values[1], f20, "#600000")
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 95,  col_right, col_labels[2], col_values[2], f20, "#600000")
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 120, col_right, col_labels[3], col_values[3], f20, "#600000")

    return ImageTk.PhotoImage(image)


# Optional alias with corrected spelling
def drawCurrentWeather(weatherForecastData=None):
    return drawCurrentWather(weatherForecastData)
