"""Execution depth policy for L1/L2/L3 tasks."""
from __future__ import annotations


def depth_policy(risk_level: str) -> dict:
    level = str(risk_level).upper()
    if level not in {"L1", "L2", "L3"}:
        raise ValueError("risk_level must be L1, L2, or L3")
    return {
        "risk_level": level,
        "owner_gate": level != "L1",
        "validator_mode": "sampled" if level == "L1" else "full",
        "completion_verifier": "lightweight" if level == "L1" else "full",
        "review_required": level == "L3",
        "timeout_policy": "expired_to_blocked" if level == "L3" else "bounded",
        "allowed_modes": {
            "L1": ["plan_only", "validation", "synthetic_dry_run"],
            "L2": ["validation", "synthetic_dry_run", "local_read_only_tool"],
            "L3": ["validation", "synthetic_dry_run", "monkeypatched_provider", "real_provider_gated"],
        }[level],
    }
