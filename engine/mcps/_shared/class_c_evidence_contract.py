# -*- coding: utf-8 -*-
"""Pure helpers for Class C evidence coverage."""
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


def context_text(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False).lower()


def verifier_missing(row: dict) -> list[str]:
    verification = row.get("verification", {}) if isinstance(row.get("verification"), dict) else {}
    checks = verification.get("checks", []) or []
    missing = list(verification.get("missing", []) or [])
    missing.extend(
        item.get("evidence", "")
        for item in checks
        if isinstance(item, dict) and item.get("present") is False
    )
    return sorted({str(item) for item in missing if str(item)})


def present_fields(row: dict, required_fields: list[str]) -> list[str]:
    text = context_text(row)
    missing = set(verifier_missing(row))
    return [field for field in required_fields if field in text and field not in missing]


def missing_fields(row: dict, required_fields: list[str]) -> list[str]:
    present = set(present_fields(row, required_fields))
    missing = set(verifier_missing(row))
    contract_missing = [field for field in required_fields if field not in present]
    return sorted(set(contract_missing) | (missing & set(required_fields)))


def task_class(row: dict) -> str:
    input_payload = row.get("input", {}) if isinstance(row.get("input"), dict) else {}
    verification = row.get("verification", {}) if isinstance(row.get("verification"), dict) else {}
    return str(input_payload.get("task_class") or verification.get("task_class") or "")


def contract_payload(schema_version: str, required_fields: list[str], field_groups: dict) -> dict:
    return {
        "schema_version": schema_version,
        "generated": now(),
        "task_class": "C",
        "required_fields": required_fields,
        "field_groups": field_groups,
        "closure_rule": "fail_closed_until_all_required_fields_are_present",
        "present_check": "field_name_present_in_completion_verifier_context_or_verifier_checks",
        "no_auto_fill": True,
        "read_only_contract": True,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    }


def evidence_item(row: dict, required_fields: list[str]) -> dict:
    missing = missing_fields(row, required_fields)
    present = present_fields(row, required_fields)
    status = "contract_satisfied" if not missing else "contract_missing_required_evidence"
    outcome = row.get("outcome", {}) if isinstance(row.get("outcome"), dict) else {}
    execution = row.get("execution", {}) if isinstance(row.get("execution"), dict) else {}
    return {
        "trajectory_id": row.get("trajectory_id", ""),
        "project": row.get("project", ""),
        "task": row.get("task", ""),
        "capability": row.get("capability", ""),
        "task_class": "C",
        "outcome_label": outcome.get("label", ""),
        "outcome_category": outcome.get("category", ""),
        "execution_status": execution.get("status", ""),
        "contract_status": status,
        "present_fields": present,
        "missing_fields": missing,
        "missing_count": len(missing),
        "required_count": len(required_fields),
        "coverage": round((len(required_fields) - len(missing)) / len(required_fields), 4),
        "recommendation": "Attach real Class C evidence before claiming completion." if missing else "Class C evidence contract satisfied.",
        "source_path": row.get("source_path", ""),
        "dashboard_replay_hint": f"trajectory_replay/trajectory/{row.get('trajectory_id', '')}.html",
    }


def report_summary(items: list[dict]) -> dict:
    by_missing = Counter()
    by_capability = Counter()
    by_status = Counter()
    for item in items:
        by_capability[item["capability"] or "unknown"] += 1
        by_status[item["contract_status"]] += 1
        for field in item["missing_fields"]:
            by_missing[field] += 1
    return {
        "by_contract_status": dict(by_status),
        "by_capability": dict(by_capability),
        "by_missing_field": dict(by_missing),
    }


def report_payload(schema_version: str, rows: list[dict], class_c_rows: list[dict],
                   required_fields: list[str], contract: dict) -> dict:
    items = [evidence_item(row, required_fields) for row in class_c_rows]
    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "class_c_gaps_found" if any(item["missing_fields"] for item in items) else "class_c_contract_satisfied",
        "trajectory_count": len(rows),
        "class_c_count": len(class_c_rows),
        "gap_count": sum(1 for item in items if item["missing_fields"]),
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
