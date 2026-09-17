# -*- coding: utf-8 -*-
"""Autonomy Level Assessor MCP server.

v6.25 produces an evidence-based autonomy level for Manual Agent OS.

v6.28 includes local audit hash chain evidence while preserving the L5 boundary:
local tamper-evidence is not third-party signature or immutable storage.

v6.29 includes approval interrupts for durable human-in-the-loop boundaries.

v6.30 includes pre-task memory retrieval packets.

v6.31 includes production readiness evidence.

v6.32 includes cost budget guardrail evidence.

v6.33 includes mathematical reasoning evidence.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
RESEARCH = DATA_ROOT / "09_投研"
REPORT_DIR = RESEARCH / "autonomy_level_assessor"
ASSESSMENT_FILE = REPORT_DIR / "autonomy_assessments.jsonl"

CAPABILITIES = [
    ("runtime_control_plane", "policy.json and mandatory runtime route exist"),
    ("mandatory_preflight", "preflight bundle is forced before runtime execution"),
    ("local_regression_gate", "local regression gate has a passing recent run"),
    ("completion_evidence_gate", "completion verifier requires evidence"),
    ("policy_consistency_audit", "policy consistency audit has a passing recent run"),
    ("backup_integrity", "backup manifest has entries and latest verification can pass"),
    ("agentops_dashboard", "dashboard exposes governance health"),
    ("audit_hash_chain", "local audit hash chain exists and dashboard exposes it"),
    ("approval_interrupts", "high-risk actions create durable interrupts instead of ad hoc questions"),
    ("memory_retrieval", "pre-task packets retrieve keyword, semantic, vector, and consolidated memory"),
    ("production_readiness", "local readiness report aggregates evidence and L5 blockers"),
    ("cost_budget", "local cost budget guardrail blocks paid API spend without approval"),
    ("mathematical_reasoning", "local mathematical reasoning events support decision quality"),
    ("long_running_checkpoints", "long-running session has checkpoints"),
    ("manual_gates", "manual-gates projects exist"),
    ("safe_capability_profile", "capability profile blocks high-risk actions"),
]

L5_BLOCKERS = [
    "no real remote PR/CI closed loop",
    "no distributed multi-agent cluster runtime",
    "no vector embedding memory with automatic distillation loop proven in this run",
    "no universal tool lifecycle hook injected into every external tool call",
    "approval interrupts are local artifacts, not remote signed approval workflow",
    "local hash chain exists, but no third-party signature or immutable storage",
]


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _count(path: Path, pattern: str) -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


def _latest(rows: list[dict]) -> dict:
    return rows[-1] if rows else {}


def _evidence() -> dict:
    policy = _read_json(RESEARCH / "control_plane" / "policy.json")
    dashboard = _read_json(RESEARCH / "agentops_dashboard" / "agentops_dashboard.json")
    preflight = _read_jsonl(RESEARCH / "preflight_bundle" / "preflight_bundles.jsonl")
    regression = _read_jsonl(RESEARCH / "local_regression_gate" / "regression_runs.jsonl")
    policy_audits = _read_jsonl(RESEARCH / "policy_consistency_auditor" / "policy_consistency_audits.jsonl")
    backup_manifest = _read_jsonl(RESEARCH / "backup_integrity" / "backup_manifest.jsonl")
    audit_chain = _read_jsonl(RESEARCH / "audit_hash_chain" / "audit_chain.jsonl")
    approval_interrupts = _read_jsonl(RESEARCH / "approval_interrupts" / "interrupts.jsonl")
    retrieval_packets = _read_jsonl(RESEARCH / "memory_retrieval" / "retrieval_packets.jsonl")
    readiness_reports = _read_jsonl(RESEARCH / "production_readiness" / "readiness_reports.jsonl")
    cost_usage = _read_jsonl(RESEARCH / "cost_budget" / "usage.jsonl")
    math_events = _read_jsonl(RESEARCH / "mathematical_reasoning" / "reasoning_events.jsonl")
    session_state = _read_json(RESEARCH / "long_running_sessions" / "manual-agent-os-overnight-loop-20260723" / "session_state.json")
    gates = DATA_ROOT / "04_技能包" / "manual-gates" / "scripts" / "manual_mcp" / "projects"
    return {
        "policy": policy,
        "dashboard": dashboard,
        "preflight_count": len(preflight),
        "latest_regression": _latest(regression),
        "latest_policy_audit": _latest(policy_audits),
        "backup_manifest_count": len(backup_manifest),
        "audit_chain_count": len(audit_chain),
        "latest_audit_record": _latest(audit_chain),
        "approval_interrupt_count": len(approval_interrupts),
        "memory_retrieval_count": len(retrieval_packets),
        "production_readiness_count": len(readiness_reports),
        "cost_budget_usage_count": len(cost_usage),
        "mathematical_reasoning_count": len(math_events),
        "session_state": session_state,
        "gate_project_count": _count(gates, "*/state.json"),
    }


def _assess(project: str = "manual-agent-os") -> dict:
    ev = _evidence()
    policy = ev["policy"]
    dashboard = ev["dashboard"]
    session = ev["session_state"]
    checks = {
        "runtime_control_plane": bool(policy.get("version") and policy.get("mandatory_preflight_runtime_integration")),
        "mandatory_preflight": bool(policy.get("preflight_bundle", {}).get("forced_by_mandatory_runtime_hook")),
        "local_regression_gate": bool(ev["latest_regression"].get("passed")),
        "completion_evidence_gate": bool(policy.get("completion_verifier", {}).get("certificate_required_before_done_claim")),
        "policy_consistency_audit": bool(ev["latest_policy_audit"].get("passed")),
        "backup_integrity": ev["backup_manifest_count"] > 0,
        "agentops_dashboard": bool(dashboard.get("health", {}).get("has_preflight") and dashboard.get("health", {}).get("has_backup_integrity")),
        "audit_hash_chain": bool(ev["audit_chain_count"] > 0 and dashboard.get("health", {}).get("has_audit_hash_chain")),
        "approval_interrupts": bool(policy.get("approval_interrupt", {}).get("enabled") and ev["approval_interrupt_count"] > 0),
        "memory_retrieval": bool(policy.get("memory_retrieval", {}).get("enabled") and ev["memory_retrieval_count"] > 0),
        "production_readiness": bool(policy.get("production_readiness", {}).get("enabled") and ev["production_readiness_count"] > 0),
        "cost_budget": bool(policy.get("cost_budget", {}).get("enabled") and policy.get("cost_budget", {}).get("paid_api_requires_approval")),
        "mathematical_reasoning": bool(policy.get("mathematical_reasoning", {}).get("enabled") and ev["mathematical_reasoning_count"] > 0),
        "long_running_checkpoints": int(session.get("checkpoint_count", 0)) > 0,
        "manual_gates": ev["gate_project_count"] > 0,
        "safe_capability_profile": bool(policy.get("capability_profile", {}).get("default_denied_operations")),
    }
    passed = sum(1 for value in checks.values() if value)
    total = len(checks)
    score = round(passed / total, 4)
    if score >= 0.9:
        level = "L4++"
    elif score >= 0.75:
        level = "L4+"
    elif score >= 0.6:
        level = "L4"
    else:
        level = "L3"
    l5_ready = score == 1.0 and not L5_BLOCKERS
    assessment = {
        "id": f"autonomy-assessment-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "score": score,
        "passed_capabilities": passed,
        "total_capabilities": total,
        "level": "L5" if l5_ready else level,
        "checks": checks,
        "capability_definitions": CAPABILITIES,
        "l5_blockers": L5_BLOCKERS,
        "evidence_summary": {
            "policy_version": policy.get("version"),
            "dashboard_version": dashboard.get("agent_os_version"),
            "preflight_count": ev["preflight_count"],
            "latest_regression_passed": ev["latest_regression"].get("passed"),
            "latest_policy_audit_passed": ev["latest_policy_audit"].get("passed"),
            "backup_manifest_count": ev["backup_manifest_count"],
            "audit_chain_count": ev["audit_chain_count"],
            "latest_audit_hash": ev["latest_audit_record"].get("hash"),
            "approval_interrupt_count": ev["approval_interrupt_count"],
            "memory_retrieval_count": ev["memory_retrieval_count"],
            "production_readiness_count": ev["production_readiness_count"],
            "cost_budget_usage_count": ev["cost_budget_usage_count"],
            "mathematical_reasoning_count": ev["mathematical_reasoning_count"],
            "checkpoint_count": session.get("checkpoint_count", 0),
            "gate_project_count": ev["gate_project_count"],
        },
    }
    assessment["report_path"] = _write_report(assessment)
    _append(assessment)
    return assessment


def _append(record: dict) -> None:
    ASSESSMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ASSESSMENT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_report(assessment: dict) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{assessment['id']}.md"
    lines = [
        "# Autonomy Level Assessment",
        "",
        f"- Project: {assessment['project']}",
        f"- Generated: {assessment['ts']}",
        f"- Level: {assessment['level']}",
        f"- Score: {assessment['passed_capabilities']}/{assessment['total_capabilities']} ({assessment['score']})",
        "",
        "## Capability Checks",
        "",
    ]
    for name, passed in assessment["checks"].items():
        lines.append(f"- {name}: {passed}")
    lines.extend(["", "## L5 Blockers", ""])
    for blocker in assessment["l5_blockers"]:
        lines.append(f"- {blocker}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def build_server() -> FastMCP:
    mcp = FastMCP("autonomy-level-assessor-mcp")

    @mcp.tool()
    def autonomy_level_assessor_brief() -> str:
        """Describe autonomy level assessor."""
        return _json({
            "name": "autonomy-level-assessor-mcp",
            "version": "v6.33",
            "capabilities": CAPABILITIES,
            "storage": str(ASSESSMENT_FILE),
        })

    @mcp.tool()
    def assess_autonomy_level(project: str = "manual-agent-os") -> str:
        """Assess current autonomy level from local evidence."""
        return _json(_assess(project))

    @mcp.tool()
    def autonomy_assessment_report(project: str = "") -> str:
        """Return recent autonomy assessments."""
        rows = _read_jsonl(ASSESSMENT_FILE)
        if project:
            rows = [row for row in rows if row.get("project") == project]
        return _json({
            "project": project or "all",
            "assessment_count": len(rows),
            "latest": rows[-1] if rows else None,
            "storage": str(ASSESSMENT_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
