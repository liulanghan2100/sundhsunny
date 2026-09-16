# -*- coding: utf-8 -*-
"""Pure helpers for the GAIA grader."""
import json
import re
from datetime import datetime, timezone


INDUSTRY_REFERENCE = {
    "best_agent_gaia": 0.7455,
    "bare_model": 0.523,
    "human": 0.92,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\bst\b", "saint", text)
    text = text.replace(" and ", " ").strip()
    return text


def first_number(text: str) -> str | None:
    m = re.search(r"\d+(?:\.\d+)?", text or "")
    return m.group(0) if m else None


NUMBER_WORDS = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000, "trillion": 1_000_000_000_000}


def expand_number_words(text: str) -> str:
    def rep(m):
        try:
            return str(float(m.group(1).replace(",", "")) * NUMBER_WORDS[m.group(2).lower()])
        except Exception:
            return m.group(0)

    return re.sub(r"(\d[\d,.]*)\s*(thousand|million|billion|trillion)\b", rep, text or "", flags=re.IGNORECASE)


def exact_match(predicted: str, ground_truth: str) -> bool:
    if "FINAL ANSWER:" in predicted:
        predicted = predicted.split("FINAL ANSWER:", 1)[1].strip()
    norm_pred, norm_truth = normalize(predicted), normalize(ground_truth)
    if norm_pred == norm_truth:
        return True
    truth_num = first_number(ground_truth)
    if truth_num is not None and normalize(ground_truth) == normalize(truth_num):
        pred_num = first_number(expand_number_words(predicted)) or first_number(predicted)
        if pred_num is not None:
            if pred_num == truth_num:
                return True
            try:
                if float(pred_num) == float(truth_num):
                    return True
            except ValueError:
                pass
            try:
                p, t = float(pred_num), float(truth_num)
                if t != 0 and abs(p - t) / abs(t) < 1e-3:
                    return True
            except ValueError:
                pass
    if len(norm_truth) >= 4 and norm_truth in norm_pred:
        return True
    if len(norm_pred) >= 4 and norm_pred in norm_truth:
        return True
    return False


def load_index(index_path) -> dict:
    if not index_path.exists():
        raise FileNotFoundError(f"GAIA index missing: {index_path}")
    return json.loads(index_path.read_text(encoding="utf-8"))


def ground_truths(index: dict, split: str) -> dict[str, str]:
    return {row["task_id"]: row.get("final_answer", "") for row in index.get(split, [])}


def load_runs(runs_dir) -> dict[str, dict]:
    runs = {}
    if runs_dir.exists():
        for path in runs_dir.glob("*/run.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                runs[data["task_id"]] = data
            except Exception:
                continue
    return runs


def failure_reason(run: dict | None, matched: bool) -> str:
    if matched:
        return "correct"
    if not run:
        return "not_run"
    status = run.get("status", "")
    if status == "api_error":
        return "api_error"
    if status == "budget_exceeded":
        return "budget_exceeded"
    steps = run.get("steps", [])
    tool_results = [s.get("result", "") for s in steps if s.get("event") == "tool_call"]
    fail_keys = ("ERROR", "WARNING", "Timeout", "timed out", "failed")
    tool_fails = [r for r in tool_results if any(k in r for k in fail_keys)]
    fail_ratio = len(tool_fails) / len(tool_results) if tool_results else 0.0
    if status == "max_steps_reached":
        return "max_steps_tool_fail" if fail_ratio >= 0.5 else "max_steps"
    if status == "completed":
        if len(run.get("final_answer", "")) > 200:
            return "answer_extraction"
        return "wrong_answer_tool_fail" if fail_ratio >= 0.5 else "wrong_answer"
    return f"status_{status}"


def score(index: dict, runs: dict, split: str) -> dict:
    truths = ground_truths(index, split)
    rows = []
    for task_id, truth in truths.items():
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
            "question": (run.get("question") or "")[:140],
            "predicted": predicted[:140],
            "ground_truth": truth,
        })
    by_level = {}
    for row in rows:
        level = row["level"]
        bucket = by_level.setdefault(level, {"total": 0, "solved": 0, "matched": 0})
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
    solved = sum(1 for r in rows if r["solved"])
    matched = sum(1 for r in rows if r["matched"] is True)
    return {
        "schema_version": "agent-os-gaia-leaderboard/v0.2",
        "generated": now(),
        "split": split,
        "total": len(rows),
        "solved": solved,
        "matched": matched,
        "accuracy": round(matched / total, 4) if total else 0.0,
        "by_level": by_level,
        "by_reason": by_reason,
        "industry_reference": INDUSTRY_REFERENCE,
        "rows": rows,
    }


