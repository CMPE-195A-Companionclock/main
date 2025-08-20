import tkinter as tk
import time
from PIL import Image, ImageDraw, ImageFont, ImageTk

class ClockScreen(tk.Frame):
    def __init__(self, parent, controller=None):
        super().__init__(parent)
        self.controller = controller

        self.windowWidth = 1024
        self.windowHeight = 600
        self.x = self.windowWidth / 2
        self.y = self.windowHeight / 2

        self.fontPath = "font/CaviarDreams_Bold.ttf"
        self.EightBitDragonDate = ImageFont.truetype(self.fontPath, 70)
        self.EightBitDragonTime = ImageFont.truetype(self.fontPath, 270)
        self.EightBitDragonSecond = ImageFont.truetype(self.fontPath, 70)

        self.image = Image.new("RGBA", (self.windowWidth, self.windowHeight), (255, 255, 255, 0))
        self.draw = ImageDraw.Draw(self.image)

        self.configure(bg="black")
        self.canvas = tk.Canvas(self, width=self.windowWidth, height=2)
        self.canvas.create_line(0, 0, self.windowWidth, 0, fill="#600000")
        self.canvas.pack()

        self.clockLabel = tk.Label(self)
        self.clockLabel.pack()

        self.bind_all('<Escape>', self.close_window)

        self.after(100, self.updateTime)

    def drawClock(self, dayName, today, currentTime, currentSecond):
        image = Image.new("RGBA", (self.windowWidth, self.windowHeight), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)

        draw.text((170, 70), f"{today} | {dayName}", font=self.EightBitDragonDate, fill="#600000")
        draw.text((50, 230), f"{currentTime}", font=self.EightBitDragonTime, fill="#600000")
        draw.text((900, 410), f"{currentSecond}", font=self.EightBitDragonSecond, fill="#600000")

        return ImageTk.PhotoImage(image)

    def updateTime(self):
        self.draw.rectangle((0, 0, self.windowWidth, self.windowHeight), fill=(255, 255, 255, 0))

        dayName = time.strftime("%a")
        today = time.strftime("%Y/%m/%d")
        currentTime = time.strftime("%H:%M")
        currentSecond = time.strftime("%S")

        self.clockImage = self.drawClock(dayName, today, currentTime, currentSecond)
        self.clockLabel.config(image=self.clockImage)

        self.after(1000, self.updateTime)

    def close_window(self, event=None):
        if self.controller:
            self.controller.attributes('-fullscreen', False)
            self.controller.destroy()