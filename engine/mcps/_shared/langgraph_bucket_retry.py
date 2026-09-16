# -*- coding: utf-8 -*-
"""Pure helpers for LangGraph bucket retry reports."""
import json
from collections import Counter


def score_result(row: dict, rec: dict | None, error: str, truth: str, blob: str, run_path: str,
                 exact_match_fn, now_fn, marker_field: str, marker_seen: bool,
                 extra_fields: dict | None = None) -> dict:
    predicted = (rec or {}).get("final_answer", "")
    payload = {
        "task_id": row["task_id"],
        "level": row.get("level"),
        "prior_reason": row.get("reason"),
        "prior_status": row.get("status"),
        "status": (rec or {}).get("status", "harness_error" if error else ""),
        "final_answer": predicted,
        "truth": truth,
        "matched": exact_match_fn(predicted, truth) if truth else False,
        "tokens_used": (rec or {}).get("tokens_used", 0),
        marker_field: marker_seen,
        "run_path": run_path,
        "error": error,
        "ended": now_fn(),
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload


def progress_payload(schema_version: str, generated: str, results: list[dict], marker_field: str) -> dict:
    return {
        "schema_version": schema_version,
        "generated": generated,
        "total_run": len(results),
        "matched": sum(1 for row in results if row.get("matched")),
        marker_field: sum(1 for row in results if row.get(marker_field)),
        "status_counts": dict(Counter(row.get("status", "") for row in results)),
        "results": results,
    }


def report_lines(payload: dict, title: str, marker_field: str, marker_label: str,
                 marker_column: str) -> list[str]:
    lines = [
        f"# {title}",
        "",
        f"Generated: `{payload['generated']}`",
        "",
        f"- Total run: `{payload['total_run']}`",
        f"- Matched: `{payload['matched']}`",
        f"- {marker_label}: `{payload[marker_field]}`",
        f"- Status counts: `{payload['status_counts']}`",
        "",
        f"| # | Task | L | Prior | Status | {marker_column} | Match | Answer | Truth | Error |",
        "|---:|---|---:|---|---|---:|---:|---|---|---|",
    ]
    for i, row in enumerate(payload["results"], 1):
        ans = str(row.get("final_answer", "")).replace("|", "\\|")[:90]
        truth = str(row.get("truth", "")).replace("|", "\\|")[:90]
        err = str(row.get("error", "")).replace("|", "\\|")[:90]
        lines.append(
            f"| {i} | `{row['task_id'][:8]}` | {row.get('level','')} | {row.get('prior_reason','')} "
            f"| {row.get('status','')} | {'Y' if row.get(marker_field) else 'N'} "
            f"| {'Y' if row.get('matched') else 'N'} | `{ans}` | `{truth}` | `{err}` |"
        )
    return lines


def final_summary(progress_path: str, report_path: str, results: list[dict], marker_field: str) -> dict:
    return {
        "progress": progress_path,
        "report": report_path,
        "total_run": len(results),
        "matched": sum(1 for row in results if row.get("matched")),
        marker_field: sum(1 for row in results if row.get(marker_field)),
        "status_counts": dict(Counter(row.get("status", "") for row in results)),
    }


def dumps_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
