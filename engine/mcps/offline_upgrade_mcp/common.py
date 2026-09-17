# -*- coding: utf-8 -*-
"""Offline upgrade MCP.

This module creates a low-risk local upgrade lane. It prepares small upgrade
tasks and sends only allowlisted work into task_queue_mcp. Anything risky is
written to an approval queue for the user.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from task_queue_mcp.common import _save_task
from _shared.io import _append_jsonl as shared_append_jsonl
from _shared.io import _json as shared_json
from _shared.time import _now as shared_now

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

DEV_MCP_DIR = _find_named_dir("03_", "03_*")
SKILL_DIR = _find_named_dir("04_", "04_*")
RESEARCH_DIR = _find_named_dir("09_", "09_投研")
OFFLINE_ROOT = RESEARCH_DIR / "offline_upgrade"
PLAN_PATH = OFFLINE_ROOT / "upgrade_plan.json"
LOG_PATH = OFFLINE_ROOT / "offline_upgrade_log.jsonl"
APPROVAL_PATH = OFFLINE_ROOT / "approval_queue.jsonl"

SAFE_TASKS = [
    {
        "key": "kb_report",
        "title": "Generate knowledge-base status report",
        "task": "Run knowledge-base report and record current quarantine/trusted counts.",
        "operation": "local_mcp",
        "risk": "low",
        "priority": 30,
        "context": {
            "offline_operation": "report_only",
            "script": str(SKILL_DIR / "knowledge-base" / "scripts" / "report.py"),
        },
    },
    {
        "key": "kb_rebuild_index",
        "title": "Rebuild knowledge-base FTS index",
        "task": "Rebuild local knowledge-base SQLite FTS index from meta.jsonl and Markdown files.",
        "operation": "local_mcp",
        "risk": "low",
        "priority": 25,
        "context": {
            "offline_operation": "local_index_rebuild",
            "script": str(SKILL_DIR / "knowledge-base" / "scripts" / "rebuild_index.py"),
        },
    },
    {
        "key": "manual_mcp_smoke",
        "title": "Run manual_mcp smoke test",
        "task": "Run manual_mcp smoke test through bundled Python runtime and record result.",
        "operation": "local_mcp",
        "risk": "normal",
        "priority": 20,
        "context": {
            "offline_operation": "smoke_test",
            "script": str(DEV_MCP_DIR / "smoke_test_mcp.py"),
            "requires_mcp_runtime": True,
        },
    },
]

RISKY_TASKS = [
    {
        "title": "Apply code refactor automatically",
        "reason": "code edits require diff review and task-specific tests",
    },
    {
        "title": "Install OS-level scheduled task or service",
        "reason": "service installation may require elevated privileges",
    },
    {
        "title": "Push commits to a remote repository",
        "reason": "remote side effects require explicit user approval",
    },
]


def _now() -> str:
    return shared_now()


def _json(data: dict) -> str:
    return shared_json(data)


def _ensure() -> None:
    OFFLINE_ROOT.mkdir(parents=True, exist_ok=True)
    for path in (LOG_PATH, APPROVAL_PATH):
        if not path.exists():
            path.write_text("", encoding="utf-8")


def _append_jsonl(path: Path, row: dict) -> None:
    _ensure()
    shared_append_jsonl(path, row, sort_keys=True)


def _task_id(key: str) -> str:
    return f"offline-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}-{key}"


def _make_queue_item(project: str, task: dict) -> dict:
    now = _now()
    return {
        "id": _task_id(task["key"]),
        "project": project,
        "task": task["task"],
        "status": "queued",
        "priority": int(task["priority"]),
        "risk": task["risk"],
        "track": "quick",
        "autonomy": "L3",
        "operation": task["operation"],
        "attempts": 0,
        "max_attempts": 1,
        "context": {"offline_upgrade": True, **task.get("context", {})},
        "result": {},
        "created": now,
        "updated": now,
        "started": None,
        "ended": None,
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def build_server() -> FastMCP:
    mcp = FastMCP("offline-upgrade-mcp")

    @mcp.tool()
    def offline_upgrade_brief() -> str:
        """Describe offline upgrade boundaries and artifacts."""
        return _json({
            "name": "offline_upgrade_mcp",
            "purpose": "local user-space offline upgrade planner",
            "offline_root": str(OFFLINE_ROOT),
            "plan": str(PLAN_PATH),
            "log": str(LOG_PATH),
            "approval_queue": str(APPROVAL_PATH),
            "boundaries": [
                "no administrator privileges",
                "no remote push",
                "no OS service install",
                "no high-risk automatic code edits",
            ],
            "safe_tasks": SAFE_TASKS,
            "risky_tasks": RISKY_TASKS,
        })

    @mcp.tool()
    def write_upgrade_plan(project: str = "manual-agent-os-offline-upgrade") -> str:
        """Write the offline upgrade plan file."""
        _ensure()
        plan = {
            "project": project,
            "created": _now(),
            "mode": "user-space",
            "admin_privileges": "forbidden",
            "safe_tasks": SAFE_TASKS,
            "approval_required": RISKY_TASKS,
            "execution": {
                "runner": "task_queue_mcp",
                "max_tasks_per_tick": 1,
                "default_track": "quick",
                "default_autonomy": "L3",
            },
        }
        PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        _append_jsonl(LOG_PATH, {"event": "write_upgrade_plan", "project": project, "ts": _now(), "path": str(PLAN_PATH)})
        return _json({"status": "written", "path": str(PLAN_PATH), "safe_task_count": len(SAFE_TASKS)})

    @mcp.tool()
    def enqueue_safe_upgrade_tasks(project: str = "manual-agent-os-offline-upgrade") -> str:
        """Enqueue allowlisted offline upgrade tasks through task_queue_mcp."""
        _ensure()
        queued = []
        for task in SAFE_TASKS:
            item = _make_queue_item(project, task)
            _save_task(item)
            queued.append({"id": item["id"], "title": task["title"], "operation": task["operation"]})
        _append_jsonl(LOG_PATH, {"event": "enqueue_safe_upgrade_tasks", "project": project, "ts": _now(), "queued": queued})
        return _json({"status": "queued", "queued": queued})

    @mcp.tool()
    def write_approval_item(title: str, reason: str, details_json: str = "{}") -> str:
        """Write a high-risk item for user approval instead of executing it."""
        try:
            details = json.loads(details_json) if details_json else {}
        except json.JSONDecodeError:
            details = {"raw": details_json}
        row = {"id": _task_id("approval"), "title": title, "reason": reason, "details": details, "status": "pending", "ts": _now()}
        _append_jsonl(APPROVAL_PATH, row)
        _append_jsonl(LOG_PATH, {"event": "write_approval_item", "approval_id": row["id"], "ts": _now()})
        return _json({"status": "pending_approval", "item": row, "path": str(APPROVAL_PATH)})

    @mcp.tool()
    def offline_upgrade_status() -> str:
        """Return offline upgrade plan, log count, and pending approvals."""
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8")) if PLAN_PATH.exists() else {}
        logs = _read_jsonl(LOG_PATH)
        approvals = _read_jsonl(APPROVAL_PATH)
        return _json({
            "offline_root": str(OFFLINE_ROOT),
            "plan_exists": PLAN_PATH.exists(),
            "plan": plan,
            "log_count": len(logs),
            "pending_approvals": [x for x in approvals if x.get("status") == "pending"],
        })

    return mcp


def main() -> None:
    build_server().run()
