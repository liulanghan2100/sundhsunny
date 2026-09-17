# -*- coding: utf-8 -*-
"""Video Generation MCP server.

Provides a reusable Agent OS-level wrapper around the short-drama video API
adapter. It keeps live calls explicit and dry-run as the default.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.io import _write_json as shared_write_json
from _shared.state import safe_project
from _shared.time import _now as shared_now

from dashboard_mcp.common import _collect as _collect_dashboard
from dashboard_mcp.common import _write_dashboard
from experience_memory_mcp.common import _append as _memory_append
from mandatory_runtime_hook_mcp.common import _mandatory_cycle

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"


def _find_named_dir(prefix: str, canonical: str) -> Path:
    """在运行时数据区定位目录，找不到就按规范名建一个。

    参数 canonical 可能是通配符形式（如 "03_*MCP"），
    这里会剥掉通配符字符再用 —— 否则 Windows 建目录会报
    WinError 123（文件名含非法字符）。

    为什么不搜包根：打包后包根是源码区，不该往里写运行时数据。
    """
    if not DATA_ROOT.is_dir():
        DATA_ROOT.mkdir(parents=True, exist_ok=True)

    # 规范名去掉通配符，作为建目录用的合法名
    safe = canonical.replace("*", "").replace("?", "").strip("_\/") or "data"

    for p in sorted(DATA_ROOT.iterdir()):
        if p.is_dir() and p.name == safe:
            return p
    for p in sorted(DATA_ROOT.iterdir()):
        if p.is_dir() and p.name.startswith(prefix):
            return p

    out = DATA_ROOT / safe
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError:
        out = DATA_ROOT / prefix.rstrip("_")
        out.mkdir(parents=True, exist_ok=True)
    return out

RESEARCH_DIR = _find_named_dir("09_", "09_投研")
PROJECT_DIR = _find_named_dir("08_", "08_*")
DEFAULT_SHORTDRAMA_PROJECT = PROJECT_DIR / "zhuxian-shortdrama-episode01-concept"
VIDEO_ROOT = RESEARCH_DIR / "video_generation_mcp"
PROVIDERS = {
    "hailuo": "MINIMAX_API_KEY",
    "runway": "RUNWAY_API_KEY",
    "veo": "GEMINI_API_KEY",
    "kling": "KLING_API_KEY",
}


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _safe_name(name: str) -> str:
    return safe_project(name, allowed="-_.", default="default")


def _project_path(project_path: str = "") -> Path:
    path = Path(project_path) if project_path else DEFAULT_SHORTDRAMA_PROJECT
    if not path.is_absolute():
        path = ROOT / path
    return path


def _status_path(project: str) -> Path:
    return VIDEO_ROOT / _safe_name(project) / "video_generation_status.json"


def _report_dir(project: str) -> Path:
    return VIDEO_ROOT / _safe_name(project)


def _write(path: Path, data: dict) -> str:
    return shared_write_json(path, data)


def _key_status() -> dict:
    status = {provider: {"env": env, "configured": bool(os.environ.get(env))} for provider, env in PROVIDERS.items()}
    status["ready_providers"] = [p for p, item in status.items() if isinstance(item, dict) and item["configured"]]
    status["live_generation_ready"] = bool(status["ready_providers"])
    return status


def _run_adapter(args: list[str], project_path: str = "") -> dict:
    project = _project_path(project_path)
    script = project / "scripts" / "video_api_adapter.py"
    if not script.exists():
        return {"status": "failed", "error": f"adapter not found: {script}"}
    proc = subprocess.run([sys.executable, str(script), *args], cwd=str(project), text=True, capture_output=True, timeout=180)
    if proc.returncode != 0:
        return {"status": "failed", "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"stdout": proc.stdout}
    return {"status": "completed", "result": data}


def _run_project_script(script_name: str, args: list[str], project_path: str = "") -> dict:
    project = _project_path(project_path)
    script = project / "scripts" / script_name
    if not script.exists():
        return {"status": "failed", "error": f"script not found: {script}"}
    proc = subprocess.run([sys.executable, str(script), *args], cwd=str(project), text=True, capture_output=True, timeout=180)
    if proc.returncode != 0:
        return {"status": "failed", "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"stdout": proc.stdout}
    return {"status": "completed", "result": data}


def _refresh_dashboard() -> dict:
    try:
        return _write_dashboard(_collect_dashboard())
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def _record(project: str, task: str, status: str, result: dict) -> dict:
    try:
        return _memory_append({
            "type": "outcome",
            "project": project,
            "task": task,
            "status": status,
            "tests": ["video_generation_mcp", "video_api_adapter"],
            "issues": result.get("errors", []),
            "gate_status": "manual-gates required",
            "result": result,
            "lesson": "Video generation should default to dry-run and require explicit live=true plus environment API keys.",
            "next_retrieval_query": "video generation MCP dry-run live API key shortdrama",
        })
    except Exception as exc:
        return {"status": "memory_failed", "error": str(exc)}


def build_server() -> FastMCP:
    mcp = FastMCP("video-generation-mcp")

    @mcp.tool()
    def video_generation_brief() -> str:
        """Describe video generation MCP capabilities."""
        return _json({
            "name": "video-generation-mcp",
            "version": "v5.20",
            "purpose": "Agent OS-level wrapper for short-drama AI video generation providers",
            "providers": list(PROVIDERS),
            "default_mode": "dry-run",
            "live_call_rule": "requires live=true and provider API key in environment",
            "default_project": str(DEFAULT_SHORTDRAMA_PROJECT),
            "storage_root": str(VIDEO_ROOT),
        })

    @mcp.tool()
    def video_api_key_status() -> str:
        """Return provider API key status without printing secrets."""
        status = _key_status()
        _write(VIDEO_ROOT / "api_key_status.json", {"generated": _now(), **status})
        return _json(status)

    @mcp.tool()
    def prepare_video_requests(project: str = "zhuxian-shortdrama-episode01-concept",
                               project_path: str = "", provider: str = "hailuo",
                               limit: int = 3) -> str:
        """Generate provider request JSON files in dry-run mode."""
        if provider not in PROVIDERS:
            return _json({"status": "failed", "error": f"unsupported provider: {provider}"})
        governed = _mandatory_cycle(
            project=project,
            task=f"prepare dry-run video requests for {provider}",
            risk="normal",
            approved=False,
            track="quick",
            autonomy="L3",
            tool="video_generation_mcp.prepare_video_requests",
            node_id=17,
            context={"provider": provider, "limit": limit, "live": False},
        )
        result = _run_adapter(["submit", "--provider", provider, "--limit", str(limit)], project_path)
        payload = {"project": project, "provider": provider, "mandatory": governed, **result}
        _write(_status_path(project), {"generated": _now(), **payload})
        _record(project, "prepare video requests", result.get("status", "unknown"), payload)
        _refresh_dashboard()
        return _json(payload)

    @mcp.tool()
    def submit_video_generation(project: str = "zhuxian-shortdrama-episode01-concept",
                                project_path: str = "", provider: str = "hailuo",
                                limit: int = 1, live: bool = False) -> str:
        """Submit video generation jobs. Dry-run by default; live requires keys."""
        if provider not in PROVIDERS:
            return _json({"status": "failed", "error": f"unsupported provider: {provider}"})
        if live and not os.environ.get(PROVIDERS[provider]):
            return _json({
                "status": "blocked",
                "reason": f"missing environment variable {PROVIDERS[provider]}",
                "live": live,
                "provider": provider,
            })
        governed = _mandatory_cycle(
            project=project,
            task=f"{'live' if live else 'dry-run'} video generation submit for {provider}",
            risk="high" if live else "normal",
            approved=False,
            track="quick",
            autonomy="L3",
            tool="video_generation_mcp.submit_video_generation",
            node_id=17,
            context={"provider": provider, "limit": limit, "live": live},
        )
        args = ["submit", "--provider", provider, "--limit", str(limit)]
        if live:
            args.append("--live")
        result = _run_adapter(args, project_path)
        payload = {"project": project, "provider": provider, "live": live, "mandatory": governed, **result}
        _write(_status_path(project), {"generated": _now(), **payload})
        _record(project, "submit video generation", result.get("status", "unknown"), payload)
        _refresh_dashboard()
        return _json(payload)

    @mcp.tool()
    def query_video_generation(project: str = "zhuxian-shortdrama-episode01-concept",
                               project_path: str = "", provider: str = "hailuo",
                               task_id: str = "", live: bool = False) -> str:
        """Query provider task status."""
        if not task_id:
            return _json({"status": "failed", "error": "task_id is required"})
        args = ["query", "--provider", provider, "--task-id", task_id]
        if live:
            args.append("--live")
        result = _run_adapter(args, project_path)
        payload = {"project": project, "provider": provider, "task_id": task_id, "live": live, **result}
        _write(_report_dir(project) / f"query_{provider}_{_safe_name(task_id)}.json", {"generated": _now(), **payload})
        return _json(payload)

    @mcp.tool()
    def download_video_generation(project: str = "zhuxian-shortdrama-episode01-concept",
                                  project_path: str = "", provider: str = "hailuo",
                                  file_id: str = "", live: bool = False) -> str:
        """Download or retrieve provider output metadata."""
        if not file_id:
            return _json({"status": "failed", "error": "file_id is required"})
        args = ["download", "--provider", provider, "--file-id", file_id]
        if live:
            args.append("--live")
        result = _run_adapter(args, project_path)
        payload = {"project": project, "provider": provider, "file_id": file_id, "live": live, **result}
        _write(_report_dir(project) / f"download_{provider}_{_safe_name(file_id)}.json", {"generated": _now(), **payload})
        return _json(payload)

    @mcp.tool()
    def video_generation_status(project: str = "zhuxian-shortdrama-episode01-concept") -> str:
        """Return latest video generation MCP status."""
        path = _status_path(project)
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return _json({
            "project": project,
            "status_exists": path.exists(),
            "path": str(path),
            "state": state,
            "api_keys": _key_status(),
        })

    @mcp.tool()
    def production_readiness_audit(project: str = "zhuxian-shortdrama-episode01-concept",
                                   project_path: str = "", write_scaffold: bool = True) -> str:
        """Audit real short-drama production readiness and scaffold manifests."""
        args = ["--write-scaffold"] if write_scaffold else []
        result = _run_project_script("production_readiness_audit.py", args, project_path)
        payload = {"project": project, "write_scaffold": write_scaffold, **result}
        _write(_report_dir(project) / "production_readiness_audit.json", {"generated": _now(), **payload})
        _record(project, "production readiness audit", result.get("status", "unknown"), payload)
        _refresh_dashboard()
        return _json(payload)

    return mcp


def main() -> None:
    build_server().run()
