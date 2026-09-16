"""AutoRobot bridge for Agent OS TaskCard drafts and outcome reviews.

AutoRobot stays in the exploration role here:
- build TaskCard drafts for Agent OS review
- build queue payloads only from approved TaskCards
- review RunState/EvidenceRecord outputs after execution

This module does not enqueue tasks, approve tasks, execute workers, call
providers, write registry/status/Skill records, or write outside AutoRobot.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent

for path in (REPO_ROOT, ROOT / "02_workflow_engine", ROOT / "workflows"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from Agent_OS_Core.schemas import (  # noqa: E402
    validate_evidence_record,
    validate_run_state,
    validate_task_card,
)
from Agent_OS_Core.agent_os import intake_task  # noqa: E402
from guard import validate_path  # noqa: E402
from task_intent import TaskIntentClassifier  # noqa: E402


DRAFT_DIR = ROOT / "processing" / "agent_os_task_cards"
REVIEW_DIR = ROOT / "logs" / "agent_os_outcome_reviews"
DEFAULT_SKILL_VERSION = "local"
DEFAULT_ROUTER_ID = "autorobot-task-planner"
DEFAULT_POLICY_VERSION = "autorobot-draft-policy-v1"


SKILL_BY_TASK_TYPE = {
    "code_fix": ("code-review", "Code repair needs review and validation."),
    "doc_generation": ("documents", "Document generation task."),
    "structure_analysis": ("mckinsey-structured-thinking", "Structure analysis task."),
    "test_addition": ("code-review", "Regression and test task."),
    "config_check": ("manual-gates", "Configuration task needs controlled gates."),
    "self_mutation": ("darwin-runbook", "Self-improvement task needs evolution controls."),
    "external_readonly_diagnosis": ("research", "Read-only diagnosis task."),
    "value_asset": ("manual-gates", "Value asset task needs staged gates."),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _safe_write(path: Path, payload: str) -> None:
    check = validate_path(path)
    if check.get("action") != "ALLOW":
        raise PermissionError(str(check.get("reason") or "AutoRobot path denied"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _skill_file(skill_id: str) -> Path | None:
    candidates = [
        Path.home() / ".codex" / "skills" / skill_id / "SKILL.md",
        Path.home() / ".codex" / "skills" / ".system" / skill_id / "SKILL.md",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _skill_hash(skill_id: str, version: str = DEFAULT_SKILL_VERSION) -> tuple[str, str]:
    path = _skill_file(skill_id)
    if path is None:
        return _digest_text(f"{skill_id}:{version}:unresolved"), "synthetic_descriptor"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(), str(path)


def build_task_profile(user_task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify a user task into an AutoRobot task profile."""
    context = context or {}
    signal = {
        "title": user_task,
        "text": user_task,
        "target": context.get("target"),
        "risk": context.get("risk"),
        "repair_hint": context.get("repair_hint"),
        "value_contract": context.get("value_contract"),
        "next_best_asset": context.get("next_best_asset"),
    }
    classifier = TaskIntentClassifier()
    intent = classifier.classify(signal, str(context.get("source") or "user_task"))
    plan = classifier.build_plan(intent, signal)
    return {
        "task_profile": intent["task_type"],
        "confidence": intent["confidence"],
        "risk": intent["risk"],
        "intent": intent,
        "plan": plan,
        "source": context.get("source") or "user_task",
        "created_at": now_iso(),
    }


