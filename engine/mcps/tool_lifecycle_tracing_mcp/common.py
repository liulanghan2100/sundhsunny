# -*- coding: utf-8 -*-
"""Tool Lifecycle Tracing MCP server.

v6.5 adds a normalized lifecycle schema for tool calls and resource IO:
tool_start -> resource_read/resource_write/event -> tool_end/tool_error.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.state import safe_project

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
TRACE_ROOT = DATA_ROOT / "09_投研" / "tool_lifecycle_tracing"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _project_dir(project: str) -> Path:
    return TRACE_ROOT / _safe_project(project)


def _trace_file(project: str) -> Path:
    return _project_dir(project) / "tool_lifecycle.jsonl"


def _append(project: str, record: dict) -> dict:
    _project_dir(project).mkdir(parents=True, exist_ok=True)
    rec = {
        "event_id": f"tooltrace-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        **record,
    }
    with _trace_file(project).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _read(project: str) -> list[dict]:
    path = _trace_file(project)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"event_type": "corrupt_line", "raw": line})
    return rows


def _duration(start: str, end: str) -> float | None:
    try:
        return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 4)
    except Exception:
        return None


def _call_id(tool_name: str) -> str:
    safe = "".join(c for c in tool_name if c.isalnum() or c in "-_.") or "tool"
    return f"{safe}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def _summary(records: list[dict]) -> dict:
    calls: dict[str, dict] = {}
    event_counts: dict[str, int] = {}
    resource_reads = 0
    resource_writes = 0
    for rec in records:
        typ = rec.get("event_type", "unknown")
        event_counts[typ] = event_counts.get(typ, 0) + 1
        call_id = rec.get("call_id")
        if call_id:
            calls.setdefault(call_id, {
                "call_id": call_id,
                "tool_name": rec.get("tool_name", ""),
                "status": "open",
                "events": 0,
                "resources": [],
            })
            calls[call_id]["events"] += 1
            if rec.get("tool_name"):
                calls[call_id]["tool_name"] = rec.get("tool_name")
            if typ == "tool_start":
                calls[call_id]["started_at"] = rec.get("ts")
                calls[call_id]["input_hash"] = rec.get("input_hash", "")
            elif typ == "tool_end":
                calls[call_id]["status"] = rec.get("status", "completed")
                calls[call_id]["ended_at"] = rec.get("ts")
                calls[call_id]["output_hash"] = rec.get("output_hash", "")
            elif typ == "tool_error":
                calls[call_id]["status"] = "error"
                calls[call_id]["ended_at"] = rec.get("ts")
                calls[call_id]["error"] = rec.get("error", "")
            elif typ in {"resource_read", "resource_write"}:
                calls[call_id]["resources"].append({
                    "event_type": typ,
                    "path": rec.get("resource_path", ""),
                    "bytes": rec.get("bytes", 0),
                })
        if typ == "resource_read":
            resource_reads += 1
        if typ == "resource_write":
            resource_writes += 1
    for call in calls.values():
        call["duration_seconds"] = _duration(call.get("started_at"), call.get("ended_at"))
    open_calls = [c for c in calls.values() if c.get("status") == "open"]
    errors = [c for c in calls.values() if c.get("status") == "error"]
    total = max(len(calls), 1)
    return {
        "tool_call_count": len(calls),
        "event_count": len(records),
        "event_counts": event_counts,
        "open_call_count": len(open_calls),
        "error_count": len(errors),
        "error_rate": round(len(errors) / total, 4),
        "resource_reads": resource_reads,
        "resource_writes": resource_writes,
        "open_calls": open_calls,
        "errors": errors,
        "calls": list(calls.values()),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("tool-lifecycle-tracing-mcp")

    @mcp.tool()
    def tool_lifecycle_brief() -> str:
        """Describe tool lifecycle tracing."""
        return _json({
            "name": "tool-lifecycle-tracing-mcp",
            "version": "v6.5",
            "purpose": "记录工具调用开始、结束、错误和资源读写，形成可审计生命周期",
            "storage": str(TRACE_ROOT),
            "events": ["tool_start", "tool_end", "tool_error", "resource_read", "resource_write", "tool_event"],
        })

    @mcp.tool()
    def tool_start(project: str, tool_name: str, task: str = "", trace_id: str = "",
                   input_hash: str = "", metadata_json: str = "{}") -> str:
        """Record tool call start."""
        call_id = _call_id(tool_name)
        rec = _append(project, {
            "event_type": "tool_start",
            "call_id": call_id,
            "trace_id": trace_id,
            "tool_name": tool_name,
            "task": task,
            "input_hash": input_hash,
            "metadata": _loads(metadata_json, {}),
        })
        return _json({"status": "started", "call_id": call_id, "record": rec, "path": str(_trace_file(project))})

    @mcp.tool()
    def tool_end(project: str, call_id: str, tool_name: str = "", status: str = "completed",
                 output_hash: str = "", result_json: str = "{}") -> str:
        """Record tool call completion."""
        rec = _append(project, {
            "event_type": "tool_end",
            "call_id": call_id,
            "tool_name": tool_name,
            "status": status,
            "output_hash": output_hash,
            "result": _loads(result_json, {}),
        })
        return _json({"status": "ended", "call_id": call_id, "record": rec})

    @mcp.tool()
    def tool_error(project: str, call_id: str, error: str, tool_name: str = "",
                   error_type: str = "runtime_error", recoverable: bool = True) -> str:
        """Record tool call error."""
        rec = _append(project, {
            "event_type": "tool_error",
            "call_id": call_id,
            "tool_name": tool_name,
            "error_type": error_type,
            "error": error,
            "recoverable": recoverable,
        })
        return _json({"status": "error_recorded", "call_id": call_id, "record": rec})

    @mcp.tool()
    def resource_read(project: str, call_id: str, resource_path: str, tool_name: str = "",
                      bytes: int = 0, purpose: str = "") -> str:
        """Record a resource read under a tool call."""
        rec = _append(project, {
            "event_type": "resource_read",
            "call_id": call_id,
            "tool_name": tool_name,
            "resource_path": resource_path,
            "bytes": bytes,
            "purpose": purpose,
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def resource_write(project: str, call_id: str, resource_path: str, tool_name: str = "",
                       bytes: int = 0, purpose: str = "") -> str:
        """Record a resource write under a tool call."""
        rec = _append(project, {
            "event_type": "resource_write",
            "call_id": call_id,
            "tool_name": tool_name,
            "resource_path": resource_path,
            "bytes": bytes,
            "purpose": purpose,
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def tool_event(project: str, call_id: str, event_name: str, tool_name: str = "",
                   data_json: str = "{}") -> str:
        """Record an arbitrary tool lifecycle event."""
        rec = _append(project, {
            "event_type": "tool_event",
            "call_id": call_id,
            "tool_name": tool_name,
            "event_name": event_name,
            "data": _loads(data_json, {}),
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def lifecycle_report(project: str, limit: int = 50) -> str:
        """Return recent lifecycle events and summary."""
        records = _read(project)
        summary = _summary(records)
        return _json({
            "project": project,
            "path": str(_trace_file(project)),
            "summary": {k: v for k, v in summary.items() if k != "calls"},
            "events": records[-limit:] if limit > 0 else records,
        })

    @mcp.tool()
    def lifecycle_stats(project: str) -> str:
        """Return lifecycle metrics."""
        return _json({"project": project, "path": str(_trace_file(project)), **_summary(_read(project))})

    @mcp.tool()
    def verify_lifecycle_integrity(project: str) -> str:
        """Verify that tool calls have valid start/end or start/error pairs."""
        summary = _summary(_read(project))
        passed = summary["open_call_count"] == 0
        return _json({
            "project": project,
            "passed": passed,
            "open_call_count": summary["open_call_count"],
            "error_count": summary["error_count"],
            "error_rate": summary["error_rate"],
            "open_calls": summary["open_calls"],
            "required_action": "close or mark open tool calls as error" if not passed else "none",
        })

    return mcp


def main() -> None:
    build_server().run()
