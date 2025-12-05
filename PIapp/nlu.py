from typing import Dict

def get_intent(text: str) -> Dict:
    """Very simple intent mapper used by the PC-side server."""
    t = (text or "").strip().lower()
    if not t:
        return {"intent": "none"}

    if "weather" in t:
        return {"intent": "goto", "view": "weather"}
    if "calendar" in t:
        return {"intent": "goto", "view": "calendar"}
    if "alarm" in t:
        return {"intent": "goto", "view": "alarm"}
    if "clock" in t:
        return {"intent": "goto", "view": "clock"}

    return {"intent": "none"}