def generate_skill_candidates(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ranked Skill candidates without executing or approving them."""
    task_type = str(profile.get("task_profile") or "structure_analysis")
    primary, reason = SKILL_BY_TASK_TYPE.get(
        task_type, SKILL_BY_TASK_TYPE["structure_analysis"]
    )
    fallback = "manual-gates" if primary != "manual-gates" else "research"
    candidates = []
    for rank, (skill_id, score, why) in enumerate(
        [(primary, 0.9, reason), (fallback, 0.65, "Fallback governance/research skill.")],
        start=1,
    ):
        content_hash, hash_source = _skill_hash(skill_id)
        candidates.append(
            {
                "skill_id": skill_id,
                "score": score,
                "rank": rank,
                "reason": why,
                "version": DEFAULT_SKILL_VERSION,
                "content_hash": content_hash,
                "hash_source": hash_source,
            }
        )
    return candidates


def build_task_card_draft(
    user_task: str,
    *,
    context: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Build an Agent OS TaskCard v1 draft for later approval."""
    context = context or {}
    profile = build_task_profile(user_task, context)
    intake = intake_task(
        user_task,
        llm_actions=context.get("requested_actions"),
        task_profile=str(profile["task_profile"]),
        context=context,
    )
    candidates = generate_skill_candidates(profile)
    selected = candidates[0]
    created_at = now_iso()
    card = {
        "schema_version": "agent-os-task-card-v1",
        "task_id": task_id or f"arb-agent-os-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "project": str(context.get("project") or "agent-os-autobot-planning"),
        "task_profile": str(profile["task_profile"]),
        "objective": user_task,
        "risk_level": {"L1": "low", "L2": "medium", "L3": "high"}[
            intake["risk"]["risk_level"]
        ],
        "risk_tier": intake["risk"]["risk_level"],
        "status": "pending_approval",
        "selected_skill": {
            "skill_id": selected["skill_id"],
            "version": selected["version"],
            "content_hash": selected["content_hash"],
            "selection_reason": selected["reason"],
        },
        "router_decision": {
            "router_id": DEFAULT_ROUTER_ID,
            "router_version": "v1",
            "candidates": [
                {
                    "skill_id": item["skill_id"],
                    "score": item["score"],
                    "rank": item["rank"],
                    "reason": item["reason"],
                }
                for item in candidates
            ],
            "selected_skill_id": selected["skill_id"],
            "selection_reason": selected["reason"],
            "decided_at": created_at,
        },
        "policy_decision": {
            "decision": "hold",
            "policy_version": DEFAULT_POLICY_VERSION,
            "rules_evaluated": ["autorobot_draft_only", "agent_os_approval_required"],
            "filtered_candidates": [
                {
                    "skill_id": item["skill_id"],
                    "decision": "hold",
                    "rule_id": "requires_agent_os_owner_gate",
                    "reason": "AutoRobot may draft but cannot approve execution.",
                }
                for item in candidates
            ],
            "reason": "Draft only; Agent OS approval required before enqueue.",
            "decided_at": created_at,
        },
        "execution_contract": {
            "execution_mode": "plan_only",
            "allowed_tools": [],
            "allowed_paths": ["AutoRobot/**"],
            "blocked_paths": [
                "Agent_OS_Core/**",
                "03_*/**",
                "04_*/**",
                "10_*/**",
                "external_execution/**",
            ],
            "allowed_actions": ["classify", "plan", "draft_task_card", "review"],
            "forbidden_actions": [
                "provider_api",
                "network",
                "sandbox",
                "runtime_dispatch",
                "runtime_writeback",
                "registry_writeback",
                "status_writeback",
                "skill_writeback",
                "file_move",
                "file_delete",
            ],
            "stop_conditions": ["boundary_escape", "missing_owner_approval"],
            "command": ["python", "-c", "print('plan-only TaskCard draft')"],
            "budget": {"max_minutes": 10, "max_cost_usd": 0, "max_retries": 0},
        },
        "acceptance_criteria": [
            {
                "criterion_id": "agent_os_owner_review",
                "description": "Agent OS validates and approves before execution.",
                "verifier": "agent_os_schema_and_policy",
                "required": True,
            }
        ],
        "failure_policy": {
            "retryable_failure_types": [],
            "max_attempts": 1,
            "on_exhaustion": "owner_review",
            "silent_fallback": False,
        },
        "expected_artifacts": [
            {
                "artifact_id": "taskcard_draft",
                "path": "AutoRobot/processing/agent_os_task_cards",
                "artifact_type": "json",
                "required": True,
            }
        ],
        "provenance": {"source": str(context.get("source") or "autorobot"), "created_by": "AutoRobot"},
        "created_at": created_at,
    }
    card["intake"] = {
        "intake_id": intake["intake_id"],
        "task_profile": intake["task_profile"],
        "risk_rules": intake["risk"]["matched_rules"],
        "effective_actions": intake["risk"]["actions"]["effective_actions"],
    }
    validation = validate_task_card(card)
    if not validation.valid:
        raise ValueError("TaskCard draft validation failed: " + "; ".join(validation.errors))
    return card


def write_task_card_draft(card: dict[str, Any]) -> dict[str, Any]:
    """Persist a TaskCard draft inside AutoRobot only."""
    validation = validate_task_card(card)
    if not validation.valid:
        raise ValueError("TaskCard draft validation failed: " + "; ".join(validation.errors))
    out = DRAFT_DIR / f"{card['task_id']}.json"
    _safe_write(out, json.dumps(card, ensure_ascii=False, indent=2, default=str))
    return {
        "status": "written",
        "task_id": card["task_id"],
        "path": str(out),
        "boundary": "AutoRobot draft only; not enqueued and not approved",
    }


def build_queue_payload(
    approved_task_card: dict[str, Any],
    *,
    openhands_workspace: str,
    execution_backend: str = "openhands",
) -> dict[str, Any]:
    """Build, but do not enqueue, a Task Queue payload from an approved TaskCard."""
    validation = validate_task_card(approved_task_card)
    if not validation.valid:
        raise ValueError("approved TaskCard validation failed: " + "; ".join(validation.errors))
    if approved_task_card.get("status") != "approved":
        raise ValueError("TaskCard must be approved before queue payload generation")
    if approved_task_card.get("approval", {}).get("decision") != "approve":
        raise ValueError("TaskCard approval decision must be approve")
    if approved_task_card.get("policy_decision", {}).get("decision") != "allow":
        raise ValueError("TaskCard policy decision must be allow")

    task_id = str(approved_task_card["task_id"])
    return {
        "project": approved_task_card["project"],
        "task": approved_task_card["objective"],
        "status": "queued",
        "priority": 1,
        "risk": approved_task_card.get("risk_level", "medium"),
        "track": "quick",
        "autonomy": "L2",
        "operation": "local_read",
        "attempts": 0,
        "max_attempts": approved_task_card["failure_policy"]["max_attempts"],
        "context": {
            "task_class": "B",
            "execution_backend": execution_backend,
            "openhands_workspace": openhands_workspace,
            "task_card": approved_task_card,
            "source": "autorobot_task_planner",
        },
        "proposed_queue_task_id": f"queue-{task_id}",
        "boundary": "queue payload draft only; caller must enqueue through Task Queue",
    }


def build_outcome_review(
    task_card: dict[str, Any],
    run_state: dict[str, Any],
    evidence_record: dict[str, Any],
    *,
    evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    """Review execution output for AutoRobot learning without writing Memory."""
    run_validation = validate_run_state(run_state)
    evidence_validation = validate_evidence_record(
        evidence_record,
        evidence_root=evidence_root or run_state.get("evidence_dir") or ROOT / "07_data",
        verify_hash=False,
    )
    completed = run_state.get("status") == "completed"
    evidence_passed = evidence_record.get("validation_status") == "pass"
    eligible = completed and run_validation.valid and evidence_validation.valid and evidence_passed
    outcome = {
        "task_id": task_card.get("task_id"),
        "goal": task_card.get("objective"),
        "state": run_state.get("status", "unknown"),
        "passed": eligible,
        "task_card": task_card,
        "run_state": run_state,
        "evidence_record": evidence_record,
        "validation": {
            "run_state": run_validation.to_dict(),
            "evidence_record": evidence_validation.to_dict(),
        },
        "failure_class": run_state.get("failure_class"),
        "policy_delta": (
            {"preserve_policy": True}
            if eligible
            else {"tighten_guard": True, "require_replay": True}
        ),
        "memory_candidate": {
            "eligible": eligible,
            "required_gate": "Memory writeback owner gate",
            "action": (
                "eligible_for_owner_gated_memory_write"
                if eligible
                else "hold_memory_write_until_verified"
            ),
        },
        "boundary": "review only; no Memory, registry, status, or Skill writeback",
        "reviewed_at": now_iso(),
    }
    return outcome


def write_outcome_review(review: dict[str, Any]) -> dict[str, Any]:
    """Persist an AutoRobot outcome review without writing long-term Memory."""
    task_id = str(review.get("task_id") or "unknown_task")
    out_json = REVIEW_DIR / f"{task_id}.json"
    out_md = REVIEW_DIR / f"{task_id}.md"
    _safe_write(out_json, json.dumps(review, ensure_ascii=False, indent=2, default=str))
    lines = [
        "# Agent OS Outcome Review",
        "",
        f"- Task ID: `{task_id}`",
        f"- State: `{review.get('state')}`",
        f"- Passed: `{review.get('passed')}`",
        f"- Memory candidate: `{review.get('memory_candidate', {}).get('action')}`",
        f"- Boundary: `{review.get('boundary')}`",
    ]
    _safe_write(out_md, "\n".join(lines) + "\n")
    return {"status": "written", "json_path": str(out_json), "md_path": str(out_md)}


def build_closed_loop_packet(user_task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the full pre-execution AutoRobot packet for Agent OS review."""
    card = build_task_card_draft(user_task, context=context)
    write_result = write_task_card_draft(card)
    return {
        "status": "draft_ready_for_agent_os",
        "task_card": card,
        "draft_write": write_result,
        "next_system": "Agent OS",
        "next_required_action": "schema_policy_owner_gate_review",
        "boundary": "AutoRobot planning only",
    }


__all__ = [
    "build_closed_loop_packet",
    "build_outcome_review",
    "build_queue_payload",
    "build_task_card_draft",
    "build_task_profile",
    "generate_skill_candidates",
    "write_outcome_review",
    "write_task_card_draft",
]
