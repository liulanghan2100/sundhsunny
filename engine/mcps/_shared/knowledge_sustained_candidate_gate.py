# -*- coding: utf-8 -*-
"""Pure helpers for the knowledge sustained-candidate gate."""
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


def gate_item(item: dict) -> dict:
    checks = {
        "review_recommended_sustained": item.get("recommendation") == "promote_to_sustained_candidate",
        "source_grade_not_missing": item.get("source_grade") != "missing",
        "path_exists": (item.get("checks") or {}).get("path_exists") is True,
        "trusted_promotion_blocked": True,
        "owner_gate_required_for_trusted": True,
    }
    failed = [key for key, value in checks.items() if not value]
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "type": item.get("type", ""),
        "source_grade": item.get("source_grade", ""),
        "risk_level": item.get("risk_level", ""),
        "status": "sustained_candidate_ready" if not failed else "sustained_candidate_blocked",
        "checks": checks,
        "failed_checks": failed,
        "owner_decision_options": ["approve_trusted", "reject", "defer_review"],
        "source_url": item.get("source_url", ""),
        "resolved_path": item.get("resolved_path", ""),
    }


def gate_payload(schema_version: str, packet_path: str, packet: dict) -> dict:
    candidates = [gate_item(item) for item in packet.get("items", []) if isinstance(item, dict)]
    ready = [item for item in candidates if item["status"] == "sustained_candidate_ready"]
    blocked = [item for item in candidates if item["status"] != "sustained_candidate_ready"]
    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "sustained_candidates_ready" if ready else "no_sustained_candidates_ready",
        "review_packet_path": packet_path,
        "candidate_count": len(candidates),
        "ready_count": len(ready),
        "blocked_count": len(blocked),
        "items": candidates,
        "ready_items": ready,
        "blocked_items": blocked,
        "read_only_knowledge_sustained_candidate_gate": True,
        "owner_approval_required": False,
        "no_status_mutation": True,
        "no_trusted_promotion": True,
        "no_knowledge_file_move": True,
        "no_knowledge_file_delete": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
