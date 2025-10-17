import os
import time
from PIL import Image, ImageDraw, ImageFont, ImageTk
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
fontPath = os.path.join(_BASE_DIR, "font", "JiyunoTsubasa.ttf")


def _font(size: int):
    try:
        return ImageFont.truetype(fontPath, size)
    except Exception:
        return ImageFont.load_default()


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
        icon_image = Image.open(requests.get(currentWeatherIconURL, stream=True, timeout=10).raw).resize((70, 70))
        image.paste(icon_image, (x1stRowOffset + 50, y1TopMergin + 20))
    except Exception:
        pass

    draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 30),  f"Temp: {currentTempInC}°C",        font=_font(20), fill="#600000")
    draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 55),  f"Feels like: {currentFeelsLike}°C", font=_font(20), fill="#600000")
    draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 80),  f"Wind: {currentWindSpeed} km/h",    font=_font(20), fill="#600000")
    draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 105), f"Humidity: {currentHumidity}%",     font=_font(20), fill="#600000")
    draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 130), f"Sunrise: {sunriseToday}",          font=_font(20), fill="#600000")
    draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 155), f"Sunset: {sunsetToday}",            font=_font(20), fill="#600000")

    # 3-day forecast
    forecastDays = weatherForecastData['forecast']['forecastday']
    for counter, day in enumerate(forecastDays):
        WeatherIconURL = day['day']['condition']['icon']
        if WeatherIconURL.startswith("//"):
            WeatherIconURL = "http:" + WeatherIconURL

        margin = x2ndRowOffset * counter
        draw.text((x2ndRightOffset + margin + 20, y2TopMergin), f"{day['date']}", font=_font(20), fill="#600000")
        try:
            icon_image = Image.open(requests.get(WeatherIconURL, stream=True, timeout=10).raw).resize((70, 70))
            image.paste(icon_image, (x2ndRightOffset + 40 + margin, y2TopMergin + 20))
        except Exception:
            pass
        draw.text((x2ndRightOffset + margin, y2TopMergin + y2ndRowOffset + 25),  f"Max: {day['day']['maxtemp_c']}°C",               font=_font(20), fill="#600000")
        draw.text((x2ndRightOffset + margin, y2TopMergin + y2ndRowOffset + 50),  f"Min: {day['day']['mintemp_c']}°C",               font=_font(20), fill="#600000")
        draw.text((x2ndRightOffset + margin, y2TopMergin + y2ndRowOffset + 75),  f"Chance of rain: {day['day']['daily_chance_of_rain']}%", font=_font(20), fill="#600000")
        draw.text((x2ndRightOffset + margin, y2TopMergin + y2ndRowOffset + 100), f"Precipitation: {day['day']['totalprecip_mm']} mm",      font=_font(20), fill="#600000")

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
