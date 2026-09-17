# -*- coding: utf-8 -*-
"""Runtime Middleware MCP server.

v6.8 composes the Agent OS runtime checks into a middleware stack contract.
It does not execute external actions; it validates that required evidence is
present before a task is accepted.
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
MIDDLEWARE_DIR = DATA_ROOT / "09_投研" / "runtime_middleware"
STACK_FILE = MIDDLEWARE_DIR / "middleware_stacks.jsonl"
REPORT_DIR = MIDDLEWARE_DIR / "reports"

CLASS_STACKS = {
    "A": ["cognitive_intake"],
    "B": ["cognitive_intake", "tool_lifecycle_tracing", "minimum_validation"],
    "C": [
        "cognitive_intake",
        "preflight_bundle",
        "pre_research",
        "failure_replay",
        "memory_consolidation",
        "workflow_runtime",
        "tool_lifecycle_tracing",
        "evaluation_harness",
        "local_regression_gate",
        "completion_verifier",
        "manual_gates",
        "backup",
    ],
    "D": ["cognitive_intake", "risk_blocker"],
}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _append(record: dict) -> dict:
    STACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with STACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _required_evidence(middleware: str) -> list[str]:
    return {
        "cognitive_intake": ["cognitive_intake", "task_class"],
        "preflight_bundle": ["preflight_bundle", "preflight_go"],
        "pre_research": ["pre_research_report"],
        "failure_replay": ["failure_replay", "avoidance_plan"],
        "memory_consolidation": ["consolidated_memory"],
        "workflow_runtime": ["execution_card", "workflow"],
        "tool_lifecycle_tracing": ["tool_lifecycle", "lifecycle_integrity"],
        "evaluation_harness": ["eval_run", "eval_score"],
        "local_regression_gate": ["local_regression_gate", "regression_passed"],
        "completion_verifier": ["completion_verifier", "completion_certificate"],
        "manual_gates": ["gate_report", "manual_gates"],
        "backup": ["backup_path"],
        "minimum_validation": ["minimum_validation"],
        "risk_blocker": ["hard_blockers", "blocked"],
    }.get(middleware, [middleware])


def _context_text(context: dict) -> str:
    return json.dumps(context, ensure_ascii=False).lower()


def _check_context(task_class: str, context: dict) -> dict:
    stack = CLASS_STACKS.get(task_class, CLASS_STACKS["A"])
    text = _context_text(context)
    checks = []
    for middleware in stack:
        evidence = _required_evidence(middleware)
        present = [item for item in evidence if item.lower() in text]
        missing = [item for item in evidence if item not in present]
        checks.append({
            "middleware": middleware,
            "required_evidence": evidence,
            "present": present,
            "missing": missing,
            "passed": not missing,
        })
    passed = all(item["passed"] for item in checks)
    return {
        "task_class": task_class,
        "stack": stack,
        "passed": passed,
        "checks": checks,
        "missing_middleware": [item["middleware"] for item in checks if not item["passed"]],
    }


def build_server() -> FastMCP:
    mcp = FastMCP("runtime-middleware-mcp")

    @mcp.tool()
    def runtime_middleware_brief() -> str:
        """Describe runtime middleware stack."""
        return _json({
            "name": "runtime-middleware-mcp",
            "version": "v6.8",
            "purpose": "把认知入口、调研、失败回放、记忆、追踪、评估、门禁、备份组织成任务级中间件栈",
            "class_stacks": CLASS_STACKS,
            "storage": str(MIDDLEWARE_DIR),
        })

    @mcp.tool()
    def build_middleware_stack(project: str, task: str, task_class: str = "C") -> str:
        """Build and record middleware stack for a task class."""
        stack = CLASS_STACKS.get(task_class, CLASS_STACKS["C"])
        record = {
            "id": f"stack-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "ts": _now(),
            "project": project,
            "task": task,
            "task_class": task_class,
            "stack": stack,
            "required_evidence": {item: _required_evidence(item) for item in stack},
        }
        _append(record)
        return _json({"status": "built", "stack": record})

    @mcp.tool()
    def validate_middleware_context(project: str, task_class: str, context_json: str) -> str:
        """Validate whether a task context contains required middleware evidence."""
        context = _loads(context_json, {})
        result = _check_context(task_class, context)
        result["project"] = project
        return _json(result)

    @mcp.tool()
    def middleware_gap_report(project: str, task: str, task_class: str, context_json: str,
                              output_path: str = "") -> str:
        """Write a middleware gap report for acceptance review."""
        result = _check_context(task_class, _loads(context_json, {}))
        if not output_path:
            output_path = str(REPORT_DIR / f"{_safe_project(project)}_middleware_gap_report.md")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Runtime Middleware Gap Report",
            "",
            f"- Project: {project}",
            f"- Task: {task}",
            f"- Task class: {task_class}",
            f"- Generated: {_now()}",
            f"- Passed: {result['passed']}",
            "",
            "## Checks",
            "",
        ]
        for item in result["checks"]:
            lines.append(f"- {item['middleware']}: passed={item['passed']} missing={json.dumps(item['missing'], ensure_ascii=False)}")
        path.write_text("\n".join(lines), encoding="utf-8")
        return _json({"status": "written", "path": str(path), **result})

    return mcp


def main() -> None:
    build_server().run()
