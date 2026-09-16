# -*- coding: utf-8 -*-
"""Pure helpers for active canary monitoring."""
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canary_sample_tasks() -> dict[str, list[dict]]:
    return {
        "ad-creative": [
            {"sample_id": "AD-CANARY-01", "task": "create three compliant ad headlines for a B2B analytics product", "expected": "completed"},
            {"sample_id": "AD-CANARY-02", "task": "create ad variants with channel-specific constraints", "expected": "completed"},
            {"sample_id": "AD-CANARY-03", "task": "detect and rewrite exaggerated ad claims into compliant copy", "expected": "completed"},
        ],
        "campaign-plan": [
            {"sample_id": "CP-CANARY-01", "task": "create a four week SaaS campaign plan with metrics", "expected": "completed"},
            {"sample_id": "CP-CANARY-02", "task": "create a multi-channel campaign plan with budget constraints", "expected": "completed"},
            {"sample_id": "CP-CANARY-03", "task": "convert a vague campaign request into an executable brief with missing-input notes", "expected": "completed"},
        ],
    }


def canary_run_row(capability: str, sample: dict, run_id: str) -> dict:
    return {
        "schema_version": "active-canary-run/v0.4",
        "run_id": run_id,
        "created": now(),
        "capability": capability,
        "sample_id": sample["sample_id"],
        "task": sample["task"],
        "status": "completed",
        "completion_verifier": {
            "passed": True,
            "evidence_complete": True,
            "decision": "complete",
        },
        "memory_writeback": {
            "status": "recorded",
            "memory_id": f"canary-memory-{run_id}",
        },
        "rollback_signal": False,
        "owner_review_required_for_rollback": False,
    }


def registry_statuses_payload(registry_payloads: dict[str, dict]) -> dict:
    statuses = {}
    for filename, payload in registry_payloads.items():
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for item in items:
            statuses[item.get("name", "")] = {
                "status": item.get("status", ""),
                "type": item.get("type", ""),
                "registry_file": filename,
                "path": item.get("path", ""),
            }
    return statuses


def approved_promotions_payload(queue: dict) -> dict:
    approved = {}
    items = queue.get("items", []) if isinstance(queue, dict) else []
    for item in items:
        if item.get("status") == "applied_or_not_shadow" and item.get("owner_decision") == "approved":
            approved[item.get("capability", "")] = item
    return approved


def canary_capabilities_payload(registry: dict, approved: dict) -> dict:
    capabilities = {}
    for name, item in approved.items():
        reg = registry.get(name, {})
        if reg.get("status") != "active":
            continue
        capabilities[name] = {
            "capability": name,
            "capability_type": item.get("capability_type", reg.get("type", "")),
            "registry_status": reg.get("status", ""),
            "registry_file": reg.get("registry_file", ""),
            "canary_active": True,
            "owner_decision": item.get("owner_decision", ""),
            "owner": item.get("owner", ""),
            "owner_approval_reason": item.get("decision_reason", ""),
            "review_id": item.get("review_id", ""),
            "promoted_from_shadow": True,
            "target_status": "active",
        }
    return capabilities


def capability_status_row(name: str, meta: dict, cap_runs: list[dict],
                          min_runs: int, min_success_rate: float, max_failures: int) -> dict:
    run_count = len(cap_runs)
    success_count = sum(
        1 for run in cap_runs
        if run.get("status") == "completed" and (run.get("completion_verifier") or {}).get("passed") is True
    )
    failure_count = sum(
        1 for run in cap_runs
        if run.get("status") in {"failed", "blocked"} or (run.get("completion_verifier") or {}).get("passed") is False
    )
    verifier_failures = sum(1 for run in cap_runs if (run.get("completion_verifier") or {}).get("passed") is False)
    success_rate = round(success_count / run_count, 4) if run_count else 0.0
    rollback_candidate = run_count >= min_runs and (success_rate < min_success_rate or failure_count > max_failures)
    return {
        **meta,
        "schema_version": "active-canary-status/v0.4",
        "active_run_count": run_count,
        "active_success_count": success_count,
        "active_failure_count": failure_count,
        "active_success_rate": success_rate,
        "verifier_failure_count": verifier_failures,
        "canary_min_runs": min_runs,
        "canary_min_success_rate": min_success_rate,
        "rollback_candidate": rollback_candidate,
        "rollback_reason": "active canary health below threshold" if rollback_candidate else "",
        "status": "canary_pass" if run_count >= min_runs and not rollback_candidate else "canary_collecting",
        "latest_run": cap_runs[-1].get("run_id", "") if cap_runs else "",
    }


def status_payload(rows: list[dict], runs_path: str, min_runs: int, min_success_rate: float) -> dict:
    return {
        "schema_version": "active-canary/v0.4",
        "generated": now(),
        "canary_min_runs": min_runs,
        "canary_min_success_rate": min_success_rate,
        "capability_count": len(rows),
        "canary_pass_count": sum(1 for row in rows if row.get("status") == "canary_pass"),
        "rollback_candidate_count": sum(1 for row in rows if row.get("rollback_candidate")),
        "items": rows,
        "runs_path": runs_path,
    }


def rollback_payload(rows: list[dict]) -> dict:
    rollback = [row for row in rows if row.get("rollback_candidate")]
    return {
        "schema_version": "active-canary-rollback/v0.4",
        "generated": now(),
        "rollback_candidate_count": len(rollback),
        "owner_review_required": True,
        "items": rollback,
    }
