import tkinter as tk
import time
from PIL import Image, ImageDraw, ImageFont, ImageTk

windowWidth = 1024		#window size of the smart display
windowHeight = 600			

x = windowWidth / 2 	#the middle point of the window
y = windowHeight / 2

image = Image.new("RGBA", (windowWidth, windowHeight), (255, 255, 255, 0))
draw = ImageDraw.Draw(image)

fontPath = "./font/EightBitDragon-anqx.ttf"		#Path of the .ttf file

EightBitDragonDate = ImageFont.truetype(fontPath, 70)
EightBitDragonTime = ImageFont.truetype(fontPath, 270)
EightBitDragonSecond = ImageFont.truetype(fontPath, 70)

root = tk.Tk()
root.title("ClockPage") 
root.geometry(f"{windowWidth}x{windowHeight}")	#setting windowsize for testing 
root.attributes("-fullscreen", True)	#make the soft fullscreen
root.configure(bg="black")
canvas = tk.Canvas(root, width = windowWidth, height = 2)
canvas.create_line(0, 0, windowWidth, 0, fill = "#600000")

clockLabel = tk.Label(root)

clockLabel.pack()

def drawClock(dayName, today, currentTime, currentSecond):
    image = Image.new("RGBA", (windowWidth,windowHeight), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
   
    draw.text((170, 70), f"{today} | {dayName}", font = EightBitDragonDate, fill = "#600000") #text(50,50) means the left upper corner is 50 pixcel down, 50 pixel left form bace picture's left upper corner
    draw.text((50, 230), f"{currentTime}", font = EightBitDragonTime, fill = "#600000")
    draw.text((900, 410), f"{currentSecond}", font = EightBitDragonSecond, fill = "#600000")
    
    return ImageTk.PhotoImage(image)

def updateTime():
    draw.rectangle((0, 0, windowWidth, windowHeight), fill = (255, 255, 255, 0))
    
    dayName = time.strftime("%a")  #%A for Full day name (e.g., "Monday"), %a for short name(e.g., "Mon")
    today = time.strftime("%Y/%m/%d")  #Date in yyyy-mm-dd format
    currentTime = time.strftime("%H:%M")
    currentSecond = time.strftime("%S")
    
    clockImage = drawClock(dayName, today, currentTime, currentSecond)
    
    # Update labels with new images 
    clockLabel.config(image = clockImage)
    clockLabel.image = clockImage
    
    # Schedule the next update
    root.after(1000, updateTime)

def close_window(event = None):
    root.attributes('-fullscreen', False)  
    root.destroy()

root.bind('<Escape>', close_window)
updateTime()
root.mainloop()