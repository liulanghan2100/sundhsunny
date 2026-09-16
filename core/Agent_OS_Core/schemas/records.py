"""Machine-verifiable Agent OS record shapes.

These records are intentionally stdlib-only. They describe the governance
surface without importing runtime, provider, network, or tool code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


DecisionValue = str
RunStatus = str
RunMode = str
EvidenceRecordType = str
ValidationStatus = str


DECISION_VALUES = frozenset({"approve", "hold", "reject"})

RUN_STATUSES = frozenset(
    {"pending", "approved", "running", "blocked", "failed", "completed"}
)

RUN_MODES = frozenset(
    {
        "plan_only",
        "validation",
        "synthetic_dry_run",
        "monkeypatched_provider",
        "local_read_only_tool",
        "real_provider_gated",
    }
)

EVIDENCE_RECORD_TYPES = frozenset(
    {
        "plan",
        "owner_gate",
        "decision_record",
        "verification",
        "dry_run",
        "trace",
        "closure_report",
        "incident_report",
    }
)

VALIDATION_STATUSES = frozenset({"pass", "fail", "hold"})


@dataclass(frozen=True)
class DecisionRecord:
    record_id: str
    decision_id: str
    decision: DecisionValue
    owner_gate: str
    scope: str
    allowed_actions: tuple[str, ...] = field(default_factory=tuple)
    blocked_actions: tuple[str, ...] = field(default_factory=tuple)
    evidence_path: str = ""
    created_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionRecord":
        return cls(
            record_id=str(data.get("record_id", "")),
            decision_id=str(data.get("decision_id", "")),
            decision=str(data.get("decision", "")),
            owner_gate=str(data.get("owner_gate", "")),
            scope=str(data.get("scope", "")),
            allowed_actions=tuple(str(v) for v in data.get("allowed_actions", ())),
            blocked_actions=tuple(str(v) for v in data.get("blocked_actions", ())),
            evidence_path=str(data.get("evidence_path", "")),
            created_at=str(data.get("created_at", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunState:
    run_id: str
    task_id: str
    mode: RunMode
    status: RunStatus
    risk_level: str
    validation_context: bool
    boundary_patch_state: str
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    allowed_model: str = ""
    evidence_dir: str = ""
    trace_path: str = ""
    stop_conditions: tuple[str, ...] = field(default_factory=tuple)
    production_context: bool = False
    owner_gate: str = ""
    runtime_writeback_allowed: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunState":
        return cls(
            run_id=str(data.get("run_id", "")),
            task_id=str(data.get("task_id", "")),
            mode=str(data.get("mode", "")),
            status=str(data.get("status", "")),
            risk_level=str(data.get("risk_level", "")),
            validation_context=bool(data.get("validation_context", False)),
            boundary_patch_state=str(data.get("boundary_patch_state", "")),
            allowed_tools=tuple(str(v) for v in data.get("allowed_tools", ())),
            allowed_model=str(data.get("allowed_model", "")),
            evidence_dir=str(data.get("evidence_dir", "")),
            trace_path=str(data.get("trace_path", "")),
            stop_conditions=tuple(str(v) for v in data.get("stop_conditions", ())),
            production_context=bool(data.get("production_context", False)),
            owner_gate=str(data.get("owner_gate", "")),
            runtime_writeback_allowed=bool(
                data.get("runtime_writeback_allowed", False)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    task_id: str
    record_type: EvidenceRecordType
    source: str
    artifact_path: str
    artifact_hash: str
    created_at: str
    validation_status: ValidationStatus

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRecord":
        return cls(
            evidence_id=str(data.get("evidence_id", "")),
            task_id=str(data.get("task_id", "")),
            record_type=str(data.get("record_type", "")),
            source=str(data.get("source", "")),
            artifact_path=str(data.get("artifact_path", "")),
            artifact_hash=str(data.get("artifact_hash", "")),
            created_at=str(data.get("created_at", "")),
            validation_status=str(data.get("validation_status", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
