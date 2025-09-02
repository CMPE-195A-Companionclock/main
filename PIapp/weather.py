#http://api.weatherapi.com/v1 #base url for weather API
#API key for weatherAPI= c526e7caac4c403e9f4212109242706

import tkinter as tk
import time
from PIL import Image, ImageDraw, ImageFont, ImageTk
import requests

APIKeyForWeatherAPI = "c526e7caac4c403e9f4212109242706"
    
def getWeatherForecast(APIKey,days):
    weatherForecastURL = f"http://api.weatherapi.com/v1/forecast.json?key={APIKey}&q=auto:ip&days={days}"
    response = requests.get(weatherForecastURL)
    if response.status_code == 200:
        return response.json()
    else:
        return None
    
windowWidth = 1024		#window size of the smart display
windowHeight = 600

image = Image.new("RGBA", (windowWidth, windowHeight), (255, 255, 255, 0))
draw = ImageDraw.Draw(image)

fontPath = "./font/JiyunoTsubasa.ttf"

CustomFont = ImageFont.truetype(fontPath, 20)
CustomFontSmall = ImageFont.truetype(fontPath, 17)

def drawCurrentWather(weatherForecastData):
    image = Image.new("RGBA", (windowWidth,windowHeight), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    weatherForecastData = getWeatherForecast(APIKeyForWeatherAPI, 3)
    currentCityName = weatherForecastData['location']['name']
    CurrentStateName = weatherForecastData['location']['region']
    CurrentCountryName = weatherForecastData['location']['country']
    currentTime = time.strftime("%H:%M") 
    currentWeatherIconURL = "http:" +  weatherForecastData['current']['condition']['icon']
    currentTempInC = weatherForecastData['current']['temp_c']
    currentHumidity = weatherForecastData['current']['humidity']
    currentWindSpeed = weatherForecastData['current']['wind_kph']
    currentFeelsLike = weatherForecastData['current']['feelslike_c']
    sunriseToday = weatherForecastData['forecast']['forecastday'][0]['astro']['sunrise']
    sunsetToday = weatherForecastData['forecast']['forecastday'][0]['astro']['sunset']
    updateTime = weatherForecastData['current']['last_updated']
        
    if weatherForecastData:
        counter = 0
        y1TopMergin = 50
        y1stRowOffset = 70  # アイコンの下にテキストを配置するためのオフセット
        x1stRowOffset = 250
        y2TopMergin = y1stRowOffset + y1TopMergin + 210
        y2ndRowOffset = 70  # アイコンの下にテキストを配置するためのオフセット
        x2ndRightOffset = 100
        x2ndRowOffset = 330
        draw.text((300, 20), f"現在地 {currentCityName}, {CurrentStateName}, {CurrentCountryName}", font = CustomFontSmall, fill = "#600000")
        draw.text((790, 570), f"最終更新 {updateTime}", font = CustomFontSmall, fill = "#600000")
        
        draw.text((x1stRowOffset, y1TopMergin), f"{currentTime} 現在の天気", font = CustomFont, fill = "#600000") #text(50,50) means the left upper corner is 50 pixcel down, 50 pixel left form bace picture's left upper corner
        icon_image = Image.open(requests.get(currentWeatherIconURL, stream = True).raw).resize((70, 70))
        image.paste(icon_image, (x1stRowOffset + 50, y1TopMergin + 20))
        draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 30), f"気温         {currentTempInC}℃", font = CustomFont, fill = "#600000")
        draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 55), f"体感温度   {currentFeelsLike}℃", font = CustomFont, fill = "#600000")
        draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 80), f"風速       {currentWindSpeed} km/h", font = CustomFont, fill = "#600000")
        draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 105), f"湿度          {currentHumidity}%", font = CustomFont, fill = "#600000")
        draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 130), f"日の出     {sunriseToday}", font = CustomFont, fill = "#600000")
        draw.text((x1stRowOffset, y1stRowOffset + y1TopMergin + 155), f"日の入り   {sunsetToday}", font = CustomFont, fill = "#600000")
    
        forecastDays = weatherForecastData['forecast']['forecastday']
        for counter, day in enumerate(forecastDays):
            WeatherIconURL = day['day']['condition']['icon']
            if WeatherIconURL.startswith("//"):
                WeatherIconURL = "http:" + WeatherIconURL
            else:
                WeatherIconURL = WeatherIconURL
                
            margin = x2ndRowOffset * counter
            draw.text((x2ndRightOffset + margin + 20, y2TopMergin), f"{day['date']}", font = CustomFont, fill = "#600000")
            icon_image = Image.open(requests.get(WeatherIconURL, stream = True).raw).resize((70, 70))
            image.paste(icon_image, (x2ndRightOffset + 40 + margin, y2TopMergin + 20))
            draw.text((x2ndRightOffset + margin, y2TopMergin + y2ndRowOffset + 25), f"最高気温   {day['day']['maxtemp_c']}℃", font = CustomFont, fill = "#600000")
            draw.text((x2ndRightOffset + margin, y2TopMergin + y2ndRowOffset + 50), f"最低気温   {day['day']['mintemp_c']}℃", font = CustomFont, fill = "#600000")
            draw.text((x2ndRightOffset + margin, y2TopMergin + y2ndRowOffset + 75), f"降水確率     {day['day']['daily_chance_of_rain']}%", font = CustomFont, fill = "#600000")
            draw.text((x2ndRightOffset + margin, y2TopMergin + y2ndRowOffset + 100), f"降水量       {day['day']['totalprecip_mm']}%", font = CustomFont, fill = "#600000")
            
        return ImageTk.PhotoImage(image)
    
    else:
        draw.text((30,30), f"天気予報データの取得に失敗しました。", font = CustomFont, fill = "#600000")
        return ImageTk.PhotoImage(image)

