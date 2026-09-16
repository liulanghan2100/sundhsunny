"""Read-only recovery policy selection.

This module selects a recommendation. It never retries, falls back, rolls back,
calls providers, invokes tools, or writes runtime state.
"""

from __future__ import annotations

from dataclasses import dataclass

from .records import FailureRecord


@dataclass(frozen=True)
class RecoveryDecision:
    failure_type: str
    action: str
    owner_required: bool
    automatic_action_allowed: bool
    rationale: str

    def to_dict(self) -> dict[str, object]:
        return {
            "failure_type": self.failure_type,
            "action": self.action,
            "owner_required": self.owner_required,
            "automatic_action_allowed": self.automatic_action_allowed,
            "rationale": self.rationale,
        }


def select_recovery_policy(record: FailureRecord) -> RecoveryDecision:
    """Return a conservative action recommendation for a failure record."""
    policies = {
        "transient": (
            "retry_pending_owner_or_policy",
            True,
            "Transient failures may be retried only after an explicit gate.",
        ),
        "config": (
            "hold",
            True,
            "Configuration failures require correction before another attempt.",
        ),
        "permission": (
            "owner_gate",
            True,
            "Permission failures require owner review.",
        ),
        "provider": (
            "fallback_pending_owner_gate",
            True,
            "Provider failures cannot trigger an unapproved fallback.",
        ),
        "tool": (
            "hold_or_allowlisted_retry",
            True,
            "Tool recovery requires an allowlisted target and owner-approved context.",
        ),
        "network": (
            "hold",
            True,
            "Network failures remain blocked in the current execution policy.",
        ),
        "sandbox": (
            "hold",
            True,
            "Sandbox failures remain blocked in the current execution policy.",
        ),
        "schema": (
            "hold",
            True,
            "Schema failures must be corrected before execution.",
        ),
        "unknown": (
            "owner_review",
            True,
            "Unknown outcomes require owner review before recovery.",
        ),
    }
    action, owner_required, rationale = policies[record.failure_type]
    return RecoveryDecision(
        failure_type=record.failure_type,
        action=action,
        owner_required=owner_required,
        automatic_action_allowed=False,
        rationale=rationale,
    )
