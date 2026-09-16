# -*- coding: utf-8 -*-
"""Pure helpers for owner-review CLI discovery and planning."""
import json
from pathlib import Path


def discover_scripts(root: Path, script_prefix: str) -> list[Path]:
    return sorted(path for path in root.glob(f"{script_prefix}*.py") if path.name != "agent_os_owner_review.py")


def command_name(path: Path, script_prefix: str) -> str:
    stem = path.stem
    if stem.startswith(script_prefix):
        stem = stem[len(script_prefix):]
    return stem.replace("_", "-")


def scripts_by_command(root: Path, script_prefix: str) -> dict[str, Path]:
    return {command_name(path, script_prefix): path for path in discover_scripts(root, script_prefix)}


def execution_target(root: Path, legacy_dir: Path, script: Path) -> Path:
    target = legacy_dir / script.name
    return target if target.exists() else script


def dry_run_payload(root: Path, script: Path, argv: list[str]) -> dict:
    return {
        "mode": "dry_run",
        "script": str(script.relative_to(root)),
        "argv": argv,
        "note": "Add --execute to run the compatibility script.",
    }


def list_payload(paths: list[Path], script_prefix: str) -> dict:
    rows = [{"command": command_name(path, script_prefix), "script": path.name} for path in paths]
    return {"count": len(rows), "items": rows}


def plan_payload(paths: list[Path], script_prefix: str) -> dict:
    groups: dict[str, int] = {}
    for path in paths:
        name = command_name(path, script_prefix)
        group = name.split("-", 2)[0] if "-" in name else name
        if name.startswith("review-"):
            group = "review"
        if name.startswith("decision-"):
            group = "decision"
        groups[group] = groups.get(group, 0) + 1
    return {
        "mode": "compatibility_preserving",
        "old_scripts_kept": True,
        "execute_requires": "--execute",
        "groups": groups,
        "recommended_next": [
            "Use this CLI as the visible owner-review entry.",
            "Keep old scripts until parity evidence exists.",
            "Later convert high-use old scripts into thin compatibility shims.",
        ],
    }