def updateWeather():
    weatherForecastData = getWeatherForecast(APIKeyForWeatherAPI, 3)
    draw.rectangle((0, 0, windowWidth, windowHeight), fill = (255, 255, 255, 0))
    
    currentWeatherImage = drawCurrentWather(weatherForecastData)
    
#    # Update labels with new images 
    weatherLabel.config(image = currentWeatherImage)
    weatherLabel.image = currentWeatherImage
    
#    # Schedule the next update
    root.after(60000, updateWeather)

root = tk.Tk()
root.title("weatherPage")
root.geometry(f"{windowWidth}x{windowHeight}")	#setting windowsize for testing 
root.attributes("-fullscreen", True)	#make the soft fullscreen
root.configure(bg="black")
canvas = tk.Canvas(root, width = windowWidth, height = 2)
canvas.create_line(0, 0, windowWidth, 0, fill = "#600000")

weatherLabel = tk.Label(root)

weatherLabel.pack()

def close_window(event = None):
    root.attributes('-fullscreen', False)  
    root.destroy()

root.bind('<Escape>', close_window)

updateWeather()
root.mainloop()

#if weatherForecastData:
#    print("今日の天気")
#    print(f"現在地: {weatherForecastData['location']['name']}, {weatherForecastData['location']['region']}, {weatherForecastData['location']['country']}")
#    print(f"現在時刻: {weatherForecastData['location']['localtime']}")
#    print(f"現在の天気: {weatherForecastData['current']['condition']['icon']}")
#    print(f"気温: {weatherForecastData['current']['temp_c']} ℃")
#    print(f"湿度: {weatherForecastData['current']['humidity']} %")
#    print(f"風速: {weatherForecastData['current']['wind_kph']} km/h")
#    print(f"気圧: {weatherForecastData['current']['pressure_mb']} hPa")
#    print(f"体感温度: {weatherForecastData['current']['feelslike_c']} ℃\n")
    
#    print("今週の天気:")
#    forecastDays = weatherForecastData['forecast']['forecastday']
#    for day in forecastDays:
#        print(f"日付: {day['date']}")
#        print(f"天気: {day['day']['condition']['icon']}")
#        print(f"最高気温: {day['day']['maxtemp_c']} ℃")
#        print(f"最低気温: {day['day']['mintemp_c']} ℃ \n")
#else:
#    print("天気予報データの取得に失敗しました。")
#print(weatherForecastData)

