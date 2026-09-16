# -*- coding: utf-8 -*-
"""State helpers shared by MCP common modules."""
import json
from pathlib import Path

from .time import _now


def safe_project(project: str, allowed: str = "-_", default: str = "default") -> str:
    return "".join(c for c in project if c.isalnum() or c in allowed) or default


def safe_name(name: str, allowed: str = "-_.", default: str = "default",
              strip_chars: str = "") -> str:
    safe = "".join(c for c in name if c.isalnum() or c in allowed)
    if strip_chars:
        safe = safe.strip(strip_chars)
    return safe or default


def load_json_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_state(path: Path, state: dict, touch_updated: bool = True) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if touch_updated:
        state["updated"] = _now()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def append_event(container: dict, event_type: str, data: dict) -> None:
    container.setdefault("events", []).append({"ts": _now(), "type": event_type, **data})
