# -*- coding: utf-8 -*-
"""Pure helpers for LangGraph mixed regression reporting."""
import json
from collections import Counter, defaultdict


def score_result(row: dict, rec: dict | None, error: str, truth: str, evidence_blob: str, run_path: str, exact_match_fn, now_fn) -> dict:
    task_id = row["task_id"]
    predicted = (rec or {}).get("final_answer", "")
    return {
        "task_id": task_id,
        "bucket": row.get("mixed_bucket") or row.get("modality", ""),
        "level": row.get("level"),
        "status": (rec or {}).get("status", "harness_error" if error else ""),
        "final_answer": predicted,
        "truth": truth,
        "matched": exact_match_fn(predicted, truth) if truth else False,
        "tokens_used": (rec or {}).get("tokens_used", 0),
        "source_candidate_seen": "source_candidate:" in evidence_blob,
        "ocr_seen": "OCR_RESULT" in evidence_blob or "LAYOUT_RESULT" in evidence_blob,
        "run_path": run_path,
        "error": error,
        "ended": now_fn(),
    }


def bucket_summary(results: list[dict]) -> dict:
    by_bucket = defaultdict(list)
    for row in results:
        by_bucket[row.get("bucket", "")].append(row)
    return {
        bucket: {
            "total": len(rows),
            "matched": sum(1 for item in rows if item.get("matched")),
            "status_counts": dict(Counter(item.get("status", "") for item in rows)),
        }
        for bucket, rows in by_bucket.items()
    }


def progress_payload(schema_version: str, generated: str, results: list[dict]) -> dict:
    return {
        "schema_version": schema_version,
        "generated": generated,
        "total_run": len(results),
        "matched": sum(1 for row in results if row.get("matched")),
        "status_counts": dict(Counter(row.get("status", "") for row in results)),
        "bucket_summary": bucket_summary(results),
        "results": results,
    }


def report_lines(payload: dict) -> list[str]:
    lines = [
        "# Mixed Regression v0.1",
        "",
        f"Generated: `{payload['generated']}`",
        "",
        f"- Total run: `{payload['total_run']}`",
        f"- Matched: `{payload['matched']}`",
        f"- Status counts: `{payload['status_counts']}`",
        "",
        "## Bucket Summary",
        "",
        "| Bucket | Total | Matched | Status counts |",
        "|---|---:|---:|---|",
    ]
    for bucket, summary in payload["bucket_summary"].items():
        lines.append(f"| `{bucket}` | {summary['total']} | {summary['matched']} | `{summary['status_counts']}` |")
    lines.extend([
        "",
        "## Results",
        "",
        "| # | Task | Bucket | L | Status | Match | Answer | Truth | Error |",
        "|---:|---|---|---:|---|---:|---|---|---|",
    ])
    for i, row in enumerate(payload["results"], 1):
        ans = str(row.get("final_answer", "")).replace("|", "\\|")[:90]
        truth = str(row.get("truth", "")).replace("|", "\\|")[:90]
        err = str(row.get("error", "")).replace("|", "\\|")[:90]
        lines.append(
            f"| {i} | `{row['task_id'][:8]}` | `{row.get('bucket','')}` | {row.get('level','')} "
            f"| {row.get('status','')} | {'Y' if row.get('matched') else 'N'} "
            f"| `{ans}` | `{truth}` | `{err}` |"
        )
    return lines


def final_summary(progress_path: str, report_path: str, results: list[dict]) -> dict:
    return {
        "progress": progress_path,
        "report": report_path,
        "total_run": len(results),
        "matched": sum(1 for row in results if row.get("matched")),
        "status_counts": dict(Counter(row.get("status", "") for row in results)),
    }


def dumps_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
