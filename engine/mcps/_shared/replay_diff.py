# -*- coding: utf-8 -*-
"""Pure helpers for replay diff analysis."""
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value)).strip("-").lower()
    return safe or "_empty"


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
            rows.append({"schema_version": "corrupt-line", "raw": line})
    return rows


def outcome(row: dict) -> dict:
    return row.get("outcome") or {}


def is_success(row: dict) -> bool:
    out = outcome(row)
    return bool(out.get("is_success")) or out.get("category") in {"success", "active_canary"} or out.get("label") in {"shadow_pass_agreement"}


def failure_key(row: dict) -> str:
    out = outcome(row)
    if out.get("is_success"):
        return ""
    category = str(out.get("category", "unknown"))
    label = str(out.get("label", "unknown"))
    reason = str(out.get("reason", ""))
    return f"{category}:{label}:{reason}"


def is_expected_failure(row: dict) -> bool:
    return bool(outcome(row).get("is_expected_failure"))


def is_shadow_warning(row: dict) -> bool:
    return outcome(row).get("label") == "shadow_warn_findings"


def is_verifier_failure(row: dict) -> bool:
    return bool(outcome(row).get("is_verifier_failure"))


def is_retry(row: dict) -> bool:
    return bool(outcome(row).get("is_retry"))


def is_unknown(row: dict) -> bool:
    return outcome(row).get("category") == "unknown"


def path_signature(row: dict) -> str:
    execution = row.get("execution") or {}
    if row.get("source_type") == "runstate":
        checks = execution.get("checks") or []
        check_names = [str(check.get("name", "")) for check in checks if isinstance(check, dict)]
        return "runstate|" + "|".join(check_names or [str(execution.get("phase", ""))])
    if row.get("source_type") == "shadow_run":
        return f"shadow|{execution.get('mode', '')}|{execution.get('shadow_result', '')}|findings:{len(execution.get('findings') or [])}"
    if row.get("source_type") == "owner_review":
        return f"owner_review|{execution.get('review_status', '')}|can_apply:{execution.get('can_apply', False)}"
    if row.get("source_type") == "active_canary":
        return f"active_canary|{execution.get('status', '')}|rollback:{outcome(row).get('rollback_signal', False)}"
    return str(row.get("source_type", "unknown"))


def common_checks(rows: list[dict]) -> list[str]:
    check_sets = []
    for row in rows:
        checks = ((row.get("execution") or {}).get("checks") or [])
        names = {str(check.get("name", "")) for check in checks if isinstance(check, dict) and check.get("name")}
        if names:
            check_sets.append(names)
    if not check_sets:
        return []
    return sorted(set.intersection(*check_sets))


def group_rows(rows: list[dict], bucket: str) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        out = outcome(row)
        if bucket == "capability":
            key = row.get("capability", "")
        elif bucket == "outcome_category":
            key = out.get("category", "")
        elif bucket == "outcome_label":
            key = out.get("label", "")
        elif bucket == "source_type":
            key = row.get("source_type", "")
        else:
            key = ""
        grouped[str(key or "_empty")].append(row)
    return dict(grouped)


def assess_group(total, success_count, failure_count, expected_count, warning_count,
                 verifier_count, retry_count, unknown_count, operational_failure_count,
                 stable_count, top_failure_count) -> str:
    if total == 0:
        return "empty"
    if total >= 3 and success_count == total:
        return "stable_success_path"
    if failure_count == total and expected_count == failure_count:
        return "stable_fail_closed_pattern"
    if failure_count == total and warning_count == failure_count:
        return "shadow_warning_pattern"
    if verifier_count >= 2:
        return "repeat_verifier_failure"
    if retry_count >= 2:
        return "repeat_retry_pattern"
    if unknown_count >= 2:
        return "repeat_unknown_state"
    if warning_count >= 2 and success_count:
        return "mixed_shadow_warning_pattern"
    if operational_failure_count >= 2 and top_failure_count >= 2:
        return "repeat_failure_pattern"
    if success_count and failure_count:
        return "mixed_outcomes"
    if failure_count == total:
        return "all_failure_or_fail_closed"
    if stable_count == 1:
        return "single_sample"
    return "observe_more"


