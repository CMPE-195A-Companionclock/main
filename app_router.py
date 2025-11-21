import importlib
import logging
from typing import Callable, Iterable, Optional
import json, os, tempfile

VOICE_CMD_PATH = os.getenv("VOICE_CMD_PATH", os.path.join(tempfile.gettempdir(), "cc_voice_cmd.json"))
log = logging.getLogger("app_router")

def _resolve(module_name: str, candidates: Iterable[str]) -> Optional[Callable]:
    try:
        mod = importlib.import_module(module_name)
    except Exception as e:
        log.warning("Router: module '%s' not found (%s)", module_name, e)
        return None
    for name in candidates:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    log.warning("Router: none of %s found in module '%s'", list(candidates), module_name)
    return None

VIEW_MAP = {
    "clock":    ("clock",        ["show", "show_clock", "render", "main"]),
    "weather":  ("weather",      ["show", "show_weather", "render", "main"]),
    "calendar": ("calendarPage", ["show", "show_calendar", "render", "main"]),
    "alarm":    ("Alarm",        ["show", "open_alarm_ui", "render", "main"]),
}

def _write(payload: dict):
    os.makedirs(os.path.dirname(VOICE_CMD_PATH), exist_ok=True)
    tmp = VOICE_CMD_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, VOICE_CMD_PATH)

def goto_view(view: str, text: str = ""):
    _write({"cmd": "goto", "view": view, "text": text})

def schedule_alarm(hhmm: str, goto_after: Optional[str] = "alarm"):
    _write({"cmd": "set_alarm", "time": hhmm, "goto": goto_after})
