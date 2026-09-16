# -*- coding: utf-8 -*-
"""Mandatory Runtime Hook MCP server.

v5.11 makes the governed runtime path explicit and testable. It is a wrapper
layer that routes task starts through hook policy and control plane before any
integrated execution is allowed.

v6.3 adds cognitive intake as the mandatory node 0 before hook policy and
control-plane execution.

v6.16 inserts the unified preflight bundle before the governed runtime cycle.
The mandatory route now fails closed when preflight says no-go.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.state import safe_project

from control_plane_mcp.common import _governed_cycle, _load_policy, _policy_check, _verify_chain
from cognitive_intake_mcp.common import _append_log as _append_intake_log
from cognitive_intake_mcp.common import _classify as _classify_task
from cognitive_intake_mcp.common import _execution_card
from hook_runtime_mcp.common import _policy as _hook_policy
from preflight_bundle_mcp.common import _append as _append_preflight_bundle
from preflight_bundle_mcp.common import _bundle as _build_preflight_bundle

ROOT = Path(__file__).resolve().parents[2]


def _find_named_dir(prefix: str, fallback: str) -> Path:
    """Resolve the research dir deterministically (same rule as task_queue_mcp).
    Multiple "09_" dirs exist; iterdir() order is filesystem-dependent."""
    candidates = sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(prefix))
    for path in candidates:
        if path.name == "09_投研":
            return path
    if candidates:
        return candidates[0]
    matches = list(ROOT.glob(fallback))
    return matches[0] if matches else ROOT / fallback.replace("*", "")


_env_queue_root = os.environ.get("TASK_QUEUE_ROOT")
RESEARCH_DIR = Path(_env_queue_root) if _env_queue_root else _find_named_dir("09_", "09_*")
MANDATORY_ROOT = RESEARCH_DIR / "mandatory_runtime_hook"


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _project_dir(project: str) -> Path:
    return MANDATORY_ROOT / _safe_project(project)


def _state_path(project: str) -> Path:
    return _project_dir(project) / "mandatory_state.json"


def _write_state(project: str, state: dict) -> str:
    path = _state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _read_state(project: str) -> dict:
    path = _state_path(project)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _route_plan(project: str, task: str, tool: str = "", event_type: str = "start",
                node_id: int = 0, risk: str = "normal", approved: bool = False) -> dict:
    cognitive_decision = _classify_task(task, {"risk": risk, "tool": tool, "node_id": node_id})
    execution_card = _execution_card(project, task, cognitive_decision)
    hook_plan = _hook_policy(task, event_type, tool or "mandatory_runtime_hook", node_id, risk)
    control_check = _policy_check(task, risk, approved, _load_policy())
    cognitive_allowed = cognitive_decision["task_class"] != "D"
    return {
        "project": project,
        "task": task,
        "tool": tool or "mandatory_runtime_hook",
        "event_type": event_type,
        "node_id": node_id,
        "risk": risk,
        "approved": approved,
        "mandatory_entry": True,
        "cognitive_intake_required": True,
        "cognitive_intake": cognitive_decision,
        "execution_card": execution_card,
        "required_route": [
            "cognitive_intake",
            "preflight_bundle",
            "mandatory_runtime_hook",
            "hook_runtime_policy",
            "control_plane",
            "runtime_integration",
        ],
        "hook_plan": hook_plan,
        "control_policy": control_check,
        "will_execute": cognitive_allowed and control_check["allowed"],
    }


def _mandatory_cycle(project: str, task: str, risk: str = "normal",
                     approved: bool = False, track: str = "quick",
                     autonomy: str = "L2", tool: str = "",
                     node_id: int = 0, context: dict | None = None) -> dict:
    plan = _route_plan(project, task, tool, "start", node_id, risk, approved)
    _append_intake_log(project, task, plan["cognitive_intake"])
    operation = (context or {}).get("operation") or "local_edit"
    if risk == "critical" and operation == "local_edit":
        operation = "admin_permission"
    preflight = _build_preflight_bundle(project, task, operation, risk, {
        "tool": tool,
        "node_id": node_id,
        "approved": approved,
        **(context or {}),
    })
    _append_preflight_bundle(preflight)
    if not preflight.get("go"):
        chain = _verify_chain(project)
        state = {
            "project": project,
            "task": task,
            "status": "blocked",
            "blocked_by": "preflight_bundle",
            "mandatory_entry": True,
            "cognitive_intake_required": True,
            "preflight_bundle_required": True,
            "preflight_bundle": preflight,
            "route": plan["required_route"],
            "cognitive_intake": plan["cognitive_intake"],
            "execution_card": plan["execution_card"],
            "hook_action_count": plan["hook_plan"].get("action_count", 0),
            "control_allowed": plan["control_policy"].get("allowed"),
            "control_requires_approval": plan["control_policy"].get("requires_approval"),
            "audit_valid": chain["valid"],
            "created": _now(),
        }
        _write_state(project, state)
        return {
            "status": "blocked",
            "project": project,
            "blocked_by": "preflight_bundle",
            "mandatory_entry": True,
            "cognitive_intake_required": True,
            "preflight_bundle_required": True,
            "preflight_go": False,
            "preflight_id": preflight.get("id"),
            "preflight_blockers": preflight.get("blockers", []),
            "task_class": plan["cognitive_intake"]["task_class"],
            "state_path": str(_state_path(project)),
        }
    if plan["cognitive_intake"]["task_class"] == "D":
        chain = _verify_chain(project)
        state = {
            "project": project,
            "task": task,
            "status": "blocked",
            "blocked_by": "cognitive_intake",
            "mandatory_entry": True,
            "cognitive_intake_required": True,
            "preflight_bundle_required": True,
            "preflight_bundle": preflight,
            "route": plan["required_route"],
            "cognitive_intake": plan["cognitive_intake"],
            "execution_card": plan["execution_card"],
            "hook_action_count": plan["hook_plan"].get("action_count", 0),
            "control_allowed": plan["control_policy"].get("allowed"),
            "control_requires_approval": plan["control_policy"].get("requires_approval"),
            "audit_valid": chain["valid"],
            "created": _now(),
        }
        _write_state(project, state)
        return {
            "status": "blocked",
            "project": project,
            "blocked_by": "cognitive_intake",
            "mandatory_entry": True,
            "cognitive_intake_required": True,
            "task_class": plan["cognitive_intake"]["task_class"],
            "state_path": str(_state_path(project)),
        }
    governed = _governed_cycle(project, task, risk, approved, track, autonomy, {
        "mandatory_runtime_hook": True,
        "cognitive_intake_required": True,
        "preflight_bundle_required": True,
        "preflight_bundle": preflight,
        "cognitive_intake": plan["cognitive_intake"],
        "execution_card": plan["execution_card"],
        "route_plan": plan,
        "context": context or {},
    })
    chain = _verify_chain(project)
    state = {
        "project": project,
        "task": task,
        "status": governed.get("status"),
        "mandatory_entry": True,
        "cognitive_intake_required": True,
        "preflight_bundle_required": True,
        "preflight_bundle": preflight,
        "cognitive_intake": plan["cognitive_intake"],
        "execution_card": plan["execution_card"],
        "route": plan["required_route"],
        "hook_action_count": plan["hook_plan"].get("action_count", 0),
        "control_allowed": plan["control_policy"].get("allowed"),
        "control_requires_approval": plan["control_policy"].get("requires_approval"),
        "governed_result": governed,
        "audit_valid": chain["valid"],
        "created": _now(),
    }
    _write_state(project, state)
    return {
        "status": state["status"],
        "project": project,
        "mandatory_entry": True,
        "cognitive_intake_required": True,
        "preflight_bundle_required": True,
        "preflight_go": preflight.get("go"),
        "preflight_id": preflight.get("id"),
        "task_class": plan["cognitive_intake"]["task_class"],
        "control_allowed": state["control_allowed"],
        "audit_valid": state["audit_valid"],
        "state_path": str(_state_path(project)),
        "governed_result": governed,
    }


def build_server() -> FastMCP:
    mcp = FastMCP("mandatory-runtime-hook-mcp")

    @mcp.tool()
    def mandatory_brief() -> str:
        """Describe the mandatory runtime hook layer."""
        return _json({
            "name": "mandatory-runtime-hook-mcp",
            "version": "v6.16",
            "purpose": "make cognitive intake, unified preflight, and control plane the mandatory route before runtime integration",
            "route": ["cognitive_intake", "preflight_bundle", "mandatory_runtime_hook", "hook_runtime_policy", "control_plane", "runtime_integration"],
            "storage_root": str(MANDATORY_ROOT),
        })

    @mcp.tool()
    def plan_mandatory_route(project: str, task: str, tool: str = "",
                             event_type: str = "start", node_id: int = 0,
                             risk: str = "normal", approved: bool = False) -> str:
        """Plan the mandatory route without executing it."""
        return _json(_route_plan(project, task, tool, event_type, node_id, risk, approved))

    @mcp.tool()
    def start_mandatory_task(project: str, task: str, risk: str = "normal",
                             approved: bool = False, track: str = "quick",
                             autonomy: str = "L2", tool: str = "",
                             node_id: int = 0, context_json: str = "{}") -> str:
        """Start a task through the mandatory governed route."""
        return _json(_mandatory_cycle(project, task, risk, approved, track, autonomy, tool, node_id, _loads(context_json, {})))

    @mcp.tool()
    def mandatory_status(project: str) -> str:
        """Return mandatory runtime state."""
        state = _read_state(project)
        if not state:
            return _json({"error": f"mandatory state not found: {project}"})
        return _json({"project": project, "state": state, "path": str(_state_path(project))})

    @mcp.tool()
    def verify_mandatory_compliance(project: str) -> str:
        """Verify that the project used mandatory route and valid control audit."""
        state = _read_state(project)
        chain = _verify_chain(project)
        required = ["cognitive_intake", "preflight_bundle", "mandatory_runtime_hook", "hook_runtime_policy", "control_plane", "runtime_integration"]
        compliant = bool(
            state.get("mandatory_entry")
            and state.get("cognitive_intake_required")
            and state.get("preflight_bundle_required")
            and state.get("preflight_bundle", {}).get("go") is True
            and state.get("route") == required
            and state.get("cognitive_intake", {}).get("task_class") in {"A", "B", "C", "D"}
            and chain.get("valid")
        )
        return _json({
            "project": project,
            "compliant": compliant,
            "mandatory_entry": state.get("mandatory_entry", False),
            "cognitive_intake_required": state.get("cognitive_intake_required", False),
            "preflight_bundle_required": state.get("preflight_bundle_required", False),
            "preflight_go": state.get("preflight_bundle", {}).get("go"),
            "preflight_id": state.get("preflight_bundle", {}).get("id"),
            "task_class": state.get("cognitive_intake", {}).get("task_class"),
            "route": state.get("route", []),
            "audit_chain": chain,
            "state_path": str(_state_path(project)),
        })

    return mcp


def main() -> None:
    build_server().run()
