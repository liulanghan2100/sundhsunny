# -*- coding: utf-8 -*-
"""Cost Budget MCP server.

v6.32 adds local budget guardrails. Budget is a runtime policy signal: allow,
warn, or block before a task can burn external API spend. This MCP records local
estimates only and does not call paid APIs.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
BUDGET_DIR = DATA_ROOT / "09_投研" / "cost_budget"
BUDGET_FILE = BUDGET_DIR / "budgets.json"
USAGE_FILE = BUDGET_DIR / "usage.jsonl"

DEFAULT_BUDGET = {
    "version": "v6.32",
    "currency": "USD",
    "default_project_budget": 0.0,
    "warn_ratio": 0.8,
    "block_when_exceeded": True,
    "paid_api_requires_approval": True,
    "note": "0.0 means no autonomous paid API spend is allowed by default",
}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _load_budget() -> dict:
    if not BUDGET_FILE.exists():
        BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
        BUDGET_FILE.write_text(json.dumps(DEFAULT_BUDGET, ensure_ascii=False, indent=2), encoding="utf-8")
    data = json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_BUDGET)
    merged.update(data)
    return merged


def _save_budget(budget: dict) -> str:
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(budget, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(BUDGET_FILE)


def _read_usage() -> list[dict]:
    if not USAGE_FILE.exists():
        return []
    rows = []
    for line in USAGE_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _append_usage(record: dict) -> dict:
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _project_limit(project: str, budget: dict) -> float:
    per_project = budget.get("projects", {})
    return float(per_project.get(project, budget.get("default_project_budget", 0.0)))


def _spent(project: str) -> float:
    return round(sum(float(row.get("estimated_cost", 0.0)) for row in _read_usage() if row.get("project") == project), 6)


def _check(project: str, estimated_cost: float, operation: str = "local_mcp",
           approval_id: str = "") -> dict:
    budget = _load_budget()
    limit = _project_limit(project, budget)
    spent = _spent(project)
    projected = round(spent + max(0.0, float(estimated_cost)), 6)
    paid_operation = operation in {"paid_api_call", "external_model_call", "video_generation_api"}
    requires_approval = paid_operation and budget.get("paid_api_requires_approval") and not approval_id
    exceeded = limit <= 0.0 and projected > 0.0 or (limit > 0.0 and projected > limit)
    warn = limit > 0.0 and projected >= limit * float(budget.get("warn_ratio", 0.8))
    allowed = not requires_approval and not (exceeded and budget.get("block_when_exceeded", True))
    return {
        "project": project,
        "operation": operation,
        "estimated_cost": round(float(estimated_cost), 6),
        "spent": spent,
        "limit": limit,
        "projected": projected,
        "allowed": allowed,
        "warn": warn,
        "blocked": not allowed,
        "requires_approval": requires_approval,
        "approval_id": approval_id,
        "decision": "allow" if allowed else "block",
        "reason": "within local budget" if allowed else "budget exceeded or paid API approval missing",
    }


def build_server() -> FastMCP:
    mcp = FastMCP("cost-budget-mcp")

    @mcp.tool()
    def cost_budget_brief() -> str:
        """Describe local budget guardrails."""
        return _json({
            "name": "cost-budget-mcp",
            "version": "v6.32",
            "budget": _load_budget(),
            "usage": str(USAGE_FILE),
            "does_not": ["call_paid_api", "store_secret", "request_admin"],
        })

    @mcp.tool()
    def define_budget(budget_json: str) -> str:
        """Replace budget policy."""
        budget = _loads(budget_json, DEFAULT_BUDGET)
        path = _save_budget(budget)
        return _json({"status": "saved", "path": path, "budget": budget})

    @mcp.tool()
    def check_budget(project: str, estimated_cost: float = 0.0,
                     operation: str = "local_mcp", approval_id: str = "") -> str:
        """Check whether a cost-like operation is within budget."""
        return _json(_check(project, estimated_cost, operation, approval_id))

    @mcp.tool()
    def record_usage(project: str, estimated_cost: float = 0.0,
                     operation: str = "local_mcp", tool: str = "",
                     units_json: str = "{}", approval_id: str = "") -> str:
        """Record local cost-like usage after budget check."""
        decision = _check(project, estimated_cost, operation, approval_id)
        record = {
            "id": f"usage-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "ts": _now(),
            "project": project,
            "tool": tool,
            "units": _loads(units_json, {}),
            **decision,
        }
        if decision["allowed"]:
            _append_usage(record)
        return _json(record)

    @mcp.tool()
    def budget_report(project: str = "") -> str:
        """Return budget and usage summary."""
        rows = _read_usage()
        if project:
            rows = [row for row in rows if row.get("project") == project]
        by_project: dict[str, float] = {}
        for row in rows:
            p = row.get("project", "")
            by_project[p] = round(by_project.get(p, 0.0) + float(row.get("estimated_cost", 0.0)), 6)
        return _json({
            "project": project or "all",
            "budget": _load_budget(),
            "usage_count": len(rows),
            "spent_by_project": by_project,
            "recent": rows[-10:],
            "storage": str(USAGE_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
