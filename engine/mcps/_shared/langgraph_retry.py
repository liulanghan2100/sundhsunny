# -*- coding: utf-8 -*-
"""Shared helpers for LangGraph targeted retry harnesses."""
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


def load_json(path: Path, *, encoding: str = "utf-8") -> dict:
    """Read one JSON object for retry/report runners."""
    return json.loads(path.read_text(encoding=encoding))


def load_filtered_rows(path: Path, predicate: Callable[[dict], bool], *, encoding: str = "utf-8") -> list[dict]:
    """Load inventory rows selected by a pure predicate."""
    data = load_json(path, encoding=encoding)
    return [row for row in data.get("items", []) if predicate(row)]


def load_progress(path: Path, default: dict, *, encoding: str = "utf-8") -> dict:
    """Read an existing progress object or return a caller-owned default."""
    if path.exists():
        return load_json(path, encoding=encoding)
    return dict(default)


def read_run_blob(path: Path, fields: tuple[str, ...] = ("prompt", "result", "content")) -> str:
    """Flatten selected run-step fields into an evidence-only search blob."""
    if not path.exists():
        return ""
    try:
        run = load_json(path)
    except Exception:
        return ""
    return "\n".join(
        "\n".join(str(step.get(field, "")) for field in fields)
        for step in run.get("steps", [])
    )


def rows_by_id(path: Path, *, encoding: str = "utf-8") -> dict[str, dict]:
    """Index inventory items by task id without executing the runner."""
    data = load_json(path, encoding=encoding)
    return {row["task_id"]: row for row in data.get("items", [])}


def select_rows_by_buckets(
    path: Path,
    selection: dict[str, list[str]],
    *,
    encoding: str = "utf-8",
) -> list[dict]:
    """Expand a bucket-to-task-id selection into annotated inventory rows."""
    indexed = rows_by_id(path, encoding=encoding)
    rows = []
    for bucket, task_ids in selection.items():
        for task_id in task_ids:
            row = dict(indexed.get(task_id, {"task_id": task_id}))
            row["mixed_bucket"] = bucket
            rows.append(row)
    return rows


def _research_root(root: Path) -> Path:
    for path in root.glob("09_*"):
        if (path / "agent_os_langgraph_runtime_adapter" / "max_steps_modality_inventory_v0.1.json").exists():
            return path
    raise FileNotFoundError("agent_os_langgraph_runtime_adapter/max_steps_modality_inventory_v0.1.json not found")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_one(
    adapter_script: Path,
    venv_python: Path,
    task_id: str,
    timeout_s: int,
    env_overrides: dict[str, str] | None = None,
) -> tuple[dict | None, str]:
    cmd = [str(venv_python) if venv_python.exists() else sys.executable, str(adapter_script), "--task-id", task_id, "--json"]
    env = None
    if env_overrides:
        env = dict(os.environ)
        env.update(env_overrides)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(adapter_script.parent),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return None, f"harness_timeout_after_{timeout_s}s"
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or f"exit_{proc.returncode}")[-1200:]
    try:
        return json.loads(proc.stdout), ""
    except Exception as exc:
        return None, f"bad_json_output: {exc}; stdout={proc.stdout[-700:]}"


def run_retry_loop(
    *,
    rows: list[dict],
    truths: dict[str, str],
    timeout_s: int,
    label: str,
    score_fn: Callable[[dict, dict | None, str, dict[str, str]], dict],
    write_outputs_fn: Callable[[list[dict]], None],
    run_one_fn: Callable[[str, int], tuple[dict | None, str]],
) -> list[dict]:
    results = []
    for idx, row in enumerate(rows, 1):
        task_id = row["task_id"]
        print(f"[{idx}/{len(rows)}] retry {label} task {task_id[:8]} timeout={timeout_s}s")
        sys.stdout.flush()
        rec, error = run_one_fn(task_id, timeout_s)
        scored = score_fn(row, rec, error, truths)
        results.append(scored)
        write_outputs_fn(results)
        print(f"  -> status={scored['status']} matched={scored['matched']} answer={scored['final_answer'][:70]!r}")
        sys.stdout.flush()
    write_outputs_fn(results)
    return results
