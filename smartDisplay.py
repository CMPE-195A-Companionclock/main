import tkinter as tk
from clock import ClockScreen
from calendarPage import CalendarScreen
from weather import WeatherScreen
import threading

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Display")
        self.geometry("1024x600")
        self.attributes("-fullscreen", True)

        container = tk.Frame(self)
        container.pack(fill="both", expand=True)

        self.frames = {}
        for F in (ClockScreen, CalendarScreen, WeatherScreen):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.place(relwidth=1, relheight=1)

        self.show_frame("ClockScreen")

    def show_frame(self, page_name):
        frame = self.frames[page_name]
        frame.tkraise()

def voice_command_loop(app):
    while True:
        result = input("音声コマンド（例: 時計 / カレンダー / 天気）: ")  # 仮にinput()で
        if "時計" in result:
            app.show_frame("ClockScreen")
        elif "カレンダー" in result:
            app.show_frame("CalendarScreen")
        elif "天気" in result:
            app.show_frame("WeatherScreen")

if __name__ == "__main__":
    app = App()
    threading.Thread(target=voice_command_loop, args=(app,), daemon=True).start()
    app.mainloop()