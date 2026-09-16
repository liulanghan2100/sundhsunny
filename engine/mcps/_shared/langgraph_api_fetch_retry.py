# -*- coding: utf-8 -*-
"""Pure helpers for API/fetch targeted retry reporting."""
import json
from collections import Counter


def score_result(row: dict, rec: dict | None, error: str, truth: str, blob: str, run_path: str, exact_match_fn, now_fn) -> dict:
    task_id = row["task_id"]
    predicted = (rec or {}).get("final_answer", "")
    return {
        "task_id": task_id,
        "level": row.get("level"),
        "prior_reason": row.get("reason"),
        "prior_status": row.get("status"),
        "status": (rec or {}).get("status", "harness_error" if error else ""),
        "final_answer": predicted,
        "truth": truth,
        "matched": exact_match_fn(predicted, truth) if truth else False,
        "tokens_used": (rec or {}).get("tokens_used", 0),
        "api_hint_seen": "api_recovery_hint" in blob or "[SOURCE RECIPE:" in blob,
        "source_candidate_seen": "source_candidate:" in blob,
        "run_path": run_path,
        "error": error,
        "ended": now_fn(),
    }


def progress_payload(schema_version: str, generated: str, results: list[dict]) -> dict:
    return {
        "schema_version": schema_version,
        "generated": generated,
        "total_run": len(results),
        "matched": sum(1 for row in results if row.get("matched")),
        "api_hint_seen": sum(1 for row in results if row.get("api_hint_seen")),
        "source_candidate_seen": sum(1 for row in results if row.get("source_candidate_seen")),
        "status_counts": dict(Counter(row.get("status", "") for row in results)),
        "results": results,
    }


def report_lines(payload: dict) -> list[str]:
    lines = [
        "# API Fetch Targeted Retry v0.1",
        "",
        f"Generated: `{payload['generated']}`",
        "",
        f"- Total run: `{payload['total_run']}`",
        f"- Matched: `{payload['matched']}`",
        f"- API/source hint seen: `{payload['api_hint_seen']}`",
        f"- Source candidate seen: `{payload['source_candidate_seen']}`",
        f"- Status counts: `{payload['status_counts']}`",
        "",
        "| # | Task | L | Prior | Status | Hint | Candidate | Match | Answer | Truth | Error |",
        "|---:|---|---:|---|---|---:|---:|---:|---|---|---|",
    ]
    for i, row in enumerate(payload["results"], 1):
        ans = str(row.get("final_answer", "")).replace("|", "\\|")[:90]
        truth = str(row.get("truth", "")).replace("|", "\\|")[:90]
        err = str(row.get("error", "")).replace("|", "\\|")[:90]
        lines.append(
            f"| {i} | `{row['task_id'][:8]}` | {row.get('level','')} | {row.get('prior_reason','')} "
            f"| {row.get('status','')} | {'Y' if row.get('api_hint_seen') else 'N'} "
            f"| {'Y' if row.get('source_candidate_seen') else 'N'} | {'Y' if row.get('matched') else 'N'} "
            f"| `{ans}` | `{truth}` | `{err}` |"
        )
    return lines


def final_summary(progress_path: str, report_path: str, results: list[dict]) -> dict:
    return {
        "progress": progress_path,
        "report": report_path,
        "total_run": len(results),
        "matched": sum(1 for row in results if row.get("matched")),
        "api_hint_seen": sum(1 for row in results if row.get("api_hint_seen")),
        "source_candidate_seen": sum(1 for row in results if row.get("source_candidate_seen")),
        "status_counts": dict(Counter(row.get("status", "") for row in results)),
    }


def dumps_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
