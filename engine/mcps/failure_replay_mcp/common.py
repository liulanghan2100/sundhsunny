# -*- coding: utf-8 -*-
"""Failure Replay MCP server.

v6.4 turns past mistakes into pre-execution constraints. It stores failure
cases, distills lessons, searches similar failures, builds avoidance plans, and
verifies that execution cards explicitly address old failure modes.
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
REPLAY_DIR = ROOT / "09_投研" / "failure_replay"
FAILURE_FILE = REPLAY_DIR / "failures.jsonl"
LESSON_FILE = REPLAY_DIR / "distilled_lessons.jsonl"
REPORT_DIR = REPLAY_DIR / "reports"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


def _tokens(text: str) -> set[str]:
    text = text.lower()
    for ch in "\r\n\t,.;:，。；：、?？!！\\|()[]{}<>\"'`":
        text = text.replace(ch, " ")
    raw = [x.strip() for x in text.split() if x.strip()]
    tokens = set(raw)
    compact = "".join(raw)
    if compact:
        tokens.update(compact[i:i + 2] for i in range(max(0, len(compact) - 1)))
        tokens.update(compact[i:i + 3] for i in range(max(0, len(compact) - 2)))
    return {x for x in tokens if x}


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


def _append_jsonl(path: Path, record: dict) -> dict:
    shared_append_jsonl(path, record)
    return record


def _record_text(record: dict) -> str:
    parts = []
    for key in [
        "task", "symptom", "cause", "impact", "wrong_assumption", "missed_workflow",
        "fix", "lesson", "prevention", "avoidance_rule", "tags", "applies_to",
    ]:
        value = record.get(key)
        if value:
            parts.append(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))
    parts.append(json.dumps(record, ensure_ascii=False))
    return "\n".join(parts)


def _score(record: dict, query: str, project: str = "") -> float:
    q = _tokens(query)
    r = _tokens(_record_text(record))
    lexical = len(q & r) / max(len(q), 1) if q else 0.0
    project_boost = 0.15 if project and record.get("project") == project else 0.0
    severity_boost = {"critical": 0.25, "high": 0.18, "normal": 0.1, "low": 0.05}.get(str(record.get("severity", "normal")).lower(), 0.1)
    return round(min(1.0, lexical * 0.6 + project_boost + severity_boost), 4)


def _failure_id() -> str:
    return f"failure-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def _lesson_id() -> str:
    return f"lesson-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def _read_failures() -> list[dict]:
    return _read_jsonl(FAILURE_FILE)


def _read_lessons() -> list[dict]:
    return _read_jsonl(LESSON_FILE)


def _distill_from_failure(failure: dict) -> dict:
    lesson = failure.get("lesson") or failure.get("prevention") or failure.get("fix") or failure.get("symptom")
    prevention = failure.get("prevention") or "开工前在执行卡中写明如何避免该失败，并在验收时检查。"
    return {
        "id": _lesson_id(),
        "ts": _now(),
        "type": "distilled_lesson",
        "project": failure.get("project", ""),
        "source_failure_id": failure.get("id"),
        "lesson": lesson,
        "avoidance_rule": prevention,
        "applies_to": failure.get("applies_to") or failure.get("tags", []),
        "severity": failure.get("severity", "normal"),
    }


def _search_failures(query: str, project: str = "", limit: int = 5, min_score: float = 0.12) -> list[dict]:
    hits = []
    for record in _read_failures():
        if project and record.get("project") not in {project, "", "global"}:
            continue
        score = _score(record, query, project)
        if score >= min_score:
            item = dict(record)
            item["_score"] = score
            hits.append(item)
    hits.sort(key=lambda x: x["_score"], reverse=True)
    return hits[:max(1, limit)]


def _build_plan(project: str, task: str, hits: list[dict]) -> dict:
    rules = []
    for hit in hits:
        rule = hit.get("prevention") or hit.get("lesson") or hit.get("fix") or hit.get("symptom")
        rules.append({
            "failure_id": hit.get("id"),
            "symptom": hit.get("symptom"),
            "score": hit.get("_score"),
            "avoidance_rule": rule,
            "verification": hit.get("verification") or "验收时确认执行卡和结果说明已覆盖该失败模式。",
        })
    return {
        "project": project,
        "task": task,
        "matched_failures": len(hits),
        "avoidance_rules": rules,
        "execution_card_additions": [
            "历史失败命中",
            "本次如何避免",
            "最小验收方式",
            "不能声称完成的边界",
        ] if hits else [],
        "required_before_class_c": bool(hits),
    }


def _card_text(card: dict | str) -> str:
    if isinstance(card, str):
        return card.lower()
    return json.dumps(card, ensure_ascii=False).lower()


def _coverage_check(card_text: str, rule: str, symptom: str = "") -> bool:
    required_markers = [
        "historical failure",
        "matched historical failures",
        "avoidance",
        "avoid",
        "failure",
        "失败",
        "历史失败",
        "避免",
        "本次如何避免",
    ]
    has_marker = any(marker in card_text for marker in required_markers)
    rule_tokens = [t for t in _tokens(rule) if len(t) >= 4]
    symptom_tokens = [t for t in _tokens(symptom) if len(t) >= 4]
    rule_overlap = sum(1 for token in rule_tokens[:16] if token in card_text)
    symptom_overlap = sum(1 for token in symptom_tokens[:12] if token in card_text)
    return bool(has_marker and (rule_overlap >= 2 or symptom_overlap >= 2))


def build_server() -> FastMCP:
    mcp = FastMCP("failure-replay-mcp")

    @mcp.tool()
    def failure_replay_brief() -> str:
        """Describe failure replay and lesson distillation."""
        return _json({
            "name": "failure-replay-mcp",
            "version": "v6.4",
            "purpose": "把过去失败转成下次执行前的强制避免计划和验收检查",
            "storage": {
                "failures": str(FAILURE_FILE),
                "lessons": str(LESSON_FILE),
                "reports": str(REPORT_DIR),
            },
            "tools": [
                "record_failure_case",
                "distill_lesson",
                "search_similar_failures",
                "build_avoidance_plan",
                "verify_failure_avoidance",
                "failure_replay_report",
            ],
        })

    @mcp.tool()
    def record_failure_case(project: str, task: str, symptom: str, cause: str = "",
                            impact: str = "", wrong_assumption: str = "",
                            missed_workflow: str = "", fix: str = "",
                            prevention: str = "", severity: str = "normal",
                            tags: str = "", applies_to: str = "") -> str:
        """Record a failure sample that future tasks must search before execution."""
        record = {
            "id": _failure_id(),
            "ts": _now(),
            "type": "failure_case",
            "project": project,
            "task": task,
            "symptom": symptom,
            "cause": cause,
            "impact": impact,
            "wrong_assumption": wrong_assumption,
            "missed_workflow": missed_workflow,
            "fix": fix,
            "prevention": prevention,
            "severity": severity,
            "tags": [x.strip() for x in tags.split(",") if x.strip()],
            "applies_to": applies_to,
        }
        _append_jsonl(FAILURE_FILE, record)
        return _json({"status": "recorded", "record": record})

    @mcp.tool()
    def distill_lesson(failure_id: str = "", failure_json: str = "{}") -> str:
        """Distill one failure into a reusable lesson."""
        failure = _loads(failure_json, {})
        if failure_id:
            for item in _read_failures():
                if item.get("id") == failure_id:
                    failure = item
                    break
        if not failure:
            return _json({"error": "failure not found"})
        lesson = _distill_from_failure(failure)
        _append_jsonl(LESSON_FILE, lesson)
        return _json({"status": "distilled", "lesson": lesson})

    @mcp.tool()
    def search_similar_failures(task: str, project: str = "", limit: int = 5,
                                min_score: float = 0.12) -> str:
        """Search similar historical failures before starting work."""
        hits = _search_failures(task, project, limit, min_score)
        return _json({"task": task, "project": project, "count": len(hits), "hits": hits})

    @mcp.tool()
    def build_avoidance_plan(project: str, task: str, limit: int = 5,
                             min_score: float = 0.12) -> str:
        """Build an avoidance plan for a new task from matched failures."""
        hits = _search_failures(task, project, limit, min_score)
        return _json(_build_plan(project, task, hits))

    @mcp.tool()
    def verify_failure_avoidance(task: str, execution_card_json: str,
                                 project: str = "", limit: int = 5,
                                 min_score: float = 0.12) -> str:
        """Verify whether an execution card covers matched historical failures."""
        hits = _search_failures(task, project, limit, min_score)
        card = _loads(execution_card_json, execution_card_json)
        text = _card_text(card)
        checks = []
        for hit in hits:
            rule = hit.get("prevention") or hit.get("lesson") or hit.get("fix") or ""
            covered = _coverage_check(text, rule, hit.get("symptom", ""))
            checks.append({
                "failure_id": hit.get("id"),
                "symptom": hit.get("symptom"),
                "score": hit.get("_score"),
                "covered": covered,
                "required_rule": rule,
            })
        passed = all(item["covered"] for item in checks) if checks else True
        return _json({
            "task": task,
            "project": project,
            "matched_failures": len(hits),
            "passed": passed,
            "checks": checks,
            "required_action": "补充执行卡中的历史失败避免计划" if not passed else "none",
        })

    @mcp.tool()
    def failure_replay_report(project: str = "", output_path: str = "") -> str:
        """Write a report summarizing failure cases and distilled lessons."""
        failures = _read_failures()
        lessons = _read_lessons()
        if project:
            failures = [x for x in failures if x.get("project") in {project, "", "global"}]
            lessons = [x for x in lessons if x.get("project") in {project, "", "global"}]
        by_severity: dict[str, int] = {}
        for item in failures:
            sev = item.get("severity", "normal")
            by_severity[sev] = by_severity.get(sev, 0) + 1
        if not output_path:
            output_path = str(REPORT_DIR / f"{_safe_project(project or 'all')}_failure_replay_report.md")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Failure Replay Report",
            "",
            f"- Project: {project or 'all'}",
            f"- Generated: {_now()}",
            f"- Failure count: {len(failures)}",
            f"- Distilled lessons: {len(lessons)}",
            f"- By severity: {json.dumps(by_severity, ensure_ascii=False)}",
            "",
            "## Recent Failures",
            "",
        ]
        for item in failures[-10:]:
            lines.append(f"- {item.get('id')}: {item.get('symptom')} -> {item.get('prevention') or item.get('fix')}")
        lines.extend(["", "## Recent Lessons", ""])
        for item in lessons[-10:]:
            lines.append(f"- {item.get('id')}: {item.get('lesson')}")
        path.write_text("\n".join(lines), encoding="utf-8")
        return _json({
            "status": "written",
            "path": str(path),
            "failure_count": len(failures),
            "lesson_count": len(lessons),
            "by_severity": by_severity,
        })

    return mcp


def main() -> None:
    build_server().run()
