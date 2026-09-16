# -*- coding: utf-8 -*-
"""Pure helpers for the knowledge trusted owner-review queue."""
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


def queue_item(item: dict, decision_file_path: str) -> dict:
    return {
        "queue_id": "knowledge_trusted_promotion",
        "item_id": f"knowledge-trusted-review-{item.get('id', '')}",
        "knowledge_id": item.get("id", ""),
        "title": item.get("title", ""),
        "type": item.get("type", ""),
        "status": "pending_owner_review",
        "risk_level": item.get("risk_level", ""),
        "source_grade": item.get("source_grade", ""),
        "owner_action": "Approve, reject, or defer trusted knowledge promotion.",
        "recommended_decision_options": ["approve_trusted", "reject", "defer_review"],
        "decision_file_required_for_actual_apply": decision_file_path,
        "forbidden_auto_actions": [
            "trusted_promotion",
            "meta_status_mutation",
            "knowledge_file_move",
            "knowledge_file_delete",
            "skill_writeback",
            "runtime_standard_writeback",
        ],
        "source_url": item.get("source_url", ""),
        "resolved_path": item.get("resolved_path", ""),
    }


def queue_payload(schema_version: str, gate_path: str, decision_file_path: str, gate: dict) -> dict:
    ready_items = [item for item in gate.get("ready_items", []) if isinstance(item, dict)]
    items = [queue_item(item, decision_file_path) for item in ready_items]
    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "owner_review_required" if items else "no_owner_review_items",
        "sustained_gate_path": gate_path,
        "decision_file_path": decision_file_path,
        "pending_count": len(items),
        "items": items,
        "read_only_knowledge_trusted_owner_review_queue": True,
        "owner_approval_required": True,
        "no_decision_file_written": True,
        "no_status_mutation": True,
        "no_trusted_promotion": True,
        "no_knowledge_file_move": True,
        "no_knowledge_file_delete": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
