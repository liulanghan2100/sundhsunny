# -*- coding: utf-8 -*-
"""Pure helpers for active capability rollback review gates."""
import json
import re
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def review_id(capability: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", capability).strip("-").lower()
    return f"rollback-review-{safe}"


def decisions_by_capability(payload: dict) -> dict:
    decisions = {}
    items = payload.get("decisions", []) if isinstance(payload, dict) else []
    for decision in items:
        if decision.get("capability"):
            decisions[decision["capability"]] = decision
    return decisions


def registry_lookup(registry_dir, capability: str) -> dict:
    for filename in ["skill_registry.json", "mcp_registry.json"]:
        path = registry_dir / filename
        payload = read_json(path, {})
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for index, item in enumerate(items):
            if item.get("name") == capability:
                return {"registry_file": filename, "registry_path": str(path), "index": index, "item": item}
    return {}


def queue_item(candidate: dict, registry: dict, decision: dict) -> dict:
    capability = candidate.get("capability", "")
    current_status = (registry.get("item") or {}).get("status", "unknown")
    status = "pending_owner_review"
    if decision.get("decision") == "approved":
        status = "approved_pending_apply" if current_status == "active" else "applied_or_not_active"
    elif decision.get("decision") == "rejected":
        status = "rejected"
    return {
        "review_id": review_id(capability),
        "capability": capability,
        "current_status": current_status,
        "target_status": "shadow",
        "status": status,
        "approval_required": True,
        "owner_decision": decision.get("decision", ""),
        "owner": decision.get("owner", ""),
        "decision_reason": decision.get("reason", ""),
        "can_apply": decision.get("decision") == "approved" and current_status == "active",
        "registry_file": registry.get("registry_file", ""),
        "registry_path": registry.get("registry_path", ""),
        "rollback_reason": candidate.get("rollback_reason", ""),
        "canary": {
            "active_run_count": candidate.get("active_run_count", 0),
            "active_success_rate": candidate.get("active_success_rate", 0),
            "active_failure_count": candidate.get("active_failure_count", 0),
            "verifier_failure_count": candidate.get("verifier_failure_count", 0),
        },
    }


def queue_payload(candidates: dict, decisions: dict, registry_lookup_fn, source_candidates: str) -> dict:
    items = []
    candidate_items = candidates.get("items", []) if isinstance(candidates, dict) else []
    for candidate in candidate_items:
        capability = candidate.get("capability", "")
        items.append(queue_item(candidate, registry_lookup_fn(capability), decisions.get(capability, {})))
    return {
        "schema_version": "rollback-review-gate/v0.5",
        "generated": now(),
        "source_candidates": source_candidates,
        "pending_count": sum(1 for item in items if item["status"] == "pending_owner_review"),
        "approved_pending_apply_count": sum(1 for item in items if item["status"] == "approved_pending_apply"),
        "rejected_count": sum(1 for item in items if item["status"] == "rejected"),
        "no_auto_rollback_guard": True,
        "items": items,
    }


def decision_record(capability: str, decision: str, owner: str, reason: str) -> dict:
    return {"capability": capability, "decision": decision, "owner": owner, "reason": reason, "decided_at": now()}
