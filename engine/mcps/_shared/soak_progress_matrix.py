# -*- coding: utf-8 -*-
"""Pure helper layer for the 7-day soak progress matrix."""
from datetime import datetime, timedelta


def now(tz) -> str:
    return datetime.now(tz).isoformat()


def expected_dates(soak_start, soak_days: int) -> list[str]:
    return [(soak_start + timedelta(days=offset)).isoformat() for offset in range(soak_days)]


def day_status(check: dict) -> tuple[str, list[str]]:
    fields = [
        "queue_report_exists",
        "knowledge_report_exists",
        "health_report_exists",
        "health_passed",
        "trusted_promote_false",
    ]
    missing = [field for field in fields if not check.get(field, False)]
    return ("passed" if not missing else "missing_evidence", missing)


def next_action(missing: list[str]) -> str:
    if not missing:
        return "No action; day has complete soak evidence."
    labels = {
        "queue_report_exists": "generate queue retro",
        "knowledge_report_exists": "generate knowledge retro",
        "health_report_exists": "run L4 health check",
        "health_passed": "fix failed health check",
        "trusted_promote_false": "record trusted_promote false proof",
    }
    return "; ".join(labels.get(field, field) for field in missing)


def matrix_rows(soak: dict, soak_start, soak_days: int) -> list[dict]:
    checks_by_date = {item.get("date"): item for item in soak.get("day_checks", []) if isinstance(item, dict)}
    rows = []
    for day in expected_dates(soak_start, soak_days):
        check = checks_by_date.get(day, {"date": day})
        status, missing = day_status(check)
        rows.append({
            "date": day,
            "status": status,
            "queue_report_exists": bool(check.get("queue_report_exists", False)),
            "knowledge_report_exists": bool(check.get("knowledge_report_exists", False)),
            "health_report_exists": bool(check.get("health_report_exists", False)),
            "health_passed": bool(check.get("health_passed", False)),
            "trusted_promote_false": bool(check.get("trusted_promote_false", False)),
            "missing_fields": missing,
            "next_action": next_action(missing),
        })
    return rows


def blocked_reasons(soak: dict, rows: list[dict], soak_days: int) -> tuple[int, list[dict], list[str]]:
    passed_days = sum(1 for row in rows if row["status"] == "passed")
    due_days = set(soak.get("expected_days", []) or [])
    overdue_missing = [
        row for row in rows
        if row["date"] in due_days and row["status"] != "passed"
    ]
    reasons = []
    if passed_days < soak_days:
        reasons.append(f"soak_not_complete:{passed_days}/{soak_days}")
    if overdue_missing:
        reasons.append(f"missing_due_day_evidence:{len(overdue_missing)}")
    if soak.get("unauthorized_self_events"):
        reasons.append("unauthorized_self_events_present")
    if soak.get("unexpected_trusted_ids"):
        reasons.append("unexpected_trusted_ids_present")
    automation = soak.get("automation", {}) if isinstance(soak.get("automation"), dict) else {}
    if automation and not automation.get("ok", False):
        reasons.append("automation_not_ok")
    return passed_days, overdue_missing, reasons


def matrix_payload(soak: dict, schema_version: str, generated: str, soak_start,
                   soak_days: int) -> dict:
    rows = matrix_rows(soak, soak_start, soak_days)
    passed_days, overdue_missing, reasons = blocked_reasons(soak, rows, soak_days)
    due_days = set(soak.get("expected_days", []) or [])
    status = "stable_candidate" if not reasons else "soak_in_progress"
    return {
        "schema_version": schema_version,
        "generated": generated,
        "status": status,
        "source_soak_status": soak.get("status", ""),
        "soak_start": str(soak.get("soak_start", "")),
        "soak_days_required": soak_days,
        "passed_days": passed_days,
        "due_days": len(due_days),
        "overdue_missing_days": len(overdue_missing),
        "rows": rows,
        "blocked_reasons": reasons,
        "stable_candidate_allowed": status == "stable_candidate",
        "trusted_promote_auto_proven_false": bool(soak.get("trusted_promote_auto_proven_false", False)),
        "unexpected_trusted_ids": soak.get("unexpected_trusted_ids", []),
        "unauthorized_self_event_count": len(soak.get("unauthorized_self_events", []) or []),
        "automation_ok": bool((soak.get("automation") or {}).get("ok", False)),
        "read_only_matrix": True,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    }


def markdown_lines(report: dict) -> list[str]:
    lines = [
        "# 7-day Soak Progress Matrix v1.5",
        "",
        f"- status: `{report['status']}`",
        f"- passed_days: `{report['passed_days']}/{report['soak_days_required']}`",
        f"- due_days: `{report['due_days']}`",
        f"- overdue_missing_days: `{report['overdue_missing_days']}`",
        f"- stable_candidate_allowed: `{str(report['stable_candidate_allowed']).lower()}`",
        "",
        "| Date | Status | Queue | Knowledge | Health | Health Passed | Trusted False | Next Action |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['date']} | {row['status']} | {row['queue_report_exists']} | "
            f"{row['knowledge_report_exists']} | {row['health_report_exists']} | "
            f"{row['health_passed']} | {row['trusted_promote_false']} | {row['next_action']} |"
        )
    lines.extend(["", "## Blocked Reasons", ""])
    if report["blocked_reasons"]:
        lines.extend(f"- {reason}" for reason in report["blocked_reasons"])
    else:
        lines.append("- none")
    return lines
