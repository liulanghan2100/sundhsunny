"""Validation helpers for Agent OS schema records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .records import (
    DECISION_VALUES,
    EVIDENCE_RECORD_TYPES,
    RUN_MODES,
    RUN_STATUSES,
    VALIDATION_STATUSES,
    DecisionRecord,
    EvidenceRecord,
    RunState,
)


DEFAULT_EVIDENCE_ROOT = Path("09_research/agent-os-structure-slimming-v1")
TASK_CARD_SCHEMA_PATH = Path(__file__).with_name("task_card_schema_v1.json")


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def validate_task_card(record: dict[str, Any]) -> ValidationResult:
    """Validate a TaskCard against the machine-readable v1 contract."""
    if not isinstance(record, dict):
        return ValidationResult(valid=False, errors=("TaskCard must be an object",))

    try:
        from jsonschema import Draft7Validator
    except ImportError:
        return ValidationResult(
            valid=False,
            errors=("jsonschema dependency is required for TaskCard validation",),
        )

    try:
        schema = json.loads(TASK_CARD_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft7Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError) as exc:
        return ValidationResult(valid=False, errors=(f"TaskCard schema load failed: {exc}",))

    validator = Draft7Validator(schema)
    errors = tuple(
        f"{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path))
    )
    risk_tier = record.get("risk_tier")
    if risk_tier and risk_tier not in {"L1", "L2", "L3"}:
        errors.append("risk_tier must be L1, L2, or L3")
    if record.get("status") in {"approved", "running", "completed"}:
        from Agent_OS_Core.governance.owner_gate import validate_decision_for_task

        approval = validate_decision_for_task(record)
        if not approval["valid"]:
            errors.append(f"owner gate: {approval['reason']}")
    return ValidationResult(valid=not errors, errors=errors)


def _missing_fields(data: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [name for name in fields if name not in data or data.get(name) in (None, "")]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_decision_record(
    record: DecisionRecord | dict[str, Any],
    *,
    require_evidence_exists: bool = False,
) -> ValidationResult:
    data = record.to_dict() if isinstance(record, DecisionRecord) else dict(record)
    errors: list[str] = []
    warnings: list[str] = []

    required = (
        "record_id",
        "decision_id",
        "decision",
        "owner_gate",
        "scope",
        "allowed_actions",
        "blocked_actions",
        "evidence_path",
        "created_at",
    )
    errors.extend(f"missing field: {name}" for name in _missing_fields(data, required))

    if data.get("decision") not in DECISION_VALUES:
        errors.append("decision must be approve, hold, or reject")

    allowed = set(data.get("allowed_actions") or ())
    blocked = set(data.get("blocked_actions") or ())
    conflicts = sorted(allowed & blocked)
    if conflicts:
        errors.append(f"allowed_actions conflict with blocked_actions: {conflicts}")

    evidence_path = str(data.get("evidence_path") or "")
    if require_evidence_exists and not Path(evidence_path).exists():
        errors.append("evidence_path must exist for execution gates")
    elif evidence_path and not Path(evidence_path).exists():
        warnings.append("evidence_path does not exist yet")

    return ValidationResult(valid=not errors, errors=tuple(errors), warnings=tuple(warnings))


def validate_run_state(record: RunState | dict[str, Any]) -> ValidationResult:
    data = record.to_dict() if isinstance(record, RunState) else dict(record)
    errors: list[str] = []
    warnings: list[str] = []

    required = (
        "run_id",
        "task_id",
        "mode",
        "status",
        "risk_level",
        "validation_context",
        "boundary_patch_state",
        "allowed_tools",
        "allowed_model",
        "evidence_dir",
        "trace_path",
        "stop_conditions",
    )
    errors.extend(f"missing field: {name}" for name in _missing_fields(data, required))

    if data.get("status") not in RUN_STATUSES:
        errors.append("status is not in the approved RunState enum")

    if data.get("mode") not in RUN_MODES:
        errors.append("mode is not in the approved RunState enum")

    if bool(data.get("production_context", False)):
        errors.append("production context is blocked by default")

    if data.get("mode") == "real_provider_gated" and not data.get("owner_gate"):
        errors.append("real_provider_gated requires owner_gate metadata")

    if bool(data.get("runtime_writeback_allowed", False)):
        errors.append("runtime writeback must be false by default")

    if not bool(data.get("validation_context", False)):
        warnings.append("validation_context is false")

    return ValidationResult(valid=not errors, errors=tuple(errors), warnings=tuple(warnings))


def validate_evidence_record(
    record: EvidenceRecord | dict[str, Any],
    *,
    evidence_root: str | Path = DEFAULT_EVIDENCE_ROOT,
    verify_hash: bool = False,
) -> ValidationResult:
    data = record.to_dict() if isinstance(record, EvidenceRecord) else dict(record)
    errors: list[str] = []
    warnings: list[str] = []

    required = (
        "evidence_id",
        "task_id",
        "record_type",
        "source",
        "artifact_path",
        "artifact_hash",
        "created_at",
        "validation_status",
    )
    errors.extend(f"missing field: {name}" for name in _missing_fields(data, required))

    if data.get("record_type") not in EVIDENCE_RECORD_TYPES:
        errors.append("record_type is not in the approved EvidenceRecord enum")

    if data.get("validation_status") not in VALIDATION_STATUSES:
        errors.append("validation_status must be pass, fail, or hold")

    artifact_path = Path(str(data.get("artifact_path") or ""))
    root = Path(evidence_root)
    if str(artifact_path):
        if not _is_relative_to(artifact_path, root):
            errors.append("artifact_path is outside the approved evidence root")
        if verify_hash:
            if not artifact_path.exists():
                errors.append("artifact_path does not exist for hash verification")
            elif str(data.get("artifact_hash") or "") != _sha256(artifact_path):
                errors.append("artifact_hash does not match file content")
        elif not artifact_path.exists():
            warnings.append("artifact_path does not exist yet")

    return ValidationResult(valid=not errors, errors=tuple(errors), warnings=tuple(warnings))
