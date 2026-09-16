# -*- coding: utf-8 -*-
"""Cognitive Intake MCP server.

This is node 0 for the AI execution manual. It classifies a user request before
work starts, so the agent can choose a proportional workflow and avoid blind
implementation, wasted compute, or pseudo-closure.
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
LOG_DIR = ROOT / "09_投研" / "cognitive_intake"
LOG_FILE = LOG_DIR / "intake_decisions.jsonl"

DIRECT_ANSWER_TERMS = {
    "解释", "区别", "是什么", "为什么", "怎么看", "分析下", "级别", "建议",
    "what", "why", "explain", "difference", "compare",
}
SMALL_TASK_TERMS = {
    "检查", "查看", "改一行", "修一下", "运行测试", "是否存在", "启动",
    "check", "inspect", "small fix", "test", "run",
}
IMPORTANT_PROJECT_TERMS = {
    "闭环", "真实", "产品", "系统", "agent", "mcp", "插件", "打包", "exe",
    "短剧", "视频", "音频", "plc", "工业", "汇川", "升级", "进化", "大模型",
    "开发", "设计", "生成", "接入", "api", "sdk", "workflow", "runtime",
    "重要", "全网搜索", "借鉴", "复用",
}
PROJECT_ACTION_TERMS = {
    "闭环", "真实", "打包", "exe", "升级", "进化", "开发", "设计", "生成",
    "接入", "api", "sdk", "workflow", "runtime", "全网搜索", "借鉴", "复用",
    "完成", "实现", "部署", "运行", "create", "build", "implement", "integrate",
    "upgrade", "package", "deliver",
}
HIGH_RISK_TERMS = {
    "管理员", "root", "sudo", "删除", "覆盖", "reset", "remove", "delete",
    "生产", "发布", "部署", "push", "pr", "ci", "密钥", "token", "credential",
    "api key", "真实付款", "付费", "硬件运行", "plc实机", "全局注册",
}
PSEUDO_CLOSURE_TERMS = {
    "真实视频", "真实生成", "真实运行", "生产部署", "实机", "商用", "发布",
    "real video", "production", "deploy",
}


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _hits(text: str, terms: set[str]) -> list[str]:
    lower = text.lower()
    return sorted(term for term in terms if term.lower() in lower)


def _risk_level(high_hits: list[str], important_hits: list[str]) -> str:
    if any(term in high_hits for term in ["管理员", "root", "sudo", "密钥", "token", "credential"]):
        return "critical"
    if high_hits:
        return "high"
    if important_hits:
        return "normal"
    return "low"


def _infer_intent(task: str) -> str:
    text = task.strip()
    if len(text) <= 80:
        return text
    return text[:77] + "..."


def _completion_criteria(task_class: str, deliverable: str) -> list[str]:
    if task_class == "A":
        return ["回答直接对应用户问题", "不启动重型项目流程", "明确不确定性或边界"]
    if task_class == "B":
        return ["完成指定本地动作", "给出可核验结果", "必要时运行最小验证"]
    if task_class == "C":
        return [
            "先完成同类方案/资料调研或写明例外",
            "给出可见工作流和完成定义",
            f"交付产物存在且与目标一致：{deliverable}",
            "运行最小验证并记录结果",
            "通过 manual-gates 关键节点",
            "完成备份",
        ]
    return ["停止高风险动作", "列出阻塞原因", "给出恢复路径或所需授权/资源"]


def _minimum_validation(task_class: str) -> str:
    return {
        "A": "逻辑自检：答案是否解决问题、是否避免无依据承诺。",
        "B": "最小命令或文件检查；能跑测试则跑对应测试。",
        "C": "py_compile/smoke test/manual-gates gate_report/备份存在性检查。",
        "D": "验证阻塞条件真实存在，不能用模拟结果替代真实交付。",
    }[task_class]


def _forbidden_claims(pseudo_hits: list[str], task_class: str) -> list[str]:
    claims = [
        "不能把 dry-run、概念稿、占位文件、模拟结果说成真实完成。",
        "不能在缺少 API key、硬件、授权、网络或外部账号时声称已真实交付。",
    ]
    if task_class != "C" and not pseudo_hits:
        return claims[:1]
    return claims


def _classify(task: str, context: dict | None = None) -> dict:
    context = context or {}
    text = " ".join([task, json.dumps(context, ensure_ascii=False)])
    direct_hits = _hits(text, DIRECT_ANSWER_TERMS)
    small_hits = _hits(text, SMALL_TASK_TERMS)
    important_hits = _hits(text, IMPORTANT_PROJECT_TERMS)
    project_action_hits = _hits(text, PROJECT_ACTION_TERMS)
    high_hits = _hits(text, HIGH_RISK_TERMS)
    pseudo_hits = _hits(text, PSEUDO_CLOSURE_TERMS)

    explain_only = bool(direct_hits) and not small_hits and not project_action_hits and not high_hits

    if high_hits and any(x in high_hits for x in ["管理员", "root", "sudo", "生产", "发布", "部署", "密钥", "token", "credential"]):
        task_class = "D"
    elif explain_only:
        task_class = "A"
    elif small_hits and not project_action_hits and context.get("force_important") is not True:
        task_class = "B"
    elif important_hits or context.get("force_important") is True:
        task_class = "C"
    else:
        task_class = "A"

    risk = _risk_level(high_hits, important_hits)
    deliverable = context.get("deliverable") or ("direct answer" if task_class == "A" else "verified task result")
    path = {
        "A": "direct_answer",
        "B": "quick",
        "C": "important_project",
        "D": "blocked",
    }[task_class]
    compute = {
        "A": "low",
        "B": "low",
        "C": "medium" if risk == "normal" else "high",
        "D": "low",
    }[task_class]
    blockers = []
    if task_class == "D":
        blockers.append("requires explicit approval, external credential, production access, admin permission, or real-world resource")

    return {
        "task_class": task_class,
        "user_intent": _infer_intent(task),
        "deliverable": deliverable,
        "completion_criteria": _completion_criteria(task_class, deliverable),
        "minimum_validation": _minimum_validation(task_class),
        "requires_research": task_class == "C",
        "requires_visible_workflow": task_class == "C",
        "hard_blockers": blockers,
        "risk_level": risk,
        "compute_budget": compute,
        "recommended_path": path,
        "forbidden_claims": _forbidden_claims(pseudo_hits, task_class),
        "signals": {
            "direct_answer_hits": direct_hits,
            "small_task_hits": small_hits,
            "important_project_hits": important_hits,
            "project_action_hits": project_action_hits,
            "high_risk_hits": high_hits,
            "pseudo_closure_hits": pseudo_hits,
        },
        "next_actions": _next_actions(task_class),
    }


def _next_actions(task_class: str) -> list[str]:
    if task_class == "A":
        return ["answer directly", "state limits if any"]
    if task_class == "B":
        return ["execute scoped action", "run minimum validation", "report result"]
    if task_class == "C":
        return [
            "produce execution card",
            "perform comparable research or cite research exception",
            "implement scoped deliverables",
            "run smoke tests",
            "submit manual-gates checks",
            "create backup",
        ]
    return ["stop risky execution", "report blocker", "request missing safe input only if unavoidable"]


def _execution_card(project: str, task: str, decision: dict) -> dict:
    return {
        "project": project,
        "task": task,
        "task_class": decision["task_class"],
        "path": decision["recommended_path"],
        "risk_level": decision["risk_level"],
        "compute_budget": decision["compute_budget"],
        "workflow": decision["next_actions"],
        "completion_criteria": decision["completion_criteria"],
        "minimum_validation": decision["minimum_validation"],
        "stop_rules": decision["hard_blockers"] or ["stop if real delivery cannot be proven"],
    }


def _append_log(project: str, task: str, decision: dict) -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "id": f"intake-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "task": task,
        "decision": decision,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def build_server() -> FastMCP:
    mcp = FastMCP("cognitive-intake-mcp")

    @mcp.tool()
    def cognitive_intake_brief() -> str:
        """Describe node 0 cognitive intake rules."""
        return _json({
            "name": "cognitive-intake-mcp",
            "version": "v6.2",
            "purpose": "在所有重要动作前做任务分级、风险判断、完成定义和最小验证建议",
            "classes": {
                "A": "ordinary Q&A: direct answer",
                "B": "small task: quick path",
                "C": "important project: research + workflow + gates + backup",
                "D": "high risk or hard blocker: stop and report recovery path",
            },
            "log_file": str(LOG_FILE),
        })

    @mcp.tool()
    def classify_task(task: str, context_json: str = "{}") -> str:
        """Classify a user request into A/B/C/D before execution."""
        return _json(_classify(task, _loads(context_json, {})))

    @mcp.tool()
    def build_execution_card(project: str, task: str, context_json: str = "{}") -> str:
        """Build a visible workflow card for important projects or quick tasks."""
        decision = _classify(task, _loads(context_json, {}))
        return _json(_execution_card(project, task, decision))

    @mcp.tool()
    def assess_response_consequence(task: str, proposed_response: str = "") -> str:
        """Check whether a response risks wasting compute or making false closure claims."""
        decision = _classify(task)
        response_text = proposed_response.lower()
        risk_flags = []
        if decision["task_class"] == "A" and any(x in response_text for x in ["先立项", "打包备份", "manual-gates"]):
            risk_flags.append("over_processing")
        if any(x in response_text for x in ["已真实生成", "已部署", "生产已完成"]) and decision["signals"]["pseudo_closure_hits"]:
            risk_flags.append("pseudo_closure")
        return _json({
            "task_class": decision["task_class"],
            "risk_flags": risk_flags,
            "useful_response_rule": "回答前必须判断：是否解决用户问题、是否会造成错误承诺、是否消耗超过任务价值的流程成本。",
            "forbidden_claims": decision["forbidden_claims"],
        })

    @mcp.tool()
    def intake_decision(project: str, task: str, context_json: str = "{}", record: bool = True) -> str:
        """Return classification, execution card, and optionally append an audit log."""
        decision = _classify(task, _loads(context_json, {}))
        card = _execution_card(project, task, decision)
        result = {"project": project, "decision": decision, "execution_card": card}
        if record:
            result["record"] = _append_log(project, task, decision)
        return _json(result)

    @mcp.tool()
    def intake_report(project: str) -> str:
        """Return recent intake decisions for a project."""
        rows = []
        if LOG_FILE.exists():
            for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("project") == project:
                    rows.append(row)
        counts: dict[str, int] = {}
        for row in rows:
            cls = row.get("decision", {}).get("task_class", "unknown")
            counts[cls] = counts.get(cls, 0) + 1
        return _json({
            "project": project,
            "count_by_class": counts,
            "decision_count": len(rows),
            "recent": rows[-10:],
            "log_file": str(LOG_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
