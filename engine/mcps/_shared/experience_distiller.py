# -*- coding: utf-8 -*-
"""Pure helpers for Replay Diff experience distillation."""
import re
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value)).strip("-").lower()
    return safe or "_empty"


def candidate_id(group: dict) -> str:
    return f"distill-{safe_name(group.get('bucket', ''))}-{safe_name(group.get('key', ''))}-{safe_name(group.get('assessment', ''))}"


def decisions_by_candidate(payload: dict) -> dict:
    decisions = {}
    for decision in payload.get("decisions", []) if isinstance(payload, dict) else []:
        if decision.get("candidate_id"):
            decisions[decision["candidate_id"]] = decision
    return decisions


def target_for_group(group: dict) -> str:
    assessment = group.get("assessment", "")
    if assessment in {"stable_success_path", "stable_fail_closed_pattern"}:
        return "experience_memory"
    if assessment in {"repeat_verifier_failure", "repeat_retry_pattern", "repeat_unknown_state", "repeat_failure_pattern"}:
        return "runtime_standard_candidate"
    if assessment in {"mixed_shadow_warning_pattern", "shadow_warning_pattern"}:
        return "skill_or_capability_review_candidate"
    return "observe_more"


def candidate_type(group: dict) -> str:
    target = target_for_group(group)
    if target == "experience_memory":
        return "experience_candidate"
    if target == "observe_more":
        return "observation_candidate"
    return "rule_candidate"


def priority_for_group(group: dict) -> str:
    assessment = group.get("assessment", "")
    if assessment in {"repeat_failure_pattern", "repeat_verifier_failure", "repeat_unknown_state"}:
        return "high"
    if assessment in {"repeat_retry_pattern", "mixed_shadow_warning_pattern"}:
        return "medium"
    return "low"


def suggested_action(group: dict) -> str:
    assessment = group.get("assessment", "")
    if assessment == "stable_success_path":
        return "Capture as reusable success-path experience."
    if assessment == "stable_fail_closed_pattern":
        return "Capture as expected fail-closed evidence pattern; do not weaken guard."
    if assessment == "repeat_verifier_failure":
        return "Review completion verifier evidence requirements before changing runtime standards."
    if assessment == "repeat_retry_pattern":
        return "Review retry policy and recovery evidence."
    if assessment == "repeat_unknown_state":
        return "Add outcome classifier coverage or require terminal-state evidence."
    if assessment == "mixed_shadow_warning_pattern":
        return "Keep capability under observation or inspect shadow warning samples."
    if assessment == "repeat_failure_pattern":
        return "Open owner review before any rule or runtime standard change."
    return "Keep in observation queue."


def lesson_for_group(group: dict) -> str:
    assessment = group.get("assessment", "")
    bucket = group.get("bucket", "")
    key = group.get("key", "")
    stable = group.get("stable_success_path", "")
    operational = group.get("top_operational_pattern", "")
    common = ", ".join(group.get("common_checks", []) or [])
    if assessment == "stable_success_path":
        return f"{bucket}:{key} has a stable success path: {stable}."
    if assessment == "stable_fail_closed_pattern":
        return f"{bucket}:{key} is a stable fail-closed pattern; preserve guard behavior and evidence classification."
    if assessment == "repeat_verifier_failure":
        return f"{bucket}:{key} repeatedly fails verifier checks: {operational}. Common checks: {common or 'none'}."
    if assessment == "repeat_retry_pattern":
        return f"{bucket}:{key} repeatedly enters retry; inspect retry trigger and recovery path."
    if assessment == "repeat_unknown_state":
        return f"{bucket}:{key} repeatedly lands in unknown state; improve outcome classification or missing terminal-state evidence."
    if assessment == "mixed_shadow_warning_pattern":
        return f"{bucket}:{key} has mixed shadow warnings; review warning findings before further capability promotion."
    if assessment == "repeat_failure_pattern":
        return f"{bucket}:{key} has a repeated operational failure: {operational}."
    return f"{bucket}:{key} needs more observation before distillation."


