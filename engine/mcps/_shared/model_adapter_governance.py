# -*- coding: utf-8 -*-
"""Pure command discovery and dry-run payload helpers."""
import json
from pathlib import Path


def discover_scripts(root: Path, prefix: str, current_file: Path) -> list[Path]:
    return sorted(
        path for path in root.glob(f"{prefix}*.py")
        if path.name != current_file.name
    )


def command_name(path: Path, prefix: str) -> str:
    stem = path.stem
    if stem.startswith(prefix):
        stem = stem[len(prefix):]
    return stem.replace("_", "-")


def scripts_by_command(root: Path, prefix: str, current_file: Path) -> dict[str, Path]:
    return {
        command_name(path, prefix): path
        for path in discover_scripts(root, prefix, current_file)
    }


def list_payload(root: Path, prefix: str, current_file: Path) -> dict:
    rows = [
        {"command": command_name(path, prefix), "script": path.name}
        for path in discover_scripts(root, prefix, current_file)
    ]
    return {"count": len(rows), "items": rows}


def plan_payload() -> dict:
    return {
        "mode": "governance_only",
        "provider_activation": "blocked_without_owner_gate",
        "real_api_calls": "blocked_without_owner_gate",
        "old_scripts_kept": True,
        "execute_requires": "--execute",
        "safe_order": [
            "harness",
            "eval",
            "contract-tests",
            "guardrail-negative-tests",
            "decision-gate",
            "daily-soak",
        ],
    }


def render_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
