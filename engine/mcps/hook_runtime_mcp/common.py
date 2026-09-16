# -*- coding: utf-8 -*-
"""Hook Runtime MCP server.

This is a lifecycle policy layer, not a system hook injector. It evaluates
what should happen before/after tool use and when the session stops.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = ROOT / "09_投研" / "hook_runtime"
HOOK_LOG = HOOK_DIR / "hook_events.jsonl"

RESEARCH_HINTS = {"搜索", "检索", "联网", "调研", "选型", "模型", "框架", "库", "pypi", "npm", "github", "api", "最新"}
MEMORY_HINTS = {"继续", "之前", "相似", "经验", "复盘", "失败", "打回", "rule_candidate"}
RISK_HINTS = {"删除", "覆盖", "全局配置", "注册", "发布", "部署", "权限", "生产", "密钥", "安装", "卸载"}
STOP_HINTS = {"结束", "停止", "收尾", "备份", "总结", "复盘", "关闭"}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _contains(text: str, hints: set[str]) -> list[str]:
    low = text.lower()
    return sorted([h for h in hints if h.lower() in low])


def _append(event: dict) -> dict:
    rec = {"id": f"hook-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}", "ts": shared_now(), **event}
    shared_append_jsonl(HOOK_LOG, rec)
    return rec


def _policy(task: str, event_type: str, tool: str, node_id: int, risk: str) -> dict:
    text = " ".join([task, event_type, tool, risk])
    research = _contains(text, RESEARCH_HINTS)
    memory = _contains(text, MEMORY_HINTS)
    risk_hits = _contains(text, RISK_HINTS)
    stop = _contains(text, STOP_HINTS)

    actions = []
    if event_type in {"pre_tool", "start"} and (research or node_id in {2, 8, 11, 15}):
        actions.append({
            "hook": "PreToolUse",
            "action": "call_research",
            "tool": "research-mcp.research_brief",
            "reason": "新技术/选型/外部变化/复用判断前必须调研",
            "evidence": research or [f"node:{node_id}"],
        })
    if event_type in {"pre_tool", "start", "resume"} and (memory or node_id in {15, 16, 17, 19, 24}):
        actions.append({
            "hook": "PreToolUse",
            "action": "search_memory",
            "tool": "experience-memory-mcp.semantic_search_memory",
            "reason": "开工/续跑/关键节点前先查经验",
            "evidence": memory or [f"node:{node_id}"],
        })
    if event_type in {"post_tool", "post_test", "review"} or node_id in {15, 16, 17, 19, 24}:
        actions.append({
            "hook": "PostToolUse",
            "action": "record_memory",
            "tool": "experience-memory-mcp.record_*",
            "reason": "工具结果、失败、通过、评审、复盘要写回经验",
        })
    if risk.lower() in {"high", "critical"} or risk_hits:
        actions.append({
            "hook": "PreToolUse",
            "action": "request_human_approval",
            "tool": "manual approval",
            "reason": "高风险/全局配置/发布/删除动作必须人工审批",
            "evidence": risk_hits or ([risk] if risk else []),
        })
    if event_type in {"stop", "close"} or stop:
        actions.append({
            "hook": "Stop",
            "action": "finalize_gate_and_backup",
            "tool": "manual-gates.gate_report + backup",
            "reason": "结束时要做门禁与备份闭环",
            "evidence": stop,
        })
    return {
        "task": task,
        "event_type": event_type,
        "tool": tool,
        "node_id": node_id,
        "risk": risk or "normal",
        "actions": actions,
        "action_count": len(actions),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("hook-runtime-mcp")

    @mcp.tool()
    def hook_brief() -> str:
        """Describe hook runtime policy."""
        return _json({
            "name": "hook-runtime-mcp",
            "purpose": "把 Auto-Trigger 从查询层升级为生命周期策略层",
            "hooks": ["PreToolUse", "PostToolUse", "Stop", "PreCompact"],
            "does_not": ["不注入系统 hooks", "不替代 manual-gates", "不直接执行危险动作"],
            "log_file": str(HOOK_LOG),
        })

    @mcp.tool()
    def pre_tool_use(project: str, task: str, tool: str, node_id: int = 0, risk: str = "normal") -> str:
        """Evaluate pre-tool actions."""
        plan = _policy(task, "pre_tool", tool, node_id, risk)
        plan["project"] = project
        return _json(plan)

    @mcp.tool()
    def post_tool_use(project: str, task: str, tool: str, result: str = "",
                      node_id: int = 0) -> str:
        """Evaluate post-tool actions."""
        plan = _policy(task, "post_tool", tool, node_id, "normal")
        plan["project"] = project
        plan["result"] = result
        return _json(plan)

    @mcp.tool()
    def stop_hook(project: str, task: str, reason: str = "", backup_path: str = "",
                  gate_status: str = "") -> str:
        """Plan stop-time actions like gate_report, backup, and memory record."""
        plan = _policy(task or reason, "stop", "stop", 24, "normal")
        plan["project"] = project
        plan["reason"] = reason
        plan["backup_path"] = backup_path
        plan["gate_status"] = gate_status
        _append({"project": project, "task": task, "reason": reason, "gate_status": gate_status, "backup_path": backup_path})
        return _json(plan)

    @mcp.tool()
    def evaluate_chain(project: str, task: str, tool: str = "", node_id: int = 0,
                       event_type: str = "pre_tool", risk: str = "normal") -> str:
        """Evaluate the full hook chain for one event."""
        plan = _policy(task, event_type, tool, node_id, risk)
        plan["project"] = project
        return _json(plan)

    @mcp.tool()
    def record_hook_event(project: str, task: str, hook: str, action: str,
                          details_json: str = "{}") -> str:
        """Append a hook event to the audit log."""
        rec = _append({
            "project": project,
            "task": task,
            "hook": hook,
            "action": action,
            "details": _loads(details_json, {}),
        })
        return _json({"status": "recorded", "record": rec})

    return mcp


def main() -> None:
    build_server().run()
