"""
Google Calendar Integration for CompanionClock
Handles authentication, event retrieval, and data formatting
"""

import os
import pickle
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the token.pickle file
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

class GoogleCalendarService:
    """
    Service class for Google Calendar API integration
    """
    
    def __init__(self, credentials_path: str = 'credentials.json', 
                 token_path: str = 'token.pickle'):
        """
        Initialize the Google Calendar service
        
        Args:
            credentials_path: Path to the OAuth2 credentials JSON file
            token_path: Path to store the authentication token
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """
        Authenticate with Google Calendar API using OAuth2
        """
        creds = None
        
        # Load existing credentials from token file
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Error refreshing credentials: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Credentials file not found: {self.credentials_path}\n"
                        "Please download your OAuth2 credentials from Google Cloud Console"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for future use
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        # Build the service
        self.service = build('calendar', 'v3', credentials=creds)
    
    def get_upcoming_events(self, max_results: int = 10, 
                          days_ahead: int = 7,
                          calendar_id: str = 'primary') -> List[Dict]:
        """
        Retrieve upcoming calendar events
        
        Args:
            max_results: Maximum number of events to return
            days_ahead: Number of days to look ahead
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            List of event dictionaries with formatted information
        """
        try:
            # Get current time and end time
            now = datetime.utcnow()
            end_time = now + timedelta(days=days_ahead)
            
            # Format times in RFC3339 format
            time_min = now.isoformat() + 'Z'
            time_max = end_time.isoformat() + 'Z'
            
            # Call the Calendar API
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Format events for display
            formatted_events = []
            for event in events:
                formatted_event = self._format_event(event)
                formatted_events.append(formatted_event)
            
            return formatted_events
            
        except HttpError as error:
            print(f'An error occurred: {error}')
            return []
    
    def get_todays_events(self, calendar_id: str = 'primary') -> List[Dict]:
        """
        Get all events for today
        
        Args:
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            List of today's events
        """
        try:
            # Get start and end of today
            now = datetime.now()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Convert to UTC
            time_min = start_of_day.isoformat() + 'Z'
            time_max = end_of_day.isoformat() + 'Z'
            
            # Call the Calendar API
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Format events
            formatted_events = []
            for event in events:
                formatted_event = self._format_event(event)
                formatted_events.append(formatted_event)
            
            return formatted_events
            
        except HttpError as error:
            print(f'An error occurred: {error}')
            return []
    
    def _format_event(self, event: Dict) -> Dict:
        """
        Format a calendar event for display
        
        Args:
            event: Raw event data from Google Calendar API
        
        Returns:
            Formatted event dictionary
        """
        # Get event start time
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        
        # Parse datetime
        is_all_day = 'date' in event['start']
        
        if is_all_day:
            # All-day event
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            start_time_str = "All Day"
            end_time_str = ""
        else:
            # Timed event
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            
            # Format times (12-hour format)
            start_time_str = start_dt.strftime('%I:%M %p')
            end_time_str = end_dt.strftime('%I:%M %p')
        
        # Get event details
        summary = event.get('summary', 'No Title')
        location = event.get('location', '')
        description = event.get('description', '')
        
        # Format date string
        date_str = start_dt.strftime('%A, %B %d')
        
        # Calculate time until event
        now = datetime.now(start_dt.tzinfo) if not is_all_day else datetime.now()
        time_until = start_dt - now
        
        return {
            'id': event['id'],
            'summary': summary,
            'location': location,
            'description': description,
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'start_time': start_time_str,
            'end_time': end_time_str,
            'date': date_str,
            'is_all_day': is_all_day,
            'time_until': time_until,
            'raw_event': event
        }
    
    def get_next_event(self, calendar_id: str = 'primary') -> Optional[Dict]:
        """
        Get the next upcoming event
        
        Args:
            calendar_id: Calendar ID (default: 'primary')
        
        Returns:
            Next event or None if no upcoming events
        """
        events = self.get_upcoming_events(max_results=1, calendar_id=calendar_id)
        return events[0] if events else None
    
    def list_calendars(self) -> List[Dict]:
        """
        List all available calendars
        
        Returns:
            List of calendar dictionaries
        """
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            
            formatted_calendars = []
            for calendar in calendars:
                formatted_calendars.append({
                    'id': calendar['id'],
                    'summary': calendar.get('summary', ''),
                    'description': calendar.get('description', ''),
                    'primary': calendar.get('primary', False),
                    'color': calendar.get('backgroundColor', '#000000')
                })
            
            return formatted_calendars
            
        except HttpError as error:
            print(f'An error occurred: {error}')
            return []


# Utility functions for easy access
def get_calendar_service(credentials_path: Optional[str] = None,
                        token_path: Optional[str] = None) -> GoogleCalendarService:
    """
    Factory function to create a GoogleCalendarService instance
    
    Args:
        credentials_path: Path to OAuth2 credentials (defaults to env var or 'credentials.json')
        token_path: Path to token file (defaults to env var or 'token.pickle')
    
    Returns:
        GoogleCalendarService instance
    """
    base_dir = Path(__file__).resolve().parent

    if credentials_path is None:
        env_path = os.getenv('GOOGLE_CREDENTIALS_PATH')
        if env_path:
            credentials_path = env_path
        else:
            credentials_path = str(base_dir / "credentials.json")

    if token_path is None:
        env_token = os.getenv('GOOGLE_TOKEN_PATH')
        if env_token:
            token_path = env_token
        else:
            token_path = str(base_dir / "token.pickle")

    return GoogleCalendarService(credentials_path, token_path)

if __name__ == '__main__':
    # Test the calendar service
    print("Testing Google Calendar Service...")
    
    try:
        service = get_calendar_service()
        
        print("\n=== Available Calendars ===")
        calendars = service.list_calendars()
        for cal in calendars:
            primary = " (PRIMARY)" if cal['primary'] else ""
            print(f"- {cal['summary']}{primary}")
        
        print("\n=== Today's Events ===")
        today_events = service.get_todays_events()
        if today_events:
            for event in today_events:
                print(f"{event['start_time']} - {event['summary']}")
                if event['location']:
                    print(f"  Location: {event['location']}")
        else:
            print("No events today")
        
        print("\n=== Upcoming Events (Next 7 Days) ===")
        upcoming = service.get_upcoming_events(max_results=10)
        if upcoming:
            for event in upcoming:
                print(f"{event['date']}")
                print(f"  {event['start_time']} - {event['summary']}")
                if event['location']:
                    print(f"  Location: {event['location']}")
        else:
            print("No upcoming events")
            
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nPlease follow these steps:")
        print("1. Go to Google Cloud Console (https://console.cloud.google.com)")
        print("2. Create a new project or select existing one")
        print("3. Enable Google Calendar API")
        print("4. Create OAuth 2.0 credentials (Desktop app)")
        print("5. Download the credentials JSON file as 'credentials.json'")
    except Exception as e:
        print(f"Error: {e}")
