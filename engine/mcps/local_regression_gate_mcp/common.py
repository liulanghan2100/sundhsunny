# -*- coding: utf-8 -*-
"""Local Regression Gate MCP server.

v6.17 provides a local CI-like gate for Agent OS changes. It collects safe
compile checks and smoke tests into one auditable report without remote CI,
admin permissions, package installs, or destructive actions.
"""
import json
import py_compile
import subprocess
import sys
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
RESEARCH = DATA_ROOT / "09_投研"
REGRESSION_DIR = RESEARCH / "local_regression_gate"
RUNS_FILE = REGRESSION_DIR / "regression_runs.jsonl"
REPORT_DIR = REGRESSION_DIR / "reports"

DEFAULT_COMPILE_TARGETS = [
    "03_分工MCP/mandatory_runtime_hook_mcp/common.py",
    "03_分工MCP/preflight_bundle_mcp/common.py",
    "03_分工MCP/runtime_middleware_mcp/common.py",
    "03_分工MCP/local_regression_gate_mcp/common.py",
]

DEFAULT_SMOKE_TESTS = [
    "Agent_OS_Core/agent_os.py delegate smoke run preflight-bundle-mcp --execute",
    "Agent_OS_Core/agent_os.py delegate smoke run mandatory-runtime-hook-mcp --execute",
]


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _append(record: dict) -> None:
    shared_append_jsonl(RUNS_FILE, record)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _safe_rel(path: str) -> Path:
    candidate = (ROOT / path).resolve()
    if ROOT.resolve() not in candidate.parents and candidate != ROOT.resolve():
        raise ValueError(f"path outside workspace is not allowed: {path}")
    return candidate


def _run_cmd(label: str, args: list[str], timeout: int = 90) -> dict:
    started = _now()
    try:
        proc = subprocess.run(
            args,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        return {
            "label": label,
            "started": started,
            "finished": _now(),
            "passed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "label": label,
            "started": started,
            "finished": _now(),
            "passed": False,
            "returncode": "timeout",
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }


def _policy_parse_check() -> dict:
    path = _safe_rel("09_投研/control_plane/policy.json")
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return {"label": "policy_json_parse", "passed": True, "path": str(path)}
    except Exception as exc:
        return {"label": "policy_json_parse", "passed": False, "path": str(path), "error": str(exc)}


def _compile_check(target: str) -> dict:
    path = _safe_rel(target)
    started = _now()
    try:
        py_compile.compile(str(path), doraise=True)
        return {
            "label": f"py_compile:{target}",
            "started": started,
            "finished": _now(),
            "passed": True,
            "path": str(path),
        }
    except Exception as exc:
        return {
            "label": f"py_compile:{target}",
            "started": started,
            "finished": _now(),
            "passed": False,
            "path": str(path),
            "error": str(exc),
        }


def _write_report(run: dict) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{run['id']}.md"
    lines = [
        "# Local Regression Gate Report",
        "",
        f"- Run: {run['id']}",
        f"- Project: {run['project']}",
        f"- Generated: {run['ts']}",
        f"- Passed: {run['passed']}",
        f"- Checks: {run['passed_checks']}/{run['check_count']}",
        "",
        "## Checks",
        "",
    ]
    for check in run["checks"]:
        lines.append(f"- {check['label']}: passed={check['passed']} returncode={check.get('returncode', '')}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _run_gate(project: str, compile_targets: list[str], smoke_tests: list[str], include_policy: bool) -> dict:
    checks = []
    for target in compile_targets:
        checks.append(_compile_check(target))
    if include_policy:
        checks.append(_policy_parse_check())
    for test in smoke_tests:
        path = _safe_rel(test)
        checks.append(_run_cmd(f"smoke:{test}", [sys.executable, str(path)], timeout=120))
    run = {
        "id": f"regression-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "type": "local_regression_gate_run",
        "check_count": len(checks),
        "passed_checks": sum(1 for check in checks if check.get("passed")),
        "failed_checks": sum(1 for check in checks if not check.get("passed")),
        "passed": all(check.get("passed") for check in checks),
        "checks": checks,
    }
    run["report_path"] = _write_report(run)
    _append(run)
    return run


def build_server() -> FastMCP:
    mcp = FastMCP("local-regression-gate-mcp")

    @mcp.tool()
    def local_regression_gate_brief() -> str:
        """Describe local regression gate."""
        return _json({
            "name": "local-regression-gate-mcp",
            "version": "v6.17",
            "safe_scope": ["py_compile", "smoke_tests", "policy_parse", "local_reports"],
            "forbidden": ["admin_permission", "package_install", "git_push", "remote_pr", "production_deploy"],
            "storage": str(RUNS_FILE),
        })

    @mcp.tool()
    def run_local_regression_gate(project: str,
                                  compile_targets_json: str = "",
                                  smoke_tests_json: str = "",
                                  include_policy: bool = True) -> str:
        """Run safe local regression checks and write a report."""
        compile_targets = _loads(compile_targets_json, DEFAULT_COMPILE_TARGETS) if compile_targets_json else DEFAULT_COMPILE_TARGETS
        smoke_tests = _loads(smoke_tests_json, DEFAULT_SMOKE_TESTS) if smoke_tests_json else DEFAULT_SMOKE_TESTS
        return _json(_run_gate(project, compile_targets, smoke_tests, include_policy))

    @mcp.tool()
    def local_regression_gate_report(project: str = "") -> str:
        """Return recent local regression gate runs."""
        rows = _read_jsonl(RUNS_FILE)
        if project:
            rows = [row for row in rows if row.get("project") == project]
        return _json({
            "project": project or "all",
            "run_count": len(rows),
            "latest": rows[-1] if rows else None,
            "passed_runs": sum(1 for row in rows if row.get("passed")),
            "failed_runs": sum(1 for row in rows if not row.get("passed")),
            "storage": str(RUNS_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
