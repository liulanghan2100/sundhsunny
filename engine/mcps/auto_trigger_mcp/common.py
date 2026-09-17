# -*- coding: utf-8 -*-
"""Auto Trigger MCP server.

This server does not execute risky actions. It decides which manual-gates,
research, memory, workflow, and approval actions should be triggered for a
task/event.
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

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
LOG_DIR = DATA_ROOT / "09_投研" / "auto_trigger"
LOG_FILE = LOG_DIR / "trigger_events.jsonl"

RESEARCH_TERMS = {
    "搜索", "检索", "联网", "调研", "pyp", "pypi", "npm", "github", "模型",
    "框架", "库", "最新", "当前", "对比", "选型", "价格", "法规", "API",
}
MEMORY_SEARCH_TERMS = {"继续", "之前", "相似", "经验", "复盘", "失败", "打回", "恢复"}
IMPORTANT_PROJECT_TERMS = {
    "important", "closed-loop", "close loop", "agent", "mcp", "plugin", "exe",
    "production", "release", "package", "video", "audio", "plc", "industrial",
    "system", "product", "framework", "model", "api", "sdk",
    "重要", "闭环", "真实", "产品", "系统", "插件", "打包", "短剧", "视频",
    "音频", "工业", "汇川", "西门子", "大模式", "升级", "进化", "同类", "借鉴", "复用",
}
MEMORY_RECORD_EVENTS = {
    "decision", "tool_result", "test_pass", "test_fail", "gate_pass",
    "gate_fail", "review_revoked", "review_sustained", "retrospective",
}
GATE_TERMS = {"完成", "验收", "检查", "门禁", "打包", "备份", "发布", "测试"}
APPROVAL_TERMS = {
    "删除", "覆盖", "全局配置", "注册", "发布", "部署", "生产", "密钥",
    "权限", "安装", "卸载", "破坏", "reset", "remove", "delete",
}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _contains_any(text: str, terms: set[str]) -> list[str]:
    lower = text.lower()
    return sorted([t for t in terms if t.lower() in lower])


def _append_event(event: dict) -> dict:
    rec = {"id": f"trigger-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}", "ts": shared_now(), **event}
    shared_append_jsonl(LOG_FILE, rec)
    return rec


def _trigger_plan(task: str, event_type: str, node_id: int, risk: str) -> dict:
    text = f"{task} {event_type} {risk}"
    research_hits = _contains_any(text, RESEARCH_TERMS)
    important_hits = _contains_any(text, IMPORTANT_PROJECT_TERMS)
    memory_hits = _contains_any(text, MEMORY_SEARCH_TERMS)
    gate_hits = _contains_any(text, GATE_TERMS)
    approval_hits = _contains_any(text, APPROVAL_TERMS)

    triggers = []
    if research_hits or important_hits or node_id in (2, 8, 11, 15):
        triggers.append({
            "trigger": "research_required",
            "reason": "important project or external selection requires web research before design/implementation",
            "tool": "research-mcp.research_brief",
            "evidence": research_hits + important_hits,
            "required_artifact": "09_投研/<project>/pre_research_report.md",
        })
    if memory_hits or event_type in {"start", "plan", "resume"}:
        triggers.append({
            "trigger": "memory_search_required",
            "reason": "开工/续跑/规划前需要检索相似经验",
            "tool": "experience-memory-mcp.semantic_search_memory",
            "evidence": memory_hits,
        })
    if event_type in MEMORY_RECORD_EVENTS:
        triggers.append({
            "trigger": "memory_record_required",
            "reason": "关键决策、工具结果、测试、评审或复盘需要结构化记忆",
            "tool": "experience-memory-mcp.record_*",
            "evidence": [event_type],
        })
    if gate_hits or node_id in {4, 9, 17, 19, 24} or event_type in {"artifact_ready", "stage_end", "release"}:
        triggers.append({
            "trigger": "gate_check_required",
            "reason": "节点产物、阶段收尾或 Quick 轨关键节点需要门禁验证",
            "tool": "manual-gates.submit_check/gate_report",
            "evidence": gate_hits + ([f"node:{node_id}"] if node_id else []),
        })
    if approval_hits or risk.lower() in {"high", "critical"}:
        triggers.append({
            "trigger": "human_approval_required",
            "reason": "涉及高风险、全局配置、发布、删除、权限或生产动作",
            "tool": "human approval",
            "evidence": approval_hits + ([risk] if risk else []),
        })
    return {
        "task": task,
        "event_type": event_type,
        "node_id": node_id,
        "risk": risk or "normal",
        "triggers": triggers,
        "trigger_count": len(triggers),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("auto-trigger-mcp")

    @mcp.tool()
    def trigger_brief() -> str:
        """Describe auto-trigger rules and manual-gates integration."""
        return _json({
            "name": "auto-trigger-mcp",
            "purpose": "把调研、记忆、门禁和人工审批从可选调用升级为规则触发建议",
            "does_not": ["不直接删除文件", "不直接发布生产", "不绕过 manual-gates"],
            "triggers": [
                "research_required",
                "memory_search_required",
                "memory_record_required",
                "gate_check_required",
                "human_approval_required",
            ],
            "log_file": str(LOG_FILE),
        })

    @mcp.tool()
    def evaluate_triggers(project: str, task: str, event_type: str = "plan",
                          node_id: int = 0, risk: str = "normal",
                          context_json: str = "{}") -> str:
        """Evaluate which actions should trigger for a task/event."""
        plan = _trigger_plan(task, event_type, node_id, risk)
        plan["project"] = project
        plan["context"] = _loads(context_json, {})
        return _json(plan)

    @mcp.tool()
    def record_trigger_event(project: str, task: str, event_type: str,
                             triggers_json: str = "[]", result: str = "",
                             node_id: int = 0) -> str:
        """Append an auto-trigger decision event for audit."""
        rec = _append_event({
            "project": project,
            "task": task,
            "event_type": event_type,
            "node_id": node_id,
            "triggers": _loads(triggers_json, []),
            "result": result,
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def startup_checklist(project: str, task: str, track: str = "standard",
                          autonomy: str = "L2") -> str:
        """Return the first actions an agent should perform before implementation."""
        plan = _trigger_plan(task, "start", 0, "normal")
        actions = [
            {"tool": "manual-gates.set_mode", "args": {"project": project, "track": track, "autonomy": autonomy}},
            {"tool": "manual-gates.full_map", "args": {"project": project}},
        ]
        actions.extend({"tool": t["tool"], "reason": t["reason"]} for t in plan["triggers"])
        return _json({"project": project, "task": task, "startup_actions": actions})

    return mcp


def main() -> None:
    build_server().run()
