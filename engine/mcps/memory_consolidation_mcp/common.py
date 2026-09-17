# -*- coding: utf-8 -*-
"""Memory Consolidation MCP server.

v6.6 organizes raw memories into semantic, episodic, and procedural layers,
then consolidates lessons and flags possible conflicts.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.state import safe_project
from _shared.io import _append_jsonl as shared_append_jsonl

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
MEMORY_DIR = DATA_ROOT / "09_投研" / "experience_memory"
FAILURE_DIR = DATA_ROOT / "09_投研" / "failure_replay"
CONSOLIDATION_DIR = DATA_ROOT / "09_投研" / "memory_consolidation"
CONSOLIDATED_FILE = CONSOLIDATION_DIR / "consolidated_memory.jsonl"
CONFLICT_FILE = CONSOLIDATION_DIR / "memory_conflicts.jsonl"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="default")


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


def _append(path: Path, record: dict) -> dict:
    shared_append_jsonl(path, record)
    return record


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


def _memory_text(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False)


def _classify_layer(record: dict) -> str:
    typ = record.get("type", "")
    text = _memory_text(record).lower()
    if typ in {"failure_case", "outcome", "action_result", "task_snapshot"}:
        return "episodic"
    if typ in {"lesson", "distilled_lesson", "user_preference"}:
        return "semantic"
    if typ in {"fix_pattern", "decision_record"}:
        return "procedural"
    if any(x in text for x in ["必须", "should", "workflow", "流程", "验收", "avoid", "避免"]):
        return "procedural"
    if any(x in text for x in ["失败", "failed", "symptom", "cause"]):
        return "episodic"
    return "semantic"


def _source_records() -> list[dict]:
    rows = []
    for path in [
        MEMORY_DIR / "memory.jsonl",
        FAILURE_DIR / "failures.jsonl",
        FAILURE_DIR / "distilled_lessons.jsonl",
    ]:
        for record in _read_jsonl(path):
            item = dict(record)
            item["_source_file"] = str(path)
            rows.append(item)
    return rows


def _score(record: dict) -> float:
    base = 0.5
    if record.get("severity") in {"critical", "high"}:
        base += 0.25
    if record.get("rule_candidate"):
        base += 0.2
    if record.get("type") in {"failure_case", "distilled_lesson", "lesson"}:
        base += 0.15
    return round(min(base, 1.0), 3)


def _consolidated_id() -> str:
    return f"cmem-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def _extract_statement(record: dict) -> str:
    for key in ["lesson", "avoidance_rule", "prevention", "fix", "why", "preference", "result", "symptom", "task"]:
        if record.get(key):
            return str(record.get(key))
    return _memory_text(record)[:240]


def _consolidate(project: str = "", limit: int = 50) -> list[dict]:
    rows = _source_records()
    if project:
        rows = [r for r in rows if r.get("project") in {project, "", "global"}]
    rows.sort(key=_score, reverse=True)
    consolidated = []
    seen: set[str] = set()
    for record in rows[:max(1, limit)]:
        statement = _extract_statement(record)
        key = " ".join(sorted(list(_tokens(statement))[:12]))
        if key in seen:
            continue
        seen.add(key)
        item = {
            "id": _consolidated_id(),
            "ts": _now(),
            "type": "consolidated_memory",
            "project": project or record.get("project", ""),
            "layer": _classify_layer(record),
            "statement": statement,
            "confidence": _score(record),
            "source_id": record.get("id", ""),
            "source_type": record.get("type", ""),
            "source_file": record.get("_source_file", ""),
            "retrieval_hint": record.get("next_retrieval_query") or record.get("applies_to") or record.get("tags", []),
        }
        _append(CONSOLIDATED_FILE, item)
        consolidated.append(item)
    return consolidated


def _detect_conflicts(project: str = "") -> list[dict]:
    memories = _read_jsonl(CONSOLIDATED_FILE)
    if project:
        memories = [m for m in memories if m.get("project") in {project, "", "global"}]
    conflicts = []
    negatives = ["不要", "不能", "禁止", "avoid", "must not", "not "]
    positives = ["必须", "需要", "should", "must ", "required"]
    for i, left in enumerate(memories):
        lt = _tokens(left.get("statement", ""))
        if not lt:
            continue
        for right in memories[i + 1:]:
            rt = _tokens(right.get("statement", ""))
            overlap = len(lt & rt) / max(min(len(lt), len(rt)), 1)
            if overlap < 0.35:
                continue
            ltxt = left.get("statement", "").lower()
            rtxt = right.get("statement", "").lower()
            opposite = (
                any(n in ltxt for n in negatives) and any(p in rtxt for p in positives)
            ) or (
                any(p in ltxt for p in positives) and any(n in rtxt for n in negatives)
            )
            if opposite:
                conflict = {
                    "id": f"conflict-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
                    "ts": _now(),
                    "project": project or "all",
                    "left_id": left.get("id"),
                    "right_id": right.get("id"),
                    "overlap": round(overlap, 4),
                    "left": left.get("statement"),
                    "right": right.get("statement"),
                    "resolution": "manual_review_required",
                }
                _append(CONFLICT_FILE, conflict)
                conflicts.append(conflict)
    return conflicts


def build_server() -> FastMCP:
    mcp = FastMCP("memory-consolidation-mcp")

    @mcp.tool()
    def memory_consolidation_brief() -> str:
        """Describe memory consolidation."""
        return _json({
            "name": "memory-consolidation-mcp",
            "version": "v6.6",
            "purpose": "把原始记忆巩固为 semantic/episodic/procedural 三层，并标记冲突",
            "storage": str(CONSOLIDATION_DIR),
        })

    @mcp.tool()
    def classify_memory_layer(record_json: str) -> str:
        """Classify one memory record as semantic, episodic, or procedural."""
        record = _loads(record_json, {})
        return _json({"layer": _classify_layer(record), "confidence": _score(record), "record": record})

    @mcp.tool()
    def consolidate_memories(project: str = "", limit: int = 50) -> str:
        """Consolidate raw memories into layered memory records."""
        items = _consolidate(project, limit)
        return _json({"status": "consolidated", "project": project or "all", "count": len(items), "items": items})

    @mcp.tool()
    def search_consolidated_memory(query: str, project: str = "", layer: str = "",
                                   limit: int = 10, min_score: float = 0.1) -> str:
        """Search consolidated memories."""
        q = _tokens(query)
        hits = []
        for item in _read_jsonl(CONSOLIDATED_FILE):
            if project and item.get("project") not in {project, "", "global"}:
                continue
            if layer and item.get("layer") != layer:
                continue
            score = len(q & _tokens(item.get("statement", ""))) / max(len(q), 1) if q else 0.0
            score = round(score * 0.7 + float(item.get("confidence", 0.5)) * 0.3, 4)
            if score >= min_score:
                hit = dict(item)
                hit["_score"] = score
                hits.append(hit)
        hits.sort(key=lambda x: x["_score"], reverse=True)
        return _json({"query": query, "project": project, "layer": layer, "count": len(hits), "hits": hits[:max(1, limit)]})

    @mcp.tool()
    def detect_memory_conflicts(project: str = "") -> str:
        """Detect possible conflicting consolidated memories."""
        conflicts = _detect_conflicts(project)
        return _json({"project": project or "all", "conflict_count": len(conflicts), "conflicts": conflicts})

    @mcp.tool()
    def memory_health_report(project: str = "") -> str:
        """Return memory consolidation health metrics."""
        raw = _source_records()
        consolidated = _read_jsonl(CONSOLIDATED_FILE)
        conflicts = _read_jsonl(CONFLICT_FILE)
        if project:
            raw = [r for r in raw if r.get("project") in {project, "", "global"}]
            consolidated = [r for r in consolidated if r.get("project") in {project, "", "global"}]
            conflicts = [r for r in conflicts if r.get("project") in {project, "", "global"}]
        by_layer: dict[str, int] = {}
        for item in consolidated:
            layer = item.get("layer", "unknown")
            by_layer[layer] = by_layer.get(layer, 0) + 1
        return _json({
            "project": project or "all",
            "raw_records": len(raw),
            "consolidated_records": len(consolidated),
            "by_layer": by_layer,
            "conflicts": len(conflicts),
            "consolidation_ratio": round(len(consolidated) / max(len(raw), 1), 4),
            "storage": {
                "consolidated": str(CONSOLIDATED_FILE),
                "conflicts": str(CONFLICT_FILE),
            },
        })

    return mcp


def main() -> None:
    build_server().run()
