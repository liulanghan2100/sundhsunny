"""Single deterministic intake entrypoint for task drafts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .depth_policy import depth_policy
from .risk_classifier import classify_risk


def build_intake(
    request_text: str,
    *,
    llm_actions: list[str] | None = None,
    task_profile: str = "general",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = dict(context or {})
    classification = classify_risk(request_text, llm_actions=llm_actions, context=context)
    level = classification["risk_level"]
    return {
        "intake_id": f"intake-{uuid4().hex[:16]}",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "raw_request": request_text,
        "task_profile": task_profile,
        "risk": classification,
        "depth": depth_policy(level),
        "status": "pending_approval" if level != "L1" else "ready_for_machine_preflight",
        "no_silent_downgrade": True,
    }
