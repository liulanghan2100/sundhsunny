# -*- coding: utf-8 -*-
"""Policy Consistency Auditor MCP server.

v6.19 detects drift between Manual Agent OS policy-as-code and the runtime
contracts introduced by v6.16-v6.18.

v6.28 adds audit hash chain policy checks.

v6.29 adds approval interrupt policy checks.

v6.30 adds memory retrieval policy checks.

v6.31 adds production readiness policy checks.

v6.32 adds cost budget policy checks.

v6.33 adds mathematical reasoning policy checks.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
RESEARCH = DATA_ROOT / "09_投研"
POLICY_FILE = RESEARCH / "control_plane" / "policy.json"
AUDIT_DIR = RESEARCH / "policy_consistency_auditor"
AUDIT_FILE = AUDIT_DIR / "policy_consistency_audits.jsonl"
REPORT_DIR = AUDIT_DIR / "reports"

REQUIRED_ROUTE = [
    "cognitive_intake",
    "preflight_bundle",
    "mandatory_runtime_hook",
    "hook_runtime_policy",
    "control_plane",
    "runtime_integration",
]

REQUIRED_CLASS_C_STACK = [
    "cognitive_intake",
    "preflight_bundle",
    "pre_research",
    "approval_interrupt",
    "memory_retrieval",
    "failure_replay",
    "memory_consolidation",
    "workflow_runtime",
    "tool_lifecycle_tracing",
    "evaluation_harness",
    "local_regression_gate",
    "completion_verifier",
    "manual_gates",
    "backup",
]

REQUIRED_COMPLETION_EVIDENCE = [
    "cognitive_intake",
    "preflight_bundle",
    "preflight_go",
    "execution_card",
    "pre_research_report",
    "approval_interrupt",
    "memory_retrieval",
    "failure_replay",
    "workflow",
    "tests",
    "eval_run",
    "local_regression_gate",
    "regression_passed",
    "gate_report",
    "backup_path",
    "backup_integrity_manifest",
    "backup_integrity_verified",
    "compiled_correction_check",
]

REQUIRED_SECTIONS = [
    "mandatory_preflight_runtime_integration",
    "preflight_bundle",
    "local_regression_gate",
    "completion_verifier",
    "runtime_middleware",
    "backup_integrity",
    "autonomy_level_assessor",
    "audit_hash_chain",
    "approval_interrupt",
    "memory_retrieval",
    "production_readiness",
    "cost_budget",
    "mathematical_reasoning",
]


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _load_policy() -> dict:
    """读策略文件。

    文件不存在时返回空策略而不是抛异常 ——
    首次调用时 control_plane 可能还没生成 policy.json，
    那种情况应给"未发现策略"的结论，不该让整条链路失败。
    """
    if not POLICY_FILE.is_file():
        return {"_missing": True, "_path": str(POLICY_FILE)}
    try:
        return json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"_error": f"{type(e).__name__}: {e}", "_path": str(POLICY_FILE)}


def _append(record: dict) -> None:
    shared_append_jsonl(AUDIT_FILE, record)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _missing(required: list[str], actual: Any) -> list[str]:
    actual_set = set(actual if isinstance(actual, list) else [])
    return [item for item in required if item not in actual_set]


def _check(name: str, passed: bool, details: dict) -> dict:
    return {"name": name, "passed": passed, **details}


def _audit(project: str, write_report: bool = True) -> dict:
    policy = _load_policy()
    checks = []

    missing_sections = [section for section in REQUIRED_SECTIONS if section not in policy]
    checks.append(_check("required_policy_sections", not missing_sections, {"missing": missing_sections}))

    route = policy.get("mandatory_preflight_runtime_integration", {}).get("required_route", [])
    checks.append(_check("mandatory_preflight_route", route == REQUIRED_ROUTE, {
        "expected": REQUIRED_ROUTE,
        "actual": route,
    }))

    cognitive_route = policy.get("mandatory_cognitive_runtime_hook", {}).get("required_route", [])
    checks.append(_check("cognitive_runtime_route", cognitive_route == REQUIRED_ROUTE, {
        "expected": REQUIRED_ROUTE,
        "actual": cognitive_route,
    }))

    stack = policy.get("runtime_middleware", {}).get("class_c_stack", [])
    missing_stack = _missing(REQUIRED_CLASS_C_STACK, stack)
    checks.append(_check("runtime_middleware_class_c_stack", not missing_stack, {
        "missing": missing_stack,
        "actual": stack,
    }))

    evidence = policy.get("completion_verifier", {}).get("class_c_required_evidence", [])
    missing_evidence = _missing(REQUIRED_COMPLETION_EVIDENCE, evidence)
    checks.append(_check("completion_verifier_class_c_evidence", not missing_evidence, {
        "missing": missing_evidence,
        "actual": evidence,
    }))

    preflight = policy.get("preflight_bundle", {})
    checks.append(_check("preflight_forced_by_runtime_hook", preflight.get("forced_by_mandatory_runtime_hook") is True, {
        "actual": preflight.get("forced_by_mandatory_runtime_hook"),
    }))

    regression = policy.get("local_regression_gate", {})
    checks.append(_check("local_regression_required_for_class_c", "C" in regression.get("required_for_task_class", []), {
        "actual": regression.get("required_for_task_class", []),
    }))

    audit_chain = policy.get("audit_hash_chain", {})
    checks.append(_check("audit_hash_chain_enabled", audit_chain.get("enabled") is True and audit_chain.get("tamper_evident") is True, {
        "enabled": audit_chain.get("enabled"),
        "tamper_evident": audit_chain.get("tamper_evident"),
    }))
    checks.append(_check("audit_hash_chain_boundary_declared", audit_chain.get("not_third_party_signature") is True and audit_chain.get("not_immutable_storage") is True, {
        "not_third_party_signature": audit_chain.get("not_third_party_signature"),
        "not_immutable_storage": audit_chain.get("not_immutable_storage"),
    }))

    approval_interrupt = policy.get("approval_interrupt", {})
    checks.append(_check("approval_interrupt_enabled", approval_interrupt.get("enabled") is True and approval_interrupt.get("only_interrupt_when_required") is True, {
        "enabled": approval_interrupt.get("enabled"),
        "only_interrupt_when_required": approval_interrupt.get("only_interrupt_when_required"),
    }))
    checks.append(_check("approval_interrupt_forbidden_scope_declared", "admin_permission" in approval_interrupt.get("never_auto_approve", []), {
        "never_auto_approve": approval_interrupt.get("never_auto_approve", []),
    }))

    memory_retrieval = policy.get("memory_retrieval", {})
    checks.append(_check("memory_retrieval_enabled", memory_retrieval.get("enabled") is True and memory_retrieval.get("required_before_task_class_c") is True, {
        "enabled": memory_retrieval.get("enabled"),
        "required_before_task_class_c": memory_retrieval.get("required_before_task_class_c"),
    }))
    checks.append(_check("memory_retrieval_sources_declared", {"keyword", "semantic", "vector", "consolidated"} <= set(memory_retrieval.get("sources", [])), {
        "sources": memory_retrieval.get("sources", []),
    }))

    readiness = policy.get("production_readiness", {})
    checks.append(_check("production_readiness_enabled", readiness.get("enabled") is True and readiness.get("required_for_final_summary") is True, {
        "enabled": readiness.get("enabled"),
        "required_for_final_summary": readiness.get("required_for_final_summary"),
    }))

    cost_budget = policy.get("cost_budget", {})
    checks.append(_check("cost_budget_enabled", cost_budget.get("enabled") is True and cost_budget.get("paid_api_requires_approval") is True, {
        "enabled": cost_budget.get("enabled"),
        "paid_api_requires_approval": cost_budget.get("paid_api_requires_approval"),
    }))

    mathematical_reasoning = policy.get("mathematical_reasoning", {})
    required_models = {"bayesian_update", "expected_value", "information_gain", "dependency_graph", "anomaly_detection", "monte_carlo_risk"}
    checks.append(_check("mathematical_reasoning_enabled", mathematical_reasoning.get("enabled") is True, {
        "enabled": mathematical_reasoning.get("enabled"),
    }))
    checks.append(_check("mathematical_reasoning_models_declared", required_models <= set(mathematical_reasoning.get("models", [])), {
        "models": mathematical_reasoning.get("models", []),
    }))

    run = {
        "id": f"policy-audit-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "policy_version": policy.get("version"),
        "type": "policy_consistency_audit",
        "check_count": len(checks),
        "passed_checks": sum(1 for item in checks if item["passed"]),
        "failed_checks": sum(1 for item in checks if not item["passed"]),
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }
    if write_report:
        run["report_path"] = _write_report(run)
    _append(run)
    return run


def _write_report(run: dict) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{run['id']}.md"
    lines = [
        "# Policy Consistency Audit",
        "",
        f"- Run: {run['id']}",
        f"- Project: {run['project']}",
        f"- Policy version: {run['policy_version']}",
        f"- Generated: {run['ts']}",
        f"- Passed: {run['passed']}",
        f"- Checks: {run['passed_checks']}/{run['check_count']}",
        "",
        "## Checks",
        "",
    ]
    for check in run["checks"]:
        lines.append(f"- {check['name']}: passed={check['passed']}")
        if check.get("missing"):
            lines.append(f"  missing: {json.dumps(check['missing'], ensure_ascii=False)}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def build_server() -> FastMCP:
    mcp = FastMCP("policy-consistency-auditor-mcp")

    @mcp.tool()
    def policy_consistency_brief() -> str:
        """Describe policy consistency auditor."""
        return _json({
            "name": "policy-consistency-auditor-mcp",
            "version": "v6.33",
            "policy": str(POLICY_FILE),
            "storage": str(AUDIT_FILE),
            "required_route": REQUIRED_ROUTE,
        })

    @mcp.tool()
    def audit_policy_consistency(project: str = "manual-agent-os", write_report: bool = True) -> str:
        """Audit policy consistency and write a report."""
        return _json(_audit(project, write_report))

    @mcp.tool()
    def policy_consistency_report(project: str = "") -> str:
        """Return recent policy consistency audits."""
        rows = _read_jsonl(AUDIT_FILE)
        if project:
            rows = [row for row in rows if row.get("project") == project]
        return _json({
            "project": project or "all",
            "audit_count": len(rows),
            "latest": rows[-1] if rows else None,
            "passed": sum(1 for row in rows if row.get("passed")),
            "failed": sum(1 for row in rows if not row.get("passed")),
            "storage": str(AUDIT_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
