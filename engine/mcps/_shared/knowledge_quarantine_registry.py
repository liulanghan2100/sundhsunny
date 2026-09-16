# -*- coding: utf-8 -*-
"""Pure helpers for knowledge quarantine registry generation."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_meta(meta_path) -> list[dict]:
    if not meta_path.exists():
        return []
    rows = []
    for line in meta_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def find_kb_root(root):
    candidates = [
        path for path in root.iterdir()
        if path.is_dir() and path.name.startswith("10_") and (path / "meta.jsonl").exists()
    ]
    return candidates[0] if candidates else root / "10_knowledge_base"


def find_research_root(root):
    candidates = [
        path for path in root.iterdir()
        if path.is_dir()
        and path.name.startswith("09_")
        and (path / "dashboard").exists()
        and (path / "agent_os_owner_decisions").exists()
    ]
    if candidates:
        return candidates[0]
    candidates = [
        path for path in root.iterdir()
        if path.is_dir() and path.name.startswith("09_") and (path / "dashboard").exists()
    ]
    return candidates[0] if candidates else root / "09_research"


def resolve_entry_path(root, kb_root, item: dict) -> str:
    raw = str(item.get("path") or "")
    candidates = []
    if raw:
        path = Path(raw)
        candidates.append(path if path.is_absolute() else root / path)
        candidates.append(kb_root / Path(raw).name)
    item_id = str(item.get("id") or "")
    if item_id and kb_root.exists():
        candidates.extend(kb_root.rglob(f"*{item_id}*"))
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def compact_item(root, kb_root, item: dict) -> dict:
    status = str(item.get("status") or "missing")
    resolved = resolve_entry_path(root, kb_root, item)
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "type": item.get("type", "unknown"),
        "status": status,
        "trust_level": item.get("trust_level", ""),
        "source_url": item.get("source_url", ""),
        "source_path": item.get("source_path", ""),
        "raw_path": item.get("path", ""),
        "resolved_path": resolved,
        "path_exists": bool(resolved),
        "reviewed_at": item.get("reviewed_at", ""),
        "tags": item.get("tags", []),
        "summary": item.get("summary", ""),
        "review_required": status == "quarantine",
        "trusted_allowed": False,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict, ts: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = ts or now()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": stamp, **payload}, ensure_ascii=True) + "\n")


def registry_payload(root, kb_root, meta_path, schema_version: str) -> dict:
    items = [compact_item(root, kb_root, item) for item in read_meta(meta_path)]
    status_counts = Counter(item["status"] for item in items)
    type_counts = Counter(str(item.get("type") or "unknown") for item in items)
    quarantine_items = [item for item in items if item["status"] == "quarantine"]
    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "quarantine_registry_ready",
        "kb_root": str(kb_root),
        "meta_path": str(meta_path),
        "item_count": len(items),
        "quarantine_count": len(quarantine_items),
        "trusted_count": status_counts.get("trusted", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "type_counts": dict(sorted(type_counts.items())),
        "items": items,
        "quarantine_items": quarantine_items,
        "read_only_knowledge_quarantine_registry": True,
        "owner_approval_required": False,
        "no_status_mutation": True,
        "no_trusted_promotion": True,
        "no_knowledge_file_move": True,
        "no_knowledge_file_delete": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
