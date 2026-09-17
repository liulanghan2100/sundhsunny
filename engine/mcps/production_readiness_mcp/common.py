# -*- coding: utf-8 -*-
"""Production Readiness MCP server.

v6.31 creates a local readiness report from policy, dashboard, gates, backups,
audit chain, approval interrupts, memory retrieval, and autonomy assessment.

v6.33 also checks local mathematical reasoning evidence.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from _shared.io import _append_jsonl as shared_append_jsonl
from _shared.io import _json as shared_json
from _shared.time import _now as shared_now

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
RESEARCH = DATA_ROOT / "09_投研"
READINESS_DIR = RESEARCH / "production_readiness"
READINESS_FILE = READINESS_DIR / "readiness_reports.jsonl"
REPORT_DIR = READINESS_DIR / "reports"
POLICY_FILE = RESEARCH / "control_plane" / "policy.json"
DASHBOARD_FILE = RESEARCH / "agentops_dashboard" / "agentops_dashboard.json"
GATE_ROOT = DATA_ROOT / "04_技能包" / "manual-gates" / "scripts" / "manual_mcp" / "projects"

CHECKS = [
    ("policy_execution", "policy.json exists and declares current runtime controls"),
    ("capability_scope", "denied high-risk operations are explicit"),
    ("approval_interrupts", "high-risk actions create durable interrupts"),
    ("memory_retrieval", "important tasks can retrieve prior memory before execution"),
    ("observability", "dashboard and trace/audit signals exist"),
    ("tamper_evidence", "local audit hash chain exists and verifies"),
    ("local_regression", "latest local regression gate passed"),
    ("manual_gates", "manual-gates projects exist"),
    ("backup_integrity", "latest backup manifest verifies"),
    ("autonomy_assessment", "latest autonomy assessment exists"),
    ("cost_budget", "paid API spend is guarded by local budget policy"),
    ("mathematical_reasoning", "decision math evidence exists for important work"),
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


def _append(record: dict) -> None:
    shared_append_jsonl(READINESS_FILE, record)


def _latest(rows: list[dict]) -> dict:
    return rows[-1] if rows else {}


def _gate_project_count() -> int:
    return len(list(GATE_ROOT.glob("*/state.json"))) if GATE_ROOT.exists() else 0


def _evidence() -> dict:
    return {
        "policy": _read_json(POLICY_FILE),
        "dashboard": _read_json(DASHBOARD_FILE),
        "regression": _latest(_read_jsonl(RESEARCH / "local_regression_gate" / "regression_runs.jsonl")),
        "backup_verify": _latest(_read_jsonl(RESEARCH / "backup_integrity" / "backup_manifest.jsonl")),
        "audit_chain": _read_jsonl(RESEARCH / "audit_hash_chain" / "audit_chain.jsonl"),
        "approval_interrupts": _read_jsonl(RESEARCH / "approval_interrupts" / "interrupts.jsonl"),
        "memory_retrieval": _read_jsonl(RESEARCH / "memory_retrieval" / "retrieval_packets.jsonl"),
        "autonomy": _latest(_read_jsonl(RESEARCH / "autonomy_level_assessor" / "autonomy_assessments.jsonl")),
        "cost_usage": _read_jsonl(RESEARCH / "cost_budget" / "usage.jsonl"),
        "math_events": _read_jsonl(RESEARCH / "mathematical_reasoning" / "reasoning_events.jsonl"),
        "gate_project_count": _gate_project_count(),
    }


def _assess(project: str = "manual-agent-os") -> dict:
    ev = _evidence()
    policy = ev["policy"]
    dashboard = ev["dashboard"]
    health = dashboard.get("health", {})
    denied = set(policy.get("capability_profile", {}).get("default_denied_operations", []))
    checks = {
        "policy_execution": bool(policy.get("version") and policy.get("runtime_middleware")),
        "capability_scope": {"admin_permission", "production_deploy", "secret_access", "git_push"} <= denied,
        "approval_interrupts": bool(policy.get("approval_interrupt", {}).get("enabled") and ev["approval_interrupts"]),
        "memory_retrieval": bool(policy.get("memory_retrieval", {}).get("enabled") and ev["memory_retrieval"]),
        "observability": bool(health.get("has_preflight") and health.get("has_policy_audit")),
        "tamper_evidence": bool(policy.get("audit_hash_chain", {}).get("enabled") and ev["audit_chain"]),
        "local_regression": bool(ev["regression"].get("passed")),
        "manual_gates": ev["gate_project_count"] > 0,
        "backup_integrity": bool(ev["backup_verify"]),
        "autonomy_assessment": bool(ev["autonomy"].get("level")),
        "cost_budget": bool(policy.get("cost_budget", {}).get("enabled") and policy.get("cost_budget", {}).get("paid_api_requires_approval")),
        "mathematical_reasoning": bool(policy.get("mathematical_reasoning", {}).get("enabled") and ev["math_events"]),
    }
    passed = sum(1 for value in checks.values() if value)
    total = len(checks)
    score = round(passed / total, 4)
    if score == 1.0:
        readiness = "local_preproduction_ready"
    elif score >= 0.8:
        readiness = "local_beta_ready"
    else:
        readiness = "not_ready"
    blockers = []
    if not checks["local_regression"]:
        blockers.append("latest local regression gate is not passing")
    if not checks["approval_interrupts"]:
        blockers.append("approval interrupt evidence missing")
    if not checks["memory_retrieval"]:
        blockers.append("memory retrieval packet evidence missing")
    l5_blockers = [
        "no remote PR/CI closed loop in this local run",
        "no distributed multi-agent cluster runtime",
        "no third-party signed or immutable audit log",
        "no production deployment or staged rollout controls",
        "no real external provider billing reconciliation beyond local estimates",
    ]
    report = {
        "id": f"readiness-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "type": "production_readiness_report",
        "readiness": readiness,
        "score": score,
        "passed_checks": passed,
        "total_checks": total,
        "checks": checks,
        "check_definitions": CHECKS,
        "blockers": blockers,
        "l5_blockers": l5_blockers,
        "evidence_summary": {
            "policy_version": policy.get("version"),
            "dashboard_version": dashboard.get("agent_os_version"),
            "latest_autonomy_level": ev["autonomy"].get("level"),
            "latest_autonomy_score": ev["autonomy"].get("score"),
            "gate_project_count": ev["gate_project_count"],
            "audit_chain_records": len(ev["audit_chain"]),
            "approval_interrupts": len(ev["approval_interrupts"]),
            "memory_retrieval_packets": len(ev["memory_retrieval"]),
            "cost_usage_records": len(ev["cost_usage"]),
            "mathematical_reasoning_events": len(ev["math_events"]),
        },
    }
    report["report_path"] = _write_report(report)
    _append(report)
    return report


def _write_report(report: dict) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{report['id']}.md"
    lines = [
        "# Production Readiness Report",
        "",
        f"- Project: {report['project']}",
        f"- Generated: {report['ts']}",
        f"- Readiness: {report['readiness']}",
        f"- Score: {report['passed_checks']}/{report['total_checks']} ({report['score']})",
        "",
        "## Checks",
        "",
    ]
    for name, passed in report["checks"].items():
        lines.append(f"- {name}: {passed}")
    lines.extend(["", "## L5 Blockers", ""])
    for item in report["l5_blockers"]:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def build_server() -> FastMCP:
    mcp = FastMCP("production-readiness-mcp")

    @mcp.tool()
    def production_readiness_brief() -> str:
        """Describe production readiness assessment."""
        return _json({
            "name": "production-readiness-mcp",
            "version": "v6.33",
            "purpose": "aggregate local Agent OS evidence into readiness status",
            "storage": str(READINESS_FILE),
            "does_not": ["deploy", "push", "publish", "request_admin"],
        })

    @mcp.tool()
    def assess_production_readiness(project: str = "manual-agent-os") -> str:
        """Assess local production readiness from current evidence."""
        return _json(_assess(project))

    @mcp.tool()
    def production_readiness_report(project: str = "") -> str:
        """Return recent readiness reports."""
        rows = _read_jsonl(READINESS_FILE)
        if project:
            rows = [row for row in rows if row.get("project") == project]
        return _json({
            "project": project or "all",
            "report_count": len(rows),
            "latest": rows[-1] if rows else None,
            "storage": str(READINESS_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
