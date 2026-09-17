# -*- coding: utf-8 -*-
"""Approval Interrupt MCP server.

v6.29 turns "ask only when necessary" into a local policy artifact. Safe local
actions can continue automatically; high-risk or denied operations create a
pending interrupt that must be explicitly approved before resume.
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

from capability_profile_mcp.common import _check as _capability_check
from side_effect_admission_mcp.common import _classify_effect

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
INTERRUPT_DIR = DATA_ROOT / "09_投研" / "approval_interrupts"
INTERRUPT_FILE = INTERRUPT_DIR / "interrupts.jsonl"
RESUME_FILE = INTERRUPT_DIR / "resume_events.jsonl"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _append(path: Path, record: dict) -> dict:
    shared_append_jsonl(path, record)
    return record


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_all(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def _find_interrupt(interrupt_id: str) -> tuple[int, dict]:
    rows = _read(INTERRUPT_FILE)
    for idx, row in enumerate(rows):
        if row.get("id") == interrupt_id:
            return idx, row
    return -1, {}


def _decision(project: str, action: str, operation: str, effect_type: str,
              risk: str, context: dict) -> dict:
    capability = _capability_check(action, operation, risk, approved=False)
    effect = _classify_effect(action, effect_type, risk)
    auto_allowed = capability.get("allowed") is True and effect.get("side_effect_level") == "local_safe"
    hard_blocked = operation in {
        "admin_permission",
        "production_deploy",
        "secret_access",
        "credential_storage",
        "destructive_delete",
        "git_push",
        "remote_pr",
        "paid_api_call",
        "hardware_control",
    } or effect.get("side_effect_level") == "blocked"
    record = {
        "id": f"interrupt-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "action": action,
        "operation": operation,
        "effect_type": effect_type,
        "risk": risk,
        "context": context,
        "capability": capability,
        "effect": effect,
        "auto_allowed": auto_allowed,
        "requires_interrupt": not auto_allowed,
        "hard_blocked": hard_blocked,
        "status": "auto_allowed" if auto_allowed else "pending",
        "approval_id": "",
        "decision_reason": "local safe operation" if auto_allowed else "approval interrupt required",
    }
    if hard_blocked:
        record["decision_reason"] = "high-risk operation requires explicit approval and may remain forbidden by policy"
    return record


def _request(project: str, action: str, operation: str, effect_type: str,
             risk: str = "normal", context_json: str = "{}") -> dict:
    record = _decision(project, action, operation, effect_type, risk, _loads(context_json, {}))
    _append(INTERRUPT_FILE, record)
    return record


def _set_status(interrupt_id: str, status: str, approver: str, notes: str) -> dict:
    idx, item = _find_interrupt(interrupt_id)
    if not item:
        return {"found": False, "allowed": False, "error": "interrupt not found"}
    rows = _read(INTERRUPT_FILE)
    if item.get("auto_allowed"):
        return {"found": True, "allowed": True, "interrupt": item, "message": "already auto allowed"}
    item["status"] = status
    item["approval_id"] = f"approval-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}" if status == "approved" else ""
    item["approver"] = approver
    item["approval_notes"] = notes
    item["updated"] = _now()
    rows[idx] = item
    _write_all(INTERRUPT_FILE, rows)
    return {"found": True, "allowed": status == "approved", "interrupt": item}


def _resume(interrupt_id: str, approval_id: str) -> dict:
    _, item = _find_interrupt(interrupt_id)
    allowed = bool(item and (item.get("auto_allowed") or (item.get("status") == "approved" and item.get("approval_id") == approval_id)))
    event = {
        "id": f"resume-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "interrupt_id": interrupt_id,
        "approval_id": approval_id,
        "allowed": allowed,
        "project": item.get("project") if item else "",
        "reason": "approved or auto allowed" if allowed else "missing matching approval",
    }
    _append(RESUME_FILE, event)
    return event


def _report(project: str = "") -> dict:
    rows = _read(INTERRUPT_FILE)
    if project:
        rows = [row for row in rows if row.get("project") == project]
    return {
        "project": project or "all",
        "interrupt_count": len(rows),
        "auto_allowed": sum(1 for row in rows if row.get("auto_allowed")),
        "pending": sum(1 for row in rows if row.get("status") == "pending"),
        "approved": sum(1 for row in rows if row.get("status") == "approved"),
        "rejected": sum(1 for row in rows if row.get("status") == "rejected"),
        "hard_blocked": sum(1 for row in rows if row.get("hard_blocked")),
        "recent": rows[-10:],
        "storage": str(INTERRUPT_FILE),
        "resume_storage": str(RESUME_FILE),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("approval-interrupt-mcp")

    @mcp.tool()
    def approval_interrupt_brief() -> str:
        """Describe approval interrupt policy."""
        return _json({
            "name": "approval-interrupt-mcp",
            "version": "v6.29",
            "purpose": "only interrupt autonomous execution when policy requires approval",
            "storage": str(INTERRUPT_FILE),
            "resume_storage": str(RESUME_FILE),
            "admin_boundary": "does not request administrator privileges",
        })

    @mcp.tool()
    def request_or_interrupt(project: str, action: str, operation: str,
                             effect_type: str, risk: str = "normal",
                             context_json: str = "{}") -> str:
        """Return auto_allowed for safe actions or create a pending interrupt."""
        return _json(_request(project, action, operation, effect_type, risk, context_json))

    @mcp.tool()
    def approve_interrupt(interrupt_id: str, approver: str = "user", notes: str = "") -> str:
        """Approve a pending interrupt locally."""
        return _json(_set_status(interrupt_id, "approved", approver, notes))

    @mcp.tool()
    def reject_interrupt(interrupt_id: str, approver: str = "user", notes: str = "") -> str:
        """Reject a pending interrupt locally."""
        return _json(_set_status(interrupt_id, "rejected", approver, notes))

    @mcp.tool()
    def resume_with_approval(interrupt_id: str, approval_id: str = "") -> str:
        """Resume only when auto-allowed or matching approval exists."""
        return _json(_resume(interrupt_id, approval_id))

    @mcp.tool()
    def interrupt_report(project: str = "") -> str:
        """Return interrupt queue status."""
        return _json(_report(project))

    return mcp


def main() -> None:
    build_server().run()
