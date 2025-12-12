from typing import Dict
import re


def _parse_alarm_request(text: str):
    t = text.lower()

    t = re.sub(r"\b(a\.m\.?|a\. m\.?)\b", "am", t)
    t = re.sub(r"\b(p\.m\.?|p\. m\.?)\b", "pm", t)
    
    word_to_digit = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
    }

    for w, d in word_to_digit.items():
        t = re.sub(rf"\b{w}\b", d, t)

    t = re.sub(r"\b(\d{1,2})\s+in the morning\b",   r"\1 am", t)
    t = re.sub(r"\b(\d{1,2})\s+in the afternoon\b", r"\1 pm", t)
    t = re.sub(r"\b(\d{1,2})\s+in the evening\b",   r"\1 pm", t)
    t = re.sub(r"\b(\d{1,2})\s+at night\b",         r"\1 pm", t)

    t = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", t)

    m = re.search(
        r"(?:set\s+(?:an\s+)?alarm(?:\s*(?:for|at|to))?"
        r"|wake\s+me(?:\s+up)?(?:\s*(?:for|at|to))?)"
        r"\s+(\d{1,2})"              # hour
        r"(?::(\d{2})|\s+(\d{1,2}))?" # :mm OR space mm (both optional)
        r"\s*(am|pm)?\b",            # optional am/pm
        t,
    )
    
    if not m:
        return None
    
    hour = int(m.group(1))
    minute_str = m.group(2) or m.group(3) or "0"
    minute = int(minute_str)
    meridiem = m.group(4)

    if hour > 23 or minute > 59:
        return None

    if meridiem:
        meridiem = meridiem.lower()
        if meridiem == "am":
            hour_24 = 0 if hour == 12 else hour
        else:  # pm
            hour_24 = hour if hour == 12 else hour + 12
        if hour_24 == 24:
            hour_24 = 0

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
    smart_off = re.search(r"\b(turn off|disable|stop)\b.*\b(commute|traffic).*update", text, re.I)
    smart_on  = re.search(r"\b(turn on|enable|start)\b.*\b(commute|traffic).*update", text, re.I)

    if smart_off:
        return {"intent": "toggle_commute_updates", "state": "off"}
    if smart_on:
        return {"intent": "toggle_commute_updates", "state": "on"}
    
    if re.search(r"\b(delete|remove|clear)\b.*\balarm(s)?\b", t):
        return {"intent": "delete_alarm"}
    
    if re.search(r"\b(turn off|disable|stop)\b.*\balarm(s)?\b", t):
        return {"intent": "disable_all_alarms"}
    if re.search(r"\b(turn on|enable)\b.*\balarm(s)?\b", t):
        return {"intent": "enable_all_alarms"}
    
    if any(w in words for w in ("weather", "forecast", "temperature", "rain", "sunny", "windy")):
        return {"intent": "goto", "view": "weather"}
    if any(w in words for w in ("calendar", "schedule", "appointments", "events", "month", "agenda")):
        return {"intent": "goto", "view": "calendar"}
    if any(w in words for w in ("alarm", "wake", "wake-up", "wakeup", "timer", "alarms")) and "set" not in words:
        return {"intent": "goto", "view": "alarm"}
    if any(w in words for w in ("clock", "time")):
        return {"intent": "goto", "view": "clock"}

    return {"intent": "none"}
