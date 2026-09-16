# -*- coding: utf-8 -*-
"""Control Plane MCP server.

v5.10 makes the runtime integration layer the governed default entry point. It
adds policy checks and an append-only SHA-256 audit chain before/after each
integrated task.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _append_jsonl as shared_append_jsonl
from _shared.io import _json as shared_json
from _shared.io import _loads as shared_loads
from _shared.state import safe_project
from _shared.time import _now as shared_now

from runtime_integration_mcp.common import _integrated_cycle

ROOT = Path(__file__).resolve().parents[2]


def _find_named_dir(prefix: str, fallback: str) -> Path:
    for path in ROOT.iterdir():
        if path.is_dir() and path.name.startswith(prefix):
            return path
    matches = list(ROOT.glob(fallback))
    return matches[0] if matches else ROOT / fallback.replace("*", "")


RESEARCH_DIR = _find_named_dir("09_", "09_*")
CONTROL_ROOT = RESEARCH_DIR / "control_plane"
POLICY_FILE = CONTROL_ROOT / "policy.json"

DEFAULT_POLICY = {
    "version": "v5.12.1",
    "default_autonomy": "L3",
    "allow_default_integrated_task": True,
    "autonomous_continue": {
        "enabled": True,
        "default_track": "quick",
        "allowed_tracks": ["quick"],
        "allowed_risks": ["low", "normal"],
        "allowed_operations": ["local_edit", "test", "gate_check", "backup", "documentation", "local_mcp"],
        "stop_after_versions": 5
    },
    "require_human_approval_for": [
        "delete",
        "remove",
        "reset",
        "publish",
        "deploy",
        "production",
        "secret",
        "token",
        "credential",
        "覆盖",
        "删除",
        "发布",
        "部署",
        "生产",
        "密钥",
        "install",
        "uninstall",
        "pip",
        "npm",
        "github",
        "push",
        "pr",
        "ci",
        "联网注册",
        "安装",
        "卸载",
    ],
    "blocked_without_approval": True,
}


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _project_dir(project: str) -> Path:
    return CONTROL_ROOT / _safe_project(project)


def _audit_path(project: str) -> Path:
    return _project_dir(project) / "audit.jsonl"


def _state_path(project: str) -> Path:
    return _project_dir(project) / "control_state.json"


def _load_policy() -> dict:
    if not POLICY_FILE.exists():
        POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        POLICY_FILE.write_text(json.dumps(DEFAULT_POLICY, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        data = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = dict(DEFAULT_POLICY)
    merged = dict(DEFAULT_POLICY)
    merged.update(data)
    return merged


def _read_audit(project: str) -> list[dict]:
    path = _audit_path(project)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _hash_payload(payload: dict, previous_hash: str) -> str:
    material = json.dumps({"previous_hash": previous_hash, "payload": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _append_audit(project: str, event_type: str, payload: dict) -> dict:
    rows = _read_audit(project)
    previous_hash = rows[-1]["hash"] if rows else "GENESIS"
    event = {
        "event_id": f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "event_type": event_type,
        "previous_hash": previous_hash,
        "payload": payload,
    }
    event["hash"] = _hash_payload({k: v for k, v in event.items() if k != "hash"}, previous_hash)
    path = _audit_path(project)
    shared_append_jsonl(path, event)
    return event


def _policy_check(task: str, risk: str, approved: bool, policy: dict) -> dict:
    text = f"{task} {risk}".lower()
    token_text = "".join(ch if ch.isalnum() else " " for ch in text)
    tokens = set(token_text.split())
    hits = []
    for term in policy.get("require_human_approval_for", []):
        lowered = term.lower()
        if lowered.isascii() and lowered.isalnum() and len(lowered) <= 3:
            if lowered in tokens:
                hits.append(term)
        elif lowered in text:
            hits.append(term)
    high_risk = risk.lower() in {"high", "critical"}
    requires_approval = bool(hits or high_risk)
    allowed = not requires_approval or approved or not policy.get("blocked_without_approval", True)
    return {
        "allowed": allowed,
        "requires_approval": requires_approval,
        "approved": approved,
        "risk": risk,
        "matched_terms": hits,
        "reason": "approved or low risk" if allowed else "human approval required before governed execution",
    }


def _autonomy_decision(task: str, track: str, risk: str, operation: str,
                       approved: bool, policy: dict) -> dict:
    """Decide whether the agent may continue without asking the user."""
    control = _policy_check(task, risk, approved, policy)
    autonomy = policy.get("autonomous_continue", {})
    enabled = bool(autonomy.get("enabled", False))
    allowed_track = track in set(autonomy.get("allowed_tracks", []))
    allowed_risk = risk.lower() in set(autonomy.get("allowed_risks", []))
    allowed_operation = operation in set(autonomy.get("allowed_operations", []))
    may_continue = bool(enabled and allowed_track and allowed_risk and allowed_operation and control["allowed"])
    blockers = []
    if not enabled:
        blockers.append("autonomous_continue disabled")
    if not allowed_track:
        blockers.append(f"track not allowed: {track}")
    if not allowed_risk:
        blockers.append(f"risk not allowed: {risk}")
    if not allowed_operation:
        blockers.append(f"operation not allowed: {operation}")
    if not control["allowed"]:
        blockers.append(control["reason"])
    return {
        "may_continue": may_continue,
        "must_ask_user": not may_continue,
        "autonomy": policy.get("default_autonomy", "L2"),
        "track": track,
        "risk": risk,
        "operation": operation,
        "policy_check": control,
        "blockers": blockers,
        "rule": "Quick + low/normal risk + local safe operation can continue autonomously; external/high-risk actions require approval",
    }


def _write_state(project: str, state: dict) -> str:
    path = _state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _verify_chain(project: str) -> dict:
    rows = _read_audit(project)
    previous_hash = "GENESIS"
    errors = []
    for idx, row in enumerate(rows):
        if row.get("previous_hash") != previous_hash:
            errors.append({"index": idx, "error": "previous_hash mismatch"})
        expected = _hash_payload({k: v for k, v in row.items() if k != "hash"}, row.get("previous_hash", ""))
        if row.get("hash") != expected:
            errors.append({"index": idx, "error": "hash mismatch"})
        previous_hash = row.get("hash", "")
    return {
        "valid": not errors,
        "event_count": len(rows),
        "head_hash": previous_hash if rows else "GENESIS",
        "errors": errors,
        "audit_path": str(_audit_path(project)),
    }


def _governed_cycle(project: str, task: str, risk: str = "normal",
                    approved: bool = False, track: str = "quick",
                    autonomy: str = "L2", context: dict | None = None) -> dict:
    """Run the reusable governed task lifecycle used by MCP tools and wrappers."""
    policy = _load_policy()
    check = _policy_check(task, risk, approved, policy)
    start_event = _append_audit(project, "policy_check", {
        "task": task,
        "risk": risk,
        "check": check,
        "context": context or {},
    })
    if not check["allowed"]:
        state = {
            "project": project,
            "task": task,
            "status": "blocked",
            "policy_check": check,
            "audit_head": start_event["hash"],
            "created": _now(),
        }
        _write_state(project, state)
        return {
            "status": "blocked",
            "policy_check": check,
            "audit": start_event,
            "state_path": str(_state_path(project)),
        }

    integration = _integrated_cycle(project, task, track, autonomy)
    done_event = _append_audit(project, "runtime_integration_completed", {
        "integration_status": integration.get("status"),
        "steps": [step.get("step") for step in integration.get("steps", [])],
        "artifacts": integration.get("artifacts", {}),
    })
    chain = _verify_chain(project)
    state = {
        "project": project,
        "task": task,
        "status": "completed",
        "policy_check": check,
        "integration_path": str(RESEARCH_DIR / "runtime_integration" / _safe_project(project) / "integration.json"),
        "audit_head": done_event["hash"],
        "audit_valid": chain["valid"],
        "created": _now(),
    }
    _write_state(project, state)
    return {
        "status": "completed",
        "policy_check": check,
        "integration_status": integration.get("status"),
        "audit_chain": chain,
        "state_path": str(_state_path(project)),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("control-plane-mcp")

    @mcp.tool()
    def control_brief() -> str:
        """Describe governed control plane."""
        return _json({
            "name": "control-plane-mcp",
            "version": "v5.10",
            "purpose": "default governed entry for runtime integration with policy checks and hash-chain audit",
            "policy_file": str(POLICY_FILE),
            "storage_root": str(CONTROL_ROOT),
        })

    @mcp.tool()
    def policy_status() -> str:
        """Return current control policy."""
        return _json({"policy": _load_policy(), "policy_file": str(POLICY_FILE)})

    @mcp.tool()
    def policy_check(task: str, risk: str = "normal", approved: bool = False) -> str:
        """Check whether a task is allowed by policy."""
        return _json(_policy_check(task, risk, approved, _load_policy()))

    @mcp.tool()
    def autonomy_decision(task: str, track: str = "quick", risk: str = "normal",
                          operation: str = "local_edit", approved: bool = False) -> str:
        """Decide whether the agent may continue without asking the user."""
        return _json(_autonomy_decision(task, track, risk, operation, approved, _load_policy()))

    @mcp.tool()
    def start_governed_task(project: str, task: str, risk: str = "normal",
                            approved: bool = False, track: str = "quick",
                            autonomy: str = "L2",
                            context_json: str = "{}") -> str:
        """Run a task through policy, audit, and runtime integration."""
        return _json(_governed_cycle(project, task, risk, approved, track, autonomy, _loads(context_json, {})))

    @mcp.tool()
    def audit_event(project: str, event_type: str, payload_json: str = "{}") -> str:
        """Append one signed audit event."""
        event = _append_audit(project, event_type, _loads(payload_json, {}))
        return _json({"status": "recorded", "event": event})

    @mcp.tool()
    def verify_audit_chain(project: str) -> str:
        """Verify project audit hash chain."""
        return _json(_verify_chain(project))

    @mcp.tool()
    def control_status(project: str) -> str:
        """Return control state and audit verification."""
        state_path = _state_path(project)
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        return _json({"project": project, "state": state, "audit_chain": _verify_chain(project)})

    return mcp


def main() -> None:
    build_server().run()
