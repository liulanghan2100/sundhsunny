# -*- coding: utf-8 -*-
"""Trace Observability MCP server.

It records project execution as JSONL traces so manual-gates, hooks, workflow
runtime, and memory can be audited through one timeline.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.state import safe_project
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
TRACE_ROOT = DATA_ROOT / "09_投研" / "trace_observability"


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _project_dir(project: str) -> Path:
    return TRACE_ROOT / _safe_project(project)


def _trace_path(project: str) -> Path:
    return _project_dir(project) / "trace.jsonl"


def _append(project: str, event: dict) -> dict:
    rec = {
        "event_id": f"trace-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": shared_now(),
        "project": project,
        **event,
    }
    shared_append_jsonl(_trace_path(project), rec)
    return rec


def _read(project: str) -> list[dict]:
    path = _trace_path(project)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"event_type": "corrupt_line", "raw": line})
    return records


def _last_open_trace(records: list[dict]) -> str:
    open_ids: list[str] = []
    closed_ids: set[str] = set()
    for rec in records:
        if rec.get("event_type") == "trace_start":
            open_ids.append(rec.get("trace_id", ""))
        elif rec.get("event_type") == "trace_end":
            closed_ids.add(rec.get("trace_id", ""))
    for trace_id in reversed(open_ids):
        if trace_id and trace_id not in closed_ids:
            return trace_id
    return open_ids[-1] if open_ids else ""


def _duration_seconds(start: str, end: str) -> float | None:
    try:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        return round((e - s).total_seconds(), 3)
    except (TypeError, ValueError):
        return None


def _trace_summary(records: list[dict]) -> dict:
    traces = {}
    spans = {}
    event_counts = {}
    failures = []
    for rec in records:
        typ = rec.get("event_type", "unknown")
        event_counts[typ] = event_counts.get(typ, 0) + 1
        trace_id = rec.get("trace_id")
        span_id = rec.get("span_id")
        if trace_id:
            traces.setdefault(trace_id, {"trace_id": trace_id, "events": 0, "status": "open"})
            traces[trace_id]["events"] += 1
            if typ == "trace_start":
                traces[trace_id]["started_at"] = rec.get("ts")
                traces[trace_id]["task"] = rec.get("task")
            if typ == "trace_end":
                traces[trace_id]["status"] = rec.get("status", "ended")
                traces[trace_id]["ended_at"] = rec.get("ts")
                traces[trace_id]["summary"] = rec.get("summary")
        if span_id:
            spans.setdefault(span_id, {"span_id": span_id, "trace_id": trace_id, "status": "open"})
            if typ == "span_start":
                spans[span_id].update({
                    "name": rec.get("name"),
                    "kind": rec.get("kind"),
                    "started_at": rec.get("ts"),
                })
            if typ == "span_end":
                spans[span_id].update({
                    "status": rec.get("status", "ended"),
                    "ended_at": rec.get("ts"),
                    "result": rec.get("result"),
                })
        if rec.get("status") in {"failed", "error", "revoked"} or typ == "failure":
            failures.append(rec)
    for span in spans.values():
        span["duration_seconds"] = _duration_seconds(span.get("started_at"), span.get("ended_at"))
    for trace in traces.values():
        trace["duration_seconds"] = _duration_seconds(trace.get("started_at"), trace.get("ended_at"))
    return {
        "trace_count": len(traces),
        "span_count": len(spans),
        "event_count": len(records),
        "event_counts": event_counts,
        "open_traces": [t for t in traces.values() if t.get("status") == "open"],
        "failed_events": failures,
        "traces": list(traces.values()),
        "spans": list(spans.values()),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("trace-observability-mcp")

    @mcp.tool()
    def trace_brief() -> str:
        """Describe trace observability capabilities."""
        return _json({
            "name": "trace-observability-mcp",
            "purpose": "record task, decision, tool, gate, result, failure, and lesson events in one audit timeline",
            "storage_root": str(TRACE_ROOT),
            "default_file": "09_投研/trace_observability/<project>/trace.jsonl",
            "tools": [
                "trace_brief",
                "start_trace",
                "end_trace",
                "start_span",
                "end_span",
                "record_event",
                "trace_report",
                "project_trace_stats",
                "export_trace",
            ],
        })

    @mcp.tool()
    def start_trace(project: str, task: str, manual_project: str = "",
                    node_id: int = 0, metadata_json: str = "{}") -> str:
        """Start an auditable execution trace."""
        trace_id = f"{_safe_project(project)}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        rec = _append(project, {
            "event_type": "trace_start",
            "trace_id": trace_id,
            "task": task,
            "manual_project": manual_project,
            "node_id": node_id,
            "metadata": _loads(metadata_json, {}),
        })
        return _json({"status": "started", "trace_id": trace_id, "path": str(_trace_path(project)), "record": rec})

    @mcp.tool()
    def end_trace(project: str, trace_id: str, status: str = "completed",
                  summary: str = "", lessons_json: str = "[]") -> str:
        """End an execution trace."""
        rec = _append(project, {
            "event_type": "trace_end",
            "trace_id": trace_id,
            "status": status,
            "summary": summary,
            "lessons": _loads(lessons_json, []),
        })
        return _json({"status": "ended", "trace_id": trace_id, "record": rec})

    @mcp.tool()
    def start_span(project: str, trace_id: str, name: str, kind: str = "tool",
                   parent_span_id: str = "", metadata_json: str = "{}") -> str:
        """Start a child span under a trace."""
        span_id = f"span-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        rec = _append(project, {
            "event_type": "span_start",
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "name": name,
            "kind": kind,
            "metadata": _loads(metadata_json, {}),
        })
        return _json({"status": "started", "span_id": span_id, "record": rec})

    @mcp.tool()
    def end_span(project: str, trace_id: str, span_id: str, status: str = "completed",
                 result_json: str = "{}", evidence_path: str = "") -> str:
        """End a trace span."""
        rec = _append(project, {
            "event_type": "span_end",
            "trace_id": trace_id,
            "span_id": span_id,
            "status": status,
            "result": _loads(result_json, {}),
            "evidence_path": evidence_path,
        })
        return _json({"status": "ended", "span_id": span_id, "record": rec})

    @mcp.tool()
    def record_event(project: str, event_type: str, trace_id: str = "",
                     span_id: str = "", node_id: int = 0, message: str = "",
                     data_json: str = "{}") -> str:
        """Record an arbitrary trace event."""
        if not trace_id:
            trace_id = _last_open_trace(_read(project))
        rec = _append(project, {
            "event_type": event_type,
            "trace_id": trace_id,
            "span_id": span_id,
            "node_id": node_id,
            "message": message,
            "data": _loads(data_json, {}),
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def trace_report(project: str, trace_id: str = "", limit: int = 50) -> str:
        """Return a readable trace report."""
        records = _read(project)
        if trace_id:
            records = [r for r in records if r.get("trace_id") == trace_id]
        selected = records[-limit:] if limit > 0 else records
        summary = _trace_summary(records)
        return _json({
            "project": project,
            "trace_id": trace_id or "all",
            "path": str(_trace_path(project)),
            "summary": {k: v for k, v in summary.items() if k not in {"traces", "spans", "failed_events"}},
            "failures": summary["failed_events"][-10:],
            "events": selected,
        })

    @mcp.tool()
    def project_trace_stats(project: str) -> str:
        """Return project-level observability metrics."""
        records = _read(project)
        summary = _trace_summary(records)
        total_spans = max(summary["span_count"], 1)
        failed_span_count = sum(1 for s in summary["spans"] if s.get("status") in {"failed", "error", "revoked"})
        return _json({
            "project": project,
            "path": str(_trace_path(project)),
            "trace_count": summary["trace_count"],
            "span_count": summary["span_count"],
            "event_count": summary["event_count"],
            "failed_span_rate": round(failed_span_count / total_spans, 4),
            "event_counts": summary["event_counts"],
            "open_trace_count": len(summary["open_traces"]),
        })

    @mcp.tool()
    def export_trace(project: str, output_path: str = "") -> str:
        """Export JSONL trace records as a JSON report."""
        records = _read(project)
        summary = _trace_summary(records)
        out = Path(output_path) if output_path else _project_dir(project) / "trace_export.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"project": project, "source": str(_trace_path(project)), "summary": summary, "events": records}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "exported", "path": str(out), "event_count": len(records)})

    return mcp


def main() -> None:
    build_server().run()

