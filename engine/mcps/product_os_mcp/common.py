# -*- coding: utf-8 -*-
"""Product OS MCP server.

v5.19 adds an upper product autonomy layer. It turns a product idea into a
local, auditable product cycle: intent, PRD, design, architecture, task plan,
runtime evidence, acceptance, feedback backlog, memory, dashboard, and report.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.io import _loads as shared_loads
from _shared.io import _write_json as shared_write_json
from _shared.state import safe_name
from _shared.time import _now as shared_now

from agent_orchestration_mcp.common import _arbitrate, _execute_task, _run_summary, _save_run
from dashboard_mcp.common import _collect as _collect_dashboard
from dashboard_mcp.common import _write_dashboard
from experience_memory_mcp.common import _append as _memory_append
from mandatory_runtime_hook_mcp.common import _mandatory_cycle
from runtime_integration_mcp.common import _integrated_cycle
from task_queue_mcp.common import _save_task

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"


# 查找顺序：DATA_ROOT（运行时数据区）优先，避免写进包根
def _find_named_dir(prefix: str, canonical: str) -> Path:
    """在运行时数据区定位目录，找不到就按规范名建一个。

    参数 canonical 可能是通配符形式（如 "03_*MCP"），
    这里会剥掉通配符字符再用 —— 否则 Windows 建目录会报
    WinError 123（文件名含非法字符）。

    为什么不搜包根：打包后包根是源码区，不该往里写运行时数据。
    """
    if not DATA_ROOT.is_dir():
        DATA_ROOT.mkdir(parents=True, exist_ok=True)

    # 规范名去掉通配符，作为建目录用的合法名
    safe = canonical.replace("*", "").replace("?", "").strip("_\/") or "data"

    for p in sorted(DATA_ROOT.iterdir()):
        if p.is_dir() and p.name == safe:
            return p
    for p in sorted(DATA_ROOT.iterdir()):
        if p.is_dir() and p.name.startswith(prefix):
            return p

    out = DATA_ROOT / safe
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError:
        out = DATA_ROOT / prefix.rstrip("_")
        out.mkdir(parents=True, exist_ok=True)
    return out

RESEARCH_DIR = _find_named_dir("09_", "09_投研")
PRODUCT_ROOT = RESEARCH_DIR / "product_os"
QUEUE_ROOT = RESEARCH_DIR / "task_queue"

FORBIDDEN_TERMS = {
    "administrator",
    "admin privilege",
    "runas",
    "sudo",
    "uac",
    "system service",
    "service install",
    "github token",
    "api key",
    "deploy production",
    "public deploy",
    "管理员",
    "提权",
    "系统服务",
    "密钥",
    "公网部署",
}


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _safe_name(name: str) -> str:
    return safe_name(name, allowed="-_.", default="local-product", strip_chars="._-")


def _product_dir(product: str) -> Path:
    return PRODUCT_ROOT / _safe_name(product)


def _write_json(path: Path, data: dict) -> str:
    return shared_write_json(path, data)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(product: str, name: str) -> Path:
    return _product_dir(product) / name


def _blocked_terms(text: str, extra: dict | None = None) -> list[str]:
    blob = f"{text} {json.dumps(extra or {}, ensure_ascii=False)}".lower()
    return sorted(term for term in FORBIDDEN_TERMS if term.lower() in blob)


def _derive_product_name(idea: str) -> str:
    clean = idea.strip().replace("\n", " ")
    if not clean:
        return "local-product"
    ascii_slug = _safe_name(clean[:36].replace(" ", "-"))
    return ascii_slug if ascii_slug != "local-product" else "personal-taskboard"


def _infer_persona(idea: str) -> str:
    text = idea.lower()
    if any(x in text for x in ["team", "团队", "协作"]):
        return "small team operator"
    if any(x in text for x in ["cad", "装配", "三维", "3d"]):
        return "technical designer"
    return "individual power user"


def _intent_payload(product: str, idea: str, context: dict | None = None) -> dict:
    persona = _infer_persona(idea)
    blocked = _blocked_terms(idea, context)
    return {
        "project": product,
        "idea": idea,
        "created": _now(),
        "persona": persona,
        "problem": idea,
        "scope": "local-first MVP",
        "autonomy": "L3-local",
        "safety_boundary": {
            "admin_privileges": "forbidden",
            "public_deploy": "forbidden_without_user_approval",
            "secrets": "forbidden",
        },
        "blocked_terms": blocked,
        "status": "blocked" if blocked else "parsed",
    }


def _prd_payload(product: str, intent: dict) -> dict:
    title = product.replace("-", " ").replace("_", " ").strip() or "local product"
    return {
        "project": product,
        "created": _now(),
        "title": title,
        "target_user": intent.get("persona", "individual power user"),
        "problem_statement": intent.get("problem", ""),
        "goals": [
            "capture product intent as structured evidence",
            "produce a small local MVP plan",
            "run acceptance and feed learnings into backlog",
        ],
        "non_goals": [
            "no administrator privilege escalation",
            "no system service installation",
            "no public deployment or real external account write",
        ],
        "mvp_requirements": [
            {"id": "R1", "requirement": "store product brief, PRD, design, architecture, plan, cycle, acceptance, feedback, and report as JSON artifacts"},
            {"id": "R2", "requirement": "route execution through mandatory runtime and local integration evidence"},
            {"id": "R3", "requirement": "record reusable product lessons in experience memory"},
            {"id": "R4", "requirement": "provide pass/fail acceptance with concrete missing evidence"},
        ],
        "acceptance_criteria": [
            "all required artifacts exist and are non-empty",
            "runtime path records mandatory_entry=true",
            "multi-agent arbitration approves local product evidence",
            "feedback backlog contains at least one next iteration item",
        ],
    }


def _design_payload(product: str, prd: dict) -> dict:
    return {
        "project": product,
        "created": _now(),
        "information_architecture": [
            "Brief",
            "PRD",
            "Design",
            "Architecture",
            "Plan",
            "Runtime Evidence",
            "Acceptance",
            "Feedback Backlog",
        ],
        "core_views": [
            {"view": "product cockpit", "purpose": "scan current product state, artifacts, pass/fail status, and next iteration"},
            {"view": "artifact viewer", "purpose": "inspect PRD, design, architecture, and acceptance evidence"},
            {"view": "feedback backlog", "purpose": "convert acceptance gaps and user notes into prioritized work"},
        ],
        "interaction_model": [
            "one command can run a complete local product cycle",
            "each stage can be regenerated independently",
            "acceptance failures become backlog items rather than silent success",
        ],
        "content_rules": [
            "prefer explicit artifact paths over prose-only claims",
            "surface safety boundaries in generated product plans",
            "keep local execution reversible and auditable",
        ],
    }


def _architecture_payload(product: str, prd: dict) -> dict:
    return {
        "project": product,
        "created": _now(),
        "style": "local-first layered orchestration",
        "components": [
            {"name": "product_os_mcp", "role": "upper product controller"},
            {"name": "mandatory_runtime_hook_mcp", "role": "govern every execution"},
            {"name": "runtime_integration_mcp", "role": "write workflow, trace, parallel evidence, health markers"},
            {"name": "task_queue_mcp", "role": "durable local queue evidence"},
            {"name": "experience_memory_mcp", "role": "cross-session product lessons"},
            {"name": "dashboard_mcp", "role": "static local observability"},
        ],
        "data_model": {
            "root": str(_product_dir(product)),
            "artifacts": [
                "product_brief.json",
                "prd.json",
                "design.json",
                "architecture.json",
                "product_plan.json",
                "product_cycle.json",
                "acceptance.json",
                "feedback_backlog.json",
                "product_report.json",
            ],
        },
        "runtime_policy": {
            "autonomy": "L3 local",
            "admin_privileges": "not requested",
            "external_write": "not performed",
            "secrets": "not used",
        },
    }


def _plan_payload(product: str, prd: dict, design: dict, architecture: dict) -> dict:
    tasks = [
        {"id": "T1", "node": 4, "owner": "strategy", "task": "confirm local product objective and safety boundary", "status": "planned"},
        {"id": "T2", "node": 9, "owner": "design", "task": "freeze product contract and artifact schema", "status": "planned"},
        {"id": "T3", "node": 17, "owner": "dev", "task": "run local governed product cycle", "status": "planned"},
        {"id": "T4", "node": 19, "owner": "qa", "task": "acceptance and multi-agent arbitration", "status": "planned"},
        {"id": "T5", "node": 24, "owner": "ops", "task": "record feedback and next iteration backlog", "status": "planned"},
    ]
    return {
        "project": product,
        "created": _now(),
        "track": "quick",
        "autonomy": "L3",
        "critical_path": ["T1", "T2", "T3", "T4", "T5"],
        "tasks": tasks,
        "dependencies": [
            {"from": "T1", "to": "T2"},
            {"from": "T2", "to": "T3"},
            {"from": "T3", "to": "T4"},
            {"from": "T4", "to": "T5"},
        ],
        "ready_definition": "all product artifacts can be generated locally without admin privileges",
        "done_definition": "acceptance passes and report plus feedback backlog are written",
    }


def _enqueue_evidence_task(product: str, task: str, context: dict) -> dict:
    item = {
        "id": f"product-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "project": product,
        "task": task,
        "status": "queued",
        "priority": 10,
        "risk": "normal",
        "track": "quick",
        "autonomy": "L3",
        "operation": "product_os_local_cycle",
        "attempts": 0,
        "max_attempts": 1,
        "context": context,
        "result": {},
        "created": _now(),
        "updated": _now(),
        "started": None,
        "ended": None,
    }
    _save_task(item)
    return item


def _consensus(product: str, objective: str) -> dict:
    tasks = [
        {"task_id": "prd", "agent": "planning-agent", "task": f"check PRD evidence for {objective}", "mode": "simulate", "evidence": "PRD artifact present"},
        {"task_id": "design", "agent": "dev-agent", "task": f"check implementation readiness for {objective}", "mode": "simulate", "evidence": "architecture and plan artifacts present"},
        {"task_id": "qa", "agent": "qa-agent", "task": f"check acceptance for {objective}", "mode": "simulate", "evidence": "local smoke evidence present"},
        {"task_id": "security", "agent": "security-agent", "task": f"check local-only boundary for {objective}", "mode": "simulate", "evidence": "local-only evidence; account write absent; key material absent"},
        {"task_id": "review", "agent": "review-agent", "task": f"check evidence chain for {objective}", "mode": "simulate", "evidence": "manual-gates quick nodes required"},
    ]
    run_id = f"product-consensus-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    run = {
        "run_id": run_id,
        "project": product,
        "objective": objective,
        "created": _now(),
        "updated": _now(),
        "max_workers": 5,
        "tasks": tasks,
        "results": [_execute_task(task) for task in tasks],
        "status": "running",
    }
    run["summary"] = _run_summary(run)
    run["arbitration"] = _arbitrate(run)
    run["status"] = run["arbitration"]["final_decision"]
    _save_run(product, run)
    return {
        "run_id": run_id,
        "status": run["status"],
        "summary": run["summary"],
        "arbitration": run["arbitration"],
    }


def _refresh_dashboard() -> dict:
    data = _collect_dashboard()
    return _write_dashboard(data)


def _acceptance_payload(product: str) -> dict:
    required = [
        "product_brief.json",
        "prd.json",
        "design.json",
        "architecture.json",
        "product_plan.json",
        "product_cycle.json",
    ]
    checks = []
    for name in required:
        path = _artifact(product, name)
        checks.append({"artifact": name, "exists": path.exists(), "non_empty": path.exists() and path.stat().st_size > 0, "path": str(path)})
    cycle = _read_json(_artifact(product, "product_cycle.json"))
    mandatory = cycle.get("mandatory_runtime", {})
    integration = cycle.get("runtime_integration", {})
    consensus = cycle.get("consensus", {})
    checks.extend([
        {"check": "mandatory_entry", "passed": bool(mandatory.get("mandatory_entry")), "evidence": mandatory.get("state_path", "")},
        {"check": "runtime_integration_completed", "passed": integration.get("status") == "completed", "evidence": integration.get("path", "")},
        {"check": "agent_arbitration_approved", "passed": consensus.get("arbitration", {}).get("final_decision") == "approved", "evidence": consensus.get("run_id", "")},
    ])
    failed = [c for c in checks if not c.get("non_empty", c.get("passed", False))]
    return {
        "project": product,
        "created": _now(),
        "status": "passed" if not failed else "failed",
        "checks": checks,
        "failed_checks": failed,
        "admin_privileges": "not_requested",
        "external_write": "not_performed",
    }


def _feedback_payload(product: str, note: str = "") -> dict:
    acceptance = _read_json(_artifact(product, "acceptance.json"))
    items = []
    for idx, failed in enumerate(acceptance.get("failed_checks", []), 1):
        items.append({
            "id": f"FB-{idx}",
            "source": "acceptance",
            "priority": "high",
            "item": f"fix failed check: {failed.get('artifact') or failed.get('check')}",
            "status": "open",
        })
    if not items:
        items.append({
            "id": "FB-1",
            "source": "retro",
            "priority": "medium",
            "item": "next iteration: turn generated product artifacts into an executable UI/app scaffold when user supplies a product idea",
            "status": "open",
        })
    if note:
        items.append({"id": f"FB-{len(items) + 1}", "source": "user", "priority": "medium", "item": note, "status": "open"})
    return {
        "project": product,
        "created": _now(),
        "items": items,
        "next_iteration_ready": bool(items),
    }


def _report_payload(product: str) -> dict:
    names = [
        "product_brief.json",
        "prd.json",
        "design.json",
        "architecture.json",
        "product_plan.json",
        "product_cycle.json",
        "acceptance.json",
        "feedback_backlog.json",
    ]
    artifacts = {name: str(_artifact(product, name)) for name in names if _artifact(product, name).exists()}
    acceptance = _read_json(_artifact(product, "acceptance.json"))
    return {
        "project": product,
        "generated": _now(),
        "status": acceptance.get("status", "unknown"),
        "autonomy_level": "L5 local product autonomy prototype",
        "artifacts": artifacts,
        "safety": {
            "administrator_privileges": "not_requested",
            "system_service": "not_installed",
            "public_deploy": "not_performed",
            "secrets": "not_used",
        },
        "next": _read_json(_artifact(product, "feedback_backlog.json")).get("items", []),
    }


def _run_cycle(product: str, idea: str = "", context: dict | None = None) -> dict:
    product = _safe_name(product or _derive_product_name(idea))
    context = context or {}
    if idea:
        intent = _intent_payload(product, idea, context)
        _write_json(_artifact(product, "product_brief.json"), intent)
    else:
        intent = _read_json(_artifact(product, "product_brief.json"))
    if intent.get("status") == "blocked":
        return {"status": "blocked", "project": product, "reason": "unsafe product idea", "blocked_terms": intent.get("blocked_terms", [])}

    prd = _prd_payload(product, intent)
    design = _design_payload(product, prd)
    architecture = _architecture_payload(product, prd)
    plan = _plan_payload(product, prd, design, architecture)
    _write_json(_artifact(product, "prd.json"), prd)
    _write_json(_artifact(product, "design.json"), design)
    _write_json(_artifact(product, "architecture.json"), architecture)
    _write_json(_artifact(product, "product_plan.json"), plan)

    queue_item = _enqueue_evidence_task(product, "run local product autonomy cycle", {"idea": idea, "artifact_root": str(_product_dir(product))})
    mandatory = _mandatory_cycle(
        project=product,
        task="run product OS local cycle",
        risk="normal",
        approved=False,
        track="quick",
        autonomy="L3",
        tool="product_os_mcp.run_product_cycle",
        node_id=17,
        context={"idea": idea, "queue_task_id": queue_item["id"]},
    )
    integration_state = _integrated_cycle(product, "integrate product OS local cycle", "quick", "L3")
    consensus = _consensus(product, idea or product)
    cycle = {
        "project": product,
        "created": _now(),
        "status": "completed",
        "queue_task": queue_item,
        "mandatory_runtime": mandatory,
        "runtime_integration": {
            "status": integration_state.get("status"),
            "path": str(RESEARCH_DIR / "runtime_integration" / _safe_name(product) / "integration.json"),
            "artifacts": integration_state.get("artifacts", {}),
        },
        "consensus": consensus,
        "admin_privileges": "not_requested",
    }
    _write_json(_artifact(product, "product_cycle.json"), cycle)

    acceptance = _acceptance_payload(product)
    _write_json(_artifact(product, "acceptance.json"), acceptance)
    feedback = _feedback_payload(product)
    _write_json(_artifact(product, "feedback_backlog.json"), feedback)
    report = _report_payload(product)
    _write_json(_artifact(product, "product_report.json"), report)

    memory = _memory_append({
        "type": "outcome",
        "project": product,
        "task": "product OS autonomous cycle",
        "status": acceptance["status"],
        "tests": ["product_os_mcp.run_product_cycle", "product_os_mcp.product_acceptance"],
        "issues": acceptance.get("failed_checks", []),
        "gate_status": "ready_for_manual_gates_quick",
        "lesson": "Product autonomy needs product-level artifacts plus mandatory runtime, acceptance, backlog, and report evidence.",
        "next_retrieval_query": "product autonomy MCP run_product_cycle acceptance feedback backlog",
    })
    dashboard = _refresh_dashboard()
    return {
        "status": acceptance["status"],
        "project": product,
        "root": str(_product_dir(product)),
        "artifacts": report["artifacts"],
        "memory_id": memory.get("id"),
        "dashboard": dashboard,
        "safety": report["safety"],
    }


def build_server() -> FastMCP:
    mcp = FastMCP("product-os-mcp")

    @mcp.tool()
    def product_os_brief() -> str:
        """Describe product autonomy capabilities and boundaries."""
        return _json({
            "name": "product-os-mcp",
            "version": "v5.19",
            "purpose": "turn product ideas into local product-cycle artifacts, governed runtime evidence, acceptance, feedback backlog, and report",
            "storage_root": str(PRODUCT_ROOT),
            "route": ["intent", "prd", "design", "architecture", "plan", "mandatory_runtime", "runtime_integration", "acceptance", "feedback", "memory", "dashboard"],
            "admin_privileges": "forbidden",
        })

    @mcp.tool()
    def parse_product_idea(product: str, idea: str, context_json: str = "{}") -> str:
        """Parse a product idea into a local product brief."""
        product = _safe_name(product or _derive_product_name(idea))
        payload = _intent_payload(product, idea, _loads(context_json, {}))
        path = _write_json(_artifact(product, "product_brief.json"), payload)
        return _json({"status": payload["status"], "project": product, "path": path, "brief": payload})

    @mcp.tool()
    def create_prd(product: str) -> str:
        """Create PRD from the product brief."""
        product = _safe_name(product)
        intent = _read_json(_artifact(product, "product_brief.json"))
        payload = _prd_payload(product, intent)
        path = _write_json(_artifact(product, "prd.json"), payload)
        return _json({"status": "written", "project": product, "path": path, "prd": payload})

    @mcp.tool()
    def generate_product_design(product: str) -> str:
        """Create product design artifact."""
        product = _safe_name(product)
        payload = _design_payload(product, _read_json(_artifact(product, "prd.json")))
        path = _write_json(_artifact(product, "design.json"), payload)
        return _json({"status": "written", "project": product, "path": path, "design": payload})

    @mcp.tool()
    def propose_architecture(product: str) -> str:
        """Create architecture artifact."""
        product = _safe_name(product)
        payload = _architecture_payload(product, _read_json(_artifact(product, "prd.json")))
        path = _write_json(_artifact(product, "architecture.json"), payload)
        return _json({"status": "written", "project": product, "path": path, "architecture": payload})

    @mcp.tool()
    def create_product_plan(product: str) -> str:
        """Create local product execution plan."""
        product = _safe_name(product)
        payload = _plan_payload(
            product,
            _read_json(_artifact(product, "prd.json")),
            _read_json(_artifact(product, "design.json")),
            _read_json(_artifact(product, "architecture.json")),
        )
        path = _write_json(_artifact(product, "product_plan.json"), payload)
        return _json({"status": "written", "project": product, "path": path, "plan": payload})

    @mcp.tool()
    def run_product_cycle(product: str, idea: str = "", context_json: str = "{}") -> str:
        """Run a full local product autonomy cycle."""
        return _json(_run_cycle(product, idea, _loads(context_json, {})))

    @mcp.tool()
    def product_acceptance(product: str) -> str:
        """Run product acceptance against local evidence."""
        product = _safe_name(product)
        payload = _acceptance_payload(product)
        path = _write_json(_artifact(product, "acceptance.json"), payload)
        return _json({"status": payload["status"], "project": product, "path": path, "acceptance": payload})

    @mcp.tool()
    def record_product_feedback(product: str, note: str = "") -> str:
        """Record feedback backlog item(s)."""
        product = _safe_name(product)
        payload = _feedback_payload(product, note)
        path = _write_json(_artifact(product, "feedback_backlog.json"), payload)
        return _json({"status": "written", "project": product, "path": path, "feedback": payload})

    @mcp.tool()
    def product_status(product: str) -> str:
        """Return product artifact status."""
        product = _safe_name(product)
        root = _product_dir(product)
        names = [
            "product_brief.json",
            "prd.json",
            "design.json",
            "architecture.json",
            "product_plan.json",
            "product_cycle.json",
            "acceptance.json",
            "feedback_backlog.json",
            "product_report.json",
        ]
        artifacts = []
        for name in names:
            path = root / name
            artifacts.append({"name": name, "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0, "path": str(path)})
        acceptance = _read_json(root / "acceptance.json")
        return _json({"project": product, "root": str(root), "status": acceptance.get("status", "not_accepted"), "artifacts": artifacts})

    @mcp.tool()
    def export_product_report(product: str, output_path: str = "") -> str:
        """Export product report JSON."""
        product = _safe_name(product)
        payload = _report_payload(product)
        path = Path(output_path) if output_path else _artifact(product, "product_report.json")
        _write_json(path, payload)
        return _json({"status": "exported", "project": product, "path": str(path), "report": payload})

    return mcp


def main() -> None:
    build_server().run()
