# -*- coding: utf-8 -*-
"""Decision and evidence workbench MCP.

This module distills ten external skills into structured, auditable helper
artifacts. It deliberately does not own task, approval, memory, runtime, or
completion state; those remain in the existing Agent OS services.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.io import _loads as shared_loads
from _shared.time import _now as shared_now

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
ARTIFACT_ROOT = DATA_ROOT / "09_投研" / "decision_workbench"
SOURCE_SKILLS = [
    "grill-me",
    "grill-with-docs",
    "improve-codebase-architecture",
    "tdd",
    "setup-matt-pocock-skills",
    "handoff",
    "triage",
    "prototype",
    "grilling",
    "teach",
]

ALLOWED_STATUSES = {
    "draft",
    "open",
    "answered",
    "verified",
    "accepted",
    "rejected",
    "expired",
    "closed",
}
TERMINAL_STATUSES = {"answered", "verified", "accepted", "closed"}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _safe(value: str, default: str = "default") -> str:
    cleaned = "".join(c for c in str(value or "") if c.isalnum() or c in "-_.")
    return cleaned or default


def _now() -> str:
    return shared_now()


def _artifact_dir(project: str) -> Path:
    return ARTIFACT_ROOT / _safe(project)


def _artifact_path(project: str, artifact_id: str) -> Path:
    return _artifact_dir(project) / f"{_safe(artifact_id)}.json"


def _artifact_id(kind: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{_safe(kind)}-{stamp}"


def _base_artifact(
    kind: str,
    project: str,
    source_skills: list[str] | None = None,
    owner_decision_required: bool = True,
) -> dict:
    now = _now()
    return {
        "id": _artifact_id(kind),
        "kind": kind,
        "project": project,
        "created_at": now,
        "updated_at": now,
        "status": "draft",
        "source_skills": source_skills or SOURCE_SKILLS,
        "provenance": {
            "producer": "decision_workbench_mcp",
            "mode": "distilled_method",
            "external_state_mutation": False,
        },
        "owner_decision_required": owner_decision_required,
        "evidence": [],
        "failure_conditions": [],
    }


def _write_artifact(artifact: dict) -> str:
    path = _artifact_path(artifact["project"], artifact["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact["updated_at"] = _now()
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _read_artifact(project: str, artifact_id: str) -> dict | None:
    path = _artifact_path(project, artifact_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_questions(value: str | list | None) -> list[dict]:
    raw = _loads(value, [])
    if not isinstance(raw, list):
        return []
    questions = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            item = {"question": item}
        if not isinstance(item, dict) or not str(item.get("question", "")).strip():
            continue
        questions.append({
            "id": str(item.get("id") or f"q{index}"),
            "question": str(item["question"]).strip(),
            "type": item.get("type", "owner_decision"),
            "dependencies": item.get("dependencies", []),
            "recommended_answer": item.get("recommended_answer"),
            "answer": item.get("answer"),
            "evidence": item.get("evidence", []),
            "status": item.get("status", "open"),
        })
    return questions


def _node_is_resolved(node: dict) -> bool:
    return (
        node.get("status") in TERMINAL_STATUSES
        and bool(str(node.get("answer") or "").strip())
    )


def _compute_frontier(nodes: list[dict]) -> list[str]:
    by_id = {str(node.get("id")): node for node in nodes}
    frontier = []
    for node in nodes:
        if node.get("status") not in {"open", "draft"}:
            continue
        dependencies = node.get("dependencies", [])
        if not isinstance(dependencies, list):
            continue
        if all(
            dependency in by_id and _node_is_resolved(by_id[dependency])
            for dependency in dependencies
        ):
            frontier.append(node["id"])
    return frontier


def _validate_evidence(evidence: Any) -> tuple[bool, list[str]]:
    """Validate evidence references without accepting caller-provided claims."""
    if not isinstance(evidence, list) or not evidence:
        return False, ["evidence must contain file references"]

    errors = []
    root = ROOT.resolve()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] must be an object with a path")
            continue
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            errors.append(f"evidence[{index}].path is required")
            continue
        path = Path(raw_path)
        resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(f"evidence[{index}] is outside the workspace")
            continue
        if not resolved.is_file():
            errors.append(f"evidence[{index}] does not reference an existing file")
    return not errors, errors


def _required_fields_for_brief() -> list[str]:
    return [
        "current_behavior",
        "target_behavior",
        "acceptance_criteria",
        "out_of_scope",
        "evidence",
    ]


def _missing_brief_fields(brief: dict) -> list[str]:
    missing = []
    for field in _required_fields_for_brief():
        value = brief.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    return missing


def _tdd_fit(change_shape: str, stable_oracle: bool, public_contract: bool,
             exploratory: bool, external_boundary: bool) -> dict:
    reasons = []
    if exploratory:
        reasons.append("探索性工作优先用 ExperimentCard，不先锁定 TDD 结构")
    if not stable_oracle:
        reasons.append("缺少稳定的行为 oracle")
    if not public_contract:
        reasons.append("尚未明确公共接口或可观察行为")
    if external_boundary:
        reasons.append("外部边界应采用 contract/integration test 与有限 mock")
    if not exploratory and stable_oracle and public_contract:
        recommendation = "recommended"
        strategy = "public_behavior_red_green_small_steps"
    elif stable_oracle or public_contract:
        recommendation = "possible"
        strategy = "contract_or_integration_first"
    else:
        recommendation = "not_preferred"
        strategy = "prototype_or_manual_acceptance"
    return {
        "change_shape": change_shape,
        "recommendation": recommendation,
        "strategy": strategy,
        "reasons": reasons,
        "rules": [
            "测试公共行为，不锁死内部实现",
            "每次只增加一个可解释的行为增量",
            "优先在外部边界使用 mock，不 mock 自家模块",
        ],
    }


def build_server() -> FastMCP:
    mcp = FastMCP("decision-workbench-mcp")

    @mcp.tool()
    def decision_workbench_brief() -> str:
        """Describe the distilled capability and its Agent OS boundaries."""
        return _json({
            "name": "decision-workbench-mcp",
            "version": "0.1.0",
            "purpose": "把复杂需求转化为决策、简报、实验、验证和续跑辅助产物",
            "source_skills": SOURCE_SKILLS,
            "does_not_own": [
                "L1/L2/L3 classification",
                "task queue",
                "approval",
                "runtime",
                "memory",
                "completion verification",
            ],
            "storage": str(ARTIFACT_ROOT),
            "invocation_policy": {
                "L1": "default_disabled",
                "L2": "selective",
                "L3": "required_inputs_only; existing gates remain authoritative",
            },
        })

    @mcp.tool()
    def recommend_capabilities(
        risk_level: str,
        ambiguity: bool = False,
        design_uncertainty: bool = False,
        stable_behavior_oracle: bool = False,
        architecture_change: bool = False,
        needs_handoff: bool = False,
        issue_or_pr_unverified: bool = False,
    ) -> str:
        """Recommend zero or more workbench objects without changing risk level."""
        risk = (risk_level or "").lower()
        selected = []
        reasons = []
        if risk == "l1":
            if any([ambiguity, design_uncertainty, needs_handoff]):
                if ambiguity:
                    selected.append("decision_tree")
                elif design_uncertainty:
                    selected.append("experiment_card")
                else:
                    selected.append("checkpoint_view")
                reasons.append("仅按用户显式需求或确有复杂歧义启用")
            else:
                return _json({
                    "risk_level": risk_level,
                    "selected": [],
                    "decision": "bypass",
                    "reason": "L1 默认不调用 Decision Workbench",
                })
        else:
            if ambiguity or risk == "l3":
                selected.append("decision_tree")
                reasons.append("需要先分离事实问题与 owner 决策")
            if issue_or_pr_unverified or risk == "l3":
                selected.append("agent_brief")
                reasons.append("需要 verify-before-ready 和范围边界")
            if design_uncertainty:
                selected.append("experiment_card")
                reasons.append("需要用最小实验回答未决设计问题")
            if stable_behavior_oracle:
                selected.append("tdd_fit")
                reasons.append("存在可观察行为和稳定验证 oracle")
            if architecture_change:
                selected.append("architecture_candidate")
                reasons.append("需要只读架构候选和 owner 选择")
            if needs_handoff:
                selected.append("checkpoint_view")
                reasons.append("需要跨会话或跨 Agent 恢复")
        return _json({
            "risk_level": risk_level,
            "selected": list(dict.fromkeys(selected)),
            "reasons": reasons,
            "preserved_invariants": [
                "不新增 L1/L2/L3",
                "不接管 queue/approval/memory/runtime",
                "现有 manual-gates 和 completion verifier 仍为正本",
            ],
        })

    @mcp.tool()
    def create_decision_tree(
        project: str,
        objective: str,
        questions_json: str = "[]",
        context_json: str = "{}",
    ) -> str:
        """Create a durable decision tree with a computed frontier."""
        artifact = _base_artifact("decision-tree", project, ["grilling", "grill-me", "grill-with-docs"])
        artifact.update({
            "objective": objective,
            "context": _loads(context_json, {}),
            "nodes": _normalize_questions(questions_json),
            "frontier": [],
            "shared_understanding": "pending",
            "failure_conditions": [
                "把可查证事实继续交给 owner 决策",
                "frontier 尚未清空却开始执行",
                "没有 owner 确认 shared understanding",
            ],
        })
        artifact["frontier"] = _compute_frontier(artifact["nodes"])
        path = _write_artifact(artifact)
        return _json({"status": "created", "artifact": artifact, "path": path})

    @mcp.tool()
    def update_decision_node(
        project: str,
        artifact_id: str,
        node_id: str,
        answer: str = "",
        status: str = "answered",
        evidence_json: str = "[]",
    ) -> str:
        """Update one decision node and recompute the frontier."""
        artifact = _read_artifact(project, artifact_id)
        if not artifact or artifact.get("kind") != "decision-tree":
            return _json({"status": "error", "error": "decision tree not found"})
        if status not in ALLOWED_STATUSES:
            return _json({"status": "error", "error": f"invalid status: {status}"})
        found = False
        for node in artifact.get("nodes", []):
            if node.get("id") == node_id:
                node["answer"] = answer or node.get("answer")
                node["status"] = status
                node["evidence"] = _loads(evidence_json, node.get("evidence", []))
                found = True
                break
        if not found:
            return _json({"status": "error", "error": f"node not found: {node_id}"})
        updated_node = next(node for node in artifact["nodes"] if node.get("id") == node_id)
        if status in TERMINAL_STATUSES and not str(updated_node.get("answer") or "").strip():
            return _json({
                "status": "error",
                "error": "terminal decision nodes require a non-empty answer",
            })
        artifact["frontier"] = _compute_frontier(artifact.get("nodes", []))
        if not artifact["frontier"]:
            artifact["shared_understanding"] = "pending_owner_confirmation"
        path = _write_artifact(artifact)
        return _json({"status": "updated", "artifact": artifact, "path": path})

    @mcp.tool()
    def create_agent_brief(
        project: str,
        title: str,
        current_behavior: str,
        target_behavior: str,
        acceptance_criteria_json: str = "[]",
        out_of_scope_json: str = "[]",
        evidence_json: str = "[]",
        risk_level: str = "",
        dependencies_json: str = "[]",
    ) -> str:
        """Create a durable execution brief without enqueueing or approving work."""
        artifact = _base_artifact("agent-brief", project, ["triage", "grill-with-docs"])
        artifact.update({
            "title": title,
            "current_behavior": current_behavior,
            "target_behavior": target_behavior,
            "acceptance_criteria": _loads(acceptance_criteria_json, []),
            "out_of_scope": _loads(out_of_scope_json, []),
            "evidence": _loads(evidence_json, []),
            "risk_level": risk_level,
            "dependencies": _loads(dependencies_json, []),
            "ready_status": "needs-verification",
            "failure_conditions": [
                "当前行为未经验证",
                "目标行为无法被验收标准观察",
                "范围边界为空或与 TaskCard 冲突",
            ],
        })
        path = _write_artifact(artifact)
        return _json({"status": "created", "artifact": artifact, "missing": _missing_brief_fields(artifact), "path": path})

    @mcp.tool()
    def verify_ready(project: str, artifact_id: str, verification_json: str = "{}") -> str:
        """Verify an Agent Brief before it is projected into the existing queue."""
        artifact = _read_artifact(project, artifact_id)
        if not artifact or artifact.get("kind") != "agent-brief":
            return _json({"status": "error", "error": "agent brief not found"})
        verification = _loads(verification_json, {})
        missing = _missing_brief_fields(artifact)
        checks = {
            "reproduced_or_current_behavior_verified": bool(verification.get("current_behavior_verified")),
            "acceptance_criteria_testable": bool(verification.get("acceptance_criteria_testable")),
            "scope_reviewed": bool(verification.get("scope_reviewed")),
            "evidence_attached": bool(artifact.get("evidence")),
        }
        evidence_valid, evidence_errors = _validate_evidence(artifact.get("evidence"))
        checks["evidence_references_valid"] = evidence_valid
        passed = not missing and all(checks.values())
        artifact["ready_status"] = "ready-for-owner-review" if passed else "needs-info"
        artifact["verification"] = {
            "checks": checks,
            "missing_fields": missing,
            "evidence_errors": evidence_errors,
            "evidence_verified": evidence_valid,
            "passed": passed,
            "verified_at": _now(),
        }
        path = _write_artifact(artifact)
        return _json({
            "status": "verified" if passed else "rejected",
            "ready_for_queue": False,
            "owner_review_required": True,
            "artifact": artifact,
            "path": path,
        })

    @mcp.tool()
    def create_experiment_card(
        project: str,
        question: str,
        hypothesis_json: str = "[]",
        experiment_type: str = "logic",
        success_signal: str = "",
        isolation_boundary: str = "isolated prototype; non-production",
        expiry_date: str = "",
        evidence_json: str = "[]",
    ) -> str:
        """Create an isolated prototype/experiment card."""
        artifact = _base_artifact("experiment-card", project, ["prototype"])
        artifact.update({
            "question": question,
            "hypotheses": _loads(hypothesis_json, []),
            "experiment_type": experiment_type,
            "success_signal": success_signal,
            "isolation_boundary": isolation_boundary,
            "expiry_date": expiry_date,
            "evidence": _loads(evidence_json, []),
            "promotion": {
                "production_promotion_allowed": False,
                "requires_new_task_card": True,
                "requires_existing_gates": True,
            },
            "failure_conditions": [
                "实验没有能区分假设的成功信号",
                "原型被当作生产实现",
                "实验过期后仍被引用为当前事实",
            ],
        })
        path = _write_artifact(artifact)
        return _json({"status": "created", "artifact": artifact, "path": path})

    @mcp.tool()
    def assess_tdd_fit(
        project: str,
        change_shape: str,
        stable_behavior_oracle: bool = False,
        public_contract: bool = False,
        exploratory: bool = False,
        external_boundary: bool = False,
    ) -> str:
        """Assess whether TDD is appropriate without forcing it."""
        result = _tdd_fit(change_shape, stable_behavior_oracle, public_contract, exploratory, external_boundary)
        artifact = _base_artifact("tdd-fit", project, ["tdd"])
        artifact.update({
            **result,
            "failure_conditions": [
                "把 TDD 适配建议当成完成证明",
                "为了测试方便扭曲生产接口",
                "测试只覆盖内部实现而非公共行为",
            ],
        })
        path = _write_artifact(artifact)
        return _json({"status": "created", "artifact": artifact, "path": path})

    @mcp.tool()
    def create_architecture_candidate(
        project: str,
        title: str,
        problem_signal: str,
        proposed_boundary: str,
        callers_json: str = "[]",
        evidence_json: str = "[]",
        migration_cost: str = "",
        rollback_plan: str = "",
        deletion_test: str = "",
    ) -> str:
        """Record a read-only architecture candidate for owner selection."""
        artifact = _base_artifact("architecture-candidate", project, ["improve-codebase-architecture"])
        artifact.update({
            "title": title,
            "problem_signal": problem_signal,
            "proposed_boundary": proposed_boundary,
            "callers": _loads(callers_json, []),
            "evidence": _loads(evidence_json, []),
            "migration_cost": migration_cost,
            "rollback_plan": rollback_plan,
            "deletion_test": deletion_test,
            "selection": "pending_owner_choice",
            "failure_conditions": [
                "只凭近期热点推断架构价值",
                "没有调用方/运行/失败证据",
                "候选报告直接触发代码修改",
            ],
        })
        path = _write_artifact(artifact)
        return _json({"status": "created", "artifact": artifact, "path": path})

    @mcp.tool()
    def create_checkpoint_view(
        project: str,
        task_id: str,
        current_phase: str,
        objective: str,
        accepted_decisions_json: str = "[]",
        pending_decisions_json: str = "[]",
        changed_files_json: str = "[]",
        validations_json: str = "[]",
        blockers_json: str = "[]",
        next_action: str = "",
        evidence_json: str = "[]",
    ) -> str:
        """Create a readable handoff/checkpoint view from external Agent OS state."""
        artifact = _base_artifact("checkpoint-view", project, ["handoff", "teach"])
        artifact.update({
            "task_id": task_id,
            "current_phase": current_phase,
            "objective": objective,
            "accepted_decisions": _loads(accepted_decisions_json, []),
            "pending_decisions": _loads(pending_decisions_json, []),
            "changed_files": _loads(changed_files_json, []),
            "validations": _loads(validations_json, []),
            "blockers": _loads(blockers_json, []),
            "next_action": next_action,
            "evidence": _loads(evidence_json, []),
            "source_of_truth": [
                "existing TaskCard",
                "existing RunState",
                "existing EvidenceRecord",
            ],
            "failure_conditions": [
                "把 checkpoint 当成 RunState 正本",
                "复制内容替代引用原始证据",
                "省略审批或阻塞状态",
            ],
        })
        path = _write_artifact(artifact)
        return _json({"status": "created", "artifact": artifact, "path": path})

    @mcp.tool()
    def get_artifact(project: str, artifact_id: str) -> str:
        """Read one workbench artifact."""
        artifact = _read_artifact(project, artifact_id)
        if artifact is None:
            return _json({"status": "error", "error": "artifact not found"})
        return _json({"status": "ok", "artifact": artifact, "path": str(_artifact_path(project, artifact_id))})

    @mcp.tool()
    def list_artifacts(project: str, kind: str = "") -> str:
        """List workbench artifacts for a project."""
        directory = _artifact_dir(project)
        rows = []
        if directory.exists():
            for path in sorted(directory.glob("*.json")):
                try:
                    item = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not kind or item.get("kind") == kind:
                    rows.append({
                        "id": item.get("id"),
                        "kind": item.get("kind"),
                        "status": item.get("status"),
                        "updated_at": item.get("updated_at"),
                        "path": str(path),
                    })
        return _json({"project": project, "kind": kind, "count": len(rows), "artifacts": rows})

    return mcp


def main() -> None:
    build_server().run()
