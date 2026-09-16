# -*- coding: utf-8 -*-
"""Pure helpers for Agent OS registry construction."""
import json
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def normalize_skill_status(raw: str, name: str, active_skills: set[str]) -> str:
    if name in active_skills:
        return "active"
    if raw in {"active", "shadow", "deprecated", "retired"}:
        return raw
    if raw == "candidate":
        return "shadow"
    if raw == "quarantine":
        return "deprecated"
    return "shadow"


def mcp_status(name: str, active_mcps: set[str]) -> str:
    if name in active_mcps:
        return "active"
    if name in {"manual_mcp"}:
        return "deprecated"
    if name.startswith("__") or name.endswith("_selftest"):
        return "retired"
    return "shadow"


def skill_description(skill_path) -> str:
    skill_file = skill_path / "SKILL.md"
    if not skill_file.exists():
        return ""
    text = skill_file.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def mcp_registry_item(path, root, mcp_dir, status: str) -> dict:
    files = sorted(path.glob("*.py"))
    runner = [item.name for item in files if item.name.startswith("run_")]
    smoke_test = mcp_dir / f"smoke_test_{path.name}.py"
    return {
        "name": path.name,
        "type": "mcp",
        "status": status,
        "risk": "normal" if status == "active" else "needs-review",
        "path": str(path.relative_to(root)),
        "has_readme": (path / "README.md").exists(),
        "runner": runner,
        "smoke_test": str(smoke_test.relative_to(root)) if smoke_test.exists() else "",
        "last_verified": "",
        "replacement": "04_?????/skills-shared-candidate/manual-gates" if path.name == "manual_mcp" else "",
        "notes": "core runtime path" if status == "active" else "kept out of primary runtime until promoted",
    }


def skill_registry_item(path, root, status_data: dict, status: str, description: str) -> dict:
    name = path.name
    raw = (status_data.get(name) or {}).get("status", "candidate")
    risk = (status_data.get(name) or {}).get("risk", "normal")
    return {
        "name": name,
        "type": "skill",
        "status": status,
        "risk": risk if status != "active" else "normal",
        "path": str(path.relative_to(root)),
        "description": description,
        "last_verified": "",
        "replacement": "",
        "notes": f"source_status={raw}",
    }


def dedupe_items_by_name(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        key = item["name"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def lifecycle_policy_text() -> str:
    return """# Agent OS Lifecycle Policy v0.1

Statuses:

- `active`: allowed in the primary runtime path.
- `shadow`: can be observed or used manually, but cannot take over primary flow.
- `deprecated`: compatibility only; new work should use replacement or stay out of primary flow.
- `retired`: disabled or ignored by runtime.

Promotion rule:

`shadow -> active` requires a smoke test, at least one successful RunState-backed task, and no failing eval regression.

Demotion rule:

Any active capability with repeated failed/blocked RunStates should move to `shadow` until fixed.
"""


def registry_payload(items: list[dict]) -> dict:
    return {"generated": now(), "schema_version": "agent-os-registry/v0.1", "items": items}
