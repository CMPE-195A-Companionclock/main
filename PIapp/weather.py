import os
import time
from PIL import Image, ImageDraw, ImageFont, ImageTk
from io import BytesIO
import requests

# Weather API key (override via env var WEATHERAPI_KEY)
APIKeyForWeatherAPI = os.getenv("WEATHERAPI_KEY", "c526e7caac4c403e9f4212109242706")
# Optional explicit location override (city name or "lat,lon")
WEATHER_LOCATION = os.getenv("WEATHER_LOCATION")
WEATHER_LAT = os.getenv("WEATHER_LAT")
WEATHER_LON = os.getenv("WEATHER_LON")


def _ip_geolocate():
    """Try to geolocate via public IP (ip-api.com). Returns (lat, lon) or None.

    This can be more reliable than WeatherAPI's auto:ip in some networks.
    """
    try:
        r = requests.get("http://ip-api.com/json/", timeout=5)
        if r.status_code == 200:
            j = r.json()
            if j.get("status") == "success" and "lat" in j and "lon" in j:
                return (str(j["lat"]), str(j["lon"]))
    except Exception:
        pass
    return None


def _build_location_query() -> str:
    """Return a WeatherAPI q=... value based on env overrides or auto:ip.

    Priority: WEATHER_LAT/LON -> WEATHER_LOCATION -> auto:ip
    WEATHER_LOCATION can be a city name (e.g., "Tokyo") or "lat,lon".
    """
    if WEATHER_LAT and WEATHER_LON:
        return f"{WEATHER_LAT},{WEATHER_LON}"
    if WEATHER_LOCATION:
        loc = WEATHER_LOCATION.strip()
        # if looks like lat,lon keep as-is, else pass city name
        if "," in loc:
            return loc
        return loc
    # Try IP geolocation first, then fall back to WeatherAPI auto:ip
    geo = _ip_geolocate()
    if geo:
        lat, lon = geo
        return f"{lat},{lon}"
    return "auto:ip"


