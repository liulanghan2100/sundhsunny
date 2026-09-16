# -*- coding: utf-8 -*-
"""Pure helpers for trajectory replay page generation."""
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value)).strip("-").lower()
    return safe or "_empty"


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
            rows.append({"schema_version": "corrupt-line", "raw": line})
    return rows


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
  <header><h1>{html.escape(title)}</h1><div>Read-only replay generated {html.escape(now())}</div></header>
  <main>
    <p><a href="{html.escape(back)}">Back to dashboard</a></p>
    {body}
  </main>
</body>
</html>
"""


def trajectory_detail_html(row: dict, source_payload) -> str:
    outcome = row.get("outcome") or {}
    summary_rows = [[
        html.escape(str(row.get("trajectory_id", ""))),
        html.escape(str(row.get("source_type", ""))),
        html.escape(str(row.get("capability", ""))),
        html.escape(str((row.get("input") or {}).get("task_class", ""))),
        html.escape(str(outcome.get("label", ""))),
        html.escape(str(outcome.get("category", ""))),
    ]]
    body = f"""
    <section><h2>Replay Summary</h2>{table(["Trajectory", "Source", "Capability", "Task Class", "Outcome", "Category"], summary_rows)}</section>
    <section><h2>Trajectory</h2><pre>{html.escape(json.dumps(row, ensure_ascii=False, indent=2))}</pre></section>
    <section><h2>Source Evidence</h2><pre>{html.escape(json.dumps(source_payload, ensure_ascii=False, indent=2))}</pre></section>
    """
    return page(str(row.get("trajectory_id", "trajectory")), body, "../../index.html")


def bucket_page(bucket: str, key: str, refs: list[dict]) -> str:
    table_rows = []
    for ref in refs:
        trajectory_id = ref.get("trajectory_id", "")
        detail = f"../trajectory/{safe_name(trajectory_id)}.html"
        table_rows.append([
            f"<a href=\"{html.escape(detail)}\">{html.escape(trajectory_id)}</a>",
            html.escape(str(ref.get("source_type", ""))),
            html.escape(str(ref.get("capability", ""))),
            html.escape(str(ref.get("task_class", ""))),
            html.escape(str(ref.get("label", ""))),
            html.escape(str(ref.get("category", ""))),
            str(ref.get("line", "")),
        ])
    body = f"""
    <section><h2>Selection</h2><p><span class="badge">{html.escape(bucket)}</span> {html.escape(key)} · <span class="badge">matches</span> {len(refs)}</p></section>
    <section><h2>Trajectories</h2>{table(["Trajectory", "Source", "Capability", "Task Class", "Outcome", "Category", "Line"], table_rows or [["None", "", "", "", "", "", ""]])}</section>
    """
    return page(f"{bucket}: {key}", body, "../../index.html")


def source_payload(row: dict, read_json_fn=read_json) -> dict:
    source_path = row.get("source_path", "")
    path = Path(source_path) if source_path else Path()
    if not path.exists():
        return {"status": "missing_source", "path": source_path}
    if path.suffix.lower() == ".jsonl":
        return {"status": "jsonl_source", "path": source_path, "line": (row.get("replay") or {}).get("line")}
    return read_json_fn(path, {"status": "unreadable_source", "path": source_path})


def refs_for_bucket(index: dict, bucket: str, key: str) -> list[dict]:
    if bucket == "by_trajectory_id":
        ref = (index.get(bucket) or {}).get(key)
        return [ref] if isinstance(ref, dict) else []
    return list((index.get(bucket) or {}).get(key, []))


def replay_summary(schema_version: str, row_count: int, detail_count: int,
                   bucket_counts: dict, replay_dir: str, audit_path: str) -> dict:
    return {
        "schema_version": schema_version,
        "generated": now(),
        "read_only": True,
        "trajectory_count": row_count,
        "detail_count": detail_count,
        "bucket_counts": bucket_counts,
        "dashboard_replay_dir": replay_dir,
        "audit_path": audit_path,
        "no_registry_mutation": True,
        "no_task_state_mutation": True,
    }
