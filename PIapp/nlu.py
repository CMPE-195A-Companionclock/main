from typing import Dict
import re

def _parse_alarm_request(text: str):
    t = text.lower()
    m = re.search(
        r"(?:set\s+(?:an\s+)?alarm(?:\s*(?:for|at))?|wake\s+me(?:\s+up)?(?:\s*(?:for|at))?)"
        r"\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
        t,
    )
    if not m:
        return None
    
    hour = int(m.group(1))
    minute = int(m.group(2) or "0")
    meridiem = m.group(3)

    if hour > 23 or minute > 59:
        return None

    if meridiem:
        meridiem = meridiem.lower()
        if meridiem == "am":
            hour_24 = 0 if hour == 12 else hour
        else:  # "pm"
            hour_24 = 12 if hour == 12 else hour + 12

        return {
            "intent": "set_alarm",
            "alarm_time": f"{hour_24:02d}:{minute:02d}",
            "hour": hour_24,
            "minute": minute,
        }
    
    if hour > 12:
        hour_24 = 0 if hour == 24 else hour
        return {
            "intent": "set_alarm",
            "alarm_time": f"{hour_24:02d}:{minute:02d}",
            "hour": hour_24,
            "minute": minute,
        }

    return {
        "intent": "set_alarm",
        "alarm_time": None,
        "hour": hour,
        "minute": minute,
        "missing": ["meridiem"],
    }

def get_intent(text: str) -> Dict:
    """Very simple intent mapper used by the PC-side server."""
    if not text:
        return {"intent": "none"}
    
    raw = text
    t = text.lower()
    words = t.split()

    alarm = _parse_alarm_request(raw)
    if alarm:
        return alarm
    
    words = t.split()

    if any(w in words for w in ("weather", "forecast", "temperature", "rain", "sunny", "windy")):
        return {"intent": "goto", "view": "weather"}
    if any(w in words for w in ("calendar", "schedule", "appointments", "events", "month", "agenda")):
        return {"intent": "goto", "view": "calendar"}
    if any(w in words for w in ("alarm", "wake", "wake-up", "wakeup", "timer", "alarms")) and "set" not in words:
        return {"intent": "goto", "view": "alarm"}
    if any(w in words for w in ("clock", "time")):
        return {"intent": "goto", "view": "clock"}

    return {"intent": "none"}