def build_candidate(group: dict, decision: dict, evidence: dict) -> dict:
    owner_decision = decision.get("decision", "")
    status = "pending_owner_review"
    if owner_decision == "approved":
        status = "approved_pending_writeback"
    elif owner_decision == "rejected":
        status = "rejected"
    elif owner_decision == "defer":
        status = "deferred"
    return {
        "candidate_id": candidate_id(group),
        "candidate_type": candidate_type(group),
        "target": target_for_group(group),
        "priority": priority_for_group(group),
        "status": status,
        "approval_required": True,
        "owner_decision": owner_decision,
        "owner": decision.get("owner", ""),
        "decision_reason": decision.get("reason", ""),
        "source": {
            "bucket": group.get("bucket", ""),
            "key": group.get("key", ""),
            "assessment": group.get("assessment", ""),
            "trajectory_count": group.get("trajectory_count", 0),
            "success_count": group.get("success_count", 0),
            "failure_count": group.get("failure_count", 0),
            "expected_fail_closed_count": group.get("expected_fail_closed_count", 0),
            "shadow_warning_count": group.get("shadow_warning_count", 0),
            "operational_failure_count": group.get("operational_failure_count", 0),
            "success_rate": group.get("success_rate", 0),
            "stable_success_path": group.get("stable_success_path", ""),
            "top_operational_pattern": group.get("top_operational_pattern", ""),
            "top_failure_pattern": group.get("top_failure_pattern", ""),
            "common_checks": group.get("common_checks", []),
        },
        "distillation": {
            "lesson": lesson_for_group(group),
            "suggested_action": suggested_action(group),
            "writeback_allowed": owner_decision == "approved",
            "writeback_target": target_for_group(group),
        },
        "evidence": evidence,
    }


def source_groups(diff: dict) -> list[dict]:
    groups = []
    for key in ["stable_success_groups", "stable_fail_closed_groups", "repeat_verifier_failure_groups", "repeat_failure_groups"]:
        groups.extend(diff.get(key, []) if isinstance(diff, dict) else [])
    for group in diff.get("top_groups", []) if isinstance(diff, dict) else []:
        if group.get("assessment") in {"repeat_retry_pattern", "repeat_unknown_state", "mixed_shadow_warning_pattern"}:
            groups.append(group)
    deduped = {}
    for group in groups:
        deduped[candidate_id(group)] = group
    return list(deduped.values())


def queue_payload(schema_version: str, source_diff_summary: str, candidates: list[dict]) -> dict:
    return {
        "schema_version": schema_version,
        "generated": now(),
        "source_diff_summary": source_diff_summary,
        "candidate_count": len(candidates),
        "pending_count": sum(1 for item in candidates if item["status"] == "pending_owner_review"),
        "approved_pending_writeback_count": sum(1 for item in candidates if item["status"] == "approved_pending_writeback"),
        "rejected_count": sum(1 for item in candidates if item["status"] == "rejected"),
        "deferred_count": sum(1 for item in candidates if item["status"] == "deferred"),
        "no_auto_writeback_guard": True,
        "owner_approval_required": True,
        "items": candidates,
    }


def decision_record(candidate: str, decision: str, owner: str, reason: str) -> dict:
    return {"candidate_id": candidate, "decision": decision, "owner": owner, "reason": reason, "decided_at": now()}


def evidence_links(group: dict, diff_summary: str, research_dir: str) -> dict:
    bucket = safe_name(group.get("bucket", ""))
    key = safe_name(group.get("key", ""))
    return {
        "diff_summary": str(diff_summary),
        "diff_page": f"{str(research_dir).rstrip('/\\')}\\dashboard\\trajectory_diff\\{bucket}__{key}.html",
        "trajectory_ids": group.get("trajectory_ids", []),
    }
