# -*- coding: utf-8 -*-
"""Completion Verifier MCP server.

v6.11 makes "done" an evidence-gated decision. It is read-only: it checks the
provided context and writes certificates/reports, but does not execute tasks.

v6.18 adds evidence closure for important projects: preflight and local
regression gate evidence are required before a Class C completion certificate
can be accepted.
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

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
CERT_DIR = DATA_ROOT / "09_投研" / "completion_verifier"

REQUIRED_BY_CLASS = {
    "A": ["answer"],
    "B": ["minimum_validation", "result"],
    "C": [
        "cognitive_intake",
        "preflight_bundle",
        "preflight_go",
        "execution_card",
        "pre_research_report",
        "failure_replay",
        "workflow",
        "tests",
        "eval_run",
        "local_regression_gate",
        "regression_passed",
        "gate_report",
        "backup_path",
        "backup_integrity_manifest",
        "backup_integrity_verified",
        "compiled_correction_check",
    ],
    "D": ["blocked", "hard_blockers", "recovery_path"],
}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _context_text(context: dict) -> str:
    return json.dumps(context, ensure_ascii=False).lower()


def _verify(task_class: str, context: dict) -> dict:
    required = REQUIRED_BY_CLASS.get(task_class, REQUIRED_BY_CLASS["A"])
    text = _context_text(context)
    checks = []
    for item in required:
        present = item.lower() in text
        checks.append({"evidence": item, "present": present})
    pseudo_claims = ["已真实完成", "生产已部署", "真实视频已生成"]
    forbidden_hits = [claim for claim in pseudo_claims if claim.lower() in text and "real_evidence" not in text]
    passed = all(c["present"] for c in checks) and not forbidden_hits
    return {
        "task_class": task_class,
        "passed": passed,
        "missing": [c["evidence"] for c in checks if not c["present"]],
        "forbidden_hits": forbidden_hits,
        "checks": checks,
        "decision": "accept" if passed else "reject",
        "rule": "fail-closed: missing evidence means completion cannot be claimed",
    }


def _certificate_path(project: str) -> Path:
    return CERT_DIR / _safe_project(project) / "completion_certificate.json"


def build_server() -> FastMCP:
    mcp = FastMCP("completion-verifier-mcp")

    @mcp.tool()
    def completion_verifier_brief() -> str:
        """Describe evidence-gated completion."""
        return _json({
            "name": "completion-verifier-mcp",
            "version": "v6.18",
            "purpose": "把完成声明变成证据准入检查，证据不足默认拒绝",
            "required_by_class": REQUIRED_BY_CLASS,
        })

    @mcp.tool()
    def verify_completion(project: str, task: str, task_class: str, context_json: str) -> str:
        """Verify completion evidence without mutating task state."""
        context = _loads(context_json, {})
        result = _verify(task_class, context)
        return _json({"project": project, "task": task, **result})

    @mcp.tool()
    def issue_completion_certificate(project: str, task: str, task_class: str,
                                     context_json: str) -> str:
        """Write a completion certificate when evidence passes."""
        context = _loads(context_json, {})
        result = _verify(task_class, context)
        cert = {
            "id": f"cert-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "ts": _now(),
            "project": project,
            "task": task,
            "task_class": task_class,
            "accepted": result["passed"],
            "verifier": result,
        }
        path = _certificate_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cert, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "issued" if result["passed"] else "rejected", "path": str(path), "certificate": cert})

    return mcp


def main() -> None:
    build_server().run()
