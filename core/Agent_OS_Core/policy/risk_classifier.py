"""Deterministic L1/L2/L3 risk classification."""
from __future__ import annotations

from typing import Any

from .action_pre_scan import scan_requested_actions


# agentos-hub：补齐 L3 动作集。
# action_pre_scan 新增的 financial / sensitive_read 必须在此登记，
# 否则会被检出却仍按 L1 放行（「转账100万」曾判为 L1）。
L3_ACTIONS = frozenset(
    {
        "delete",
        "move",
        "provider_api",
        "network",
        "sandbox",
        "publish",
        "credentials",
        "runtime_dispatch",
        "registry_writeback",
        "external_write",
        "financial",
        "sensitive_read",
    }
)
L2_ACTIONS = frozenset({"write"})


def classify_risk(
    request_text: str,
    *,
    llm_actions: list[str] | tuple[str, ...] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a conservative, machine-derived risk result.

    Missing or ambiguous side-effect information is elevated to L2. Any
    discovered external or destructive action is L3. Multiple actions take
    the highest level.
    """
    context = dict(context or {})
    scan = scan_requested_actions(request_text, llm_actions=llm_actions, context=context)
    actions = set(scan.effective_actions)
    dimensions = {
        "reversibility": "low",
        "impact": "local",
        "data_sensitivity": "normal",
        "external_side_effect": False,
        "cost_known": context.get("cost_budget_usd") is not None,
    }
    rules: list[str] = []
    if actions & L3_ACTIONS:
        level = "L3"
        dimensions["external_side_effect"] = True
        rules.append("high_impact_action_detected")
    elif actions & L2_ACTIONS:
        level = "L2"
        rules.append("local_mutation_detected")
    elif not request_text.strip() or context.get("risk_information_complete") is False:
        level = "L2"
        rules.append("missing_risk_information")
    else:
        level = "L1"
        rules.append("read_only_or_synthetic")
    if "credentials" in actions:
        dimensions["data_sensitivity"] = "sensitive"
        rules.append("sensitive_data_detected")
    if scan.disagreements:
        rules.append("llm_action_disagreement_escalates")
        if level == "L1":
            level = "L2"
    if context.get("production_context") or context.get("irreversible"):
        level = "L3"
        rules.append("production_or_irreversible_context")
    return {
        "risk_level": level,
        "matched_rules": rules,
        "risk_dimensions": dimensions,
        "actions": scan.to_dict(),
    }
