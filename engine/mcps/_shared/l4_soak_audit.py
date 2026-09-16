# -*- coding: utf-8 -*-
"""Pure helpers for L4 soak audit construction."""
import json
import os
from datetime import date, datetime, timedelta, timezone


CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def read_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            items.append(data)
    return items


def kb_items(kb_meta) -> list[dict]:
    return read_jsonl(kb_meta)


def automation_status(automation_file) -> dict:
    text = automation_file.read_text(encoding="utf-8-sig") if automation_file.exists() else ""
    normalized = text.replace("\\\\", "\\")
    checks = {
        "exists": automation_file.exists(),
        "active": 'status = "ACTIVE"' in text,
        "daily_7am": "BYHOUR=7" in text and "BYMINUTE=0" in text,
        "uses_guard": "agent_os_l4_daily_guard.py" in text,
        "uses_absolute_workspace": "C:\\Users\\sundh\\Documents\\KIMI_MODE\\createMCP\\MCPCreate20260719" in normalized,
        "uses_absolute_guard": "python C:\\Users\\sundh\\Documents\\KIMI_MODE\\createMCP\\MCPCreate20260719\\03_鍒嗗伐MCP\\agent_os_l4_daily_guard.py" in normalized,
        "mentions_health_check": "agent_os_l4_daily_health_check.py" in text and "l4_health_check" in text,
        "mentions_not_before": "2026-08-01 07:00" in text,
        "no_trusted_promote": "涓嶈嚜鍔?promote trusted" in text,
    }
    return {"path": str(automation_file), "checks": checks, "ok": all(checks.values())}


