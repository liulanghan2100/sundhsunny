# -*- coding: utf-8 -*-
"""Workflow Runtime MCP server.

It models manual-gates execution as a checkpointed workflow. It is intentionally
small and file-based so it can run in the local Codex/Kimi workspace.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.state import safe_project

from _shared.io import _json as shared_json
from _shared.io import _loads as shared_loads
from _shared.state import append_event, load_json_state, safe_project, save_json_state
from _shared.time import _now as shared_now

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
WORKFLOW_ROOT = DATA_ROOT / "09_投研" / "workflow_runtime"
DEFAULT_QUICK_NODES = [4, 9, 17, 19, 24]
STANDARD_NODES = [1, 2, 3, 4, 5, 27, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 26, 22, 23, 24, 25]


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_")


def _path(project: str) -> Path:
    return WORKFLOW_ROOT / _safe_project(project) / "workflow.json"


def _nodes_for_track(track: str) -> list[int]:
    return DEFAULT_QUICK_NODES if track == "quick" else STANDARD_NODES


def _load(project: str) -> dict:
    return load_json_state(_path(project))


def _save(project: str, data: dict) -> dict:
    return save_json_state(_path(project), data, touch_updated=False)


def _event(wf: dict, event_type: str, data: dict) -> None:
    append_event(wf, event_type, data)


def _status(wf: dict, node_id: int) -> str:
    return wf.setdefault("nodes", {}).setdefault(str(node_id), {"status": "pending"}).get("status", "pending")


def build_server() -> FastMCP:
    mcp = FastMCP("workflow-runtime-mcp")

    @mcp.tool()
    def runtime_brief() -> str:
        """Describe workflow runtime capabilities."""
        return _json({
            "name": "workflow-runtime-mcp",
            "purpose": "把 AI执行手册节点执行变成可恢复 checkpoint 状态机",
            "storage_root": str(WORKFLOW_ROOT),
            "tools": [
                "create_workflow",
                "workflow_next",
                "checkpoint_step",
                "complete_step",
                "reopen_step",
                "workflow_report",
                "export_workflow",
            ],
        })

    @mcp.tool()
    def create_workflow(project: str, goal: str, track: str = "standard",
                        autonomy: str = "L2", nodes_json: str = "") -> str:
        """Create or replace a workflow state file."""
        nodes = _loads(nodes_json, []) or _nodes_for_track(track)
        wf = {
            "project": project,
            "goal": goal,
            "track": track,
            "autonomy": autonomy,
            "created": _now(),
            "updated": _now(),
            "nodes": {str(n): {"status": "pending", "checkpoints": []} for n in nodes},
            "events": [],
        }
        _event(wf, "created", {"goal": goal, "track": track, "autonomy": autonomy})
        _save(project, wf)
        return _json({"status": "created", "path": str(_path(project)), "node_count": len(nodes), "workflow": wf})

    @mcp.tool()
    def workflow_next(project: str) -> str:
        """Return the next pending/reopened step."""
        wf = _load(project)
        if not wf:
            return _json({"error": f"workflow not found: {project}"})
        for node_id, rec in wf.get("nodes", {}).items():
            if rec.get("status") in {"pending", "reopened", "failed"}:
                return _json({"project": project, "next_node": int(node_id), "status": rec.get("status"), "record": rec})
        return _json({"project": project, "conclusion": "workflow complete"})

    @mcp.tool()
    def checkpoint_step(project: str, node_id: int, action: str, evidence_path: str = "",
                        result_json: str = "{}", status: str = "checkpointed") -> str:
        """Append a checkpoint to a workflow node."""
        wf = _load(project)
        if not wf:
            return _json({"error": f"workflow not found: {project}"})
        node = wf.setdefault("nodes", {}).setdefault(str(node_id), {"status": "pending", "checkpoints": []})
        cp = {
            "ts": _now(),
            "action": action,
            "evidence_path": evidence_path,
            "result": _loads(result_json, {}),
            "status": status,
        }
        node.setdefault("checkpoints", []).append(cp)
        node["status"] = status
        wf["updated"] = _now()
        _event(wf, "checkpoint", {"node_id": node_id, "action": action, "status": status})
        _save(project, wf)
        return _json({"status": "checkpointed", "node_id": node_id, "checkpoint": cp})

    @mcp.tool()
    def complete_step(project: str, node_id: int, evidence_path: str = "", notes: str = "") -> str:
        """Mark a workflow node complete."""
        wf = _load(project)
        if not wf:
            return _json({"error": f"workflow not found: {project}"})
        node = wf.setdefault("nodes", {}).setdefault(str(node_id), {"status": "pending", "checkpoints": []})
        node["status"] = "completed"
        node["completed_at"] = _now()
        node["evidence_path"] = evidence_path
        node["notes"] = notes
        wf["updated"] = _now()
        _event(wf, "completed", {"node_id": node_id, "evidence_path": evidence_path})
        _save(project, wf)
        return _json({"status": "completed", "node_id": node_id, "next": json.loads(workflow_next(project))})

    @mcp.tool()
    def reopen_step(project: str, node_id: int, reason: str) -> str:
        """Reopen a workflow node and preserve history."""
        wf = _load(project)
        if not wf:
            return _json({"error": f"workflow not found: {project}"})
        node = wf.setdefault("nodes", {}).setdefault(str(node_id), {"status": "pending", "checkpoints": []})
        node["status"] = "reopened"
        node.setdefault("reopen_reasons", []).append({"ts": _now(), "reason": reason})
        wf["updated"] = _now()
        _event(wf, "reopened", {"node_id": node_id, "reason": reason})
        _save(project, wf)
        return _json({"status": "reopened", "node_id": node_id, "reason": reason})

    @mcp.tool()
    def workflow_report(project: str) -> str:
        """Return workflow progress and checkpoint metrics."""
        wf = _load(project)
        if not wf:
            return _json({"error": f"workflow not found: {project}"})
        nodes = wf.get("nodes", {})
        total = len(nodes)
        completed = sum(1 for r in nodes.values() if r.get("status") == "completed")
        reopened = [int(k) for k, v in nodes.items() if v.get("status") == "reopened"]
        checkpoints = sum(len(v.get("checkpoints", [])) for v in nodes.values())
        return _json({
            "project": project,
            "track": wf.get("track"),
            "autonomy": wf.get("autonomy"),
            "progress": f"{completed}/{total}",
            "completed": completed,
            "reopened_nodes": reopened,
            "checkpoint_count": checkpoints,
            "next": json.loads(workflow_next(project)),
            "path": str(_path(project)),
        })

    @mcp.tool()
    def export_workflow(project: str, output_path: str = "") -> str:
        """Export workflow state to a chosen path."""
        wf = _load(project)
        if not wf:
            return _json({"error": f"workflow not found: {project}"})
        p = Path(output_path) if output_path else _path(project).with_name("workflow_export.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "exported", "path": str(p), "event_count": len(wf.get("events", []))})

    return mcp


def main() -> None:
    build_server().run()
