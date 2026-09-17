# -*- coding: utf-8 -*-
"""Side Effect Admission MCP server.

v6.14 issues pre-action tickets for side-effecting operations.
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
ADMISSION_DIR = DATA_ROOT / "09_投研" / "side_effect_admission"
TICKET_FILE = ADMISSION_DIR / "admission_tickets.jsonl"

SAFE_EFFECTS = {"local_edit", "local_test", "local_mcp", "manual_gates", "backup", "documentation"}
DENIED_EFFECTS = {"admin_permission", "secret_access", "production_deploy", "remote_publish", "git_push", "hardware_control", "paid_api_call", "destructive_delete"}
DENY_TERMS = {"管理员", "admin", "root", "sudo", "生产", "deploy", "发布", "secret", "token", "密钥", "delete", "删除", "push", "付费", "实机"}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _append(record: dict) -> dict:
    TICKET_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TICKET_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _read_tickets() -> list[dict]:
    if not TICKET_FILE.exists():
        return []
    rows = []
    for line in TICKET_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _classify_effect(action: str, effect_type: str, risk: str) -> dict:
    text = f"{action} {effect_type} {risk}".lower()
    deny_hits = [t for t in DENY_TERMS if t.lower() in text]
    if effect_type in DENIED_EFFECTS or deny_hits or risk.lower() in {"high", "critical"}:
        return {"side_effect_level": "blocked", "deny_hits": deny_hits}
    if effect_type in SAFE_EFFECTS:
        return {"side_effect_level": "local_safe", "deny_hits": []}
    return {"side_effect_level": "review_required", "deny_hits": []}


def build_server() -> FastMCP:
    mcp = FastMCP("side-effect-admission-mcp")

    @mcp.tool()
    def side_effect_admission_brief() -> str:
        """Describe side-effect admission gate."""
        return _json({
            "name": "side-effect-admission-mcp",
            "version": "v6.14",
            "purpose": "为有副作用动作签发准入票；高风险动作 fail-closed",
            "safe_effects": sorted(SAFE_EFFECTS),
            "denied_effects": sorted(DENIED_EFFECTS),
            "storage": str(TICKET_FILE),
        })

    @mcp.tool()
    def request_admission(project: str, action: str, effect_type: str,
                          risk: str = "normal", evidence_json: str = "{}") -> str:
        """Request a pre-action admission ticket."""
        cls = _classify_effect(action, effect_type, risk)
        allowed = cls["side_effect_level"] == "local_safe"
        ticket = {
            "id": f"admission-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "ts": _now(),
            "project": project,
            "action": action,
            "effect_type": effect_type,
            "risk": risk,
            "allowed": allowed,
            "side_effect_level": cls["side_effect_level"],
            "deny_hits": cls["deny_hits"],
            "evidence": _loads(evidence_json, {}),
            "decision": "allow" if allowed else "reject",
        }
        _append(ticket)
        return _json(ticket)

    @mcp.tool()
    def verify_admission_ticket(ticket_id: str) -> str:
        """Verify that a ticket exists and allows execution."""
        for ticket in _read_tickets():
            if ticket.get("id") == ticket_id:
                return _json({"found": True, "allowed": ticket.get("allowed"), "ticket": ticket})
        return _json({"found": False, "allowed": False, "error": "ticket not found"})

    @mcp.tool()
    def admission_report(project: str = "") -> str:
        """Return admission stats."""
        tickets = _read_tickets()
        if project:
            tickets = [t for t in tickets if t.get("project") == project]
        return _json({
            "project": project or "all",
            "ticket_count": len(tickets),
            "allowed": sum(1 for t in tickets if t.get("allowed")),
            "rejected": sum(1 for t in tickets if not t.get("allowed")),
            "recent": tickets[-10:],
            "storage": str(TICKET_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
