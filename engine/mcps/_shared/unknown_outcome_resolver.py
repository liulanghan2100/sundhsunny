# -*- coding: utf-8 -*-
"""Pure helpers for unknown outcome resolution."""
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


def is_unknown(row: dict) -> bool:
    outcome = row.get("outcome", {}) if isinstance(row.get("outcome"), dict) else {}
    label = str(outcome.get("label", "")).lower()
    category = str(outcome.get("category", "")).lower()
    return category == "unknown" or label.startswith("unknown")


def resolve(row: dict) -> tuple[str, str, str]:
    execution = row.get("execution", {}) if isinstance(row.get("execution"), dict) else {}
    verification = row.get("verification", {}) if isinstance(row.get("verification"), dict) else {}
    outcome = row.get("outcome", {}) if isinstance(row.get("outcome"), dict) else {}
    status = str(execution.get("status", outcome.get("status", ""))).lower()
    phase = str(execution.get("phase", "")).lower()
    decision = str(execution.get("decision", outcome.get("decision", ""))).lower()
    checks = execution.get("checks", []) or []
    tool_calls = execution.get("tool_calls", []) or []

    if status == "queued" and phase == "intake" and not checks and not tool_calls:
        return (
            "queued_snapshot_not_executed",
            "Trajectory is an intake snapshot that never entered execution.",
            "Keep as non-failure queue evidence; exclude from stability failure rate.",
        )
    if not verification and status in {"completed", "success", "passed"}:
        return (
            "missing_verifier_payload",
            "Run appears complete but has no verifier payload.",
            "Require completion_verifier evidence before completion can be trusted.",
        )
    if status in {"queued", "running", "retry", "blocked"} or decision in {"continue", "retry", "block"}:
        return (
            "incomplete_runstate",
            "RunState was captured before terminal archive or verification.",
            "Resume or replay the run before making stability or promotion conclusions.",
        )
    required = ["trajectory_id", "outcome", "execution"]
    missing = [field for field in required if field not in row]
    if missing:
        return (
            "schema_gap",
            f"Trajectory is missing required fields: {', '.join(missing)}.",
            "Backfill schema fields in trajectory generation before analysis.",
        )
    return (
        "needs_manual_triage",
        "Unknown outcome does not match an automated resolver rule.",
        "Review source trajectory and add a resolver rule only after repeated evidence.",
    )


def report_payload(rows: list[dict], schema_version: str) -> dict:
    items = []
    by_resolution = Counter()
    by_task_class = Counter()
    by_capability = Counter()
    by_status = Counter()

    for row in rows:
        if not is_unknown(row):
            continue
        resolution, reason, recommendation = resolve(row)
        execution = row.get("execution", {}) if isinstance(row.get("execution"), dict) else {}
        outcome = row.get("outcome", {}) if isinstance(row.get("outcome"), dict) else {}
        task_class = (row.get("input", {}) or {}).get("task_class", "")
        capability = row.get("capability", "")
        status = execution.get("status", outcome.get("status", ""))
        item = {
            "trajectory_id": row.get("trajectory_id", ""),
            "project": row.get("project", ""),
            "task": row.get("task", ""),
            "capability": capability,
            "task_class": task_class,
            "outcome_label": outcome.get("label", ""),
            "outcome_category": outcome.get("category", ""),
            "execution_phase": execution.get("phase", ""),
            "execution_status": status,
            "execution_decision": execution.get("decision", outcome.get("decision", "")),
            "resolution": resolution,
            "reason": reason,
            "recommendation": recommendation,
            "source_path": row.get("source_path", ""),
            "dashboard_replay_hint": f"trajectory_replay/trajectory/{row.get('trajectory_id', '')}.html",
        }
        items.append(item)
        by_resolution[resolution] += 1
        by_task_class[task_class or "unknown"] += 1
        by_capability[capability or "unknown"] += 1
        by_status[str(status or "unknown")] += 1

    groups = defaultdict(list)
    for item in items:
        groups[item["resolution"]].append(item["trajectory_id"])

    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "unknown_outcomes_found" if items else "no_unknown_outcomes",
        "unknown_count": len(items),
        "items": items[:50],
        "summary": {
            "by_resolution": dict(by_resolution),
            "by_task_class": dict(by_task_class),
            "by_capability": dict(by_capability),
            "by_status": dict(by_status),
        },
        "recommendation_groups": [
            {"resolution": key, "count": len(ids), "trajectory_ids": ids[:20]}
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
