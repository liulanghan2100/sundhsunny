"""Machine-verifiable knowledge and lab archive record shapes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


KNOWLEDGE_LAYERS = frozenset({"quarantine", "trusted", "deprecated"})
TRUST_STATUSES = frozenset({"unreviewed", "reviewed", "verified", "stale"})


@dataclass(frozen=True)
class KnowledgeRecord:
    knowledge_id: str
    title: str
    source_path: str
    source_hash: str
    layer: str
    trust_status: str
    owner_gate: str
    allowed_use: str
    promotion_path: str
    created_at: str
    last_review: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeRecord":
        return cls(
            knowledge_id=str(data.get("knowledge_id", "")),
            title=str(data.get("title", "")),
            source_path=str(data.get("source_path", "")),
            source_hash=str(data.get("source_hash", "")),
            layer=str(data.get("layer", "")),
            trust_status=str(data.get("trust_status", "")),
            owner_gate=str(data.get("owner_gate", "")),
            allowed_use=str(data.get("allowed_use", "")),
            promotion_path=str(data.get("promotion_path", "")),
            created_at=str(data.get("created_at", "")),
            last_review=str(data.get("last_review", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LabArchiveRecord:
    archive_id: str
    title: str
    surface: str
    source_path: str
    source_hash: str
    isolation_policy: str
    owner_gate: str
    evidence_path: str
    created_at: str
    last_review: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LabArchiveRecord":
        return cls(
            archive_id=str(data.get("archive_id", "")),
            title=str(data.get("title", "")),
            surface=str(data.get("surface", "")),
            source_path=str(data.get("source_path", "")),
            source_hash=str(data.get("source_hash", "")),
            isolation_policy=str(data.get("isolation_policy", "")),
            owner_gate=str(data.get("owner_gate", "")),
            evidence_path=str(data.get("evidence_path", "")),
            created_at=str(data.get("created_at", "")),
            last_review=str(data.get("last_review", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _missing(data: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if data.get(field) in (None, "")]


def validate_knowledge_record(
    record: KnowledgeRecord | dict[str, Any],
) -> tuple[bool, list[str]]:
    data = record.to_dict() if isinstance(record, KnowledgeRecord) else dict(record)
    required = (
        "knowledge_id",
        "title",
        "source_path",
        "source_hash",
        "layer",
        "trust_status",
        "owner_gate",
        "allowed_use",
        "promotion_path",
        "created_at",
        "last_review",
    )
    errors = [f"missing field: {field}" for field in _missing(data, required)]
    if data.get("layer") not in KNOWLEDGE_LAYERS:
        errors.append("layer is not quarantine, trusted, or deprecated")
    if data.get("trust_status") not in TRUST_STATUSES:
        errors.append("trust_status is not in the approved enum")
    if data.get("layer") == "trusted" and not data.get("source_path"):
        errors.append("trusted knowledge requires source_path")
    if data.get("layer") == "trusted" and not data.get("source_hash"):
        errors.append("trusted knowledge requires source_hash")
    return not errors, errors


def validate_lab_archive_record(
    record: LabArchiveRecord | dict[str, Any],
) -> tuple[bool, list[str]]:
    data = record.to_dict() if isinstance(record, LabArchiveRecord) else dict(record)
    required = (
        "archive_id",
        "title",
        "surface",
        "source_path",
        "source_hash",
        "isolation_policy",
        "owner_gate",
        "evidence_path",
        "created_at",
        "last_review",
    )
    errors = [f"missing field: {field}" for field in _missing(data, required)]
    if data.get("isolation_policy") != "no_formal_knowledge_writeback":
        errors.append("lab archive isolation_policy must block formal knowledge writeback")
    return not errors, errors
