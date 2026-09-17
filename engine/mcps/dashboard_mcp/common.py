# -*- coding: utf-8 -*-
"""Dashboard MCP server.

Generates a static local HTML dashboard for the manual-agent OS. It summarizes
manual-gates projects, MCP inventory, trace/runtime/memory evidence, and backup
archives without requiring a web server.
"""
import html
import importlib.util
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
MCP_DIR = DATA_ROOT / "03_分工MCP"
PROJECT_DIR = DATA_ROOT / "04_技能包" / "manual-gates" / "scripts" / "manual_mcp" / "projects"
RESEARCH_DIR = DATA_ROOT / "09_投研"
BACKUP_DIR = DATA_ROOT / "10_备份"
DASHBOARD_DIR = RESEARCH_DIR / "dashboard"
REGISTRY_DIR = RESEARCH_DIR / "agent_os_registry"
STABILITY_DIR = RESEARCH_DIR / "agent_os_stability"
SHADOW_DIR = RESEARCH_DIR / "agent_os_shadow"
REVIEW_QUEUE_DIR = SHADOW_DIR
CANARY_DIR = RESEARCH_DIR / "agent_os_active_canary"
TRAJECTORY_DIR = RESEARCH_DIR / "agent_os_trajectories"
MODEL_ADAPTER_DIR = RESEARCH_DIR / "agent_os_model_adapters"
OWNER_DECISION_DIR = RESEARCH_DIR / "agent_os_owner_decisions"
KNOWLEDGE_TRUST_DIR = RESEARCH_DIR / "agent_os_knowledge_trust"
DASHBOARD_PERF_DIR = RESEARCH_DIR / "agent_os_dashboard_perf"
INVESTMENT_EVAL_DIR = RESEARCH_DIR / "agent_fund_studio" / "eval"


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc), "path": str(path)}


def _fmt_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _mcp_inventory() -> list[dict]:
    if not MCP_DIR.exists():
        return []
    items = []
    for path in sorted(MCP_DIR.iterdir()):
        if not path.is_dir() or not path.name.endswith("_mcp"):
            continue
        files = list(path.glob("*.py"))
        items.append({
            "name": path.name,
            "path": str(path),
            "file_count": len(files),
            "has_readme": (path / "README.md").exists(),
            "runner": [p.name for p in files if p.name.startswith("run_")],
        })
    return items


def _manual_projects() -> list[dict]:
    if not PROJECT_DIR.exists():
        return []
    rows = []
    for path in sorted(PROJECT_DIR.iterdir()):
        state_path = path / "state.json"
        if not state_path.exists():
            continue
        state = _read_json(state_path)
        nodes = state.get("nodes", {}) if isinstance(state, dict) else {}
        passed = sum(1 for node in nodes.values() if node.get("status") == "passed")
        total = len(nodes)
        rows.append({
            "name": state.get("project", path.name),
            "dir": path.name,
            "track": state.get("track", ""),
            "autonomy": state.get("autonomy", ""),
            "progress": f"{passed}/{total}" if total else "0/0",
            "passed": passed,
            "total": total,
            "iteration": state.get("iteration", 0),
            "updated": max((node.get("ts", "") for node in nodes.values()), default=state.get("created", "")),
            "path": str(state_path),
        })
    rows.sort(key=lambda x: x.get("updated", ""), reverse=True)
    return rows


