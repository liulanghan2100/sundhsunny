# -*- coding: utf-8 -*-
"""Health Check MCP server.

Provides self-audit for the manual-agent OS: MCP inventory, smoke test
availability/execution, manual-gates status, evidence directories, backups, and
static health reports.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
MCP_DIR = DATA_ROOT / "03_分工MCP"
PROJECT_DIR = DATA_ROOT / "04_技能包" / "manual-gates" / "scripts" / "manual_mcp" / "projects"
RESEARCH_DIR = DATA_ROOT / "09_投研"
BACKUP_DIR = DATA_ROOT / "10_备份"
HEALTH_DIR = RESEARCH_DIR / "health_check"


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def _mcp_inventory() -> list[dict]:
    rows = []
    for path in sorted(MCP_DIR.glob("*_mcp")):
        if not path.is_dir():
            continue
        runner = [p.name for p in path.glob("run_*.py")]
        rows.append({
            "name": path.name,
            "path": str(path),
            "has_common": (path / "common.py").exists(),
            "has_runner": bool(runner),
            "runner": runner,
            "has_readme": (path / "README.md").exists(),
        })
    return rows


def _smoke_inventory() -> list[dict]:
    rows = []
    for path in sorted(MCP_DIR.glob("smoke_test_*.py")):
        rows.append({
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
        })
    return rows


def _manual_gate_summary() -> list[dict]:
    rows = []
    for state_path in sorted(PROJECT_DIR.glob("*/state.json")):
        state = _read_json(state_path)
        nodes = state.get("nodes", {}) if isinstance(state, dict) else {}
        passed = sum(1 for node in nodes.values() if node.get("status") == "passed")
        total = len(nodes)
        rows.append({
            "project": state.get("project", state_path.parent.name),
            "dir": state_path.parent.name,
            "track": state.get("track", ""),
            "autonomy": state.get("autonomy", ""),
            "progress": f"{passed}/{total}" if total else "0/0",
            "passed": passed,
            "total": total,
            "complete": bool(total and passed == total),
            "path": str(state_path),
        })
    rows.sort(key=lambda r: (r["complete"], r["project"]), reverse=True)
    return rows


def _evidence_status() -> dict:
    expected = [
        "agent_orchestration",
        "agent_runtime_kernel",
        "dashboard",
        "experience_memory",
        "git_ci",
        "hook_runtime",
        "trace_observability",
        "workflow_runtime",
    ]
    dirs = {}
    for name in expected:
        path = RESEARCH_DIR / name
        files = list(path.rglob("*")) if path.exists() else []
        dirs[name] = {
            "exists": path.exists(),
            "path": str(path),
            "file_count": sum(1 for p in files if p.is_file()),
        }
    return dirs


def _backup_status(limit: int = 20) -> dict:
    files = sorted([p for p in BACKUP_DIR.glob("*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "backup_dir_exists": BACKUP_DIR.exists(),
        "count": len(files),
        "latest": [{
            "name": p.name,
            "path": str(p),
            "size": p.stat().st_size,
            "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        } for p in files[:limit]],
    }


def _run_smoke(path: Path, timeout: int = 60) -> dict:
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return {
        "name": path.name,
        "path": str(path),
        "returncode": proc.returncode,
        "status": "passed" if proc.returncode == 0 else "failed",
        "stdout": proc.stdout.strip()[-2000:],
        "stderr": proc.stderr.strip()[-2000:],
    }


def _collect(run_smokes: bool = False, smoke_names: list[str] | None = None) -> dict:
    smokes = _smoke_inventory()
    smoke_results = []
    if run_smokes:
        wanted = set(smoke_names or [])
        for smoke in smokes:
            if wanted and smoke["name"] not in wanted:
                continue
            try:
                smoke_results.append(_run_smoke(Path(smoke["path"])))
            except Exception as exc:
                smoke_results.append({"name": smoke["name"], "path": smoke["path"], "status": "failed", "error": str(exc)})
    mcps = _mcp_inventory()
    gates = _manual_gate_summary()
    evidence = _evidence_status()
    backups = _backup_status()
    failed_smokes = [r for r in smoke_results if r.get("status") != "passed"]
    missing_mcp = [m for m in mcps if not (m["has_common"] and m["has_runner"])]
    incomplete_gates = [g for g in gates if g["project"].startswith("manual-agent-os-v") and not g["complete"]]
    missing_evidence = [name for name, rec in evidence.items() if not rec["exists"]]
    health = "passed"
    if missing_mcp or incomplete_gates or missing_evidence or failed_smokes or backups["count"] == 0:
        health = "attention"
    return {
        "generated": _now(),
        "root": str(ROOT),
        "health": health,
        "mcp_inventory": mcps,
        "smoke_inventory": smokes,
        "smoke_results": smoke_results,
        "manual_gates": gates,
        "evidence": evidence,
        "backups": backups,
        "findings": {
            "missing_mcp_structure": missing_mcp,
            "incomplete_manual_agent_projects": incomplete_gates,
            "missing_evidence_dirs": missing_evidence,
            "failed_smokes": failed_smokes,
            "backup_count": backups["count"],
        },
    }


def _write_report(data: dict, output_dir: str = "") -> dict:
    out = Path(output_dir) if output_dir else HEALTH_DIR
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "health_report.json"
    md_path = out / "health_report.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Manual Agent OS Health Report",
        "",
        f"- Generated: {data['generated']}",
        f"- Health: {data['health']}",
        f"- MCP modules: {len(data['mcp_inventory'])}",
        f"- Smoke tests: {len(data['smoke_inventory'])}",
        f"- Manual-gates projects: {len(data['manual_gates'])}",
        f"- Backups: {data['backups']['count']}",
        "",
        "## Findings",
        "",
        f"- Missing MCP structure: {len(data['findings']['missing_mcp_structure'])}",
        f"- Incomplete manual-agent projects: {len(data['findings']['incomplete_manual_agent_projects'])}",
        f"- Missing evidence dirs: {len(data['findings']['missing_evidence_dirs'])}",
        f"- Failed smokes: {len(data['findings']['failed_smokes'])}",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def build_server() -> FastMCP:
    mcp = FastMCP("health-check-mcp")

    @mcp.tool()
    def health_brief() -> str:
        """Describe health-check capabilities."""
        return _json({
            "name": "health-check-mcp",
            "version": "v5.8",
            "purpose": "self-audit MCP inventory, smoke tests, manual-gates status, evidence dirs, and backups",
            "default_output": str(HEALTH_DIR),
        })

    @mcp.tool()
    def health_snapshot() -> str:
        """Collect health snapshot without running smoke tests."""
        return _json(_collect(run_smokes=False))

    @mcp.tool()
    def run_health_smokes(smoke_names_json: str = "[]") -> str:
        """Run selected smoke tests, or all when smoke_names_json is empty."""
        names = json.loads(smoke_names_json) if smoke_names_json else []
        return _json(_collect(run_smokes=True, smoke_names=names))

    @mcp.tool()
    def write_health_report(output_dir: str = "", run_smokes: bool = False,
                            smoke_names_json: str = "[]") -> str:
        """Write JSON and Markdown health report."""
        names = json.loads(smoke_names_json) if smoke_names_json else []
        data = _collect(run_smokes=run_smokes, smoke_names=names)
        paths = _write_report(data, output_dir)
        return _json({"status": "written", **paths, "health": data["health"]})

    @mcp.tool()
    def health_report_status(output_dir: str = "") -> str:
        """Return health report file status."""
        out = Path(output_dir) if output_dir else HEALTH_DIR
        json_path = out / "health_report.json"
        md_path = out / "health_report.md"
        return _json({
            "json_exists": json_path.exists(),
            "markdown_exists": md_path.exists(),
            "json_path": str(json_path),
            "markdown_path": str(md_path),
            "json_size": json_path.stat().st_size if json_path.exists() else 0,
            "markdown_size": md_path.stat().st_size if md_path.exists() else 0,
        })

    return mcp


def main() -> None:
    build_server().run()
