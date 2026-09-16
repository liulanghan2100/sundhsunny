# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEV_MCP_DIR = next((p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("03_")), ROOT / "03_分工MCP")
sys.path.insert(0, str(DEV_MCP_DIR))

try:
    from offline_upgrade_mcp.common import (  # noqa: E402
        PLAN_PATH,
        SAFE_TASKS,
        _append_jsonl,
        _ensure,
        _make_queue_item,
        _now,
        _read_jsonl,
    )
    from task_queue_mcp.common import DAEMON_STOP, _save_task, _daemon_tick, _task_counts  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover
    if exc.name == "mcp":
        bundled = Path(r"C:\Users\sundh\AppData\Roaming\kimi-desktop\daimon-share\daimon\runtime\python\.venv\Scripts\python.exe")
        if bundled.exists() and os.environ.get("OFFLINE_UPGRADE_BOOTSTRAPPED") != "1":
            os.environ["OFFLINE_UPGRADE_BOOTSTRAPPED"] = "1"
            os.execv(str(bundled), [str(bundled), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit(
        "offline-upgrade needs the bundled Kimi Python runtime with the 'mcp' package installed."
    ) from exc


def write_plan(project: str) -> dict:
    _ensure()
    plan = {
        "project": project,
        "created": _now(),
        "mode": "user-space",
        "admin_privileges": "forbidden",
        "safe_tasks": SAFE_TASKS,
        "execution": {"runner": "task_queue_mcp", "max_tasks_per_tick": 1},
    }
    PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(PLAN_PATH.parent / "offline_upgrade_log.jsonl", {"event": "write_plan", "project": project, "ts": _now()})
    return {"status": "written", "path": str(PLAN_PATH)}


def enqueue(project: str) -> dict:
    queued = []
    for task in SAFE_TASKS:
        item = _make_queue_item(project, task)
        _save_task(item)
        queued.append({"id": item["id"], "title": task["title"]})
    _append_jsonl(PLAN_PATH.parent / "offline_upgrade_log.jsonl", {"event": "enqueue", "project": project, "queued": queued, "ts": _now()})
    return {"status": "queued", "queued": queued}


def status() -> dict:
    return {
        "plan_exists": PLAN_PATH.exists(),
        "counts": _task_counts(),
        "logs": len(_read_jsonl(PLAN_PATH.parent / "offline_upgrade_log.jsonl")),
        "pending_approvals": _read_jsonl(PLAN_PATH.parent / "approval_queue.jsonl"),
    }


def loop(max_ticks: int, interval_seconds: int, max_tasks: int) -> dict:
    history = []
    for idx in range(max(1, int(max_ticks))):
        if DAEMON_STOP.exists():
            break
        result = _daemon_tick(max_tasks)
        result["tick"] = idx + 1
        history.append(result)
        if idx < max_ticks - 1 and not DAEMON_STOP.exists():
            time.sleep(max(1, int(interval_seconds)))
    return {
        "status": "completed" if not DAEMON_STOP.exists() else "stopped",
        "ticks": len(history),
        "history": history,
        "counts": _task_counts(),
        "admin_privileges": "not_requested",
    }


def _parse_until(value: str) -> datetime:
    now = datetime.now()
    text = value.strip()
    if "T" in text:
        target = datetime.fromisoformat(text)
    else:
        hour, minute = [int(part) for part in text.split(":", 1)]
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
    return target


def run_until(until: str, interval_seconds: int, max_tasks: int) -> dict:
    target = _parse_until(until)
    if DAEMON_STOP.exists():
        DAEMON_STOP.unlink()
    history = []
    while datetime.now() < target:
        result = _daemon_tick(max_tasks)
        result["tick"] = len(history) + 1
        history.append(result)
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(max(1, int(interval_seconds)), remaining))
    return {
        "status": "completed" if datetime.now() < target else "deadline_reached",
        "until": target.isoformat(timespec="seconds"),
        "ticks": len(history),
        "history": history[-10:],
        "counts": _task_counts(),
        "admin_privileges": "not_requested",
    }


def resume() -> dict:
    if DAEMON_STOP.exists():
        DAEMON_STOP.unlink()
        return {"status": "resumed", "stop_file_removed": str(DAEMON_STOP)}
    return {"status": "already_running", "stop_file": str(DAEMON_STOP)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline user-space Agent upgrade runner.")
    parser.add_argument("command", choices=["plan", "enqueue", "status", "tick", "loop", "run-until", "resume"])
    parser.add_argument("--project", default="manual-agent-os-offline-upgrade")
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument("--max-ticks", type=int, default=5)
    parser.add_argument("--interval-seconds", type=int, default=2)
    parser.add_argument("--until", default="07:30")
    args = parser.parse_args()

    if args.command == "plan":
        result = write_plan(args.project)
    elif args.command == "enqueue":
        result = enqueue(args.project)
    elif args.command == "tick":
        result = _daemon_tick(args.max_tasks)
    elif args.command == "loop":
        result = loop(args.max_ticks, args.interval_seconds, args.max_tasks)
    elif args.command == "run-until":
        result = run_until(args.until, args.interval_seconds, args.max_tasks)
    elif args.command == "resume":
        result = resume()
    else:
        result = status()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
