# -*- coding: utf-8 -*-
"""Pure helpers for non-binding model routing policy generation."""
import json
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def routing_rule(rec: dict, canary_item: dict) -> dict:
    adapter_id = rec.get("recommended_adapter", "")
    return {
        "capability": rec.get("capability", ""),
        "task_class": "any",
        "risk": "normal_or_lower",
        "recommended_adapter": adapter_id,
        "recommended_display_name": rec.get("recommended_display_name", adapter_id),
        "pass_rate": rec.get("pass_rate", 0),
        "evidence_score": rec.get("evidence_score", 0),
        "routing_status": "recommend_only",
        "canary_status": canary_item.get("canary_status", "unknown"),
        "requires_owner_approval": True,
        "auto_switch_allowed": False,
        "reason": rec.get("reason", ""),
    }


def policy_payload(schema_version: str, results: dict, canary: dict,
                   eval_results_path: str, canary_queue_path: str) -> dict:
    canary_index = {
        item.get("provider_id", ""): item
        for item in canary.get("items", [])
    } if isinstance(canary, dict) else {}
    rules = [
        routing_rule(rec, canary_index.get(rec.get("recommended_adapter", ""), {}))
        for rec in results.get("recommended_by_capability", [])
    ] if isinstance(results, dict) else []
    return {
        "schema_version": schema_version,
        "generated": now(),
        "recommend_only": True,
        "auto_switch_allowed": False,
        "owner_approval_required": True,
        "no_runtime_mutation": True,
        "rule_count": len(rules),
        "rules": rules,
        "results_path": eval_results_path,
        "canary_queue_path": canary_queue_path,
    }
