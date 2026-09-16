# -*- coding: utf-8 -*-
"""Pure helpers for promotion review gate bookkeeping."""
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


def research_dir(root):
    for path in sorted(root.glob("09_*")):
        if (path / "agent_os_shadow" / "promotion_scoring.json").exists():
            return path
    for path in sorted(root.glob("09_*")):
        if (path / "agent_os_runtime").exists():
            return path
    return root / "09_research"


def review_id(capability: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", capability).strip("-").lower()
    return f"promotion-review-{safe}"


def registry_lookup(registry_dir, capability: str) -> dict:
    for filename in ["skill_registry.json", "mcp_registry.json"]:
        path = registry_dir / filename
        payload = read_json(path, {})
        for index, item in enumerate(payload.get("items", []) if isinstance(payload, dict) else []):
            if item.get("name") == capability:
                return {"registry_file": filename, "registry_path": str(path), "index": index, "item": item}
    return {}


def decisions_by_capability(decisions_path) -> dict:
    payload = read_json(decisions_path, {"decisions": []})
    decisions = {}
    for decision in payload.get("decisions", []) if isinstance(payload, dict) else []:
        capability = decision.get("capability", "")
        if capability:
            decisions[capability] = decision
    return decisions


def promotion_candidate_scores(scoring: dict) -> list[dict]:
    score_items = scoring.get("scores", []) if isinstance(scoring, dict) else []
    return [
        score for score in score_items
        if score.get("promotion_recommendation") == "promote_to_active_candidate"
    ]


def eligible_capabilities(scoring: dict) -> set:
    return {
        score.get("capability")
        for score in promotion_candidate_scores(scoring)
    }


def queue_item(score: dict, registry: dict, decision: dict) -> dict:
    current_status = (registry.get("item") or {}).get("status", "unknown")
    status = "pending_owner_review"
    if decision.get("decision") == "approved":
        status = "approved_pending_apply" if current_status == "shadow" else "applied_or_not_shadow"
    elif decision.get("decision") == "rejected":
        status = "rejected"
    return {
        "review_id": review_id(score.get("capability", "")),
        "capability": score.get("capability", ""),
        "capability_type": (registry.get("item") or {}).get("type", score.get("type", "")),
        "current_status": current_status,
        "target_status": "active",
        "status": status,
        "approval_required": True,
        "owner_decision": decision.get("decision", ""),
        "owner": decision.get("owner", ""),
        "decision_reason": decision.get("reason", ""),
        "can_apply": decision.get("decision") == "approved" and current_status == "shadow",
        "registry_file": registry.get("registry_file", ""),
        "registry_path": registry.get("registry_path", ""),
        "scoring": {
            "shadow_run_count": score.get("shadow_run_count", 0),
            "agreement_rate": score.get("agreement_rate", 0),
            "warn_rate": score.get("warn_rate", 0),
            "false_positive_rate": score.get("false_positive_rate", 0),
            "evidence_completeness": score.get("evidence_completeness", 0),
            "takeover_count": score.get("takeover_count", 0),
            "promotion_reason": score.get("promotion_reason", ""),
            "latest_path": score.get("latest_path", ""),
        },
    }


def queue_payload(scoring: dict, decisions: dict, registry_lookup_fn, source_scoring: str) -> dict:
    items = []
    for score in promotion_candidate_scores(scoring):
        capability = score.get("capability", "")
        registry = registry_lookup_fn(capability)
        decision = decisions.get(capability, {})
        items.append(queue_item(score, registry, decision))
    return {
        "schema_version": "promotion-review-gate/v0.3",
        "generated": now(),
        "source_scoring": source_scoring,
        "pending_count": sum(1 for item in items if item["status"] == "pending_owner_review"),
        "approved_pending_apply_count": sum(1 for item in items if item["status"] == "approved_pending_apply"),
        "rejected_count": sum(1 for item in items if item["status"] == "rejected"),
        "no_auto_promotion_guard": True,
        "items": items,
    }


def decision_record(capability: str, decision: str, owner: str, reason: str) -> dict:
    return {
        "capability": capability,
        "decision": decision,
        "owner": owner,
        "reason": reason,
        "decided_at": now(),
    }
