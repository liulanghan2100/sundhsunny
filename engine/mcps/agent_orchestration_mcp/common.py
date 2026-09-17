# -*- coding: utf-8 -*-
"""Agent Orchestration MCP server.

v5.6 keeps the role/handoff layer and adds a local parallel execution runtime.
It can run safe command tasks concurrently, record simulated agent results, and
export an auditable report. It does not bypass manual-gates.
"""
import concurrent.futures
import json
import subprocess
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
CONFIG_DIR = DATA_ROOT / "09_投研" / "agent_orchestration"
RUN_DIR = CONFIG_DIR / "parallel_runs"

AGENTS = {
    "research-agent": {
        "mission": "External research, source review, candidate comparison",
        "tools": ["research-mcp", "web", "experience-memory.search"],
        "manual_nodes": [2, 8, 11, 15],
    },
    "planning-agent": {
        "mission": "Scope, WBS, schedule, risk, and track selection",
        "tools": ["manual-gates", "workflow-runtime"],
        "manual_nodes": [4, 12, 13],
    },
    "dev-agent": {
        "mission": "Implement the smallest viable change and run local checks",
        "tools": ["filesystem", "tests", "manual-gates"],
        "manual_nodes": [14, 15, 16, 17],
    },
    "qa-agent": {
        "mission": "Smoke/SIT/UAT evidence, regression and acceptance checks",
        "tools": ["tests", "manual-gates", "experience-memory.record"],
        "manual_nodes": [17, 18, 19, 20, 21],
    },
    "security-agent": {
        "mission": "Permission, config, dependency, release, and remote-write risk review",
        "tools": ["git-ci", "manual-gates", "research-mcp"],
        "manual_nodes": [20, 22, 23],
    },
    "review-agent": {
        "mission": "Adversarial review, revoke risk, and evidence-chain checks",
        "tools": ["manual-gates.review_challenge", "git-ci.pr_checklist"],
        "manual_nodes": [16, 19, 21, 24],
    },
    "memory-agent": {
        "mission": "Retrieve experience, record decisions, and surface rule candidates",
        "tools": ["experience-memory-mcp", "manual-gates.feedback_loop"],
        "manual_nodes": [15, 16, 17, 19, 24],
    },
}

SAFE_COMMAND_PREFIXES = [
    ["python", "-m", "py_compile"],
    ["python", "--version"],
    ["git", "status"],
    ["git", "rev-parse"],
]


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _run_path(project: str, run_id: str) -> Path:
    return RUN_DIR / _safe_project(project) / f"{run_id}.json"


