"""Incident evidence payload builder."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .policy import RecoveryDecision
from .records import FailureRecord


def build_incident_payload(
    record: FailureRecord,
    decision: RecoveryDecision,
    *,
    incident_id: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "incident_id": incident_id,
        "task_id": record.task_id,
        "failure": record.to_dict(),
        "recovery_decision": decision.to_dict(),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "execution_performed": False,
        "provider_api_call": False,
        "network": False,
        "sandbox": False,
        "runtime_writeback": False,
        "automatic_retry": False,
        "automatic_fallback": False,
        "automatic_rollback": False,
    }