def getWeatherForecast(APIKey, days):
    """Fetch forecast JSON from weatherapi.com.

    Returns parsed JSON dict on success, otherwise None.
    """
    q = _build_location_query()
    weatherForecastURL = f"http://api.weatherapi.com/v1/forecast.json?key={APIKey}&q={q}&days={days}"
    try:
        response = requests.get(weatherForecastURL, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


# Window size used across UI pages
windowWidth = 1024
windowHeight = 600

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
fontPath = os.path.join(_BASE_DIR, "font", "CaviarDreams_Bold.ttf")


def _font(size: int):
    try:
        return ImageFont.truetype(fontPath, size)
    except Exception:
        return ImageFont.load_default()


def _text_size(drw: ImageDraw.ImageDraw, text: str, font):
    try:
        l, t, r, b = drw.textbbox((0, 0), text, font=font)
        return (r - l, b - t)
    except Exception:
        return drw.textsize(text, font=font)


def _draw_label_value(drw: ImageDraw.ImageDraw, left_x: int, y: int, right_x: int,
                      label: str, value: str, font, color: str):
    # label left-aligned
    drw.text((left_x, y), label, font=font, fill=color)
    # value right-aligned
    vw, _ = _text_size(drw, value, font)
    drw.text((right_x - vw, y), value, font=font, fill=color)


def drawCurrentWather(weatherForecastData=None):
    """Render the weather page as an ImageTk.PhotoImage (English labels)."""
    image = Image.new("RGBA", (windowWidth, windowHeight), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)

    if weatherForecastData is None:
        weatherForecastData = getWeatherForecast(APIKeyForWeatherAPI, 3)

    if not weatherForecastData:
        draw.text((30, 30), "Failed to fetch weather data.", font=_font(20), fill="#600000")
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

    # Layout constants (preserve original positions)
    y1TopMergin = 50
    y1stRowOffset = 70
    x1stRowOffset = 250
    y2TopMergin = y1stRowOffset + y1TopMergin + 210
    y2ndRowOffset = 70
    x2ndRightOffset = 100
    x2ndRowOffset = 330

    # Header and updated time
    draw.text((300, 20), f"{city}, {state}, {country}", font=_font(17), fill="#600000")
    draw.text((790, 570), f"Updated: {updateTime}", font=_font(17), fill="#600000")

    # Current conditions
    draw.text((x1stRowOffset, y1TopMergin), f"{currentTime} Current Weather", font=_font(20), fill="#600000")
    try:
        r = requests.get(currentWeatherIconURL, timeout=10)
        if r.status_code == 200:
            icon_image = Image.open(BytesIO(r.content)).resize((70, 70))
            image.paste(icon_image, (x1stRowOffset + 50, y1TopMergin + 20))
    except Exception:
        pass

    # Right boundary for current conditions (mirror right section padding)
    line_font = _font(20)
    labels = ["Temp:", "Feels like:", "Wind:", "Humidity:", "Sunrise:", "Sunset:"]
    values = [
        f"{currentTempInC}°C",
        f"{currentFeelsLike}°C",
        f"{currentWindSpeed} km/h",
        f"{currentHumidity}%",
        f"{sunriseToday}",
        f"{sunsetToday}",
    ]
    lbl_w_max = max(_text_size(draw, s, line_font)[0] for s in labels)
    val_w_max = max(_text_size(draw, s, line_font)[0] for s in values)
    gap = 12
    right_bound = x1stRowOffset + lbl_w_max + gap + val_w_max
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 30,  right_bound, "Temp:",       f"{currentTempInC}°C", line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 55,  right_bound, "Feels like:", f"{currentFeelsLike}°C", line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 80,  right_bound, "Wind:",       f"{currentWindSpeed} km/h", line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 105, right_bound, "Humidity:",   f"{currentHumidity}%", line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 130, right_bound, "Sunrise:",    f"{sunriseToday}", line_font, "#600000")
    _draw_label_value(draw, x1stRowOffset, y1stRowOffset + y1TopMergin + 155, right_bound, "Sunset:",     f"{sunsetToday}", line_font, "#600000")

    # 3-day forecast
    forecastDays = weatherForecastData['forecast']['forecastday']
    for counter, day in enumerate(forecastDays):
        WeatherIconURL = day['day']['condition']['icon']
        if WeatherIconURL.startswith("//"):
            WeatherIconURL = "http:" + WeatherIconURL

        margin = x2ndRowOffset * counter
        draw.text((x2ndRightOffset + margin + 20, y2TopMergin), f"{day['date']}", font=_font(20), fill="#600000")
        try:
            r = requests.get(WeatherIconURL, timeout=10)
            if r.status_code == 200:
                icon_image = Image.open(BytesIO(r.content)).resize((70, 70))
                image.paste(icon_image, (x2ndRightOffset + 40 + margin, y2TopMergin + 20))
        except Exception:
            pass
        # Column right boundary slightly inset for padding
        col_right = x2ndRightOffset + margin + x2ndRowOffset - 10
        col_left  = x2ndRightOffset + margin
        f20 = _font(20)
        # compute compact right edge per column based on max label/value widths
        lbl_samples = ["Max:", "Min:", "Chance:", "Precip:"]
        val_samples = [
            f"{day['day']['maxtemp_c']}°C",
            f"{day['day']['mintemp_c']}°C",
            f"{day['day']['daily_chance_of_rain']}%",
            f"{day['day']['totalprecip_mm']} mm",
        ]
        col_lbl_w_max = max(_text_size(draw, s, f20)[0] for s in lbl_samples)
        col_val_w_max = max(_text_size(draw, s, f20)[0] for s in val_samples)
        col_gap = 10
        col_right = col_left + col_lbl_w_max + col_gap + col_val_w_max
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 25,  col_right, "Max:",  f"{day['day']['maxtemp_c']}°C", f20, "#600000")
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 50,  col_right, "Min:",  f"{day['day']['mintemp_c']}°C", f20, "#600000")
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 75,  col_right, "Chance:",  f"{day['day']['daily_chance_of_rain']}%", f20, "#600000")
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 100, col_right, "Precip:", f"{day['day']['totalprecip_mm']} mm", f20, "#600000")
        # redraw with proper degree symbol for temperatures
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 25,  col_right, "Max:",  f"{day['day']['maxtemp_c']}°C", f20, "#600000")
        _draw_label_value(draw, col_left, y2TopMergin + y2ndRowOffset + 50,  col_right, "Min:",  f"{day['day']['mintemp_c']}°C", f20, "#600000")

    return ImageTk.PhotoImage(image)


# Optional alias with corrected spelling
def drawCurrentWeather(weatherForecastData=None):
    return drawCurrentWather(weatherForecastData)


def updateWeather():
    """Standalone demo refresh for the weather page (Tkinter)."""
    global weatherLabel
    weatherForecastData = getWeatherForecast(APIKeyForWeatherAPI, 3)
    currentWeatherImage = drawCurrentWather(weatherForecastData)
    weatherLabel.config(image=currentWeatherImage)
    weatherLabel.image = currentWeatherImage
    root.after(60000, updateWeather)


if __name__ == "__main__":
    import tkinter as tk
    root = tk.Tk()
    root.title("weatherPage")
    root.geometry(f"{windowWidth}x{windowHeight}")
    root.attributes("-fullscreen", True)
    root.configure(bg="black")
    canvas = tk.Canvas(root, width=windowWidth, height=2)
    canvas.create_line(0, 0, windowWidth, 0, fill="#600000")

    weatherLabel = tk.Label(root)
    weatherLabel.pack()

    def close_window(event=None):
        root.attributes('-fullscreen', False)
        root.destroy()

    root.bind('<Escape>', close_window)

    updateWeather()
    root.mainloop()
