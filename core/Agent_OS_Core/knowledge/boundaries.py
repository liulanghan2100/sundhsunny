"""Read-only classification and promotion guards for knowledge boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LAB_ARCHIVE_SURFACES = frozenset(
    {"GAIA", "LangGraph", "Firecrawl", "Cognee", "Omnigent", "Better Harness"}
)


@dataclass(frozen=True)
class KnowledgeBoundaryDecision:
    allowed: bool
    action: str
    reason: str
    requires_owner_gate: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action,
            "reason": self.reason,
            "requires_owner_gate": self.requires_owner_gate,
        }


def classify_knowledge_boundary(
    *,
    layer: str,
    source_kind: str,
) -> KnowledgeBoundaryDecision:
    if source_kind == "lab_archive":
        return KnowledgeBoundaryDecision(
            allowed=False,
            action="isolate",
            reason="lab artifacts cannot update core or formal knowledge directly",
            requires_owner_gate=True,
        )
    if layer == "quarantine":
        return KnowledgeBoundaryDecision(
            allowed=False,
            action="hold",
            reason="quarantine items are not routable",
            requires_owner_gate=True,
        )
    if layer == "trusted":
        return KnowledgeBoundaryDecision(
            allowed=True,
            action="read",
            reason="trusted knowledge may be read when source and review metadata are present",
            requires_owner_gate=False,
        )
    return KnowledgeBoundaryDecision(
        allowed=False,
        action="hold",
        reason="unknown or non-promoted knowledge layer",
        requires_owner_gate=True,
    )


def evaluate_promotion(
    *,
    source_kind: str,
    target: str,
    owner_gate_approved: bool,
) -> KnowledgeBoundaryDecision:
    if target in {"core", "skill_standard", "memory"} and not owner_gate_approved:
        return KnowledgeBoundaryDecision(
            allowed=False,
            action="block",
            reason="promotion target requires an explicit owner gate",
            requires_owner_gate=True,
        )
    if source_kind == "lab_archive":
        return KnowledgeBoundaryDecision(
            allowed=False,
            action="block",
            reason="lab archive cannot promote directly into core or formal surfaces",
            requires_owner_gate=True,
        )
    if target == "skill_standard":
        return KnowledgeBoundaryDecision(
            allowed=False,
            action="block",
            reason="Skill standard promotion must pass Nuwa or Darwin intake",
            requires_owner_gate=True,
        )
    if target == "runtime":
        return KnowledgeBoundaryDecision(
            allowed=False,
            action="block",
            reason="knowledge promotion cannot enable runtime routing",
            requires_owner_gate=True,
        )
    return KnowledgeBoundaryDecision(
        allowed=owner_gate_approved,
        action="promote" if owner_gate_approved else "hold",
        reason="promotion is limited to an explicitly approved non-runtime target",
        requires_owner_gate=not owner_gate_approved,
    )
