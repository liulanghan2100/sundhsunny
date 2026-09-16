"""Owner Gate DecisionRecord API.

The record is bound to the approved TaskCard scope. A changed card therefore
cannot reuse an earlier approval.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class DecisionRecordError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def task_scope_hash(task_card: dict[str, Any]) -> str:
    scope = {key: value for key, value in task_card.items() if key not in {"approval", "updated_at"}}
    return "sha256:" + hashlib.sha256(_canonical(scope).encode("utf-8")).hexdigest()


def build_decision_record(
    task_card: dict[str, Any],
    *,
    decision: str,
    decided_by: str,
    decision_id: str,
    expires_at: str | None = None,
    conditions: list[str] | None = None,
) -> dict[str, Any]:
    if decision not in {"approve", "hold", "reject"}:
        raise DecisionRecordError("decision must be approve, hold, or reject")
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "decision": decision,
        "decision_id": decision_id,
        "decided_by": decided_by,
        "decided_at": now,
        "scope_hash": task_scope_hash(task_card),
        "expires_at": expires_at,
        "conditions": list(conditions or []),
    }
    return record


def validate_decision_for_task(
    task_card: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    approval = task_card.get("approval")
    if not isinstance(approval, dict):
        return {"valid": False, "reason": "missing approval record", "status": "blocked"}
    if approval.get("decision") != "approve":
        return {"valid": False, "reason": "approval decision is not approve", "status": "blocked"}
    if not approval.get("decision_id") or not approval.get("decided_by"):
        return {"valid": False, "reason": "approval identity is incomplete", "status": "blocked"}
    expected = task_scope_hash(task_card)
    actual = approval.get("scope_hash")
    if actual and actual != expected:
        return {"valid": False, "reason": "approval scope hash does not match TaskCard", "status": "blocked"}
    expiry = approval.get("expires_at")
    if expiry:
        try:
            expiry_dt = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
            current = now or datetime.now(timezone.utc)
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
            if current >= expiry_dt:
                return {"valid": False, "reason": "owner gate expired", "status": "expired"}
        except ValueError:
            return {"valid": False, "reason": "invalid owner gate expiry", "status": "blocked"}
    return {"valid": True, "reason": "owner gate valid", "status": "approved", "scope_hash": expected}
