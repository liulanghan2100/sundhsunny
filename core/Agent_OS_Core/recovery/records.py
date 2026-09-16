"""Machine-verifiable failure records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


FAILURE_TYPES = frozenset(
    {
        "transient",
        "config",
        "permission",
        "provider",
        "tool",
        "network",
        "sandbox",
        "schema",
        "unknown",
    }
)


@dataclass(frozen=True)
class FailureRecord:
    failure_id: str
    task_id: str
    failure_type: str
    source: str
    retryable: bool
    owner_required: bool
    recovery_hint: str
    evidence_path: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureRecord":
        return cls(
            failure_id=str(data.get("failure_id", "")),
            task_id=str(data.get("task_id", "")),
            failure_type=str(data.get("failure_type", "")),
            source=str(data.get("source", "")),
            retryable=bool(data.get("retryable", False)),
            owner_required=bool(data.get("owner_required", False)),
            recovery_hint=str(data.get("recovery_hint", "")),
            evidence_path=str(data.get("evidence_path", "")),
            created_at=str(data.get("created_at", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_failure_record(
    record: FailureRecord | dict[str, Any],
) -> tuple[bool, list[str]]:
    data = record.to_dict() if isinstance(record, FailureRecord) else dict(record)
    required = (
        "failure_id",
        "task_id",
        "failure_type",
        "source",
        "retryable",
        "owner_required",
        "recovery_hint",
        "evidence_path",
        "created_at",
    )
    errors = [
        f"missing field: {field}"
        for field in required
        if field not in data or data.get(field) in (None, "")
    ]
    if data.get("failure_type") not in FAILURE_TYPES:
        errors.append("failure_type is not in the approved enum")
    if not isinstance(data.get("retryable"), bool):
        errors.append("retryable must be boolean")
    if not isinstance(data.get("owner_required"), bool):
        errors.append("owner_required must be boolean")
    return not errors, errors