def date_range(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def parse_datetime(value: str, tz=CHINA_TZ) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def new_baseline(now: datetime, soak_start: datetime, kb_meta) -> dict:
    items = kb_items(kb_meta)
    trusted_ids = sorted(item.get("id", "") for item in items if item.get("status") == "trusted")
    quarantine_ids = sorted(item.get("id", "") for item in items if item.get("status") == "quarantine")
    return {
        "created_at": now.isoformat(),
        "soak_start": soak_start.isoformat(),
        "trusted_count": len(trusted_ids),
        "trusted_ids": trusted_ids,
        "quarantine_count": len(quarantine_ids),
        "quarantine_ids": quarantine_ids,
    }


def ensure_baseline(now: datetime, soak_start: datetime, baseline_json, daily_retro_dir, kb_meta) -> tuple[dict, list[str]]:
    existing = load_json(baseline_json, {})
    issues: list[str] = []
    if existing:
        created_at = parse_datetime(str(existing.get("created_at", "")))
        if created_at and created_at > now + timedelta(minutes=5):
            issues.append("baseline_created_at_in_future")
            if now < soak_start:
                backup = baseline_json.with_suffix(f".invalid-{now.strftime('%Y%m%d%H%M%S')}.json")
                baseline_json.replace(backup)
                baseline = new_baseline(now, soak_start, kb_meta)
                baseline["repaired_from"] = str(backup)
                daily_retro_dir.mkdir(parents=True, exist_ok=True)
                baseline_json.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
                return baseline, issues
        return existing, issues
    baseline = new_baseline(now, soak_start, kb_meta)
    daily_retro_dir.mkdir(parents=True, exist_ok=True)
    baseline_json.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    return baseline, issues


def audit_payload(now: datetime, soak_start: datetime, soak_days: int, daily_retro_dir, baseline_json,
                  kb_meta, governance_path, events_path, automation_file, report_json_path, report_md_path) -> dict:
    baseline, baseline_issues = ensure_baseline(now, soak_start, baseline_json, daily_retro_dir, kb_meta)
    governance = load_json(governance_path, {})
    events = read_jsonl(events_path)
    kb_items_current = kb_items(kb_meta)
    trusted_ids = sorted(item.get("id", "") for item in kb_items_current if item.get("status") == "trusted")
    unexpected_trusted = sorted(set(trusted_ids) - set(baseline.get("trusted_ids", [])))
    automation = automation_status(automation_file)
    unauthorized_self_events = [
        event for event in events
        if event.get("initiated_by") == "self"
        and event.get("event") == "enqueued"
        and event.get("template") not in {"daily_queue_retro"}
    ]
    if now.date() < soak_start.date():
        expected_days = []
        status = "waiting_until_start"
    else:
        end = min(now.date(), (soak_start.date() + timedelta(days=soak_days - 1)))
        expected_days = [d.isoformat() for d in date_range(soak_start.date(), end)]
        status = "in_progress"

    day_checks = []
    for day in expected_days:
        queue_report = daily_retro_dir / f"{day}_queue_retro.md"
        knowledge_report = kb_meta.parent / "reports" / f"{day}_knowledge_retro.md"
        health_report = daily_retro_dir / f"{day}_l4_health_check.json"
        knowledge_text = knowledge_report.read_text(encoding="utf-8") if knowledge_report.exists() else ""
        health = load_json(health_report, {})
        day_checks.append({
            "date": day,
            "queue_report_exists": queue_report.exists(),
            "knowledge_report_exists": knowledge_report.exists(),
            "health_report_exists": health_report.exists(),
            "health_passed": health.get("status") == "passed",
            "trusted_promote_false": "trusted_promote: `false`" in knowledge_text,
        })

    missing = [
        check for check in day_checks
        if not (
            check["queue_report_exists"]
            and check["knowledge_report_exists"]
            and check["health_report_exists"]
            and check["health_passed"]
            and check["trusted_promote_false"]
        )
    ]
    completed_days = len(day_checks) - len(missing)
    if expected_days and completed_days == soak_days and not unauthorized_self_events and not unexpected_trusted:
        status = "stable_candidate"
    elif missing or unauthorized_self_events or unexpected_trusted or not automation["ok"] or (baseline_issues and now >= soak_start):
        status = "attention_required"

    result = {
        "generated_at": now.isoformat(),
        "status": status,
        "soak_start": soak_start.isoformat(),
        "soak_days_required": soak_days,
        "completed_days": completed_days,
        "expected_days": expected_days,
        "day_checks": day_checks,
        "governance_enabled": bool(governance.get("enabled")),
        "breaker_tripped": bool(governance.get("breaker_tripped")),
        "automation": automation,
        "unauthorized_self_events": unauthorized_self_events,
        "baseline": baseline,
        "baseline_issues": baseline_issues,
        "trusted_count_current": len(trusted_ids),
        "unexpected_trusted_ids": unexpected_trusted,
        "trusted_promote_auto_proven_false": not unexpected_trusted,
    }
    return result


def report_lines(result: dict) -> list[str]:
    lines = [
        "# Agent OS L4 Soak Audit",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- status: `{result['status']}`",
        f"- soak_start: `{result['soak_start']}`",
        f"- completed_days: `{result['completed_days']}/{result['soak_days_required']}`",
        f"- governance_enabled: `{str(result['governance_enabled']).lower()}`",
        f"- breaker_tripped: `{str(result['breaker_tripped']).lower()}`",
        f"- automation_ok: `{str(result['automation']['ok']).lower()}`",
        f"- trusted_promote_auto_proven_false: `{str(result['trusted_promote_auto_proven_false']).lower()}`",
        "",
        "## Day Checks",
        "",
    ]
    if result["day_checks"]:
        for check in result["day_checks"]:
            lines.append(
                f"- {check['date']}: queue={check['queue_report_exists']} "
                f"knowledge={check['knowledge_report_exists']} "
                f"health={check['health_report_exists']} "
                f"health_passed={check['health_passed']} "
                f"trusted_promote_false={check['trusted_promote_false']}"
            )
    else:
        lines.append("- waiting for first formal soak day")
    lines.extend(["", "## Attention", ""])
    if result["unauthorized_self_events"]:
        lines.append(f"- unauthorized self events: {len(result['unauthorized_self_events'])}")
    if result.get("baseline_issues"):
        lines.append(f"- baseline issues: {', '.join(result['baseline_issues'])}")
    if result["unexpected_trusted_ids"]:
        lines.append(f"- trusted ids added since baseline: {', '.join(result['unexpected_trusted_ids'])}")
    if not result["automation"]["ok"]:
        failed = [name for name, ok in result["automation"]["checks"].items() if not ok]
        lines.append(f"- automation checks failed: {', '.join(failed)}")
    if (
        not result["unauthorized_self_events"]
        and not result.get("baseline_issues")
        and not result["unexpected_trusted_ids"]
        and result["automation"]["ok"]
    ):
        lines.append("- no unauthorized self enqueue or trusted auto-promotion detected")
    return lines
