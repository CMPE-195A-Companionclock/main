"""
Calendar UI Page for CompanionClock
Displays Google Calendar events with touch-friendly interface
"""

import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
from PIL import Image, ImageTk
import threading
import time

from google_calendar_service import get_calendar_service, GoogleCalendarService


class CalendarPage(tk.Frame):
    """
    Calendar page displaying Google Calendar events
    """
    
    def __init__(self, parent, font_path: str = "font/CaviarDreams_Bold.ttf",
                 bg_color: str = "#000000", text_color: str = "#FFFFFF",
                 accent_color: str = "#4285F4"):
        """
        Initialize the Calendar page
        
        Args:
            parent: Parent Tkinter widget
            font_path: Path to the custom font file
            bg_color: Background color
            text_color: Text color
            accent_color: Accent color for highlights
        """
        super().__init__(parent, bg=bg_color)
        
        self.bg_color = bg_color
        self.text_color = text_color
        self.accent_color = accent_color
        self.font_path = font_path
        
        # Calendar service
        self.calendar_service: Optional[GoogleCalendarService] = None
        self.events: List[Dict] = []
        self.current_event_index = 0
        
        # Auto-refresh settings
        self.refresh_interval = int(os.getenv('CALENDAR_REFRESH_INTERVAL', '300'))  # 5 minutes default
        self.auto_refresh = True
        self.refresh_thread = None
        
        # UI state
        self.scroll_offset = 0
        self.max_visible_events = 5
        
        # Setup UI
        self._setup_ui()
        
        # Initialize calendar service in background
        self._initialize_calendar()
    
    def _setup_ui(self):
        """Setup the UI components"""
        self.grid_rowconfigure(0, weight=0)  # Header
        self.grid_rowconfigure(1, weight=1)  # Content
        self.grid_rowconfigure(2, weight=0)  # Footer
        self.grid_columnconfigure(0, weight=1)
        
        # Header
        self._create_header()
        
        # Event list container
        self._create_event_list()
        
        # Footer with navigation
        self._create_footer()
        
        # Loading message
        self.loading_label = tk.Label(
            self.event_container,
            text="Loading calendar...",
            bg=self.bg_color,
            fg=self.text_color,
            font=(self.font_path, 24) if os.path.exists(self.font_path) else ("Arial", 24)
        )
        self.loading_label.pack(expand=True)
    
    def _create_header(self):
        """Create the header section"""
        header_frame = tk.Frame(self, bg=self.bg_color, height=80)
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header_frame.grid_propagate(False)
        
        # Title
        title_font = (self.font_path, 36, "bold") if os.path.exists(self.font_path) else ("Arial", 36, "bold")
        self.title_label = tk.Label(
            header_frame,
            text="Calendar",
            bg=self.bg_color,
            fg=self.accent_color,
            font=title_font
        )
        self.title_label.pack(side=tk.LEFT)
        
        # Current date
        date_font = (self.font_path, 20) if os.path.exists(self.font_path) else ("Arial", 20)
        self.date_label = tk.Label(
            header_frame,
            text=datetime.now().strftime("%A, %B %d, %Y"),
            bg=self.bg_color,
            fg=self.text_color,
            font=date_font
        )
        self.date_label.pack(side=tk.RIGHT)
        
        # Update date every minute
        self._update_date()
    
    def _create_event_list(self):
        """Create the scrollable event list"""
        # Main container
        self.event_container = tk.Frame(self, bg=self.bg_color)
        self.event_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        
        # Canvas for scrolling
        self.canvas = tk.Canvas(
            self.event_container,
            bg=self.bg_color,
            highlightthickness=0
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = tk.Scrollbar(
            self.event_container,
            orient=tk.VERTICAL,
            command=self.canvas.yview,
            bg=self.bg_color,
            troughcolor=self.bg_color,
            activebackground=self.accent_color
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # Frame inside canvas for events
        self.events_frame = tk.Frame(self.canvas, bg=self.bg_color)
        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.events_frame,
            anchor="nw"
        )
        
        # Bind canvas resize
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        self.events_frame.bind('<Configure>', self._on_frame_configure)
    
    def _create_footer(self):
        """Create footer with controls"""
        footer_frame = tk.Frame(self, bg=self.bg_color, height=60)
        footer_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 20))
        footer_frame.grid_propagate(False)
        
        button_font = (self.font_path, 18) if os.path.exists(self.font_path) else ("Arial", 18)
        
        # Refresh button
        self.refresh_btn = tk.Button(
            footer_frame,
            text="⟳ Refresh",
            bg=self.accent_color,
            fg="#FFFFFF",
            font=button_font,
            bd=0,
            padx=20,
            pady=10,
            command=self.refresh_events,
            activebackground="#357AE8"
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Last update label
        self.update_label = tk.Label(
            footer_frame,
            text="",
            bg=self.bg_color,
            fg=self.text_color,
            font=(self.font_path, 14) if os.path.exists(self.font_path) else ("Arial", 14)
        )
        self.update_label.pack(side=tk.LEFT, padx=20)
        
        # Event count
        self.count_label = tk.Label(
            footer_frame,
            text="",
            bg=self.bg_color,
            fg=self.text_color,
            font=(self.font_path, 16) if os.path.exists(self.font_path) else ("Arial", 16)
        )
        self.count_label.pack(side=tk.RIGHT)
    
    def _on_canvas_configure(self, event):
        """Handle canvas resize"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_frame_configure(self, event):
        """Handle frame resize"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _initialize_calendar(self):
        """Initialize the Google Calendar service"""
        def init_thread():
            try:
                credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
                token_path = os.getenv('GOOGLE_TOKEN_PATH', 'token.pickle')
                
                self.calendar_service = GoogleCalendarService(credentials_path, token_path)
                
                # Load events
                self.after(0, self.refresh_events)
                
                # Start auto-refresh thread
                if self.auto_refresh:
                    self.after(0, self._start_auto_refresh)
                    
            except Exception as e:
                error_msg = f"Failed to initialize calendar: {str(e)}"
                print(error_msg)
                self.after(0, lambda: self._show_error(error_msg))
        
        thread = threading.Thread(target=init_thread, daemon=True)
        thread.start()
    
    def refresh_events(self):
        """Refresh calendar events from Google"""
        if not self.calendar_service:
            self._show_error("Calendar service not initialized")
            return
        
        def fetch_events():
            try:
                days_ahead = int(os.getenv('CALENDAR_DAYS_AHEAD', '7'))
                max_events = int(os.getenv('CALENDAR_MAX_EVENTS', '50'))
                
                # Fetch events
                events = self.calendar_service.get_upcoming_events(
                    max_results=max_events,
                    days_ahead=days_ahead
                )
                
                self.events = events
                self.after(0, self._display_events)
                
            except Exception as e:
                error_msg = f"Error fetching events: {str(e)}"
                print(error_msg)
                self.after(0, lambda: self._show_error(error_msg))
        
        thread = threading.Thread(target=fetch_events, daemon=True)
        thread.start()
        
        # Update refresh time
        self.update_label.config(text=f"Updated: {datetime.now().strftime('%I:%M %p')}")
    
    def _display_events(self):
        """Display events in the UI"""
        # Clear existing events
        for widget in self.events_frame.winfo_children():
            widget.destroy()
        
        # Remove loading message
        if self.loading_label:
            self.loading_label.pack_forget()
        
        # Update count
        self.count_label.config(text=f"{len(self.events)} event{'s' if len(self.events) != 1 else ''}")
        
        if not self.events:
            no_events_label = tk.Label(
                self.events_frame,
                text="No upcoming events",
                bg=self.bg_color,
                fg=self.text_color,
                font=(self.font_path, 24) if os.path.exists(self.font_path) else ("Arial", 24)
            )
            no_events_label.pack(pady=50)
            return
        
        # Group events by date
        events_by_date = {}
        for event in self.events:
            date_key = event['start_datetime'].date()
            if date_key not in events_by_date:
                events_by_date[date_key] = []
            events_by_date[date_key].append(event)
        
        # Display events grouped by date
        for date, day_events in sorted(events_by_date.items()):
            self._create_date_section(date, day_events)
    
    def _create_date_section(self, date, events):
        """Create a section for a specific date"""
        # Date header
        date_str = self._format_date_header(date)
        date_header = tk.Frame(self.events_frame, bg=self.bg_color)
        date_header.pack(fill=tk.X, pady=(15, 5))
        
        date_label = tk.Label(
            date_header,
            text=date_str,
            bg=self.bg_color,
            fg=self.accent_color,
            font=(self.font_path, 22, "bold") if os.path.exists(self.font_path) else ("Arial", 22, "bold"),
            anchor="w"
        )
        date_label.pack(side=tk.LEFT, padx=5)
        
        # Separator line
        separator = tk.Frame(date_header, bg=self.accent_color, height=2)
        separator.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        # Events for this date
        for event in events:
            self._create_event_card(event)
    
    def _create_event_card(self, event: Dict):
        """Create a card for a single event"""
        # Event card frame
        card = tk.Frame(
            self.events_frame,
            bg="#1A1A1A",
            bd=1,
            relief=tk.SOLID,
            highlightbackground=self.accent_color,
            highlightthickness=1
        )
        card.pack(fill=tk.X, pady=5, padx=10)
        
        # Time column
        time_frame = tk.Frame(card, bg="#1A1A1A", width=120)
        time_frame.pack(side=tk.LEFT, fill=tk.Y, padx=15, pady=10)
        time_frame.pack_propagate(False)
        
        time_font = (self.font_path, 20, "bold") if os.path.exists(self.font_path) else ("Arial", 20, "bold")
        time_label = tk.Label(
            time_frame,
            text=event['start_time'],
            bg="#1A1A1A",
            fg=self.accent_color,
            font=time_font,
            anchor="w"
        )
        time_label.pack(anchor="w")
        
        if event['end_time']:
            end_time_font = (self.font_path, 14) if os.path.exists(self.font_path) else ("Arial", 14)
            end_label = tk.Label(
                time_frame,
                text=event['end_time'],
                bg="#1A1A1A",
                fg=self.text_color,
                font=end_time_font,
                anchor="w"
            )
            end_label.pack(anchor="w")
        
        # Details column
        details_frame = tk.Frame(card, bg="#1A1A1A")
        details_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        # Event title
        title_font = (self.font_path, 20, "bold") if os.path.exists(self.font_path) else ("Arial", 20, "bold")
        title_label = tk.Label(
            details_frame,
            text=event['summary'],
            bg="#1A1A1A",
            fg=self.text_color,
            font=title_font,
            anchor="w",
            wraplength=500
        )
        title_label.pack(anchor="w")
        
        # Location
        if event.get('location'):
            location_font = (self.font_path, 16) if os.path.exists(self.font_path) else ("Arial", 16)
            location_label = tk.Label(
                details_frame,
                text=f"📍 {event['location']}",
                bg="#1A1A1A",
                fg="#888888",
                font=location_font,
                anchor="w",
                wraplength=500
            )
            location_label.pack(anchor="w", pady=(5, 0))
        
        # Time until event (if within 24 hours)
        if event['time_until'].total_seconds() > 0 and event['time_until'].days == 0:
            hours = int(event['time_until'].total_seconds() // 3600)
            minutes = int((event['time_until'].total_seconds() % 3600) // 60)
            
            if hours > 0:
                time_until_text = f"In {hours}h {minutes}m"
            else:
                time_until_text = f"In {minutes}m"
            
            time_until_font = (self.font_path, 14) if os.path.exists(self.font_path) else ("Arial", 14)
            time_until_label = tk.Label(
                details_frame,
                text=time_until_text,
                bg="#1A1A1A",
                fg=self.accent_color,
                font=time_until_font,
                anchor="w"
            )
            time_until_label.pack(anchor="w", pady=(5, 0))
    
    def _format_date_header(self, date) -> str:
        """Format date for section headers"""
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        if date == today:
            return "Today"
        elif date == tomorrow:
            return "Tomorrow"
        else:
            return date.strftime("%A, %B %d")
    
    def _update_date(self):
        """Update the current date display"""
        self.date_label.config(text=datetime.now().strftime("%A, %B %d, %Y"))
        self.after(60000, self._update_date)  # Update every minute
    
    def _start_auto_refresh(self):
        """Start automatic refresh of events"""
        def auto_refresh_loop():
            while self.auto_refresh:
                time.sleep(self.refresh_interval)
                if self.auto_refresh:
                    self.after(0, self.refresh_events)
        
        self.refresh_thread = threading.Thread(target=auto_refresh_loop, daemon=True)
        self.refresh_thread.start()
    
    def _show_error(self, message: str):
        """Display an error message"""
        # Clear existing content
        for widget in self.events_frame.winfo_children():
            widget.destroy()
        
        if self.loading_label:
            self.loading_label.pack_forget()
        
        error_label = tk.Label(
            self.events_frame,
            text=f"❌ {message}",
            bg=self.bg_color,
            fg="#FF4444",
            font=(self.font_path, 20) if os.path.exists(self.font_path) else ("Arial", 20),
            wraplength=600
        )
        error_label.pack(pady=50, padx=20)
        
        # Instructions
        if "credentials" in message.lower() or "not found" in message.lower():
            instructions = tk.Label(
                self.events_frame,
                text="Please set up Google Calendar API credentials:\n"
                     "1. Visit Google Cloud Console\n"
                     "2. Enable Calendar API\n"
                     "3. Create OAuth 2.0 credentials\n"
                     "4. Download as 'credentials.json'",
                bg=self.bg_color,
                fg=self.text_color,
                font=(self.font_path, 14) if os.path.exists(self.font_path) else ("Arial", 14),
                justify=tk.LEFT
            )
            instructions.pack(pady=20)
    
    def stop(self):
        """Stop auto-refresh and cleanup"""
        self.auto_refresh = False


# Standalone test
if __name__ == '__main__':
    root = tk.Tk()
    root.title("CompanionClock - Calendar")
    root.geometry("800x600")
    root.configure(bg="#000000")
    
    # Create calendar page
    calendar_page = CalendarPage(root)
    calendar_page.pack(fill=tk.BOTH, expand=True)
    
    root.mainloop()
