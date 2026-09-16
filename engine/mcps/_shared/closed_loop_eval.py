# -*- coding: utf-8 -*-
"""Pure helper layer for closed-loop eval bookkeeping."""
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def task_id(suffix: str) -> str:
    return f"task-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}-{suffix}"


def make_task_payload(project: str, name: str, task: str, context: dict | None = None,
                      max_attempts: int = 1, risk: str = "normal",
                      operation: str = "local_mcp") -> dict:
    ts = now()
    return {
        "id": task_id(name),
        "project": project,
        "task": task,
        "status": "queued",
        "priority": 0,
        "risk": risk,
        "track": "standard",
        "autonomy": "L3",
        "operation": operation,
        "attempts": 0,
        "max_attempts": max_attempts,
        "context": context or {},
        "result": {},
        "created": ts,
        "updated": ts,
        "started": None,
        "ended": None,
    }


def case_record(project: str, case: dict, source: str) -> dict:
    return {
        **case,
        "ts": now(),
        "type": "eval_case",
        "project": project,
        "source": source,
        "weight": 1.0,
    }


def check_payload(case_id: str, passed: bool, evidence: object) -> dict:
    return {
        "case_id": case_id,
        "passed": bool(passed),
        "evidence": evidence,
    }


def run_payload(project: str, suite: str, results: list[dict], created_cases: list[dict]) -> dict:
    passed = sum(1 for item in results if item["passed"])
    return {
        "id": f"evalrun-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": now(),
        "type": "eval_run",
        "project": project,
        "suite": suite,
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "score": round(passed / len(results), 4) if results else 0,
        "created_cases": [case["id"] for case in created_cases],
        "results": results,
    }


def cli_summary(run: dict, created_cases: list[dict], cases_path: str, runs_path: str) -> dict:
    return {
        "status": "passed" if run["failed"] == 0 else "failed",
        "project": run["project"],
        "case_count": run["case_count"],
        "passed": run["passed"],
        "failed": run["failed"],
        "score": run["score"],
        "created_cases": len(created_cases),
        "run_id": run["id"],
        "cases_path": cases_path,
        "runs_path": runs_path,
    }
