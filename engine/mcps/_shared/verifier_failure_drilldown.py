# -*- coding: utf-8 -*-
"""Pure helpers for verifier failure drilldown."""
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


def verifier_failed(row: dict) -> bool:
    outcome = row.get("outcome", {}) if isinstance(row.get("outcome"), dict) else {}
    verification = row.get("verification", {}) if isinstance(row.get("verification"), dict) else {}
    if outcome.get("is_verifier_failure"):
        return True
    if outcome.get("category") == "verification_failure":
        return True
    if verification and verification.get("passed") is False:
        return True
    return False


def failed_checks(row: dict) -> list[str]:
    execution = row.get("execution", {}) if isinstance(row.get("execution"), dict) else {}
    return [
        str(check.get("name", ""))
        for check in execution.get("checks", []) or []
        if isinstance(check, dict) and not check.get("passed", False) and str(check.get("name", ""))
    ]


def missing_evidence(row: dict) -> list[str]:
    verification = row.get("verification", {}) if isinstance(row.get("verification"), dict) else {}
    missing = verification.get("missing", []) or []
    checks = verification.get("checks", []) or []
    missing_from_checks = [
        str(item.get("evidence", ""))
        for item in checks
        if isinstance(item, dict) and item.get("present") is False and str(item.get("evidence", ""))
    ]
    return sorted({str(item) for item in missing + missing_from_checks if str(item)})


def expected_artifact_gaps(row: dict) -> list[dict]:
    execution = row.get("execution", {}) if isinstance(row.get("execution"), dict) else {}
    gaps = []
    for check in execution.get("checks", []) or []:
        details = check.get("details", {}) if isinstance(check, dict) else {}
        for artifact in details.get("expected_artifacts", []) or []:
            if isinstance(artifact, dict) and artifact.get("exists") is False:
                gaps.append({"path": artifact.get("path", ""), "check": check.get("name", "")})
    return gaps


def recommendation(row: dict, missing: list[str], artifact_gaps: list[dict], checks: list[str]) -> str:
    task_class = (row.get("input", {}) or {}).get("task_class", "")
    if artifact_gaps:
        return "Add artifact creation or mark artifact optional in task card before claiming completion."
    if missing:
        return f"Attach verifier evidence fields before completion: {', '.join(missing)}."
    if "execution_evidence" in checks:
        return "Inspect execution evidence and require command/artifact proof before verifier acceptance."
    if task_class == "C":
        return "For class C tasks, require explicit execution evidence and result proof."
    return "Review completion_verifier payload and add missing evidence contract to task card or RunState."


def report_payload(rows: list[dict], schema_version: str) -> dict:
    failures = []
    by_task_class = Counter()
    by_capability = Counter()
    by_missing = Counter()
    by_failed_check = Counter()
    by_recommendation = Counter()

    for row in rows:
        if not verifier_failed(row):
            continue
        missing = missing_evidence(row)
        checks = failed_checks(row)
        artifacts = expected_artifact_gaps(row)
        rec = recommendation(row, missing, artifacts, checks)
        task_class = (row.get("input", {}) or {}).get("task_class", "")
        capability = row.get("capability", "")
        item = {
            "trajectory_id": row.get("trajectory_id", ""),
            "project": row.get("project", ""),
            "task": row.get("task", ""),
            "capability": capability,
            "task_class": task_class,
            "outcome_label": (row.get("outcome", {}) or {}).get("label", ""),
            "outcome_category": (row.get("outcome", {}) or {}).get("category", ""),
            "source_path": row.get("source_path", ""),
            "missing_evidence": missing,
            "failed_checks": checks,
            "expected_artifact_gaps": artifacts,
            "recommendation": rec,
            "dashboard_replay_hint": f"trajectory_replay/trajectory/{row.get('trajectory_id', '')}.html",
        }
        failures.append(item)
        by_task_class[task_class or "unknown"] += 1
        by_capability[capability or "unknown"] += 1
        by_recommendation[rec] += 1
        for missing_item in missing:
            by_missing[missing_item] += 1
        for check in checks:
            by_failed_check[check] += 1

    groups = defaultdict(list)
    for item in failures:
        groups[item["recommendation"]].append(item["trajectory_id"])

    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "verifier_failures_found" if failures else "no_verifier_failures",
        "failure_count": len(failures),
        "items": failures[:50],
        "summary": {
            "by_task_class": dict(by_task_class),
            "by_capability": dict(by_capability),
            "by_missing_evidence": dict(by_missing),
            "by_failed_check": dict(by_failed_check),
            "by_recommendation": dict(by_recommendation),
        },
        "recommendation_groups": [
            {"recommendation": key, "count": len(ids), "trajectory_ids": ids[:20]}
            for key, ids in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        ],
        "read_only": True,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
