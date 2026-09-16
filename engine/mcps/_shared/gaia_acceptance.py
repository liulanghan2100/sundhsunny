# -*- coding: utf-8 -*-
"""Pure scoring and reporting helpers for the GAIA acceptance runner."""
import json
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_runs(runs_dir: Path) -> dict[str, dict]:
    runs = {}
    if runs_dir.exists():
        for path in runs_dir.glob("*/run.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                runs[data["task_id"]] = data
            except Exception:
                continue
    return runs


def pick_smoke(index: dict, baseline_runs: dict[str, dict]) -> list[str]:
    val = index.get("validation", [])
    by_level: dict[int, list] = {}
    attachments = []
    for row in val:
        by_level.setdefault(row.get("level", 0), []).append(row)
        if row.get("file_path"):
            attachments.append(row)
    prev_max_steps = [r for r in baseline_runs.values() if r.get("status") == "max_steps_reached"]

    picked: list[str] = []
    for row in attachments[:2]:
        if row["task_id"] not in picked:
            picked.append(row["task_id"])
    for level in (3, 2, 1):
        for row in (by_level.get(level) or [])[:2]:
            if row["task_id"] not in picked:
                picked.append(row["task_id"])
    for run in prev_max_steps[:2]:
        if run["task_id"] not in picked:
            picked.append(run["task_id"])
    return picked[:10]


def score_accuracy(index: dict, runs: dict[str, dict], ground_truths, exact_match, failure_reason,
                   split: str, task_ids: list[str] | None = None) -> dict:
    truths = ground_truths(index, split)
    rows = []
    for task_id, truth in truths.items():
        if task_ids is not None and task_id not in task_ids:
            continue
        run = runs.get(task_id)
        if not run:
            rows.append({"task_id": task_id, "level": 0, "solved": False, "matched": False, "reason": "not_run"})
            continue
        predicted = run.get("final_answer", "")
        matched = exact_match(predicted, truth) if truth else None
        rows.append({
            "task_id": task_id,
            "level": run.get("level", 0),
            "status": run.get("status", ""),
            "solved": run.get("status") == "completed" and bool(predicted),
            "matched": matched,
            "reason": failure_reason(run, bool(matched)),
            "predicted": predicted[:120],
            "ground_truth": truth,
        })
    by_level = {}
    for row in rows:
        bucket = by_level.setdefault(row["level"], {"total": 0, "solved": 0, "matched": 0})
        bucket["total"] += 1
        if row["solved"]:
            bucket["solved"] += 1
        if row["matched"]:
            bucket["matched"] += 1
    by_reason = {}
    for row in rows:
        reason = row.get("reason") or "unknown"
        by_reason[reason] = by_reason.get(reason, 0) + 1
    total = len(rows) or 1
    matched = sum(1 for r in rows if r["matched"] is True)
    return {
        "generated": now(),
        "split": split,
        "total": len(rows),
        "solved": sum(1 for r in rows if r["solved"]),
        "matched": matched,
        "accuracy": round(matched / total, 4),
        "by_level": by_level,
        "by_reason": by_reason,
        "rows": rows,
    }


def gate_verdict(accuracy: float, floor: float, target: float, stage: str) -> str:
    verdict = "HOLD (shadow only)" if accuracy >= floor and accuracy < target else (
        "PASS -> owner canary review" if accuracy >= target else "REJECT (below floor)")
    return f"GATE[{stage}]: accuracy={accuracy:.2%} floor={floor:.2%} target={target:.2%} -> {verdict}"


def summary_payload(scored: dict, stage: str) -> dict:
    return {
        "mode": stage,
        "total": scored["total"],
        "solved": scored["solved"],
        "matched": scored["matched"],
        "accuracy": scored["accuracy"],
        "by_reason": scored["by_reason"],
    }


def brief_scores(s: dict) -> dict:
    return {"accuracy": s["accuracy"], "matched": s["matched"], "solved": s["solved"],
            "total": s["total"], "by_reason": s["by_reason"]}