def render_markdown(result: dict) -> str:
    lines = [
        "# GAIA Eval Report",
        "",
        f"Generated: {result['generated']}",
        f"Split: **{result['split']}**",
        "",
        "## Status",
        "",
        f"- Total questions: `{result['total']}`",
        f"- Solved: `{result['solved']}`",
        f"- Exact-match: `{result['matched']}`",
        f"- **Accuracy: {result['accuracy']:.2%}**",
        "",
        "## By Level",
        "",
        "| Level | Total | Solved | Matched | Rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for level in sorted(result["by_level"]):
        b = result["by_level"][level]
        rate = f"{b['matched'] / b['total']:.2%}" if b["total"] else "-"
        lines.append(f"| {level} | {b['total']} | {b['solved']} | {b['matched']} | {rate} |")
    lines += ["", "## Failure Reasons", "", "| Reason | Count | Meaning |", "|---|---:|---|"]
    reason_labels = {
        "correct": "correct",
        "not_run": "not run",
        "api_error": "api/network error",
        "budget_exceeded": "token budget exceeded",
        "max_steps": "max steps exceeded",
        "max_steps_tool_fail": "max steps with tool failures",
        "answer_extraction": "answer extraction failure",
        "wrong_answer_tool_fail": "wrong answer with tool failures",
        "wrong_answer": "wrong answer",
    }
    for reason in sorted(result.get("by_reason", {})):
        lines.append(f"| {reason} | {result['by_reason'][reason]} | {reason_labels.get(reason, '-')} |")
    lines += [
        "",
        "## Per Question",
        "",
        "| # | Level | Status | Solved | Match | Reason | Question | Answer (pred/truth) |",
        "|---|---:|---|---:|---:|---|---|---|---|",
    ]
    for i, row in enumerate(result["rows"], 1):
        q = (row.get("question") or "").replace("|", "\\|")
        pred = (row.get("predicted") or "").replace("|", "\\|")
        truth = (row.get("ground_truth") or "").replace("|", "\\|")
        solved = "Y" if row["solved"] else "-"
        matched = "Y" if row["matched"] else ("N" if row["matched"] is False else "?")
        lines.append(
            f"| {i} | {row['level']} | {row.get('status', '-')} | {solved} | {matched} "
            f"| {row.get('reason', '-')} | {q[:100]} | `{pred[:40]}` / `{truth[:40]}` |"
        )
    lines += [
        "",
        "## vs Industry (GAIA)",
        "",
        "| Reference | Score |",
        "|---|---|",
    ]
    for label, value in result["industry_reference"].items():
        lines.append(f"| {label} | {value:.2%} |")
    lines += [
        "",
        f"Your Agent OS accuracy: **{result['accuracy']:.2%}** "
        f"(industry best agent {result['industry_reference']['best_agent_gaia']:.2%}, "
        f"human {result['industry_reference']['human']:.2%}).",
        "",
        "> Note: validation split has public answers; test split answers are private. "
        "> For test, accuracy is reported only after official submission.",
        "",
    ]
    return "\n".join(lines)


def failure_reason_label(reason: str) -> str:
    return {
        "correct": "correct",
        "not_run": "not run",
        "api_error": "api/network error",
        "budget_exceeded": "token budget exceeded",
        "max_steps": "max steps exceeded",
        "max_steps_tool_fail": "max steps with tool failures",
        "answer_extraction": "answer extraction failure",
        "wrong_answer_tool_fail": "wrong answer with tool failures",
        "wrong_answer": "wrong answer",
    }.get(reason, '-')


def score_summary(result: dict) -> dict:
    return {
        "total": result["total"],
        "solved": result["solved"],
        "matched": result["matched"],
        "accuracy": result["accuracy"],
        "by_level": result["by_level"],
        "by_reason": result["by_reason"],
        "industry_reference": result["industry_reference"],
    }


def markdown_report(result: dict) -> str:
    lines = [
        "# GAIA Eval Report",
        "",
        f"Generated: {result['generated']}",
        f"Split: **{result['split']}**",
        "",
        "## Status",
        "",
        f"- Total questions: `{result['total']}`",
        f"- Solved: `{result['solved']}`",
        f"- Exact-match: `{result['matched']}`",
        f"- **Accuracy: {result['accuracy']:.2%}**",
        "",
        "## By Level",
        "",
        "| Level | Total | Solved | Matched | Rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for level in sorted(result['by_level']):
        b = result['by_level'][level]
        rate = f"{b['matched'] / b['total']:.2%}" if b['total'] else "-"
        lines.append(f"| {level} | {b['total']} | {b['solved']} | {b['matched']} | {rate} |")
    lines += ["", "## Failure Reasons", "", "| Reason | Count | Meaning |", "|---|---:|---|"]
    for reason in sorted(result.get('by_reason', {})):
        lines.append(f"| {reason} | {result['by_reason'][reason]} | {failure_reason_label(reason)} |")
    lines += [
        "",
        "## Per Question",
        "",
        "| # | Level | Status | Solved | Match | Reason | Question | Answer (pred/truth) |",
        "|---|---:|---|---:|---:|---|---|---|---|",
    ]
    for i, row in enumerate(result['rows'], 1):
        q = (row.get('question') or '').replace('|', '\\|')
        pred = (row.get('predicted') or '').replace('|', '\\|')
        truth = (row.get('ground_truth') or '').replace('|', '\\|')
        solved = 'Y' if row['solved'] else '-'
        matched = 'Y' if row['matched'] else ('N' if row['matched'] is False else '?')
        lines.append(
            f"| {i} | {row['level']} | {row.get('status', '-')} | {solved} | {matched} "
            f"| {row.get('reason', '-')} | {q[:100]} | `{pred[:40]}` / `{truth[:40]}` |"
        )
    lines += [
        "",
        "## vs Industry (GAIA)",
        "",
        "| Reference | Score |",
        "|---|---|",
    ]
    for label, value in result['industry_reference'].items():
        lines.append(f"| {label} | {value:.2%} |")
    lines += [
        "",
        f"Your Agent OS accuracy: **{result['accuracy']:.2%}** "
        f"(industry best agent {result['industry_reference']['best_agent_gaia']:.2%}, "
        f"human {result['industry_reference']['human']:.2%}).",
        "",
        "> Note: validation split has public answers; test split answers are private. "
        "> For test, accuracy is reported only after official submission.",
        "",
    ]
    return "\n".join(lines)
