# -*- coding: utf-8 -*-
"""Pure helpers for trajectory export."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = "agent-os-trajectory/v0.2"
SUMMARY_SCHEMA_VERSION = "agent-os-trajectory-summary/v0.2"
REPLAY_INDEX_SCHEMA_VERSION = "agent-os-replay-index/v0.2"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def write_jsonl(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def fingerprint(row: dict) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def compat() -> dict:
    return {
        "current": SCHEMA_VERSION,
        "compatible_with": ["agent-os-trajectory/v0.1"],
        "v0_1_fields_preserved": [
            "schema_version",
            "trajectory_id",
            "source_type",
            "source_path",
            "created",
            "updated",
            "project",
            "task",
            "capability",
            "capability_status",
            "input",
            "execution",
            "verification",
            "human_decision",
            "memory_writeback",
            "outcome",
        ],
    }


def outcome(label: str, legacy_label: str, category: str, reason: str, **flags) -> dict:
    return {
        "label": label,
        "legacy_label": legacy_label,
        "category": category,
        "reason": reason,
        "is_success": bool(flags.get("is_success", False)),
        "is_expected_failure": bool(flags.get("is_expected_failure", False)),
        "is_verifier_failure": bool(flags.get("is_verifier_failure", False)),
        "is_retry": bool(flags.get("is_retry", False)),
        "requires_owner_review": bool(flags.get("requires_owner_review", False)),
    }


def runstate_outcome(run: dict) -> dict:
    verifier = run.get("completion_verifier") or {}
    if run.get("status") == "completed" and run.get("decision") == "complete":
        return outcome("run_success_complete", "pass", "success", "run completed and task decision is complete", is_success=True)
    if verifier and verifier.get("passed") is False:
        missing = verifier.get("missing", [])
        forbidden_hits = verifier.get("forbidden_hits", [])
        if missing:
            label = "verifier_reject_missing_evidence"
            reason = "completion verifier rejected because required evidence is missing"
        elif forbidden_hits:
            label = "verifier_reject_forbidden_output"
            reason = "completion verifier rejected because forbidden output was detected"
        else:
            label = "verifier_reject_insufficient_evidence"
            reason = "completion verifier rejected without enough acceptance evidence"
        return outcome(label, "verifier_reject", "verification_failure", reason, is_verifier_failure=True)
    if run.get("status") in {"blocked", "failed"} or run.get("decision") == "block":
        task = str(run.get("task", "")).lower()
        if "admin" in task:
            return outcome("expected_fail_closed_admin_guard", "expected_fail_closed", "expected_fail_closed", "admin permission request was blocked by policy", is_expected_failure=True)
        if "missing" in task or "evidence" in task:
            return outcome("expected_fail_closed_missing_artifact", "expected_fail_closed", "expected_fail_closed", "missing artifact or evidence case failed closed", is_expected_failure=True)
        if "must fail" in task or "fail-closed" in task:
            return outcome("expected_fail_closed_policy_case", "expected_fail_closed", "expected_fail_closed", "synthetic fail-closed case behaved as expected", is_expected_failure=True)
        return outcome("unexpected_failure_runtime", "unexpected_failure", "unexpected_failure", "runtime failed or blocked without expected-failure markers")
    if run.get("status") == "retry" or run.get("decision") == "retry":
        return outcome("retry_event", "retry", "retry", "task entered retry path", is_retry=True)
    return outcome("unknown_incomplete", "unknown", "unknown", "outcome cannot be classified from current evidence")


def base_row(source_type: str, source_path: Path, trajectory_id: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_compat": compat(),
        "trajectory_id": trajectory_id,
        "source_type": source_type,
        "source_path": str(source_path),
    }


def replay_ref(row: dict, line_no: int) -> dict:
    return {
        "trajectory_id": row.get("trajectory_id", ""),
        "line": line_no,
        "source_type": row.get("source_type", ""),
        "capability": row.get("capability", ""),
        "task_class": row.get("input", {}).get("task_class", ""),
        "label": row.get("outcome", {}).get("label", ""),
        "legacy_label": row.get("outcome", {}).get("legacy_label", ""),
        "category": row.get("outcome", {}).get("category", ""),
        "source_path": row.get("source_path", ""),
    }


def add_index(index: dict, bucket: str, key: str, ref: dict) -> None:
    if not key:
        key = "_empty"
    index.setdefault(bucket, {}).setdefault(key, []).append(ref)


def build_replay_index(rows: list[dict], replay_index_schema_version: str, jsonl_path: str) -> dict:
    index = {
        "schema_version": replay_index_schema_version,
        "generated": now(),
        "trajectory_schema_version": SCHEMA_VERSION,
        "jsonl_path": jsonl_path,
        "count": len(rows),
        "by_trajectory_id": {},
        "by_source_type": {},
        "by_capability": {},
        "by_task_class": {},
        "by_outcome_label": {},
        "by_legacy_label": {},
        "by_outcome_category": {},
    }
    for line_no, row in enumerate(rows, start=1):
        ref = replay_ref(row, line_no)
        index["by_trajectory_id"][ref["trajectory_id"]] = ref
        add_index(index, "by_source_type", ref["source_type"], ref)
        add_index(index, "by_capability", ref["capability"], ref)
        add_index(index, "by_task_class", ref["task_class"], ref)
        add_index(index, "by_outcome_label", ref["label"], ref)
        add_index(index, "by_legacy_label", ref["legacy_label"], ref)
        add_index(index, "by_outcome_category", ref["category"], ref)
    return index


def summary_payload(rows: list[dict], replay_index: dict, trajectory_jsonl: str, replay_index_path: str) -> dict:
    counts = {}
    labels = {}
    legacy_labels = {}
    categories = {}
    for row in rows:
        source_type = row.get("source_type", "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1
        label = row.get("outcome", {}).get("label", "unknown")
        labels[label] = labels.get(label, 0) + 1
        legacy_label = row.get("outcome", {}).get("legacy_label", "unknown")
        legacy_labels[legacy_label] = legacy_labels.get(legacy_label, 0) + 1
        category = row.get("outcome", {}).get("category", "unknown")
        categories[category] = categories.get(category, 0) + 1
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "generated": now(),
        "trajectory_schema_version": SCHEMA_VERSION,
        "compatible_with": ["agent-os-trajectory-summary/v0.1"],
        "trajectory_count": len(rows),
        "source_counts": counts,
        "label_counts": labels,
        "legacy_label_counts": legacy_labels,
        "category_counts": categories,
        "path": trajectory_jsonl,
        "replay_index_path": replay_index_path,
        "replay_index_count": replay_index.get("count", 0),
    }



def export_rows(runstate_rows: list[dict], shadow_rows: list[dict], review_rows: list[dict], canary_rows: list[dict]) -> list[dict]:
    rows = []
    rows.extend(runstate_rows)
    rows.extend(shadow_rows)
    rows.extend(review_rows)
    rows.extend(canary_rows)
    rows.sort(key=lambda row: (row.get("created", ""), row.get("trajectory_id", "")))
    for line_no, row in enumerate(rows, start=1):
        row["replay"] = {
            "jsonl_path": "",
            "line": line_no,
            "fingerprint": fingerprint(row),
        }
    return rows


def export_summary(rows: list[dict], replay_index: dict, trajectory_jsonl: str, replay_index_path: str) -> dict:
    return summary_payload(rows, replay_index, trajectory_jsonl, replay_index_path)
