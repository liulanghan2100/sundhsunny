# -*- coding: utf-8 -*-
"""Agent Runtime Kernel MCP server.

This is the coordinator layer for the manual-agent OS. It does not bypass
manual-gates. It turns a task into a resumable execution plan that points to
the right MCPs, checkpoints, traces, and handoffs.
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

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
RUNTIME_ROOT = DATA_ROOT / "09_投研" / "agent_runtime_kernel"
QUICK_NODES = [4, 9, 17, 19, 24]
STANDARD_NODES = [1, 2, 3, 4, 5, 27, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 26, 22, 23, 24, 25]

NODE_ACTIONS = {
    4: {
        "name": "scope",
        "agent": "planning-agent",
        "mcp_calls": [
            "manual-gates.set_mode",
            "workflow-runtime.create_workflow",
            "trace-observability.start_trace",
        ],
        "exit_evidence": "MVP scope and success criteria recorded",
    },
    9: {
        "name": "contract",
        "agent": "planning-agent",
        "mcp_calls": [
            "auto-trigger.evaluate_task",
            "experience-memory.semantic_search_memory",
            "trace-observability.record_event",
        ],
        "exit_evidence": "interfaces, data shape, and orchestration contract recorded",
    },
    17: {
        "name": "verify",
        "agent": "dev-agent",
        "mcp_calls": [
            "trace-observability.start_span",
            "local smoke test",
            "workflow-runtime.checkpoint_step",
            "manual-gates.submit_check",
        ],
        "exit_evidence": "smoke test or equivalent verification passed",
    },
    19: {
        "name": "evaluate",
        "agent": "qa-agent",
        "mcp_calls": [
            "trace-observability.trace_report",
            "agent-orchestration.review_matrix",
            "manual-gates.submit_check",
        ],
        "exit_evidence": "value boundary and residual risk recorded",
    },
    24: {
        "name": "retro",
        "agent": "memory-agent",
        "mcp_calls": [
            "experience-memory.record_lesson",
            "manual-gates.gate_report",
            "trace-observability.end_trace",
            "backup archive",
        ],
        "exit_evidence": "retro, learning, gate report, and backup completed",
    },
}


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _runtime_dir(project: str) -> Path:
    return RUNTIME_ROOT / _safe_project(project)


def _runtime_path(project: str) -> Path:
    return _runtime_dir(project) / "runtime.json"


def _event(rt: dict, event_type: str, data: dict) -> None:
    rt.setdefault("events", []).append({"ts": _now(), "type": event_type, **data})


def _nodes_for_track(track: str) -> list[int]:
    return QUICK_NODES if track == "quick" else STANDARD_NODES


def _load(project: str) -> dict:
    p = _runtime_path(project)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save(project: str, data: dict) -> dict:
    p = _runtime_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated"] = _now()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _current_node(rt: dict) -> int | None:
    for node_id in rt.get("nodes", []):
        rec = rt.setdefault("node_status", {}).setdefault(str(node_id), {"status": "pending"})
        if rec.get("status") in {"pending", "active", "failed", "reopened"}:
            return int(node_id)
    return None


def _action_for(rt: dict, node_id: int | None) -> dict:
    if node_id is None:
        return {
            "status": "complete",
            "recommended_action": "runtime_stop",
            "mcp_calls": ["manual-gates.gate_report", "trace-observability.end_trace", "backup archive"],
        }
    spec = NODE_ACTIONS.get(node_id, {
        "name": f"node-{node_id}",
        "agent": "planning-agent",
        "mcp_calls": ["manual-gates.plan_next", "workflow-runtime.checkpoint_step"],
        "exit_evidence": "node evidence recorded",
    })
    return {
        "status": "ready",
        "node_id": node_id,
        "node_name": spec["name"],
        "assigned_agent": spec["agent"],
        "recommended_action": "execute_checkpoint",
        "mcp_calls": spec["mcp_calls"],
        "exit_evidence": spec["exit_evidence"],
        "trace_required": True,
        "gate_required": node_id in QUICK_NODES,
    }


def _metrics(rt: dict) -> dict:
    statuses = rt.get("node_status", {})
    total = len(rt.get("nodes", []))
    completed = sum(1 for r in statuses.values() if r.get("status") == "completed")
    failed = sum(1 for r in statuses.values() if r.get("status") in {"failed", "reopened"})
    return {
        "progress": f"{completed}/{total}",
        "completed": completed,
        "failed_or_reopened": failed,
        "event_count": len(rt.get("events", [])),
        "current_node": _current_node(rt),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("agent-runtime-kernel-mcp")

    @mcp.tool()
    def kernel_brief() -> str:
        """Describe the runtime kernel."""
        return _json({
            "name": "agent-runtime-kernel-mcp",
            "purpose": "coordinate manual-gates, auto-trigger, memory, workflow, trace, git-ci, and agent orchestration",
            "storage_root": str(RUNTIME_ROOT),
            "does_not": [
                "does not bypass manual-gates",
                "does not push code or call remote GitHub APIs",
                "does not spawn real parallel agents in v5.3",
            ],
            "tools": [
                "start_task",
                "resume_task",
                "runtime_next_action",
                "execute_checkpoint",
                "runtime_status",
                "runtime_stop",
                "runtime_report",
                "runtime_export",
            ],
        })

    @mcp.tool()
    def start_task(project: str, task: str, manual_project: str = "",
                   track: str = "quick", autonomy: str = "L2",
                   context_json: str = "{}") -> str:
        """Create a runtime task and return the first action plan."""
        nodes = _nodes_for_track(track)
        trace_id = f"{_safe_project(project)}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        rt = {
            "project": project,
            "task": task,
            "manual_project": manual_project or project,
            "track": track,
            "autonomy": autonomy,
            "trace_id": trace_id,
            "created": _now(),
            "updated": _now(),
            "nodes": nodes,
            "node_status": {str(n): {"status": "pending", "checkpoints": []} for n in nodes},
            "context": _loads(context_json, {}),
            "integrations": {
                "manual_gates": True,
                "auto_trigger": True,
                "experience_memory": True,
                "workflow_runtime": True,
                "trace_observability": True,
                "git_ci": True,
                "agent_orchestration": True,
            },
            "events": [],
        }
        _event(rt, "task_started", {"trace_id": trace_id, "task": task, "track": track, "autonomy": autonomy})
        _save(project, rt)
        return _json({"status": "started", "path": str(_runtime_path(project)), "trace_id": trace_id, "next": _action_for(rt, _current_node(rt))})

    @mcp.tool()
    def resume_task(project: str) -> str:
        """Load an existing runtime task and return its next action."""
        rt = _load(project)
        if not rt:
            return _json({"error": f"runtime task not found: {project}"})
        _event(rt, "task_resumed", {"current_node": _current_node(rt)})
        _save(project, rt)
        return _json({"status": "resumed", "metrics": _metrics(rt), "next": _action_for(rt, _current_node(rt))})

    @mcp.tool()
    def runtime_next_action(project: str) -> str:
        """Return the next coordinated action."""
        rt = _load(project)
        if not rt:
            return _json({"error": f"runtime task not found: {project}"})
        return _json({"project": project, "metrics": _metrics(rt), "next": _action_for(rt, _current_node(rt))})

    @mcp.tool()
    def execute_checkpoint(project: str, node_id: int, action: str,
                           evidence_path: str = "", result_json: str = "{}",
                           status: str = "completed") -> str:
        """Record an execution checkpoint and advance the runtime state."""
        rt = _load(project)
        if not rt:
            return _json({"error": f"runtime task not found: {project}"})
        if node_id not in rt.get("nodes", []):
            return _json({"error": f"node {node_id} is not in current runtime track", "nodes": rt.get("nodes", [])})
        rec = rt.setdefault("node_status", {}).setdefault(str(node_id), {"status": "pending", "checkpoints": []})
        checkpoint = {
            "ts": _now(),
            "action": action,
            "evidence_path": evidence_path,
            "result": _loads(result_json, {}),
            "status": status,
            "mcp_calls": NODE_ACTIONS.get(node_id, {}).get("mcp_calls", []),
        }
        rec.setdefault("checkpoints", []).append(checkpoint)
        rec["status"] = status
        if status == "completed":
            rec["completed_at"] = _now()
        _event(rt, "checkpoint", {"node_id": node_id, "action": action, "status": status, "evidence_path": evidence_path})
        _save(project, rt)
        return _json({"status": "checkpointed", "node_id": node_id, "metrics": _metrics(rt), "next": _action_for(rt, _current_node(rt))})

    @mcp.tool()
    def runtime_status(project: str) -> str:
        """Return runtime status."""
        rt = _load(project)
        if not rt:
            return _json({"error": f"runtime task not found: {project}"})
        return _json({
            "project": project,
            "task": rt.get("task"),
            "track": rt.get("track"),
            "autonomy": rt.get("autonomy"),
            "trace_id": rt.get("trace_id"),
            "metrics": _metrics(rt),
            "path": str(_runtime_path(project)),
        })

    @mcp.tool()
    def runtime_stop(project: str, status: str = "completed",
                     summary: str = "", backup_path: str = "") -> str:
        """Close a runtime task."""
        rt = _load(project)
        if not rt:
            return _json({"error": f"runtime task not found: {project}"})
        rt["status"] = status
        rt["summary"] = summary
        rt["backup_path"] = backup_path
        rt["stopped_at"] = _now()
        _event(rt, "task_stopped", {"status": status, "summary": summary, "backup_path": backup_path})
        _save(project, rt)
        return _json({
            "status": "stopped",
            "metrics": _metrics(rt),
            "required_closeout": [
                "manual-gates.gate_report",
                "trace-observability.end_trace",
                "experience-memory.record_lesson",
                "backup archive",
            ],
        })

    @mcp.tool()
    def runtime_report(project: str) -> str:
        """Return a detailed runtime report."""
        rt = _load(project)
        if not rt:
            return _json({"error": f"runtime task not found: {project}"})
        return _json({
            "project": project,
            "path": str(_runtime_path(project)),
            "metrics": _metrics(rt),
            "next": _action_for(rt, _current_node(rt)),
            "integrations": rt.get("integrations", {}),
            "nodes": rt.get("node_status", {}),
            "events": rt.get("events", []),
        })

    @mcp.tool()
    def runtime_export(project: str, output_path: str = "") -> str:
        """Export runtime state to JSON."""
        rt = _load(project)
        if not rt:
            return _json({"error": f"runtime task not found: {project}"})
        out = Path(output_path) if output_path else _runtime_dir(project) / "runtime_export.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rt, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "exported", "path": str(out), "event_count": len(rt.get("events", []))})

    return mcp


def main() -> None:
    build_server().run()

