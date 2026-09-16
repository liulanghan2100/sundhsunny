# -*- coding: utf-8 -*-
"""Pure JSON and file IO helpers shared by MCP common modules."""
import json
from pathlib import Path
from typing import Any


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, data: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _append_jsonl(path: Path, record: dict, sort_keys: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=sort_keys) + "\n")
    return str(path)
