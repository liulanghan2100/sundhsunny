# -*- coding: utf-8 -*-
"""Pure helpers for retry recovery verification."""
import json
from collections import Counter
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


def write_json(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def append_jsonl(path, payload: dict, ts: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = ts or now()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": stamp, **payload}, ensure_ascii=True) + "\n")


def outcome(row: dict) -> dict:
    return row.get("outcome", {}) if isinstance(row.get("outcome"), dict) else {}


def execution(row: dict) -> dict:
    return row.get("execution", {}) if isinstance(row.get("execution"), dict) else {}


def is_retry(row: dict) -> bool:
    out = outcome(row)
    exe = execution(row)
    return bool(out.get("is_retry")) or exe.get("status") == "retry" or exe.get("decision") == "retry"


def task_key(row: dict) -> tuple[str, str]:
    return str(row.get("capability", "")), str(row.get("task", ""))


def created(row: dict) -> str:
    return str(row.get("created", ""))


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


def recovery_payload(row: dict) -> dict:
    text = json.dumps(row, ensure_ascii=False).lower()
    return {
        "retry_attempt_id": row.get("trajectory_id", ""),
        "original_failure_id": "failure_id" in text,
        "recovery_action": "recovery_action" in text,
        "rerun_evidence": "rerun_evidence" in text,
        "artifact_recheck_result": "artifact_recheck_result" in text,
        "verifier_result": bool(row.get("verification")),
        "final_outcome": outcome(row).get("label", ""),
    }


def present_recovery_fields(row: dict, required_fields: list[str]) -> list[str]:
    payload = recovery_payload(row)
    present = []
    for field in required_fields:
        value = payload.get(field)
        if (isinstance(value, bool) and value) or (not isinstance(value, bool) and value):
            present.append(field)
    return present


def followup_rows(row: dict, rows: list[dict]) -> list[dict]:
    key = task_key(row)
    start = created(row)
    return [
        candidate for candidate in rows
        if candidate is not row and task_key(candidate) == key and created(candidate) > start
    ]


def recovery_status(row: dict, rows: list[dict], required_fields: list[str]) -> tuple[str, list[str], list[str]]:
    present = set(present_recovery_fields(row, required_fields))
    missing = [field for field in required_fields if field not in present]
    followups = followup_rows(row, rows)
    if any(outcome(candidate).get("is_success") for candidate in followups) and not missing:
        return "retry_recovered", sorted(present), []
    if any(not outcome(candidate).get("is_success") and not outcome(candidate).get("is_expected_failure")
           for candidate in followups):
        return "retry_failed_again", sorted(present), missing
    return "retry_still_open", sorted(present), missing


def contract_payload(schema_version: str, required_fields: list[str]) -> dict:
    return {
        "schema_version": schema_version,
        "generated": now(),
        "required_fields": required_fields,
        "closure_rule": "retry_cannot_be_stable_without_recovery_evidence_and_final_success",
        "states": ["retry_recovered", "retry_still_open", "retry_failed_again"],
        "read_only_contract": True,
        "no_auto_retry": True,
        "no_auto_success": True,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    }


def recovery_item(row: dict, rows: list[dict], required_fields: list[str]) -> dict:
    status, present, missing = recovery_status(row, rows, required_fields)
    followups = followup_rows(row, rows)
    return {
        "trajectory_id": row.get("trajectory_id", ""),
        "project": row.get("project", ""),
        "task": row.get("task", ""),
        "capability": row.get("capability", ""),
        "task_class": (row.get("input") or {}).get("task_class", ""),
        "outcome_label": outcome(row).get("label", ""),
        "execution_status": execution(row).get("status", ""),
        "execution_decision": execution(row).get("decision", ""),
        "recovery_status": status,
        "present_recovery_fields": present,
        "missing_recovery_fields": missing,
        "failed_checks": failed_checks(row),
        "artifact_gaps": artifact_gaps(row),
        "followup_count": len(followups),
        "followup_success_count": sum(1 for candidate in followups if outcome(candidate).get("is_success")),
        "stable_allowed": status == "retry_recovered",
        "recommendation": "Keep retry open until recovery evidence and final success exist." if status != "retry_recovered" else "Retry recovery is converged.",
        "source_path": row.get("source_path", ""),
        "dashboard_replay_hint": f"trajectory_replay/trajectory/{row.get('trajectory_id', '')}.html",
    }


def report_summary(items: list[dict]) -> dict:
    by_status = Counter()
    by_missing = Counter()
    by_capability = Counter()
    for item in items:
        by_status[item["recovery_status"]] += 1
        by_capability[item["capability"] or "unknown"] += 1
        for field in item["missing_recovery_fields"]:
            by_missing[field] += 1
    return {
        "by_recovery_status": dict(by_status),
        "by_capability": dict(by_capability),
        "by_missing_recovery_field": dict(by_missing),
    }


def report_payload(schema_version: str, rows: list[dict], retry_rows: list[dict],
                   required_fields: list[str], contract: dict) -> dict:
    items = [recovery_item(row, rows, required_fields) for row in retry_rows]
    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "open_retry_recovery_found" if any(item["recovery_status"] != "retry_recovered" for item in items) else "all_retries_recovered",
        "trajectory_count": len(rows),
        "retry_count": len(retry_rows),
        "open_retry_count": sum(1 for item in items if item["recovery_status"] == "retry_still_open"),
        "failed_again_count": sum(1 for item in items if item["recovery_status"] == "retry_failed_again"),
        "recovered_count": sum(1 for item in items if item["recovery_status"] == "retry_recovered"),
        "contract": contract,
        "items": items[:50],
        "summary": report_summary(items),
        "read_only": True,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
