# -*- coding: utf-8 -*-
"""Capability Profile MCP server.

v6.13 defines scoped permissions for local autonomous work and checks actions
before execution.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[2]
CAP_DIR = ROOT / "09_投研" / "capability_profile"
PROFILE_FILE = CAP_DIR / "capability_profile.json"
AUDIT_FILE = CAP_DIR / "permission_checks.jsonl"

DEFAULT_PROFILE = {
    "version": "v6.13",
    "allowed_operations": [
        "local_read",
        "local_edit",
        "local_test",
        "local_mcp",
        "manual_gates",
        "backup",
        "documentation",
        "web_research",
    ],
    "denied_operations": [
        "admin_permission",
        "production_deploy",
        "secret_access",
        "credential_storage",
        "destructive_delete",
        "git_push",
        "remote_pr",
        "paid_api_call",
        "hardware_control",
    ],
    "deny_terms": [
        "管理员",
        "admin",
        "sudo",
        "root",
        "生产",
        "deploy",
        "发布",
        "secret",
        "token",
        "密钥",
        "delete",
        "remove",
        "删除",
        "push",
        "pr",
        "付费",
        "实机",
    ],
    "requires_user_approval": [
        "install",
        "uninstall",
        "network_registration",
        "external_account",
        "payment",
        "hardware_run",
    ],
}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _load_profile() -> dict:
    if not PROFILE_FILE.exists():
        PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_FILE.write_text(json.dumps(DEFAULT_PROFILE, ensure_ascii=False, indent=2), encoding="utf-8")
    data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_PROFILE)
    merged.update(data)
    return merged


def _save_profile(profile: dict) -> str:
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(PROFILE_FILE)


def _append_audit(record: dict) -> None:
    shared_append_jsonl(AUDIT_FILE, record)


def _term_hit(term: str, text: str) -> bool:
    """ASCII deny terms match on word boundaries so 'pr' no longer fires inside
    'proof'/'process'; non-ASCII (CJK) terms keep substring matching."""
    needle = term.lower()
    if needle.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", text) is not None
    return needle in text


def _check(action: str, operation: str, risk: str = "normal", approved: bool = False) -> dict:
    profile = _load_profile()
    text = f"{action} {operation} {risk}".lower()
    deny_hits = [term for term in profile.get("deny_terms", []) if _term_hit(term, text)]
    denied_operation = operation in set(profile.get("denied_operations", []))
    allowed_operation = operation in set(profile.get("allowed_operations", []))
    high_risk = risk.lower() in {"high", "critical"}
    requires_approval = high_risk or denied_operation or bool(deny_hits)
    allowed = allowed_operation and not requires_approval
    if requires_approval and approved and operation not in {"admin_permission", "production_deploy", "secret_access"}:
        allowed = True
    return {
        "allowed": allowed,
        "operation": operation,
        "risk": risk,
        "approved": approved,
        "allowed_operation": allowed_operation,
        "requires_approval": requires_approval,
        "deny_hits": deny_hits,
        "reason": "allowed local scoped operation" if allowed else "blocked by capability profile or missing approval",
    }


def build_server() -> FastMCP:
    mcp = FastMCP("capability-profile-mcp")

    @mcp.tool()
    def capability_profile_brief() -> str:
        """Describe capability profile."""
        return _json({"name": "capability-profile-mcp", "version": "v6.13", "profile": _load_profile(), "storage": str(PROFILE_FILE)})

    @mcp.tool()
    def define_capability_profile(profile_json: str) -> str:
        """Replace capability profile."""
        profile = _loads(profile_json, DEFAULT_PROFILE)
        path = _save_profile(profile)
        return _json({"status": "saved", "path": path, "profile": profile})

    @mcp.tool()
    def check_action_permission(action: str, operation: str, risk: str = "normal",
                                approved: bool = False) -> str:
        """Check whether an action is allowed."""
        result = _check(action, operation, risk, approved)
        record = {"id": f"perm-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}", "ts": _now(), "action": action, **result}
        _append_audit(record)
        return _json(record)

    @mcp.tool()
    def capability_report() -> str:
        """Return profile and recent permission checks."""
        checks = []
        if AUDIT_FILE.exists():
            for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines()[-20:]:
                if line.strip():
                    checks.append(json.loads(line))
        return _json({"profile": _load_profile(), "recent_checks": checks, "audit": str(AUDIT_FILE)})

    return mcp


def main() -> None:
    build_server().run()
