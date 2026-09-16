# -*- coding: utf-8 -*-
"""Pure helpers for LangGraph targeted retry reporting."""
import json
from collections import Counter


def candidate_rows(candidates: dict, labels: tuple[str, ...]) -> list[dict]:
    rows = []
    seen = set()
    sets = candidates.get("sets", {}) if isinstance(candidates, dict) else {}
    for label in labels:
        for row in sets.get(label, []):
            task_id = row.get("task_id")
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            item = dict(row)
            item["retry_set"] = label
            rows.append(item)
    return rows


def default_progress(schema_version: str, generated: str, updated: str) -> dict:
    return {
        "schema_version": schema_version,
        "generated": generated,
        "updated": updated,
        "results": [],
    }


def score_result(row: dict, rec: dict | None, error: str, truth: str, exact_match_fn, now_fn) -> dict:
    predicted = (rec or {}).get("final_answer", "")
    return {
        "task_id": row["task_id"],
        "retry_set": row.get("retry_set", ""),
        "level": row.get("level"),
        "prior_reason": row.get("reason"),
        "status": (rec or {}).get("status", "harness_error" if error else ""),
        "final_answer": predicted,
        "truth": truth,
        "matched": exact_match_fn(predicted, truth) if truth else False,
        "tokens_used": (rec or {}).get("tokens_used", 0),
        "error": error,
        "ended": now_fn(),
    }


def update_progress(progress: dict, updated: str) -> dict:
    progress["updated"] = updated
    results = progress.get("results", [])
    progress["total_run"] = len(results)
    progress["matched"] = sum(1 for row in results if row.get("matched"))
    progress["status_counts"] = dict(Counter(row.get("status", "") for row in results))
    progress["set_counts"] = dict(Counter(row.get("retry_set", "") for row in results))
    return progress


def report_lines(progress: dict) -> list[str]:
    lines = [
        "# Targeted Retry v0.5",
        "",
        f"Updated: `{progress['updated']}`",
        "",
        f"- Total run: `{progress['total_run']}`",
        f"- Matched: `{progress['matched']}`",
        f"- Status counts: `{progress['status_counts']}`",
        "",
        "| # | Task | Set | L | Status | Match | Answer | Truth | Error |",
        "|---:|---|---|---:|---|---:|---|---|---|",
    ]
    for i, row in enumerate(progress.get("results", []), 1):
        ans = str(row.get("final_answer", "")).replace("|", "\\|")[:80]
        truth = str(row.get("truth", "")).replace("|", "\\|")[:80]
        err = str(row.get("error", "")).replace("|", "\\|")[:80]
        lines.append(
            f"| {i} | `{row['task_id'][:8]}` | {row.get('retry_set','')} | {row.get('level','')} "
            f"| {row.get('status','')} | {'Y' if row.get('matched') else 'N'} | `{ans}` | `{truth}` | `{err}` |"
        )
    return lines


def final_summary(progress_path: str, report_path: str, progress: dict) -> dict:
    return {
        "progress": progress_path,
        "report": report_path,
        "total_run": progress["total_run"],
        "matched": progress["matched"],
        "status_counts": progress["status_counts"],
    }


def dumps_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