def _backups(limit: int = 20) -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    files = sorted([p for p in BACKUP_DIR.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    return [{
        "name": p.name,
        "path": str(p),
        "size": p.stat().st_size,
        "size_human": _fmt_size(p.stat().st_size),
        "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    } for p in files[:limit]]


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())


def _evidence_summary() -> dict:
    trace_root = RESEARCH_DIR / "trace_observability"
    runtime_root = RESEARCH_DIR / "agent_runtime_kernel"
    memory_root = RESEARCH_DIR / "experience_memory"
    orchestration_root = RESEARCH_DIR / "agent_orchestration" / "parallel_runs"
    workflow_root = RESEARCH_DIR / "workflow_runtime"
    agent_os_runtime_root = RESEARCH_DIR / "agent_os_runtime"

    trace_projects = []
    if trace_root.exists():
        for p in sorted(trace_root.iterdir()):
            if p.is_dir():
                trace_projects.append({"project": p.name, "events": _count_jsonl(p / "trace.jsonl"), "path": str(p / "trace.jsonl")})

    runtime_projects = []
    if runtime_root.exists():
        for p in sorted(runtime_root.iterdir()):
            if p.is_dir() and (p / "runtime.json").exists():
                rt = _read_json(p / "runtime.json")
                runtime_projects.append({"project": p.name, "task": rt.get("task"), "status": rt.get("status", ""), "path": str(p / "runtime.json")})

    parallel_runs = []
    if orchestration_root.exists():
        for file in orchestration_root.rglob("*.json"):
            data = _read_json(file)
            summary = data.get("summary", {})
            parallel_runs.append({"project": data.get("project", file.parent.name), "run_id": data.get("run_id", file.stem), "progress": summary.get("progress", ""), "status": data.get("status", ""), "path": str(file)})

    workflow_projects = []
    if workflow_root.exists():
        for p in sorted(workflow_root.iterdir()):
            if p.is_dir() and (p / "workflow.json").exists():
                wf = _read_json(p / "workflow.json")
                workflow_projects.append({"project": p.name, "track": wf.get("track", ""), "path": str(p / "workflow.json")})

    return {
        "trace_projects": trace_projects,
        "runtime_projects": runtime_projects,
        "memory_records": _count_jsonl(memory_root / "memory.jsonl"),
        "memory_index_exists": (memory_root / "memory_index.sqlite").exists(),
        "memory_vector_index_exists": (memory_root / "memory_vector.sqlite").exists(),
        "parallel_runs": parallel_runs,
        "workflow_projects": workflow_projects,
        "agent_os_runtime": _agent_os_runtime_summary(agent_os_runtime_root),
    }


def _agent_os_runtime_summary(root: Path) -> dict:
    run_dir = root / "runs"
    card_dir = root / "task_cards"
    snapshot_path = root / "control_snapshot.json"
    runs = []
    blocked_runs = []
    retry_runs = []
    completion_failures = []
    memory_writes = []
    if run_dir.exists():
        for path in sorted(run_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            data = _read_json(path)
            row = {
                "run_id": data.get("run_id", path.stem),
                "project": data.get("project", ""),
                "task": data.get("task", ""),
                "phase": data.get("phase", ""),
                "status": data.get("status", ""),
                "decision": data.get("decision", ""),
                "manual_node": data.get("manual_node", ""),
                "updated": data.get("updated", ""),
                "path": str(path),
                "detail_path": str(DASHBOARD_DIR / "run_details" / f"{path.stem}.html"),
            }
            if len(runs) < 25:
                runs.append(row)
            if row["status"] in {"failed", "blocked"} or row["decision"] == "block":
                blocked_runs.append({
                    **row,
                    "failed_checks": [c.get("name") for c in data.get("checks", []) if not c.get("passed")],
                })
            if row["status"] == "retry" or row["decision"] == "retry":
                retry_runs.append(row)
            verifier = data.get("completion_verifier") or {}
            if verifier and not verifier.get("passed", False):
                completion_failures.append({
                    **row,
                    "task_class": verifier.get("task_class"),
                    "missing": verifier.get("missing", []),
                    "forbidden_hits": verifier.get("forbidden_hits", []),
                    "decision_detail": verifier.get("decision", ""),
                })
            for write in data.get("memory_writes", []) or []:
                memory_writes.append({
                    "run_id": row["run_id"],
                    "project": row["project"],
                    "task": row["task"],
                    "status": write.get("status", ""),
                    "memory_id": write.get("id", write.get("memory_id", "")),
                    "path": str(path),
                })
            if len(blocked_runs) > 25:
                blocked_runs = blocked_runs[:25]
            if len(retry_runs) > 25:
                retry_runs = retry_runs[:25]
            if len(completion_failures) > 25:
                completion_failures = completion_failures[:25]
            if len(memory_writes) > 25:
                memory_writes = memory_writes[:25]
    return {
        "root": str(root),
        "run_count": len(list(run_dir.glob("*.json"))) if run_dir.exists() else 0,
        "task_card_count": len(list(card_dir.glob("*.json"))) if card_dir.exists() else 0,
        "snapshot_exists": snapshot_path.exists(),
        "snapshot_path": str(snapshot_path),
        "runs": runs,
        "blocked_runs": blocked_runs,
        "retry_runs": retry_runs,
        "completion_failures": completion_failures,
        "memory_writes": memory_writes,
    }


def _registry_summary() -> dict:
    mcp = _read_json(REGISTRY_DIR / "mcp_registry.json")
    skill = _read_json(REGISTRY_DIR / "skill_registry.json")
    def counts(payload: dict) -> dict:
        out = {"active": 0, "shadow": 0, "deprecated": 0, "retired": 0}
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            status = item.get("status", "shadow")
            out[status] = out.get(status, 0) + 1
        return out
    return {
        "mcp": mcp if isinstance(mcp, dict) else {},
        "skill": skill if isinstance(skill, dict) else {},
        "mcp_counts": counts(mcp),
        "skill_counts": counts(skill),
        "policy_path": str(REGISTRY_DIR / "lifecycle_policy.md"),
    }


def _stability_summary() -> dict:
    metrics = _read_json(STABILITY_DIR / "capability_metrics.json")
    advice = _read_json(STABILITY_DIR / "promotion_advice.json")
    soak = _read_json(STABILITY_DIR / "daily_soak_report.json")
    l4_soak_sanitizer = _read_json(RESEARCH_DIR / "daily_retro" / "l4_soak_json_sanitizer.json")
    l4_soak_matrix = _read_json(RESEARCH_DIR / "daily_retro" / "7_day_soak_progress_matrix.json")
    capabilities = []
    if isinstance(metrics, dict):
        for name, item in (metrics.get("capabilities") or {}).items():
            capabilities.append({
                "name": name,
                "calls": item.get("calls", 0),
                "completed": item.get("completed", 0),
                "failed": item.get("failed", 0),
                "blocked": item.get("blocked", 0),
                "retry": item.get("retry", 0),
                "expected_fail_closed": item.get("expected_fail_closed", 0),
                "success_rate": item.get("success_rate", 0),
                "operational_success_rate": item.get("operational_success_rate", item.get("success_rate", 0)),
                "last_failure_reason": item.get("last_failure_reason", ""),
            })
    capabilities.sort(key=lambda item: (item["failed"] + item["blocked"], item["calls"]), reverse=True)
    actionable = []
    if isinstance(advice, dict):
        actionable = [item for item in advice.get("advice", []) if item.get("recommendation") != "hold"][:30]
    return {
        "metrics": metrics if isinstance(metrics, dict) else {},
        "advice": advice if isinstance(advice, dict) else {},
        "soak": soak if isinstance(soak, dict) else {},
        "l4_soak_sanitizer": l4_soak_sanitizer if isinstance(l4_soak_sanitizer, dict) else {},
        "l4_soak_matrix": l4_soak_matrix if isinstance(l4_soak_matrix, dict) else {},
        "capabilities": capabilities[:30],
        "actionable": actionable,
        "paths": {
            "metrics": str(STABILITY_DIR / "capability_metrics.json"),
            "advice": str(STABILITY_DIR / "promotion_advice.json"),
            "soak": str(STABILITY_DIR / "daily_soak_report.json"),
            "soak_md": str(STABILITY_DIR / f"{datetime.now().strftime('%Y-%m-%d')}_daily_soak_report.md"),
            "l4_soak_sanitizer": str(RESEARCH_DIR / "daily_retro" / "l4_soak_json_sanitizer.json"),
            "l4_soak_sanitizer_audit": str(RESEARCH_DIR / "daily_retro" / "l4_soak_json_sanitizer_audit.jsonl"),
            "l4_soak_matrix": str(RESEARCH_DIR / "daily_retro" / "7_day_soak_progress_matrix.json"),
            "l4_soak_matrix_md": str(RESEARCH_DIR / "daily_retro" / "7_day_soak_progress_matrix.md"),
            "l4_soak_matrix_audit": str(RESEARCH_DIR / "daily_retro" / "7_day_soak_progress_matrix_audit.jsonl"),
        },
    }


def _shadow_summary() -> dict:
    summary = _read_json(SHADOW_DIR / "shadow_summary.json")
    scoring = _read_json(SHADOW_DIR / "promotion_scoring.json")
    eval_summary = _read_json(SHADOW_DIR / "shadow_eval_summary.json")
    runs = summary.get("runs", []) if isinstance(summary, dict) else []
    candidates = [r for r in runs if r.get("promotion_signal") == "candidate_for_more_shadow_runs"]
    warnings = [r for r in runs if r.get("shadow_result") == "warn"]
    scores = scoring.get("scores", []) if isinstance(scoring, dict) else []
    readiness = [s for s in scores if s.get("promotion_candidate")]
    return {
        "summary": summary if isinstance(summary, dict) else {},
        "scoring": scoring if isinstance(scoring, dict) else {},
        "eval_summary": eval_summary if isinstance(eval_summary, dict) else {},
        "runs": runs[:30],
        "candidates": candidates[:20],
        "warnings": warnings[:20],
        "scores": scores[:30],
        "readiness": readiness[:20],
        "paths": {
            "summary": str(SHADOW_DIR / "shadow_summary.json"),
            "runs": str(SHADOW_DIR / "runs"),
            "scoring": str(SHADOW_DIR / "promotion_scoring.json"),
            "eval_summary": str(SHADOW_DIR / "shadow_eval_summary.json"),
        },
    }


def _promotion_review_summary() -> dict:
    queue = _read_json(SHADOW_DIR / "promotion_review_queue.json")
    decisions = _read_json(SHADOW_DIR / "promotion_review_decisions.json")
    items = queue.get("items", []) if isinstance(queue, dict) else []
    return {
        "queue": queue if isinstance(queue, dict) else {},
        "decisions": decisions if isinstance(decisions, dict) else {},
        "items": items[:30],
        "pending": [item for item in items if item.get("status") == "pending_owner_review"][:20],
        "approved_pending_apply": [item for item in items if item.get("status") == "approved_pending_apply"][:20],
        "rejected": [item for item in items if item.get("status") == "rejected"][:20],
        "paths": {
            "queue": str(SHADOW_DIR / "promotion_review_queue.json"),
            "decisions": str(SHADOW_DIR / "promotion_review_decisions.json"),
            "audit": str(SHADOW_DIR / "promotion_review_audit.jsonl"),
        },
    }


def _investment_eval_summary() -> dict:
    dashboard = _read_json(INVESTMENT_EVAL_DIR / "eval_dashboard.json")
    review_packet = _read_json(INVESTMENT_EVAL_DIR / "promotion_review_packet.json")
    cases = dashboard.get("cases", []) if isinstance(dashboard, dict) else []
    queue = dashboard.get("promotion_queue", []) if isinstance(dashboard, dict) else []
    return {
        "dashboard": dashboard if isinstance(dashboard, dict) else {},
        "review_packet": review_packet if isinstance(review_packet, dict) else {},
        "summary": dashboard.get("summary", {}) if isinstance(dashboard, dict) else {},
        "target_skills": dashboard.get("target_skills", {}) if isinstance(dashboard, dict) else {},
        "cases": cases[:30],
        "failed_cases": [item for item in cases if not item.get("passed")][:20],
        "degraded_cases": [item for item in cases if str(item.get("verdict", "")).startswith("degraded")][:20],
        "promotion_queue": queue[:20],
        "owner_review_required": review_packet.get("owner_review_required", False) if isinstance(review_packet, dict) else False,
        "paths": {
            "dashboard_json": str(INVESTMENT_EVAL_DIR / "eval_dashboard.json"),
            "dashboard_md": str(INVESTMENT_EVAL_DIR / "eval_dashboard.md"),
            "review_packet_json": str(INVESTMENT_EVAL_DIR / "promotion_review_packet.json"),
            "review_packet_md": str(INVESTMENT_EVAL_DIR / "promotion_review_packet.md"),
        },
    }


def _active_canary_summary() -> dict:
    status = _read_json(CANARY_DIR / "canary_status.json")
    rollback = _read_json(CANARY_DIR / "rollback_candidates.json")
    rollback_queue = _read_json(CANARY_DIR / "rollback_review_queue.json")
    items = status.get("items", []) if isinstance(status, dict) else []
    rollback_items = rollback.get("items", []) if isinstance(rollback, dict) else []
    rollback_review_items = rollback_queue.get("items", []) if isinstance(rollback_queue, dict) else []
    return {
        "status": status if isinstance(status, dict) else {},
        "rollback": rollback if isinstance(rollback, dict) else {},
        "rollback_queue": rollback_queue if isinstance(rollback_queue, dict) else {},
        "items": items[:30],
        "newly_active": [item for item in items if item.get("canary_active")][:20],
        "rollback_candidates": rollback_items[:20],
        "rollback_review_items": rollback_review_items[:20],
        "paths": {
            "status": str(CANARY_DIR / "canary_status.json"),
            "runs": str(CANARY_DIR / "canary_runs.jsonl"),
            "rollback": str(CANARY_DIR / "rollback_candidates.json"),
            "rollback_queue": str(CANARY_DIR / "rollback_review_queue.json"),
        },
    }


def _trajectory_summary() -> dict:
    summary = _read_json(TRAJECTORY_DIR / "trajectory_summary.json")
    replay_index = _read_json(TRAJECTORY_DIR / "replay_index.json")
    replay_runner = _read_json(TRAJECTORY_DIR / "replay_runner_summary.json")
    replay_diff = _read_json(TRAJECTORY_DIR / "replay_diff_summary.json")
    distillation_queue = _read_json(TRAJECTORY_DIR / "experience_distillation_queue.json")
    verifier_drilldown = _read_json(TRAJECTORY_DIR / "verifier_failure_drilldown.json")
    class_c_drilldown = _read_json(TRAJECTORY_DIR / "class_c_evidence_drilldown.json")
    unknown_resolver = _read_json(TRAJECTORY_DIR / "unknown_outcome_resolver.json")
    retry_drilldown = _read_json(TRAJECTORY_DIR / "retry_pattern_drilldown.json")
    retry_recovery = _read_json(TRAJECTORY_DIR / "retry_recovery_verifier.json")
    return {
        "summary": summary if isinstance(summary, dict) else {},
        "replay_index": replay_index if isinstance(replay_index, dict) else {},
        "replay_runner": replay_runner if isinstance(replay_runner, dict) else {},
        "replay_diff": replay_diff if isinstance(replay_diff, dict) else {},
        "distillation_queue": distillation_queue if isinstance(distillation_queue, dict) else {},
        "verifier_drilldown": verifier_drilldown if isinstance(verifier_drilldown, dict) else {},
        "class_c_drilldown": class_c_drilldown if isinstance(class_c_drilldown, dict) else {},
        "unknown_resolver": unknown_resolver if isinstance(unknown_resolver, dict) else {},
        "retry_drilldown": retry_drilldown if isinstance(retry_drilldown, dict) else {},
        "retry_recovery": retry_recovery if isinstance(retry_recovery, dict) else {},
        "paths": {
            "summary": str(TRAJECTORY_DIR / "trajectory_summary.json"),
            "jsonl": str(TRAJECTORY_DIR / "trajectories.jsonl"),
            "replay_index": str(TRAJECTORY_DIR / "replay_index.json"),
            "replay_runner": str(TRAJECTORY_DIR / "replay_runner_summary.json"),
            "replay_diff": str(TRAJECTORY_DIR / "replay_diff_summary.json"),
            "verifier_drilldown": str(TRAJECTORY_DIR / "verifier_failure_drilldown.json"),
            "verifier_drilldown_audit": str(TRAJECTORY_DIR / "verifier_failure_drilldown_audit.jsonl"),
            "class_c_contract": str(TRAJECTORY_DIR / "class_c_evidence_contract.json"),
            "class_c_drilldown": str(TRAJECTORY_DIR / "class_c_evidence_drilldown.json"),
            "class_c_drilldown_audit": str(TRAJECTORY_DIR / "class_c_evidence_drilldown_audit.jsonl"),
            "unknown_resolver": str(TRAJECTORY_DIR / "unknown_outcome_resolver.json"),
            "unknown_resolver_audit": str(TRAJECTORY_DIR / "unknown_outcome_resolver_audit.jsonl"),
            "retry_drilldown": str(TRAJECTORY_DIR / "retry_pattern_drilldown.json"),
            "retry_drilldown_audit": str(TRAJECTORY_DIR / "retry_pattern_drilldown_audit.jsonl"),
            "retry_recovery_contract": str(TRAJECTORY_DIR / "retry_recovery_contract.json"),
            "retry_recovery": str(TRAJECTORY_DIR / "retry_recovery_verifier.json"),
            "retry_recovery_audit": str(TRAJECTORY_DIR / "retry_recovery_verifier_audit.jsonl"),
            "distillation_queue": str(TRAJECTORY_DIR / "experience_distillation_queue.json"),
            "distillation_decisions": str(TRAJECTORY_DIR / "experience_distillation_decisions.json"),
            "distillation_audit": str(TRAJECTORY_DIR / "experience_distillation_audit.jsonl"),
        },
    }


def _distillation_summary() -> dict:
    queue = _read_json(TRAJECTORY_DIR / "experience_distillation_queue.json")
    decisions = _read_json(TRAJECTORY_DIR / "experience_distillation_decisions.json")
    items = queue.get("items", []) if isinstance(queue, dict) else []
    return {
        "queue": queue if isinstance(queue, dict) else {},
        "decisions": decisions if isinstance(decisions, dict) else {},
        "items": items[:30],
        "pending": [item for item in items if item.get("status") == "pending_owner_review"][:20],
        "approved_pending_writeback": [item for item in items if item.get("status") == "approved_pending_writeback"][:20],
        "rejected": [item for item in items if item.get("status") == "rejected"][:20],
        "deferred": [item for item in items if item.get("status") == "deferred"][:20],
        "paths": {
            "queue": str(TRAJECTORY_DIR / "experience_distillation_queue.json"),
            "decisions": str(TRAJECTORY_DIR / "experience_distillation_decisions.json"),
            "audit": str(TRAJECTORY_DIR / "experience_distillation_audit.jsonl"),
            "writeback": str(RESEARCH_DIR / "experience_memory" / "distilled_candidates.jsonl"),
        },
    }


def _model_adapter_summary() -> dict:
    registry = _read_json(MODEL_ADAPTER_DIR / "model_adapter_registry.json")
    harness_plan = _read_json(MODEL_ADAPTER_DIR / "model_adapter_harness_plan.json")
    daily_soak = _read_json(MODEL_ADAPTER_DIR / "model_adapter_daily_soak.json")
    guardrail_negative_tests = _read_json(MODEL_ADAPTER_DIR / "model_adapter_guardrail_negative_tests.json")
    evidence_completeness = _read_json(MODEL_ADAPTER_DIR / "model_adapter_evidence_completeness.json")
    sample_plan = _read_json(MODEL_ADAPTER_DIR / "model_adapter_sample_plan.json")
    path_consistency = _read_json(MODEL_ADAPTER_DIR / "model_adapter_path_consistency.json")
    path_cleanup_review = _read_json(MODEL_ADAPTER_DIR / "model_adapter_path_cleanup_review_queue.json")
    canary_queue = _read_json(MODEL_ADAPTER_DIR / "model_adapter_canary_queue.json")
    routing_policy = _read_json(MODEL_ADAPTER_DIR / "model_routing_policy.json")
    decision_queue = _read_json(MODEL_ADAPTER_DIR / "model_adapter_decision_queue.json")
    decisions = _read_json(MODEL_ADAPTER_DIR / "model_adapter_decisions.json")
    contract_tests = _read_json(MODEL_ADAPTER_DIR / "model_adapter_contract_tests.json")
    drift_report = _read_json(MODEL_ADAPTER_DIR / "model_adapter_drift_report.json")
    incident_queue = _read_json(MODEL_ADAPTER_DIR / "model_adapter_incident_queue.json")
    results = _read_json(MODEL_ADAPTER_DIR / "model_adapter_eval_results.json")
    adapters = results.get("adapters", []) if isinstance(results, dict) else []
    recommendations = results.get("recommended_by_capability", []) if isinstance(results, dict) else []
    run_samples = results.get("run_samples", {}) if isinstance(results, dict) else {}
    return {
        "registry": registry if isinstance(registry, dict) else {},
        "harness_plan": harness_plan if isinstance(harness_plan, dict) else {},
        "daily_soak": daily_soak if isinstance(daily_soak, dict) else {},
        "guardrail_negative_tests": guardrail_negative_tests if isinstance(guardrail_negative_tests, dict) else {},
        "evidence_completeness": evidence_completeness if isinstance(evidence_completeness, dict) else {},
        "sample_plan": sample_plan if isinstance(sample_plan, dict) else {},
        "path_consistency": path_consistency if isinstance(path_consistency, dict) else {},
        "path_cleanup_review": path_cleanup_review if isinstance(path_cleanup_review, dict) else {},
        "canary_queue": canary_queue if isinstance(canary_queue, dict) else {},
        "routing_policy": routing_policy if isinstance(routing_policy, dict) else {},
        "decision_queue": decision_queue if isinstance(decision_queue, dict) else {},
        "decisions": decisions if isinstance(decisions, dict) else {},
        "contract_tests": contract_tests if isinstance(contract_tests, dict) else {},
        "drift_report": drift_report if isinstance(drift_report, dict) else {},
        "incident_queue": incident_queue if isinstance(incident_queue, dict) else {},
        "results": results if isinstance(results, dict) else {},
        "providers": (registry.get("providers", []) if isinstance(registry, dict) else [])[:20],
        "harness_items": (harness_plan.get("items", []) if isinstance(harness_plan, dict) else [])[:20],
        "canary_items": (canary_queue.get("items", []) if isinstance(canary_queue, dict) else [])[:20],
        "routing_rules": (routing_policy.get("rules", []) if isinstance(routing_policy, dict) else [])[:30],
        "decision_items": (decision_queue.get("items", []) if isinstance(decision_queue, dict) else [])[:20],
        "decision_records": (decisions.get("decisions", []) if isinstance(decisions, dict) else [])[:20],
        "contract_checks": (contract_tests.get("checks", []) if isinstance(contract_tests, dict) else [])[:20],
        "drift_findings": (drift_report.get("findings", []) if isinstance(drift_report, dict) else [])[:20],
        "incident_items": (incident_queue.get("items", []) if isinstance(incident_queue, dict) else [])[:20],
        "adapters": adapters[:20],
        "recommendations": recommendations[:30],
        "run_samples": run_samples,
        "paths": {
            "registry": str(MODEL_ADAPTER_DIR / "model_adapter_registry.json"),
            "harness_plan": str(MODEL_ADAPTER_DIR / "model_adapter_harness_plan.json"),
            "harness_audit": str(MODEL_ADAPTER_DIR / "model_adapter_harness_audit.jsonl"),
            "daily_soak": str(MODEL_ADAPTER_DIR / "model_adapter_daily_soak.json"),
            "guardrail_negative_tests": str(MODEL_ADAPTER_DIR / "model_adapter_guardrail_negative_tests.json"),
            "guardrail_negative_tests_audit": str(MODEL_ADAPTER_DIR / "model_adapter_guardrail_negative_tests_audit.jsonl"),
            "evidence_completeness": str(MODEL_ADAPTER_DIR / "model_adapter_evidence_completeness.json"),
            "evidence_completeness_audit": str(MODEL_ADAPTER_DIR / "model_adapter_evidence_completeness_audit.jsonl"),
            "sample_plan": str(MODEL_ADAPTER_DIR / "model_adapter_sample_plan.json"),
            "sample_plan_audit": str(MODEL_ADAPTER_DIR / "model_adapter_sample_plan_audit.jsonl"),
            "path_consistency": str(MODEL_ADAPTER_DIR / "model_adapter_path_consistency.json"),
            "path_consistency_audit": str(MODEL_ADAPTER_DIR / "model_adapter_path_consistency_audit.jsonl"),
            "path_cleanup_review": str(MODEL_ADAPTER_DIR / "model_adapter_path_cleanup_review_queue.json"),
            "path_cleanup_review_decisions": str(MODEL_ADAPTER_DIR / "model_adapter_path_cleanup_review_decisions.json"),
            "path_cleanup_review_audit": str(MODEL_ADAPTER_DIR / "model_adapter_path_cleanup_review_audit.jsonl"),
            "canary_queue": str(MODEL_ADAPTER_DIR / "model_adapter_canary_queue.json"),
            "canary_audit": str(MODEL_ADAPTER_DIR / "model_adapter_canary_audit.jsonl"),
            "routing_policy": str(MODEL_ADAPTER_DIR / "model_routing_policy.json"),
            "routing_audit": str(MODEL_ADAPTER_DIR / "model_routing_policy_audit.jsonl"),
            "decision_queue": str(MODEL_ADAPTER_DIR / "model_adapter_decision_queue.json"),
            "decision_audit": str(MODEL_ADAPTER_DIR / "model_adapter_decision_audit.jsonl"),
            "decisions": str(MODEL_ADAPTER_DIR / "model_adapter_decisions.json"),
            "contract_tests": str(MODEL_ADAPTER_DIR / "model_adapter_contract_tests.json"),
            "contract_audit": str(MODEL_ADAPTER_DIR / "model_adapter_contract_tests_audit.jsonl"),
            "drift_report": str(MODEL_ADAPTER_DIR / "model_adapter_drift_report.json"),
            "drift_baseline": str(MODEL_ADAPTER_DIR / "model_adapter_drift_baseline.json"),
            "drift_audit": str(MODEL_ADAPTER_DIR / "model_adapter_drift_audit.jsonl"),
            "incident_queue": str(MODEL_ADAPTER_DIR / "model_adapter_incident_queue.json"),
            "incident_audit": str(MODEL_ADAPTER_DIR / "model_adapter_incident_audit.jsonl"),
            "results": str(MODEL_ADAPTER_DIR / "model_adapter_eval_results.json"),
            "audit": str(MODEL_ADAPTER_DIR / "model_adapter_eval_audit.jsonl"),
        },
    }


def _owner_decision_summary() -> dict:
    report = _read_json(OWNER_DECISION_DIR / "owner_decision_summary.json")
    priorities = _read_json(OWNER_DECISION_DIR / "owner_decision_priorities.json")
    packet = _read_json(OWNER_DECISION_DIR / "owner_review_packet.json")
    consistency = _read_json(OWNER_DECISION_DIR / "owner_decision_consistency.json")
    staleness = _read_json(OWNER_DECISION_DIR / "owner_decision_staleness.json")
    trend = _read_json(OWNER_DECISION_DIR / "owner_decision_trend_snapshot.json")
    dependency = _read_json(OWNER_DECISION_DIR / "owner_decision_dependency_map.json")
    risk_heatmap = _read_json(OWNER_DECISION_DIR / "owner_decision_risk_heatmap.json")
    review_checklist = _read_json(OWNER_DECISION_DIR / "owner_decision_review_checklist.json")
    guardrail_validator = _read_json(OWNER_DECISION_DIR / "owner_decision_guardrail_validator.json")
    guardrail_trend = _read_json(OWNER_DECISION_DIR / "owner_decision_guardrail_trend_snapshot.json")
    guardrail_coverage = _read_json(OWNER_DECISION_DIR / "owner_decision_guardrail_coverage_matrix.json")
    guardrail_coverage_trend = _read_json(OWNER_DECISION_DIR / "owner_decision_guardrail_coverage_trend_snapshot.json")
    governance_health = _read_json(OWNER_DECISION_DIR / "owner_decision_governance_health_summary.json")
    governance_health_trend = _read_json(OWNER_DECISION_DIR / "owner_decision_governance_health_trend_snapshot.json")
    governance_freshness = _read_json(OWNER_DECISION_DIR / "owner_decision_governance_freshness_summary.json")
    governance_ops_digest = _read_json(OWNER_DECISION_DIR / "owner_decision_governance_ops_digest.json")
    owner_review_drilldown = _read_json(OWNER_DECISION_DIR / "owner_review_drilldown.json")
    owner_review_packet_coverage = _read_json(OWNER_DECISION_DIR / "owner_review_packet_coverage.json")
    owner_review_integrity_manifest = _read_json(OWNER_DECISION_DIR / "owner_review_integrity_manifest.json")
    owner_review_integrity_trend = _read_json(OWNER_DECISION_DIR / "owner_review_integrity_trend_snapshot.json")
    owner_review_readiness_checklist = _read_json(OWNER_DECISION_DIR / "owner_review_readiness_checklist.json")
    owner_review_readiness_trend = _read_json(OWNER_DECISION_DIR / "owner_review_readiness_trend_snapshot.json")
    owner_review_queue_aging = _read_json(OWNER_DECISION_DIR / "owner_review_queue_aging.json")
    owner_review_queue_aging_trend = _read_json(OWNER_DECISION_DIR / "owner_review_queue_aging_trend_snapshot.json")
    owner_review_queue_sla_forecast = _read_json(OWNER_DECISION_DIR / "owner_review_queue_sla_forecast.json")
    owner_review_queue_sla_forecast_trend = _read_json(OWNER_DECISION_DIR / "owner_review_queue_sla_forecast_trend_snapshot.json")
    owner_review_next_action_preview = _read_json(OWNER_DECISION_DIR / "owner_review_next_action_preview.json")
    owner_review_next_action_trend = _read_json(OWNER_DECISION_DIR / "owner_review_next_action_trend_snapshot.json")
    owner_review_action_brief = _read_json(OWNER_DECISION_DIR / "owner_review_action_brief.json")
    owner_review_action_brief_trend = _read_json(OWNER_DECISION_DIR / "owner_review_action_brief_trend_snapshot.json")
    owner_review_packet_diff = _read_json(OWNER_DECISION_DIR / "owner_review_packet_diff.json")
    owner_review_decision_simulator = _read_json(OWNER_DECISION_DIR / "owner_review_decision_simulator.json")
    owner_review_decision_impact_trend = _read_json(OWNER_DECISION_DIR / "owner_review_decision_impact_trend_snapshot.json")
    owner_review_blocker_digest = _read_json(OWNER_DECISION_DIR / "owner_review_blocker_digest.json")
    owner_review_blocker_digest_trend = _read_json(OWNER_DECISION_DIR / "owner_review_blocker_digest_trend_snapshot.json")
    owner_review_blocker_guardrail_matrix = _read_json(OWNER_DECISION_DIR / "owner_review_blocker_guardrail_matrix.json")
    owner_review_blocker_guardrail_matrix_trend = _read_json(OWNER_DECISION_DIR / "owner_review_blocker_guardrail_matrix_trend_snapshot.json")
    owner_review_guardrail_action_drilldown = _read_json(OWNER_DECISION_DIR / "owner_review_guardrail_action_drilldown.json")
    owner_review_guardrail_action_drilldown_trend = _read_json(OWNER_DECISION_DIR / "owner_review_guardrail_action_drilldown_trend_snapshot.json")
    owner_review_action_dependency_index = _read_json(OWNER_DECISION_DIR / "owner_review_action_dependency_index.json")
    owner_review_action_dependency_trend = _read_json(OWNER_DECISION_DIR / "owner_review_action_dependency_trend_snapshot.json")
    owner_review_action_dependency_coverage = _read_json(OWNER_DECISION_DIR / "owner_review_action_dependency_coverage.json")
    owner_review_action_dependency_coverage_trend = _read_json(OWNER_DECISION_DIR / "owner_review_action_dependency_coverage_trend_snapshot.json")
    owner_review_coverage_sla_consistency = _read_json(OWNER_DECISION_DIR / "owner_review_coverage_sla_consistency.json")
    owner_review_coverage_sla_consistency_trend = _read_json(OWNER_DECISION_DIR / "owner_review_coverage_sla_consistency_trend_snapshot.json")
    owner_pending_decision_freeze_guard = _read_json(OWNER_DECISION_DIR / "owner_pending_decision_freeze_guard.json")
    owner_pending_decision_freeze_guard_trend = _read_json(OWNER_DECISION_DIR / "owner_pending_decision_freeze_guard_trend_snapshot.json")
    owner_review_packet_freshness_cross_check = _read_json(OWNER_DECISION_DIR / "owner_review_packet_freshness_cross_check.json")
    owner_review_packet_freshness_trend = _read_json(OWNER_DECISION_DIR / "owner_review_packet_freshness_trend_snapshot.json")
    owner_review_evidence_manifest = _read_json(OWNER_DECISION_DIR / "owner_review_evidence_manifest.json")
    owner_review_evidence_manifest_trend = _read_json(OWNER_DECISION_DIR / "owner_review_evidence_manifest_trend_snapshot.json")
    owner_review_decision_readiness_seal = _read_json(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal.json")
    owner_review_decision_readiness_seal_trend = _read_json(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal_trend_snapshot.json")
    owner_review_decision_readiness_seal_ops_digest = _read_json(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal_ops_digest.json")
    owner_review_dry_run_decision_plan = _read_json(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan.json")
    owner_review_dry_run_decision_plan_trend = _read_json(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_trend_snapshot.json")
    owner_review_dry_run_decision_plan_coverage = _read_json(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_coverage.json")
    owner_review_dry_run_decision_plan_coverage_trend = _read_json(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_coverage_trend_snapshot.json")
    return {
        "report": report if isinstance(report, dict) else {},
        "priorities": priorities if isinstance(priorities, dict) else {},
        "packet": packet if isinstance(packet, dict) else {},
        "consistency": consistency if isinstance(consistency, dict) else {},
        "staleness": staleness if isinstance(staleness, dict) else {},
        "trend": trend if isinstance(trend, dict) else {},
        "dependency": dependency if isinstance(dependency, dict) else {},
        "risk_heatmap": risk_heatmap if isinstance(risk_heatmap, dict) else {},
        "review_checklist": review_checklist if isinstance(review_checklist, dict) else {},
        "guardrail_validator": guardrail_validator if isinstance(guardrail_validator, dict) else {},
        "guardrail_trend": guardrail_trend if isinstance(guardrail_trend, dict) else {},
        "guardrail_coverage": guardrail_coverage if isinstance(guardrail_coverage, dict) else {},
        "guardrail_coverage_trend": guardrail_coverage_trend if isinstance(guardrail_coverage_trend, dict) else {},
        "governance_health": governance_health if isinstance(governance_health, dict) else {},
        "governance_health_trend": governance_health_trend if isinstance(governance_health_trend, dict) else {},
        "governance_freshness": governance_freshness if isinstance(governance_freshness, dict) else {},
        "governance_ops_digest": governance_ops_digest if isinstance(governance_ops_digest, dict) else {},
        "owner_review_drilldown": owner_review_drilldown if isinstance(owner_review_drilldown, dict) else {},
        "owner_review_packet_coverage": owner_review_packet_coverage if isinstance(owner_review_packet_coverage, dict) else {},
        "owner_review_integrity_manifest": owner_review_integrity_manifest if isinstance(owner_review_integrity_manifest, dict) else {},
        "owner_review_integrity_trend": owner_review_integrity_trend if isinstance(owner_review_integrity_trend, dict) else {},
        "owner_review_readiness_checklist": owner_review_readiness_checklist if isinstance(owner_review_readiness_checklist, dict) else {},
        "owner_review_readiness_trend": owner_review_readiness_trend if isinstance(owner_review_readiness_trend, dict) else {},
        "owner_review_queue_aging": owner_review_queue_aging if isinstance(owner_review_queue_aging, dict) else {},
        "owner_review_queue_aging_trend": owner_review_queue_aging_trend if isinstance(owner_review_queue_aging_trend, dict) else {},
        "owner_review_queue_sla_forecast": owner_review_queue_sla_forecast if isinstance(owner_review_queue_sla_forecast, dict) else {},
        "owner_review_queue_sla_forecast_trend": owner_review_queue_sla_forecast_trend if isinstance(owner_review_queue_sla_forecast_trend, dict) else {},
        "owner_review_next_action_preview": owner_review_next_action_preview if isinstance(owner_review_next_action_preview, dict) else {},
        "owner_review_next_action_trend": owner_review_next_action_trend if isinstance(owner_review_next_action_trend, dict) else {},
        "owner_review_action_brief": owner_review_action_brief if isinstance(owner_review_action_brief, dict) else {},
        "owner_review_action_brief_trend": owner_review_action_brief_trend if isinstance(owner_review_action_brief_trend, dict) else {},
        "owner_review_packet_diff": owner_review_packet_diff if isinstance(owner_review_packet_diff, dict) else {},
        "owner_review_decision_simulator": owner_review_decision_simulator if isinstance(owner_review_decision_simulator, dict) else {},
        "owner_review_decision_impact_trend": owner_review_decision_impact_trend if isinstance(owner_review_decision_impact_trend, dict) else {},
        "owner_review_blocker_digest": owner_review_blocker_digest if isinstance(owner_review_blocker_digest, dict) else {},
        "owner_review_blocker_digest_trend": owner_review_blocker_digest_trend if isinstance(owner_review_blocker_digest_trend, dict) else {},
        "owner_review_blocker_guardrail_matrix": owner_review_blocker_guardrail_matrix if isinstance(owner_review_blocker_guardrail_matrix, dict) else {},
        "owner_review_blocker_guardrail_matrix_trend": owner_review_blocker_guardrail_matrix_trend if isinstance(owner_review_blocker_guardrail_matrix_trend, dict) else {},
        "owner_review_guardrail_action_drilldown": owner_review_guardrail_action_drilldown if isinstance(owner_review_guardrail_action_drilldown, dict) else {},
        "owner_review_guardrail_action_drilldown_trend": owner_review_guardrail_action_drilldown_trend if isinstance(owner_review_guardrail_action_drilldown_trend, dict) else {},
        "owner_review_action_dependency_index": owner_review_action_dependency_index if isinstance(owner_review_action_dependency_index, dict) else {},
        "owner_review_action_dependency_trend": owner_review_action_dependency_trend if isinstance(owner_review_action_dependency_trend, dict) else {},
        "owner_review_action_dependency_coverage": owner_review_action_dependency_coverage if isinstance(owner_review_action_dependency_coverage, dict) else {},
        "owner_review_action_dependency_coverage_trend": owner_review_action_dependency_coverage_trend if isinstance(owner_review_action_dependency_coverage_trend, dict) else {},
        "owner_review_coverage_sla_consistency": owner_review_coverage_sla_consistency if isinstance(owner_review_coverage_sla_consistency, dict) else {},
        "owner_review_coverage_sla_consistency_trend": owner_review_coverage_sla_consistency_trend if isinstance(owner_review_coverage_sla_consistency_trend, dict) else {},
        "owner_pending_decision_freeze_guard": owner_pending_decision_freeze_guard if isinstance(owner_pending_decision_freeze_guard, dict) else {},
        "owner_pending_decision_freeze_guard_trend": owner_pending_decision_freeze_guard_trend if isinstance(owner_pending_decision_freeze_guard_trend, dict) else {},
        "owner_review_packet_freshness_cross_check": owner_review_packet_freshness_cross_check if isinstance(owner_review_packet_freshness_cross_check, dict) else {},
        "owner_review_packet_freshness_trend": owner_review_packet_freshness_trend if isinstance(owner_review_packet_freshness_trend, dict) else {},
        "owner_review_evidence_manifest": owner_review_evidence_manifest if isinstance(owner_review_evidence_manifest, dict) else {},
        "owner_review_evidence_manifest_trend": owner_review_evidence_manifest_trend if isinstance(owner_review_evidence_manifest_trend, dict) else {},
        "owner_review_decision_readiness_seal": owner_review_decision_readiness_seal if isinstance(owner_review_decision_readiness_seal, dict) else {},
        "owner_review_decision_readiness_seal_trend": owner_review_decision_readiness_seal_trend if isinstance(owner_review_decision_readiness_seal_trend, dict) else {},
        "owner_review_decision_readiness_seal_ops_digest": owner_review_decision_readiness_seal_ops_digest if isinstance(owner_review_decision_readiness_seal_ops_digest, dict) else {},
        "owner_review_dry_run_decision_plan": owner_review_dry_run_decision_plan if isinstance(owner_review_dry_run_decision_plan, dict) else {},
        "owner_review_dry_run_decision_plan_trend": owner_review_dry_run_decision_plan_trend if isinstance(owner_review_dry_run_decision_plan_trend, dict) else {},
        "owner_review_dry_run_decision_plan_coverage": owner_review_dry_run_decision_plan_coverage if isinstance(owner_review_dry_run_decision_plan_coverage, dict) else {},
        "owner_review_dry_run_decision_plan_coverage_trend": owner_review_dry_run_decision_plan_coverage_trend if isinstance(owner_review_dry_run_decision_plan_coverage_trend, dict) else {},
        "attention_items": (report.get("attention_items", []) if isinstance(report, dict) else [])[:40],
        "queues": (report.get("queues", []) if isinstance(report, dict) else [])[:20],
        "priority_items": (priorities.get("items", []) if isinstance(priorities, dict) else [])[:40],
        "top_priority_items": (priorities.get("top_items", []) if isinstance(priorities, dict) else [])[:10],
        "packet_groups": (packet.get("groups", []) if isinstance(packet, dict) else [])[:20],
        "packet_items": (packet.get("items", []) if isinstance(packet, dict) else [])[:20],
        "consistency_checks": (consistency.get("checks", []) if isinstance(consistency, dict) else [])[:40],
        "staleness_items": (staleness.get("attention_items", []) if isinstance(staleness, dict) else [])[:40],
        "trend_recent": (trend.get("recent", []) if isinstance(trend, dict) else [])[-10:],
        "dependency_actions": (dependency.get("blocked_actions", []) if isinstance(dependency, dict) else [])[:20],
        "dependency_queues": (dependency.get("queues", []) if isinstance(dependency, dict) else [])[:20],
        "risk_heatmap_actions": (risk_heatmap.get("action_heat", []) if isinstance(risk_heatmap, dict) else [])[:20],
        "risk_heatmap_queues": (risk_heatmap.get("queue_heat", []) if isinstance(risk_heatmap, dict) else [])[:20],
        "risk_heatmap_top_items": (risk_heatmap.get("top_risk_items", []) if isinstance(risk_heatmap, dict) else [])[:10],
        "review_checklist_items": (review_checklist.get("items", []) if isinstance(review_checklist, dict) else [])[:20],
        "guardrail_validator_checks": (guardrail_validator.get("checks", []) if isinstance(guardrail_validator, dict) else [])[:20],
        "guardrail_trend_recent": (guardrail_trend.get("recent", []) if isinstance(guardrail_trend, dict) else [])[-10:],
        "guardrail_coverage_rows": (guardrail_coverage.get("coverage_rows", []) if isinstance(guardrail_coverage, dict) else [])[:20],
        "guardrail_coverage_trend_recent": (guardrail_coverage_trend.get("recent", []) if isinstance(guardrail_coverage_trend, dict) else [])[-10:],
        "governance_health_checks": (governance_health.get("checks", []) if isinstance(governance_health, dict) else [])[:20],
        "governance_health_trend_recent": (governance_health_trend.get("recent", []) if isinstance(governance_health_trend, dict) else [])[-10:],
        "governance_freshness_items": (governance_freshness.get("items", []) if isinstance(governance_freshness, dict) else [])[:20],
        "governance_ops_digest_queues": (governance_ops_digest.get("queues", []) if isinstance(governance_ops_digest, dict) else [])[:20],
        "owner_review_drilldown_queue_risk": (owner_review_drilldown.get("queue_risk", []) if isinstance(owner_review_drilldown, dict) else [])[:20],
        "owner_review_drilldown_items": (owner_review_drilldown.get("items", []) if isinstance(owner_review_drilldown, dict) else [])[:20],
        "owner_review_packet_coverage_mismatches": (owner_review_packet_coverage.get("mismatches", []) if isinstance(owner_review_packet_coverage, dict) else [])[:20],
        "owner_review_integrity_manifest_artifacts": (owner_review_integrity_manifest.get("artifacts", []) if isinstance(owner_review_integrity_manifest, dict) else [])[:20],
        "owner_review_integrity_trend_recent": (owner_review_integrity_trend.get("recent", []) if isinstance(owner_review_integrity_trend, dict) else [])[-10:],
        "owner_review_readiness_checks": (owner_review_readiness_checklist.get("checks", []) if isinstance(owner_review_readiness_checklist, dict) else [])[:20],
        "owner_review_readiness_trend_recent": (owner_review_readiness_trend.get("recent", []) if isinstance(owner_review_readiness_trend, dict) else [])[-10:],
        "owner_review_queue_aging_rows": (owner_review_queue_aging.get("queues", []) if isinstance(owner_review_queue_aging, dict) else [])[:20],
        "owner_review_queue_aging_trend_recent": (owner_review_queue_aging_trend.get("recent", []) if isinstance(owner_review_queue_aging_trend, dict) else [])[-10:],
        "owner_review_queue_sla_forecasts": (owner_review_queue_sla_forecast.get("forecasts", []) if isinstance(owner_review_queue_sla_forecast, dict) else [])[:20],
        "owner_review_queue_sla_forecast_trend_recent": (owner_review_queue_sla_forecast_trend.get("recent", []) if isinstance(owner_review_queue_sla_forecast_trend, dict) else [])[-10:],
        "owner_review_next_action_preview_rows": (owner_review_next_action_preview.get("queue_previews", []) if isinstance(owner_review_next_action_preview, dict) else [])[:20],
        "owner_review_next_action_trend_recent": (owner_review_next_action_trend.get("recent", []) if isinstance(owner_review_next_action_trend, dict) else [])[-10:],
        "owner_review_action_brief_trend_recent": (owner_review_action_brief_trend.get("recent", []) if isinstance(owner_review_action_brief_trend, dict) else [])[-10:],
        "owner_review_packet_diff_findings": (owner_review_packet_diff.get("findings", []) if isinstance(owner_review_packet_diff, dict) else [])[:20],
        "owner_review_decision_simulations": (owner_review_decision_simulator.get("simulations", []) if isinstance(owner_review_decision_simulator, dict) else [])[:20],
        "owner_review_decision_impact_rows": (owner_review_decision_impact_trend.get("current_impact_rows", []) if isinstance(owner_review_decision_impact_trend, dict) else [])[:20],
        "owner_review_blocker_digest_top_blockers": (owner_review_blocker_digest.get("top_blockers", []) if isinstance(owner_review_blocker_digest, dict) else [])[:20],
        "owner_review_blocker_digest_next_actions": (owner_review_blocker_digest.get("next_owner_actions", []) if isinstance(owner_review_blocker_digest, dict) else [])[:20],
        "owner_review_blocker_digest_trend_recent": (owner_review_blocker_digest_trend.get("recent", []) if isinstance(owner_review_blocker_digest_trend, dict) else [])[-10:],
        "owner_review_blocker_guardrail_matrix_queues": (owner_review_blocker_guardrail_matrix.get("queues", []) if isinstance(owner_review_blocker_guardrail_matrix, dict) else [])[:20],
        "owner_review_blocker_guardrail_matrix_actions": (owner_review_blocker_guardrail_matrix.get("actions", []) if isinstance(owner_review_blocker_guardrail_matrix, dict) else [])[:20],
        "owner_review_blocker_guardrail_matrix_trend_recent": (owner_review_blocker_guardrail_matrix_trend.get("recent", []) if isinstance(owner_review_blocker_guardrail_matrix_trend, dict) else [])[-10:],
        "owner_review_guardrail_action_drilldown_actions": (owner_review_guardrail_action_drilldown.get("actions", []) if isinstance(owner_review_guardrail_action_drilldown, dict) else [])[:20],
        "owner_review_guardrail_action_drilldown_top_actions": (owner_review_guardrail_action_drilldown.get("top_actions", []) if isinstance(owner_review_guardrail_action_drilldown, dict) else [])[:10],
        "owner_review_guardrail_action_drilldown_trend_recent": (owner_review_guardrail_action_drilldown_trend.get("recent", []) if isinstance(owner_review_guardrail_action_drilldown_trend, dict) else [])[-10:],
        "owner_review_action_dependency_index_rows": (owner_review_action_dependency_index.get("review_order", []) if isinstance(owner_review_action_dependency_index, dict) else [])[:20],
        "owner_review_action_dependency_trend_recent": (owner_review_action_dependency_trend.get("recent", []) if isinstance(owner_review_action_dependency_trend, dict) else [])[-10:],
        "owner_review_action_dependency_coverage_queues": (owner_review_action_dependency_coverage.get("queues", []) if isinstance(owner_review_action_dependency_coverage, dict) else [])[:20],
        "owner_review_action_dependency_coverage_trend_recent": (owner_review_action_dependency_coverage_trend.get("recent", []) if isinstance(owner_review_action_dependency_coverage_trend, dict) else [])[-10:],
        "owner_review_coverage_sla_consistency_rows": (owner_review_coverage_sla_consistency.get("queues", []) if isinstance(owner_review_coverage_sla_consistency, dict) else [])[:20],
        "owner_review_coverage_sla_consistency_trend_recent": (owner_review_coverage_sla_consistency_trend.get("recent", []) if isinstance(owner_review_coverage_sla_consistency_trend, dict) else [])[-10:],
        "owner_pending_decision_freeze_guard_queues": (owner_pending_decision_freeze_guard.get("queues", []) if isinstance(owner_pending_decision_freeze_guard, dict) else [])[:20],
        "owner_pending_decision_freeze_guard_files": (owner_pending_decision_freeze_guard.get("decision_files", []) if isinstance(owner_pending_decision_freeze_guard, dict) else [])[:20],
        "owner_pending_decision_freeze_guard_trend_recent": (owner_pending_decision_freeze_guard_trend.get("recent", []) if isinstance(owner_pending_decision_freeze_guard_trend, dict) else [])[-10:],
        "owner_review_packet_freshness_cross_check_artifacts": (owner_review_packet_freshness_cross_check.get("artifacts", []) if isinstance(owner_review_packet_freshness_cross_check, dict) else [])[:20],
        "owner_review_packet_freshness_trend_recent": (owner_review_packet_freshness_trend.get("recent", []) if isinstance(owner_review_packet_freshness_trend, dict) else [])[-10:],
        "owner_review_evidence_manifest_artifacts_v70": (owner_review_evidence_manifest.get("artifacts", []) if isinstance(owner_review_evidence_manifest, dict) else [])[:20],
        "owner_review_evidence_manifest_trend_recent": (owner_review_evidence_manifest_trend.get("recent", []) if isinstance(owner_review_evidence_manifest_trend, dict) else [])[-10:],
        "owner_review_decision_readiness_seal_trends": (owner_review_decision_readiness_seal.get("trends", []) if isinstance(owner_review_decision_readiness_seal, dict) else [])[:20],
        "owner_review_decision_readiness_seal_files": (owner_review_decision_readiness_seal.get("decision_files", []) if isinstance(owner_review_decision_readiness_seal, dict) else [])[:20],
        "owner_review_decision_readiness_seal_trend_recent": (owner_review_decision_readiness_seal_trend.get("recent", []) if isinstance(owner_review_decision_readiness_seal_trend, dict) else [])[-10:],
        "owner_review_decision_readiness_seal_ops_digest_trends": (owner_review_decision_readiness_seal_ops_digest.get("trend_readiness", []) if isinstance(owner_review_decision_readiness_seal_ops_digest, dict) else [])[:20],
        "owner_review_decision_readiness_seal_ops_digest_files": (owner_review_decision_readiness_seal_ops_digest.get("decision_files", []) if isinstance(owner_review_decision_readiness_seal_ops_digest, dict) else [])[:20],
        "owner_review_dry_run_decision_plan_queues": (owner_review_dry_run_decision_plan.get("queue_plans", []) if isinstance(owner_review_dry_run_decision_plan, dict) else [])[:20],
        "owner_review_dry_run_decision_plan_trend_recent": (owner_review_dry_run_decision_plan_trend.get("recent", []) if isinstance(owner_review_dry_run_decision_plan_trend, dict) else [])[-10:],
        "owner_review_dry_run_decision_plan_coverage_rows": (owner_review_dry_run_decision_plan_coverage.get("queue_rows", []) if isinstance(owner_review_dry_run_decision_plan_coverage, dict) else [])[:20],
        "owner_review_dry_run_decision_plan_coverage_trend_recent": (owner_review_dry_run_decision_plan_coverage_trend.get("recent", []) if isinstance(owner_review_dry_run_decision_plan_coverage_trend, dict) else [])[-10:],
        "paths": {
            "report": str(OWNER_DECISION_DIR / "owner_decision_summary.json"),
            "audit": str(OWNER_DECISION_DIR / "owner_decision_summary_audit.jsonl"),
            "priorities": str(OWNER_DECISION_DIR / "owner_decision_priorities.json"),
            "priorities_audit": str(OWNER_DECISION_DIR / "owner_decision_priorities_audit.jsonl"),
            "packet": str(OWNER_DECISION_DIR / "owner_review_packet.json"),
            "packet_md": str(OWNER_DECISION_DIR / "owner_review_packet.md"),
            "packet_audit": str(OWNER_DECISION_DIR / "owner_review_packet_audit.jsonl"),
            "consistency": str(OWNER_DECISION_DIR / "owner_decision_consistency.json"),
            "consistency_audit": str(OWNER_DECISION_DIR / "owner_decision_consistency_audit.jsonl"),
            "staleness": str(OWNER_DECISION_DIR / "owner_decision_staleness.json"),
            "staleness_audit": str(OWNER_DECISION_DIR / "owner_decision_staleness_audit.jsonl"),
            "trend": str(OWNER_DECISION_DIR / "owner_decision_trend_snapshot.json"),
            "trend_audit": str(OWNER_DECISION_DIR / "owner_decision_trend_audit.jsonl"),
            "dependency": str(OWNER_DECISION_DIR / "owner_decision_dependency_map.json"),
            "dependency_audit": str(OWNER_DECISION_DIR / "owner_decision_dependency_map_audit.jsonl"),
            "risk_heatmap": str(OWNER_DECISION_DIR / "owner_decision_risk_heatmap.json"),
            "risk_heatmap_audit": str(OWNER_DECISION_DIR / "owner_decision_risk_heatmap_audit.jsonl"),
            "review_checklist": str(OWNER_DECISION_DIR / "owner_decision_review_checklist.json"),
            "review_checklist_md": str(OWNER_DECISION_DIR / "owner_decision_review_checklist.md"),
            "review_checklist_audit": str(OWNER_DECISION_DIR / "owner_decision_review_checklist_audit.jsonl"),
            "guardrail_validator": str(OWNER_DECISION_DIR / "owner_decision_guardrail_validator.json"),
            "guardrail_validator_audit": str(OWNER_DECISION_DIR / "owner_decision_guardrail_validator_audit.jsonl"),
            "guardrail_trend": str(OWNER_DECISION_DIR / "owner_decision_guardrail_trend_snapshot.json"),
            "guardrail_trend_audit": str(OWNER_DECISION_DIR / "owner_decision_guardrail_trend_audit.jsonl"),
            "guardrail_coverage": str(OWNER_DECISION_DIR / "owner_decision_guardrail_coverage_matrix.json"),
            "guardrail_coverage_audit": str(OWNER_DECISION_DIR / "owner_decision_guardrail_coverage_audit.jsonl"),
            "guardrail_coverage_trend": str(OWNER_DECISION_DIR / "owner_decision_guardrail_coverage_trend_snapshot.json"),
            "guardrail_coverage_trend_audit": str(OWNER_DECISION_DIR / "owner_decision_guardrail_coverage_trend_audit.jsonl"),
            "governance_health": str(OWNER_DECISION_DIR / "owner_decision_governance_health_summary.json"),
            "governance_health_audit": str(OWNER_DECISION_DIR / "owner_decision_governance_health_audit.jsonl"),
            "governance_health_trend": str(OWNER_DECISION_DIR / "owner_decision_governance_health_trend_snapshot.json"),
            "governance_health_trend_audit": str(OWNER_DECISION_DIR / "owner_decision_governance_health_trend_audit.jsonl"),
            "governance_freshness": str(OWNER_DECISION_DIR / "owner_decision_governance_freshness_summary.json"),
            "governance_freshness_audit": str(OWNER_DECISION_DIR / "owner_decision_governance_freshness_audit.jsonl"),
            "governance_ops_digest": str(OWNER_DECISION_DIR / "owner_decision_governance_ops_digest.json"),
            "governance_ops_digest_md": str(OWNER_DECISION_DIR / "owner_decision_governance_ops_digest.md"),
            "governance_ops_digest_audit": str(OWNER_DECISION_DIR / "owner_decision_governance_ops_digest_audit.jsonl"),
            "owner_review_drilldown": str(OWNER_DECISION_DIR / "owner_review_drilldown.json"),
            "owner_review_drilldown_md": str(OWNER_DECISION_DIR / "owner_review_drilldown.md"),
            "owner_review_drilldown_audit": str(OWNER_DECISION_DIR / "owner_review_drilldown_audit.jsonl"),
            "owner_review_packet_coverage": str(OWNER_DECISION_DIR / "owner_review_packet_coverage.json"),
            "owner_review_packet_coverage_audit": str(OWNER_DECISION_DIR / "owner_review_packet_coverage_audit.jsonl"),
            "owner_review_integrity_manifest": str(OWNER_DECISION_DIR / "owner_review_integrity_manifest.json"),
            "owner_review_integrity_manifest_audit": str(OWNER_DECISION_DIR / "owner_review_integrity_manifest_audit.jsonl"),
            "owner_review_integrity_trend": str(OWNER_DECISION_DIR / "owner_review_integrity_trend_snapshot.json"),
            "owner_review_integrity_trend_audit": str(OWNER_DECISION_DIR / "owner_review_integrity_trend_audit.jsonl"),
            "owner_review_readiness_checklist": str(OWNER_DECISION_DIR / "owner_review_readiness_checklist.json"),
            "owner_review_readiness_checklist_md": str(OWNER_DECISION_DIR / "owner_review_readiness_checklist.md"),
            "owner_review_readiness_checklist_audit": str(OWNER_DECISION_DIR / "owner_review_readiness_checklist_audit.jsonl"),
            "owner_review_readiness_trend": str(OWNER_DECISION_DIR / "owner_review_readiness_trend_snapshot.json"),
            "owner_review_readiness_trend_audit": str(OWNER_DECISION_DIR / "owner_review_readiness_trend_audit.jsonl"),
            "owner_review_queue_aging": str(OWNER_DECISION_DIR / "owner_review_queue_aging.json"),
            "owner_review_queue_aging_audit": str(OWNER_DECISION_DIR / "owner_review_queue_aging_audit.jsonl"),
            "owner_review_queue_aging_trend": str(OWNER_DECISION_DIR / "owner_review_queue_aging_trend_snapshot.json"),
            "owner_review_queue_aging_trend_audit": str(OWNER_DECISION_DIR / "owner_review_queue_aging_trend_audit.jsonl"),
            "owner_review_queue_sla_forecast": str(OWNER_DECISION_DIR / "owner_review_queue_sla_forecast.json"),
            "owner_review_queue_sla_forecast_audit": str(OWNER_DECISION_DIR / "owner_review_queue_sla_forecast_audit.jsonl"),
            "owner_review_queue_sla_forecast_trend": str(OWNER_DECISION_DIR / "owner_review_queue_sla_forecast_trend_snapshot.json"),
            "owner_review_queue_sla_forecast_trend_audit": str(OWNER_DECISION_DIR / "owner_review_queue_sla_forecast_trend_audit.jsonl"),
            "owner_review_next_action_preview": str(OWNER_DECISION_DIR / "owner_review_next_action_preview.json"),
            "owner_review_next_action_preview_audit": str(OWNER_DECISION_DIR / "owner_review_next_action_preview_audit.jsonl"),
            "owner_review_next_action_trend": str(OWNER_DECISION_DIR / "owner_review_next_action_trend_snapshot.json"),
            "owner_review_next_action_trend_audit": str(OWNER_DECISION_DIR / "owner_review_next_action_trend_audit.jsonl"),
            "owner_review_action_brief": str(OWNER_DECISION_DIR / "owner_review_action_brief.json"),
            "owner_review_action_brief_md": str(OWNER_DECISION_DIR / "owner_review_action_brief.md"),
            "owner_review_action_brief_audit": str(OWNER_DECISION_DIR / "owner_review_action_brief_audit.jsonl"),
            "owner_review_action_brief_trend": str(OWNER_DECISION_DIR / "owner_review_action_brief_trend_snapshot.json"),
            "owner_review_action_brief_trend_audit": str(OWNER_DECISION_DIR / "owner_review_action_brief_trend_audit.jsonl"),
            "owner_review_packet_diff": str(OWNER_DECISION_DIR / "owner_review_packet_diff.json"),
            "owner_review_packet_diff_md": str(OWNER_DECISION_DIR / "owner_review_packet_diff.md"),
            "owner_review_packet_diff_audit": str(OWNER_DECISION_DIR / "owner_review_packet_diff_audit.jsonl"),
            "owner_review_decision_simulator": str(OWNER_DECISION_DIR / "owner_review_decision_simulator.json"),
            "owner_review_decision_simulator_md": str(OWNER_DECISION_DIR / "owner_review_decision_simulator.md"),
            "owner_review_decision_simulator_audit": str(OWNER_DECISION_DIR / "owner_review_decision_simulator_audit.jsonl"),
            "owner_review_decision_impact_trend": str(OWNER_DECISION_DIR / "owner_review_decision_impact_trend_snapshot.json"),
            "owner_review_decision_impact_trend_audit": str(OWNER_DECISION_DIR / "owner_review_decision_impact_trend_audit.jsonl"),
            "owner_review_blocker_digest": str(OWNER_DECISION_DIR / "owner_review_blocker_digest.json"),
            "owner_review_blocker_digest_md": str(OWNER_DECISION_DIR / "owner_review_blocker_digest.md"),
            "owner_review_blocker_digest_audit": str(OWNER_DECISION_DIR / "owner_review_blocker_digest_audit.jsonl"),
            "owner_review_blocker_digest_trend": str(OWNER_DECISION_DIR / "owner_review_blocker_digest_trend_snapshot.json"),
            "owner_review_blocker_digest_trend_audit": str(OWNER_DECISION_DIR / "owner_review_blocker_digest_trend_audit.jsonl"),
            "owner_review_blocker_guardrail_matrix": str(OWNER_DECISION_DIR / "owner_review_blocker_guardrail_matrix.json"),
            "owner_review_blocker_guardrail_matrix_audit": str(OWNER_DECISION_DIR / "owner_review_blocker_guardrail_matrix_audit.jsonl"),
            "owner_review_blocker_guardrail_matrix_trend": str(OWNER_DECISION_DIR / "owner_review_blocker_guardrail_matrix_trend_snapshot.json"),
            "owner_review_blocker_guardrail_matrix_trend_audit": str(OWNER_DECISION_DIR / "owner_review_blocker_guardrail_matrix_trend_audit.jsonl"),
            "owner_review_guardrail_action_drilldown": str(OWNER_DECISION_DIR / "owner_review_guardrail_action_drilldown.json"),
            "owner_review_guardrail_action_drilldown_md": str(OWNER_DECISION_DIR / "owner_review_guardrail_action_drilldown.md"),
            "owner_review_guardrail_action_drilldown_audit": str(OWNER_DECISION_DIR / "owner_review_guardrail_action_drilldown_audit.jsonl"),
            "owner_review_guardrail_action_drilldown_trend": str(OWNER_DECISION_DIR / "owner_review_guardrail_action_drilldown_trend_snapshot.json"),
            "owner_review_guardrail_action_drilldown_trend_audit": str(OWNER_DECISION_DIR / "owner_review_guardrail_action_drilldown_trend_audit.jsonl"),
            "owner_review_action_dependency_index": str(OWNER_DECISION_DIR / "owner_review_action_dependency_index.json"),
            "owner_review_action_dependency_index_audit": str(OWNER_DECISION_DIR / "owner_review_action_dependency_index_audit.jsonl"),
            "owner_review_action_dependency_trend": str(OWNER_DECISION_DIR / "owner_review_action_dependency_trend_snapshot.json"),
            "owner_review_action_dependency_trend_audit": str(OWNER_DECISION_DIR / "owner_review_action_dependency_trend_audit.jsonl"),
            "owner_review_action_dependency_coverage": str(OWNER_DECISION_DIR / "owner_review_action_dependency_coverage.json"),
            "owner_review_action_dependency_coverage_audit": str(OWNER_DECISION_DIR / "owner_review_action_dependency_coverage_audit.jsonl"),
            "owner_review_action_dependency_coverage_trend": str(OWNER_DECISION_DIR / "owner_review_action_dependency_coverage_trend_snapshot.json"),
            "owner_review_action_dependency_coverage_trend_audit": str(OWNER_DECISION_DIR / "owner_review_action_dependency_coverage_trend_audit.jsonl"),
            "owner_review_coverage_sla_consistency": str(OWNER_DECISION_DIR / "owner_review_coverage_sla_consistency.json"),
            "owner_review_coverage_sla_consistency_audit": str(OWNER_DECISION_DIR / "owner_review_coverage_sla_consistency_audit.jsonl"),
            "owner_review_coverage_sla_consistency_trend": str(OWNER_DECISION_DIR / "owner_review_coverage_sla_consistency_trend_snapshot.json"),
            "owner_review_coverage_sla_consistency_trend_audit": str(OWNER_DECISION_DIR / "owner_review_coverage_sla_consistency_trend_audit.jsonl"),
            "owner_pending_decision_freeze_guard": str(OWNER_DECISION_DIR / "owner_pending_decision_freeze_guard.json"),
            "owner_pending_decision_freeze_guard_audit": str(OWNER_DECISION_DIR / "owner_pending_decision_freeze_guard_audit.jsonl"),
            "owner_pending_decision_freeze_guard_trend": str(OWNER_DECISION_DIR / "owner_pending_decision_freeze_guard_trend_snapshot.json"),
            "owner_pending_decision_freeze_guard_trend_audit": str(OWNER_DECISION_DIR / "owner_pending_decision_freeze_guard_trend_audit.jsonl"),
            "owner_review_packet_freshness_cross_check": str(OWNER_DECISION_DIR / "owner_review_packet_freshness_cross_check.json"),
            "owner_review_packet_freshness_cross_check_audit": str(OWNER_DECISION_DIR / "owner_review_packet_freshness_cross_check_audit.jsonl"),
            "owner_review_packet_freshness_trend": str(OWNER_DECISION_DIR / "owner_review_packet_freshness_trend_snapshot.json"),
            "owner_review_packet_freshness_trend_audit": str(OWNER_DECISION_DIR / "owner_review_packet_freshness_trend_audit.jsonl"),
            "owner_review_evidence_manifest_v70": str(OWNER_DECISION_DIR / "owner_review_evidence_manifest.json"),
            "owner_review_evidence_manifest_v70_audit": str(OWNER_DECISION_DIR / "owner_review_evidence_manifest_audit.jsonl"),
            "owner_review_evidence_manifest_trend": str(OWNER_DECISION_DIR / "owner_review_evidence_manifest_trend_snapshot.json"),
            "owner_review_evidence_manifest_trend_audit": str(OWNER_DECISION_DIR / "owner_review_evidence_manifest_trend_audit.jsonl"),
            "owner_review_decision_readiness_seal": str(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal.json"),
            "owner_review_decision_readiness_seal_audit": str(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal_audit.jsonl"),
            "owner_review_decision_readiness_seal_trend": str(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal_trend_snapshot.json"),
            "owner_review_decision_readiness_seal_trend_audit": str(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal_trend_audit.jsonl"),
            "owner_review_decision_readiness_seal_ops_digest": str(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal_ops_digest.json"),
            "owner_review_decision_readiness_seal_ops_digest_md": str(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal_ops_digest.md"),
            "owner_review_decision_readiness_seal_ops_digest_audit": str(OWNER_DECISION_DIR / "owner_review_decision_readiness_seal_ops_digest_audit.jsonl"),
            "owner_review_dry_run_decision_plan": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan.json"),
            "owner_review_dry_run_decision_plan_md": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan.md"),
            "owner_review_dry_run_decision_plan_audit": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_audit.jsonl"),
            "owner_review_dry_run_decision_plan_trend": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_trend_snapshot.json"),
            "owner_review_dry_run_decision_plan_trend_audit": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_trend_audit.jsonl"),
            "owner_review_dry_run_decision_plan_coverage": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_coverage.json"),
            "owner_review_dry_run_decision_plan_coverage_audit": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_coverage_audit.jsonl"),
            "owner_review_dry_run_decision_plan_coverage_trend": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_coverage_trend_snapshot.json"),
            "owner_review_dry_run_decision_plan_coverage_trend_audit": str(OWNER_DECISION_DIR / "owner_review_dry_run_decision_plan_coverage_trend_audit.jsonl"),
        },
    }


def _knowledge_trust_summary() -> dict:
    registry = _read_json(KNOWLEDGE_TRUST_DIR / "knowledge_quarantine_registry.json")
    review_packet = _read_json(KNOWLEDGE_TRUST_DIR / "knowledge_review_packet.json")
    sustained_gate = _read_json(KNOWLEDGE_TRUST_DIR / "knowledge_sustained_candidate_gate.json")
    trusted_queue = _read_json(KNOWLEDGE_TRUST_DIR / "knowledge_trusted_owner_review_queue.json")
    return {
        "registry": registry if isinstance(registry, dict) else {},
        "review_packet": review_packet if isinstance(review_packet, dict) else {},
        "sustained_gate": sustained_gate if isinstance(sustained_gate, dict) else {},
        "trusted_queue": trusted_queue if isinstance(trusted_queue, dict) else {},
        "quarantine_items": (registry.get("quarantine_items", []) if isinstance(registry, dict) else [])[:20],
        "review_items": (review_packet.get("items", []) if isinstance(review_packet, dict) else [])[:20],
        "sustained_ready_items": (sustained_gate.get("ready_items", []) if isinstance(sustained_gate, dict) else [])[:20],
        "owner_queue_items": (trusted_queue.get("items", []) if isinstance(trusted_queue, dict) else [])[:20],
        "paths": {
            "registry": str(KNOWLEDGE_TRUST_DIR / "knowledge_quarantine_registry.json"),
            "registry_audit": str(KNOWLEDGE_TRUST_DIR / "knowledge_quarantine_registry_audit.jsonl"),
            "review_packet": str(KNOWLEDGE_TRUST_DIR / "knowledge_review_packet.json"),
            "review_packet_audit": str(KNOWLEDGE_TRUST_DIR / "knowledge_review_packet_audit.jsonl"),
            "sustained_gate": str(KNOWLEDGE_TRUST_DIR / "knowledge_sustained_candidate_gate.json"),
            "sustained_gate_audit": str(KNOWLEDGE_TRUST_DIR / "knowledge_sustained_candidate_gate_audit.jsonl"),
            "trusted_queue": str(KNOWLEDGE_TRUST_DIR / "knowledge_trusted_owner_review_queue.json"),
            "trusted_queue_audit": str(KNOWLEDGE_TRUST_DIR / "knowledge_trusted_owner_review_queue_audit.jsonl"),
            "trusted_decisions": str(KNOWLEDGE_TRUST_DIR / "knowledge_trusted_owner_decisions.json"),
        },
    }


def _dashboard_perf_summary() -> dict:
    profile = _read_json(DASHBOARD_PERF_DIR / "dashboard_refresh_profile.json")
    manifest = _read_json(DASHBOARD_PERF_DIR / "dashboard_refresh_manifest.json")
    cache = _read_json(DASHBOARD_PERF_DIR / "dashboard_refresh_cache_summary.json")
    write_steps = _read_json(DASHBOARD_PERF_DIR / "dashboard_refresh_write_steps.json")
    return {
        "profile": profile if isinstance(profile, dict) else {},
        "manifest": manifest if isinstance(manifest, dict) else {},
        "cache": cache if isinstance(cache, dict) else {},
        "write_steps": write_steps if isinstance(write_steps, dict) else {},
        "manifest_modules": (manifest.get("modules", []) if isinstance(manifest, dict) else [])[:20],
        "cache_modules": (cache.get("modules", []) if isinstance(cache, dict) else [])[:20],
        "write_step_rows": (write_steps.get("steps", []) if isinstance(write_steps, dict) else [])[:20],
        "paths": {
            "profile": str(DASHBOARD_PERF_DIR / "dashboard_refresh_profile.json"),
            "audit": str(DASHBOARD_PERF_DIR / "dashboard_refresh_profile_audit.jsonl"),
            "manifest": str(DASHBOARD_PERF_DIR / "dashboard_refresh_manifest.json"),
            "manifest_audit": str(DASHBOARD_PERF_DIR / "dashboard_refresh_manifest_audit.jsonl"),
            "cache": str(DASHBOARD_PERF_DIR / "dashboard_refresh_cache_summary.json"),
            "cache_audit": str(DASHBOARD_PERF_DIR / "dashboard_refresh_cache_audit.jsonl"),
            "write_steps": str(DASHBOARD_PERF_DIR / "dashboard_refresh_write_steps.json"),
            "write_steps_audit": str(DASHBOARD_PERF_DIR / "dashboard_refresh_write_steps_audit.jsonl"),
        },
    }


def _write_dashboard_cache_summary(plan: dict) -> None:
    DASHBOARD_PERF_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = DASHBOARD_PERF_DIR / "dashboard_refresh_cache_summary.json"
    audit_path = DASHBOARD_PERF_DIR / "dashboard_refresh_cache_audit.jsonl"
    summary_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": _now(), **plan}, ensure_ascii=False) + "\n")


def _write_dashboard_step_profile(plan: dict) -> None:
    DASHBOARD_PERF_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = DASHBOARD_PERF_DIR / "dashboard_refresh_write_steps.json"
    audit_path = DASHBOARD_PERF_DIR / "dashboard_refresh_write_steps_audit.jsonl"
    summary_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": _now(), **plan}, ensure_ascii=False) + "\n")


def _latest_json_files(root: Path, limit: int = 10) -> list[dict]:
    if not root.exists():
        return []
    files = sorted(root.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for path in files[:limit]:
        data = _read_json(path)
        rows.append({
            "name": path.name,
            "project": data.get("project", path.parent.name) if isinstance(data, dict) else path.parent.name,
            "status": data.get("status", data.get("health", "")) if isinstance(data, dict) else "",
            "path": str(path),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        })
    return rows


def _realtime_summary() -> dict:
    control_states = _latest_json_files(RESEARCH_DIR / "control_plane", 20)
    mandatory_states = _latest_json_files(RESEARCH_DIR / "mandatory_runtime_hook", 20)
    git_ci_states = _latest_json_files(RESEARCH_DIR / "git_ci", 20)
    health_path = RESEARCH_DIR / "health_check" / "health_report.json"
    memory_root = RESEARCH_DIR / "experience_memory"
    agent_os_runtime = _agent_os_runtime_summary(RESEARCH_DIR / "agent_os_runtime")
    return {
        "generated": _now(),
        "pid": os.getpid(),
        "control_states": control_states,
        "mandatory_states": mandatory_states,
        "git_ci_states": git_ci_states,
        "health": _read_json(health_path) if health_path.exists() else {},
        "memory": {
            "records": _count_jsonl(memory_root / "memory.jsonl"),
            "fts_index": str(memory_root / "memory_index.sqlite"),
            "fts_exists": (memory_root / "memory_index.sqlite").exists(),
            "vector_index": str(memory_root / "memory_vector.sqlite"),
            "vector_exists": (memory_root / "memory_vector.sqlite").exists(),
        },
        "agent_os_runtime": agent_os_runtime,
        "latest_backups": _backups(8),
    }


def _collect() -> dict:
    return {
        "generated": _now(),
        "root": str(ROOT),
        "mcp_inventory": _mcp_inventory(),
        "manual_projects": _manual_projects(),
        "evidence": _evidence_summary(),
        "registry": _registry_summary(),
        "stability": _stability_summary(),
        "shadow": _shadow_summary(),
        "promotion_review": _promotion_review_summary(),
        "investment_eval": _investment_eval_summary(),
        "active_canary": _active_canary_summary(),
        "trajectory": _trajectory_summary(),
        "distillation": _distillation_summary(),
        "model_adapter": _model_adapter_summary(),
        "owner_decision": _owner_decision_summary(),
        "knowledge_trust": _knowledge_trust_summary(),
        "dashboard_perf": _dashboard_perf_summary(),
        "backups": _backups(),
    }


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _link(path: str, label: str = "") -> str:
    text = html.escape(label or Path(path).name or path)
    return f"<span title=\"{html.escape(path)}\">{text}</span>"


def _detail_link(path: str, label: str = "detail") -> str:
    text = html.escape(label)
    if not path:
        return text
    try:
        rel = Path(path).resolve().relative_to(DASHBOARD_DIR.resolve()).as_posix()
        return f"<a href=\"{html.escape(rel)}\">{text}</a>"
    except Exception:
        return _link(path, label)


def _safe_replay_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value)).strip("-").lower()
    return safe or "_empty"


def _replay_link(bucket: str, key: str, label: str = "") -> str:
    if not key:
        key = "_empty"
    text = html.escape(label or key)
    href = f"trajectory_replay/{bucket}/{_safe_replay_name(key)}.html"
    return f"<a href=\"{html.escape(href)}\">{text}</a>"


def _diff_link(bucket: str, key: str, label: str = "") -> str:
    text = html.escape(label or key)
    href = f"trajectory_diff/{_safe_replay_name(bucket)}__{_safe_replay_name(key)}.html"
    return f"<a href=\"{html.escape(href)}\">{text}</a>"


def _html(data: dict) -> str:
    projects = data["manual_projects"]
    mcps = data["mcp_inventory"]
    evidence = data["evidence"]
    runtime = evidence.get("agent_os_runtime", {})
    registry = data.get("registry", {})
    stability = data.get("stability", {})
    shadow = data.get("shadow", {})
    promotion_review = data.get("promotion_review", {})
    investment_eval = data.get("investment_eval", {})
    active_canary = data.get("active_canary", {})
    trajectory = data.get("trajectory", {})
    distillation = data.get("distillation", {})
    model_adapter = data.get("model_adapter", {})
    owner_decision = data.get("owner_decision", {})
    knowledge_trust = data.get("knowledge_trust", {})
    dashboard_perf = data.get("dashboard_perf", {})
    backups = data["backups"]
    passed_projects = sum(1 for p in projects if p["total"] and p["passed"] == p["total"])
    replay_index = trajectory.get("replay_index") or {}

    def replay_cell(bucket: str, key: str, label: str = "") -> str:
        display = label or key
        if key and key in (replay_index.get(bucket) or {}):
            return _replay_link(bucket, key, display)
        return html.escape(str(display))

    project_rows = [[
        html.escape(p["name"]),
        html.escape(p["track"]),
        html.escape(p["autonomy"]),
        html.escape(p["progress"]),
        str(p["iteration"]),
        _link(p["path"], "state.json"),
    ] for p in projects[:25]]

    mcp_rows = [[html.escape(m["name"]), str(m["file_count"]), "yes" if m["has_readme"] else "no", html.escape(", ".join(m["runner"]))] for m in mcps]
    backup_rows = [[html.escape(b["name"]), html.escape(b["size_human"]), html.escape(b["modified"][:19]), _link(b["path"], "zip")] for b in backups[:15]]
    trace_rows = [[html.escape(t["project"]), str(t["events"]), _link(t["path"], "trace.jsonl")] for t in evidence["trace_projects"]]
    parallel_rows = [[html.escape(r["project"]), html.escape(r["run_id"]), html.escape(r["progress"]), html.escape(r["status"]), _link(r["path"], "run.json")] for r in evidence["parallel_runs"]]
    runstate_rows = [[
        html.escape(str(r.get("project", ""))),
        html.escape(str(r.get("run_id", ""))),
        html.escape(str(r.get("phase", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("decision", ""))),
        html.escape(str(r.get("manual_node", ""))),
        _link(str(r.get("path", "")), "RunState") + " · " + _detail_link(str(r.get("detail_path", "")), "drill-down"),
    ] for r in runtime.get("runs", [])]
    blocked_rows = [[
        html.escape(str(r.get("project", ""))),
        html.escape(str(r.get("run_id", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("decision", ""))),
        html.escape(", ".join(str(x) for x in r.get("failed_checks", []))),
        _link(str(r.get("path", "")), "RunState"),
    ] for r in runtime.get("blocked_runs", [])]
    retry_rows = [[
        html.escape(str(r.get("project", ""))),
        html.escape(str(r.get("run_id", ""))),
        html.escape(str(r.get("phase", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("updated", ""))[:19]),
        _link(str(r.get("path", "")), "RunState"),
    ] for r in runtime.get("retry_runs", [])]
    completion_rows = [[
        html.escape(str(r.get("project", ""))),
        html.escape(str(r.get("run_id", ""))),
        html.escape(str(r.get("task_class", ""))),
        html.escape(", ".join(str(x) for x in r.get("missing", []))),
        html.escape(", ".join(str(x) for x in r.get("forbidden_hits", []))),
        _link(str(r.get("path", "")), "RunState"),
    ] for r in runtime.get("completion_failures", [])]
    memory_rows = [[
        html.escape(str(r.get("project", ""))),
        html.escape(str(r.get("run_id", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("memory_id", ""))),
        _link(str(r.get("path", "")), "RunState"),
    ] for r in runtime.get("memory_writes", [])]
    mcp_lifecycle_rows = [[
        html.escape(status),
        str(count),
    ] for status, count in (registry.get("mcp_counts") or {}).items()]
    skill_lifecycle_rows = [[
        html.escape(status),
        str(count),
    ] for status, count in (registry.get("skill_counts") or {}).items()]
    soak = stability.get("soak", {})
    l4_soak_sanitizer = stability.get("l4_soak_sanitizer", {})
    l4_soak_matrix = stability.get("l4_soak_matrix", {})
    stability_paths = stability.get("paths", {})
    capability_rows = [[
        replay_cell("by_capability", str(r.get("name", ""))),
        str(r.get("calls", 0)),
        str(r.get("completed", 0)),
        str(r.get("failed", 0)),
        str(r.get("blocked", 0)),
        str(r.get("retry", 0)),
        str(r.get("expected_fail_closed", 0)),
        str(r.get("success_rate", 0)),
        str(r.get("operational_success_rate", 0)),
        html.escape(str(r.get("last_failure_reason", ""))),
    ] for r in stability.get("capabilities", [])]
    advice_rows = [[
        replay_cell("by_capability", str(r.get("name", ""))),
        html.escape(str(r.get("type", ""))),
        html.escape(str(r.get("current_status", ""))),
        html.escape(str(r.get("recommendation", ""))),
        str(r.get("calls", 0)),
        str(r.get("success_rate", 0)),
        str(r.get("operational_success_rate", 0)),
        str(r.get("expected_fail_closed", 0)),
        html.escape(str(r.get("reason", ""))),
    ] for r in stability.get("actionable", [])]
    shadow_rows = [[
        html.escape(str(r.get("shadow_run_id", ""))),
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("task_card_id", ""))),
        html.escape(str(r.get("shadow_result", ""))),
        html.escape(str(r.get("promotion_signal", ""))),
        str(r.get("finding_count", 0)),
        _link(str(r.get("path", "")), "ShadowRun"),
    ] for r in shadow.get("runs", [])]
    shadow_candidate_rows = [[
        html.escape(str(r.get("shadow_run_id", ""))),
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("task_card_id", ""))),
        html.escape(str(r.get("promotion_signal", ""))),
        _link(str(r.get("path", "")), "ShadowRun"),
    ] for r in shadow.get("candidates", [])]
    shadow_warning_rows = [[
        html.escape(str(r.get("shadow_run_id", ""))),
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("task_card_id", ""))),
        str(r.get("finding_count", 0)),
        _link(str(r.get("path", "")), "ShadowRun"),
    ] for r in shadow.get("warnings", [])]
    shadow_score_rows = [[
        replay_cell("by_capability", str(r.get("capability", ""))),
        str(r.get("shadow_run_count", 0)),
        str(r.get("agreement_rate", 0)),
        str(r.get("warn_rate", 0)),
        str(r.get("false_positive_rate", 0)),
        str(r.get("evidence_completeness", 0)),
        html.escape(str(r.get("promotion_recommendation", ""))),
        html.escape(str(r.get("promotion_reason", ""))),
        _link(str(r.get("latest_path", "")), "latest"),
    ] for r in shadow.get("scores", [])]
    shadow_readiness_rows = [[
        replay_cell("by_capability", str(r.get("capability", ""))),
        str(r.get("shadow_run_count", 0)),
        str(r.get("agreement_rate", 0)),
        str(r.get("evidence_completeness", 0)),
        html.escape(str(r.get("promotion_reason", ""))),
        _link(str(r.get("latest_path", "")), "latest"),
    ] for r in shadow.get("readiness", [])]
    review_rows = [[
        html.escape(str(r.get("review_id", ""))),
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("capability_type", ""))),
        html.escape(str(r.get("current_status", ""))),
        html.escape(str(r.get("target_status", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("owner_decision", ""))),
        html.escape(str(r.get("decision_reason", ""))),
        _link(str(r.get("registry_path", "")), "registry"),
    ] for r in promotion_review.get("items", [])]
    review_apply_rows = [[
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("owner", ""))),
        html.escape(str(r.get("decision_reason", ""))),
        _link(str(r.get("registry_path", "")), "registry"),
    ] for r in promotion_review.get("approved_pending_apply", [])]
    investment_summary = investment_eval.get("summary") or {}
    investment_target_rows = [[
        html.escape(str(skill)),
        html.escape(str(state.get("status", ""))),
        html.escape(str(state.get("lifecycle", ""))),
        html.escape(str((state.get("owner_override") or {}).get("lifecycle", ""))),
    ] for skill, state in (investment_eval.get("target_skills") or {}).items()]
    investment_case_rows = [[
        html.escape(str(r.get("case_id", ""))),
        html.escape(str(r.get("target", ""))),
        html.escape(str(r.get("case_type", ""))),
        html.escape(str(r.get("verdict", ""))),
        "yes" if r.get("passed") else "no",
        html.escape(str(r.get("failure_reason", ""))),
    ] for r in investment_eval.get("cases", [])]
    investment_queue_rows = [[
        html.escape(str(r.get("skill", ""))),
        html.escape(str(r.get("current_lifecycle", ""))),
        html.escape(str(r.get("queue_status", ""))),
        html.escape(str(r.get("recommended_action", ""))),
        html.escape(str(r.get("owner_decision", ""))),
    ] for r in investment_eval.get("promotion_queue", [])]
    canary_rows = [[
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("registry_status", ""))),
        str(r.get("active_run_count", 0)),
        str(r.get("active_success_rate", 0)),
        str(r.get("active_failure_count", 0)),
        str(r.get("verifier_failure_count", 0)),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("rollback_reason", ""))),
        html.escape(str(r.get("latest_run", ""))),
    ] for r in active_canary.get("items", [])]
    rollback_rows = [[
        replay_cell("by_capability", str(r.get("capability", ""))),
        str(r.get("active_run_count", 0)),
        str(r.get("active_success_rate", 0)),
        str(r.get("active_failure_count", 0)),
        html.escape(str(r.get("rollback_reason", ""))),
    ] for r in active_canary.get("rollback_candidates", [])]
    rollback_review_rows = [[
        html.escape(str(r.get("review_id", ""))),
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("current_status", ""))),
        html.escape(str(r.get("target_status", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("owner_decision", ""))),
        html.escape(str(r.get("rollback_reason", ""))),
    ] for r in active_canary.get("rollback_review_items", [])]
    trajectory_summary = trajectory.get("summary") or {}
    trajectory_rows = [[
        replay_cell("by_source_type", str(source)),
        str(count),
    ] for source, count in (trajectory_summary.get("source_counts") or {}).items()]
    trajectory_label_rows = [[
        replay_cell("by_outcome_label", str(label)),
        str(count),
    ] for label, count in (trajectory_summary.get("label_counts") or {}).items()]
    trajectory_category_rows = [[
        replay_cell("by_outcome_category", str(category)),
        str(count),
    ] for category, count in (trajectory_summary.get("category_counts") or {}).items()]
    trajectory_legacy_rows = [[
        replay_cell("by_legacy_label", str(label)),
        str(count),
    ] for label, count in (trajectory_summary.get("legacy_label_counts") or {}).items()]
    replay_bucket_rows = [[
        "source_type",
        str(len(replay_index.get("by_source_type") or {})),
    ], [
        "capability",
        str(len(replay_index.get("by_capability") or {})),
    ], [
        "task_class",
        str(len(replay_index.get("by_task_class") or {})),
    ], [
        "outcome_label",
        str(len(replay_index.get("by_outcome_label") or {})),
    ], [
        "legacy_label",
        str(len(replay_index.get("by_legacy_label") or {})),
    ], [
        "outcome_category",
        str(len(replay_index.get("by_outcome_category") or {})),
    ]]
    replay_diff = trajectory.get("replay_diff") or {}
    verifier_drilldown = trajectory.get("verifier_drilldown") or {}
    class_c_drilldown = trajectory.get("class_c_drilldown") or {}
    unknown_resolver = trajectory.get("unknown_resolver") or {}
    retry_drilldown = trajectory.get("retry_drilldown") or {}
    diff_group_rows = [[
        _diff_link(str(r.get("bucket", "")), str(r.get("key", "")), f"{r.get('bucket', '')}: {r.get('key', '')}"),
        html.escape(str(r.get("assessment", ""))),
        str(r.get("trajectory_count", 0)),
        str(r.get("success_count", 0)),
        str(r.get("failure_count", 0)),
        str(r.get("expected_fail_closed_count", 0)),
        str(r.get("shadow_warning_count", 0)),
        str(r.get("operational_failure_count", 0)),
        str(r.get("success_rate", 0)),
        html.escape(str(r.get("top_operational_pattern") or r.get("top_failure_pattern", ""))),
    ] for r in (replay_diff.get("top_groups") or [])[:12]]
    stable_path_rows = [[
        _diff_link(str(r.get("bucket", "")), str(r.get("key", "")), f"{r.get('bucket', '')}: {r.get('key', '')}"),
        str(r.get("trajectory_count", 0)),
        str(r.get("success_rate", 0)),
        html.escape(str(r.get("stable_success_path", ""))),
    ] for r in (replay_diff.get("stable_success_groups") or [])[:8]]
    repeat_failure_rows = [[
        _diff_link(str(r.get("bucket", "")), str(r.get("key", "")), f"{r.get('bucket', '')}: {r.get('key', '')}"),
        str(r.get("trajectory_count", 0)),
        str(r.get("failure_count", 0)),
        str(r.get("operational_failure_count", 0)),
        html.escape(str(r.get("top_operational_pattern") or r.get("top_failure_pattern", ""))),
    ] for r in (replay_diff.get("repeat_failure_groups") or [])[:8]]
    verifier_drilldown_items = verifier_drilldown.get("items", []) if isinstance(verifier_drilldown, dict) else []
    verifier_drilldown_rows = [[
        replay_cell("by_outcome_label", str(r.get("outcome_label", ""))),
        html.escape(str(r.get("trajectory_id", ""))),
        html.escape(str(r.get("task_class", ""))),
        html.escape(", ".join(r.get("missing_evidence", []) or []) or "none"),
        html.escape(", ".join(r.get("failed_checks", []) or []) or "none"),
        html.escape(str(r.get("recommendation", ""))),
    ] for r in verifier_drilldown_items[:12]]
    verifier_drilldown_summary = verifier_drilldown.get("summary", {}) if isinstance(verifier_drilldown, dict) else {}
    verifier_recommendation_rows = [[
        html.escape(str(r.get("recommendation", ""))),
        str(r.get("count", 0)),
    ] for r in (verifier_drilldown.get("recommendation_groups", []) if isinstance(verifier_drilldown, dict) else [])[:8]]
    class_c_summary = class_c_drilldown.get("summary", {}) if isinstance(class_c_drilldown, dict) else {}
    class_c_rows = [[
        replay_cell("by_outcome_label", str(r.get("outcome_label", ""))),
        html.escape(str(r.get("trajectory_id", ""))),
        html.escape(str(r.get("contract_status", ""))),
        str(r.get("missing_count", 0)),
        str(r.get("coverage", 0)),
        html.escape(", ".join(r.get("missing_fields", []) or []) or "none"),
        html.escape(str(r.get("recommendation", ""))),
    ] for r in (class_c_drilldown.get("items", []) if isinstance(class_c_drilldown, dict) else [])[:12]]
    class_c_missing_rows = [[
        html.escape(str(r.get("field", ""))),
        str(r.get("count", 0)),
    ] for r in [
        {"field": field, "count": count}
        for field, count in (class_c_summary.get("by_missing_field", {}) or {}).items()
    ][:12]]
    unknown_resolver_summary = unknown_resolver.get("summary", {}) if isinstance(unknown_resolver, dict) else {}
    unknown_resolution_rows = [[
        html.escape(str(r.get("resolution", ""))),
        str(r.get("count", 0)),
    ] for r in (unknown_resolver.get("recommendation_groups", []) if isinstance(unknown_resolver, dict) else [])[:8]]
    unknown_resolver_rows = [[
        replay_cell("by_outcome_label", str(r.get("outcome_label", ""))),
        html.escape(str(r.get("trajectory_id", ""))),
        html.escape(str(r.get("execution_phase", ""))),
        html.escape(str(r.get("execution_status", ""))),
        html.escape(str(r.get("resolution", ""))),
        html.escape(str(r.get("recommendation", ""))),
    ] for r in (unknown_resolver.get("items", []) if isinstance(unknown_resolver, dict) else [])[:12]]
    retry_drilldown_summary = retry_drilldown.get("summary", {}) if isinstance(retry_drilldown, dict) else {}
    retry_pattern_rows = [[
        html.escape(str(r.get("pattern", ""))),
        str(r.get("count", 0)),
        html.escape(str(r.get("retry_reason", ""))),
        str(r.get("followup_success_count", 0)),
        "yes" if r.get("repeated") else "no",
        html.escape(str(r.get("recommendation", ""))),
    ] for r in (retry_drilldown.get("pattern_groups", []) if isinstance(retry_drilldown, dict) else [])[:8]]
    retry_drilldown_rows = [[
        replay_cell("by_outcome_label", str(r.get("outcome_label", ""))),
        html.escape(str(r.get("trajectory_id", ""))),
        html.escape(str(r.get("task_class", ""))),
        html.escape(str(r.get("retry_reason", ""))),
        html.escape(str(r.get("retry_source", ""))),
        "yes" if r.get("has_followup_success") else "no",
    ] for r in (retry_drilldown.get("items", []) if isinstance(retry_drilldown, dict) else [])[:12]]
    retry_recovery = trajectory.get("retry_recovery") or {}
    retry_recovery_summary = retry_recovery.get("summary", {}) if isinstance(retry_recovery, dict) else {}
    retry_recovery_rows = [[
        replay_cell("by_outcome_label", str(r.get("outcome_label", ""))),
        html.escape(str(r.get("trajectory_id", ""))),
        html.escape(str(r.get("recovery_status", ""))),
        str(r.get("followup_count", 0)),
        str(r.get("followup_success_count", 0)),
        "yes" if r.get("stable_allowed") else "no",
        html.escape(", ".join(r.get("missing_recovery_fields", []) or []) or "none"),
        html.escape(str(r.get("recommendation", ""))),
    ] for r in (retry_recovery.get("items", []) if isinstance(retry_recovery, dict) else [])[:12]]
    retry_recovery_missing_rows = [[
        html.escape(str(r.get("field", ""))),
        str(r.get("count", 0)),
    ] for r in [
        {"field": field, "count": count}
        for field, count in (retry_recovery_summary.get("by_missing_recovery_field", {}) or {}).items()
    ][:12]]
    distillation_queue = distillation.get("queue") or (trajectory.get("distillation_queue") or {})
    distillation_paths = distillation.get("paths") or (trajectory.get("paths") or {})
    distillation_rows = [[
        html.escape(str(r.get("candidate_id", ""))),
        html.escape(str(r.get("candidate_type", ""))),
        html.escape(str(r.get("target", ""))),
        html.escape(str(r.get("priority", ""))),
        html.escape(str(r.get("status", ""))),
        _diff_link(
            str((r.get("source") or {}).get("bucket", "")),
            str((r.get("source") or {}).get("key", "")),
            str((r.get("source") or {}).get("assessment", "")),
        ),
        html.escape(str((r.get("distillation") or {}).get("lesson", ""))),
        html.escape(str((r.get("distillation") or {}).get("suggested_action", ""))),
    ] for r in (distillation.get("items") or distillation_queue.get("items") or [])[:20]]
    owner_report = owner_decision.get("report") or {}
    owner_paths = owner_decision.get("paths") or {}
    owner_queue_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("domain", ""))),
        "yes" if r.get("exists") else "no",
        str(r.get("queue_count", 0)),
        str(r.get("pending_count", 0)),
        str(r.get("approved_pending_count", 0)),
        html.escape(json.dumps(r.get("status_counts", {}), ensure_ascii=False)),
        _link(str(r.get("source_path", "")), "queue"),
    ] for r in owner_decision.get("queues", [])]
    owner_attention_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("domain", ""))),
        html.escape(str(r.get("item_id", ""))),
        html.escape(str(r.get("subject", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("blocked_action", ""))),
        html.escape(", ".join(str(x) for x in r.get("forbidden_auto_actions", []))),
        _link(str(r.get("source_path", "")), "source"),
    ] for r in owner_decision.get("attention_items", [])]
    owner_priorities = owner_decision.get("priorities") or {}
    owner_priority_rows = [[
        html.escape(str(r.get("priority_band", ""))),
        str(r.get("priority_score", 0)),
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("item_id", ""))),
        html.escape(str(r.get("subject", ""))),
        html.escape(str(r.get("owner_action", ""))),
        html.escape(", ".join(str(x) for x in r.get("recommended_decision_options", []))),
        html.escape(str(r.get("reason", ""))),
        _link(str(r.get("source_path", "")), "source"),
    ] for r in owner_decision.get("top_priority_items", [])]
    owner_packet = owner_decision.get("packet") or {}
    owner_packet_group_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        str(r.get("item_count", 0)),
        str(r.get("p0_count", 0)),
        str(r.get("p2_count", 0)),
        html.escape(str(r.get("recommended_review_mode", ""))),
        html.escape(str(r.get("first_action", ""))),
    ] for r in owner_decision.get("packet_groups", [])]
    owner_packet_item_rows = [[
        html.escape(str(r.get("priority_band", ""))),
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("subject", ""))),
        html.escape(str(r.get("decision_prompt", ""))),
        html.escape(", ".join(str(x) for x in r.get("recommended_decision_options", []))),
        _link(str(r.get("source_path", "")), "source"),
    ] for r in owner_decision.get("packet_items", [])]
    owner_consistency = owner_decision.get("consistency") or {}
    owner_consistency_rows = [[
        html.escape(str(r.get("name", ""))),
        "yes" if r.get("passed") else "no",
        html.escape(str(r.get("observed", ""))),
        html.escape(str(r.get("expected", ""))),
        html.escape(str(r.get("severity", ""))),
    ] for r in owner_decision.get("consistency_checks", [])]
    owner_staleness = owner_decision.get("staleness") or {}
    owner_staleness_rows = [[
        html.escape(str(r.get("staleness", ""))),
        str(r.get("age_hours", "")),
        html.escape(str(r.get("priority_band", ""))),
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("subject", ""))),
        html.escape(str(r.get("recommendation", ""))),
        html.escape(str(r.get("age_basis", ""))),
        _link(str(r.get("source_path", "")), "source"),
    ] for r in owner_decision.get("staleness_items", [])]
    owner_trend = owner_decision.get("trend") or {}
    owner_trend_current = owner_trend.get("current") or {}
    owner_trend_delta = owner_trend.get("delta_from_previous") or {}
    owner_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        str(r.get("pending_count", 0)),
        str(r.get("p0_count", 0)),
        str(r.get("stale_count", 0)),
        str(r.get("watch_count", 0)),
        html.escape(json.dumps(r.get("delta", {}), ensure_ascii=False)),
    ] for r in owner_decision.get("trend_recent", [])]
    owner_dependency = owner_decision.get("dependency") or {}
    owner_dependency_action_rows = [[
        html.escape(str(r.get("action", ""))),
        html.escape(str(r.get("label", ""))),
        str(r.get("blocking_decision_count", 0)),
        html.escape(", ".join(str(x.get("item_id", "")) for x in (r.get("top_blockers", []) or [])[:3])),
    ] for r in owner_decision.get("dependency_actions", [])]
    owner_dependency_queue_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        str(r.get("pending_decision_count", 0)),
    ] for r in owner_decision.get("dependency_queues", [])]
    owner_risk_heatmap = owner_decision.get("risk_heatmap") or {}
    owner_risk_action_rows = [[
        html.escape(str(r.get("action", ""))),
        str(r.get("decision_count", 0)),
        str(r.get("risk_score", 0)),
    ] for r in owner_decision.get("risk_heatmap_actions", [])]
    owner_risk_queue_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        str(r.get("risk_score", 0)),
        html.escape(json.dumps(r.get("action_counts", {}), ensure_ascii=False)),
    ] for r in owner_decision.get("risk_heatmap_queues", [])]
    owner_risk_top_rows = [[
        html.escape(str(r.get("risk_band", ""))),
        str(r.get("risk_score", 0)),
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("item_id", ""))),
        html.escape(str(r.get("subject", ""))),
        html.escape(", ".join(str(x) for x in r.get("blocked_actions", []))),
    ] for r in owner_decision.get("risk_heatmap_top_items", [])]
    owner_review_checklist = owner_decision.get("review_checklist") or {}
    owner_review_checklist_rows = [[
        html.escape(str(r.get("risk_band", ""))),
        str(r.get("risk_score", 0)),
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("item_id", ""))),
        html.escape(str(r.get("review_mode", ""))),
        html.escape(", ".join(str(x) for x in r.get("recommended_decision_options", []))),
        html.escape(str(r.get("decision_prompt", ""))),
    ] for r in owner_decision.get("review_checklist_items", [])]
    owner_guardrail_validator = owner_decision.get("guardrail_validator") or {}
    owner_guardrail_validator_rows = [[
        html.escape(str(r.get("name", ""))),
        "yes" if r.get("passed") else "no",
        html.escape(str(r.get("severity", ""))),
        html.escape(json.dumps(r.get("evidence", {}), ensure_ascii=False)),
        html.escape(str(r.get("recommendation", ""))),
    ] for r in owner_decision.get("guardrail_validator_checks", [])]
    owner_guardrail_trend = owner_decision.get("guardrail_trend") or {}
    owner_guardrail_trend_current = owner_guardrail_trend.get("current") or {}
    owner_guardrail_trend_delta = owner_guardrail_trend.get("delta_from_previous") or {}
    owner_guardrail_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        str(r.get("check_count", 0)),
        str(r.get("failed_count", 0)),
    ] for r in owner_decision.get("guardrail_trend_recent", [])]
    owner_guardrail_coverage = owner_decision.get("guardrail_coverage") or {}
    owner_guardrail_coverage_rows = [[
        html.escape(str(r.get("action", ""))),
        str(r.get("blocking_decision_count", 0)),
        html.escape(str(r.get("coverage_status", ""))),
        html.escape(", ".join(str(x) for x in r.get("expected_checks", []))),
        html.escape(", ".join(str(x) for x in r.get("present_checks", []))),
        html.escape(", ".join(str(x) for x in r.get("failed_checks", []))),
    ] for r in owner_decision.get("guardrail_coverage_rows", [])]
    owner_guardrail_coverage_trend = owner_decision.get("guardrail_coverage_trend") or {}
    owner_guardrail_coverage_trend_current = owner_guardrail_coverage_trend.get("current") or {}
    owner_guardrail_coverage_trend_delta = owner_guardrail_coverage_trend.get("delta_from_previous") or {}
    owner_guardrail_coverage_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        str(r.get("action_count", 0)),
        str(r.get("uncovered_count", 0)),
    ] for r in owner_decision.get("guardrail_coverage_trend_recent", [])]
    owner_governance_health = owner_decision.get("governance_health") or {}
    owner_governance_health_rows = [[
        html.escape(str(r.get("name", ""))),
        "yes" if r.get("passed") else "no",
        html.escape(str(r.get("severity", ""))),
        html.escape(json.dumps(r.get("evidence", {}), ensure_ascii=False)),
        html.escape(str(r.get("recommendation", ""))),
    ] for r in owner_decision.get("governance_health_checks", [])]
    owner_governance_health_trend = owner_decision.get("governance_health_trend") or {}
    owner_governance_health_trend_current = owner_governance_health_trend.get("current") or {}
    owner_governance_health_trend_delta = owner_governance_health_trend.get("delta_from_previous") or {}
    owner_governance_health_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        str(r.get("check_count", 0)),
        str(r.get("failed_count", 0)),
    ] for r in owner_decision.get("governance_health_trend_recent", [])]
    owner_governance_freshness = owner_decision.get("governance_freshness") or {}
    owner_governance_freshness_rows = [[
        html.escape(str(r.get("name", ""))),
        html.escape(str(r.get("status", ""))),
        "yes" if r.get("fresh") else "no",
        str(r.get("age_hours", "")),
        html.escape(str(r.get("effective_ts", ""))[:19]),
        _link(r.get("path", ""), r.get("filename", "")),
    ] for r in owner_decision.get("governance_freshness_items", [])]
    owner_governance_ops_digest = owner_decision.get("governance_ops_digest") or {}
    owner_governance_ops_digest_health = owner_governance_ops_digest.get("health") or {}
    owner_governance_ops_digest_trend = owner_governance_ops_digest.get("health_trend") or {}
    owner_governance_ops_digest_freshness = owner_governance_ops_digest.get("freshness") or {}
    owner_governance_ops_digest_rows = [[
        html.escape(str(r.get("name", ""))),
        str(r.get("pending_count", 0)),
        str(r.get("approved_pending_count", 0)),
        str(r.get("rejected_count", 0)),
        str(r.get("deferred_count", 0)),
        "yes" if r.get("owner_approval_required") else "no",
        _link(r.get("path", ""), "queue"),
    ] for r in owner_decision.get("governance_ops_digest_queues", [])]
    owner_review_drilldown = owner_decision.get("owner_review_drilldown") or {}
    owner_review_drilldown_queue_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        str(r.get("critical", 0)),
        str(r.get("high", 0)),
        str(r.get("medium", 0)),
        str(r.get("low", 0)),
        str(r.get("total", 0)),
    ] for r in owner_decision.get("owner_review_drilldown_queue_risk", [])]
    owner_review_drilldown_item_rows = [[
        html.escape(str(r.get("risk_level", ""))),
        html.escape(str(r.get("domain", ""))),
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("subject", ""))),
        html.escape(str(r.get("blocked_action", ""))),
        html.escape(", ".join(str(x) for x in r.get("forbidden_auto_actions", []))),
        _link(r.get("source_path", ""), "source"),
    ] for r in owner_decision.get("owner_review_drilldown_items", [])]
    owner_review_packet_coverage = owner_decision.get("owner_review_packet_coverage") or {}
    owner_review_packet_coverage_rows = [[
        html.escape(str(r.get("item_id", ""))),
        "yes" if (r.get("presence", {}) or {}).get("packet") else "no",
        "yes" if (r.get("presence", {}) or {}).get("summary") else "no",
        "yes" if (r.get("presence", {}) or {}).get("drilldown") else "no",
        html.escape(", ".join(str(x) for x in r.get("conflicts", []))),
    ] for r in owner_decision.get("owner_review_packet_coverage_mismatches", [])]
    owner_review_integrity_manifest = owner_decision.get("owner_review_integrity_manifest") or {}
    owner_review_integrity_manifest_rows = [[
        html.escape(str(r.get("name", ""))),
        "yes" if r.get("exists") else "no",
        str(r.get("size_bytes", 0)),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("schema_version", ""))),
        html.escape(str(r.get("sha256", ""))[:16]),
        _link(r.get("path", ""), r.get("filename", "")),
    ] for r in owner_decision.get("owner_review_integrity_manifest_artifacts", [])]
    owner_review_integrity_trend = owner_decision.get("owner_review_integrity_trend") or {}
    owner_review_integrity_trend_current = owner_review_integrity_trend.get("current") or {}
    owner_review_integrity_trend_delta = owner_review_integrity_trend.get("delta_from_previous") or {}
    owner_review_integrity_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        str(r.get("artifact_count", 0)),
        str(r.get("present_count", 0)),
        str(r.get("missing_count", 0)),
    ] for r in owner_decision.get("owner_review_integrity_trend_recent", [])]
    owner_review_readiness_checklist = owner_decision.get("owner_review_readiness_checklist") or {}
    owner_review_readiness_rows = [[
        html.escape(str(r.get("name", ""))),
        "yes" if r.get("passed") else "no",
        html.escape(str(r.get("severity", ""))),
        html.escape(json.dumps(r.get("evidence", {}), ensure_ascii=False)),
        html.escape(str(r.get("next_action", ""))),
    ] for r in owner_decision.get("owner_review_readiness_checks", [])]
    owner_review_readiness_trend = owner_decision.get("owner_review_readiness_trend") or {}
    owner_review_readiness_trend_current = owner_review_readiness_trend.get("current") or {}
    owner_review_readiness_trend_delta = owner_review_readiness_trend.get("delta_from_previous") or {}
    owner_review_readiness_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        str(r.get("check_count", 0)),
        str(r.get("failed_count", 0)),
        str(r.get("critical_failed_count", 0)),
    ] for r in owner_decision.get("owner_review_readiness_trend_recent", [])]
    owner_review_queue_aging = owner_decision.get("owner_review_queue_aging") or {}
    owner_review_queue_aging_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("aging_status", ""))),
        str(r.get("pending_count", 0)),
        str(r.get("item_count", 0)),
        str(r.get("max_age_hours", "")),
        str(r.get("watch_count", 0)),
        str(r.get("stale_count", 0)),
        str(r.get("unknown_age_count", 0)),
        html.escape(str(r.get("oldest_item_id", ""))),
        html.escape(str(r.get("recommendation", ""))),
    ] for r in owner_decision.get("owner_review_queue_aging_rows", [])]
    owner_review_queue_aging_trend = owner_decision.get("owner_review_queue_aging_trend") or {}
    owner_review_queue_aging_trend_current = owner_review_queue_aging_trend.get("current") or {}
    owner_review_queue_aging_trend_delta = owner_review_queue_aging_trend.get("delta_from_previous") or {}
    owner_review_queue_aging_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        str(r.get("queue_count", 0)),
        str(r.get("stale_queue_count", 0)),
        str(r.get("watch_queue_count", 0)),
        str(r.get("unknown_age_queue_count", 0)),
    ] for r in owner_decision.get("owner_review_queue_aging_trend_recent", [])]
    owner_review_queue_sla_forecast = owner_decision.get("owner_review_queue_sla_forecast") or {}
    owner_review_queue_sla_forecast_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("forecast_band", ""))),
        str(r.get("pending_count", 0)),
        str(r.get("item_count", 0)),
        str(r.get("max_age_hours", "")),
        str(r.get("min_hours_to_watch", "")),
        str(r.get("min_hours_to_stale", "")),
        str(r.get("unknown_age_count", 0)),
        html.escape(str(r.get("oldest_item_id", ""))),
        html.escape(str(r.get("recommendation", ""))),
    ] for r in owner_decision.get("owner_review_queue_sla_forecasts", [])]
    owner_review_queue_sla_forecast_trend = owner_decision.get("owner_review_queue_sla_forecast_trend") or {}
    owner_review_queue_sla_forecast_trend_current = owner_review_queue_sla_forecast_trend.get("current") or {}
    owner_review_queue_sla_forecast_trend_delta = owner_review_queue_sla_forecast_trend.get("delta_from_previous") or {}
    owner_review_queue_sla_forecast_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        str(r.get("queue_count", 0)),
        str(r.get("attention_queue_count", 0)),
        html.escape(json.dumps(r.get("band_counts", {}), ensure_ascii=False)),
    ] for r in owner_decision.get("owner_review_queue_sla_forecast_trend_recent", [])]
    owner_review_next_action_preview = owner_decision.get("owner_review_next_action_preview") or {}
    owner_review_next_action_preview_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("review_mode", ""))),
        str(r.get("preview_rank_score", 0)),
        str(r.get("pending_count", 0)),
        html.escape(str(r.get("top_priority_band", ""))),
        html.escape(str(r.get("forecast_band", ""))),
        str(r.get("min_hours_to_watch", "")),
        html.escape(str(r.get("top_item_id", ""))),
        html.escape(str(r.get("owner_action", ""))),
        html.escape(", ".join(str(x) for x in r.get("forbidden_auto_actions", []))),
    ] for r in owner_decision.get("owner_review_next_action_preview_rows", [])]
    owner_review_next_action_trend = owner_decision.get("owner_review_next_action_trend") or {}
    owner_review_next_action_trend_current = owner_review_next_action_trend.get("current") or {}
    owner_review_next_action_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        str(r.get("queue_count", 0)),
        html.escape(str(r.get("next_queue_id", ""))),
        html.escape(str(r.get("next_review_mode", ""))),
    ] for r in owner_decision.get("owner_review_next_action_trend_recent", [])]
    owner_review_action_brief = owner_decision.get("owner_review_action_brief") or {}
    owner_review_action_brief_trend = owner_decision.get("owner_review_action_brief_trend") or {}
    owner_review_action_brief_trend_current = owner_review_action_brief_trend.get("current") or {}
    owner_review_action_brief_trend_rows = [[
        html.escape(str(r.get("ts", ""))[:19]),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("item_id", ""))),
        html.escape(str(r.get("review_mode", ""))),
    ] for r in owner_decision.get("owner_review_action_brief_trend_recent", [])]
    owner_review_packet_diff = owner_decision.get("owner_review_packet_diff") or {}
    owner_review_packet_diff_rows = [[
        html.escape(str(r.get("severity", ""))),
        html.escape(str(r.get("kind", ""))),
        html.escape(str(r.get("field", ""))),
        html.escape(str(r.get("message", ""))),
        html.escape(str(r.get("right_source", ""))),
    ] for r in owner_decision.get("owner_review_packet_diff_findings", [])]
    owner_review_decision_simulator = owner_decision.get("owner_review_decision_simulator") or {}
    owner_review_decision_simulator_rows = [[
        html.escape(str(r.get("option", ""))),
        html.escape(str(r.get("decision_kind", ""))),
        html.escape(str(r.get("item_id", ""))),
        html.escape(str(r.get("current_counts", {}))),
        html.escape(str(r.get("simulated_counts", {}))),
        html.escape(", ".join(str(x) for x in r.get("follow_up_required", []))),
    ] for r in owner_decision.get("owner_review_decision_simulations", [])]
    owner_review_decision_impact_trend = owner_decision.get("owner_review_decision_impact_trend") or {}
    owner_review_decision_impact_trend_current = owner_review_decision_impact_trend.get("current") or {}
    owner_review_decision_impact_rows = [[
        html.escape(str(r.get("option", ""))),
        html.escape(str(r.get("decision_kind", ""))),
        html.escape(str(r.get("delta", {}))),
        str(r.get("would_write_decision_record", False)).lower(),
        str(r.get("would_trigger_api_call", False)).lower(),
        str(r.get("would_activate_provider", False)).lower(),
        str(r.get("would_switch_routing", False)).lower(),
    ] for r in owner_decision.get("owner_review_decision_impact_rows", [])]
    owner_review_blocker_digest = owner_decision.get("owner_review_blocker_digest") or {}
    owner_review_blocker_digest_context = owner_review_blocker_digest.get("current_dry_run_context") or {}
    owner_review_blocker_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("domain", ""))),
        html.escape(str(r.get("priority_band", ""))),
        html.escape(str(r.get("item_id", ""))),
        html.escape(str(r.get("subject", ""))),
        html.escape(str(r.get("owner_action", ""))),
        html.escape(", ".join(str(x) for x in r.get("forbidden_auto_actions", []))),
    ] for r in owner_decision.get("owner_review_blocker_digest_top_blockers", [])]
    owner_review_blocker_action_rows = [[
        html.escape(str(index + 1)),
        html.escape(str(action)),
    ] for index, action in enumerate(owner_decision.get("owner_review_blocker_digest_next_actions", []))]
    owner_review_blocker_digest_trend = owner_decision.get("owner_review_blocker_digest_trend") or {}
    owner_review_blocker_digest_trend_current = owner_review_blocker_digest_trend.get("current") or {}
    owner_review_blocker_digest_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("total_blockers", 0)),
        str(r.get("p0_blockers", 0)),
        str(r.get("batch_blockers", 0)),
        str(r.get("forbidden_auto_action_count", 0)),
    ] for r in owner_decision.get("owner_review_blocker_digest_trend_recent", [])]
    owner_review_blocker_guardrail_matrix = owner_decision.get("owner_review_blocker_guardrail_matrix") or {}
    owner_review_blocker_guardrail_queue_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        str(r.get("item_count", 0)),
        str(r.get("distinct_forbidden_action_count", 0)),
        html.escape(json.dumps(r.get("action_counts", {}), ensure_ascii=False)),
    ] for r in owner_decision.get("owner_review_blocker_guardrail_matrix_queues", [])]
    owner_review_blocker_guardrail_action_rows = [[
        html.escape(str(r.get("action", ""))),
        html.escape(str(r.get("severity", ""))),
        str(r.get("total_count", 0)),
        html.escape(json.dumps(r.get("queue_counts", {}), ensure_ascii=False)),
        html.escape(json.dumps(r.get("priority_band_counts", {}), ensure_ascii=False)),
    ] for r in owner_decision.get("owner_review_blocker_guardrail_matrix_actions", [])]
    owner_review_blocker_guardrail_matrix_trend = owner_decision.get("owner_review_blocker_guardrail_matrix_trend") or {}
    owner_review_blocker_guardrail_matrix_trend_current = owner_review_blocker_guardrail_matrix_trend.get("current") or {}
    owner_review_blocker_guardrail_matrix_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("source_item_count", 0)),
        str(r.get("queue_count", 0)),
        str(r.get("forbidden_action_count", 0)),
        str(r.get("p0_guardrail_action_count", 0)),
    ] for r in owner_decision.get("owner_review_blocker_guardrail_matrix_trend_recent", [])]
    owner_review_guardrail_action_drilldown = owner_decision.get("owner_review_guardrail_action_drilldown") or {}
    owner_review_guardrail_action_rows = [[
        html.escape(str(r.get("action", ""))),
        html.escape(str(r.get("severity", ""))),
        str(r.get("item_count", 0)),
        str(r.get("queue_count", 0)),
        html.escape(json.dumps(r.get("queue_counts", {}), ensure_ascii=False)),
        html.escape(json.dumps(r.get("priority_band_counts", {}), ensure_ascii=False)),
    ] for r in owner_decision.get("owner_review_guardrail_action_drilldown_actions", [])]
    owner_review_guardrail_affected_rows = []
    for action in owner_decision.get("owner_review_guardrail_action_drilldown_top_actions", []):
        for item in (action.get("affected_items", []) or [])[:3]:
            owner_review_guardrail_affected_rows.append([
                html.escape(str(action.get("action", ""))),
                html.escape(str(action.get("severity", ""))),
                html.escape(str(item.get("queue_id", ""))),
                html.escape(str(item.get("priority_band", ""))),
                html.escape(str(item.get("item_id", ""))),
                html.escape(str(item.get("subject", ""))),
                html.escape(str(item.get("owner_action", ""))),
            ])
    owner_review_guardrail_action_drilldown_trend = owner_decision.get("owner_review_guardrail_action_drilldown_trend") or {}
    owner_review_guardrail_action_drilldown_trend_current = owner_review_guardrail_action_drilldown_trend.get("current") or {}
    owner_review_guardrail_action_drilldown_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("source_item_count", 0)),
        str(r.get("forbidden_action_count", 0)),
        str(r.get("p0_guardrail_action_count", 0)),
    ] for r in owner_decision.get("owner_review_guardrail_action_drilldown_trend_recent", [])]
    owner_review_action_dependency_index = owner_decision.get("owner_review_action_dependency_index") or {}
    owner_review_action_dependency_rows = [[
        str(r.get("review_order", 0)),
        html.escape(str(r.get("action", ""))),
        html.escape(str(r.get("severity", ""))),
        str(r.get("item_count", 0)),
        str(r.get("queue_count", 0)),
        html.escape(", ".join(str(x) for x in r.get("guardrails", []))),
        "yes" if r.get("owner_gate_required") else "no",
        "yes" if r.get("automation_allowed") else "no",
    ] for r in owner_decision.get("owner_review_action_dependency_index_rows", [])]
    owner_review_action_dependency_queue_rows = []
    for action in owner_decision.get("owner_review_action_dependency_index_rows", [])[:8]:
        for queue in (action.get("queue_dependencies", []) or [])[:4]:
            owner_review_action_dependency_queue_rows.append([
                html.escape(str(action.get("action", ""))),
                html.escape(str(queue.get("queue_id", ""))),
                str(queue.get("item_count", 0)),
                html.escape(json.dumps(queue.get("domain_counts", {}), ensure_ascii=False)),
                html.escape(json.dumps(queue.get("priority_band_counts", {}), ensure_ascii=False)),
                "yes" if queue.get("matched_queue_guardrail") else "no",
            ])
    owner_review_action_dependency_trend = owner_decision.get("owner_review_action_dependency_trend") or {}
    owner_review_action_dependency_trend_current = owner_review_action_dependency_trend.get("current") or {}
    owner_review_action_dependency_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("source_action_count", 0)),
        str(r.get("source_item_count", 0)),
        str(r.get("p0_action_count", 0)),
    ] for r in owner_decision.get("owner_review_action_dependency_trend_recent", [])]
    owner_review_action_dependency_coverage = owner_decision.get("owner_review_action_dependency_coverage") or {}
    owner_review_action_dependency_coverage_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("domain", ""))),
        "yes" if r.get("queue_exists") else "no",
        str(r.get("pending_count", 0)),
        "yes" if r.get("covered") else "no",
        html.escape(", ".join(str(x) for x in r.get("covered_actions", []))),
        html.escape(", ".join(str(x) for x in r.get("missing_actions", []))),
        "yes" if r.get("automation_blocked") else "no",
        "yes" if r.get("owner_gate_present") else "no",
    ] for r in owner_decision.get("owner_review_action_dependency_coverage_queues", [])]
    owner_review_action_dependency_coverage_trend = owner_decision.get("owner_review_action_dependency_coverage_trend") or {}
    owner_review_action_dependency_coverage_trend_current = owner_review_action_dependency_coverage_trend.get("current") or {}
    owner_review_action_dependency_coverage_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("queue_count", 0)),
        str(r.get("covered_queue_count", 0)),
        str(r.get("uncovered_queue_count", 0)),
        str(r.get("pending_item_count", 0)),
    ] for r in owner_decision.get("owner_review_action_dependency_coverage_trend_recent", [])]
    owner_review_coverage_sla_consistency = owner_decision.get("owner_review_coverage_sla_consistency") or {}
    owner_review_coverage_sla_consistency_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("domain", ""))),
        str(r.get("coverage_pending_count", 0)),
        str(r.get("aging_pending_count", "")),
        str(r.get("sla_pending_count", "")),
        html.escape(str(r.get("aging_status", ""))),
        html.escape(str(r.get("forecast_band", ""))),
        "yes" if r.get("consistent") else "no",
    ] for r in owner_decision.get("owner_review_coverage_sla_consistency_rows", [])]
    owner_review_coverage_sla_consistency_trend = owner_decision.get("owner_review_coverage_sla_consistency_trend") or {}
    owner_review_coverage_sla_consistency_trend_current = owner_review_coverage_sla_consistency_trend.get("current") or {}
    owner_review_coverage_sla_consistency_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("queue_count", 0)),
        str(r.get("consistent_queue_count", 0)),
        str(r.get("inconsistent_queue_count", 0)),
        str(r.get("pending_mismatch_count", 0)),
    ] for r in owner_decision.get("owner_review_coverage_sla_consistency_trend_recent", [])]
    owner_pending_decision_freeze_guard = owner_decision.get("owner_pending_decision_freeze_guard") or {}
    owner_pending_decision_freeze_guard_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        html.escape(str(r.get("domain", ""))),
        str(r.get("pending_count", 0)),
        str(r.get("queue_count", 0)),
        "yes" if r.get("frozen") else "no",
        html.escape(", ".join(k for k, v in (r.get("checks") or {}).items() if not v)),
    ] for r in owner_decision.get("owner_pending_decision_freeze_guard_queues", [])]
    owner_pending_decision_freeze_guard_file_rows = [[
        html.escape(str(r.get("decision_file_id", ""))),
        "yes" if r.get("exists") else "no",
        "yes" if r.get("must_be_absent_for_freeze") else "no",
    ] for r in owner_decision.get("owner_pending_decision_freeze_guard_files", [])]
    owner_pending_decision_freeze_guard_trend = owner_decision.get("owner_pending_decision_freeze_guard_trend") or {}
    owner_pending_decision_freeze_guard_trend_current = owner_pending_decision_freeze_guard_trend.get("current") or {}
    owner_pending_decision_freeze_guard_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("pending_total", 0)),
        str(r.get("frozen_queue_count", 0)),
        str(r.get("unfrozen_queue_count", 0)),
        str(r.get("decision_file_present_count", 0)),
        "yes" if r.get("coverage_sla_consistency_trend_stable") else "no",
    ] for r in owner_decision.get("owner_pending_decision_freeze_guard_trend_recent", [])]
    owner_review_packet_freshness_cross_check = owner_decision.get("owner_review_packet_freshness_cross_check") or {}
    owner_review_packet_freshness_item_counts = owner_review_packet_freshness_cross_check.get("item_counts") or {}
    owner_review_packet_freshness_queue_counts = owner_review_packet_freshness_cross_check.get("queue_counts") or {}
    owner_review_packet_freshness_failed_checks = [
        key for key, value in (owner_review_packet_freshness_cross_check.get("checks") or {}).items() if not value
    ]
    owner_review_packet_freshness_failed_guard_checks = [
        key for key, value in (owner_review_packet_freshness_cross_check.get("guard_checks") or {}).items() if not value
    ]
    owner_review_packet_freshness_rows = [[
        html.escape(str(r.get("artifact_id", ""))),
        "yes" if r.get("exists") else "no",
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("generated", ""))),
        html.escape(str(r.get("schema_version", ""))),
    ] for r in owner_decision.get("owner_review_packet_freshness_cross_check_artifacts", [])]
    owner_review_packet_freshness_trend = owner_decision.get("owner_review_packet_freshness_trend") or {}
    owner_review_packet_freshness_trend_current = owner_review_packet_freshness_trend.get("current") or {}
    owner_review_packet_freshness_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("generated_skew_seconds", 0)),
        str(r.get("packet_review_item_count", 0)),
        str(r.get("freeze_pending_total", 0)),
        str(r.get("packet_group_count", 0)),
        str(r.get("freeze_queue_count", 0)),
        str(r.get("failed_check_count", 0)),
        str(r.get("failed_guard_check_count", 0)),
    ] for r in owner_decision.get("owner_review_packet_freshness_trend_recent", [])]
    owner_review_evidence_manifest_v70 = owner_decision.get("owner_review_evidence_manifest") or {}
    owner_review_evidence_manifest_failed_checks = [
        key for key, value in (owner_review_evidence_manifest_v70.get("checks") or {}).items() if not value
    ]
    owner_review_evidence_manifest_rows = [[
        html.escape(str(r.get("artifact_id", ""))),
        "yes" if r.get("exists") else "no",
        str(r.get("size_bytes", 0)),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("generated", ""))),
        html.escape(str(r.get("sha256", ""))[:16]),
    ] for r in owner_decision.get("owner_review_evidence_manifest_artifacts_v70", [])]
    owner_review_evidence_manifest_trend = owner_decision.get("owner_review_evidence_manifest_trend") or {}
    owner_review_evidence_manifest_trend_current = owner_review_evidence_manifest_trend.get("current") or {}
    owner_review_evidence_manifest_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("artifact_count", 0)),
        str(r.get("missing_count", 0)),
        str(r.get("empty_count", 0)),
        str(r.get("duplicate_hash_group_count", 0)),
        html.escape(str(r.get("manifest_digest", ""))[:16]),
    ] for r in owner_decision.get("owner_review_evidence_manifest_trend_recent", [])]
    owner_review_decision_readiness_seal = owner_decision.get("owner_review_decision_readiness_seal") or {}
    owner_review_decision_readiness_failed_checks = [
        key for key, value in (owner_review_decision_readiness_seal.get("checks") or {}).items() if not value
    ]
    owner_review_decision_readiness_trend_rows = [[
        html.escape(str(r.get("trend_id", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("consecutive_count", 0)),
        str(r.get("min_consecutive_required", 0)),
        str(r.get("transition_count", 0)),
        "yes" if r.get("transition_warning") else "no",
        "yes" if r.get("ready") else "no",
    ] for r in owner_decision.get("owner_review_decision_readiness_seal_trends", [])]
    owner_review_decision_readiness_file_rows = [[
        html.escape(str(r.get("decision_file_id", ""))),
        "yes" if r.get("exists") else "no",
        "yes" if r.get("must_be_absent_for_seal") else "no",
    ] for r in owner_decision.get("owner_review_decision_readiness_seal_files", [])]
    owner_review_decision_readiness_seal_trend = owner_decision.get("owner_review_decision_readiness_seal_trend") or {}
    owner_review_decision_readiness_seal_trend_current = owner_review_decision_readiness_seal_trend.get("current") or {}
    owner_review_decision_readiness_seal_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("pending_total", 0)),
        str(r.get("ready_trend_count", 0)),
        str(r.get("transition_warning_count", 0)),
        str(r.get("decision_file_present_count", 0)),
        str(r.get("failed_check_count", 0)),
    ] for r in owner_decision.get("owner_review_decision_readiness_seal_trend_recent", [])]
    owner_review_decision_readiness_seal_ops_digest = owner_decision.get("owner_review_decision_readiness_seal_ops_digest") or {}
    owner_review_decision_readiness_seal_ops_digest_trend_rows = [[
        html.escape(str(r.get("trend_id", ""))),
        html.escape(str(r.get("status", ""))),
        "yes" if r.get("ready") else "no",
        str(r.get("consecutive_count", 0)),
        str(r.get("transition_count", 0)),
        "yes" if r.get("transition_warning") else "no",
        html.escape(", ".join(r.get("failed_checks", []) or []) or "none"),
    ] for r in owner_decision.get("owner_review_decision_readiness_seal_ops_digest_trends", [])]
    owner_review_decision_readiness_seal_ops_digest_file_rows = [[
        html.escape(str(r.get("decision_file_id", ""))),
        "yes" if r.get("exists") else "no",
        "yes" if r.get("must_be_absent_for_seal") else "no",
        "yes" if r.get("compliant") else "no",
    ] for r in owner_decision.get("owner_review_decision_readiness_seal_ops_digest_files", [])]
    owner_review_dry_run_decision_plan = owner_decision.get("owner_review_dry_run_decision_plan") or {}
    owner_review_dry_run_decision_plan_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        str(r.get("item_count", 0)),
        html.escape(str(r.get("decision_file_required_for_actual_apply", ""))),
        html.escape(", ".join(option.get("option", "") for option in (r.get("recommended_options", []) or [])) or "none"),
        html.escape(", ".join(f"{key}:{value}" for key, value in (r.get("forbidden_auto_action_counts", {}) or {}).items()) or "none"),
        "yes" if r.get("dry_run_only") else "no",
    ] for r in owner_decision.get("owner_review_dry_run_decision_plan_queues", [])]
    owner_review_dry_run_decision_plan_trend = owner_decision.get("owner_review_dry_run_decision_plan_trend") or {}
    owner_review_dry_run_decision_plan_trend_current = owner_review_dry_run_decision_plan_trend.get("current") or {}
    owner_review_dry_run_decision_plan_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("total_items", 0)),
        str(r.get("queue_count", 0)),
        "yes" if r.get("no_decisions_applied") else "no",
    ] for r in owner_decision.get("owner_review_dry_run_decision_plan_trend_recent", [])]
    owner_review_dry_run_decision_plan_coverage = owner_decision.get("owner_review_dry_run_decision_plan_coverage") or {}
    owner_review_dry_run_decision_plan_coverage_rows = [[
        html.escape(str(r.get("queue_id", ""))),
        str(r.get("packet_item_count", 0)),
        str(r.get("packet_group_count", 0)),
        str(r.get("plan_item_count", 0)),
        "yes" if r.get("item_count_match") else "no",
        "yes" if r.get("option_coverage_match") else "no",
        "yes" if r.get("dry_run_only") else "no",
        "yes" if r.get("no_queue_mutation") else "no",
    ] for r in owner_decision.get("owner_review_dry_run_decision_plan_coverage_rows", [])]
    owner_review_dry_run_decision_plan_coverage_trend = owner_decision.get("owner_review_dry_run_decision_plan_coverage_trend") or {}
    owner_review_dry_run_decision_plan_coverage_trend_current = owner_review_dry_run_decision_plan_coverage_trend.get("current") or {}
    owner_review_dry_run_decision_plan_coverage_trend_rows = [[
        html.escape(str(r.get("ts", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("packet_item_count", 0)),
        str(r.get("plan_item_count", 0)),
        str(r.get("failed_check_count", 0)),
    ] for r in owner_decision.get("owner_review_dry_run_decision_plan_coverage_trend_recent", [])]
    knowledge_registry = knowledge_trust.get("registry") or {}
    knowledge_review_packet = knowledge_trust.get("review_packet") or {}
    knowledge_sustained_gate = knowledge_trust.get("sustained_gate") or {}
    knowledge_trusted_queue = knowledge_trust.get("trusted_queue") or {}
    knowledge_paths = knowledge_trust.get("paths") or {}
    knowledge_quarantine_rows = [[
        html.escape(str(r.get("id", ""))),
        html.escape(str(r.get("type", ""))),
        "yes" if r.get("path_exists") else "no",
        html.escape(str(r.get("source_url", ""))),
        html.escape(str(r.get("title", ""))),
    ] for r in knowledge_trust.get("quarantine_items", [])]
    knowledge_review_rows = [[
        html.escape(str(r.get("id", ""))),
        html.escape(str(r.get("source_grade", ""))),
        html.escape(str(r.get("risk_level", ""))),
        html.escape(str(r.get("recommendation", ""))),
        html.escape(", ".join(r.get("failed_checks", []) or []) or "none"),
    ] for r in knowledge_trust.get("review_items", [])]
    knowledge_owner_queue_rows = [[
        html.escape(str(r.get("knowledge_id", ""))),
        html.escape(str(r.get("risk_level", ""))),
        html.escape(str(r.get("source_grade", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(", ".join(r.get("recommended_decision_options", []) or [])),
    ] for r in knowledge_trust.get("owner_queue_items", [])]
    dashboard_profile = dashboard_perf.get("profile") or {}
    dashboard_manifest = dashboard_perf.get("manifest") or {}
    dashboard_cache = dashboard_perf.get("cache") or {}
    dashboard_perf_paths = dashboard_perf.get("paths") or {}
    dashboard_manifest_rows = [[
        html.escape(str(r.get("module", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("present_count", 0)),
        str(r.get("missing_count", 0)),
        str(r.get("total_bytes", 0)),
        "yes" if r.get("cache_observation_only") else "no",
        "yes" if r.get("skip_allowed") else "no",
        html.escape(str(r.get("input_hash", ""))[:12]),
    ] for r in dashboard_perf.get("manifest_modules", [])]
    dashboard_cache_rows = [[
        html.escape(str(r.get("module", ""))),
        html.escape(str(r.get("status", ""))),
        "yes" if r.get("skipped") else "no",
        str(r.get("freshness_age_seconds", "")),
        html.escape(str(r.get("freshness_status", ""))),
        html.escape(str(r.get("reason", ""))),
    ] for r in dashboard_perf.get("cache_modules", [])]
    dashboard_write_steps = dashboard_perf.get("write_steps") or {}
    dashboard_write_step_rows = [[
        html.escape(str(r.get("step", ""))),
        str(r.get("elapsed_ms", 0)),
        html.escape(str(r.get("status", ""))),
    ] for r in dashboard_perf.get("write_step_rows", [])]
    adapter_results = model_adapter.get("results") or {}
    adapter_registry = model_adapter.get("registry") or {}
    harness_plan = model_adapter.get("harness_plan") or {}
    daily_soak = model_adapter.get("daily_soak") or {}
    guardrail_negative_tests = model_adapter.get("guardrail_negative_tests") or {}
    evidence_completeness = model_adapter.get("evidence_completeness") or {}
    sample_plan = model_adapter.get("sample_plan") or {}
    path_consistency = model_adapter.get("path_consistency") or {}
    path_cleanup_review = model_adapter.get("path_cleanup_review") or {}
    canary_queue = model_adapter.get("canary_queue") or {}
    routing_policy = model_adapter.get("routing_policy") or {}
    decision_queue = model_adapter.get("decision_queue") or {}
    contract_tests = model_adapter.get("contract_tests") or {}
    drift_report = model_adapter.get("drift_report") or {}
    incident_queue = model_adapter.get("incident_queue") or {}
    adapter_paths = model_adapter.get("paths") or {}
    provider_rows = [[
        html.escape(str(r.get("display_name", r.get("provider_id", "")))),
        html.escape(str(r.get("provider_id", ""))),
        html.escape(str(r.get("adapter_state", ""))),
        "yes" if r.get("enabled") else "no",
        html.escape(str(r.get("cost_tier", ""))),
        html.escape(str(r.get("risk", ""))),
        html.escape(str(r.get("privacy", ""))),
        html.escape(", ".join(str(x) for x in r.get("purpose", []))),
    ] for r in model_adapter.get("providers", [])]
    harness_rows = [[
        html.escape(str(r.get("display_name", r.get("provider_id", "")))),
        html.escape(str(r.get("adapter_state", ""))),
        "yes" if r.get("dry_run") else "no",
        html.escape(str(r.get("execution_mode", ""))),
        html.escape(str(r.get("blocked_reason", ""))),
    ] for r in model_adapter.get("harness_items", [])]
    canary_rows_model = [[
        html.escape(str(r.get("display_name", r.get("provider_id", "")))),
        html.escape(str(r.get("adapter_state", ""))),
        html.escape(str(r.get("canary_status", ""))),
        str(r.get("current_pass_rate", 0)),
        "yes" if r.get("requires_owner_approval") else "no",
        "yes" if r.get("no_auto_activation") else "no",
        html.escape(str(r.get("reason", ""))),
    ] for r in model_adapter.get("canary_items", [])]
    routing_rows_model = [[
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("recommended_display_name", r.get("recommended_adapter", "")))),
        html.escape(str(r.get("routing_status", ""))),
        str(r.get("pass_rate", 0)),
        str(r.get("evidence_score", 0)),
        "yes" if r.get("requires_owner_approval") else "no",
        "yes" if r.get("auto_switch_allowed") else "no",
        html.escape(str(r.get("reason", ""))),
    ] for r in model_adapter.get("routing_rules", [])]
    decision_rows_model = [[
        html.escape(str(r.get("display_name", r.get("provider_id", "")))),
        html.escape(str(r.get("provider_id", ""))),
        html.escape(str(r.get("status", ""))),
        str(r.get("current_pass_rate", 0)),
        str(r.get("routing_rule_count", 0)),
        html.escape(", ".join(str(x) for x in r.get("recommended_capabilities", []))),
        html.escape(str(r.get("owner_decision", ""))),
        html.escape(str(r.get("decision_reason", ""))),
        "yes" if r.get("no_api_call_on_approval") else "no",
    ] for r in model_adapter.get("decision_items", [])]
    contract_rows = [[
        html.escape(str(r.get("name", ""))),
        "yes" if r.get("passed") else "no",
        html.escape(", ".join(str(x) for x in r.get("missing", []))),
        html.escape(str(r.get("severity", ""))),
    ] for r in model_adapter.get("contract_checks", [])]
    drift_rows = [[
        html.escape(str(r.get("kind", ""))),
        html.escape(str(r.get("severity", ""))),
        html.escape(str(r.get("adapter_id", ""))),
        html.escape(str(r.get("before", ""))),
        html.escape(str(r.get("after", ""))),
        html.escape(str(r.get("delta", ""))),
    ] for r in model_adapter.get("drift_findings", [])]
    incident_rows_model = [[
        html.escape(str(r.get("incident_id", ""))),
        html.escape(str(r.get("kind", ""))),
        html.escape(str(r.get("severity", ""))),
        html.escape(str(r.get("status", ""))),
        html.escape(str(r.get("source", ""))),
        html.escape(str(r.get("summary", ""))),
        html.escape(str(r.get("recommended_action", ""))),
    ] for r in model_adapter.get("incident_items", [])]
    adapter_rows = [[
        html.escape(str(r.get("display_name", r.get("adapter_id", "")))),
        html.escape(str(r.get("adapter_type", ""))),
        html.escape(str(r.get("provider_state", ""))),
        "yes" if r.get("enabled") else "no",
        str(r.get("trajectory_count", 0)),
        str(r.get("pass_rate", 0)),
        str(r.get("avg_score", 0)),
        str(r.get("avg_evidence_score", 0)),
        str(r.get("latency_ms", 0)),
        str(r.get("cost_score", 0)),
        str(r.get("privacy_score", 0)),
        html.escape(", ".join(str(x) for x in r.get("strengths", []))),
    ] for r in model_adapter.get("adapters", [])]
    adapter_recommendation_rows = [[
        replay_cell("by_capability", str(r.get("capability", ""))),
        html.escape(str(r.get("recommended_display_name", r.get("recommended_adapter", "")))),
        str(r.get("pass_rate", 0)),
        str(r.get("evidence_score", 0)),
        html.escape(str(r.get("reason", ""))),
    ] for r in model_adapter.get("recommendations", [])]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Manual Agent OS Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1f2937;
      --muted: #667085;
      --line: #d7dce3;
      --accent: #0f766e;
      --warn: #b45309;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--ink); }}
    header {{ padding: 24px 32px 18px; background: #102a43; color: white; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    header p {{ margin: 0; color: #c9d6e2; }}
    main {{ padding: 24px 32px 40px; max-width: 1440px; margin: 0 auto; }}
    .metrics {{ display: grid; grid-template-columns: repeat(5, minmax(140px, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .metric {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    .metric strong {{ display: block; font-size: 26px; margin-bottom: 4px; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; margin: 14px 0; overflow: auto; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 680px; }}
    th, td {{ border-bottom: 1px solid var(--line); text-align: left; padding: 9px 10px; font-size: 13px; vertical-align: top; }}
    th {{ color: #344054; background: #f9fafb; position: sticky; top: 0; }}
    td {{ color: #263238; }}
    .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .badge {{ display: inline-block; padding: 2px 7px; border-radius: 999px; background: #e6fffb; color: var(--accent); border: 1px solid #99f6e4; }}
    .live {{ display: grid; grid-template-columns: repeat(4, minmax(130px, 1fr)); gap: 10px; }}
    .live div {{ border: 1px solid var(--line); border-radius: 8px; padding: 10px; background: #fbfcfd; }}
    .live strong {{ display: block; font-size: 22px; }}
    @media (max-width: 900px) {{ .metrics, .grid2 {{ grid-template-columns: 1fr; }} main, header {{ padding-left: 16px; padding-right: 16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Manual Agent OS Dashboard</h1>
    <p>Generated {html.escape(data["generated"])} · {_link(data["root"], "workspace")}</p>
  </header>
  <main>
    <div class="metrics">
      <div class="metric"><strong>{len(mcps)}</strong><span>MCP modules</span></div>
      <div class="metric"><strong>{len(projects)}</strong><span>manual-gates projects</span></div>
      <div class="metric"><strong>{passed_projects}</strong><span>fully passed projects</span></div>
      <div class="metric"><strong>{evidence["memory_records"]}</strong><span>memory records</span></div>
      <div class="metric"><strong>{runtime.get("run_count", 0)}</strong><span>Agent OS runs</span></div>
    </div>
    <div class="metrics">
      <div class="metric"><strong>{len(runtime.get("blocked_runs", []))}</strong><span>failed / blocked runs</span></div>
      <div class="metric"><strong>{len(runtime.get("retry_runs", []))}</strong><span>retry runs</span></div>
      <div class="metric"><strong>{len(runtime.get("completion_failures", []))}</strong><span>completion failures</span></div>
      <div class="metric"><strong>{len(runtime.get("memory_writes", []))}</strong><span>recent memory writes</span></div>
      <div class="metric"><strong>{runtime.get("task_card_count", 0)}</strong><span>task cards</span></div>
    </div>
    <section><h2>Agent OS Runtime</h2>
      <p><span class="badge">task cards</span> {runtime.get("task_card_count", 0)} · <span class="badge">snapshot</span> {"exists" if runtime.get("snapshot_exists") else "missing"} · {_link(runtime.get("snapshot_path", ""), "control_snapshot.json")}</p>
      {_table(["Project", "Run", "Phase", "Status", "Decision", "Node", "File"], runstate_rows or [["None", "", "", "", "", "", ""]])}
    </section>
    <div class="grid2">
      <section><h2>MCP Lifecycle Registry</h2>
        <p>{_link(str(registry.get("mcp", {}).get("generated", "")), "generated")} · {_link(registry.get("policy_path", ""), "policy")}</p>
        {_table(["Status", "Count"], mcp_lifecycle_rows or [["None", "0"]])}
      </section>
      <section><h2>Skill Lifecycle Registry</h2>
        <p>{_link(registry.get("policy_path", ""), "policy")}</p>
        {_table(["Status", "Count"], skill_lifecycle_rows or [["None", "0"]])}
      </section>
    </div>
    <section><h2>Daily Soak Report</h2>
      <p><span class="badge">runs</span> {soak.get("run_count", 0)} · <span class="badge">completion rejects</span> {soak.get("completion_verifier_rejects", 0)} · <span class="badge">memory writes</span> {soak.get("memory_write_count", 0)} · {_link(stability_paths.get("soak_md", ""), "soak report")}</p>
      <p><span class="badge">expected fail-closed</span> {soak.get("expected_fail_closed", 0)} · <span class="badge">unexpected failed</span> {soak.get("unexpected_failed", 0)} · <span class="badge">unexpected blocked</span> {soak.get("unexpected_blocked", 0)}</p>
      <p><span class="badge">status</span> {html.escape(json.dumps(soak.get("status_counts", {}), ensure_ascii=False))}</p>
      <p><span class="badge">advice</span> {html.escape(json.dumps(soak.get("promotion_recommendations", {}), ensure_ascii=False))}</p>
      <p><span class="badge">sanitizer</span> {html.escape(str(l4_soak_sanitizer.get("status", "")))} · <span class="badge">illegal controls</span> {l4_soak_sanitizer.get("illegal_control_count", 0)} · <span class="badge">canonical</span> {str(l4_soak_sanitizer.get("canonical_written", True)).lower()} · {_link(stability_paths.get("l4_soak_sanitizer", ""), "sanitizer json")} · {_link(stability_paths.get("l4_soak_sanitizer_audit", ""), "audit")}</p>
      <p><span class="badge">matrix</span> {html.escape(str(l4_soak_matrix.get("status", "")))} · <span class="badge">passed days</span> {l4_soak_matrix.get("passed_days", 0)}/{l4_soak_matrix.get("soak_days_required", 0)} · <span class="badge">blocked</span> {len(l4_soak_matrix.get("blocked_reasons", []) or [])} · {_link(stability_paths.get("l4_soak_matrix", ""), "matrix json")} · {_link(stability_paths.get("l4_soak_matrix_md", ""), "matrix md")} · {_link(stability_paths.get("l4_soak_matrix_audit", ""), "audit")}</p>
    </section>
    <section><h2>Promotion / Demotion Advice</h2>{_table(["Capability", "Type", "Current", "Recommendation", "Calls", "Raw Success", "Operational Success", "Expected Fail-Closed", "Reason"], advice_rows or [["None", "", "", "", "0", "0", "0", "0", ""]])}</section>
    <section><h2>Capability Success Rates</h2>{_table(["Capability", "Calls", "Completed", "Unexpected Failed", "Unexpected Blocked", "Retry", "Expected Fail-Closed", "Raw Success", "Operational Success", "Last Failure Reason"], capability_rows or [["None", "0", "0", "0", "0", "0", "0", "0", "0", ""]])}</section>
    <section><h2>Shadow Runs</h2>
      <p><span class="badge">runs</span> {(shadow.get("summary") or {}).get("run_count", 0)} · {_link((shadow.get("paths") or {}).get("summary", ""), "shadow_summary.json")}</p>
      {_table(["Shadow Run", "Capability", "Task Card", "Result", "Promotion Signal", "Findings", "File"], shadow_rows or [["None", "", "", "", "", "0", ""]])}
    </section>
    <section><h2>Shadow Scoring</h2>
      <p><span class="badge">no auto promotion</span> {str((shadow.get("scoring") or {}).get("no_auto_promotion_guard", True)).lower()} · {_link((shadow.get("paths") or {}).get("scoring", ""), "promotion_scoring.json")} · {_link((shadow.get("paths") or {}).get("eval_summary", ""), "shadow_eval_summary.json")}</p>
      {_table(["Capability", "Runs", "Agreement", "Warn Rate", "False Positive", "Evidence", "Recommendation", "Reason", "Latest"], shadow_score_rows or [["None", "0", "0", "0", "0", "0", "", "", ""]])}
    </section>
    <div class="grid2">
      <section><h2>Promotion Readiness</h2>{_table(["Capability", "Runs", "Agreement", "Evidence", "Reason", "Latest"], shadow_readiness_rows or [["None", "0", "0", "0", "", ""]])}</section>
      <section><h2>Evidence Completeness</h2><p><span class="badge">eval cases</span> {(shadow.get("eval_summary") or {}).get("case_count", 0)} · <span class="badge">shadow records</span> {(shadow.get("eval_summary") or {}).get("shadow_record_count", 0)} · <span class="badge">guard</span> {str((shadow.get("eval_summary") or {}).get("no_auto_promotion_guard", True)).lower()}</p></section>
    </div>
    <section><h2>Promotion Review Gate</h2>
      <p><span class="badge">pending</span> {(promotion_review.get("queue") or {}).get("pending_count", 0)} · <span class="badge">approved pending apply</span> {(promotion_review.get("queue") or {}).get("approved_pending_apply_count", 0)} · <span class="badge">no auto promotion</span> {str((promotion_review.get("queue") or {}).get("no_auto_promotion_guard", True)).lower()} · {_link((promotion_review.get("paths") or {}).get("queue", ""), "promotion_review_queue.json")} · {_link((promotion_review.get("paths") or {}).get("audit", ""), "audit")}</p>
      {_table(["Review", "Capability", "Type", "Current", "Target", "Status", "Decision", "Reason", "Registry"], review_rows or [["None", "", "", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Investment Eval Dashboard</h2>
      <p><span class="badge">cases</span> {investment_summary.get("passed_cases", 0)}/{investment_summary.get("total_cases", 0)} бд <span class="badge">A-share</span> {investment_summary.get("a_share_passed", 0)}/{investment_summary.get("a_share_total", 0)} бд <span class="badge">degrade</span> {investment_summary.get("degrade_passed", 0)}/{investment_summary.get("degrade_total", 0)} бд <span class="badge">promotion ready</span> {str(investment_summary.get("promotion_ready", False)).lower()} բд <span class="badge">owner review required</span> {str(investment_eval.get("owner_review_required", False)).lower()} բд {_link((investment_eval.get("paths") or {}).get("dashboard_json", ""), "eval_dashboard.json")} бд {_link((investment_eval.get("paths") or {}).get("review_packet_json", ""), "review_packet.json")}</p>
      {_table(["Skill", "Status", "Lifecycle", "Owner Override"], investment_target_rows or [["None", "", "", ""]])}
      {_table(["Case", "Target", "Type", "Verdict", "Passed", "Failure"], investment_case_rows or [["None", "", "", "", "", ""]])}
      {_table(["Skill", "Current Lifecycle", "Queue Status", "Recommended Action", "Owner Decision"], investment_queue_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Approved Pending Apply</h2>{_table(["Capability", "Status", "Owner", "Reason", "Registry"], review_apply_rows or [["None", "", "", "", ""]])}</section>
    <section><h2>Active Canary</h2>
      <p><span class="badge">capabilities</span> {(active_canary.get("status") or {}).get("capability_count", 0)} · <span class="badge">canary pass</span> {(active_canary.get("status") or {}).get("canary_pass_count", 0)} · <span class="badge">rollback candidates</span> {(active_canary.get("status") or {}).get("rollback_candidate_count", 0)} · {_link((active_canary.get("paths") or {}).get("status", ""), "canary_status.json")} · {_link((active_canary.get("paths") or {}).get("runs", ""), "canary_runs.jsonl")}</p>
      {_table(["Capability", "Registry", "Active Runs", "Success Rate", "Failures", "Verifier Failures", "Canary Status", "Rollback Reason", "Latest Run"], canary_rows or [["None", "", "0", "0", "0", "0", "", "", ""]])}
    </section>
    <div class="grid2">
      <section><h2>Newly Active</h2>{_table(["Capability", "Registry", "Active Runs", "Success Rate", "Failures", "Verifier Failures", "Canary Status", "Rollback Reason", "Latest Run"], canary_rows or [["None", "", "0", "0", "0", "0", "", "", ""]])}</section>
      <section><h2>Rollback Candidates</h2>{_table(["Capability", "Runs", "Success Rate", "Failures", "Reason"], rollback_rows or [["None", "0", "0", "0", ""]])}</section>
    </div>
    <section><h2>Rollback Review Gate</h2>
      <p><span class="badge">pending</span> {(active_canary.get("rollback_queue") or {}).get("pending_count", 0)} · <span class="badge">approved pending apply</span> {(active_canary.get("rollback_queue") or {}).get("approved_pending_apply_count", 0)} · <span class="badge">no auto rollback</span> {str((active_canary.get("rollback_queue") or {}).get("no_auto_rollback_guard", True)).lower()} · {_link((active_canary.get("paths") or {}).get("rollback_queue", ""), "rollback_review_queue.json")}</p>
      {_table(["Review", "Capability", "Current", "Target", "Status", "Decision", "Reason"], rollback_review_rows or [["None", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Trajectory Schema</h2>
      <p><span class="badge">version</span> {html.escape(str(trajectory_summary.get("trajectory_schema_version", trajectory_summary.get("schema_version", ""))))} · <span class="badge">trajectories</span> {trajectory_summary.get("trajectory_count", 0)} · <span class="badge">replay indexed</span> {trajectory_summary.get("replay_index_count", 0)} · {_link((trajectory.get("paths") or {}).get("jsonl", ""), "trajectories.jsonl")} · {_link((trajectory.get("paths") or {}).get("replay_index", ""), "replay_index.json")}</p>
      {_table(["Source", "Count"], trajectory_rows or [["None", "0"]])}
    </section>
    <div class="grid2">
      <section><h2>Outcome Categories</h2>{_table(["Category", "Count"], trajectory_category_rows or [["None", "0"]])}</section>
      <section><h2>Outcome Labels</h2>{_table(["Label", "Count"], trajectory_label_rows or [["None", "0"]])}</section>
    </div>
    <div class="grid2">
      <section><h2>Legacy Labels</h2>{_table(["v0.1 Label", "Count"], trajectory_legacy_rows or [["None", "0"]])}</section>
      <section><h2>Replay Index</h2>{_table(["Bucket", "Keys"], replay_bucket_rows)}</section>
    </div>
    <section><h2>Replay Diff</h2>
      <p><span class="badge">groups</span> {replay_diff.get("group_count", 0)} · <span class="badge">stable success</span> {replay_diff.get("stable_success_group_count", 0)} · <span class="badge">fail-closed</span> {replay_diff.get("stable_fail_closed_group_count", 0)} · <span class="badge">verifier failures</span> {replay_diff.get("repeat_verifier_failure_group_count", 0)} · <span class="badge">true repeat failures</span> {replay_diff.get("repeat_failure_group_count", 0)} · {_link((trajectory.get("paths") or {}).get("replay_diff", ""), "replay_diff_summary.json")}</p>
      {_table(["Group", "Assessment", "Total", "Success", "Failure", "Fail-Closed", "Shadow Warn", "Operational Fail", "Success Rate", "Top Pattern"], diff_group_rows or [["None", "", "0", "0", "0", "0", "0", "0", "0", ""]])}
    </section>
    <section><h2>Verifier Failure Drilldown v0.7</h2>
      <p><span class="badge">schema</span> {html.escape(str(verifier_drilldown.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(verifier_drilldown.get("status", "")))} / <span class="badge">failures</span> {verifier_drilldown.get("failure_count", 0)} / <span class="badge">trajectories</span> {verifier_drilldown.get("trajectory_count", 0)} / {_link((trajectory.get("paths") or {}).get("verifier_drilldown", ""), "verifier_failure_drilldown.json")} / {_link((trajectory.get("paths") or {}).get("verifier_drilldown_audit", ""), "audit")}</p>
      <p><span class="badge">by task class</span> {html.escape(json.dumps(verifier_drilldown_summary.get("by_task_class", {}), ensure_ascii=False))} / <span class="badge">by capability</span> {html.escape(json.dumps(verifier_drilldown_summary.get("by_capability", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(verifier_drilldown.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(verifier_drilldown.get("no_model_api_calls", True)).lower()} / <span class="badge">no runtime mutation</span> {str(verifier_drilldown.get("no_runtime_mutation", True)).lower()} / <span class="badge">no writeback</span> {str(verifier_drilldown.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Recommendation", "Count"], verifier_recommendation_rows or [["None", "0"]])}
      {_table(["Outcome", "Trajectory", "Class", "Missing Evidence", "Failed Checks", "Recommendation"], verifier_drilldown_rows or [["None", "", "", "", "", ""]])}
    </section>
    <section><h2>Class C Evidence Drilldown v1.1</h2>
      <p><span class="badge">schema</span> {html.escape(str(class_c_drilldown.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(class_c_drilldown.get("status", "")))} / <span class="badge">class C</span> {class_c_drilldown.get("class_c_count", 0)} / <span class="badge">gaps</span> {class_c_drilldown.get("gap_count", 0)} / {_link((trajectory.get("paths") or {}).get("class_c_contract", ""), "class_c_evidence_contract.json")} / {_link((trajectory.get("paths") or {}).get("class_c_drilldown", ""), "class_c_evidence_drilldown.json")} / {_link((trajectory.get("paths") or {}).get("class_c_drilldown_audit", ""), "audit")}</p>
      <p><span class="badge">by contract status</span> {html.escape(json.dumps(class_c_summary.get("by_contract_status", {}), ensure_ascii=False))} / <span class="badge">by capability</span> {html.escape(json.dumps(class_c_summary.get("by_capability", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(class_c_drilldown.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(class_c_drilldown.get("no_model_api_calls", True)).lower()} / <span class="badge">no runtime mutation</span> {str(class_c_drilldown.get("no_runtime_mutation", True)).lower()} / <span class="badge">no writeback</span> {str(class_c_drilldown.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Field", "Count"], class_c_missing_rows or [["None", "0"]])}
      {_table(["Outcome", "Trajectory", "Status", "Missing", "Coverage", "Missing Fields", "Recommendation"], class_c_rows or [["None", "", "", "0", "0", "", ""]])}
    </section>
    <section><h2>Unknown Outcome Resolver v0.8</h2>
      <p><span class="badge">schema</span> {html.escape(str(unknown_resolver.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(unknown_resolver.get("status", "")))} / <span class="badge">unknown</span> {unknown_resolver.get("unknown_count", 0)} / <span class="badge">trajectories</span> {unknown_resolver.get("trajectory_count", 0)} / {_link((trajectory.get("paths") or {}).get("unknown_resolver", ""), "unknown_outcome_resolver.json")} / {_link((trajectory.get("paths") or {}).get("unknown_resolver_audit", ""), "audit")}</p>
      <p><span class="badge">by resolution</span> {html.escape(json.dumps(unknown_resolver_summary.get("by_resolution", {}), ensure_ascii=False))} / <span class="badge">by status</span> {html.escape(json.dumps(unknown_resolver_summary.get("by_status", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(unknown_resolver.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(unknown_resolver.get("no_model_api_calls", True)).lower()} / <span class="badge">no runtime mutation</span> {str(unknown_resolver.get("no_runtime_mutation", True)).lower()} / <span class="badge">no writeback</span> {str(unknown_resolver.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Resolution", "Count"], unknown_resolution_rows or [["None", "0"]])}
      {_table(["Outcome", "Trajectory", "Phase", "Status", "Resolution", "Recommendation"], unknown_resolver_rows or [["None", "", "", "", "", ""]])}
    </section>
    <section><h2>Retry Pattern Drilldown v0.9</h2>
      <p><span class="badge">schema</span> {html.escape(str(retry_drilldown.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(retry_drilldown.get("status", "")))} / <span class="badge">retry</span> {retry_drilldown.get("retry_count", 0)} / <span class="badge">repeat patterns</span> {retry_drilldown.get("repeat_pattern_count", 0)} / {_link((trajectory.get("paths") or {}).get("retry_drilldown", ""), "retry_pattern_drilldown.json")} / {_link((trajectory.get("paths") or {}).get("retry_drilldown_audit", ""), "audit")}</p>
      <p><span class="badge">by reason</span> {html.escape(json.dumps(retry_drilldown_summary.get("by_reason", {}), ensure_ascii=False))} / <span class="badge">by source</span> {html.escape(json.dumps(retry_drilldown_summary.get("by_source", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(retry_drilldown.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(retry_drilldown.get("no_model_api_calls", True)).lower()} / <span class="badge">no runtime mutation</span> {str(retry_drilldown.get("no_runtime_mutation", True)).lower()} / <span class="badge">no writeback</span> {str(retry_drilldown.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Pattern", "Count", "Reason", "Follow-up Success", "Repeated", "Recommendation"], retry_pattern_rows or [["None", "0", "", "0", "", ""]])}
      {_table(["Outcome", "Trajectory", "Class", "Reason", "Source", "Follow-up Success"], retry_drilldown_rows or [["None", "", "", "", "", ""]])}
    </section>
    <section><h2>Retry Recovery Verifier v1.3</h2>
      <p><span class="badge">schema</span> {html.escape(str(retry_recovery.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(retry_recovery.get("status", "")))} / <span class="badge">retry</span> {retry_recovery.get("retry_count", 0)} / <span class="badge">open</span> {retry_recovery.get("open_retry_count", 0)} / <span class="badge">recovered</span> {retry_recovery.get("recovered_count", 0)} / {_link((trajectory.get("paths") or {}).get("retry_recovery_contract", ""), "retry_recovery_contract.json")} / {_link((trajectory.get("paths") or {}).get("retry_recovery", ""), "retry_recovery_verifier.json")} / {_link((trajectory.get("paths") or {}).get("retry_recovery_audit", ""), "audit")}</p>
      <p><span class="badge">by recovery status</span> {html.escape(json.dumps(retry_recovery_summary.get("by_recovery_status", {}), ensure_ascii=False))} / <span class="badge">by capability</span> {html.escape(json.dumps(retry_recovery_summary.get("by_capability", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(retry_recovery.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(retry_recovery.get("no_model_api_calls", True)).lower()} / <span class="badge">no runtime mutation</span> {str(retry_recovery.get("no_runtime_mutation", True)).lower()} / <span class="badge">no writeback</span> {str(retry_recovery.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Missing Recovery Field", "Count"], retry_recovery_missing_rows or [["None", "0"]])}
      {_table(["Outcome", "Trajectory", "Recovery", "Follow-ups", "Follow-up Success", "Stable Allowed", "Missing Recovery Fields", "Recommendation"], retry_recovery_rows or [["None", "", "", "0", "0", "", "", ""]])}
    </section>
    <section><h2>Experience Distillation Queue</h2>
      <p><span class="badge">candidates</span> {distillation_queue.get("candidate_count", 0)} 路 <span class="badge">pending</span> {distillation_queue.get("pending_count", 0)} 路 <span class="badge">approved pending writeback</span> {distillation_queue.get("approved_pending_writeback_count", 0)} 路 <span class="badge">rejected</span> {distillation_queue.get("rejected_count", 0)} 路 <span class="badge">deferred</span> {distillation_queue.get("deferred_count", 0)} 路 <span class="badge">no auto writeback</span> {str(distillation_queue.get("no_auto_writeback_guard", True)).lower()} 路 {_link(distillation_paths.get("queue", ""), "experience_distillation_queue.json")} 路 {_link(distillation_paths.get("decisions", ""), "decisions")} 路 {_link(distillation_paths.get("audit", ""), "audit")}</p>
      {_table(["Candidate", "Type", "Target", "Priority", "Status", "Source Assessment", "Lesson", "Suggested Action"], distillation_rows or [["None", "", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Summary v2.0</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_report.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_report.get("status", "")))} 路 <span class="badge">pending</span> {owner_report.get("pending_count", 0)} 路 <span class="badge">approved pending</span> {owner_report.get("approved_pending_count", 0)} 路 <span class="badge">attention</span> {owner_report.get("attention_item_count", 0)} 路 <span class="badge">read only</span> {str(owner_report.get("read_only_summary", True)).lower()} 路 {_link(owner_paths.get("report", ""), "owner_decision_summary.json")} 路 {_link(owner_paths.get("audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_report.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_report.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_report.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no registry mutation</span> {str(owner_report.get("no_registry_lifecycle_mutation", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_report.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Domain", "Exists", "Items", "Pending", "Approved Pending", "Status Counts", "File"], owner_queue_rows or [["None", "", "", "0", "0", "0", "", ""]])}
      {_table(["Queue", "Domain", "Item", "Subject", "Status", "Owner Action", "Forbidden Auto Actions", "Source"], owner_attention_rows or [["None", "", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Prioritizer v2.1</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_priorities.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_priorities.get("status", "")))} 路 <span class="badge">items</span> {owner_priorities.get("item_count", 0)} 路 <span class="badge">p0</span> {owner_priorities.get("p0_count", 0)} 路 <span class="badge">p1</span> {owner_priorities.get("p1_count", 0)} 路 <span class="badge">p2</span> {owner_priorities.get("p2_count", 0)} 路 <span class="badge">read only</span> {str(owner_priorities.get("read_only_prioritization", True)).lower()} 路 {_link(owner_paths.get("priorities", ""), "owner_decision_priorities.json")} 路 {_link(owner_paths.get("priorities_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_priorities.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_priorities.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_priorities.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no registry mutation</span> {str(owner_priorities.get("no_registry_lifecycle_mutation", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_priorities.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Band", "Score", "Queue", "Item", "Subject", "Owner Action", "Options", "Reason", "Source"], owner_priority_rows or [["None", "0", "", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Packet v2.2</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_packet.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_packet.get("status", "")))} 路 <span class="badge">items</span> {owner_packet.get("review_item_count", 0)} 路 <span class="badge">p0</span> {owner_packet.get("p0_count", 0)} 路 <span class="badge">batch</span> {owner_packet.get("batch_count", 0)} 路 <span class="badge">read only</span> {str(owner_packet.get("read_only_packet", True)).lower()} 路 {_link(owner_paths.get("packet", ""), "owner_review_packet.json")} 路 {_link(owner_paths.get("packet_md", ""), "owner_review_packet.md")} 路 {_link(owner_paths.get("packet_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_packet.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file written</span> {str(owner_packet.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_packet.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_packet.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_packet.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Items", "P0", "P2", "Review Mode", "First Action"], owner_packet_group_rows or [["None", "0", "0", "0", "", ""]])}
      {_table(["Band", "Queue", "Subject", "Decision Prompt", "Options", "Source"], owner_packet_item_rows or [["None", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Consistency v2.3</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_consistency.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_consistency.get("status", "")))} 路 <span class="badge">checks</span> {owner_consistency.get("check_count", 0)} 路 <span class="badge">failed</span> {owner_consistency.get("failed_count", 0)} 路 <span class="badge">critical</span> {owner_consistency.get("critical_count", 0)} 路 <span class="badge">read only</span> {str(owner_consistency.get("read_only_consistency_check", True)).lower()} 路 {_link(owner_paths.get("consistency", ""), "owner_decision_consistency.json")} 路 {_link(owner_paths.get("consistency_audit", ""), "audit")}</p>
      <p><span class="badge">summary</span> {owner_consistency.get("summary_item_count", 0)} 路 <span class="badge">priorities</span> {owner_consistency.get("priority_item_count", 0)} 路 <span class="badge">packet</span> {owner_consistency.get("packet_item_count", 0)} 路 <span class="badge">no decisions applied</span> {str(owner_consistency.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_consistency.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_consistency.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Check", "Passed", "Observed", "Expected", "Severity"], owner_consistency_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Staleness v2.4</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_staleness.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_staleness.get("status", "")))} 路 <span class="badge">items</span> {owner_staleness.get("item_count", 0)} 路 <span class="badge">stale</span> {owner_staleness.get("stale_count", 0)} 路 <span class="badge">watch</span> {owner_staleness.get("watch_count", 0)} 路 <span class="badge">unknown age</span> {owner_staleness.get("unknown_age_count", 0)} 路 <span class="badge">read only</span> {str(owner_staleness.get("read_only_staleness_monitor", True)).lower()} 路 {_link(owner_paths.get("staleness", ""), "owner_decision_staleness.json")} 路 {_link(owner_paths.get("staleness_audit", ""), "audit")}</p>
      <p><span class="badge">p0 stale</span> {owner_staleness.get("p0_stale_count", 0)} 路 <span class="badge">age basis</span> source_queue_generated 路 <span class="badge">no decisions applied</span> {str(owner_staleness.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_staleness.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_staleness.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_staleness.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Staleness", "Age Hours", "Priority", "Queue", "Subject", "Recommendation", "Age Basis", "Source"], owner_staleness_rows or [["None", "", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Trend v2.5</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_trend.get("window_count", 0)} 路 <span class="badge">read only</span> {str(owner_trend.get("read_only_trend_snapshot", True)).lower()} 路 {_link(owner_paths.get("trend", ""), "owner_decision_trend_snapshot.json")} 路 {_link(owner_paths.get("trend_audit", ""), "audit")}</p>
      <p><span class="badge">pending</span> {owner_trend_current.get("pending_count", 0)} ({owner_trend_delta.get("pending_count", 0)}) 路 <span class="badge">p0</span> {owner_trend_current.get("p0_count", 0)} ({owner_trend_delta.get("p0_count", 0)}) 路 <span class="badge">stale</span> {owner_trend_current.get("stale_count", 0)} ({owner_trend_delta.get("stale_count", 0)}) 路 <span class="badge">consistency failed</span> {owner_trend_current.get("consistency_failed_count", 0)} ({owner_trend_delta.get("consistency_failed_count", 0)}) 路 <span class="badge">no decisions applied</span> {str(owner_trend.get("no_decisions_applied", True)).lower()}</p>
      {_table(["TS", "Pending", "P0", "Stale", "Watch", "Delta"], owner_trend_rows or [["None", "0", "0", "0", "0", ""]])}
    </section>
    <section><h2>Owner Decision Dependency Map v2.6</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_dependency.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_dependency.get("status", "")))} 路 <span class="badge">decisions</span> {owner_dependency.get("decision_count", 0)} 路 <span class="badge">blocked actions</span> {owner_dependency.get("blocked_action_count", 0)} 路 <span class="badge">edges</span> {owner_dependency.get("edge_count", 0)} 路 <span class="badge">read only</span> {str(owner_dependency.get("read_only_dependency_map", True)).lower()} 路 {_link(owner_paths.get("dependency", ""), "owner_decision_dependency_map.json")} 路 {_link(owner_paths.get("dependency_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_dependency.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_dependency.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_dependency.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no registry mutation</span> {str(owner_dependency.get("no_registry_lifecycle_mutation", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_dependency.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Action", "Label", "Blocking Decisions", "Top Blockers"], owner_dependency_action_rows or [["None", "", "0", ""]])}
      {_table(["Queue", "Pending Decisions"], owner_dependency_queue_rows or [["None", "0"]])}
    </section>
    <section><h2>Owner Decision Risk Heatmap v2.7</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_risk_heatmap.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_risk_heatmap.get("status", "")))} 路 <span class="badge">items</span> {owner_risk_heatmap.get("item_count", 0)} 路 <span class="badge">critical</span> {owner_risk_heatmap.get("critical_count", 0)} 路 <span class="badge">high</span> {owner_risk_heatmap.get("high_count", 0)} 路 <span class="badge">medium</span> {owner_risk_heatmap.get("medium_count", 0)} 路 <span class="badge">low</span> {owner_risk_heatmap.get("low_count", 0)} 路 <span class="badge">read only</span> {str(owner_risk_heatmap.get("read_only_risk_heatmap", True)).lower()} 路 {_link(owner_paths.get("risk_heatmap", ""), "owner_decision_risk_heatmap.json")} 路 {_link(owner_paths.get("risk_heatmap_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_risk_heatmap.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_risk_heatmap.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_risk_heatmap.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no registry mutation</span> {str(owner_risk_heatmap.get("no_registry_lifecycle_mutation", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_risk_heatmap.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Action", "Blocking Decisions", "Risk Score"], owner_risk_action_rows or [["None", "0", "0"]])}
      {_table(["Queue", "Risk Score", "Action Counts"], owner_risk_queue_rows or [["None", "0", ""]])}
      {_table(["Band", "Score", "Queue", "Item", "Subject", "Blocked Actions"], owner_risk_top_rows or [["None", "0", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Review Checklist v2.8</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_checklist.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_checklist.get("status", "")))} 路 <span class="badge">items</span> {owner_review_checklist.get("item_count", 0)} 路 <span class="badge">critical</span> {owner_review_checklist.get("critical_count", 0)} 路 <span class="badge">single review</span> {owner_review_checklist.get("single_item_review_count", 0)} 路 <span class="badge">batch review</span> {owner_review_checklist.get("batch_review_count", 0)} 路 <span class="badge">read only</span> {str(owner_review_checklist.get("read_only_review_checklist", True)).lower()} 路 {_link(owner_paths.get("review_checklist", ""), "owner_decision_review_checklist.json")} 路 {_link(owner_paths.get("review_checklist_md", ""), "markdown")} 路 {_link(owner_paths.get("review_checklist_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_checklist.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_checklist.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_checklist.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_review_checklist.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_checklist.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Risk", "Score", "Queue", "Item", "Review Mode", "Decision Options", "Prompt"], owner_review_checklist_rows or [["None", "0", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Guardrail Validator v2.9</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_guardrail_validator.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_guardrail_validator.get("status", "")))} 路 <span class="badge">checks</span> {owner_guardrail_validator.get("check_count", 0)} 路 <span class="badge">failed</span> {owner_guardrail_validator.get("failed_count", 0)} 路 <span class="badge">critical failed</span> {owner_guardrail_validator.get("critical_failed_count", 0)} 路 <span class="badge">read only</span> {str(owner_guardrail_validator.get("read_only_guardrail_validator", True)).lower()} 路 {_link(owner_paths.get("guardrail_validator", ""), "owner_decision_guardrail_validator.json")} 路 {_link(owner_paths.get("guardrail_validator_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_guardrail_validator.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_guardrail_validator.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_guardrail_validator.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_guardrail_validator.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no registry mutation</span> {str(owner_guardrail_validator.get("no_registry_lifecycle_mutation", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_guardrail_validator.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Check", "Passed", "Severity", "Evidence", "Recommendation"], owner_guardrail_validator_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Guardrail Trend v3.0</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_guardrail_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_guardrail_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_guardrail_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_guardrail_trend.get("window_count", 0)} 路 <span class="badge">consecutive passed</span> {owner_guardrail_trend.get("consecutive_passed_count", 0)} 路 <span class="badge">read only</span> {str(owner_guardrail_trend.get("read_only_guardrail_trend_snapshot", True)).lower()} 路 {_link(owner_paths.get("guardrail_trend", ""), "owner_decision_guardrail_trend_snapshot.json")} 路 {_link(owner_paths.get("guardrail_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current failed</span> {owner_guardrail_trend_current.get("failed_count", 0)} ({owner_guardrail_trend_delta.get("failed_count", 0)}) 路 <span class="badge">current checks</span> {owner_guardrail_trend_current.get("check_count", 0)} ({owner_guardrail_trend_delta.get("check_count", 0)}) 路 <span class="badge">no decisions applied</span> {str(owner_guardrail_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_guardrail_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_guardrail_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Checks", "Failed"], owner_guardrail_trend_rows or [["None", "", "0", "0"]])}
    </section>
    <section><h2>Owner Decision Guardrail Coverage v3.1</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_guardrail_coverage.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_guardrail_coverage.get("status", "")))} 路 <span class="badge">actions</span> {owner_guardrail_coverage.get("action_count", 0)} 路 <span class="badge">covered</span> {owner_guardrail_coverage.get("covered_count", 0)} 路 <span class="badge">uncovered</span> {owner_guardrail_coverage.get("uncovered_count", 0)} 路 <span class="badge">validator failed</span> {owner_guardrail_coverage.get("validator_failed_count", 0)} 路 <span class="badge">read only</span> {str(owner_guardrail_coverage.get("read_only_guardrail_coverage_matrix", True)).lower()} 路 {_link(owner_paths.get("guardrail_coverage", ""), "owner_decision_guardrail_coverage_matrix.json")} 路 {_link(owner_paths.get("guardrail_coverage_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_guardrail_coverage.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_guardrail_coverage.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_guardrail_coverage.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_guardrail_coverage.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_guardrail_coverage.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Action", "Blocking Decisions", "Coverage", "Expected Checks", "Present Checks", "Failed Checks"], owner_guardrail_coverage_rows or [["None", "0", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Guardrail Coverage Trend v3.2</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_guardrail_coverage_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_guardrail_coverage_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_guardrail_coverage_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_guardrail_coverage_trend.get("window_count", 0)} 路 <span class="badge">consecutive covered</span> {owner_guardrail_coverage_trend.get("consecutive_covered_count", 0)} 路 <span class="badge">read only</span> {str(owner_guardrail_coverage_trend.get("read_only_guardrail_coverage_trend_snapshot", True)).lower()} 路 {_link(owner_paths.get("guardrail_coverage_trend", ""), "owner_decision_guardrail_coverage_trend_snapshot.json")} 路 {_link(owner_paths.get("guardrail_coverage_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current uncovered</span> {owner_guardrail_coverage_trend_current.get("uncovered_count", 0)} ({owner_guardrail_coverage_trend_delta.get("uncovered_count", 0)}) 路 <span class="badge">current actions</span> {owner_guardrail_coverage_trend_current.get("action_count", 0)} ({owner_guardrail_coverage_trend_delta.get("action_count", 0)}) 路 <span class="badge">no decisions applied</span> {str(owner_guardrail_coverage_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_guardrail_coverage_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_guardrail_coverage_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Actions", "Uncovered"], owner_guardrail_coverage_trend_rows or [["None", "", "0", "0"]])}
    </section>
    <section><h2>Owner Decision Governance Health v3.3</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_governance_health.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_governance_health.get("status", "")))} 路 <span class="badge">checks</span> {owner_governance_health.get("check_count", 0)} 路 <span class="badge">failed</span> {owner_governance_health.get("failed_count", 0)} 路 <span class="badge">critical failed</span> {owner_governance_health.get("critical_failed_count", 0)} 路 <span class="badge">read only</span> {str(owner_governance_health.get("read_only_governance_health_summary", True)).lower()} 路 {_link(owner_paths.get("governance_health", ""), "owner_decision_governance_health_summary.json")} 路 {_link(owner_paths.get("governance_health_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_governance_health.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_governance_health.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_governance_health.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_governance_health.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_governance_health.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Check", "Passed", "Severity", "Evidence", "Recommendation"], owner_governance_health_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Governance Health Trend v3.4</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_governance_health_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_governance_health_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_governance_health_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_governance_health_trend.get("window_count", 0)} 路 <span class="badge">consecutive healthy</span> {owner_governance_health_trend.get("consecutive_healthy_count", 0)} 路 <span class="badge">read only</span> {str(owner_governance_health_trend.get("read_only_governance_health_trend_snapshot", True)).lower()} 路 {_link(owner_paths.get("governance_health_trend", ""), "owner_decision_governance_health_trend_snapshot.json")} 路 {_link(owner_paths.get("governance_health_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current failed</span> {owner_governance_health_trend_current.get("failed_count", 0)} ({owner_governance_health_trend_delta.get("failed_count", 0)}) 路 <span class="badge">current checks</span> {owner_governance_health_trend_current.get("check_count", 0)} ({owner_governance_health_trend_delta.get("check_count", 0)}) 路 <span class="badge">no decisions applied</span> {str(owner_governance_health_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_governance_health_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_governance_health_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Checks", "Failed"], owner_governance_health_trend_rows or [["None", "", "0", "0"]])}
    </section>
    <section><h2>Owner Decision Governance Freshness v3.5</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_governance_freshness.get("schema_version", "")))} 璺?<span class="badge">status</span> {html.escape(str(owner_governance_freshness.get("status", "")))} 璺?<span class="badge">reports</span> {owner_governance_freshness.get("report_count", 0)} 璺?<span class="badge">fresh</span> {owner_governance_freshness.get("fresh_count", 0)} 璺?<span class="badge">missing</span> {owner_governance_freshness.get("missing_count", 0)} 璺?<span class="badge">stale</span> {owner_governance_freshness.get("stale_count", 0)} 璺?<span class="badge">max age h</span> {owner_governance_freshness.get("max_age_hours", "")} 璺?<span class="badge">read only</span> {str(owner_governance_freshness.get("read_only_governance_freshness_summary", True)).lower()} 璺?{_link(owner_paths.get("governance_freshness", ""), "owner_decision_governance_freshness_summary.json")} 璺?{_link(owner_paths.get("governance_freshness_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_governance_freshness.get("no_decisions_applied", True)).lower()} 璺?<span class="badge">no decision file</span> {str(owner_governance_freshness.get("no_decision_file_written", True)).lower()} 璺?<span class="badge">no API calls</span> {str(owner_governance_freshness.get("no_model_api_calls", True)).lower()} 璺?<span class="badge">no cleanup</span> {str(owner_governance_freshness.get("no_filesystem_cleanup", True)).lower()} 璺?<span class="badge">no writeback</span> {str(owner_governance_freshness.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Report", "Status", "Fresh", "Age Hours", "Effective TS", "File"], owner_governance_freshness_rows or [["None", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Decision Governance Ops Digest v3.6</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_governance_ops_digest.get("schema_version", "")))} 璺?<span class="badge">status</span> {html.escape(str(owner_governance_ops_digest.get("status", "")))} 璺?<span class="badge">owner action</span> {html.escape(str(owner_governance_ops_digest.get("owner_action", "")))} 璺?<span class="badge">pending owner</span> {owner_governance_ops_digest.get("pending_owner_items", 0)} 璺?<span class="badge">blockers</span> {len(owner_governance_ops_digest.get("blockers", []))} 璺?<span class="badge">read only</span> {str(owner_governance_ops_digest.get("read_only_governance_ops_digest", True)).lower()} 璺?{_link(owner_paths.get("governance_ops_digest", ""), "owner_decision_governance_ops_digest.json")} 璺?{_link(owner_paths.get("governance_ops_digest_md", ""), "markdown")} 璺?{_link(owner_paths.get("governance_ops_digest_audit", ""), "audit")}</p>
      <p><span class="badge">health</span> {html.escape(str(owner_governance_ops_digest_health.get("status", "")))} failed={owner_governance_ops_digest_health.get("failed_count", 0)} critical={owner_governance_ops_digest_health.get("critical_failed_count", 0)} 璺?<span class="badge">trend</span> {html.escape(str(owner_governance_ops_digest_trend.get("status", "")))} consecutive={owner_governance_ops_digest_trend.get("consecutive_healthy_count", 0)} 璺?<span class="badge">freshness</span> {html.escape(str(owner_governance_ops_digest_freshness.get("status", "")))} fresh={owner_governance_ops_digest_freshness.get("fresh_count", 0)}/{owner_governance_ops_digest_freshness.get("report_count", 0)}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_governance_ops_digest.get("no_decisions_applied", True)).lower()} 璺?<span class="badge">no decision file</span> {str(owner_governance_ops_digest.get("no_decision_file_written", True)).lower()} 璺?<span class="badge">no API calls</span> {str(owner_governance_ops_digest.get("no_model_api_calls", True)).lower()} 璺?<span class="badge">no cleanup</span> {str(owner_governance_ops_digest.get("no_filesystem_cleanup", True)).lower()} 璺?<span class="badge">no writeback</span> {str(owner_governance_ops_digest.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Pending", "Approved Pending", "Rejected", "Deferred", "Owner Approval", "File"], owner_governance_ops_digest_rows or [["None", "0", "0", "0", "0", "", ""]])}
    </section>
    <section><h2>Owner Review Drilldown v3.7</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_drilldown.get("schema_version", "")))} 璺?<span class="badge">status</span> {html.escape(str(owner_review_drilldown.get("status", "")))} 璺?<span class="badge">pending</span> {owner_review_drilldown.get("pending_owner_item_count", 0)} 璺?<span class="badge">critical</span> {owner_review_drilldown.get("critical_count", 0)} 璺?<span class="badge">high</span> {owner_review_drilldown.get("high_count", 0)} 璺?<span class="badge">medium</span> {owner_review_drilldown.get("medium_count", 0)} 璺?<span class="badge">low</span> {owner_review_drilldown.get("low_count", 0)} 璺?<span class="badge">read only</span> {str(owner_review_drilldown.get("read_only_owner_review_drilldown", True)).lower()} 璺?{_link(owner_paths.get("owner_review_drilldown", ""), "owner_review_drilldown.json")} 璺?{_link(owner_paths.get("owner_review_drilldown_md", ""), "markdown")} 璺?{_link(owner_paths.get("owner_review_drilldown_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_drilldown.get("no_decisions_applied", True)).lower()} 璺?<span class="badge">no decision file</span> {str(owner_review_drilldown.get("no_decision_file_written", True)).lower()} 璺?<span class="badge">no API calls</span> {str(owner_review_drilldown.get("no_model_api_calls", True)).lower()} 璺?<span class="badge">no cleanup</span> {str(owner_review_drilldown.get("no_filesystem_cleanup", True)).lower()} 璺?<span class="badge">no writeback</span> {str(owner_review_drilldown.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Critical", "High", "Medium", "Low", "Total"], owner_review_drilldown_queue_rows or [["None", "0", "0", "0", "0", "0"]])}
      {_table(["Risk", "Domain", "Queue", "Subject", "Blocked Action", "Forbidden Auto Actions", "File"], owner_review_drilldown_item_rows or [["None", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Packet Coverage v3.8</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_packet_coverage.get("schema_version", "")))} 璺?<span class="badge">status</span> {html.escape(str(owner_review_packet_coverage.get("status", "")))} 璺?<span class="badge">items</span> {owner_review_packet_coverage.get("item_count", 0)} 璺?<span class="badge">packet</span> {owner_review_packet_coverage.get("packet_count", 0)} 璺?<span class="badge">summary</span> {owner_review_packet_coverage.get("summary_count", 0)} 璺?<span class="badge">drilldown</span> {owner_review_packet_coverage.get("drilldown_count", 0)} 璺?<span class="badge">mismatch</span> {owner_review_packet_coverage.get("mismatch_count", 0)} 璺?<span class="badge">conflicts</span> {owner_review_packet_coverage.get("conflict_count", 0)} 璺?<span class="badge">read only</span> {str(owner_review_packet_coverage.get("read_only_packet_coverage", True)).lower()} 璺?{_link(owner_paths.get("owner_review_packet_coverage", ""), "owner_review_packet_coverage.json")} 璺?{_link(owner_paths.get("owner_review_packet_coverage_audit", ""), "audit")}</p>
      <p><span class="badge">missing packet</span> {owner_review_packet_coverage.get("missing_packet_count", 0)} 璺?<span class="badge">missing summary</span> {owner_review_packet_coverage.get("missing_summary_count", 0)} 璺?<span class="badge">missing drilldown</span> {owner_review_packet_coverage.get("missing_drilldown_count", 0)} 璺?<span class="badge">no decisions applied</span> {str(owner_review_packet_coverage.get("no_decisions_applied", True)).lower()} 璺?<span class="badge">no API calls</span> {str(owner_review_packet_coverage.get("no_model_api_calls", True)).lower()} 璺?<span class="badge">no writeback</span> {str(owner_review_packet_coverage.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Item", "Packet", "Summary", "Drilldown", "Conflicts"], owner_review_packet_coverage_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Integrity Manifest v3.9</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_integrity_manifest.get("schema_version", "")))} 璺?<span class="badge">status</span> {html.escape(str(owner_review_integrity_manifest.get("status", "")))} 璺?<span class="badge">artifacts</span> {owner_review_integrity_manifest.get("artifact_count", 0)} 璺?<span class="badge">present</span> {owner_review_integrity_manifest.get("present_count", 0)} 璺?<span class="badge">missing</span> {owner_review_integrity_manifest.get("missing_count", 0)} 璺?<span class="badge">duplicate hashes</span> {owner_review_integrity_manifest.get("duplicate_hash_count", 0)} 璺?<span class="badge">read only</span> {str(owner_review_integrity_manifest.get("read_only_integrity_manifest", True)).lower()} 璺?{_link(owner_paths.get("owner_review_integrity_manifest", ""), "owner_review_integrity_manifest.json")} 璺?{_link(owner_paths.get("owner_review_integrity_manifest_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_integrity_manifest.get("no_decisions_applied", True)).lower()} 璺?<span class="badge">no decision file</span> {str(owner_review_integrity_manifest.get("no_decision_file_written", True)).lower()} 璺?<span class="badge">no API calls</span> {str(owner_review_integrity_manifest.get("no_model_api_calls", True)).lower()} 璺?<span class="badge">no cleanup</span> {str(owner_review_integrity_manifest.get("no_filesystem_cleanup", True)).lower()} 璺?<span class="badge">no writeback</span> {str(owner_review_integrity_manifest.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Artifact", "Exists", "Bytes", "Status", "Schema", "SHA256", "File"], owner_review_integrity_manifest_rows or [["None", "", "0", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Integrity Trend v4.0</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_integrity_trend.get("schema_version", "")))} 璺?<span class="badge">status</span> {html.escape(str(owner_review_integrity_trend.get("status", "")))} 璺?<span class="badge">history</span> {owner_review_integrity_trend.get("history_count", 0)} 璺?<span class="badge">window</span> {owner_review_integrity_trend.get("window_count", 0)} 璺?<span class="badge">consecutive complete</span> {owner_review_integrity_trend.get("consecutive_complete_count", 0)} 璺?<span class="badge">read only</span> {str(owner_review_integrity_trend.get("read_only_integrity_trend_snapshot", True)).lower()} 璺?{_link(owner_paths.get("owner_review_integrity_trend", ""), "owner_review_integrity_trend_snapshot.json")} 璺?{_link(owner_paths.get("owner_review_integrity_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current artifacts</span> {owner_review_integrity_trend_current.get("artifact_count", 0)} ({owner_review_integrity_trend_delta.get("artifact_count", 0)}) 璺?<span class="badge">present</span> {owner_review_integrity_trend_current.get("present_count", 0)} ({owner_review_integrity_trend_delta.get("present_count", 0)}) 璺?<span class="badge">missing</span> {owner_review_integrity_trend_current.get("missing_count", 0)} ({owner_review_integrity_trend_delta.get("missing_count", 0)}) 璺?<span class="badge">no decisions applied</span> {str(owner_review_integrity_trend.get("no_decisions_applied", True)).lower()} 璺?<span class="badge">no API calls</span> {str(owner_review_integrity_trend.get("no_model_api_calls", True)).lower()} 璺?<span class="badge">no writeback</span> {str(owner_review_integrity_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Artifacts", "Present", "Missing"], owner_review_integrity_trend_rows or [["None", "", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Readiness Checklist v4.1</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_readiness_checklist.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_readiness_checklist.get("status", "")))} 路 <span class="badge">checks</span> {owner_review_readiness_checklist.get("check_count", 0)} 路 <span class="badge">passed</span> {owner_review_readiness_checklist.get("passed_count", 0)} 路 <span class="badge">failed</span> {owner_review_readiness_checklist.get("failed_count", 0)} 路 <span class="badge">pending owner</span> {owner_review_readiness_checklist.get("pending_owner_items", 0)} 路 <span class="badge">read only</span> {str(owner_review_readiness_checklist.get("read_only_owner_review_readiness_checklist", True)).lower()} 路 {_link(owner_paths.get("owner_review_readiness_checklist", ""), "owner_review_readiness_checklist.json")} 路 {_link(owner_paths.get("owner_review_readiness_checklist_md", ""), "markdown")} 路 {_link(owner_paths.get("owner_review_readiness_checklist_audit", ""), "audit")}</p>
      <p><span class="badge">owner action</span> {html.escape(str(owner_review_readiness_checklist.get("owner_action", "")))} 路 <span class="badge">no decisions applied</span> {str(owner_review_readiness_checklist.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_readiness_checklist.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_readiness_checklist.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_readiness_checklist.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Check", "Passed", "Severity", "Evidence", "Next Action"], owner_review_readiness_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Readiness Trend v4.2</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_readiness_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_readiness_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_review_readiness_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_review_readiness_trend.get("window_count", 0)} 路 <span class="badge">consecutive ready</span> {owner_review_readiness_trend.get("consecutive_ready_count", 0)} 路 <span class="badge">failed observations</span> {owner_review_readiness_trend.get("failed_observation_count", 0)} 路 <span class="badge">read only</span> {str(owner_review_readiness_trend.get("read_only_owner_review_readiness_trend", True)).lower()} 路 {_link(owner_paths.get("owner_review_readiness_trend", ""), "owner_review_readiness_trend_snapshot.json")} 路 {_link(owner_paths.get("owner_review_readiness_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current checks</span> {owner_review_readiness_trend_current.get("check_count", 0)} ({owner_review_readiness_trend_delta.get("check_count", 0)}) 路 <span class="badge">current failed</span> {owner_review_readiness_trend_current.get("failed_count", 0)} ({owner_review_readiness_trend_delta.get("failed_count", 0)}) 路 <span class="badge">current critical failed</span> {owner_review_readiness_trend_current.get("critical_failed_count", 0)} ({owner_review_readiness_trend_delta.get("critical_failed_count", 0)}) 路 <span class="badge">no decisions applied</span> {str(owner_review_readiness_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_readiness_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_readiness_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Checks", "Failed", "Critical Failed"], owner_review_readiness_trend_rows or [["None", "", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Queue Aging v4.3</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_queue_aging.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_queue_aging.get("status", "")))} 路 <span class="badge">queues</span> {owner_review_queue_aging.get("queue_count", 0)} 路 <span class="badge">items</span> {owner_review_queue_aging.get("item_count", 0)} 路 <span class="badge">stale queues</span> {owner_review_queue_aging.get("stale_queue_count", 0)} 路 <span class="badge">watch queues</span> {owner_review_queue_aging.get("watch_queue_count", 0)} 路 <span class="badge">max age h</span> {owner_review_queue_aging.get("max_age_hours", 0)} 路 <span class="badge">read only</span> {str(owner_review_queue_aging.get("read_only_owner_review_queue_aging", True)).lower()} 路 {_link(owner_paths.get("owner_review_queue_aging", ""), "owner_review_queue_aging.json")} 路 {_link(owner_paths.get("owner_review_queue_aging_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_queue_aging.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_queue_aging.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_queue_aging.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_review_queue_aging.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_queue_aging.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Aging", "Pending", "Items", "Max Age H", "Watch", "Stale", "Unknown", "Oldest Item", "Recommendation"], owner_review_queue_aging_rows or [["None", "", "0", "0", "", "0", "0", "0", "", ""]])}
    </section>
    <section><h2>Owner Review Queue Aging Trend v4.4</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_queue_aging_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_queue_aging_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_review_queue_aging_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_review_queue_aging_trend.get("window_count", 0)} 路 <span class="badge">consecutive fresh</span> {owner_review_queue_aging_trend.get("consecutive_fresh_count", 0)} 路 <span class="badge">attention observations</span> {owner_review_queue_aging_trend.get("attention_observation_count", 0)} 路 <span class="badge">read only</span> {str(owner_review_queue_aging_trend.get("read_only_owner_review_queue_aging_trend", True)).lower()} 路 {_link(owner_paths.get("owner_review_queue_aging_trend", ""), "owner_review_queue_aging_trend_snapshot.json")} 路 {_link(owner_paths.get("owner_review_queue_aging_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current queues</span> {owner_review_queue_aging_trend_current.get("queue_count", 0)} ({owner_review_queue_aging_trend_delta.get("queue_count", 0)}) 路 <span class="badge">current stale</span> {owner_review_queue_aging_trend_current.get("stale_queue_count", 0)} ({owner_review_queue_aging_trend_delta.get("stale_queue_count", 0)}) 路 <span class="badge">current watch</span> {owner_review_queue_aging_trend_current.get("watch_queue_count", 0)} ({owner_review_queue_aging_trend_delta.get("watch_queue_count", 0)}) 路 <span class="badge">current unknown</span> {owner_review_queue_aging_trend_current.get("unknown_age_queue_count", 0)} ({owner_review_queue_aging_trend_delta.get("unknown_age_queue_count", 0)}) 路 <span class="badge">no decisions applied</span> {str(owner_review_queue_aging_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_queue_aging_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_queue_aging_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Queues", "Stale", "Watch", "Unknown"], owner_review_queue_aging_trend_rows or [["None", "", "0", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Queue SLA Forecast v4.5</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_queue_sla_forecast.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_queue_sla_forecast.get("status", "")))} 路 <span class="badge">queues</span> {owner_review_queue_sla_forecast.get("queue_count", 0)} 路 <span class="badge">items</span> {owner_review_queue_sla_forecast.get("item_count", 0)} 路 <span class="badge">attention queues</span> {owner_review_queue_sla_forecast.get("attention_queue_count", 0)} 路 <span class="badge">bands</span> {html.escape(json.dumps(owner_review_queue_sla_forecast.get("band_counts", {}), ensure_ascii=False))} 路 <span class="badge">read only</span> {str(owner_review_queue_sla_forecast.get("read_only_owner_review_queue_sla_forecast", True)).lower()} 路 {_link(owner_paths.get("owner_review_queue_sla_forecast", ""), "owner_review_queue_sla_forecast.json")} 路 {_link(owner_paths.get("owner_review_queue_sla_forecast_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_queue_sla_forecast.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_queue_sla_forecast.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_queue_sla_forecast.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no cleanup</span> {str(owner_review_queue_sla_forecast.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_queue_sla_forecast.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Forecast", "Pending", "Items", "Max Age H", "Hours To Watch", "Hours To Stale", "Unknown", "Oldest Item", "Recommendation"], owner_review_queue_sla_forecast_rows or [["None", "", "0", "0", "", "", "", "0", "", ""]])}
    </section>
    <section><h2>Owner Review Queue SLA Forecast Trend v4.6</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_queue_sla_forecast_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_queue_sla_forecast_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_review_queue_sla_forecast_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_review_queue_sla_forecast_trend.get("window_count", 0)} 路 <span class="badge">consecutive healthy</span> {owner_review_queue_sla_forecast_trend.get("consecutive_healthy_count", 0)} 路 <span class="badge">attention observations</span> {owner_review_queue_sla_forecast_trend.get("attention_observation_count", 0)} 路 <span class="badge">read only</span> {str(owner_review_queue_sla_forecast_trend.get("read_only_owner_review_queue_sla_forecast_trend", True)).lower()} 路 {_link(owner_paths.get("owner_review_queue_sla_forecast_trend", ""), "owner_review_queue_sla_forecast_trend_snapshot.json")} 路 {_link(owner_paths.get("owner_review_queue_sla_forecast_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current queues</span> {owner_review_queue_sla_forecast_trend_current.get("queue_count", 0)} ({owner_review_queue_sla_forecast_trend_delta.get("queue_count", 0)}) 路 <span class="badge">current attention</span> {owner_review_queue_sla_forecast_trend_current.get("attention_queue_count", 0)} ({owner_review_queue_sla_forecast_trend_delta.get("attention_queue_count", 0)}) 路 <span class="badge">band delta</span> {html.escape(json.dumps(owner_review_queue_sla_forecast_trend_delta.get("band_counts", {}), ensure_ascii=False))} 路 <span class="badge">no decisions applied</span> {str(owner_review_queue_sla_forecast_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_queue_sla_forecast_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_queue_sla_forecast_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Queues", "Attention", "Bands"], owner_review_queue_sla_forecast_trend_rows or [["None", "", "0", "0", "{}"]])}
    </section>
    <section><h2>Owner Review Next Action Preview v4.7</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_next_action_preview.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_next_action_preview.get("status", "")))} 路 <span class="badge">readiness</span> {html.escape(str(owner_review_next_action_preview.get("readiness_status", "")))} 路 <span class="badge">queues</span> {owner_review_next_action_preview.get("queue_count", 0)} 路 <span class="badge">pending owner</span> {owner_review_next_action_preview.get("pending_owner_items", 0)} 路 <span class="badge">next queue</span> {html.escape(str(owner_review_next_action_preview.get("next_queue_id", "")))} 路 <span class="badge">next mode</span> {html.escape(str(owner_review_next_action_preview.get("next_review_mode", "")))} 路 <span class="badge">read only</span> {str(owner_review_next_action_preview.get("read_only_owner_review_next_action_preview", True)).lower()} 路 {_link(owner_paths.get("owner_review_next_action_preview", ""), "owner_review_next_action_preview.json")} 路 {_link(owner_paths.get("owner_review_next_action_preview_audit", ""), "audit")}</p>
      <p><span class="badge">next owner action</span> {html.escape(str(owner_review_next_action_preview.get("next_owner_action", "")))} 路 <span class="badge">no decisions applied</span> {str(owner_review_next_action_preview.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_next_action_preview.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_next_action_preview.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_next_action_preview.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Mode", "Rank", "Pending", "Priority", "Forecast", "Hours To Watch", "Top Item", "Owner Action", "Forbidden Auto Actions"], owner_review_next_action_preview_rows or [["None", "", "0", "0", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Next Action Trend v4.8</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_next_action_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_next_action_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_review_next_action_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_review_next_action_trend.get("window_count", 0)} 路 <span class="badge">same next action</span> {owner_review_next_action_trend.get("consecutive_same_next_action_count", 0)} 路 <span class="badge">transitions</span> {owner_review_next_action_trend.get("transition_count", 0)} 路 <span class="badge">changed</span> {str(owner_review_next_action_trend.get("changed_from_previous", False)).lower()} 路 <span class="badge">read only</span> {str(owner_review_next_action_trend.get("read_only_owner_review_next_action_trend", True)).lower()} 路 {_link(owner_paths.get("owner_review_next_action_trend", ""), "owner_review_next_action_trend_snapshot.json")} 路 {_link(owner_paths.get("owner_review_next_action_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current queue</span> {html.escape(str(owner_review_next_action_trend_current.get("next_queue_id", "")))} 路 <span class="badge">current mode</span> {html.escape(str(owner_review_next_action_trend_current.get("next_review_mode", "")))} 路 <span class="badge">no decisions applied</span> {str(owner_review_next_action_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_next_action_trend.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_next_action_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_next_action_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Queues", "Next Queue", "Mode"], owner_review_next_action_trend_rows or [["None", "", "0", "", ""]])}
    </section>
    <section><h2>Owner Review Action Brief v4.9</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_action_brief.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_action_brief.get("status", "")))} 路 <span class="badge">queue</span> {html.escape(str(owner_review_action_brief.get("queue_id", "")))} 路 <span class="badge">mode</span> {html.escape(str(owner_review_action_brief.get("review_mode", "")))} 路 <span class="badge">item</span> {html.escape(str(owner_review_action_brief.get("item_id", "")))} 路 <span class="badge">priority</span> {html.escape(str(owner_review_action_brief.get("priority_band", "")))} 路 <span class="badge">trend</span> {html.escape(str(owner_review_action_brief.get("trend_status", "")))} 路 <span class="badge">read only</span> {str(owner_review_action_brief.get("read_only_owner_review_action_brief", True)).lower()} 路 {_link(owner_paths.get("owner_review_action_brief", ""), "owner_review_action_brief.json")} 路 {_link(owner_paths.get("owner_review_action_brief_md", ""), "markdown")} 路 {_link(owner_paths.get("owner_review_action_brief_audit", ""), "audit")}</p>
      <p><span class="badge">subject</span> {html.escape(str(owner_review_action_brief.get("subject", "")))} 路 <span class="badge">options</span> {html.escape(", ".join(str(x) for x in owner_review_action_brief.get("recommended_decision_options", [])))} 路 <span class="badge">forbidden auto</span> {html.escape(", ".join(str(x) for x in owner_review_action_brief.get("forbidden_auto_actions", [])))}</p>
      <p><span class="badge">prompt</span> {html.escape(str(owner_review_action_brief.get("decision_prompt", "")))} 路 <span class="badge">no decisions applied</span> {str(owner_review_action_brief.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_action_brief.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_action_brief.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_action_brief.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
    </section>
    <section><h2>Owner Review Action Brief Trend v5.0</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_action_brief_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_action_brief_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_review_action_brief_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_review_action_brief_trend.get("window_count", 0)} 路 <span class="badge">same brief</span> {owner_review_action_brief_trend.get("consecutive_same_action_brief_count", 0)} 路 <span class="badge">transitions</span> {owner_review_action_brief_trend.get("transition_count", 0)} 路 <span class="badge">changed</span> {str(owner_review_action_brief_trend.get("changed_from_previous", False)).lower()} 路 <span class="badge">read only</span> {str(owner_review_action_brief_trend.get("read_only_owner_review_action_brief_trend", True)).lower()} 路 {_link(owner_paths.get("owner_review_action_brief_trend", ""), "owner_review_action_brief_trend_snapshot.json")} 路 {_link(owner_paths.get("owner_review_action_brief_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current queue</span> {html.escape(str(owner_review_action_brief_trend_current.get("queue_id", "")))} 路 <span class="badge">current item</span> {html.escape(str(owner_review_action_brief_trend_current.get("item_id", "")))} 路 <span class="badge">current mode</span> {html.escape(str(owner_review_action_brief_trend_current.get("review_mode", "")))} 路 <span class="badge">no decisions applied</span> {str(owner_review_action_brief_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_action_brief_trend.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_action_brief_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_action_brief_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Queue", "Item", "Mode"], owner_review_action_brief_trend_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Packet Diff v5.1</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_packet_diff.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_packet_diff.get("status", "")))} 路 <span class="badge">findings</span> {owner_review_packet_diff.get("finding_count", 0)} 路 <span class="badge">high</span> {owner_review_packet_diff.get("high_count", 0)} 路 <span class="badge">medium</span> {owner_review_packet_diff.get("medium_count", 0)} 路 <span class="badge">info</span> {owner_review_packet_diff.get("info_count", 0)} 路 <span class="badge">read only</span> {str(owner_review_packet_diff.get("read_only_owner_review_packet_diff", True)).lower()} 路 {_link(owner_paths.get("owner_review_packet_diff", ""), "owner_review_packet_diff.json")} 路 {_link(owner_paths.get("owner_review_packet_diff_md", ""), "markdown")} 路 {_link(owner_paths.get("owner_review_packet_diff_audit", ""), "audit")}</p>
      <p><span class="badge">brief</span> {html.escape(str(owner_review_packet_diff.get("brief_key", "")))} 路 <span class="badge">packet first</span> {html.escape(str(owner_review_packet_diff.get("packet_first_key", "")))} 路 <span class="badge">priority first</span> {html.escape(str(owner_review_packet_diff.get("priority_first_key", "")))} 路 <span class="badge">preview first</span> {html.escape(str(owner_review_packet_diff.get("preview_first_key", "")))} 路 <span class="badge">no decisions applied</span> {str(owner_review_packet_diff.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_packet_diff.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_packet_diff.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Severity", "Kind", "Field", "Message", "Source"], owner_review_packet_diff_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Decision Simulator v5.2</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_decision_simulator.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_decision_simulator.get("status", "")))} 路 <span class="badge">queue</span> {html.escape(str(owner_review_decision_simulator.get("queue_id", "")))} 路 <span class="badge">item</span> {html.escape(str(owner_review_decision_simulator.get("item_id", "")))} 路 <span class="badge">options</span> {owner_review_decision_simulator.get("option_count", 0)} 路 <span class="badge">read only</span> {str(owner_review_decision_simulator.get("read_only_owner_review_decision_simulator", True)).lower()} 路 {_link(owner_paths.get("owner_review_decision_simulator", ""), "owner_review_decision_simulator.json")} 路 {_link(owner_paths.get("owner_review_decision_simulator_md", ""), "markdown")} 路 {_link(owner_paths.get("owner_review_decision_simulator_audit", ""), "audit")}</p>
      <p><span class="badge">simulated owner gate required</span> {str(owner_review_decision_simulator.get("owner_approval_required_for_simulated_decision", True)).lower()} 路 <span class="badge">no decisions applied</span> {str(owner_review_decision_simulator.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_decision_simulator.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_decision_simulator.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no provider activation</span> {str(owner_review_decision_simulator.get("no_provider_activation", True)).lower()} 路 <span class="badge">no routing switch</span> {str(owner_review_decision_simulator.get("no_routing_auto_switch", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_decision_simulator.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Option", "Kind", "Item", "Current Counts", "Simulated Counts", "Follow-up"], owner_review_decision_simulator_rows or [["None", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Decision Impact Trend v5.3</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_decision_impact_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_decision_impact_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_review_decision_impact_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_review_decision_impact_trend.get("window_count", 0)} 路 <span class="badge">same impact</span> {owner_review_decision_impact_trend.get("consecutive_same_decision_impact_count", 0)} 路 <span class="badge">transitions</span> {owner_review_decision_impact_trend.get("transition_count", 0)} 路 <span class="badge">changed</span> {str(owner_review_decision_impact_trend.get("changed_from_previous", False)).lower()} 路 <span class="badge">read only</span> {str(owner_review_decision_impact_trend.get("read_only_owner_review_decision_impact_trend", True)).lower()} 路 {_link(owner_paths.get("owner_review_decision_impact_trend", ""), "owner_review_decision_impact_trend_snapshot.json")} 路 {_link(owner_paths.get("owner_review_decision_impact_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current queue</span> {html.escape(str(owner_review_decision_impact_trend_current.get("queue_id", "")))} 路 <span class="badge">current item</span> {html.escape(str(owner_review_decision_impact_trend_current.get("item_id", "")))} 路 <span class="badge">options</span> {owner_review_decision_impact_trend_current.get("option_count", 0)} 路 <span class="badge">no decisions applied</span> {str(owner_review_decision_impact_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_decision_impact_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no provider activation</span> {str(owner_review_decision_impact_trend.get("no_provider_activation", True)).lower()} 路 <span class="badge">no routing switch</span> {str(owner_review_decision_impact_trend.get("no_routing_auto_switch", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_decision_impact_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Option", "Kind", "Delta", "Would Write Decision", "Would API", "Would Activate", "Would Switch"], owner_review_decision_impact_rows or [["None", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Blocker Digest v5.4</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_blocker_digest.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_blocker_digest.get("status", "")))} 路 <span class="badge">blockers</span> {owner_review_blocker_digest.get("total_blockers", 0)} 路 <span class="badge">p0</span> {owner_review_blocker_digest.get("p0_blockers", 0)} 路 <span class="badge">batch</span> {owner_review_blocker_digest.get("batch_blockers", 0)} 路 <span class="badge">read only</span> {str(owner_review_blocker_digest.get("read_only_owner_review_blocker_digest", True)).lower()} 路 {_link(owner_paths.get("owner_review_blocker_digest", ""), "owner_review_blocker_digest.json")} 路 {_link(owner_paths.get("owner_review_blocker_digest_md", ""), "markdown")} 路 {_link(owner_paths.get("owner_review_blocker_digest_audit", ""), "audit")}</p>
      <p><span class="badge">forbidden auto actions</span> {html.escape(json.dumps(owner_review_blocker_digest.get("forbidden_auto_action_counts", {}), ensure_ascii=False))} 路 <span class="badge">dry-run context</span> {html.escape(str(owner_review_blocker_digest_context.get("status", "")))} 路 <span class="badge">no decisions applied</span> {str(owner_review_blocker_digest.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_blocker_digest.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_blocker_digest.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no provider activation</span> {str(owner_review_blocker_digest.get("no_provider_activation", True)).lower()} 路 <span class="badge">no routing switch</span> {str(owner_review_blocker_digest.get("no_routing_auto_switch", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_blocker_digest.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Domain", "Priority", "Item", "Subject", "Owner Action", "Forbidden Auto Actions"], owner_review_blocker_rows or [["None", "", "", "", "", "", ""]])}
      {_table(["Rank", "Next Owner Action"], owner_review_blocker_action_rows or [["None", ""]])}
    </section>
    <section><h2>Owner Review Blocker Digest Trend v5.5</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_blocker_digest_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_blocker_digest_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_review_blocker_digest_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_review_blocker_digest_trend.get("window_count", 0)} 路 <span class="badge">same digest</span> {owner_review_blocker_digest_trend.get("consecutive_same_blocker_digest_count", 0)} 路 <span class="badge">transitions</span> {owner_review_blocker_digest_trend.get("transition_count", 0)} 路 <span class="badge">changed</span> {str(owner_review_blocker_digest_trend.get("changed_from_previous", False)).lower()} 路 <span class="badge">read only</span> {str(owner_review_blocker_digest_trend.get("read_only_owner_review_blocker_digest_trend", True)).lower()} 路 {_link(owner_paths.get("owner_review_blocker_digest_trend", ""), "owner_review_blocker_digest_trend_snapshot.json")} 路 {_link(owner_paths.get("owner_review_blocker_digest_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current blockers</span> {owner_review_blocker_digest_trend_current.get("total_blockers", 0)} 路 <span class="badge">current p0</span> {owner_review_blocker_digest_trend_current.get("p0_blockers", 0)} 路 <span class="badge">current batch</span> {owner_review_blocker_digest_trend_current.get("batch_blockers", 0)} 路 <span class="badge">delta</span> {html.escape(json.dumps(owner_review_blocker_digest_trend.get("delta_from_previous", {}), ensure_ascii=False))} 路 <span class="badge">no decisions applied</span> {str(owner_review_blocker_digest_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_blocker_digest_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no provider activation</span> {str(owner_review_blocker_digest_trend.get("no_provider_activation", True)).lower()} 路 <span class="badge">no routing switch</span> {str(owner_review_blocker_digest_trend.get("no_routing_auto_switch", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_blocker_digest_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Blockers", "P0", "Batch", "Forbidden Actions"], owner_review_blocker_digest_trend_rows or [["None", "", "0", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Blocker Guardrail Matrix v5.6</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_blocker_guardrail_matrix.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_blocker_guardrail_matrix.get("status", "")))} 路 <span class="badge">items</span> {owner_review_blocker_guardrail_matrix.get("source_item_count", 0)} 路 <span class="badge">queues</span> {owner_review_blocker_guardrail_matrix.get("queue_count", 0)} 路 <span class="badge">actions</span> {owner_review_blocker_guardrail_matrix.get("forbidden_action_count", 0)} 路 <span class="badge">p0 actions</span> {owner_review_blocker_guardrail_matrix.get("p0_guardrail_action_count", 0)} 路 <span class="badge">read only</span> {str(owner_review_blocker_guardrail_matrix.get("read_only_owner_review_blocker_guardrail_matrix", True)).lower()} 路 {_link(owner_paths.get("owner_review_blocker_guardrail_matrix", ""), "owner_review_blocker_guardrail_matrix.json")} 路 {_link(owner_paths.get("owner_review_blocker_guardrail_matrix_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_blocker_guardrail_matrix.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_blocker_guardrail_matrix.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no provider activation</span> {str(owner_review_blocker_guardrail_matrix.get("no_provider_activation", True)).lower()} 路 <span class="badge">no routing switch</span> {str(owner_review_blocker_guardrail_matrix.get("no_routing_auto_switch", True)).lower()} 路 <span class="badge">no filesystem cleanup</span> {str(owner_review_blocker_guardrail_matrix.get("no_filesystem_cleanup", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_blocker_guardrail_matrix.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Items", "Distinct Actions", "Action Counts"], owner_review_blocker_guardrail_queue_rows or [["None", "0", "0", ""]])}
      {_table(["Action", "Severity", "Total", "Queue Counts", "Priority Counts"], owner_review_blocker_guardrail_action_rows or [["None", "", "0", "", ""]])}
    </section>
    <section><h2>Owner Review Blocker Guardrail Matrix Trend v5.7</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_blocker_guardrail_matrix_trend.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_blocker_guardrail_matrix_trend.get("status", "")))} 路 <span class="badge">history</span> {owner_review_blocker_guardrail_matrix_trend.get("history_count", 0)} 路 <span class="badge">window</span> {owner_review_blocker_guardrail_matrix_trend.get("window_count", 0)} 路 <span class="badge">same matrix</span> {owner_review_blocker_guardrail_matrix_trend.get("consecutive_same_guardrail_matrix_count", 0)} 路 <span class="badge">transitions</span> {owner_review_blocker_guardrail_matrix_trend.get("transition_count", 0)} 路 <span class="badge">changed</span> {str(owner_review_blocker_guardrail_matrix_trend.get("changed_from_previous", False)).lower()} 路 <span class="badge">read only</span> {str(owner_review_blocker_guardrail_matrix_trend.get("read_only_owner_review_blocker_guardrail_matrix_trend", True)).lower()} 路 {_link(owner_paths.get("owner_review_blocker_guardrail_matrix_trend", ""), "owner_review_blocker_guardrail_matrix_trend_snapshot.json")} 路 {_link(owner_paths.get("owner_review_blocker_guardrail_matrix_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current items</span> {owner_review_blocker_guardrail_matrix_trend_current.get("source_item_count", 0)} 路 <span class="badge">current queues</span> {owner_review_blocker_guardrail_matrix_trend_current.get("queue_count", 0)} 路 <span class="badge">current actions</span> {owner_review_blocker_guardrail_matrix_trend_current.get("forbidden_action_count", 0)} 路 <span class="badge">current p0 actions</span> {owner_review_blocker_guardrail_matrix_trend_current.get("p0_guardrail_action_count", 0)} 路 <span class="badge">delta</span> {html.escape(json.dumps(owner_review_blocker_guardrail_matrix_trend.get("delta_from_previous", {}), ensure_ascii=False))} 路 <span class="badge">no decisions applied</span> {str(owner_review_blocker_guardrail_matrix_trend.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_blocker_guardrail_matrix_trend.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_blocker_guardrail_matrix_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Items", "Queues", "Actions", "P0 Actions"], owner_review_blocker_guardrail_matrix_trend_rows or [["None", "", "0", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Guardrail Action Drilldown v5.8</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_guardrail_action_drilldown.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(owner_review_guardrail_action_drilldown.get("status", "")))} 路 <span class="badge">items</span> {owner_review_guardrail_action_drilldown.get("source_item_count", 0)} 路 <span class="badge">actions</span> {owner_review_guardrail_action_drilldown.get("forbidden_action_count", 0)} 路 <span class="badge">p0 actions</span> {owner_review_guardrail_action_drilldown.get("p0_guardrail_action_count", 0)} 路 <span class="badge">matrix</span> {html.escape(str(owner_review_guardrail_action_drilldown.get("matrix_status", "")))} 路 <span class="badge">read only</span> {str(owner_review_guardrail_action_drilldown.get("read_only_owner_review_guardrail_action_drilldown", True)).lower()} 路 {_link(owner_paths.get("owner_review_guardrail_action_drilldown", ""), "owner_review_guardrail_action_drilldown.json")} 路 {_link(owner_paths.get("owner_review_guardrail_action_drilldown_md", ""), "markdown")} 路 {_link(owner_paths.get("owner_review_guardrail_action_drilldown_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_guardrail_action_drilldown.get("no_decisions_applied", True)).lower()} 路 <span class="badge">no decision file</span> {str(owner_review_guardrail_action_drilldown.get("no_decision_file_written", True)).lower()} 路 <span class="badge">no API calls</span> {str(owner_review_guardrail_action_drilldown.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no provider activation</span> {str(owner_review_guardrail_action_drilldown.get("no_provider_activation", True)).lower()} 路 <span class="badge">no routing switch</span> {str(owner_review_guardrail_action_drilldown.get("no_routing_auto_switch", True)).lower()} 路 <span class="badge">no writeback</span> {str(owner_review_guardrail_action_drilldown.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Action", "Severity", "Items", "Queues", "Queue Counts", "Priority Counts"], owner_review_guardrail_action_rows or [["None", "", "0", "0", "", ""]])}
      {_table(["Action", "Severity", "Queue", "Priority", "Item", "Subject", "Owner Action"], owner_review_guardrail_affected_rows or [["None", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Guardrail Action Drilldown Trend v5.9</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_guardrail_action_drilldown_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_guardrail_action_drilldown_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_guardrail_action_drilldown_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_guardrail_action_drilldown_trend.get("window_count", 0)} / <span class="badge">same drilldown</span> {owner_review_guardrail_action_drilldown_trend.get("consecutive_same_guardrail_action_drilldown_count", 0)} / <span class="badge">transitions</span> {owner_review_guardrail_action_drilldown_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_guardrail_action_drilldown_trend.get("changed_from_previous", False)).lower()} / <span class="badge">read only</span> {str(owner_review_guardrail_action_drilldown_trend.get("read_only_owner_review_guardrail_action_drilldown_trend", True)).lower()} / {_link(owner_paths.get("owner_review_guardrail_action_drilldown_trend", ""), "owner_review_guardrail_action_drilldown_trend_snapshot.json")} / {_link(owner_paths.get("owner_review_guardrail_action_drilldown_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current items</span> {owner_review_guardrail_action_drilldown_trend_current.get("source_item_count", 0)} / <span class="badge">current actions</span> {owner_review_guardrail_action_drilldown_trend_current.get("forbidden_action_count", 0)} / <span class="badge">current p0 actions</span> {owner_review_guardrail_action_drilldown_trend_current.get("p0_guardrail_action_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_guardrail_action_drilldown_trend.get("delta_from_previous", {}), ensure_ascii=False))} / <span class="badge">no decisions applied</span> {str(owner_review_guardrail_action_drilldown_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_guardrail_action_drilldown_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_guardrail_action_drilldown_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Items", "Actions", "P0 Actions"], owner_review_guardrail_action_drilldown_trend_rows or [["None", "", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Action Dependency Index v6.0</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_action_dependency_index.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_action_dependency_index.get("status", "")))} / <span class="badge">actions</span> {owner_review_action_dependency_index.get("source_action_count", 0)} / <span class="badge">items</span> {owner_review_action_dependency_index.get("source_item_count", 0)} / <span class="badge">p0 actions</span> {owner_review_action_dependency_index.get("p0_action_count", 0)} / <span class="badge">matrix</span> {html.escape(str(owner_review_action_dependency_index.get("matrix_status", "")))} / <span class="badge">read only</span> {str(owner_review_action_dependency_index.get("read_only_owner_review_action_dependency_index", True)).lower()} / {_link(owner_paths.get("owner_review_action_dependency_index", ""), "owner_review_action_dependency_index.json")} / {_link(owner_paths.get("owner_review_action_dependency_index_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_action_dependency_index.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_action_dependency_index.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_action_dependency_index.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_action_dependency_index.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_action_dependency_index.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Order", "Action", "Severity", "Items", "Queues", "Guardrails", "Owner Gate", "Automation"], owner_review_action_dependency_rows or [["None", "", "", "0", "0", "", "", ""]])}
      {_table(["Action", "Queue", "Items", "Domains", "Priority Bands", "Matched"], owner_review_action_dependency_queue_rows or [["None", "", "0", "", "", ""]])}
    </section>
    <section><h2>Owner Review Action Dependency Trend v6.1</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_action_dependency_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_action_dependency_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_action_dependency_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_action_dependency_trend.get("window_count", 0)} / <span class="badge">same index</span> {owner_review_action_dependency_trend.get("consecutive_same_dependency_index_count", 0)} / <span class="badge">transitions</span> {owner_review_action_dependency_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_action_dependency_trend.get("changed_from_previous", False)).lower()} / <span class="badge">read only</span> {str(owner_review_action_dependency_trend.get("read_only_owner_review_action_dependency_trend", True)).lower()} / {_link(owner_paths.get("owner_review_action_dependency_trend", ""), "owner_review_action_dependency_trend_snapshot.json")} / {_link(owner_paths.get("owner_review_action_dependency_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current actions</span> {owner_review_action_dependency_trend_current.get("source_action_count", 0)} / <span class="badge">current items</span> {owner_review_action_dependency_trend_current.get("source_item_count", 0)} / <span class="badge">current p0 actions</span> {owner_review_action_dependency_trend_current.get("p0_action_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_action_dependency_trend.get("delta_from_previous", {}), ensure_ascii=False))} / <span class="badge">no decisions applied</span> {str(owner_review_action_dependency_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_action_dependency_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_action_dependency_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Actions", "Items", "P0 Actions"], owner_review_action_dependency_trend_rows or [["None", "", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Action Dependency Coverage v6.2</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_action_dependency_coverage.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_action_dependency_coverage.get("status", "")))} / <span class="badge">queues</span> {owner_review_action_dependency_coverage.get("queue_count", 0)} / <span class="badge">covered</span> {owner_review_action_dependency_coverage.get("covered_queue_count", 0)} / <span class="badge">uncovered</span> {owner_review_action_dependency_coverage.get("uncovered_queue_count", 0)} / <span class="badge">pending items</span> {owner_review_action_dependency_coverage.get("pending_item_count", 0)} / <span class="badge">read only</span> {str(owner_review_action_dependency_coverage.get("read_only_owner_review_action_dependency_coverage", True)).lower()} / {_link(owner_paths.get("owner_review_action_dependency_coverage", ""), "owner_review_action_dependency_coverage.json")} / {_link(owner_paths.get("owner_review_action_dependency_coverage_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_action_dependency_coverage.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_action_dependency_coverage.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_action_dependency_coverage.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_action_dependency_coverage.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_action_dependency_coverage.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Domain", "Exists", "Pending", "Covered", "Actions", "Missing", "Automation Blocked", "Owner Gate"], owner_review_action_dependency_coverage_rows or [["None", "", "", "0", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Action Dependency Coverage Trend v6.3</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_action_dependency_coverage_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_action_dependency_coverage_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_action_dependency_coverage_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_action_dependency_coverage_trend.get("window_count", 0)} / <span class="badge">same coverage</span> {owner_review_action_dependency_coverage_trend.get("consecutive_same_dependency_coverage_count", 0)} / <span class="badge">transitions</span> {owner_review_action_dependency_coverage_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_action_dependency_coverage_trend.get("changed_from_previous", False)).lower()} / <span class="badge">read only</span> {str(owner_review_action_dependency_coverage_trend.get("read_only_owner_review_action_dependency_coverage_trend", True)).lower()} / {_link(owner_paths.get("owner_review_action_dependency_coverage_trend", ""), "owner_review_action_dependency_coverage_trend_snapshot.json")} / {_link(owner_paths.get("owner_review_action_dependency_coverage_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current queues</span> {owner_review_action_dependency_coverage_trend_current.get("queue_count", 0)} / <span class="badge">current covered</span> {owner_review_action_dependency_coverage_trend_current.get("covered_queue_count", 0)} / <span class="badge">current uncovered</span> {owner_review_action_dependency_coverage_trend_current.get("uncovered_queue_count", 0)} / <span class="badge">current pending</span> {owner_review_action_dependency_coverage_trend_current.get("pending_item_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_action_dependency_coverage_trend.get("delta_from_previous", {}), ensure_ascii=False))} / <span class="badge">no decisions applied</span> {str(owner_review_action_dependency_coverage_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_action_dependency_coverage_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_action_dependency_coverage_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Queues", "Covered", "Uncovered", "Pending"], owner_review_action_dependency_coverage_trend_rows or [["None", "", "0", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Coverage SLA Consistency v6.4</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_coverage_sla_consistency.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_coverage_sla_consistency.get("status", "")))} / <span class="badge">queues</span> {owner_review_coverage_sla_consistency.get("queue_count", 0)} / <span class="badge">consistent</span> {owner_review_coverage_sla_consistency.get("consistent_queue_count", 0)} / <span class="badge">inconsistent</span> {owner_review_coverage_sla_consistency.get("inconsistent_queue_count", 0)} / <span class="badge">pending mismatches</span> {owner_review_coverage_sla_consistency.get("pending_mismatch_count", 0)} / <span class="badge">read only</span> {str(owner_review_coverage_sla_consistency.get("read_only_owner_review_coverage_sla_consistency", True)).lower()} / {_link(owner_paths.get("owner_review_coverage_sla_consistency", ""), "owner_review_coverage_sla_consistency.json")} / {_link(owner_paths.get("owner_review_coverage_sla_consistency_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_coverage_sla_consistency.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_coverage_sla_consistency.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_coverage_sla_consistency.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_coverage_sla_consistency.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_coverage_sla_consistency.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Domain", "Coverage Pending", "Aging Pending", "SLA Pending", "Aging", "SLA Band", "Consistent"], owner_review_coverage_sla_consistency_rows or [["None", "", "0", "", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Coverage SLA Consistency Trend v6.5</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_coverage_sla_consistency_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_coverage_sla_consistency_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_coverage_sla_consistency_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_coverage_sla_consistency_trend.get("window_count", 0)} / <span class="badge">same consistency</span> {owner_review_coverage_sla_consistency_trend.get("consecutive_same_coverage_sla_consistency_count", 0)} / <span class="badge">transitions</span> {owner_review_coverage_sla_consistency_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_coverage_sla_consistency_trend.get("changed_from_previous", False)).lower()} / <span class="badge">read only</span> {str(owner_review_coverage_sla_consistency_trend.get("read_only_owner_review_coverage_sla_consistency_trend", True)).lower()} / {_link(owner_paths.get("owner_review_coverage_sla_consistency_trend", ""), "owner_review_coverage_sla_consistency_trend_snapshot.json")} / {_link(owner_paths.get("owner_review_coverage_sla_consistency_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current queues</span> {owner_review_coverage_sla_consistency_trend_current.get("queue_count", 0)} / <span class="badge">current consistent</span> {owner_review_coverage_sla_consistency_trend_current.get("consistent_queue_count", 0)} / <span class="badge">current inconsistent</span> {owner_review_coverage_sla_consistency_trend_current.get("inconsistent_queue_count", 0)} / <span class="badge">current mismatches</span> {owner_review_coverage_sla_consistency_trend_current.get("pending_mismatch_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_coverage_sla_consistency_trend.get("delta_from_previous", {}), ensure_ascii=False))} / <span class="badge">no decisions applied</span> {str(owner_review_coverage_sla_consistency_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_coverage_sla_consistency_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_coverage_sla_consistency_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Queues", "Consistent", "Inconsistent", "Mismatches"], owner_review_coverage_sla_consistency_trend_rows or [["None", "", "0", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Pending Decision Freeze Guard v6.6</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_pending_decision_freeze_guard.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_pending_decision_freeze_guard.get("status", "")))} / <span class="badge">pending total</span> {owner_pending_decision_freeze_guard.get("pending_total", 0)} / <span class="badge">frozen queues</span> {owner_pending_decision_freeze_guard.get("frozen_queue_count", 0)} / <span class="badge">unfrozen queues</span> {owner_pending_decision_freeze_guard.get("unfrozen_queue_count", 0)} / <span class="badge">decision files present</span> {owner_pending_decision_freeze_guard.get("decision_file_present_count", 0)} / <span class="badge">trend stable</span> {str(owner_pending_decision_freeze_guard.get("coverage_sla_consistency_trend_stable", False)).lower()} / {_link(owner_paths.get("owner_pending_decision_freeze_guard", ""), "owner_pending_decision_freeze_guard.json")} / {_link(owner_paths.get("owner_pending_decision_freeze_guard_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_pending_decision_freeze_guard.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_pending_decision_freeze_guard.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_pending_decision_freeze_guard.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_pending_decision_freeze_guard.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_pending_decision_freeze_guard.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Domain", "Pending", "Queue Count", "Frozen", "Failed Checks"], owner_pending_decision_freeze_guard_rows or [["None", "", "0", "0", "", ""]])}
      {_table(["Decision File", "Exists", "Must Be Absent"], owner_pending_decision_freeze_guard_file_rows or [["None", "", ""]])}
    </section>
    <section><h2>Owner Pending Decision Freeze Guard Trend v6.7</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_pending_decision_freeze_guard_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_pending_decision_freeze_guard_trend.get("status", "")))} / <span class="badge">history</span> {owner_pending_decision_freeze_guard_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_pending_decision_freeze_guard_trend.get("window_count", 0)} / <span class="badge">same freeze</span> {owner_pending_decision_freeze_guard_trend.get("consecutive_same_freeze_guard_count", 0)} / <span class="badge">transitions</span> {owner_pending_decision_freeze_guard_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_pending_decision_freeze_guard_trend.get("changed_from_previous", False)).lower()} / {_link(owner_paths.get("owner_pending_decision_freeze_guard_trend", ""), "owner_pending_decision_freeze_guard_trend_snapshot.json")} / {_link(owner_paths.get("owner_pending_decision_freeze_guard_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current pending</span> {owner_pending_decision_freeze_guard_trend_current.get("pending_total", 0)} / <span class="badge">current frozen</span> {owner_pending_decision_freeze_guard_trend_current.get("frozen_queue_count", 0)} / <span class="badge">current unfrozen</span> {owner_pending_decision_freeze_guard_trend_current.get("unfrozen_queue_count", 0)} / <span class="badge">decision files present</span> {owner_pending_decision_freeze_guard_trend_current.get("decision_file_present_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_pending_decision_freeze_guard_trend.get("delta_from_previous", {}), ensure_ascii=False))} / <span class="badge">no decisions applied</span> {str(owner_pending_decision_freeze_guard_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_pending_decision_freeze_guard_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no writeback</span> {str(owner_pending_decision_freeze_guard_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Pending", "Frozen", "Unfrozen", "Decision Files", "SLA Stable"], owner_pending_decision_freeze_guard_trend_rows or [["None", "", "0", "0", "0", "0", ""]])}
    </section>
    <section><h2>Owner Review Packet Freshness Cross Check v6.8</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_packet_freshness_cross_check.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_packet_freshness_cross_check.get("status", "")))} / <span class="badge">skew seconds</span> {owner_review_packet_freshness_cross_check.get("generated_skew_seconds", "")} / <span class="badge">max skew</span> {owner_review_packet_freshness_cross_check.get("max_generated_skew_seconds", 0)} / <span class="badge">failed checks</span> {len(owner_review_packet_freshness_failed_checks)} / <span class="badge">failed guard checks</span> {len(owner_review_packet_freshness_failed_guard_checks)} / {_link(owner_paths.get("owner_review_packet_freshness_cross_check", ""), "owner_review_packet_freshness_cross_check.json")} / {_link(owner_paths.get("owner_review_packet_freshness_cross_check_audit", ""), "audit")}</p>
      <p><span class="badge">packet items</span> {owner_review_packet_freshness_item_counts.get("packet_review_item_count", 0)} / <span class="badge">checklist items</span> {owner_review_packet_freshness_item_counts.get("review_checklist_item_count", 0)} / <span class="badge">drilldown items</span> {owner_review_packet_freshness_item_counts.get("drilldown_pending_owner_item_count", 0)} / <span class="badge">freeze pending</span> {owner_review_packet_freshness_item_counts.get("freeze_pending_total", 0)} / <span class="badge">packet groups</span> {owner_review_packet_freshness_queue_counts.get("packet_group_count", 0)} / <span class="badge">freeze queues</span> {owner_review_packet_freshness_queue_counts.get("freeze_queue_count", 0)}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_packet_freshness_cross_check.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_packet_freshness_cross_check.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_packet_freshness_cross_check.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_packet_freshness_cross_check.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_packet_freshness_cross_check.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Artifact", "Exists", "Status", "Generated", "Schema"], owner_review_packet_freshness_rows or [["None", "", "", "", ""]])}
      <p><strong>Failed checks:</strong> {html.escape(", ".join(owner_review_packet_freshness_failed_checks + owner_review_packet_freshness_failed_guard_checks) or "none")}</p>
    </section>
    <section><h2>Owner Review Packet Freshness Trend v6.9</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_packet_freshness_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_packet_freshness_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_packet_freshness_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_packet_freshness_trend.get("window_count", 0)} / <span class="badge">same freshness</span> {owner_review_packet_freshness_trend.get("consecutive_same_freshness_count", 0)} / <span class="badge">transitions</span> {owner_review_packet_freshness_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_packet_freshness_trend.get("changed_from_previous", False)).lower()} / {_link(owner_paths.get("owner_review_packet_freshness_trend", ""), "owner_review_packet_freshness_trend_snapshot.json")} / {_link(owner_paths.get("owner_review_packet_freshness_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current skew</span> {owner_review_packet_freshness_trend_current.get("generated_skew_seconds", 0)} / <span class="badge">packet items</span> {owner_review_packet_freshness_trend_current.get("packet_review_item_count", 0)} / <span class="badge">freeze pending</span> {owner_review_packet_freshness_trend_current.get("freeze_pending_total", 0)} / <span class="badge">failed checks</span> {owner_review_packet_freshness_trend_current.get("failed_check_count", 0)} / <span class="badge">failed guards</span> {owner_review_packet_freshness_trend_current.get("failed_guard_check_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_packet_freshness_trend.get("delta_from_previous", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_packet_freshness_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_packet_freshness_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_packet_freshness_trend.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_packet_freshness_trend.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_packet_freshness_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Skew", "Packet Items", "Freeze Pending", "Packet Groups", "Freeze Queues", "Failed Checks", "Failed Guards"], owner_review_packet_freshness_trend_rows or [["None", "", "0", "0", "0", "0", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Evidence Manifest v7.0</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_evidence_manifest_v70.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_evidence_manifest_v70.get("status", "")))} / <span class="badge">artifacts</span> {owner_review_evidence_manifest_v70.get("artifact_count", 0)} / <span class="badge">missing</span> {owner_review_evidence_manifest_v70.get("missing_count", 0)} / <span class="badge">empty</span> {owner_review_evidence_manifest_v70.get("empty_count", 0)} / <span class="badge">duplicate hashes</span> {owner_review_evidence_manifest_v70.get("duplicate_hash_group_count", 0)} / <span class="badge">failed checks</span> {len(owner_review_evidence_manifest_failed_checks)} / {_link(owner_paths.get("owner_review_evidence_manifest_v70", ""), "owner_review_evidence_manifest.json")} / {_link(owner_paths.get("owner_review_evidence_manifest_v70_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_evidence_manifest_v70.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_evidence_manifest_v70.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_evidence_manifest_v70.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_evidence_manifest_v70.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_evidence_manifest_v70.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Artifact", "Exists", "Bytes", "Status", "Generated", "SHA256"], owner_review_evidence_manifest_rows or [["None", "", "0", "", "", ""]])}
      <p><strong>Failed checks:</strong> {html.escape(", ".join(owner_review_evidence_manifest_failed_checks) or "none")}</p>
    </section>
    <section><h2>Owner Review Evidence Manifest Trend v7.1</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_evidence_manifest_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_evidence_manifest_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_evidence_manifest_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_evidence_manifest_trend.get("window_count", 0)} / <span class="badge">same manifest</span> {owner_review_evidence_manifest_trend.get("consecutive_same_manifest_count", 0)} / <span class="badge">transitions</span> {owner_review_evidence_manifest_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_evidence_manifest_trend.get("changed_from_previous", False)).lower()} / {_link(owner_paths.get("owner_review_evidence_manifest_trend", ""), "owner_review_evidence_manifest_trend_snapshot.json")} / {_link(owner_paths.get("owner_review_evidence_manifest_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current artifacts</span> {owner_review_evidence_manifest_trend_current.get("artifact_count", 0)} / <span class="badge">current missing</span> {owner_review_evidence_manifest_trend_current.get("missing_count", 0)} / <span class="badge">current empty</span> {owner_review_evidence_manifest_trend_current.get("empty_count", 0)} / <span class="badge">duplicate hashes</span> {owner_review_evidence_manifest_trend_current.get("duplicate_hash_group_count", 0)} / <span class="badge">digest</span> {html.escape(str(owner_review_evidence_manifest_trend_current.get("manifest_digest", ""))[:16])} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_evidence_manifest_trend.get("delta_from_previous", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_evidence_manifest_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_evidence_manifest_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_evidence_manifest_trend.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_evidence_manifest_trend.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_evidence_manifest_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Artifacts", "Missing", "Empty", "Duplicate Hashes", "Digest"], owner_review_evidence_manifest_trend_rows or [["None", "", "0", "0", "0", "0", ""]])}
    </section>
    <section><h2>Owner Review Decision Readiness Seal v7.2</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_decision_readiness_seal.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_decision_readiness_seal.get("status", "")))} / <span class="badge">mode</span> {html.escape(str(owner_review_decision_readiness_seal.get("owner_decision_mode", "")))} / <span class="badge">pending total</span> {owner_review_decision_readiness_seal.get("pending_total", 0)} / <span class="badge">ready trends</span> {owner_review_decision_readiness_seal.get("ready_trend_count", 0)} / <span class="badge">transition warnings</span> {owner_review_decision_readiness_seal.get("transition_warning_count", 0)} / <span class="badge">decision files present</span> {owner_review_decision_readiness_seal.get("decision_file_present_count", 0)} / <span class="badge">failed checks</span> {len(owner_review_decision_readiness_failed_checks)} / {_link(owner_paths.get("owner_review_decision_readiness_seal", ""), "owner_review_decision_readiness_seal.json")} / {_link(owner_paths.get("owner_review_decision_readiness_seal_audit", ""), "audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_decision_readiness_seal.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_decision_readiness_seal.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_decision_readiness_seal.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_decision_readiness_seal.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_decision_readiness_seal.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Trend", "Status", "Consecutive", "Required", "Transitions", "Warning", "Ready"], owner_review_decision_readiness_trend_rows or [["None", "", "0", "0", "0", "", ""]])}
      {_table(["Decision File", "Exists", "Must Be Absent"], owner_review_decision_readiness_file_rows or [["None", "", ""]])}
      <p><strong>Failed checks:</strong> {html.escape(", ".join(owner_review_decision_readiness_failed_checks) or "none")}</p>
    </section>
    <section><h2>Owner Review Decision Readiness Seal Trend v7.3</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_decision_readiness_seal_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_decision_readiness_seal_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_decision_readiness_seal_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_decision_readiness_seal_trend.get("window_count", 0)} / <span class="badge">same seal</span> {owner_review_decision_readiness_seal_trend.get("consecutive_same_seal_count", 0)} / <span class="badge">transitions</span> {owner_review_decision_readiness_seal_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_decision_readiness_seal_trend.get("changed_from_previous", False)).lower()} / {_link(owner_paths.get("owner_review_decision_readiness_seal_trend", ""), "owner_review_decision_readiness_seal_trend_snapshot.json")} / {_link(owner_paths.get("owner_review_decision_readiness_seal_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current pending</span> {owner_review_decision_readiness_seal_trend_current.get("pending_total", 0)} / <span class="badge">ready trends</span> {owner_review_decision_readiness_seal_trend_current.get("ready_trend_count", 0)} / <span class="badge">transition warnings</span> {owner_review_decision_readiness_seal_trend_current.get("transition_warning_count", 0)} / <span class="badge">decision files present</span> {owner_review_decision_readiness_seal_trend_current.get("decision_file_present_count", 0)} / <span class="badge">failed checks</span> {owner_review_decision_readiness_seal_trend_current.get("failed_check_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_decision_readiness_seal_trend.get("delta_from_previous", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_decision_readiness_seal_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_decision_readiness_seal_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_decision_readiness_seal_trend.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_decision_readiness_seal_trend.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_decision_readiness_seal_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Pending", "Ready Trends", "Warnings", "Decision Files", "Failed Checks"], owner_review_decision_readiness_seal_trend_rows or [["None", "", "0", "0", "0", "0", "0"]])}
    </section>
    <section><h2>Owner Review Decision Readiness Seal Ops Digest v7.4</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_decision_readiness_seal_ops_digest.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_decision_readiness_seal_ops_digest.get("status", "")))} / <span class="badge">owner next action</span> {html.escape(str(owner_review_decision_readiness_seal_ops_digest.get("owner_next_action", "")))} / <span class="badge">automation</span> {html.escape(str(owner_review_decision_readiness_seal_ops_digest.get("automation_state", "")))} / <span class="badge">pending owner</span> {owner_review_decision_readiness_seal_ops_digest.get("pending_owner_items", 0)} / {_link(owner_paths.get("owner_review_decision_readiness_seal_ops_digest", ""), "ops_digest.json")} / {_link(owner_paths.get("owner_review_decision_readiness_seal_ops_digest_md", ""), "md")} / {_link(owner_paths.get("owner_review_decision_readiness_seal_ops_digest_audit", ""), "audit")}</p>
      <p><span class="badge">seal</span> {html.escape(str(owner_review_decision_readiness_seal_ops_digest.get("seal_status", "")))} / <span class="badge">trend</span> {html.escape(str(owner_review_decision_readiness_seal_ops_digest.get("trend_status", "")))} / <span class="badge">ready trends</span> {owner_review_decision_readiness_seal_ops_digest.get("ready_trend_count", 0)} / <span class="badge">warnings</span> {owner_review_decision_readiness_seal_ops_digest.get("transition_warning_count", 0)} / <span class="badge">decision files present</span> {owner_review_decision_readiness_seal_ops_digest.get("decision_file_present_count", 0)} / <span class="badge">failed checks</span> {owner_review_decision_readiness_seal_ops_digest.get("failed_check_count", 0)}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_decision_readiness_seal_ops_digest.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_decision_readiness_seal_ops_digest.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_decision_readiness_seal_ops_digest.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_decision_readiness_seal_ops_digest.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_decision_readiness_seal_ops_digest.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Trend", "Status", "Ready", "Consecutive", "Transitions", "Warning", "Failed Checks"], owner_review_decision_readiness_seal_ops_digest_trend_rows or [["None", "", "", "0", "0", "", ""]])}
      {_table(["Decision File", "Exists", "Must Be Absent", "Compliant"], owner_review_decision_readiness_seal_ops_digest_file_rows or [["None", "", "", ""]])}
      <p><strong>Forbidden automatic actions:</strong> {html.escape(", ".join(owner_review_decision_readiness_seal_ops_digest.get("forbidden_auto_actions", []) or []) or "none")}</p>
    </section>
    <section><h2>Owner Review Dry-Run Decision Plan v7.5</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_dry_run_decision_plan.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_dry_run_decision_plan.get("status", "")))} / <span class="badge">packet</span> {html.escape(str(owner_review_dry_run_decision_plan.get("packet_status", "")))} / <span class="badge">readiness</span> {html.escape(str(owner_review_dry_run_decision_plan.get("readiness_status", "")))} / <span class="badge">automation</span> {html.escape(str(owner_review_dry_run_decision_plan.get("automation_state", "")))} / <span class="badge">items</span> {owner_review_dry_run_decision_plan.get("total_items", 0)} / <span class="badge">queues</span> {owner_review_dry_run_decision_plan.get("queue_count", 0)} / {_link(owner_paths.get("owner_review_dry_run_decision_plan", ""), "dry_run_decision_plan.json")} / {_link(owner_paths.get("owner_review_dry_run_decision_plan_md", ""), "md")} / {_link(owner_paths.get("owner_review_dry_run_decision_plan_audit", ""), "audit")}</p>
      <p><span class="badge">decision file preview only</span> {str(owner_review_dry_run_decision_plan.get("decision_file_preview_only", True)).lower()} / <span class="badge">no decisions applied</span> {str(owner_review_dry_run_decision_plan.get("no_decisions_applied", True)).lower()} / <span class="badge">no decision files</span> {str(owner_review_dry_run_decision_plan.get("no_decision_file_written", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_dry_run_decision_plan.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_dry_run_decision_plan.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_dry_run_decision_plan.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_dry_run_decision_plan.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Items", "Decision File Required For Actual Apply", "Options", "Forbidden Auto Actions", "Dry Run Only"], owner_review_dry_run_decision_plan_rows or [["None", "0", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Dry-Run Decision Plan Trend v7.6</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_dry_run_decision_plan_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_dry_run_decision_plan_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_dry_run_decision_plan_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_dry_run_decision_plan_trend.get("window_count", 0)} / <span class="badge">same plan</span> {owner_review_dry_run_decision_plan_trend.get("consecutive_same_plan_count", 0)} / <span class="badge">transitions</span> {owner_review_dry_run_decision_plan_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_dry_run_decision_plan_trend.get("changed_from_previous", False)).lower()} / {_link(owner_paths.get("owner_review_dry_run_decision_plan_trend", ""), "dry_run_decision_plan_trend.json")} / {_link(owner_paths.get("owner_review_dry_run_decision_plan_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current status</span> {html.escape(str(owner_review_dry_run_decision_plan_trend_current.get("status", "")))} / <span class="badge">current items</span> {owner_review_dry_run_decision_plan_trend_current.get("total_items", 0)} / <span class="badge">current queues</span> {owner_review_dry_run_decision_plan_trend_current.get("queue_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_dry_run_decision_plan_trend.get("delta_from_previous", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_dry_run_decision_plan_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no decision files</span> {str(owner_review_dry_run_decision_plan_trend.get("no_decision_file_written", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_dry_run_decision_plan_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_dry_run_decision_plan_trend.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_dry_run_decision_plan_trend.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_dry_run_decision_plan_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Items", "Queues", "No Decisions Applied"], owner_review_dry_run_decision_plan_trend_rows or [["None", "", "0", "0", ""]])}
    </section>
    <section><h2>Owner Review Dry-Run Decision Plan Coverage v7.7</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_dry_run_decision_plan_coverage.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_dry_run_decision_plan_coverage.get("status", "")))} / <span class="badge">packet</span> {html.escape(str(owner_review_dry_run_decision_plan_coverage.get("packet_status", "")))} / <span class="badge">plan</span> {html.escape(str(owner_review_dry_run_decision_plan_coverage.get("plan_status", "")))} / <span class="badge">trend</span> {html.escape(str(owner_review_dry_run_decision_plan_coverage.get("trend_status", "")))} / <span class="badge">packet items</span> {owner_review_dry_run_decision_plan_coverage.get("packet_item_count", 0)} / <span class="badge">plan items</span> {owner_review_dry_run_decision_plan_coverage.get("plan_item_count", 0)} / <span class="badge">failed checks</span> {len(owner_review_dry_run_decision_plan_coverage.get("failed_checks", []) or [])} / {_link(owner_paths.get("owner_review_dry_run_decision_plan_coverage", ""), "dry_run_decision_plan_coverage.json")} / {_link(owner_paths.get("owner_review_dry_run_decision_plan_coverage_audit", ""), "audit")}</p>
      <p><span class="badge">missing queues</span> {html.escape(", ".join(owner_review_dry_run_decision_plan_coverage.get("missing_queues", []) or []) or "none")} / <span class="badge">extra queues</span> {html.escape(", ".join(owner_review_dry_run_decision_plan_coverage.get("extra_queues", []) or []) or "none")} / <span class="badge">count mismatches</span> {html.escape(", ".join(owner_review_dry_run_decision_plan_coverage.get("item_count_mismatches", []) or []) or "none")} / <span class="badge">option mismatches</span> {html.escape(", ".join(owner_review_dry_run_decision_plan_coverage.get("option_mismatches", []) or []) or "none")}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_dry_run_decision_plan_coverage.get("no_decisions_applied", True)).lower()} / <span class="badge">no decision files</span> {str(owner_review_dry_run_decision_plan_coverage.get("no_decision_file_written", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_dry_run_decision_plan_coverage.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_dry_run_decision_plan_coverage.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_dry_run_decision_plan_coverage.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_dry_run_decision_plan_coverage.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["Queue", "Packet Items", "Packet Group", "Plan Items", "Count Match", "Option Match", "Dry Run", "No Queue Mutation"], owner_review_dry_run_decision_plan_coverage_rows or [["None", "0", "0", "0", "", "", "", ""]])}
    </section>
    <section><h2>Owner Review Dry-Run Decision Plan Coverage Trend v7.8</h2>
      <p><span class="badge">schema</span> {html.escape(str(owner_review_dry_run_decision_plan_coverage_trend.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(owner_review_dry_run_decision_plan_coverage_trend.get("status", "")))} / <span class="badge">history</span> {owner_review_dry_run_decision_plan_coverage_trend.get("history_count", 0)} / <span class="badge">window</span> {owner_review_dry_run_decision_plan_coverage_trend.get("window_count", 0)} / <span class="badge">same coverage</span> {owner_review_dry_run_decision_plan_coverage_trend.get("consecutive_same_coverage_count", 0)} / <span class="badge">transitions</span> {owner_review_dry_run_decision_plan_coverage_trend.get("transition_count", 0)} / <span class="badge">changed</span> {str(owner_review_dry_run_decision_plan_coverage_trend.get("changed_from_previous", False)).lower()} / {_link(owner_paths.get("owner_review_dry_run_decision_plan_coverage_trend", ""), "coverage_trend.json")} / {_link(owner_paths.get("owner_review_dry_run_decision_plan_coverage_trend_audit", ""), "audit")}</p>
      <p><span class="badge">current status</span> {html.escape(str(owner_review_dry_run_decision_plan_coverage_trend_current.get("status", "")))} / <span class="badge">packet items</span> {owner_review_dry_run_decision_plan_coverage_trend_current.get("packet_item_count", 0)} / <span class="badge">plan items</span> {owner_review_dry_run_decision_plan_coverage_trend_current.get("plan_item_count", 0)} / <span class="badge">failed checks</span> {owner_review_dry_run_decision_plan_coverage_trend_current.get("failed_check_count", 0)} / <span class="badge">delta</span> {html.escape(json.dumps(owner_review_dry_run_decision_plan_coverage_trend.get("delta_from_previous", {}), ensure_ascii=False))}</p>
      <p><span class="badge">no decisions applied</span> {str(owner_review_dry_run_decision_plan_coverage_trend.get("no_decisions_applied", True)).lower()} / <span class="badge">no decision files</span> {str(owner_review_dry_run_decision_plan_coverage_trend.get("no_decision_file_written", True)).lower()} / <span class="badge">no API calls</span> {str(owner_review_dry_run_decision_plan_coverage_trend.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(owner_review_dry_run_decision_plan_coverage_trend.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(owner_review_dry_run_decision_plan_coverage_trend.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(owner_review_dry_run_decision_plan_coverage_trend.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["TS", "Status", "Packet Items", "Plan Items", "Failed Checks"], owner_review_dry_run_decision_plan_coverage_trend_rows or [["None", "", "0", "0", "0"]])}
    </section>
    <section><h2>Knowledge Trust Pipeline v0.1-v0.4</h2>
      <p><span class="badge">registry</span> {html.escape(str(knowledge_registry.get("status", "")))} / <span class="badge">items</span> {knowledge_registry.get("item_count", 0)} / <span class="badge">quarantine</span> {knowledge_registry.get("quarantine_count", 0)} / <span class="badge">trusted</span> {knowledge_registry.get("trusted_count", 0)} / {_link(knowledge_paths.get("registry", ""), "registry")} / {_link(knowledge_paths.get("registry_audit", ""), "audit")}</p>
      <p><span class="badge">review packet</span> {html.escape(str(knowledge_review_packet.get("status", "")))} / <span class="badge">review items</span> {knowledge_review_packet.get("review_item_count", 0)} / <span class="badge">sustained recommendations</span> {knowledge_review_packet.get("sustained_candidate_recommendation_count", 0)} / {_link(knowledge_paths.get("review_packet", ""), "review_packet")} / {_link(knowledge_paths.get("review_packet_audit", ""), "audit")}</p>
      <p><span class="badge">sustained gate</span> {html.escape(str(knowledge_sustained_gate.get("status", "")))} / <span class="badge">ready</span> {knowledge_sustained_gate.get("ready_count", 0)} / <span class="badge">blocked</span> {knowledge_sustained_gate.get("blocked_count", 0)} / {_link(knowledge_paths.get("sustained_gate", ""), "sustained_gate")} / {_link(knowledge_paths.get("sustained_gate_audit", ""), "audit")}</p>
      <p><span class="badge">trusted owner queue</span> {html.escape(str(knowledge_trusted_queue.get("status", "")))} / <span class="badge">pending owner</span> {knowledge_trusted_queue.get("pending_count", 0)} / <span class="badge">decision file written</span> {str(not knowledge_trusted_queue.get("no_decision_file_written", True)).lower()} / <span class="badge">no trusted promotion</span> {str(knowledge_trusted_queue.get("no_trusted_promotion", True)).lower()} / {_link(knowledge_paths.get("trusted_queue", ""), "trusted_queue")} / {_link(knowledge_paths.get("trusted_queue_audit", ""), "audit")}</p>
      {_table(["Quarantine ID", "Type", "Path Exists", "Source", "Title"], knowledge_quarantine_rows or [["None", "", "", "", ""]])}
      {_table(["Review ID", "Source Grade", "Risk", "Recommendation", "Failed Checks"], knowledge_review_rows or [["None", "", "", "", ""]])}
      {_table(["Owner Queue ID", "Risk", "Source Grade", "Status", "Options"], knowledge_owner_queue_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Dashboard Refresh Profiler v0.1</h2>
      <p><span class="badge">schema</span> {html.escape(str(dashboard_profile.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(dashboard_profile.get("status", "")))} / <span class="badge">total ms</span> {dashboard_profile.get("total_ms", 0)} / <span class="badge">collect ms</span> {dashboard_profile.get("collect_ms", 0)} / <span class="badge">write ms</span> {dashboard_profile.get("write_dashboard_ms", 0)} / {_link(dashboard_perf_paths.get("profile", ""), "profile")} / {_link(dashboard_perf_paths.get("audit", ""), "audit")}</p>
      <p><span class="badge">projects</span> {dashboard_profile.get("project_count", 0)} / <span class="badge">mcps</span> {dashboard_profile.get("mcp_count", 0)} / <span class="badge">owner sections</span> {dashboard_profile.get("owner_decision_sections", 0)} / <span class="badge">model sections</span> {dashboard_profile.get("model_adapter_sections", 0)} / <span class="badge">knowledge sections</span> {dashboard_profile.get("knowledge_trust_sections", 0)}</p>
      <p><span class="badge">no decisions applied</span> {str(dashboard_profile.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(dashboard_profile.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(dashboard_profile.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(dashboard_profile.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(dashboard_profile.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      <h3>Refresh Manifest v0.2</h3>
      <p><span class="badge">schema</span> {html.escape(str(dashboard_manifest.get("schema_version", "")))} / <span class="badge">modules</span> {dashboard_manifest.get("summary", {}).get("module_count", 0)} / <span class="badge">unchanged</span> {dashboard_manifest.get("summary", {}).get("unchanged_count", 0)} / <span class="badge">changed</span> {dashboard_manifest.get("summary", {}).get("changed_count", 0)} / <span class="badge">new</span> {dashboard_manifest.get("summary", {}).get("new_count", 0)} / {_link(dashboard_perf_paths.get("manifest", ""), "manifest")} / {_link(dashboard_perf_paths.get("manifest_audit", ""), "manifest audit")}</p>
      {_table(["module", "status", "present", "missing", "bytes", "observe only", "skip allowed", "hash"], dashboard_manifest_rows or [["None", "", "0", "0", "0", "", "", ""]])}
      <h3>Skip Unchanged Heavy Modules v0.3 / Lazy Import v0.5 / Freshness v0.6</h3>
      <p><span class="badge">schema</span> {html.escape(str(dashboard_cache.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(dashboard_cache.get("status", "")))} / <span class="badge">skipped</span> {dashboard_cache.get("summary", {}).get("skipped_count", 0)} / <span class="badge">rebuilt</span> {dashboard_cache.get("summary", {}).get("rebuilt_count", 0)} / <span class="badge">html rewritten</span> {str(dashboard_cache.get("html_rewritten", True)).lower()} / {_link(dashboard_perf_paths.get("cache", ""), "cache")} / {_link(dashboard_perf_paths.get("cache_audit", ""), "cache audit")}</p>
      <p><span class="badge">no decisions applied</span> {str(dashboard_cache.get("no_decisions_applied", True)).lower()} / <span class="badge">no API calls</span> {str(dashboard_cache.get("no_model_api_calls", True)).lower()} / <span class="badge">no provider activation</span> {str(dashboard_cache.get("no_provider_activation", True)).lower()} / <span class="badge">no routing switch</span> {str(dashboard_cache.get("no_routing_auto_switch", True)).lower()} / <span class="badge">no writeback</span> {str(dashboard_cache.get("no_skill_or_runtime_standard_writeback", True)).lower()}</p>
      {_table(["module", "input status", "skipped", "age seconds", "freshness", "reason"], dashboard_cache_rows or [["None", "", "", "", "", ""]])}
      <h3>Write Step Profiler v0.4</h3>
      <p><span class="badge">schema</span> {html.escape(str(dashboard_write_steps.get("schema_version", "")))} / <span class="badge">status</span> {html.escape(str(dashboard_write_steps.get("status", "")))} / <span class="badge">total ms</span> {dashboard_write_steps.get("total_ms", 0)} / <span class="badge">slowest</span> {html.escape(str(dashboard_write_steps.get("slowest_step", "")))} / {_link(dashboard_perf_paths.get("write_steps", ""), "write steps")} / {_link(dashboard_perf_paths.get("write_steps_audit", ""), "write steps audit")}</p>
      {_table(["step", "elapsed ms", "status"], dashboard_write_step_rows or [["None", "0", ""]])}
    </section>
    <section><h2>Model Adapter Eval</h2>
      <p><span class="badge">schema</span> {html.escape(str(adapter_results.get("schema_version", "")))} 路 <span class="badge">trajectories</span> {adapter_results.get("trajectory_count", 0)} 路 <span class="badge">adapters</span> {adapter_results.get("adapter_count", 0)} 路 <span class="badge">simulated</span> {str(adapter_results.get("simulated", True)).lower()} 路 <span class="badge">dry-run harness</span> {str(adapter_results.get("dry_run_harness", True)).lower()} 路 <span class="badge">no model API calls</span> {str(adapter_results.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no runtime mutation</span> {str(adapter_results.get("no_skill_or_runtime_standard_mutation", True)).lower()} 路 {_link(adapter_paths.get("results", ""), "model_adapter_eval_results.json")} 路 {_link(adapter_paths.get("audit", ""), "audit")}</p>
      {_table(["Adapter", "Type", "State", "Enabled", "Traj", "Pass Rate", "Avg Score", "Evidence", "Latency ms", "Cost", "Privacy", "Strengths"], adapter_rows or [["None", "", "", "", "0", "0", "0", "0", "0", "0", "0", ""]])}
    </section>
    <section><h2>Model Adapter Daily Soak</h2>
      <p><span class="badge">schema</span> {html.escape(str(daily_soak.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(daily_soak.get("status", "")))} 路 <span class="badge">providers</span> {daily_soak.get("provider_count", 0)} 路 <span class="badge">adapters</span> {daily_soak.get("adapter_count", 0)} 路 <span class="badge">incidents</span> {daily_soak.get("incident_count", 0)} 路 <span class="badge">contract fails</span> {daily_soak.get("contract_failed_count", 0)} 路 <span class="badge">drift findings</span> {daily_soak.get("drift_finding_count", 0)} 路 <span class="badge">pending owner</span> {daily_soak.get("pending_owner_review_count", 0)} 路 {_link(adapter_paths.get("daily_soak", ""), "model_adapter_daily_soak.json")}</p>
      <p><span class="badge">no model API calls</span> {str(daily_soak.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no runtime mutation</span> {str(daily_soak.get("no_runtime_mutation", True)).lower()} 路 <span class="badge">no auto switch</span> {str(daily_soak.get("no_auto_switch", True)).lower()} 路 <span class="badge">owner approval</span> {str(daily_soak.get("guards", {}).get("owner_approval_required", True)).lower()}</p>
      {_table(["Adapter", "State", "Pass Rate", "Verifier Pass", "Evidence"], [[html.escape(str(r.get("display_name", ""))), html.escape(str(r.get("state", ""))), str(r.get("pass_rate", 0)), str(r.get("verifier_pass_rate", 0)), str(r.get("evidence_score", 0))] for r in daily_soak.get("top_adapters", [])] or [["None", "", "0", "0", "0"]])}
      <p><strong>Next actions:</strong> {html.escape("; ".join(str(x) for x in daily_soak.get("next_actions", [])))}</p>
    </section>
    <section><h2>Model Adapter Guardrail Negative Tests</h2>
      <p><span class="badge">schema</span> {html.escape(str(guardrail_negative_tests.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(guardrail_negative_tests.get("status", "")))} 路 <span class="badge">cases</span> {guardrail_negative_tests.get("case_count", 0)} 路 <span class="badge">failed</span> {guardrail_negative_tests.get("failed_count", 0)} 路 <span class="badge">no API calls</span> {str(guardrail_negative_tests.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no queue mutation</span> {str(guardrail_negative_tests.get("no_real_incident_queue_mutation", True)).lower()} 路 {_link(adapter_paths.get("guardrail_negative_tests", ""), "negative_tests.json")} 路 {_link(adapter_paths.get("guardrail_negative_tests_audit", ""), "audit")}</p>
      {_table(["Case", "Passed", "Expected", "Observed", "Incident Kinds"], [[html.escape(str(r.get("case", ""))), "yes" if r.get("passed") else "no", html.escape(json.dumps(r.get("expected", {}), ensure_ascii=False)), html.escape(json.dumps(r.get("observed", {}), ensure_ascii=False)), html.escape(", ".join(str(x) for x in r.get("incident_kinds", [])))] for r in guardrail_negative_tests.get("cases", [])] or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Model Adapter Evidence Completeness</h2>
      <p><span class="badge">schema</span> {html.escape(str(evidence_completeness.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(evidence_completeness.get("status", "")))} 路 <span class="badge">complete</span> {evidence_completeness.get("complete_count", 0)} 路 <span class="badge">needs samples</span> {evidence_completeness.get("needs_more_samples_count", 0)} 路 <span class="badge">blocked</span> {evidence_completeness.get("blocked_by_guardrail_count", 0)} 路 <span class="badge">no routing change</span> {str(evidence_completeness.get("no_routing_change", True)).lower()} 路 {_link(adapter_paths.get("evidence_completeness", ""), "evidence_completeness.json")} 路 {_link(adapter_paths.get("evidence_completeness_audit", ""), "audit")}</p>
      {_table(["Adapter", "State", "Status", "Traj", "Pass Rate", "Evidence", "Owner Gate", "Sample Gaps"], [[html.escape(str(r.get("display_name", ""))), html.escape(str(r.get("provider_state", ""))), html.escape(str(r.get("status", ""))), str(r.get("trajectory_count", 0)), str(r.get("pass_rate", 0)), str(r.get("avg_evidence_score", 0)), html.escape(str(r.get("owner_decision_status", ""))), html.escape(json.dumps(r.get("sample_gap", {}), ensure_ascii=False))] for r in evidence_completeness.get("items", [])] or [["None", "", "", "0", "0", "0", "", ""]])}
    </section>
    <section><h2>Model Adapter Sample Plan</h2>
      <p><span class="badge">schema</span> {html.escape(str(sample_plan.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(sample_plan.get("status", "")))} 路 <span class="badge">plans</span> {sample_plan.get("plan_count", 0)} 路 <span class="badge">high</span> {sample_plan.get("high_priority_count", 0)} 路 <span class="badge">medium</span> {sample_plan.get("medium_priority_count", 0)} 路 <span class="badge">no task execution</span> {str(sample_plan.get("no_task_execution", True)).lower()} 路 {_link(adapter_paths.get("sample_plan", ""), "sample_plan.json")} 路 {_link(adapter_paths.get("sample_plan_audit", ""), "audit")}</p>
      {_table(["Plan", "Adapter", "Priority", "Reason", "Target", "Count", "Mode", "Task Type"], [[html.escape(str(r.get("plan_id", ""))), html.escape(str(r.get("display_name", ""))), html.escape(str(r.get("priority", ""))), html.escape(str(r.get("reason", ""))), html.escape(str(r.get("target_outcome_category", ""))), str(r.get("target_sample_count", 0)), html.escape(str(r.get("sample_mode", ""))), html.escape(str(r.get("recommended_task_type", "")))] for r in sample_plan.get("items", [])] or [["None", "", "", "", "", "0", "", ""]])}
    </section>
    <section><h2>Model Adapter Path Consistency</h2>
      <p><span class="badge">schema</span> {html.escape(str(path_consistency.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(path_consistency.get("status", "")))} 路 <span class="badge">findings</span> {path_consistency.get("finding_count", 0)} 路 <span class="badge">high</span> {path_consistency.get("high_count", 0)} 路 <span class="badge">medium</span> {path_consistency.get("medium_count", 0)} 路 <span class="badge">no fs mutation</span> {str(path_consistency.get("no_filesystem_mutation", True)).lower()} 路 {_link(adapter_paths.get("path_consistency", ""), "path_consistency.json")} 路 {_link(adapter_paths.get("path_consistency_audit", ""), "audit")}</p>
      {_table(["Kind", "Severity", "Path", "Artifact", "Field", "Action"], [[html.escape(str(r.get("kind", ""))), html.escape(str(r.get("severity", ""))), html.escape(str(r.get("path", ""))), _link(str(r.get("artifact", "")), "artifact") if r.get("artifact") else "", html.escape(str(r.get("field", ""))), html.escape(str(r.get("recommended_action", "")))] for r in path_consistency.get("items", [])] or [["None", "", "", "", "", ""]])}
    </section>
    <section><h2>Path Cleanup Review Gate</h2>
      <p><span class="badge">schema</span> {html.escape(str(path_cleanup_review.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(path_cleanup_review.get("status", "")))} 路 <span class="badge">queue</span> {path_cleanup_review.get("queue_count", 0)} 路 <span class="badge">pending</span> {path_cleanup_review.get("pending_count", 0)} 路 <span class="badge">approved pending manual cleanup</span> {path_cleanup_review.get("approved_pending_manual_cleanup_count", 0)} 路 <span class="badge">no auto cleanup</span> {str(path_cleanup_review.get("no_auto_cleanup", True)).lower()} 路 {_link(adapter_paths.get("path_cleanup_review", ""), "cleanup_review_queue.json")} 路 {_link(adapter_paths.get("path_cleanup_review_decisions", ""), "decisions")} 路 {_link(adapter_paths.get("path_cleanup_review_audit", ""), "audit")}</p>
      {_table(["Review", "Status", "Decision", "Kind", "Severity", "Path", "Action"], [[html.escape(str(r.get("review_id", ""))), html.escape(str(r.get("status", ""))), html.escape(str(r.get("owner_decision", ""))), html.escape(str((r.get("finding") or {}).get("kind", ""))), html.escape(str((r.get("finding") or {}).get("severity", ""))), html.escape(str((r.get("finding") or {}).get("path", ""))), html.escape(str(r.get("proposed_action", "")))] for r in path_cleanup_review.get("items", [])] or [["None", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Adapter Config Registry</h2>
      <p><span class="badge">schema</span> {html.escape(str(adapter_registry.get("schema_version", "")))} 路 <span class="badge">providers</span> {len(model_adapter.get("providers", []))} 路 <span class="badge">owner approval</span> {str(adapter_registry.get("owner_approval_required", True)).lower()} 路 <span class="badge">no auto activation</span> {str(adapter_registry.get("no_auto_activation_guard", True)).lower()} 路 {_link(adapter_paths.get("registry", ""), "model_adapter_registry.json")}</p>
      {_table(["Provider", "Id", "State", "Enabled", "Cost", "Risk", "Privacy", "Purpose"], provider_rows or [["None", "", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Real Adapter Harness</h2>
      <p><span class="badge">schema</span> {html.escape(str(harness_plan.get("schema_version", "")))} 路 <span class="badge">providers</span> {harness_plan.get("provider_count", 0)} 路 <span class="badge">no model API calls</span> {str(harness_plan.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no auto activation</span> {str(harness_plan.get("no_auto_activation_guard", True)).lower()} 路 {_link(adapter_paths.get("harness_plan", ""), "model_adapter_harness_plan.json")} 路 {_link(adapter_paths.get("harness_audit", ""), "harness audit")}</p>
      {_table(["Provider", "State", "Dry Run", "Mode", "Blocked Reason"], harness_rows or [["None", "", "", "", ""]])}
    </section>
    <section><h2>Adapter Canary</h2>
      <p><span class="badge">schema</span> {html.escape(str(canary_queue.get("schema_version", "")))} 路 <span class="badge">queue</span> {canary_queue.get("queue_count", 0)} 路 <span class="badge">shadow</span> {canary_queue.get("shadow_count", 0)} 路 <span class="badge">enabled</span> {canary_queue.get("enabled_count", 0)} 路 <span class="badge">no auto activation</span> {str(canary_queue.get("no_auto_activation_guard", True)).lower()} 路 {_link(adapter_paths.get("canary_queue", ""), "model_adapter_canary_queue.json")} 路 {_link(adapter_paths.get("canary_audit", ""), "canary audit")}</p>
      {_table(["Provider", "State", "Canary Status", "Pass Rate", "Owner Approval", "No Auto Activation", "Reason"], canary_rows_model or [["None", "", "", "0", "", "", ""]])}
    </section>
    <section><h2>Model Routing Policy</h2>
      <p><span class="badge">schema</span> {html.escape(str(routing_policy.get("schema_version", "")))} 路 <span class="badge">rules</span> {routing_policy.get("rule_count", 0)} 路 <span class="badge">recommend only</span> {str(routing_policy.get("recommend_only", True)).lower()} 路 <span class="badge">auto switch</span> {str(routing_policy.get("auto_switch_allowed", False)).lower()} 路 <span class="badge">owner approval</span> {str(routing_policy.get("owner_approval_required", True)).lower()} 路 {_link(adapter_paths.get("routing_policy", ""), "model_routing_policy.json")} 路 {_link(adapter_paths.get("routing_audit", ""), "routing audit")}</p>
      {_table(["Capability", "Adapter", "Status", "Pass Rate", "Evidence", "Owner Approval", "Auto Switch", "Reason"], routing_rows_model or [["None", "", "", "0", "0", "", "", ""]])}
    </section>
    <section><h2>Model Adapter Decision Gate</h2>
      <p><span class="badge">schema</span> {html.escape(str(decision_queue.get("schema_version", "")))} 路 <span class="badge">queue</span> {decision_queue.get("queue_count", 0)} 路 <span class="badge">pending</span> {decision_queue.get("pending_count", 0)} 路 <span class="badge">approved pending real canary</span> {decision_queue.get("approved_pending_real_canary_count", 0)} 路 <span class="badge">no API on approval</span> {str(decision_queue.get("no_api_call_on_approval", True)).lower()} 路 <span class="badge">no auto activation</span> {str(decision_queue.get("no_auto_activation_guard", True)).lower()} 路 {_link(adapter_paths.get("decision_queue", ""), "model_adapter_decision_queue.json")} 路 {_link(adapter_paths.get("decisions", ""), "decisions")} 路 {_link(adapter_paths.get("decision_audit", ""), "decision audit")}</p>
      {_table(["Provider", "Id", "Status", "Pass Rate", "Rules", "Capabilities", "Decision", "Reason", "No API On Approval"], decision_rows_model or [["None", "", "", "0", "0", "", "", "", ""]])}
    </section>
    <section><h2>Model Adapter Contract Tests</h2>
      <p><span class="badge">schema</span> {html.escape(str(contract_tests.get("schema_version", "")))} 路 <span class="badge">checks</span> {contract_tests.get("check_count", 0)} 路 <span class="badge">failed</span> {contract_tests.get("failed_count", 0)} 路 <span class="badge">status</span> {html.escape(str(contract_tests.get("status", "")))} 路 <span class="badge">no API calls</span> {str(contract_tests.get("no_model_api_calls", True)).lower()} 路 <span class="badge">no runtime mutation</span> {str(contract_tests.get("no_runtime_mutation", True)).lower()} 路 {_link(adapter_paths.get("contract_tests", ""), "model_adapter_contract_tests.json")} 路 {_link(adapter_paths.get("contract_audit", ""), "contract audit")}</p>
      {_table(["Check", "Passed", "Missing", "Severity"], contract_rows or [["None", "", "", ""]])}
    </section>
    <section><h2>Model Adapter Drift Monitor</h2>
      <p><span class="badge">schema</span> {html.escape(str(drift_report.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(drift_report.get("status", "")))} 路 <span class="badge">findings</span> {drift_report.get("finding_count", 0)} 路 <span class="badge">critical</span> {drift_report.get("critical_count", 0)} 路 <span class="badge">high</span> {drift_report.get("high_count", 0)} 路 <span class="badge">no auto switch</span> {str(drift_report.get("no_auto_switch_guard", True)).lower()} 路 {_link(adapter_paths.get("drift_report", ""), "model_adapter_drift_report.json")} 路 {_link(adapter_paths.get("drift_baseline", ""), "baseline")} 路 {_link(adapter_paths.get("drift_audit", ""), "drift audit")}</p>
      {_table(["Kind", "Severity", "Adapter", "Before", "After", "Delta"], drift_rows or [["None", "", "", "", "", ""]])}
    </section>
    <section><h2>Model Adapter Incident Queue</h2>
      <p><span class="badge">schema</span> {html.escape(str(incident_queue.get("schema_version", "")))} 路 <span class="badge">status</span> {html.escape(str(incident_queue.get("status", "")))} 路 <span class="badge">incidents</span> {incident_queue.get("incident_count", 0)} 路 <span class="badge">critical</span> {incident_queue.get("critical_count", 0)} 路 <span class="badge">high</span> {incident_queue.get("high_count", 0)} 路 <span class="badge">pending</span> {incident_queue.get("pending_count", 0)} 路 <span class="badge">no auto remediation</span> {str(incident_queue.get("no_auto_remediation", True)).lower()} 路 {_link(adapter_paths.get("incident_queue", ""), "model_adapter_incident_queue.json")} 路 {_link(adapter_paths.get("incident_audit", ""), "incident audit")}</p>
      {_table(["Incident", "Kind", "Severity", "Status", "Source", "Summary", "Recommended Action"], incident_rows_model or [["None", "", "", "", "", "", ""]])}
    </section>
    <section><h2>Model Routing Recommendations</h2>{_table(["Capability", "Recommended Adapter", "Pass Rate", "Evidence", "Reason"], adapter_recommendation_rows or [["None", "", "0", "0", ""]])}</section>
    <div class="grid2">
      <section><h2>Stable Success Paths</h2>{_table(["Group", "Total", "Success Rate", "Stable Path"], stable_path_rows or [["None", "0", "0", ""]])}</section>
      <section><h2>Repeat Failure Patterns</h2>{_table(["Group", "Total", "Failures", "Operational Fail", "Pattern"], repeat_failure_rows or [["None", "0", "0", "0", ""]])}</section>
    </div>
    <div class="grid2">
      <section><h2>Shadow Promotion Candidates</h2>{_table(["Shadow Run", "Capability", "Task Card", "Signal", "File"], shadow_candidate_rows or [["None", "", "", "", ""]])}</section>
      <section><h2>Shadow Diff Warnings</h2>{_table(["Shadow Run", "Capability", "Task Card", "Findings", "File"], shadow_warning_rows or [["None", "", "", "0", ""]])}</section>
    </div>
    <div class="grid2">
      <section><h2>Failed / Blocked Runs</h2>{_table(["Project", "Run", "Status", "Decision", "Failed Checks", "File"], blocked_rows or [["None", "", "", "", "", ""]])}</section>
      <section><h2>Retry Queue</h2>{_table(["Project", "Run", "Phase", "Status", "Updated", "File"], retry_rows or [["None", "", "", "", "", ""]])}</section>
    </div>
    <section><h2>Completion Verifier Failures</h2>{_table(["Project", "Run", "Class", "Missing Evidence", "Forbidden Hits", "File"], completion_rows or [["None", "", "", "", "", ""]])}</section>
    <section><h2>Recent Memory Writeback</h2>{_table(["Project", "Run", "Status", "Memory Id", "File"], memory_rows or [["None", "", "", "", ""]])}</section>
    <section><h2>Manual-Gates Projects</h2>{_table(["Project", "Track", "Autonomy", "Progress", "Iteration", "State"], project_rows)}</section>
    <section><h2>MCP Inventory</h2>{_table(["MCP", "Python Files", "README", "Runner"], mcp_rows)}</section>
    <div class="grid2">
      <section><h2>Trace Evidence</h2>{_table(["Project", "Events", "File"], trace_rows or [["None", "0", ""]])}</section>
      <section><h2>Parallel Agent Runs</h2>{_table(["Project", "Run", "Progress", "Status", "File"], parallel_rows or [["None", "", "", "", ""]])}</section>
    </div>
    <section><h2>Backups</h2>{_table(["Archive", "Size", "Modified", "File"], backup_rows)}</section>
    <section><h2>Evidence Summary</h2>
      <p><span class="badge">memory index</span> {"exists" if evidence["memory_index_exists"] else "missing"}</p>
      <p><span class="badge">vector memory</span> {"exists" if evidence["memory_vector_index_exists"] else "missing"}</p>
      <p><span class="badge">runtime projects</span> {len(evidence["runtime_projects"])}</p>
      <p><span class="badge">workflow projects</span> {len(evidence["workflow_projects"])}</p>
    </section>
    <section>
      <h2>Realtime Snapshot</h2>
      <div class="live">
        <div><strong id="live-control">-</strong><span>control states</span></div>
        <div><strong id="live-mandatory">-</strong><span>mandatory states</span></div>
        <div><strong id="live-gitci">-</strong><span>git/ci records</span></div>
        <div><strong id="live-runs">-</strong><span>Agent OS runs</span></div>
      </div>
      <p id="live-updated">Waiting for dashboard_realtime.json</p>
    </section>
  </main>
  <script>
    async function refreshRealtime() {{
      try {{
        const res = await fetch('dashboard_realtime.json?ts=' + Date.now());
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('live-control').textContent = (data.control_states || []).length;
        document.getElementById('live-mandatory').textContent = (data.mandatory_states || []).length;
        document.getElementById('live-gitci').textContent = (data.git_ci_states || []).length;
        document.getElementById('live-runs').textContent = ((data.agent_os_runtime || {{}}).runs || []).length;
        document.getElementById('live-updated').textContent = 'Updated ' + (data.generated || '');
      }} catch (err) {{
        document.getElementById('live-updated').textContent = 'Realtime file unavailable when opened through this browser mode.';
      }}
    }}
    refreshRealtime();
    setInterval(refreshRealtime, 5000);
  </script>
</body>
</html>
"""


def _run_detail_html(run_state: dict, path: Path) -> str:
    context = run_state.get("inputs", {}).get("context", {}) if isinstance(run_state.get("inputs"), dict) else {}
    task_card_path = context.get("task_card_path") or run_state.get("task_card_path", "")
    task_card = _read_json(Path(task_card_path)) if task_card_path else {}
    execution = run_state.get("execution", {})
    evidence_path = execution.get("evidence_path", "") if isinstance(execution, dict) else ""
    execution_evidence = _read_json(Path(evidence_path)) if evidence_path else execution
    verifier = run_state.get("completion_verifier", {})
    memory_writes = run_state.get("memory_writes", [])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(str(run_state.get("run_id", path.stem)))}</title>
  <style>
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: #f6f7f9; color: #1f2937; }}
    header {{ padding: 20px 28px; background: #102a43; color: white; }}
    main {{ padding: 20px 28px 40px; max-width: 1200px; margin: 0 auto; }}
    section {{ background: white; border: 1px solid #d7dce3; border-radius: 8px; padding: 16px; margin: 14px 0; overflow: auto; }}
    h1 {{ margin: 0 0 6px; font-size: 22px; }}
    h2 {{ margin: 0 0 10px; font-size: 17px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f9fafb; border: 1px solid #d7dce3; border-radius: 6px; padding: 12px; font-size: 12px; }}
    a {{ color: #0f766e; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(str(run_state.get("run_id", path.stem)))}</h1>
    <div>{html.escape(str(run_state.get("project", "")))} · {html.escape(str(run_state.get("status", "")))} · {html.escape(str(run_state.get("decision", "")))}</div>
  </header>
  <main>
    <p><a href="../index.html">Back to dashboard</a></p>
    <section><h2>RunState</h2><pre>{html.escape(json.dumps(run_state, ensure_ascii=False, indent=2))}</pre></section>
    <section><h2>Task Card</h2><pre>{html.escape(json.dumps(task_card, ensure_ascii=False, indent=2))}</pre></section>
    <section><h2>Execution Evidence</h2><pre>{html.escape(json.dumps(execution_evidence, ensure_ascii=False, indent=2))}</pre></section>
    <section><h2>Completion Verifier</h2><pre>{html.escape(json.dumps(verifier, ensure_ascii=False, indent=2))}</pre></section>
    <section><h2>Memory Writes</h2><pre>{html.escape(json.dumps(memory_writes, ensure_ascii=False, indent=2))}</pre></section>
  </main>
</body>
</html>
"""


def _write_run_details(output_dir: Path) -> int:
    detail_dir = output_dir / "run_details"
    detail_dir.mkdir(parents=True, exist_ok=True)
    run_dir = RESEARCH_DIR / "agent_os_runtime" / "runs"
    count = 0
    if not run_dir.exists():
        return count
    for run_path in sorted(run_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        run_state = _read_json(run_path)
        (detail_dir / f"{run_path.stem}.html").write_text(_run_detail_html(run_state, run_path), encoding="utf-8")
        count += 1
    return count


def _write_replay_details(output_dir: Path) -> dict:
    try:
        from agent_os_replay_runner import generate_replay_pages

        return generate_replay_pages(str(output_dir))
    except Exception as exc:
        return {"status": "replay_generation_failed", "error": str(exc)}


def _write_replay_diff(output_dir: Path) -> dict:
    try:
        from agent_os_replay_diff import generate_replay_diff

        return generate_replay_diff(str(output_dir))
    except Exception as exc:
        return {"status": "replay_diff_generation_failed", "error": str(exc)}


def _write_verifier_failure_drilldown() -> dict:
    try:
        from agent_os_verifier_failure_drilldown import build_report

        return build_report()
    except Exception as exc:
        return {"status": "verifier_failure_drilldown_failed", "error": str(exc)}


def _write_class_c_evidence_drilldown() -> dict:
    try:
        from agent_os_class_c_evidence_contract import build_report

        return build_report()
    except Exception as exc:
        return {"status": "class_c_evidence_drilldown_failed", "error": str(exc)}


def _write_unknown_outcome_resolver() -> dict:
    try:
        from agent_os_unknown_outcome_resolver import build_report

        return build_report()
    except Exception as exc:
        return {"status": "unknown_outcome_resolver_failed", "error": str(exc)}


def _write_retry_pattern_drilldown() -> dict:
    try:
        from agent_os_retry_pattern_drilldown import build_report

        return build_report()
    except Exception as exc:
        return {"status": "retry_pattern_drilldown_failed", "error": str(exc)}


def _write_retry_recovery_verifier() -> dict:
    try:
        from agent_os_retry_recovery_verifier import build_report

        return build_report()
    except Exception as exc:
        return {"status": "retry_recovery_verifier_failed", "error": str(exc)}


def _write_dashboard(data: dict, output_dir: str = "") -> dict:
    out_dir = Path(output_dir) if output_dir else DASHBOARD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    dashboard_write_started = time.perf_counter()
    dashboard_write_steps = []

    def record_step(name: str, started: float, status: str = "ok") -> None:
        dashboard_write_steps.append({
            "step": name,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "status": status,
        })

    distillation_started = time.perf_counter()
    try:
        from agent_os_experience_distiller import build_queue as build_distillation_queue

        distillation = build_distillation_queue()
        data.setdefault("trajectory", {})["distillation_queue"] = distillation
        data["distillation"] = _distillation_summary()
    except Exception as exc:
        data.setdefault("distillation", {})["error"] = str(exc)
        record_step("distillation_queue", distillation_started, "error")
    else:
        record_step("distillation_queue", distillation_started)
    derived_started = time.perf_counter()
    try:
        from agent_os_dashboard_refresh_manifest import build_manifest as build_dashboard_refresh_manifest
        from agent_os_soak_json_sanitizer import sanitize as sanitize_soak_json
        from agent_os_7_day_soak_progress_matrix import build_matrix as build_7_day_soak_matrix

        sanitize_soak_json()
        build_7_day_soak_matrix()
        dashboard_manifest_before = build_dashboard_refresh_manifest()
        manifest_by_module = {
            item.get("module"): item
            for item in dashboard_manifest_before.get("modules", [])
            if isinstance(item, dict) and item.get("module")
        }

        def cache_status(module: str) -> dict:
            item = manifest_by_module.get(module, {})
            skipped = item.get("status") == "unchanged" and item.get("missing_count", 0) == 0
            newest_mtime_ns = max((file.get("mtime_ns", 0) for file in item.get("files", []) if isinstance(file, dict)), default=0)
            freshness_age_seconds = int(time.time() - (newest_mtime_ns / 1_000_000_000)) if newest_mtime_ns else None
            if freshness_age_seconds is None:
                freshness_status = "unknown"
            elif freshness_age_seconds <= 3600:
                freshness_status = "fresh_under_1h"
            elif freshness_age_seconds <= 86400:
                freshness_status = "warm_under_24h"
            else:
                freshness_status = "stale_over_24h"
            return {
                "module": module,
                "status": item.get("status", "missing_manifest"),
                "skipped": skipped,
                "reason": "input_hash_unchanged" if skipped else "input_changed_or_not_observed",
                "freshness_age_seconds": freshness_age_seconds,
                "freshness_status": freshness_status,
                "newest_input_mtime_ns": newest_mtime_ns,
            }

        cache_modules = []

        model_adapter_cache = cache_status("model_adapter")
        cache_modules.append(model_adapter_cache)
        if not model_adapter_cache["skipped"]:
            from agent_os_model_adapter_harness import refresh as refresh_model_adapter_harness
            from agent_os_model_adapter_eval import build_eval as build_model_adapter_eval
            from agent_os_model_adapter_canary import build_queue as build_model_adapter_canary
            from agent_os_model_routing_policy import build_policy as build_model_routing_policy
            from agent_os_model_adapter_decision_gate import build_queue as build_model_adapter_decision_queue
            from agent_os_model_adapter_contract_tests import build_report as build_model_adapter_contract_tests
            from agent_os_model_adapter_drift_monitor import build_report as build_model_adapter_drift_report
            from agent_os_model_adapter_incident_queue import build_queue as build_model_adapter_incident_queue
            from agent_os_model_adapter_daily_soak import build_report as build_model_adapter_daily_soak
            from agent_os_model_adapter_guardrail_negative_tests import build_report as build_model_adapter_guardrail_negative_tests
            from agent_os_model_adapter_evidence_completeness import build_report as build_model_adapter_evidence_completeness
            from agent_os_model_adapter_sample_plan import build_report as build_model_adapter_sample_plan
            from agent_os_model_adapter_path_consistency import build_report as build_model_adapter_path_consistency
            from agent_os_model_adapter_path_cleanup_review import build_queue as build_model_adapter_path_cleanup_review

            refresh_model_adapter_harness()
            build_model_adapter_eval()
            build_model_adapter_canary()
            build_model_routing_policy()
            build_model_adapter_decision_queue()
            build_model_adapter_contract_tests()
            build_model_adapter_drift_report()
            build_model_adapter_incident_queue()
            build_model_adapter_daily_soak()
            build_model_adapter_guardrail_negative_tests()
            build_model_adapter_evidence_completeness()
            build_model_adapter_sample_plan()
            build_model_adapter_path_consistency()
            build_model_adapter_path_cleanup_review()
        data["model_adapter"] = _model_adapter_summary()

        owner_decision_cache = cache_status("owner_decision")
        cache_modules.append(owner_decision_cache)
        if not owner_decision_cache["skipped"]:
            from agent_os_owner_decision_summary import build_report as build_owner_decision_summary
            from agent_os_owner_decision_prioritizer import build_report as build_owner_decision_priorities
            from agent_os_owner_review_packet import build_packet as build_owner_review_packet
            from agent_os_owner_decision_consistency import build_report as build_owner_decision_consistency
            from agent_os_owner_decision_staleness import build_report as build_owner_decision_staleness
            from agent_os_owner_decision_trend import build_report as build_owner_decision_trend
            from agent_os_owner_decision_dependency_map import build_report as build_owner_decision_dependency_map
            from agent_os_owner_decision_risk_heatmap import build_report as build_owner_decision_risk_heatmap
            from agent_os_owner_decision_review_checklist import build_report as build_owner_decision_review_checklist
            from agent_os_owner_decision_guardrail_validator import build_report as build_owner_decision_guardrail_validator
            from agent_os_owner_decision_guardrail_trend import build_report as build_owner_decision_guardrail_trend
            from agent_os_owner_decision_guardrail_coverage import build_report as build_owner_decision_guardrail_coverage
            from agent_os_owner_decision_guardrail_coverage_trend import build_report as build_owner_decision_guardrail_coverage_trend
            from agent_os_owner_decision_governance_health import build_report as build_owner_decision_governance_health
            from agent_os_owner_decision_governance_health_trend import build_report as build_owner_decision_governance_health_trend
            from agent_os_owner_decision_governance_freshness import build_report as build_owner_decision_governance_freshness
            from agent_os_owner_decision_governance_ops_digest import build_report as build_owner_decision_governance_ops_digest
            from agent_os_owner_review_drilldown import build_report as build_owner_review_drilldown
            from agent_os_owner_review_packet_coverage import build_report as build_owner_review_packet_coverage
            from agent_os_owner_review_integrity_manifest import build_report as build_owner_review_integrity_manifest
            from agent_os_owner_review_integrity_trend import build_report as build_owner_review_integrity_trend
            from agent_os_owner_review_readiness_checklist import build_report as build_owner_review_readiness_checklist
            from agent_os_owner_review_readiness_trend import build_report as build_owner_review_readiness_trend
            from agent_os_owner_review_queue_aging import build_report as build_owner_review_queue_aging
            from agent_os_owner_review_queue_aging_trend import build_report as build_owner_review_queue_aging_trend
            from agent_os_owner_review_queue_sla_forecast import build_report as build_owner_review_queue_sla_forecast
            from agent_os_owner_review_queue_sla_forecast_trend import build_report as build_owner_review_queue_sla_forecast_trend
            from agent_os_owner_review_next_action_preview import build_report as build_owner_review_next_action_preview
            from agent_os_owner_review_next_action_trend import build_report as build_owner_review_next_action_trend
            from agent_os_owner_review_action_brief import build_report as build_owner_review_action_brief
            from agent_os_owner_review_action_brief_trend import build_report as build_owner_review_action_brief_trend
            from agent_os_owner_review_packet_diff import build_report as build_owner_review_packet_diff
            from agent_os_owner_review_decision_simulator import build_report as build_owner_review_decision_simulator
            from agent_os_owner_review_decision_impact_trend import build_report as build_owner_review_decision_impact_trend
            from agent_os_owner_review_blocker_digest import build_report as build_owner_review_blocker_digest
            from agent_os_owner_review_blocker_digest_trend import build_report as build_owner_review_blocker_digest_trend
            from agent_os_owner_review_blocker_guardrail_matrix import build_report as build_owner_review_blocker_guardrail_matrix
            from agent_os_owner_review_blocker_guardrail_matrix_trend import build_report as build_owner_review_blocker_guardrail_matrix_trend
            from agent_os_owner_review_guardrail_action_drilldown import build_report as build_owner_review_guardrail_action_drilldown
            from agent_os_owner_review_guardrail_action_drilldown_trend import build_report as build_owner_review_guardrail_action_drilldown_trend
            from agent_os_owner_review_action_dependency_index import build_report as build_owner_review_action_dependency_index
            from agent_os_owner_review_action_dependency_trend import build_report as build_owner_review_action_dependency_trend
            from agent_os_owner_review_action_dependency_coverage import build_report as build_owner_review_action_dependency_coverage
            from agent_os_owner_review_action_dependency_coverage_trend import build_report as build_owner_review_action_dependency_coverage_trend
            from agent_os_owner_review_coverage_sla_consistency import build_report as build_owner_review_coverage_sla_consistency
            from agent_os_owner_review_coverage_sla_consistency_trend import build_report as build_owner_review_coverage_sla_consistency_trend
            from agent_os_owner_pending_decision_freeze_guard import build_report as build_owner_pending_decision_freeze_guard
            from agent_os_owner_pending_decision_freeze_guard_trend import build_report as build_owner_pending_decision_freeze_guard_trend
            from agent_os_owner_review_packet_freshness_cross_check import build_report as build_owner_review_packet_freshness_cross_check
            from agent_os_owner_review_packet_freshness_trend import build_report as build_owner_review_packet_freshness_trend
            from agent_os_owner_review_evidence_manifest import build_report as build_owner_review_evidence_manifest
            from agent_os_owner_review_evidence_manifest_trend import build_report as build_owner_review_evidence_manifest_trend
            from agent_os_owner_review_decision_readiness_seal import build_report as build_owner_review_decision_readiness_seal
            from agent_os_owner_review_decision_readiness_seal_trend import build_report as build_owner_review_decision_readiness_seal_trend
            from agent_os_owner_review_decision_readiness_seal_ops_digest import build_report as build_owner_review_decision_readiness_seal_ops_digest
            from agent_os_owner_review_dry_run_decision_plan import build_report as build_owner_review_dry_run_decision_plan
            from agent_os_owner_review_dry_run_decision_plan_trend import build_report as build_owner_review_dry_run_decision_plan_trend
            from agent_os_owner_review_dry_run_decision_plan_coverage import build_report as build_owner_review_dry_run_decision_plan_coverage
            from agent_os_owner_review_dry_run_decision_plan_coverage_trend import build_report as build_owner_review_dry_run_decision_plan_coverage_trend

            build_owner_decision_summary()
            build_owner_decision_priorities()
            build_owner_review_packet()
            build_owner_decision_consistency()
            build_owner_decision_staleness()
            build_owner_decision_trend()
            build_owner_decision_dependency_map()
            build_owner_decision_risk_heatmap()
            build_owner_decision_review_checklist()
            build_owner_decision_guardrail_validator()
            build_owner_decision_guardrail_trend()
            build_owner_decision_guardrail_coverage()
            build_owner_decision_guardrail_coverage_trend()
            build_owner_decision_governance_health()
            build_owner_decision_governance_health_trend()
            build_owner_decision_governance_freshness()
            build_owner_decision_governance_ops_digest()
            build_owner_review_drilldown()
            build_owner_review_packet_coverage()
            build_owner_review_integrity_manifest()
            build_owner_review_integrity_trend()
            build_owner_review_readiness_checklist()
            build_owner_review_readiness_trend()
            build_owner_review_queue_aging()
            build_owner_review_queue_aging_trend()
            build_owner_review_queue_sla_forecast()
            build_owner_review_queue_sla_forecast_trend()
            build_owner_review_next_action_preview()
            build_owner_review_next_action_trend()
            build_owner_review_action_brief()
            build_owner_review_action_brief_trend()
            build_owner_review_packet_diff()
            build_owner_review_decision_simulator()
            build_owner_review_decision_impact_trend()
            build_owner_review_blocker_digest()
            build_owner_review_blocker_digest_trend()
            build_owner_review_blocker_guardrail_matrix()
            build_owner_review_blocker_guardrail_matrix_trend()
            build_owner_review_guardrail_action_drilldown()
            build_owner_review_guardrail_action_drilldown_trend()
            build_owner_review_action_dependency_index()
            build_owner_review_action_dependency_trend()
            build_owner_review_action_dependency_coverage()
            build_owner_review_action_dependency_coverage_trend()
            build_owner_review_coverage_sla_consistency()
            build_owner_review_coverage_sla_consistency_trend()
            build_owner_pending_decision_freeze_guard()
            build_owner_pending_decision_freeze_guard_trend()
            build_owner_review_packet_freshness_cross_check()
            build_owner_review_packet_freshness_trend()
            build_owner_review_evidence_manifest()
            build_owner_review_evidence_manifest_trend()
            build_owner_review_decision_readiness_seal()
            build_owner_review_decision_readiness_seal_trend()
            build_owner_review_decision_readiness_seal_ops_digest()
            build_owner_review_dry_run_decision_plan()
            build_owner_review_dry_run_decision_plan_trend()
            build_owner_review_dry_run_decision_plan_coverage()
            build_owner_review_dry_run_decision_plan_coverage_trend()
        data["owner_decision"] = _owner_decision_summary()

        knowledge_trust_cache = cache_status("knowledge_trust")
        cache_modules.append(knowledge_trust_cache)
        if not knowledge_trust_cache["skipped"]:
            from agent_os_knowledge_quarantine_registry import build_registry as build_knowledge_quarantine_registry
            from agent_os_knowledge_review_packet import build_packet as build_knowledge_review_packet
            from agent_os_knowledge_sustained_candidate_gate import build_gate as build_knowledge_sustained_candidate_gate
            from agent_os_knowledge_trusted_owner_review_queue import build_queue as build_knowledge_trusted_owner_review_queue

            build_knowledge_quarantine_registry()
            build_knowledge_review_packet()
            build_knowledge_sustained_candidate_gate()
            build_knowledge_trusted_owner_review_queue()
        data["knowledge_trust"] = _knowledge_trust_summary()

        investment_eval_started = time.perf_counter()
        try:
            investment_script = INVESTMENT_EVAL_DIR / "investment_eval_dashboard.py"
            if investment_script.exists():
                spec = importlib.util.spec_from_file_location("investment_eval_dashboard", investment_script)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.main()
        except Exception as exc:
            data.setdefault("investment_eval", {})["error"] = str(exc)
            record_step("investment_eval_dashboard", investment_eval_started, "error")
        else:
            data["investment_eval"] = _investment_eval_summary()
            record_step("investment_eval_dashboard", investment_eval_started)

        _write_dashboard_cache_summary({
            "schema_version": "agent-os-dashboard-refresh-cache/v0.6",
            "generated": _now(),
            "status": "cache_applied" if any(item["skipped"] for item in cache_modules) else "full_rebuild",
            "modules": cache_modules,
            "summary": {
                "module_count": len(cache_modules),
                "skipped_count": sum(1 for item in cache_modules if item["skipped"]),
                "rebuilt_count": sum(1 for item in cache_modules if not item["skipped"]),
            },
            "lazy_imports_enabled": True,
            "html_rewritten": True,
            "data_rewritten": True,
            "no_decisions_applied": True,
            "no_model_api_calls": True,
            "no_provider_activation": True,
            "no_routing_auto_switch": True,
            "no_runtime_mutation": True,
            "no_registry_lifecycle_mutation": True,
            "no_skill_or_runtime_standard_writeback": True,
        })
        build_dashboard_refresh_manifest()
        data["dashboard_perf"] = _dashboard_perf_summary()
    except Exception as exc:
        data.setdefault("model_adapter", {})["error"] = str(exc)
        record_step("derived_report_refresh", derived_started, "error")
    else:
        record_step("derived_report_refresh", derived_started)
    data_path = out_dir / "dashboard_data.json"
    html_path = out_dir / "index.html"
    data_json_started = time.perf_counter()
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    record_step("dashboard_data_json_write", data_json_started)
    realtime_path = out_dir / "dashboard_realtime.json"
    realtime_started = time.perf_counter()
    realtime_path.write_text(json.dumps(_realtime_summary(), ensure_ascii=False, indent=2), encoding="utf-8")
    record_step("realtime_json_write", realtime_started)
    run_details_started = time.perf_counter()
    detail_count = _write_run_details(out_dir)
    record_step("run_details_write", run_details_started)
    replay_started = time.perf_counter()
    replay = _write_replay_details(out_dir)
    record_step("replay_details_write", replay_started)
    replay_diff_started = time.perf_counter()
    replay_diff = _write_replay_diff(out_dir)
    record_step("replay_diff_write", replay_diff_started)
    verifier_drilldown_started = time.perf_counter()
    verifier_drilldown = _write_verifier_failure_drilldown()
    record_step("verifier_failure_drilldown_write", verifier_drilldown_started)
    class_c_started = time.perf_counter()
    class_c_drilldown = _write_class_c_evidence_drilldown()
    record_step("class_c_evidence_drilldown_write", class_c_started)
    unknown_resolver_started = time.perf_counter()
    unknown_resolver = _write_unknown_outcome_resolver()
    record_step("unknown_outcome_resolver_write", unknown_resolver_started)
    retry_drilldown_started = time.perf_counter()
    retry_drilldown = _write_retry_pattern_drilldown()
    record_step("retry_pattern_drilldown_write", retry_drilldown_started)
    retry_recovery_started = time.perf_counter()
    retry_recovery = _write_retry_recovery_verifier()
    record_step("retry_recovery_verifier_write", retry_recovery_started)
    data.setdefault("trajectory", {})["replay_runner"] = replay
    data.setdefault("trajectory", {})["replay_diff"] = replay_diff
    data.setdefault("trajectory", {})["verifier_drilldown"] = verifier_drilldown
    data.setdefault("trajectory", {})["class_c_drilldown"] = class_c_drilldown
    data.setdefault("trajectory", {})["unknown_resolver"] = unknown_resolver
    data.setdefault("trajectory", {})["retry_drilldown"] = retry_drilldown
    data.setdefault("trajectory", {})["retry_recovery"] = retry_recovery
    html_started = time.perf_counter()
    html_path.write_text(_html(data), encoding="utf-8")
    record_step("dashboard_html_render_write", html_started)
    slowest = max(dashboard_write_steps, key=lambda item: item["elapsed_ms"], default={"step": "", "elapsed_ms": 0})
    _write_dashboard_step_profile({
        "schema_version": "agent-os-dashboard-write-step-profiler/v0.4",
        "generated": _now(),
        "status": "profiled",
        "total_ms": int((time.perf_counter() - dashboard_write_started) * 1000),
        "slowest_step": slowest.get("step", ""),
        "slowest_step_ms": slowest.get("elapsed_ms", 0),
        "steps": dashboard_write_steps,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    })
    return {"html_path": str(html_path), "data_path": str(data_path), "realtime_path": str(realtime_path), "run_detail_count": detail_count, "replay": replay, "replay_diff": replay_diff}


def build_server() -> FastMCP:
    mcp = FastMCP("dashboard-mcp")

    @mcp.tool()
    def dashboard_brief() -> str:
        """Describe dashboard generation."""
        return _json({
            "name": "dashboard-mcp",
            "version": "v5.14",
            "purpose": "generate a static local dashboard for manual-agent OS evidence",
            "default_output": str(DASHBOARD_DIR / "index.html"),
        })

    @mcp.tool()
    def collect_dashboard_data() -> str:
        """Collect dashboard data without writing files."""
        return _json(_collect())

    @mcp.tool()
    def generate_dashboard(output_dir: str = "") -> str:
        """Generate dashboard_data.json and index.html."""
        data = _collect()
        paths = _write_dashboard(data, output_dir)
        return _json({"status": "generated", **paths, "project_count": len(data["manual_projects"]), "mcp_count": len(data["mcp_inventory"])})

    @mcp.tool()
    def collect_realtime_data() -> str:
        """Collect realtime dashboard snapshot data."""
        return _json(_realtime_summary())

    @mcp.tool()
    def refresh_realtime_dashboard(output_dir: str = "") -> str:
        """Refresh dashboard_realtime.json for the local dashboard."""
        out_dir = Path(output_dir) if output_dir else DASHBOARD_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "dashboard_realtime.json"
        data = _realtime_summary()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "refreshed", "path": str(path), "generated": data["generated"]})

    @mcp.tool()
    def dashboard_status(output_dir: str = "") -> str:
        """Return dashboard file status."""
        out_dir = Path(output_dir) if output_dir else DASHBOARD_DIR
        html_path = out_dir / "index.html"
        data_path = out_dir / "dashboard_data.json"
        realtime_path = out_dir / "dashboard_realtime.json"
        return _json({
            "html_exists": html_path.exists(),
            "data_exists": data_path.exists(),
            "realtime_exists": realtime_path.exists(),
            "html_path": str(html_path),
            "data_path": str(data_path),
            "realtime_path": str(realtime_path),
            "html_size": html_path.stat().st_size if html_path.exists() else 0,
            "data_size": data_path.stat().st_size if data_path.exists() else 0,
            "realtime_size": realtime_path.stat().st_size if realtime_path.exists() else 0,
        })

    return mcp


def main() -> None:
    build_server().run()
