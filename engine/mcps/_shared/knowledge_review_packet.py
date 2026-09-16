# -*- coding: utf-8 -*-
"""Pure helpers for knowledge review packet generation."""
import json
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def write_json(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def append_jsonl(path, payload: dict, ts: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = ts or now()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": stamp, **payload}, ensure_ascii=True) + "\n")


def source_grade(item: dict) -> str:
    url = str(item.get("source_url") or "")
    if url.startswith("https://github.com/") or "claymath.org" in url:
        return "high"
    if url.startswith("https://"):
        return "medium"
    if url.startswith("local://"):
        return "local_unverified"
    return "missing"


def review_item(item: dict) -> dict:
    grade = source_grade(item)
    checks = {
        "is_quarantine": item.get("status") == "quarantine",
        "source_present": bool(item.get("source_url") or item.get("source_path")),
        "path_exists": item.get("path_exists") is True,
        "not_already_trusted": item.get("status") != "trusted",
        "owner_gate_required": True,
    }
    failed = [key for key, value in checks.items() if not value]
    recommendation = "promote_to_sustained_candidate" if not failed and grade in {"high", "medium", "local_unverified"} else "defer_review"
    risk_level = "medium" if grade == "local_unverified" else ("low" if grade in {"high", "medium"} else "high")
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "type": item.get("type", ""),
        "source_grade": grade,
        "risk_level": risk_level,
        "checks": checks,
        "failed_checks": failed,
        "recommendation": recommendation,
        "review_summary": item.get("summary", ""),
        "source_url": item.get("source_url", ""),
        "resolved_path": item.get("resolved_path", ""),
        "allowed_next_options": ["promote_to_sustained_candidate", "reject", "defer_review"],
        "forbidden_auto_actions": ["trusted_promotion", "knowledge_file_move", "knowledge_file_delete", "skill_writeback", "runtime_standard_writeback"],
    }


def packet_payload(schema_version: str, registry_path: str, registry: dict) -> dict:
    items = [review_item(item) for item in registry.get("quarantine_items", []) if isinstance(item, dict)]
    ready = [item for item in items if item["recommendation"] == "promote_to_sustained_candidate"]
    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "knowledge_review_packet_ready",
        "registry_path": registry_path,
        "review_item_count": len(items),
        "sustained_candidate_recommendation_count": len(ready),
        "items": items,
        "read_only_knowledge_review_packet": True,
        "owner_approval_required": False,
        "no_status_mutation": True,
        "no_trusted_promotion": True,
        "no_knowledge_file_move": True,
        "no_knowledge_file_delete": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
