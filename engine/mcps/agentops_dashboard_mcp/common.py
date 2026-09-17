# -*- coding: utf-8 -*-
"""AgentOps Dashboard MCP server.

v6.10 aggregates local Agent OS signals into dashboard-ready JSON and Markdown.

v6.20 extends the dashboard with preflight, local regression, policy audit, and
completion certificate signals.

v6.24 adds backup integrity manifest and verification signals.

v6.26 adds autonomy level assessment signals.

v6.28 adds audit hash chain visibility signals.

v6.29 adds approval interrupt queue signals.

v6.30 adds memory retrieval packet signals.

v6.31 adds production readiness report signals.

v6.32 adds cost budget usage signals.

v6.33 adds mathematical reasoning event signals.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
RESEARCH = DATA_ROOT / "09_投研"
BACKUP = DATA_ROOT / "10_备份"
DASH_DIR = RESEARCH / "agentops_dashboard"
DASH_JSON = DASH_DIR / "agentops_dashboard.json"
DASH_MD = DASH_DIR / "agentops_dashboard.md"
GATES_PROJECTS = DATA_ROOT / "04_技能包" / "manual-gates" / "scripts" / "manual_mcp" / "projects"


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"type": "corrupt_line", "raw": line})
    return rows


def _count_files(path: Path, pattern: str) -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


def _latest_files(path: Path, pattern: str, limit: int = 10) -> list[dict]:
    if not path.exists():
        return []
    files = sorted(path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": f.name, "path": str(f), "bytes": f.stat().st_size, "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()} for f in files[:limit]]


def _latest_recursive(path: Path, pattern: str, limit: int = 10) -> list[dict]:
    if not path.exists():
        return []
    files = sorted(path.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": f.name, "path": str(f), "bytes": f.stat().st_size, "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()} for f in files[:limit]]


def _gate_stats() -> dict:
    states = list(GATES_PROJECTS.glob("*/state.json")) if GATES_PROJECTS.exists() else []
    projects = []
    passed_total = 0
    nodes_total = 0
    for path in states:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        nodes = state.get("nodes", {})
        passed = sum(1 for n in nodes.values() if n.get("status") == "passed")
        total = len(nodes)
        passed_total += passed
        nodes_total += total
        projects.append({
            "project": state.get("project", path.parent.name),
            "track": state.get("track", ""),
            "passed": passed,
            "total": total,
            "path": str(path),
        })
    projects.sort(key=lambda x: x["project"], reverse=True)
    return {
        "project_count": len(projects),
        "node_progress": f"{passed_total}/{nodes_total}",
        "latest_projects": projects[:10],
    }


def _build_dashboard() -> dict:
    failures = _read_jsonl(RESEARCH / "failure_replay" / "failures.jsonl")
    lessons = _read_jsonl(RESEARCH / "failure_replay" / "distilled_lessons.jsonl")
    lifecycle_events = []
    lifecycle_root = RESEARCH / "tool_lifecycle_tracing"
    if lifecycle_root.exists():
        for file in lifecycle_root.glob("*/tool_lifecycle.jsonl"):
            lifecycle_events.extend(_read_jsonl(file))
    eval_cases = _read_jsonl(RESEARCH / "evaluation_harness" / "eval_cases.jsonl")
    eval_runs = _read_jsonl(RESEARCH / "evaluation_harness" / "eval_runs.jsonl")
    preflight_bundles = _read_jsonl(RESEARCH / "preflight_bundle" / "preflight_bundles.jsonl")
    regression_runs = _read_jsonl(RESEARCH / "local_regression_gate" / "regression_runs.jsonl")
    policy_audits = _read_jsonl(RESEARCH / "policy_consistency_auditor" / "policy_consistency_audits.jsonl")
    backup_manifest = _read_jsonl(RESEARCH / "backup_integrity" / "backup_manifest.jsonl")
    autonomy_assessments = _read_jsonl(RESEARCH / "autonomy_level_assessor" / "autonomy_assessments.jsonl")
    audit_chain = _read_jsonl(RESEARCH / "audit_hash_chain" / "audit_chain.jsonl")
    approval_interrupts = _read_jsonl(RESEARCH / "approval_interrupts" / "interrupts.jsonl")
    retrieval_packets = _read_jsonl(RESEARCH / "memory_retrieval" / "retrieval_packets.jsonl")
    readiness_reports = _read_jsonl(RESEARCH / "production_readiness" / "readiness_reports.jsonl")
    cost_usage = _read_jsonl(RESEARCH / "cost_budget" / "usage.jsonl")
    math_events = _read_jsonl(RESEARCH / "mathematical_reasoning" / "reasoning_events.jsonl")
    consolidated = _read_jsonl(RESEARCH / "memory_consolidation" / "consolidated_memory.jsonl")
    correction_rules = _read_jsonl(RESEARCH / "compiled_corrections" / "compiled_rules.jsonl")
    backups = _latest_files(BACKUP, "*.zip", 12)
    certificates = _latest_recursive(RESEARCH / "completion_verifier", "completion_certificate.json", 12)
    errors = [e for e in lifecycle_events if e.get("event_type") == "tool_error"]
    latest_eval = eval_runs[-1] if eval_runs else None
    latest_regression = regression_runs[-1] if regression_runs else None
    latest_policy_audit = policy_audits[-1] if policy_audits else None
    latest_autonomy = autonomy_assessments[-1] if autonomy_assessments else None
    latest_audit_record = audit_chain[-1] if audit_chain else None
    latest_readiness = readiness_reports[-1] if readiness_reports else None
    return {
        "generated": _now(),
        "agent_os_version": "v6.33",
        "summary": {
            "backups": _count_files(BACKUP, "*.zip"),
            "gate_projects": _gate_stats()["project_count"],
            "failure_cases": len(failures),
            "distilled_lessons": len(lessons),
            "tool_lifecycle_events": len(lifecycle_events),
            "tool_errors": len(errors),
            "eval_cases": len(eval_cases),
            "eval_runs": len(eval_runs),
            "preflight_bundles": len(preflight_bundles),
            "preflight_no_go": sum(1 for item in preflight_bundles if not item.get("go")),
            "local_regression_runs": len(regression_runs),
            "local_regression_failures": sum(1 for item in regression_runs if not item.get("passed")),
            "policy_audits": len(policy_audits),
            "policy_audit_failures": sum(1 for item in policy_audits if not item.get("passed")),
            "backup_manifest_entries": len(backup_manifest),
            "backup_manifest_projects": len({item.get("project") for item in backup_manifest if item.get("project")}),
            "autonomy_assessments": len(autonomy_assessments),
            "latest_autonomy_level": latest_autonomy.get("level") if latest_autonomy else None,
            "latest_autonomy_score": latest_autonomy.get("score") if latest_autonomy else None,
            "audit_chain_records": len(audit_chain),
            "latest_audit_hash": latest_audit_record.get("hash") if latest_audit_record else None,
            "approval_interrupts": len(approval_interrupts),
            "pending_approval_interrupts": sum(1 for item in approval_interrupts if item.get("status") == "pending"),
            "auto_allowed_interrupts": sum(1 for item in approval_interrupts if item.get("auto_allowed")),
            "memory_retrieval_packets": len(retrieval_packets),
            "production_readiness_reports": len(readiness_reports),
            "latest_readiness": latest_readiness.get("readiness") if latest_readiness else None,
            "cost_budget_usage_records": len(cost_usage),
            "estimated_cost_total": round(sum(float(item.get("estimated_cost", 0.0)) for item in cost_usage), 6),
            "mathematical_reasoning_events": len(math_events),
            "completion_certificates": len(certificates),
            "consolidated_memories": len(consolidated),
            "compiled_correction_rules": len(correction_rules),
        },
        "gates": _gate_stats(),
        "latest_backup": backups[0] if backups else None,
        "recent_backups": backups,
        "latest_eval": latest_eval,
        "latest_regression": latest_regression,
        "latest_policy_audit": latest_policy_audit,
        "recent_completion_certificates": certificates,
        "recent_preflight": preflight_bundles[-10:],
        "recent_regression_runs": regression_runs[-10:],
        "recent_policy_audits": policy_audits[-10:],
        "recent_backup_manifest": backup_manifest[-10:],
        "latest_autonomy_assessment": latest_autonomy,
        "recent_autonomy_assessments": autonomy_assessments[-10:],
        "latest_audit_chain_record": latest_audit_record,
        "recent_audit_chain": audit_chain[-10:],
        "recent_approval_interrupts": approval_interrupts[-10:],
        "recent_memory_retrieval_packets": retrieval_packets[-10:],
        "latest_production_readiness": latest_readiness,
        "recent_production_readiness": readiness_reports[-10:],
        "recent_cost_budget_usage": cost_usage[-10:],
        "recent_mathematical_reasoning": math_events[-10:],
        "recent_failures": failures[-10:],
        "recent_tool_errors": errors[-10:],
        "health": {
            "has_failure_replay": len(failures) > 0,
            "has_eval_runs": len(eval_runs) > 0,
            "has_preflight": len(preflight_bundles) > 0,
            "has_local_regression": len(regression_runs) > 0 and latest_regression and latest_regression.get("passed"),
            "has_policy_audit": len(policy_audits) > 0 and latest_policy_audit and latest_policy_audit.get("passed"),
            "has_backup_integrity": len(backup_manifest) > 0,
            "has_autonomy_assessment": latest_autonomy is not None,
            "has_audit_hash_chain": len(audit_chain) > 0,
            "has_approval_interrupts": len(approval_interrupts) > 0,
            "has_memory_retrieval": len(retrieval_packets) > 0,
            "has_production_readiness": latest_readiness is not None,
            "has_cost_budget": len(cost_usage) > 0,
            "has_mathematical_reasoning": len(math_events) > 0,
            "has_completion_certificates": len(certificates) > 0,
            "has_correction_rules": len(correction_rules) > 0,
            "has_recent_backup": bool(backups),
        },
    }


def _write_dashboard(data: dict) -> None:
    DASH_DIR.mkdir(parents=True, exist_ok=True)
    DASH_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    s = data["summary"]
    lines = [
        "# AgentOps Dashboard",
        "",
        f"- Generated: {data['generated']}",
        f"- Version: {data['agent_os_version']}",
        "",
        "## Summary",
        "",
        f"- Backups: {s['backups']}",
        f"- Gate projects: {s['gate_projects']}",
        f"- Failure cases: {s['failure_cases']}",
        f"- Tool lifecycle events: {s['tool_lifecycle_events']}",
        f"- Tool errors: {s['tool_errors']}",
        f"- Eval cases/runs: {s['eval_cases']}/{s['eval_runs']}",
        f"- Preflight bundles/no-go: {s['preflight_bundles']}/{s['preflight_no_go']}",
        f"- Local regression runs/failures: {s['local_regression_runs']}/{s['local_regression_failures']}",
        f"- Policy audits/failures: {s['policy_audits']}/{s['policy_audit_failures']}",
        f"- Backup manifest entries/projects: {s['backup_manifest_entries']}/{s['backup_manifest_projects']}",
        f"- Autonomy assessments/latest: {s['autonomy_assessments']}/{s['latest_autonomy_level']}",
        f"- Audit chain records: {s['audit_chain_records']}",
        f"- Latest audit hash: {s['latest_audit_hash']}",
        f"- Approval interrupts/pending: {s['approval_interrupts']}/{s['pending_approval_interrupts']}",
        f"- Memory retrieval packets: {s['memory_retrieval_packets']}",
        f"- Production readiness reports/latest: {s['production_readiness_reports']}/{s['latest_readiness']}",
        f"- Cost budget usage/estimated total: {s['cost_budget_usage_records']}/{s['estimated_cost_total']}",
        f"- Mathematical reasoning events: {s['mathematical_reasoning_events']}",
        f"- Completion certificates: {s['completion_certificates']}",
        f"- Consolidated memories: {s['consolidated_memories']}",
        f"- Compiled correction rules: {s['compiled_correction_rules']}",
    ]
    DASH_MD.write_text("\n".join(lines), encoding="utf-8")


def build_server() -> FastMCP:
    mcp = FastMCP("agentops-dashboard-mcp")

    @mcp.tool()
    def agentops_dashboard_brief() -> str:
        """Describe AgentOps dashboard aggregation."""
        return _json({
            "name": "agentops-dashboard-mcp",
            "version": "v6.33",
            "purpose": "聚合门禁、备份、失败、工具生命周期、评估、记忆和纠正规则为 dashboard 数据",
            "outputs": [str(DASH_JSON), str(DASH_MD)],
        })

    @mcp.tool()
    def refresh_agentops_dashboard() -> str:
        """Refresh dashboard JSON and Markdown."""
        data = _build_dashboard()
        _write_dashboard(data)
        return _json({"status": "refreshed", "json": str(DASH_JSON), "markdown": str(DASH_MD), "summary": data["summary"]})

    @mcp.tool()
    def agentops_dashboard_status() -> str:
        """Return current dashboard data, refreshing if missing."""
        if not DASH_JSON.exists():
            data = _build_dashboard()
            _write_dashboard(data)
        return DASH_JSON.read_text(encoding="utf-8")

    return mcp


def main() -> None:
    build_server().run()
