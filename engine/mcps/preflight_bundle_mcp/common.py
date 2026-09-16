# -*- coding: utf-8 -*-
"""Preflight Bundle MCP server.

v6.15 produces one pre-task admission bundle for cognitive intake, failures,
memory, corrections, capability, side-effect admission, and middleware stack.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _append_jsonl as shared_append_jsonl
from _shared.io import _json as shared_json
from _shared.io import _loads as shared_loads
from _shared.time import _now as shared_now

from capability_profile_mcp.common import _check as _capability_check
from cognitive_intake_mcp.common import _classify as _classify_task, _execution_card
from compiled_correction_mcp.common import _check as _correction_check, _read_jsonl as _read_correction_jsonl, RULE_FILE
from failure_replay_mcp.common import _build_plan as _build_failure_plan, _search_failures
from memory_consolidation_mcp.common import _read_jsonl as _read_memory_jsonl, CONSOLIDATED_FILE
from runtime_middleware_mcp.common import CLASS_STACKS
from side_effect_admission_mcp.common import _classify_effect

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_DIR = ROOT / "09_投研" / "preflight_bundle"
PREFLIGHT_FILE = PREFLIGHT_DIR / "preflight_bundles.jsonl"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _append(record: dict) -> dict:
    shared_append_jsonl(PREFLIGHT_FILE, record)
    return record


def _search_memories(query: str, limit: int = 5) -> list[dict]:
    q = set(query.lower().split())
    hits = []
    for item in _read_memory_jsonl(CONSOLIDATED_FILE):
        text = json.dumps(item, ensure_ascii=False).lower()
        score = sum(1 for token in q if token in text)
        if score:
            hit = dict(item)
            hit["_score"] = score
            hits.append(hit)
    hits.sort(key=lambda x: x["_score"], reverse=True)
    return hits[:limit]


def _bundle(project: str, task: str, operation: str, risk: str, context: dict) -> dict:
    decision = _classify_task(task, {"risk": risk, **context})
    task_class = decision["task_class"]
    failure_hits = _search_failures(task, project, 5, 0.05) if task_class == "C" else []
    failure_plan = _build_failure_plan(project, task, failure_hits) if task_class == "C" else {"matched_failures": 0, "avoidance_rules": []}
    memories = _search_memories(task) if task_class == "C" else []
    all_rules = _read_correction_jsonl(RULE_FILE)
    rules = [
        rule for rule in all_rules
        if rule.get("project") in {project, "global", ""}
    ]
    correction_result = _correction_check(json.dumps({"task": task, "execution_card": _execution_card(project, task, decision)}, ensure_ascii=False), rules)
    capability = _capability_check(task, operation, risk, False)
    side_effect = _classify_effect(task, operation, risk)
    stack = CLASS_STACKS.get(task_class, CLASS_STACKS["A"])
    blockers = []
    if task_class == "D":
        blockers.append("cognitive intake classified task as blocked")
    if task_class == "C" and not decision.get("requires_research"):
        blockers.append("important project missing research requirement")
    if task_class == "C" and not correction_result.get("passed", True):
        blockers.append("compiled correction rules not satisfied")
    if not capability.get("allowed") and operation not in {"local_read", "web_research"}:
        blockers.append("capability profile rejected operation")
    if side_effect["side_effect_level"] == "blocked":
        blockers.append("side-effect admission rejected operation")
    go = not blockers
    return {
        "id": f"preflight-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "task": task,
        "task_class": task_class,
        "go": go,
        "decision": decision,
        "execution_card": _execution_card(project, task, decision),
        "required_stack": stack,
        "failure_replay": {"matched": len(failure_hits), "plan": failure_plan},
        "memory_consolidation": {"matched": len(memories), "hits": memories},
        "compiled_corrections": correction_result,
        "capability_profile": capability,
        "side_effect_admission": side_effect,
        "blockers": blockers,
    }


def build_server() -> FastMCP:
    mcp = FastMCP("preflight-bundle-mcp")

    @mcp.tool()
    def preflight_bundle_brief() -> str:
        """Describe unified preflight bundle."""
        return _json({"name": "preflight-bundle-mcp", "version": "v6.15", "storage": str(PREFLIGHT_FILE)})

    @mcp.tool()
    def run_preflight_bundle(project: str, task: str, operation: str = "local_edit",
                             risk: str = "normal", context_json: str = "{}") -> str:
        """Run unified preflight checks and record bundle."""
        bundle = _bundle(project, task, operation, risk, _loads(context_json, {}))
        _append(bundle)
        return _json(bundle)

    @mcp.tool()
    def preflight_report(project: str = "") -> str:
        """Return recent preflight bundles."""
        rows = []
        if PREFLIGHT_FILE.exists():
            for line in PREFLIGHT_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        if project:
            rows = [r for r in rows if r.get("project") == project]
        return _json({"project": project or "all", "count": len(rows), "go": sum(1 for r in rows if r.get("go")), "no_go": sum(1 for r in rows if not r.get("go")), "recent": rows[-10:]})

    return mcp


def main() -> None:
    build_server().run()
