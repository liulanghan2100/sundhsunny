# -*- coding: utf-8 -*-
"""Long Running Session MCP server.

v6.12 records autonomous loop sessions, checkpoints, deadlines, and resume
state without requiring elevated privileges.

v6.21 adds deadline/resume guard and final summary generation for autonomous
upgrade loops.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
SESSION_DIR = DATA_ROOT / "09_投研" / "long_running_sessions"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe(value: str) -> str:
    return "".join(c for c in value if c.isalnum() or c in "-_.") or "session"


def _session_dir(session_id: str) -> Path:
    return SESSION_DIR / _safe(session_id)


def _state_path(session_id: str) -> Path:
    return _session_dir(session_id) / "session_state.json"


def _checkpoint_path(session_id: str) -> Path:
    return _session_dir(session_id) / "checkpoints.jsonl"


def _read_checkpoints(session_id: str) -> list[dict]:
    path = _checkpoint_path(session_id)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _load(session_id: str) -> dict:
    path = _state_path(session_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(session_id: str, state: dict) -> str:
    path = _state_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated"] = _now()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _append_checkpoint(session_id: str, record: dict) -> dict:
    path = _checkpoint_path(session_id)
    shared_append_jsonl(path, record)
    return record


def _deadline_status(deadline_iso: str) -> dict:
    try:
        deadline = datetime.fromisoformat(deadline_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        remaining = (deadline - now).total_seconds()
        return {"deadline": deadline_iso, "now": now.isoformat(), "expired": remaining <= 0, "remaining_seconds": round(remaining, 1)}
    except Exception:
        return {"deadline": deadline_iso, "expired": False, "remaining_seconds": None, "error": "invalid deadline"}


def _resume_guard(session_id: str, min_remaining_seconds: int = 900) -> dict:
    state = _load(session_id)
    if not state:
        return {"decision": "stop", "reason": "session not found", "session_id": session_id}
    deadline = _deadline_status(state.get("deadline_iso", ""))
    if state.get("status") not in {"running", "deadline_reached"}:
        return {"decision": "stop", "reason": f"session status is {state.get('status')}", "state": state, "deadline": deadline}
    if deadline.get("expired"):
        state["status"] = "deadline_reached"
        _save(session_id, state)
        return {"decision": "finalize", "reason": "deadline reached", "state": state, "deadline": deadline}
    remaining = deadline.get("remaining_seconds")
    if remaining is not None and remaining < min_remaining_seconds:
        return {"decision": "finalize", "reason": "remaining time below threshold", "state": state, "deadline": deadline, "min_remaining_seconds": min_remaining_seconds}
    return {"decision": "continue", "reason": "deadline allows another loop", "state": state, "deadline": deadline, "min_remaining_seconds": min_remaining_seconds}


def _final_summary(session_id: str) -> dict:
    state = _load(session_id)
    checkpoints = _read_checkpoints(session_id)
    completed_versions = state.get("completed_versions", [])
    artifacts = []
    for item in checkpoints:
        artifacts.extend(item.get("artifacts", []))
    return {
        "session_id": session_id,
        "objective": state.get("objective"),
        "status": state.get("status"),
        "deadline": _deadline_status(state.get("deadline_iso", "")),
        "completed_version_count": len(completed_versions),
        "completed_versions": completed_versions,
        "checkpoint_count": len(checkpoints),
        "latest_checkpoint": checkpoints[-1] if checkpoints else None,
        "artifacts": artifacts[-20:],
    }


def build_server() -> FastMCP:
    mcp = FastMCP("long-running-session-mcp")

    @mcp.tool()
    def long_running_session_brief() -> str:
        """Describe long running session checkpoints."""
        return _json({
            "name": "long-running-session-mcp",
            "version": "v6.21",
            "purpose": "记录长运行自主循环的目标、截止时间、checkpoint 和恢复状态",
            "storage": str(SESSION_DIR),
        })

    @mcp.tool()
    def start_session(session_id: str, objective: str, deadline_iso: str,
                      constraints_json: str = "{}") -> str:
        """Start or overwrite a long-running session state."""
        state = {
            "session_id": session_id,
            "objective": objective,
            "deadline_iso": deadline_iso,
            "constraints": _loads(constraints_json, {}),
            "status": "running",
            "created": _now(),
            "completed_versions": [],
            "checkpoint_count": 0,
        }
        _save(session_id, state)
        return _json({"status": "started", "state_path": str(_state_path(session_id)), "state": state})

    @mcp.tool()
    def record_checkpoint(session_id: str, version: str, status: str,
                          summary: str = "", artifacts_json: str = "[]") -> str:
        """Record one loop checkpoint."""
        state = _load(session_id)
        record = {
            "id": f"checkpoint-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "ts": _now(),
            "session_id": session_id,
            "version": version,
            "status": status,
            "summary": summary,
            "artifacts": _loads(artifacts_json, []),
        }
        _append_checkpoint(session_id, record)
        state.setdefault("completed_versions", [])
        if status == "completed" and version not in state["completed_versions"]:
            state["completed_versions"].append(version)
        state["checkpoint_count"] = int(state.get("checkpoint_count", 0)) + 1
        state["last_checkpoint"] = record
        _save(session_id, state)
        return _json({"status": "recorded", "checkpoint": record, "state_path": str(_state_path(session_id))})

    @mcp.tool()
    def session_status(session_id: str) -> str:
        """Return session status and deadline."""
        state = _load(session_id)
        if not state:
            return _json({"error": "session not found", "session_id": session_id})
        deadline = _deadline_status(state.get("deadline_iso", ""))
        if deadline.get("expired") and state.get("status") == "running":
            state["status"] = "deadline_reached"
            _save(session_id, state)
        return _json({"state": state, "deadline": deadline, "state_path": str(_state_path(session_id)), "checkpoint_path": str(_checkpoint_path(session_id))})

    @mcp.tool()
    def deadline_resume_guard(session_id: str, min_remaining_seconds: int = 900) -> str:
        """Decide whether a loop should continue, finalize, or stop."""
        return _json(_resume_guard(session_id, min_remaining_seconds))

    @mcp.tool()
    def session_final_summary(session_id: str) -> str:
        """Return a final summary from state and checkpoints."""
        return _json(_final_summary(session_id))

    @mcp.tool()
    def close_session(session_id: str, final_status: str = "completed",
                      summary: str = "") -> str:
        """Close a long-running session."""
        state = _load(session_id)
        if not state:
            return _json({"error": "session not found", "session_id": session_id})
        state["status"] = final_status
        state["summary"] = summary
        state["closed"] = _now()
        _save(session_id, state)
        return _json({"status": "closed", "state": state, "state_path": str(_state_path(session_id))})

    return mcp


def main() -> None:
    build_server().run()
