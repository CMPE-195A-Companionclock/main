from typing import Dict

def get_intent(text: str) -> Dict:
    """Very simple intent mapper used by the PC-side server."""
    t = (text or "").strip().lower()
    if not t:
        return {"intent": "none"}
    
    words = t.split()

    if any(w in words for w in ("weather", "forecast", "temperature", "rain", "sunny")):
        return {"intent": "goto", "view": "weather"}
    if any(w in words for w in ("calendar", "schedule", "appointments", "events", "month")):
        return {"intent": "goto", "view": "calendar"}
    if any(w in words for w in ("alarm", "wake", "wake-up", "wake-up", "wake-up", "timer")):
        return {"intent": "goto", "view": "alarm"}
    if any(w in words for w in ("clock", "time", "current", "now", "what's", "whats")):
        return {"intent": "goto", "view": "clock"}

    return {"intent": "none"}