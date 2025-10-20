import tkinter as tk
import time
from PIL import Image, ImageDraw, ImageFont, ImageTk

windowWidth = 1024		# window size of the smart display
windowHeight = 600

fontPath = "./font/CaviarDreams_Bold.ttf"  # Path of the .ttf file


def drawClock(dayName, today, currentTime, currentSecond):
    image = Image.new("RGBA", (windowWidth, windowHeight), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)

    EightBitDragonDate = ImageFont.truetype(fontPath, 70)
    EightBitDragonTime = ImageFont.truetype(fontPath, 270)
    EightBitDragonSecond = ImageFont.truetype(fontPath, 70)

    draw.text((170, 70), f"{today} | {dayName}", font=EightBitDragonDate, fill="#600000")
    draw.text((50, 230), f"{currentTime}", font=EightBitDragonTime, fill="#600000")
    draw.text((900, 410), f"{currentSecond}", font=EightBitDragonSecond, fill="#600000")

    return ImageTk.PhotoImage(image)


def run(fullscreen=True):
    root = tk.Tk()
    root.title("ClockPage")
    root.geometry(f"{windowWidth}x{windowHeight}")
    if fullscreen:
        root.attributes("-fullscreen", True)
    root.configure(bg="black")

    canvas = tk.Canvas(root, width=windowWidth, height=2)
    canvas.create_line(0, 0, windowWidth, 0, fill="#600000")

    clockLabel = tk.Label(root)
    clockLabel.pack()

    def updateTime():
        dayName = time.strftime("%a")
        today = time.strftime("%Y/%m/%d")
        currentTime = time.strftime("%H:%M")
        currentSecond = time.strftime("%S")

        clockImage = drawClock(dayName, today, currentTime, currentSecond)
        clockLabel.config(image=clockImage)
        clockLabel.image = clockImage
        root.after(1000, updateTime)

    def close_window(event=None):
        root.attributes('-fullscreen', False)
        root.destroy()

    root.bind('<Escape>', close_window)
    updateTime()
    root.mainloop()


if __name__ == "__main__":
    run()
