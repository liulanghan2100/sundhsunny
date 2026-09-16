# -*- coding: utf-8 -*-
"""Task Queue MCP server.

v5.16 adds a local user-space queue runner. It turns "continue" into a durable
queue: enqueue tasks, run the next safe task through mandatory runtime, record
memory, refresh dashboard, and keep retry state.
"""
import json
import hashlib
import subprocess
import sqlite3
import sys
import time
import io
import runpy
import contextlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.state import safe_project

from completion_verifier_mcp.common import _verify as _verify_completion
from dashboard_mcp.common import _collect as _collect_dashboard
from dashboard_mcp.common import _write_dashboard
from experience_memory_mcp.common import _append as _memory_append
from mandatory_runtime_hook_mcp.common import _mandatory_cycle
from Agent_OS_Core.schemas import validate_evidence_record, validate_task_card
from Agent_OS_Core.governance.owner_gate import validate_decision_for_task
from Agent_OS_Core.policy.resource_lock_manager import ResourceLockManager, ResourceBusyError
from Agent_OS_Core.policy.cost_budget_guard import CostBudgetGuard, CostBudgetExceeded

ROOT = Path(__file__).resolve().parents[2]


def _find_named_dir(prefix: str, fallback: str) -> Path:
    """Resolve the research dir deterministically.

    Multiple "09_" dirs exist in this workspace (09_research sandbox,
    09_投研 production, plus a mojibake duplicate). Plain iterdir() order is
    filesystem-dependent, which let different server processes pick different
    queue roots. Prefer the canonical production dir explicitly.
    """
    candidates = sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith(prefix))
    for path in candidates:
        if path.name == "09_投研":
            return path
    if candidates:
        return candidates[0]
    matches = list(ROOT.glob(fallback))
    return matches[0] if matches else ROOT / fallback.replace("*", "")


_env_queue_root = os.environ.get("TASK_QUEUE_ROOT")
RESEARCH_DIR = Path(_env_queue_root) if _env_queue_root else _find_named_dir("09_", "09_*")
QUEUE_ROOT = RESEARCH_DIR / "task_queue"
QUEUE_DB = QUEUE_ROOT / "task_queue.sqlite"
REPORT_DIR = QUEUE_ROOT / "reports"
EXECUTION_DIR = QUEUE_ROOT / "execution_evidence"
RUNTIME_ROOT = RESEARCH_DIR / "agent_os_runtime"
TASK_CARD_DIR = RUNTIME_ROOT / "task_cards"
RUN_STATE_DIR = RUNTIME_ROOT / "runs"
CONTROL_SNAPSHOT = RUNTIME_ROOT / "control_snapshot.json"
DAEMON_CONFIG = QUEUE_ROOT / "daemon_config.json"
DAEMON_STATE = QUEUE_ROOT / "daemon_state.json"
DAEMON_STOP = QUEUE_ROOT / "daemon.stop"
SELF_INIT_ROOT = RESEARCH_DIR / "self_initiation"
SELF_GOVERNANCE = SELF_INIT_ROOT / "governance.json"
SELF_EVENTS = SELF_INIT_ROOT / "governance_events.jsonl"
DAILY_RETRO_DIR = RESEARCH_DIR / "daily_retro"
SELF_TEMPLATE_ALLOWLIST = {"daily_queue_retro"}
RESOURCE_LOCKS = ResourceLockManager()

