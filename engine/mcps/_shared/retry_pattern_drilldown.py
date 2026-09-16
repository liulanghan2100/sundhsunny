# -*- coding: utf-8 -*-
"""Pure helpers for retry pattern drilldown."""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def outcome(row: dict) -> dict:
    return row.get("outcome", {}) if isinstance(row.get("outcome"), dict) else {}


def execution(row: dict) -> dict:
    return row.get("execution", {}) if isinstance(row.get("execution"), dict) else {}


def is_retry(row: dict) -> bool:
    out = outcome(row)
    exe = execution(row)
    return bool(out.get("is_retry")) or exe.get("status") == "retry" or exe.get("decision") == "retry"


def failed_checks(row: dict) -> list[str]:
    return [
        str(check.get("name", ""))
        for check in execution(row).get("checks", []) or []
        if isinstance(check, dict) and check.get("passed") is False and str(check.get("name", ""))
    ]


def artifact_gaps(row: dict) -> list[str]:
    gaps = []
    for check in execution(row).get("checks", []) or []:
        details = check.get("details", {}) if isinstance(check, dict) else {}
        for artifact in details.get("expected_artifacts", []) or []:
            if isinstance(artifact, dict) and artifact.get("exists") is False and str(artifact.get("path", "")):
                gaps.append(str(artifact.get("path", "")))
    return gaps


def retry_reason(row: dict) -> str:
    gaps = artifact_gaps(row)
    checks = failed_checks(row)
    if gaps:
        return "missing_expected_artifact"
    if "completion_verifier" in checks:
        return "completion_verifier_reject"
    if "execution_evidence" in checks:
        return "execution_evidence_failed"
    if checks:
        return "failed_check:" + ",".join(checks)
    return "retry_requested_without_failed_check"


def retry_source(row: dict) -> str:
    events = execution(row).get("events", []) or row.get("events", []) or []
    if any(isinstance(event, dict) and event.get("event") == "retry_requested" for event in events):
        return "runstate_retry_requested_event"
    if execution(row).get("decision") == "retry":
        return "execution_decision_retry"
    if outcome(row).get("is_retry"):
        return "trajectory_outcome_retry"
    return "unknown_retry_source"


def has_followup_success(row: dict, all_rows: list[dict]) -> bool:
    task = str(row.get("task", ""))
    capability = str(row.get("capability", ""))
    created = str(row.get("created", ""))
    for candidate in all_rows:
        if candidate is row:
            continue
        if str(candidate.get("capability", "")) != capability:
            continue
        if str(candidate.get("task", "")) != task:
            continue
        if str(candidate.get("created", "")) <= created:
            continue
        if outcome(candidate).get("is_success"):
            return True
    return False


def recommendation(reason: str, repeat_count: int, followup_success_count: int) -> str:
    if reason == "missing_expected_artifact":
        if followup_success_count:
            return "Keep retry path; inspect successful follow-up and distill artifact recovery rule after owner approval."
        if repeat_count >= 2:
            return "Add pre-retry artifact contract check and require explicit recovery evidence before retry is considered stable."
        return "Observe one more retry sample before changing runtime behavior."
    if reason == "completion_verifier_reject":
        return "Attach missing verifier evidence before retry; do not treat retry as success."
    if reason == "execution_evidence_failed":
        return "Classify execution failure type before retrying and record replay evidence."
    return "Review retry source and add a narrower retry reason rule if repeated."


def report_payload(rows: list[dict], schema_version: str) -> dict:
    retry_rows = [row for row in rows if is_retry(row)]
    by_reason = Counter()
    by_capability = Counter()
    by_task_class = Counter()
    by_source = Counter()
    items = []

    for row in retry_rows:
        reason = retry_reason(row)
        source = retry_source(row)
        task_class = (row.get("input") or {}).get("task_class", "")
        capability = row.get("capability", "")
        followup_success = has_followup_success(row, rows)
        item = {
            "trajectory_id": row.get("trajectory_id", ""),
            "project": row.get("project", ""),
            "task": row.get("task", ""),
            "capability": capability,
            "task_class": task_class,
            "outcome_label": outcome(row).get("label", ""),
            "execution_status": execution(row).get("status", ""),
            "execution_decision": execution(row).get("decision", ""),
            "retry_reason": reason,
            "retry_source": source,
            "failed_checks": failed_checks(row),
            "artifact_gaps": artifact_gaps(row),
            "has_followup_success": followup_success,
            "source_path": row.get("source_path", ""),
            "dashboard_replay_hint": f"trajectory_replay/trajectory/{row.get('trajectory_id', '')}.html",
        }
        items.append(item)
        by_reason[reason] += 1
        by_capability[capability or "unknown"] += 1
        by_task_class[task_class or "unknown"] += 1
        by_source[source] += 1

    groups = defaultdict(list)
    for item in items:
        groups["|".join([item["capability"], item["task_class"], item["retry_reason"]])].append(item)

    pattern_groups = []
    for key, group_items in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        reason = group_items[0]["retry_reason"] if group_items else ""
        followup_success_count = sum(1 for item in group_items if item["has_followup_success"])
        pattern_groups.append({
            "pattern": key,
            "count": len(group_items),
            "retry_reason": reason,
            "followup_success_count": followup_success_count,
            "repeated": len(group_items) >= 2,
            "recommendation": recommendation(reason, len(group_items), followup_success_count),
            "trajectory_ids": [item["trajectory_id"] for item in group_items[:20]],
        })

    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "retry_patterns_found" if retry_rows else "no_retry_patterns",
        "retry_count": len(retry_rows),
        "repeat_pattern_count": sum(1 for group in pattern_groups if group["repeated"]),
        "items": items[:50],
        "summary": {
            "by_reason": dict(by_reason),
            "by_capability": dict(by_capability),
            "by_task_class": dict(by_task_class),
            "by_source": dict(by_source),
        },
        "pattern_groups": pattern_groups,
        "read_only": True,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
