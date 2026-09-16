"""Rollback plan record builder without rollback execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .records import FailureRecord


def build_rollback_plan(
    record: FailureRecord,
    *,
    plan_id: str,
    candidate_paths: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "plan_id": plan_id,
        "task_id": record.task_id,
        "failure_id": record.failure_id,
        "candidate_paths": list(candidate_paths or []),
        "status": "planned",
        "owner_gate_required": True,
        "rollback_execution_allowed": False,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "file_move": False,
        "file_delete": False,
        "runtime_writeback": False,
    }
