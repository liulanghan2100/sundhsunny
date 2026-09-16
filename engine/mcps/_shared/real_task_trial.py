# -*- coding: utf-8 -*-
"""Pure helpers for the real task trial shell."""
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def worker_script_text() -> str:
    return (
        "from pathlib import Path\n"
        "import json\n"
        "root = Path(__file__).resolve().parent\n"
        "summary = root / 'runtime_summary.md'\n"
        "summary.write_text('# Agent OS Real Task Trial\\n\\n"
        "- task card: required\\n"
        "- RunState: required\\n"
        "- completion verifier: required\\n"
        "- memory writeback: required\\n', encoding='utf-8')\n"
        "print(json.dumps({'summary': str(summary), 'status': 'written'}, ensure_ascii=False))\n"
    )


def task_payload(project: str, trial_dir, worker_path, summary_path) -> dict:
    ts = now()
    return {
        "id": f"task-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}-real-trial",
        "project": project,
        "task": "write a real Agent OS runtime trial summary artifact",
        "status": "queued",
        "priority": 10,
        "risk": "normal",
        "track": "standard",
        "autonomy": "L3",
        "operation": "local_mcp",
        "attempts": 0,
        "max_attempts": 1,
        "context": {
            "script": str(worker_path),
            "cwd": str(trial_dir),
            "expected_artifacts": [str(summary_path)],
            "timeout_seconds": 30,
            "acceptance_criteria": [
                "task queue executes local script",
                "summary artifact exists",
                "RunState records completion verifier and memory writeback",
                "dashboard refresh includes the run",
            ],
        },
        "result": {},
        "created": ts,
        "updated": ts,
        "started": None,
        "ended": None,
    }


def result_payload(result: dict, task: dict, run: dict, summary_path, trial_dir) -> dict:
    return {
        "status": result["status"],
        "task_id": task["id"],
        "run_id": run.get("run_id"),
        "summary_exists": summary_path.exists(),
        "decision": run.get("decision"),
        "completion_passed": (run.get("completion_verifier") or {}).get("passed"),
        "memory_writes": len(run.get("memory_writes", [])),
        "dashboard": result.get("dashboard", {}),
        "run_state_path": str(trial_dir.parent / "agent_os_runtime" / "runs" / f"{run.get('run_id')}.json"),
        "summary_path": str(summary_path),
    }