def analyze_group(bucket: str, key: str, rows: list[dict]) -> dict:
    success_rows = [row for row in rows if is_success(row)]
    failure_rows = [row for row in rows if not is_success(row)]
    expected_rows = [row for row in failure_rows if is_expected_failure(row)]
    warning_rows = [row for row in failure_rows if is_shadow_warning(row)]
    verifier_rows = [row for row in failure_rows if is_verifier_failure(row)]
    retry_rows = [row for row in failure_rows if is_retry(row)]
    unknown_rows = [row for row in failure_rows if is_unknown(row)]
    operational_failure_count = len(failure_rows) - len(expected_rows) - len(warning_rows)
    path_counts = Counter(path_signature(row) for row in success_rows)
    failure_counts = Counter(failure_key(row) for row in failure_rows if failure_key(row))
    operational_counts = Counter(
        failure_key(row)
        for row in failure_rows
        if failure_key(row) and not is_expected_failure(row) and not is_shadow_warning(row)
    )
    source_counts = Counter(str(row.get("source_type", "")) for row in rows)
    label_counts = Counter(str(outcome(row).get("label", "")) for row in rows)
    stable_path, stable_count = path_counts.most_common(1)[0] if path_counts else ("", 0)
    top_failure, failure_count = failure_counts.most_common(1)[0] if failure_counts else ("", 0)
    top_operational, operational_count = operational_counts.most_common(1)[0] if operational_counts else ("", 0)
    return {
        "bucket": bucket,
        "key": key,
        "trajectory_count": len(rows),
        "success_count": len(success_rows),
        "failure_count": len(failure_rows),
        "expected_fail_closed_count": len(expected_rows),
        "shadow_warning_count": len(warning_rows),
        "verifier_failure_count": len(verifier_rows),
        "retry_count": len(retry_rows),
        "unknown_count": len(unknown_rows),
        "operational_failure_count": operational_failure_count,
        "success_rate": round(len(success_rows) / len(rows), 4) if rows else 0,
        "stable_success_path": stable_path,
        "stable_success_path_count": stable_count,
        "top_failure_pattern": top_failure,
        "top_failure_count": failure_count,
        "top_operational_pattern": top_operational,
        "top_operational_count": operational_count,
        "common_checks": common_checks(rows),
        "source_counts": dict(source_counts),
        "label_counts": dict(label_counts),
        "trajectory_ids": [row.get("trajectory_id", "") for row in rows],
        "assessment": assess_group(
            len(rows), len(success_rows), len(failure_rows), len(expected_rows), len(warning_rows),
            len(verifier_rows), len(retry_rows), len(unknown_rows), operational_failure_count,
            stable_count, failure_count,
        ),
    }


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def page(title: str, body: str, back: str = "../index.html") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: #f6f7f9; color: #1f2937; }}
    header {{ padding: 20px 28px; background: #102a43; color: white; }}
    main {{ padding: 20px 28px 40px; max-width: 1280px; margin: 0 auto; }}
    section {{ background: white; border: 1px solid #d7dce3; border-radius: 8px; padding: 16px; margin: 14px 0; overflow: auto; }}
    h1 {{ margin: 0 0 6px; font-size: 22px; }}
    h2 {{ margin: 0 0 10px; font-size: 17px; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 780px; }}
    th, td {{ border-bottom: 1px solid #d7dce3; text-align: left; padding: 9px 10px; font-size: 13px; vertical-align: top; }}
    th {{ background: #f9fafb; color: #344054; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f9fafb; border: 1px solid #d7dce3; border-radius: 6px; padding: 12px; font-size: 12px; }}
    a {{ color: #0f766e; }}
    .badge {{ display: inline-block; padding: 2px 7px; border-radius: 999px; background: #e6fffb; color: #0f766e; border: 1px solid #99f6e4; }}
  </style>
</head>
<body>
  <header><h1>{html.escape(title)}</h1><div>Read-only replay diff generated {html.escape(now())}</div></header>
  <main>
    <p><a href="{html.escape(back)}">Back to dashboard</a></p>
    {body}
  </main>
</body>
</html>
"""


def diff_page(group: dict) -> str:
    replay_base = "../trajectory_replay/trajectory"
    ids = group.get("trajectory_ids") or []
    rows = [[
        f"<a href=\"{html.escape(replay_base + '/' + safe_name(tid) + '.html')}\">{html.escape(tid)}</a>",
    ] for tid in ids]
    body = f"""
    <section><h2>Group</h2>
      <p><span class="badge">{html.escape(str(group.get("bucket", "")))}</span> {html.escape(str(group.get("key", "")))} · <span class="badge">assessment</span> {html.escape(str(group.get("assessment", "")))}</p>
      {table(["Total", "Success", "Failure", "Expected Fail-Closed", "Shadow Warnings", "Verifier Failures", "Retry", "Unknown", "Operational Failures", "Success Rate"], [[str(group.get("trajectory_count", 0)), str(group.get("success_count", 0)), str(group.get("failure_count", 0)), str(group.get("expected_fail_closed_count", 0)), str(group.get("shadow_warning_count", 0)), str(group.get("verifier_failure_count", 0)), str(group.get("retry_count", 0)), str(group.get("unknown_count", 0)), str(group.get("operational_failure_count", 0)), str(group.get("success_rate", 0))]])}
    </section>
    <section><h2>Stable Success Path</h2><pre>{html.escape(str(group.get("stable_success_path", "")))}</pre></section>
    <section><h2>Operational Pattern</h2><pre>{html.escape(str(group.get("top_operational_pattern", "")))}</pre></section>
    <section><h2>Most Common Non-Success Pattern</h2><pre>{html.escape(str(group.get("top_failure_pattern", "")))}</pre></section>
    <section><h2>Common Checks</h2><pre>{html.escape(json.dumps(group.get("common_checks", []), ensure_ascii=False, indent=2))}</pre></section>
    <section><h2>Label Counts</h2><pre>{html.escape(json.dumps(group.get("label_counts", {}), ensure_ascii=False, indent=2))}</pre></section>
    <section><h2>Trajectories</h2>{table(["Trajectory"], rows or [["None"]])}</section>
    """
    return page(f"Replay Diff: {group.get('bucket')} / {group.get('key')}", body, "../index.html")
