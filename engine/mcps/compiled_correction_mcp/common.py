# -*- coding: utf-8 -*-
"""Compiled Correction MCP server.

v6.9 converts user corrections into deterministic runtime checks.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.state import safe_project

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[2]
CORRECTION_DIR = ROOT / "09_投研" / "compiled_corrections"
CORRECTION_FILE = CORRECTION_DIR / "corrections.jsonl"
RULE_FILE = CORRECTION_DIR / "compiled_rules.jsonl"
REPORT_DIR = CORRECTION_DIR / "reports"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _append(path: Path, record: dict) -> dict:
    shared_append_jsonl(path, record)
    return record


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


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _rule_from_correction(correction: dict) -> dict:
    text = f"{correction.get('correction','')} {correction.get('expected_behavior','')}".lower()
    required_terms = []
    forbidden_terms = []
    if any(x in text for x in ["工作流", "提纲", "大纲", "workflow"]):
        required_terms.extend(["工作流", "执行卡"])
    if any(x in text for x in ["思考", "先想", "后果"]):
        required_terms.extend(["任务等级", "完成标准"])
    if any(x in text for x in ["全网", "搜索", "对比", "借鉴"]):
        required_terms.extend(["全网", "对比"])
    if any(x in text for x in ["伪闭环", "真实", "dry-run", "模拟"]):
        required_terms.append("不能声称")
        forbidden_terms.extend(["已真实完成", "生产已部署"])
    if any(x in text for x in ["不要问", "不要一直问", "闭环"]):
        required_terms.append("自主")
    if not required_terms:
        required_terms.append(correction.get("expected_behavior", ""))
    return {
        "id": f"rule-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "type": "compiled_correction_rule",
        "project": correction.get("project", "global"),
        "source_correction_id": correction.get("id"),
        "scope": correction.get("scope", "important_project"),
        "required_terms": sorted(set(x for x in required_terms if x)),
        "forbidden_terms": sorted(set(forbidden_terms)),
        "severity": correction.get("severity", "high"),
        "rule_text": correction.get("expected_behavior") or correction.get("correction"),
    }


def _check(text: str, rules: list[dict]) -> dict:
    lower = text.lower()
    checks = []
    for rule in rules:
        required = rule.get("required_terms", [])
        forbidden = rule.get("forbidden_terms", [])
        required_hits = [t for t in required if str(t).lower() in lower]
        forbidden_hits = [t for t in forbidden if str(t).lower() in lower]
        missing = [t for t in required if t not in required_hits]
        passed = not missing and not forbidden_hits
        checks.append({
            "rule_id": rule.get("id"),
            "rule_text": rule.get("rule_text"),
            "passed": passed,
            "missing_required": missing,
            "forbidden_hits": forbidden_hits,
            "severity": rule.get("severity"),
        })
    return {
        "passed": all(c["passed"] for c in checks) if checks else True,
        "rule_count": len(rules),
        "failed": [c for c in checks if not c["passed"]],
        "checks": checks,
    }


def build_server() -> FastMCP:
    mcp = FastMCP("compiled-correction-mcp")

    @mcp.tool()
    def compiled_correction_brief() -> str:
        """Describe compiled correction rules."""
        return _json({
            "name": "compiled-correction-mcp",
            "version": "v6.9",
            "purpose": "把用户纠正从普通记忆升级为 completion 前的确定性检查规则",
            "storage": {"corrections": str(CORRECTION_FILE), "rules": str(RULE_FILE)},
        })

    @mcp.tool()
    def record_user_correction(project: str, correction: str, expected_behavior: str,
                               scope: str = "important_project", severity: str = "high") -> str:
        """Record a user correction."""
        record = {
            "id": f"correction-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "ts": _now(),
            "type": "user_correction",
            "project": project,
            "correction": correction,
            "expected_behavior": expected_behavior,
            "scope": scope,
            "severity": severity,
        }
        _append(CORRECTION_FILE, record)
        return _json({"status": "recorded", "correction": record})

    @mcp.tool()
    def compile_correction_rules(project: str = "") -> str:
        """Compile recorded corrections into runtime check rules."""
        corrections = _read_jsonl(CORRECTION_FILE)
        if project:
            corrections = [c for c in corrections if c.get("project") in {project, "global", ""}]
        rules = []
        for correction in corrections:
            rule = _rule_from_correction(correction)
            _append(RULE_FILE, rule)
            rules.append(rule)
        return _json({"status": "compiled", "project": project or "all", "count": len(rules), "rules": rules})

    @mcp.tool()
    def check_against_corrections(candidate_text: str, project: str = "",
                                  scope: str = "important_project") -> str:
        """Check text against compiled correction rules."""
        rules = _read_jsonl(RULE_FILE)
        if project:
            rules = [r for r in rules if r.get("project") in {project, "global", ""}]
        if scope:
            rules = [r for r in rules if r.get("scope") in {scope, "global", ""}]
        return _json({"project": project or "all", "scope": scope, **_check(candidate_text, rules)})

    @mcp.tool()
    def correction_report(project: str = "", output_path: str = "") -> str:
        """Write correction rule report."""
        corrections = _read_jsonl(CORRECTION_FILE)
        rules = _read_jsonl(RULE_FILE)
        if project:
            corrections = [c for c in corrections if c.get("project") in {project, "global", ""}]
            rules = [r for r in rules if r.get("project") in {project, "global", ""}]
        if not output_path:
            output_path = str(REPORT_DIR / f"{_safe_project(project or 'all')}_correction_report.md")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Compiled Correction Report",
            "",
            f"- Project: {project or 'all'}",
            f"- Generated: {_now()}",
            f"- Corrections: {len(corrections)}",
            f"- Rules: {len(rules)}",
            "",
            "## Rules",
            "",
        ]
        for rule in rules[-20:]:
            lines.append(f"- {rule.get('id')}: required={rule.get('required_terms')} forbidden={rule.get('forbidden_terms')}")
        path.write_text("\n".join(lines), encoding="utf-8")
        return _json({"status": "written", "path": str(path), "corrections": len(corrections), "rules": len(rules)})

    return mcp


def main() -> None:
    build_server().run()