def _save_run(project: str, run: dict) -> dict:
    path = _run_path(project, run["run_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    run["updated"] = _now()
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return run


def _load_run(project: str, run_id: str) -> dict:
    path = _run_path(project, run_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_command(command: list[str]) -> bool:
    if not command:
        return False
    return any(command[:len(prefix)] == prefix for prefix in SAFE_COMMAND_PREFIXES)


def _execute_task(task: dict) -> dict:
    started = _now()
    mode = task.get("mode", "simulate")
    result = {
        "task_id": task.get("task_id"),
        "agent": task.get("agent"),
        "mode": mode,
        "started": started,
    }
    if task.get("agent") not in AGENTS:
        return {**result, "status": "failed", "error": f"unknown agent: {task.get('agent')}", "ended": _now()}
    if mode == "simulate":
        return {
            **result,
            "status": "completed",
            "output": f"{task.get('agent')} simulated: {task.get('task')}",
            "evidence": task.get("evidence", ""),
            "ended": _now(),
        }
    if mode == "command":
        command = task.get("command", [])
        if not isinstance(command, list) or not _safe_command([str(x) for x in command]):
            return {**result, "status": "blocked", "error": "command is not in safe prefix allowlist", "command": command, "ended": _now()}
        try:
            proc = subprocess.run([str(x) for x in command], cwd=str(ROOT), text=True, capture_output=True, timeout=int(task.get("timeout", 20)))
            return {
                **result,
                "status": "completed" if proc.returncode == 0 else "failed",
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "command": command,
                "ended": _now(),
            }
        except subprocess.TimeoutExpired as exc:
            return {**result, "status": "failed", "error": f"command timed out after {exc.timeout} seconds", "command": command, "ended": _now()}
        except Exception as exc:
            return {**result, "status": "failed", "error": str(exc), "command": command, "ended": _now()}
    return {**result, "status": "blocked", "error": f"unknown mode: {mode}", "ended": _now()}


def _run_summary(run: dict) -> dict:
    results = run.get("results", [])
    total = len(results)
    completed = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    blocked = sum(1 for r in results if r.get("status") == "blocked")
    agents = sorted({r.get("agent") for r in results if r.get("agent")})
    return {
        "progress": f"{completed}/{total}",
        "completed": completed,
        "failed": failed,
        "blocked": blocked,
        "agents": agents,
        "status": "passed" if total and completed == total else ("failed" if failed else ("blocked" if blocked else "pending")),
    }


def _agent_vote(result: dict) -> dict:
    agent = result.get("agent", "")
    status = result.get("status", "")
    text = " ".join(str(result.get(k, "")) for k in ["output", "stderr", "error", "evidence"]).lower()
    risk_text = text
    for safe_phrase in ["no secret", "no credential", "no production", "no deploy", "without secret", "without credential"]:
        risk_text = risk_text.replace(safe_phrase, "")
    if status == "blocked":
        decision = "block"
        reason = result.get("error", "blocked task")
    elif status == "failed":
        decision = "rework"
        reason = result.get("error") or result.get("stderr") or "agent task failed"
    elif any(term in risk_text for term in ["critical", "secret", "credential", "production", "deploy", "高风险", "密钥"]):
        decision = "block" if agent == "security-agent" else "rework"
        reason = "risk terms found in agent output"
    elif any(term in text for term in ["missing", "todo", "pending", "未完成", "缺失"]):
        decision = "rework"
        reason = "unfinished evidence found"
    else:
        decision = "approve"
        reason = "completed without blocking signal"
    weight = {
        "security-agent": 3,
        "qa-agent": 2,
        "review-agent": 2,
        "dev-agent": 1,
        "research-agent": 1,
        "planning-agent": 1,
        "memory-agent": 1,
    }.get(agent, 1)
    return {
        "agent": agent,
        "task_id": result.get("task_id"),
        "decision": decision,
        "weight": weight,
        "reason": reason,
        "status": status,
    }


def _arbitrate(run: dict) -> dict:
    votes = [_agent_vote(result) for result in run.get("results", [])]
    weighted = {"approve": 0, "rework": 0, "block": 0}
    for vote in votes:
        weighted[vote["decision"]] += vote["weight"]
    if weighted["block"] > 0:
        final = "blocked"
        release_allowed = False
        next_action = "stop and request human approval or security remediation"
    elif weighted["rework"] > 0:
        final = "rework"
        release_allowed = False
        next_action = "fix failed or incomplete evidence, then rerun arbitration"
    elif votes and weighted["approve"] >= max(1, len(votes)):
        final = "approved"
        release_allowed = True
        next_action = "submit manual-gates evidence and prepare backup"
    else:
        final = "pending"
        release_allowed = False
        next_action = "collect more agent evidence"
    return {
        "final_decision": final,
        "release_allowed": release_allowed,
        "next_action": next_action,
        "weighted_votes": weighted,
        "votes": votes,
        "summary": _run_summary(run),
        "manual_gate_required": True,
    }


def build_server() -> FastMCP:
    mcp = FastMCP("agent-orchestration-mcp")

    @mcp.tool()
    def orchestration_brief() -> str:
        """Describe multi-agent orchestration boundaries."""
        return _json({
            "name": "agent-orchestration-mcp",
            "version": "v5.15",
            "purpose": "assign, hand off, review, and locally run safe parallel agent tasks",
            "boundary": "parallel agents cannot bypass manual-gates; command mode is allowlisted",
            "storage_root": str(CONFIG_DIR),
        })

    @mcp.tool()
    def agent_roster() -> str:
        """Return available agent roles."""
        return _json({"agents": AGENTS})

    @mcp.tool()
    def assign_task(project: str, task: str, node_id: int = 0, risk: str = "normal") -> str:
        """Assign a task to recommended agents based on node and risk."""
        selected = []
        for name, spec in AGENTS.items():
            if node_id and node_id in spec["manual_nodes"]:
                selected.append(name)
        if not selected:
            selected = ["planning-agent", "memory-agent"]
        if risk in {"high", "critical"} and "security-agent" not in selected:
            selected.append("security-agent")
        return _json({
            "project": project,
            "task": task,
            "node_id": node_id,
            "risk": risk,
            "primary": selected[0],
            "support": selected[1:],
            "handoff_required": len(selected) > 1,
        })

    @mcp.tool()
    def handoff_contract(from_agent: str, to_agent: str, project: str,
                         artifact_paths: str = "", open_questions: str = "") -> str:
        """Create a handoff contract between agents."""
        artifacts = [x.strip() for x in artifact_paths.split(",") if x.strip()]
        questions = [x.strip() for x in open_questions.split("|") if x.strip()]
        return _json({
            "project": project,
            "from": from_agent,
            "to": to_agent,
            "artifacts": artifacts,
            "open_questions": questions,
            "required_before_handoff": [
                "artifact paths exist",
                "current manual node acceptance criteria are stated",
                "risks and unresolved issues are listed",
                "next agent input contract is clear",
            ],
        })

    @mcp.tool()
    def review_matrix(project: str, agents_json: str = "") -> str:
        """Generate a review responsibility matrix."""
        agents = _loads(agents_json, []) or list(AGENTS)
        matrix = []
        for agent in agents:
            spec = AGENTS.get(agent, {})
            matrix.append({
                "agent": agent,
                "reviews": spec.get("manual_nodes", []),
                "must_use": "manual-gates.review_challenge" if agent == "review-agent" else "submit_check/gate_report as applicable",
            })
        return _json({"project": project, "matrix": matrix})

    @mcp.tool()
    def export_agent_config(project: str, output_path: str = "") -> str:
        """Export agent roster/config to JSON."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        path = Path(output_path) if output_path else CONFIG_DIR / f"{project}_agents.json"
        data = {"project": project, "generated": _now(), "agents": AGENTS, "manual_gate_required": True}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "exported", "path": str(path), "agent_count": len(AGENTS)})

    @mcp.tool()
    def plan_parallel_run(project: str, objective: str, tasks_json: str,
                          max_workers: int = 3) -> str:
        """Create a parallel agent run plan without executing it."""
        tasks = _loads(tasks_json, [])
        if not isinstance(tasks, list) or not tasks:
            return _json({"error": "tasks_json must be a non-empty JSON list"})
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        normalized = []
        for i, task in enumerate(tasks, 1):
            item = dict(task)
            item.setdefault("task_id", f"task-{i}")
            item.setdefault("mode", "simulate")
            item.setdefault("agent", "planning-agent")
            item.setdefault("task", objective)
            normalized.append(item)
        run = {
            "run_id": run_id,
            "project": project,
            "objective": objective,
            "created": _now(),
            "updated": _now(),
            "max_workers": max(1, min(int(max_workers), 8)),
            "tasks": normalized,
            "results": [],
            "status": "planned",
        }
        _save_run(project, run)
        return _json({"status": "planned", "run_id": run_id, "path": str(_run_path(project, run_id)), "task_count": len(normalized)})

    @mcp.tool()
    def execute_parallel_run(project: str, run_id: str) -> str:
        """Execute a planned run concurrently."""
        run = _load_run(project, run_id)
        if not run:
            return _json({"error": f"run not found: {run_id}"})
        run["status"] = "running"
        run["started"] = _now()
        workers = max(1, min(int(run.get("max_workers", 3)), 8))
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_execute_task, task) for task in run.get("tasks", [])]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda x: x.get("task_id", ""))
        run["results"] = results
        run["ended"] = _now()
        summary = _run_summary(run)
        run["status"] = summary["status"]
        run["summary"] = summary
        run["arbitration"] = _arbitrate(run)
        _save_run(project, run)
        return _json({"status": run["status"], "run_id": run_id, "summary": summary, "results": results})

    @mcp.tool()
    def arbitrate_parallel_run(project: str, run_id: str) -> str:
        """Arbitrate a completed parallel run into approve/rework/block."""
        run = _load_run(project, run_id)
        if not run:
            return _json({"error": f"run not found: {run_id}"})
        arbitration = _arbitrate(run)
        run["arbitration"] = arbitration
        _save_run(project, run)
        return _json({"project": project, "run_id": run_id, "arbitration": arbitration})

    @mcp.tool()
    def agent_consensus_run(project: str, objective: str, tasks_json: str = "",
                            max_workers: int = 5) -> str:
        """Plan, execute, and arbitrate a multi-agent consensus run."""
        tasks = _loads(tasks_json, [])
        if not tasks:
            tasks = [
                {"task_id": "research", "agent": "research-agent", "task": f"check external/context risk for {objective}", "mode": "simulate", "evidence": "context reviewed"},
                {"task_id": "dev", "agent": "dev-agent", "task": f"check implementation readiness for {objective}", "mode": "simulate", "evidence": "implementation evidence present"},
                {"task_id": "qa", "agent": "qa-agent", "task": f"check tests for {objective}", "mode": "simulate", "evidence": "tests passed"},
                {"task_id": "security", "agent": "security-agent", "task": f"check permission risk for {objective}", "mode": "simulate", "evidence": "local safe action only"},
                {"task_id": "review", "agent": "review-agent", "task": f"check evidence chain for {objective}", "mode": "simulate", "evidence": "manual-gates required"},
            ]
        run_id = f"consensus-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        run = {
            "run_id": run_id,
            "project": project,
            "objective": objective,
            "created": _now(),
            "updated": _now(),
            "max_workers": max(1, min(int(max_workers), 8)),
            "tasks": tasks,
            "results": [],
            "status": "running",
        }
        _save_run(project, run)
        workers = run["max_workers"]
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_execute_task, task) for task in tasks]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda x: x.get("task_id", ""))
        run["results"] = results
        run["ended"] = _now()
        summary = _run_summary(run)
        run["summary"] = summary
        run["arbitration"] = _arbitrate(run)
        run["status"] = run["arbitration"]["final_decision"]
        _save_run(project, run)
        return _json({
            "status": run["status"],
            "run_id": run_id,
            "path": str(_run_path(project, run_id)),
            "summary": summary,
            "arbitration": run["arbitration"],
        })

    @mcp.tool()
    def parallel_run_status(project: str, run_id: str) -> str:
        """Return status for one parallel run."""
        run = _load_run(project, run_id)
        if not run:
            return _json({"error": f"run not found: {run_id}"})
        return _json({"project": project, "run_id": run_id, "status": run.get("status"), "summary": _run_summary(run), "path": str(_run_path(project, run_id))})

    @mcp.tool()
    def parallel_run_report(project: str, run_id: str) -> str:
        """Return full report for one parallel run."""
        run = _load_run(project, run_id)
        if not run:
            return _json({"error": f"run not found: {run_id}"})
        return _json({"project": project, "run": run, "summary": _run_summary(run), "manual_gate_required": True})

    @mcp.tool()
    def export_parallel_run(project: str, run_id: str, output_path: str = "") -> str:
        """Export a parallel run report."""
        run = _load_run(project, run_id)
        if not run:
            return _json({"error": f"run not found: {run_id}"})
        path = Path(output_path) if output_path else _run_path(project, run_id).with_name(f"{run_id}_export.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"project": project, "run": run, "summary": _run_summary(run), "manual_gate_required": True}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "exported", "path": str(path), "task_count": len(run.get("tasks", []))})

    return mcp


def main() -> None:
    build_server().run()