ADMIN_HINTS = {
    "admin", "administrator", "runas", "sudo", "uac", "elevated",
    "管理员", "提权", "系统服务", "service install",
}


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _loads(value: str | dict | list | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        value = value.lstrip("\ufeff")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _safe_id(value: str) -> str:
    return "".join(c for c in value if c.isalnum() or c in "-_.") or "task"


def _task_node_id(task: dict) -> int:
    """Resolve gate node tag from task context; default 17 keeps backward compatibility."""
    try:
        return int((task.get("context") or {}).get("node_id", 17))
    except (TypeError, ValueError):
        return 17


def _task_card_path(task_card_id: str) -> Path:
    return TASK_CARD_DIR / f"{_safe_id(task_card_id)}.json"


def _run_state_path(run_id: str) -> Path:
    return RUN_STATE_DIR / f"{_safe_id(run_id)}.json"


def _task_context(task: dict) -> dict:
    context = task.get("context") or {}
    return context if isinstance(context, dict) else {}


def _acceptance_criteria(task: dict) -> list[str]:
    context = _task_context(task)
    raw = context.get("acceptance_criteria") or context.get("completion_criteria") or []
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    criteria = ["mandatory runtime route completes", "completion verifier accepts evidence"]
    if context.get("expected_artifacts"):
        criteria.append("expected artifacts exist")
    return criteria


def _artifact_contracts(task: dict) -> list[dict]:
    context = _task_context(task)
    raw = context.get("expected_artifacts", [])
    if isinstance(raw, str):
        raw = [raw]
    items = []
    for item in raw if isinstance(raw, list) else []:
        path = item.get("path") if isinstance(item, dict) else item
        if path:
            items.append({"path": str(path), "required": True})
    return items


def _ensure_task_card(task: dict) -> dict:
    context = _task_context(task)
    card = context.get("task_card") if isinstance(context.get("task_card"), dict) else {}
    if card.get("schema_version") == "agent-os-task-card-v1":
        task_card = dict(card)
        card_id = str(task_card["task_id"])
        run_id = str(context.get("run_id") or f"run-{task['id']}")
        task_card["id"] = card_id
        task_card["run_id"] = run_id
        task_card["queue_task_id"] = task["id"]
        validation = validate_task_card(task_card)
        if not validation.valid:
            raise ValueError(
                "agent-os-task-card-v1 validation failed: "
                + "; ".join(validation.errors)
            )
        TASK_CARD_DIR.mkdir(parents=True, exist_ok=True)
        _task_card_path(card_id).write_text(
            json.dumps(task_card, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        context["task_card_id"] = card_id
        context["task_card_path"] = str(_task_card_path(card_id))
        context["run_id"] = run_id
        context["acceptance_criteria"] = task_card["acceptance_criteria"]
        context["expected_artifacts"] = task_card["expected_artifacts"]
        task["context"] = context
        return task_card

    card_id = str(card.get("id") or f"card-{task['id']}")
    run_id = str(context.get("run_id") or card.get("run_id") or f"run-{task['id']}")
    task_card = {
        "schema_version": "task-card/v0.1",
        "id": card_id,
        "run_id": run_id,
        "queue_task_id": task["id"],
        "project": task["project"],
        "task": task["task"],
        "risk": task["risk"],
        "track": task["track"],
        "autonomy": task["autonomy"],
        "operation": task["operation"],
        "manual_node": _task_node_id(task),
        "task_class": context.get("task_class", "B"),
        "acceptance_criteria": _acceptance_criteria(task),
        "expected_artifacts": _artifact_contracts(task),
        "status": task.get("status", "queued"),
        "created": task.get("created") or _now(),
        "updated": _now(),
        "source": context.get("initiated_by") or "queue",
    }
    task_card.update(card)
    task_card["id"] = card_id
    task_card["run_id"] = run_id
    task_card["queue_task_id"] = task["id"]
    TASK_CARD_DIR.mkdir(parents=True, exist_ok=True)
    _task_card_path(card_id).write_text(json.dumps(task_card, ensure_ascii=False, indent=2), encoding="utf-8")
    context["task_card_id"] = card_id
    context["task_card_path"] = str(_task_card_path(card_id))
    context["run_id"] = run_id
    task["context"] = context
    return task_card


def _formal_task_card_preflight(task_card: Any) -> tuple[bool, str]:
    if not isinstance(task_card, dict):
        return False, "formal queue admission requires a v1 TaskCard"
    if task_card.get("schema_version") != "agent-os-task-card-v1":
        return False, "formal queue admission rejects legacy TaskCard versions"
    validation = validate_task_card(task_card)
    if not validation.valid:
        return False, "TaskCard validation failed: " + "; ".join(validation.errors)
    gate = validate_decision_for_task(task_card)
    if not gate["valid"]:
        return False, f"Owner Gate {gate['status']}: {gate['reason']}"
    return True, ""


def _approved_task_card_enqueue_impl(
    task_card: dict,
    *,
    openhands_workspace: str = "",
    execution_backend: str = "openhands",
    priority: int = 0,
) -> dict:
    """唯一正式入队 API：只接受已批准的 v1 TaskCard。"""
    admitted, reason = _formal_task_card_preflight(task_card)
    if not admitted:
        return {
            "status": "blocked",
            "reason": reason,
            "admission": "approved_task_card_enqueue",
            "no_task_created": True,
        }
    queue_id = f"queue-{_safe_id(task_card['task_id'])}"
    context = {
        "task_class": "B",
        "execution_backend": execution_backend,
        "openhands_workspace": openhands_workspace,
        "task_card": task_card,
        "source": "agent_os_approved_task_card",
    }
    item = {
        "id": queue_id,
        "project": task_card["project"],
        "task": task_card["objective"],
        "status": "queued",
        "priority": int(priority),
        "risk": task_card.get("risk_level", "medium"),
        "track": "standard",
        "autonomy": "L2",
        "operation": "approved_task_card",
        "attempts": 0,
        "max_attempts": task_card["failure_policy"]["max_attempts"],
        "context": context,
        "result": {},
        "created": _now(),
        "updated": _now(),
        "started": None,
        "ended": None,
    }
    _ensure_task_card(item)
    _save_task(item)
    run_state = _ensure_run_state(item, "approved_task_card_enqueued")
    return {
        "status": "queued",
        "admission": "approved_task_card_enqueue",
        "task_id": queue_id,
        "run_id": run_state["run_id"],
        "task_card_path": str(_task_card_path(task_card["task_id"])),
        "run_state_path": str(_run_state_path(run_state["run_id"])),
        "task": item,
        "run_state": run_state,
        "db": str(QUEUE_DB),
    }


def approved_task_card_enqueue(
    task_card: dict,
    *,
    openhands_workspace: str = "",
    execution_backend: str = "openhands",
    priority: int = 0,
) -> dict:
    """Public Python API for the only formal Task Queue admission path."""
    return _approved_task_card_enqueue_impl(
        task_card,
        openhands_workspace=openhands_workspace,
        execution_backend=execution_backend,
        priority=priority,
    )


def _run_phase(status: str) -> str:
    if status in {"queued", "retry"}:
        return "intake"
    if status == "running":
        return "execute"
    if status == "completed":
        return "archive"
    if status in {"blocked", "failed"}:
        return "verify"
    return "plan"


def _load_run_state(run_id: str) -> dict:
    path = _run_state_path(run_id)
    if not path.exists():
        return {}
    data = _loads(path.read_text(encoding="utf-8"), {})
    return data if isinstance(data, dict) else {}


def _write_run_state(state: dict) -> dict:
    RUN_STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated"] = _now()
    _run_state_path(state["run_id"]).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_control_snapshot()
    return state


def _ensure_run_state(task: dict, event: str = "intake") -> dict:
    task_card = _ensure_task_card(task)
    run_id = task_card["run_id"]
    state = _load_run_state(run_id)
    if not state:
        state = {
            "schema_version": "run-state/v0.1",
            "run_id": run_id,
            "task_card_id": task_card["id"],
            "queue_task_id": task["id"],
            "project": task["project"],
            "task": task["task"],
            "phase": _run_phase(task.get("status", "queued")),
            "status": task.get("status", "queued"),
            "manual_node": _task_node_id(task),
            "risk": task["risk"],
            "track": task["track"],
            "autonomy": task["autonomy"],
            "operation": task["operation"],
            "task_class": task_card.get("task_class", "B"),
            "task_card_path": task_card.get("task_card_path") or str(_task_card_path(task_card["id"])),
            "inputs": {"context": _task_context(task)},
            "tool_calls": [],
            "artifacts": task_card.get("expected_artifacts", []),
            "checks": [],
            "decision": "continue",
            "memory_writes": [],
            "events": [],
            "created": _now(),
        }
    state["phase"] = _run_phase(task.get("status", state.get("status", "queued")))
    state["status"] = task.get("status", state.get("status", "queued"))
    state["events"].append({"ts": _now(), "event": event, "status": state["status"]})
    return _write_run_state(state)


def _update_run_state(task: dict, event: str, **fields: Any) -> dict:
    state = _ensure_run_state(task, event)
    for key, value in fields.items():
        if key in {"tool_calls", "checks", "artifacts", "memory_writes"} and isinstance(value, list):
            state.setdefault(key, []).extend(value)
        else:
            state[key] = value
    state["phase"] = _run_phase(task.get("status", state.get("status", "")))
    state["status"] = task.get("status", state.get("status", ""))
    return _write_run_state(state)


def _completion_context(task: dict, result: dict) -> dict:
    context = _task_context(task)
    execution = result.get("execution", {})
    mandatory = result.get("mandatory", {})
    return {
        **context,
        "minimum_validation": True,
        "result": task.get("status"),
        "mandatory_runtime": mandatory,
        "manual_gates": mandatory,
        "gate_report": mandatory.get("state_path") or mandatory.get("status"),
        "execution_evidence": execution,
        "tests": execution.get("status") or "not_requested",
        "expected_artifacts": execution.get("expected_artifacts", []),
        "run_state": _task_context(task).get("run_id"),
        "task_card": _task_context(task).get("task_card_id"),
    }


def _verify_task_completion(task: dict, result: dict) -> dict:
    task_class = str(_task_context(task).get("task_class") or "B")
    verification = _verify_completion(task_class, _completion_context(task, result))
    return {"task_class": task_class, **verification}


def _latest_run_states(limit: int = 20) -> list[dict]:
    if not RUN_STATE_DIR.exists():
        return []
    rows = []
    for path in sorted(RUN_STATE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        data = _loads(path.read_text(encoding="utf-8"), {})
        if isinstance(data, dict):
            rows.append({
                "run_id": data.get("run_id", path.stem),
                "project": data.get("project", ""),
                "task": data.get("task", ""),
                "status": data.get("status", ""),
                "phase": data.get("phase", ""),
                "decision": data.get("decision", ""),
                "manual_node": data.get("manual_node", ""),
                "updated": data.get("updated", ""),
                "path": str(path),
            })
    return rows


def _write_control_snapshot() -> dict:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "generated": _now(),
        "counts": _task_counts(),
        "runs": _latest_run_states(50),
        "queued": _list_tasks(10),
    }
    CONTROL_SNAPSHOT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def _blocked_by_admin(task: str, context: dict | None = None) -> list[str]:
    text = f"{task} {json.dumps(context or {}, ensure_ascii=False)}".lower()
    return sorted([hint for hint in ADMIN_HINTS if hint.lower() in text])


def _resolve_workspace_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"path outside workspace is not allowed: {resolved}") from exc
    return resolved


def _execution_command(context: dict) -> list[str]:
    script = context.get("script")
    if script:
        script_path = _resolve_workspace_path(str(script))
        if not script_path.exists():
            raise FileNotFoundError(f"script not found: {script_path}")
        args = [str(x) for x in (context.get("args") or [])]
        return [sys.executable, str(script_path), *args]
    command = context.get("command")
    if isinstance(command, list) and command:
        executable = str(command[0])
        if executable.lower() in {"python", "python.exe", "py"}:
            return [sys.executable, *[str(x) for x in command[1:]]]
        executable_path = _resolve_workspace_path(executable)
        return [str(executable_path), *[str(x) for x in command[1:]]]
    if isinstance(command, str) and command.strip():
        raise ValueError("string commands are not allowed; use a JSON list or script path")
    return []


def _expected_artifacts(context: dict) -> list[dict]:
    raw = context.get("expected_artifacts", [])
    if isinstance(raw, str):
        raw = [raw]
    artifacts = []
    for item in raw if isinstance(raw, list) else []:
        path = item.get("path") if isinstance(item, dict) else item
        if not path:
            continue
        resolved = _resolve_workspace_path(str(path))
        artifacts.append({"path": str(resolved), "exists": resolved.exists()})
    return artifacts


def _run_script_in_process(script_path: Path, cwd: Path) -> tuple[int, str, str]:
    old_cwd = Path.cwd()
    old_path = list(sys.path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        os.chdir(cwd)
        sys.path.insert(0, str(script_path.parent))
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            runpy.run_path(str(script_path), run_name="__main__")
        return 0, stdout.getvalue(), stderr.getvalue()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        return code, stdout.getvalue(), stderr.getvalue()
    except Exception as exc:
        stderr.write(str(exc))
        return 1, stdout.getvalue(), stderr.getvalue()
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path


def _record_execution_failure(task: dict, execution: dict) -> dict:
    try:
        from failure_replay_mcp.common import FAILURE_FILE, _append_jsonl

        record = {
            "id": f"failure-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "ts": _now(),
            "type": "failure_case",
            "project": task["project"],
            "task": task["task"],
            "symptom": "task queue real executor failed",
            "cause": execution.get("error") or execution.get("stderr_tail") or f"returncode={execution.get('returncode')}",
            "impact": "queued task did not produce accepted execution evidence",
            "fix": "inspect execution evidence and rerun with a valid script/command contract",
            "prevention": "task queue tasks that require real work must include a valid local script, timeout, and expected artifacts",
            "severity": "normal",
            "tags": ["task_queue", "real_executor"],
            "applies_to": "queued local execution",
        }
        _append_jsonl(FAILURE_FILE, record)
        return {"status": "recorded", "failure_id": record["id"]}
    except Exception as exc:
        return {"status": "failure_record_failed", "error": str(exc)}


def _execute_contract(task: dict) -> dict:
    context = task.get("context") or {}
    has_contract = bool(context.get("script") or context.get("command"))
    if not has_contract:
        return {"status": "not_requested"}
    timeout = max(1, int(context.get("timeout_seconds", 120)))
    evidence_root = EXECUTION_DIR / _safe_project(task["project"]) / _safe_id(task["id"])
    evidence_root.mkdir(parents=True, exist_ok=True)
    try:
        command = _execution_command(context)
        cwd = _resolve_workspace_path(str(context.get("cwd", ".")))
        started = _now()
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
            )
            returncode = proc.returncode
            stdout_text = proc.stdout or ""
            stderr_text = proc.stderr or ""
            run_mode = "subprocess"
        except subprocess.TimeoutExpired:
            if context.get("script"):
                returncode, stdout_text, stderr_text = _run_script_in_process(Path(command[-1]), cwd)
                run_mode = "in_process_fallback"
            else:
                raise
        ended = _now()
        stdout_path = evidence_root / "stdout.txt"
        stderr_path = evidence_root / "stderr.txt"
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        artifacts = _expected_artifacts(context)
        artifacts_ok = all(item["exists"] for item in artifacts)
        passed = returncode == 0 and artifacts_ok
        evidence = {
            "status": "completed" if passed else "failed",
            "started": started,
            "ended": ended,
            "command": command,
            "run_mode": run_mode,
            "cwd": str(cwd),
            "returncode": returncode,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "stdout_tail": stdout_text[-2000:],
            "stderr_tail": stderr_text[-2000:],
            "expected_artifacts": artifacts,
            "artifacts_ok": artifacts_ok,
            "project": task["project"],
            "node_id": _task_node_id(task),
            "evidence_path": str(evidence_root / "execution.json"),
        }
    except Exception as exc:
        evidence = {
            "status": "failed",
            "error": str(exc),
            "project": task["project"],
            "node_id": _task_node_id(task),
            "expected_artifacts": _expected_artifacts(context),
            "evidence_path": str(evidence_root / "execution.json"),
        }
    if evidence["status"] != "completed":
        evidence["failure_replay"] = _record_execution_failure(task, evidence)
    if context.get("initiated_by"):
        evidence["initiated_by"] = context.get("initiated_by")
        evidence["trigger"] = context.get("trigger")
        evidence["template"] = context.get("template")
    (evidence_root / "execution.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def _execute_openhands_worker(task: dict) -> dict:
    """Run an explicitly selected TaskCard through the OpenHands worker."""
    context = _task_context(task)
    task_card_path = context.get("task_card_path")
    target_workspace = context.get("openhands_workspace") or context.get("target_workspace")
    if not task_card_path or not target_workspace:
        return {
            "status": "failed",
            "failure_class": "policy_block",
            "error": "OpenHands backend requires task_card_path and openhands_workspace",
        }
    try:
        card = _loads(Path(str(task_card_path)).read_text(encoding="utf-8"), {})
        if not isinstance(card, dict):
            raise ValueError("TaskCard file must contain an object")
        from external_execution.openhands.bridge.worker import execute_task_card

        result = execute_task_card(card, target_workspace=str(target_workspace))
        evidence_root = EXECUTION_DIR / _safe_project(task["project"]) / _safe_id(task["id"])
        evidence_root.mkdir(parents=True, exist_ok=True)
        worker_result_path = evidence_root / "openhands_worker_result.json"
        worker_result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        evidence_path = evidence_root / "evidence_record.json"
        evidence_record = dict(result["evidence_record"])
        evidence_record["artifact_path"] = str(worker_result_path)
        evidence_record["artifact_hash"] = hashlib.sha256(
            worker_result_path.read_bytes()
        ).hexdigest()
        evidence_validation = validate_evidence_record(
            evidence_record,
            evidence_root=EXECUTION_DIR,
            verify_hash=True,
        )
        if not evidence_validation.valid:
            raise ValueError(
                "OpenHands EvidenceRecord validation failed: "
                + "; ".join(evidence_validation.errors)
            )
        evidence_path.write_text(
            json.dumps(evidence_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["evidence_record"] = evidence_record
        result["run_state"]["evidence_record"] = evidence_record
        return result
    except Exception as exc:
        return {
            "status": "failed",
            "failure_class": "policy_block",
            "error": str(exc),
        }


def _connect() -> sqlite3.Connection:
    QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(QUEUE_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            task TEXT NOT NULL,
            status TEXT NOT NULL,
            priority INTEGER NOT NULL,
            risk TEXT NOT NULL,
            track TEXT NOT NULL,
            autonomy TEXT NOT NULL,
            operation TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            max_attempts INTEGER NOT NULL,
            context TEXT NOT NULL,
            result TEXT NOT NULL,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            started TEXT,
            ended TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority, created)")
    return conn


def _row_to_task(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["context"] = _loads(item.get("context"), {})
    item["result"] = _loads(item.get("result"), {})
    return item


def _save_task(task: dict) -> dict:
    conn = _connect()
    try:
        task["updated"] = _now()
        conn.execute(
            """
            INSERT OR REPLACE INTO tasks(
                id, project, task, status, priority, risk, track, autonomy,
                operation, attempts, max_attempts, context, result,
                created, updated, started, ended
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task["id"],
                task["project"],
                task["task"],
                task["status"],
                int(task["priority"]),
                task["risk"],
                task["track"],
                task["autonomy"],
                task["operation"],
                int(task["attempts"]),
                int(task["max_attempts"]),
                json.dumps(task.get("context", {}), ensure_ascii=False),
                json.dumps(task.get("result", {}), ensure_ascii=False),
                task["created"],
                task["updated"],
                task.get("started"),
                task.get("ended"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return task


def _load_task(task_id: str) -> dict:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_task(row) if row else {}
    finally:
        conn.close()


WATCHDOG_MARGIN_SECONDS = 600  # fixed grace on top of timeout*2


def _default_self_governance() -> dict:
    return {
        "enabled": False,
        "breaker_tripped": False,
        "templates": {
            "daily_queue_retro": {"enabled": False},
            "daily_knowledge_retro": {"enabled": False},
        },
        "schedule": {"cron_daily": "21:40", "timezone": "Asia/Shanghai"},
        "quota": {"max_tasks_per_day": 1, "cooldown_minutes": 1380},
        "breaker": {"failures_trip": 1, "trip_requires": "owner_reset"},
        "trial": {"soak_days": 7, "report_only": True, "trusted_promote": False},
        "updated": _now(),
    }


def _read_self_governance(create: bool = True) -> dict:
    if not SELF_GOVERNANCE.exists():
        config = _default_self_governance()
        if create:
            SELF_INIT_ROOT.mkdir(parents=True, exist_ok=True)
            SELF_GOVERNANCE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return config
    data = _loads(SELF_GOVERNANCE.read_text(encoding="utf-8"), {})
    if not isinstance(data, dict):
        data = {}
    merged = _default_self_governance()
    merged.update(data)
    merged["templates"] = {**_default_self_governance()["templates"], **(data.get("templates") or {})}
    merged["quota"] = {**_default_self_governance()["quota"], **(data.get("quota") or {})}
    merged["breaker"] = {**_default_self_governance()["breaker"], **(data.get("breaker") or {})}
    merged["trial"] = {**_default_self_governance()["trial"], **(data.get("trial") or {})}
    return merged


def _write_self_governance(config: dict) -> None:
    SELF_INIT_ROOT.mkdir(parents=True, exist_ok=True)
    config["updated"] = _now()
    SELF_GOVERNANCE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _self_event(event: str, **fields: Any) -> dict:
    SELF_INIT_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"ts": _now(), "local_date": datetime.now().strftime("%Y-%m-%d"), "event": event, **fields}
    with SELF_EVENTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def _self_events() -> list[dict]:
    if not SELF_EVENTS.exists():
        return []
    items = []
    for line in SELF_EVENTS.read_text(encoding="utf-8").splitlines():
        data = _loads(line, {})
        if isinstance(data, dict):
            items.append(data)
    return items


def _trip_self_breaker(reason: str, task_id: str = "", template: str = "") -> dict:
    config = _read_self_governance()
    config["enabled"] = False
    config["breaker_tripped"] = True
    config["breaker_reason"] = reason
    config["breaker_task_id"] = task_id
    config["breaker_template"] = template
    config["breaker_tripped_at"] = _now()
    _write_self_governance(config)
    return _self_event("tripped_failure", reason=reason, task_id=task_id, template=template, initiated_by="self")


def _self_template_task(template: str) -> dict:
    if template != "daily_queue_retro":
        raise ValueError(f"template not allowed: {template}")
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = DAILY_RETRO_DIR / f"{today}_queue_retro.md"
    context = {
        "initiated_by": "self",
        "trigger": "daemon_schedule",
        "template": template,
        "node_id": 23,
        "script": str(ROOT / "03_分工MCP" / "self_initiation_daily_queue_retro.py"),
        "cwd": str(ROOT),
        "timeout_seconds": 120,
        "expected_artifacts": [{"path": str(report_path)}],
    }
    return {
        "id": f"task-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "project": "self-initiation-daily-retro",
        "task": "self initiated daily queue and gate health retro",
        "status": "queued",
        "priority": 0,
        "risk": "low",
        "track": "quick",
        "autonomy": "L3",
        "operation": "local_read",
        "attempts": 0,
        "max_attempts": 1,
        "context": context,
        "result": {},
        "created": _now(),
        "updated": _now(),
        "started": None,
        "ended": None,
    }


def _self_initiation_skip(reason: str, template: str = "daily_queue_retro") -> dict:
    return {"status": "skipped", "reason": reason, "event": _self_event(reason, template=template, initiated_by="self")}


def _self_enqueue_template(template: str = "daily_queue_retro", trigger: str = "daemon_schedule") -> dict:
    config = _read_self_governance()
    if DAEMON_STOP.exists():
        return _self_initiation_skip("skipped_stop_file", template)
    if template not in SELF_TEMPLATE_ALLOWLIST:
        event = _self_event("denied_template", template=template, initiated_by="self", trigger=trigger)
        _trip_self_breaker(f"template outside allowlist: {template}", template=template)
        return {"status": "denied", "reason": "template outside allowlist", "event": event}
    if config.get("breaker_tripped"):
        return _self_initiation_skip("skipped_breaker_tripped", template)
    if not config.get("enabled"):
        return _self_initiation_skip("skipped_disabled", template)
    if not (config.get("templates") or {}).get(template, {}).get("enabled"):
        return _self_initiation_skip("skipped_template_disabled", template)

    today = datetime.now().strftime("%Y-%m-%d")
    enqueued_today = [
        event for event in _self_events()
        if event.get("event") == "enqueued"
        and event.get("template") == template
        and event.get("local_date") == today
    ]
    max_per_day = max(1, int((config.get("quota") or {}).get("max_tasks_per_day", 1)))
    if len(enqueued_today) >= max_per_day:
        return _self_initiation_skip("skipped_quota", template)

    item = _self_template_task(template)
    _save_task(item)
    _ensure_run_state(item, "self_template_enqueued")
    event = _self_event(
        "enqueued",
        template=template,
        task_id=item["id"],
        project=item["project"],
        initiated_by="self",
        trigger=trigger,
    )
    return {"status": "enqueued", "task_id": item["id"], "task": item, "event": event}


def _observe_self_task_result(task: dict) -> None:
    context = task.get("context") or {}
    if context.get("initiated_by") != "self":
        return
    if task.get("status") == "completed":
        return
    _trip_self_breaker(
        f"self initiated task ended with status={task.get('status')}",
        task_id=task.get("id", ""),
        template=str(context.get("template") or ""),
    )


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _running_tasks() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM tasks WHERE status = 'running'").fetchall()
        return [_row_to_task(row) for row in rows]
    finally:
        conn.close()


def _sweep_stale_running() -> int:
    """Lazy watchdog: reap tasks stuck in 'running' beyond timeout*2 + margin.

    Conservative by design: tasks whose started/updated timestamps cannot be
    parsed are never swept. Returns the number of swept tasks."""
    swept = 0
    for task in _running_tasks():
        anchor = _parse_ts(task.get("started")) or _parse_ts(task.get("updated"))
        if anchor is None:
            continue
        context = task.get("context") or {}
        try:
            timeout = max(1, int(context.get("timeout_seconds", 120)))
        except (TypeError, ValueError):
            timeout = 120
        threshold = timeout * 2 + WATCHDOG_MARGIN_SECONDS
        elapsed = (datetime.now(timezone.utc) - anchor).total_seconds()
        if elapsed <= threshold:
            continue
        result = task.get("result") or {}
        result["watchdog"] = {
            "event": "stale_running_swept",
            "elapsed_seconds": int(elapsed),
            "timeout_seconds": timeout,
            "threshold_seconds": threshold,
            "swept_at": _now(),
        }
        task["result"] = result
        task["status"] = "failed"
        task["ended"] = _now()
        _save_task(task)
        _update_run_state(task, "watchdog_swept", decision="block", checks=[{"name": "queue_watchdog", "passed": False, "details": result["watchdog"]}])
        swept += 1
    return swept


def _next_task() -> dict:
    _sweep_stale_running()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM tasks
            WHERE status IN ('queued', 'retry')
            ORDER BY priority DESC, created ASC
            LIMIT 1
            """
        ).fetchone()
        return _row_to_task(row) if row else {}
    finally:
        conn.close()


def _task_counts() -> dict:
    conn = _connect()
    try:
        rows = conn.execute("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status").fetchall()
        return {row["status"]: row["count"] for row in rows}
    finally:
        conn.close()


def _list_tasks(limit: int = 20) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY updated DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [_row_to_task(row) for row in rows]
    finally:
        conn.close()


def _refresh_dashboard() -> dict:
    try:
        data = _collect_dashboard()
        paths = _write_dashboard(data)
        return {"status": "refreshed", **paths}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def _read_daemon_config() -> dict:
    if not DAEMON_CONFIG.exists():
        config = {
            "enabled": True,
            "interval_seconds": 2,
            "max_ticks": 5,
            "max_tasks_per_tick": 1,
            "admin_privileges": "forbidden",
        }
        QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
        DAEMON_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return config
    return _loads(DAEMON_CONFIG.read_text(encoding="utf-8"), {})


def _write_daemon_state(state: dict) -> str:
    QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
    state["updated"] = _now()
    DAEMON_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(DAEMON_STATE)


def _read_daemon_state() -> dict:
    if not DAEMON_STATE.exists():
        return {}
    return _loads(DAEMON_STATE.read_text(encoding="utf-8"), {})


def _daemon_tick(max_tasks: int = 1) -> dict:
    started = _now()
    self_initiation = _self_enqueue_template("daily_queue_retro", trigger="daemon_tick")
    result = json.loads(build_queue_runner_payload(max_tasks))
    state = {
        "status": "ticked",
        "started": started,
        "ended": _now(),
        "self_initiation": self_initiation,
        "executed": result.get("executed", 0),
        "counts": result.get("counts", {}),
        "admin_privileges": "not_requested",
        "stop_file": str(DAEMON_STOP),
    }
    _write_daemon_state(state)
    return state


def build_queue_runner_payload(max_tasks: int = 5) -> str:
    results = []
    for _ in range(max(1, int(max_tasks))):
        task = _next_task()
        if not task:
            break
        task["status"] = "running"
        _save_task(task)
        _update_run_state(task, "dequeued_for_run", tool_calls=[{"tool": "task_queue_mcp.run_queue", "ts": _now()}])
        results.append(_run_task(task))
    return _json({"status": "completed", "executed": len(results), "results": results, "counts": _task_counts()})


def _record_queue_memory(task: dict, status: str, result: dict) -> dict:
    completion = result.get("completion_verifier") or {}
    if status != "completed" or not completion.get("passed"):
        return {
            "status": "skipped",
            "reason": "memory requires completed task with passing completion verifier",
        }
    try:
        return _memory_append({
            "type": "outcome",
            "project": task["project"],
            "task": task["task"],
            "status": status,
            "tests": ["task_queue.run_next_task"],
            "issues": result.get("blockers") or result.get("errors") or [],
            "gate_status": result.get("gate_status", ""),
            "result": result,
        })
    except Exception as exc:
        return {"status": "memory_failed", "error": str(exc)}


def _run_task(task: dict) -> dict:
    admin_hits = _blocked_by_admin(task["task"], task.get("context"))
    task["attempts"] = int(task.get("attempts", 0)) + 1
    task["started"] = _now()
    _update_run_state(task, "run_started", tool_calls=[{"tool": "task_queue_mcp.run_next_task", "ts": _now()}])
    if admin_hits:
        result = {
            "status": "blocked",
            "reason": "administrator privilege request is outside autonomy scope",
            "matched_terms": admin_hits,
        }
        task["status"] = "blocked"
        task["result"] = result
        task["ended"] = _now()
        _save_task(task)
        _observe_self_task_result(task)
        memory = _record_queue_memory(task, "blocked", result)
        _update_run_state(
            task,
            "blocked_by_admin_boundary",
            decision="block",
            checks=[{"name": "admin_boundary", "passed": False, "details": result}],
            memory_writes=[memory],
        )
        return {"status": "blocked", "task": task}

    task_card = _ensure_task_card(task)
    contract = task_card.get("execution_contract") or {}
    budget = contract.get("budget") or {}
    estimated_cost = float(_task_context(task).get("estimated_cost_usd", 0) or 0)
    max_cost = float(budget.get("max_cost_usd", 0) or 0)
    try:
        cost_guard = CostBudgetGuard(max_cost)
        cost_guard.reserve(estimated_cost)
    except (ValueError, CostBudgetExceeded) as exc:
        result = {
            "status": "blocked",
            "reason": "cost budget preflight failed",
            "failure_class": "cost_budget_exceeded",
            "error": str(exc),
        }
        task["status"] = "blocked"
        task["result"] = result
        task["ended"] = _now()
        _save_task(task)
        _update_run_state(
            task,
            "blocked_on_cost_budget",
            decision="block",
            checks=[{"name": "cost_budget", "passed": False, "details": result}],
        )
        return {"status": "blocked", "task": task}

    resources = contract.get("resource_locks") or []
    try:
        RESOURCE_LOCKS.acquire(task["id"], resources)
    except ResourceBusyError as exc:
        result = {
            "status": "blocked",
            "reason": "resource lock conflict",
            "failure_class": "resource_conflict",
            "error": str(exc),
        }
        task["status"] = "blocked"
        task["result"] = result
        task["ended"] = _now()
        _save_task(task)
        _update_run_state(
            task,
            "blocked_on_resource_lock",
            decision="block",
            checks=[{"name": "resource_lock", "passed": False, "details": result}],
        )
        return {"status": "blocked", "task": task}

    governed = _mandatory_cycle(
        project=task["project"],
        task=task["task"],
        risk=task["risk"],
        approved=False,
        track=task["track"],
        autonomy=task["autonomy"],
        tool="task_queue_mcp.run_next_task",
        node_id=_task_node_id(task),
        context={"queue_task_id": task["id"], "operation": task["operation"], **task.get("context", {})},
    )
    dashboard = _refresh_dashboard()
    execution = {"status": "skipped"}
    try:
        if governed.get("status") == "completed":
            backend = str(_task_context(task).get("execution_backend") or "local_contract")
            execution = (
                _execute_openhands_worker(task)
                if backend == "openhands"
                else _execute_contract(task)
            )
    finally:
        RESOURCE_LOCKS.release(task["id"])
    result = {"mandatory": governed, "execution": execution, "dashboard": dashboard}
    completion = _verify_task_completion(task, result)
    result["completion_verifier"] = completion
    if governed.get("status") == "completed" and execution.get("status") in {"completed", "not_requested"} and completion.get("passed"):
        task["status"] = "completed"
    elif task["attempts"] < task["max_attempts"]:
        task["status"] = "retry"
    else:
        task["status"] = execution.get("status") if execution.get("status") == "failed" else governed.get("status", "failed")
        if not completion.get("passed") and task["status"] == "completed":
            task["status"] = "failed"
    task["result"] = result
    task["ended"] = _now()
    _save_task(task)
    _observe_self_task_result(task)
    memory = _record_queue_memory(task, task["status"], result)
    _update_run_state(
        task,
        "run_finished",
        decision="complete" if task["status"] == "completed" else "retry" if task["status"] == "retry" else "block",
        mandatory=governed,
        execution=execution,
        completion_verifier=completion,
        dashboard=dashboard,
        openhands_run_state=execution.get("run_state", {}),
        evidence_record=execution.get("evidence_record", {}),
        checks=[
            {"name": "mandatory_runtime", "passed": governed.get("status") == "completed", "details": governed},
            {"name": "execution_evidence", "passed": execution.get("status") in {"completed", "not_requested"}, "details": execution},
            {"name": "completion_verifier", "passed": bool(completion.get("passed")), "details": completion},
        ],
        memory_writes=[memory],
    )
    return {"status": task["status"], "task": task}


def build_server() -> FastMCP:
    mcp = FastMCP("task-queue-mcp")

    @mcp.tool()
    def queue_brief() -> str:
        """Describe task queue runner capabilities."""
        return _json({
            "name": "task-queue-mcp",
            "version": "v5.17",
            "purpose": "local user-space task queue and daemon-runner core",
            "db": str(QUEUE_DB),
            "daemon_config": str(DAEMON_CONFIG),
            "daemon_state": str(DAEMON_STATE),
            "daemon_stop_file": str(DAEMON_STOP),
            "admin_boundary": "does not request administrator privileges",
            "runtime_root": str(RUNTIME_ROOT),
            "task_card_dir": str(TASK_CARD_DIR),
            "run_state_dir": str(RUN_STATE_DIR),
            "route": ["task_card", "run_state", "task_queue", "mandatory_runtime_hook", "execution_evidence", "completion_verifier", "memory_writeback", "dashboard_refresh"],
        })

    @mcp.tool()
    def self_initiation_status() -> str:
        """Return self-initiation governance config and recent audit events."""
        return _json({
            "config_path": str(SELF_GOVERNANCE),
            "events_path": str(SELF_EVENTS),
            "daily_retro_dir": str(DAILY_RETRO_DIR),
            "config": _read_self_governance(),
            "recent_events": _self_events()[-20:],
            "allowlist": sorted(SELF_TEMPLATE_ALLOWLIST),
            "daemon_stop_file": str(DAEMON_STOP),
            "daemon_stop_exists": DAEMON_STOP.exists(),
        })

    @mcp.tool()
    def self_enqueue_template(template: str = "daily_queue_retro") -> str:
        """Enqueue one allowlisted self-initiation template if governance permits it."""
        return _json(_self_enqueue_template(template, trigger="manual_self_enqueue_tool"))

    @mcp.tool()
    def enqueue_task(project: str, task: str, priority: int = 0,
                     risk: str = "normal", track: str = "quick",
                     autonomy: str = "L3", operation: str = "local_mcp",
                     max_attempts: int = 2, context_json: str = "{}") -> str:
        """Compatibility stub; direct queue admission is permanently blocked."""
        return _json({
            "status": "blocked",
            "reason": (
                "direct enqueue_task is disabled; submit an approved v1 TaskCard "
                "through approved_task_card_enqueue"
            ),
            "admission": "approved_task_card_enqueue_only",
            "no_task_created": True,
        })

    @mcp.tool()
    def approved_task_card_enqueue(
        task_card_json: str,
        openhands_workspace: str = "",
        execution_backend: str = "openhands",
        priority: int = 0,
    ) -> str:
        """Enqueue exactly one owner-approved v1 TaskCard."""
        task_card = _loads(task_card_json, {})
        return _json(
            _approved_task_card_enqueue_impl(
                task_card,
                openhands_workspace=openhands_workspace,
                execution_backend=execution_backend,
                priority=priority,
            )
        )

    @mcp.tool()
    def queue_status(limit: int = 20) -> str:
        """Return queue counts and recent tasks."""
        return _json({"db": str(QUEUE_DB), "counts": _task_counts(), "tasks": _list_tasks(limit), "runs": _latest_run_states(limit)})

    @mcp.tool()
    def task_status(task_id: str) -> str:
        """Return one queued task."""
        task = _load_task(task_id)
        if not task:
            return _json({"error": f"task not found: {task_id}"})
        run_id = (_task_context(task) or {}).get("run_id", "")
        return _json({"task": task, "run_state": _load_run_state(run_id) if run_id else {}})

    @mcp.tool()
    def run_state_status(run_id: str = "", task_id: str = "") -> str:
        """Return one RunState by run_id or task_id."""
        if task_id and not run_id:
            task = _load_task(task_id)
            run_id = (_task_context(task) or {}).get("run_id", "")
        if not run_id:
            return _json({"error": "run_id or task_id is required"})
        state = _load_run_state(run_id)
        if not state:
            return _json({"error": f"run state not found: {run_id}"})
        return _json({"run_state": state, "path": str(_run_state_path(run_id))})

    @mcp.tool()
    def task_card_status(task_id: str = "", task_card_id: str = "") -> str:
        """Return one generated task card by task_id or task_card_id."""
        if task_id and not task_card_id:
            task = _load_task(task_id)
            task_card_id = (_task_context(task) or {}).get("task_card_id", "")
        if not task_card_id:
            return _json({"error": "task_card_id or task_id is required"})
        path = _task_card_path(task_card_id)
        if not path.exists():
            return _json({"error": f"task card not found: {task_card_id}"})
        return _json({"task_card": _loads(path.read_text(encoding="utf-8"), {}), "path": str(path)})

    @mcp.tool()
    def runtime_control_snapshot() -> str:
        """Write and return the Agent OS runtime control snapshot."""
        return _json({"status": "generated", "path": str(CONTROL_SNAPSHOT), "snapshot": _write_control_snapshot()})

    @mcp.tool()
    def run_next_task() -> str:
        """Run the next queued or retry task."""
        task = _next_task()
        if not task:
            return _json({"status": "idle", "message": "no queued task"})
        task["status"] = "running"
        _save_task(task)
        _update_run_state(task, "dequeued_for_run", tool_calls=[{"tool": "task_queue_mcp.run_next_task", "ts": _now()}])
        return _json(_run_task(task))

    @mcp.tool()
    def run_queue(max_tasks: int = 5) -> str:
        """Run up to max_tasks queued tasks sequentially."""
        return build_queue_runner_payload(max_tasks)

    @mcp.tool()
    def configure_daemon(interval_seconds: int = 2, max_ticks: int = 5,
                         max_tasks_per_tick: int = 1, enabled: bool = True) -> str:
        """Write user-space daemon loop config. Does not install a system service."""
        config = {
            "enabled": bool(enabled),
            "interval_seconds": max(1, int(interval_seconds)),
            "max_ticks": max(1, int(max_ticks)),
            "max_tasks_per_tick": max(1, int(max_tasks_per_tick)),
            "admin_privileges": "forbidden",
            "updated": _now(),
        }
        QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
        DAEMON_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        if DAEMON_STOP.exists():
            DAEMON_STOP.unlink()
        return _json({"status": "configured", "config": config, "path": str(DAEMON_CONFIG)})

    @mcp.tool()
    def daemon_tick(max_tasks: int = 1) -> str:
        """Run one user-space daemon tick."""
        if DAEMON_STOP.exists():
            state = {"status": "stopped", "reason": "stop file present", "stop_file": str(DAEMON_STOP)}
            _write_daemon_state(state)
            return _json(state)
        return _json(_daemon_tick(max_tasks))

    @mcp.tool()
    def run_daemon_loop(max_ticks: int = 0, interval_seconds: int = 0,
                        max_tasks_per_tick: int = 0) -> str:
        """Run a finite user-space daemon loop. No service install, no admin privileges."""
        config = _read_daemon_config()
        if not config.get("enabled", True):
            state = {"status": "disabled", "config": config}
            _write_daemon_state(state)
            return _json(state)
        ticks = max(1, int(max_ticks or config.get("max_ticks", 5)))
        interval = max(1, int(interval_seconds or config.get("interval_seconds", 2)))
        per_tick = max(1, int(max_tasks_per_tick or config.get("max_tasks_per_tick", 1)))
        history = []
        for idx in range(ticks):
            if DAEMON_STOP.exists():
                break
            tick = _daemon_tick(per_tick)
            tick["tick"] = idx + 1
            history.append(tick)
            if idx < ticks - 1 and not DAEMON_STOP.exists():
                time.sleep(interval)
        state = {
            "status": "completed" if not DAEMON_STOP.exists() else "stopped",
            "ticks": len(history),
            "history": history,
            "counts": _task_counts(),
            "admin_privileges": "not_requested",
        }
        _write_daemon_state(state)
        return _json(state)

    @mcp.tool()
    def daemon_status() -> str:
        """Return daemon config and latest state."""
        return _json({
            "config": _read_daemon_config(),
            "state": _read_daemon_state(),
            "stop_file_exists": DAEMON_STOP.exists(),
            "stop_file": str(DAEMON_STOP),
        })

    @mcp.tool()
    def stop_daemon() -> str:
        """Create stop file for the user-space daemon loop."""
        QUEUE_ROOT.mkdir(parents=True, exist_ok=True)
        DAEMON_STOP.write_text(_now(), encoding="utf-8")
        state = {"status": "stop_requested", "stop_file": str(DAEMON_STOP)}
        _write_daemon_state(state)
        return _json(state)

    @mcp.tool()
    def retry_task(task_id: str) -> str:
        """Move a failed/blocked task back to retry if it does not request admin privileges."""
        task = _load_task(task_id)
        if not task:
            return _json({"error": f"task not found: {task_id}"})
        admin_hits = _blocked_by_admin(task["task"], task.get("context"))
        if admin_hits:
            return _json({"status": "blocked", "reason": "administrator privilege request is outside autonomy scope", "matched_terms": admin_hits})
        task["status"] = "retry"
        _save_task(task)
        _update_run_state(task, "retry_requested", decision="retry")
        return _json({"status": "retry", "task": task})

    @mcp.tool()
    def export_queue_report(output_path: str = "") -> str:
        """Export queue state to JSON."""
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = Path(output_path) if output_path else REPORT_DIR / f"queue_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report = {"generated": _now(), "counts": _task_counts(), "tasks": _list_tasks(200), "runs": _latest_run_states(200), "db": str(QUEUE_DB)}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "exported", "path": str(out), "counts": report["counts"]})

    @mcp.tool()
    def collect_gate_evidence(project: str, node_id: int = 0) -> str:
        """Collect execution evidence for a project, optionally filtered by gate node_id tag."""
        root = EXECUTION_DIR / _safe_project(project)
        items = []
        if root.exists():
            for path in sorted(root.glob("*/execution.json")):
                data = _loads(path.read_text(encoding="utf-8"), {})
                if not isinstance(data, dict):
                    continue
                if node_id and int(data.get("node_id") or 0) != int(node_id):
                    continue
                items.append({
                    "task_dir": path.parent.name,
                    "status": data.get("status"),
                    "returncode": data.get("returncode"),
                    "node_id": data.get("node_id"),
                    "ended": data.get("ended"),
                    "artifacts_ok": data.get("artifacts_ok"),
                    "evidence_path": str(path),
                })
        return _json({
            "project": project,
            "node_id_filter": int(node_id) if node_id else "all",
            "total": len(items),
            "completed": sum(1 for item in items if item.get("status") == "completed"),
            "evidence": items,
            "latest": items[-1] if items else None,
        })

    return mcp


def main() -> None:
    build_server().run()
