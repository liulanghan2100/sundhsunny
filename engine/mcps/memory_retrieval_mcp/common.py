# -*- coding: utf-8 -*-
"""Memory Retrieval MCP server.

v6.30 creates a pre-task retrieval packet from the existing memory stack. It
does not train model weights or call external embedding APIs; it makes local
memory easier to use before important execution.
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

from experience_memory_mcp.common import _read_all as _read_experience
from experience_memory_mcp.common import _semantic_score, _vector_search
from memory_consolidation_mcp.common import _read_jsonl as _read_jsonl_shared
from memory_consolidation_mcp.common import _tokens

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
RESEARCH = DATA_ROOT / "09_投研"
RETRIEVAL_DIR = RESEARCH / "memory_retrieval"
PACKET_FILE = RETRIEVAL_DIR / "retrieval_packets.jsonl"
CONSOLIDATED_FILE = RESEARCH / "memory_consolidation" / "consolidated_memory.jsonl"


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _append(record: dict) -> dict:
    shared_append_jsonl(PACKET_FILE, record)
    return record


def _read_packets() -> list[dict]:
    if not PACKET_FILE.exists():
        return []
    rows = []
    for line in PACKET_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _record_brief(record: dict) -> dict:
    return {
        "id": record.get("id"),
        "ts": record.get("ts"),
        "project": record.get("project", ""),
        "type": record.get("type", ""),
        "summary": (
            record.get("lesson")
            or record.get("fix")
            or record.get("why")
            or record.get("result")
            or record.get("task")
            or record.get("statement")
            or json.dumps(record, ensure_ascii=False)[:220]
        ),
        "score": record.get("_score") or record.get("_semantic_score") or record.get("_hybrid_score") or record.get("_fts_rank"),
    }


def _keyword_search(query: str, project: str, limit: int) -> list[dict]:
    terms = _tokens(query)
    hits = []
    for record in _read_experience():
        if project and record.get("project") not in {project, "", "global"}:
            continue
        text = json.dumps(record, ensure_ascii=False)
        score = len(terms & _tokens(text)) / max(len(terms), 1) if terms else 0.0
        if score > 0:
            item = dict(record)
            item["_score"] = round(score, 4)
            hits.append(item)
    hits.sort(key=lambda item: item["_score"], reverse=True)
    return [_record_brief(item) for item in hits[:limit]]


def _semantic_search(query: str, project: str, limit: int) -> list[dict]:
    hits = []
    for record in _read_experience():
        if project and record.get("project") not in {project, "", "global"}:
            continue
        score = _semantic_score(record, query, project, "")
        if score >= 0.1:
            item = dict(record)
            item["_semantic_score"] = score
            hits.append(item)
    hits.sort(key=lambda item: item["_semantic_score"], reverse=True)
    return [_record_brief(item) for item in hits[:limit]]


def _vector_hits(query: str, project: str, limit: int) -> list[dict]:
    try:
        result = _vector_search(query, project, "", limit, 0.01)
        return [_record_brief(item) for item in result.get("hits", [])]
    except Exception as exc:
        return [{"error": str(exc), "summary": "vector search failed"}]


def _consolidated_search(query: str, project: str, layer: str, limit: int) -> list[dict]:
    terms = _tokens(query)
    hits = []
    for item in _read_jsonl_shared(CONSOLIDATED_FILE):
        if project and item.get("project") not in {project, "", "global"}:
            continue
        if layer and item.get("layer") != layer:
            continue
        score = len(terms & _tokens(item.get("statement", ""))) / max(len(terms), 1) if terms else 0.0
        score = round(score * 0.7 + float(item.get("confidence", 0.5)) * 0.3, 4)
        if score >= 0.1:
            enriched = dict(item)
            enriched["_score"] = score
            hits.append(enriched)
    hits.sort(key=lambda row: row["_score"], reverse=True)
    return [_record_brief(item) for item in hits[:limit]]


def _recommendations(packet: dict) -> list[str]:
    recs = []
    if packet["summary"]["total_hits"] == 0:
        recs.append("No reusable memory found; create outcome and lesson records after completion.")
    if packet["summary"]["consolidated_hits"] > 0:
        recs.append("Read consolidated memory before implementation and cite applicable procedural lessons in the execution card.")
    if packet["summary"]["vector_hits"] > 0:
        recs.append("Use vector hits to catch semantically similar failures even when keywords differ.")
    if packet["summary"]["semantic_hits"] > 0:
        recs.append("Prefer recent high-importance memories when tradeoffs conflict.")
    return recs


def _build_packet(project: str, task: str, query: str = "", layer: str = "",
                  limit: int = 5, context_json: str = "{}") -> dict:
    q = query or task
    keyword = _keyword_search(q, project, limit)
    semantic = _semantic_search(q, project, limit)
    vector = _vector_hits(q, project, limit)
    consolidated = _consolidated_search(q, project, layer, limit)
    packet = {
        "id": f"retrieval-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "task": task,
        "query": q,
        "layer": layer or "all",
        "context": _loads(context_json, {}),
        "type": "memory_retrieval_packet",
        "sources": {
            "keyword": keyword,
            "semantic": semantic,
            "vector": vector,
            "consolidated": consolidated,
        },
        "summary": {
            "keyword_hits": len(keyword),
            "semantic_hits": len(semantic),
            "vector_hits": len([x for x in vector if not x.get("error")]),
            "consolidated_hits": len(consolidated),
        },
        "storage": str(PACKET_FILE),
    }
    packet["summary"]["total_hits"] = sum(packet["summary"].values())
    packet["recommendations"] = _recommendations(packet)
    _append(packet)
    return packet


def build_server() -> FastMCP:
    mcp = FastMCP("memory-retrieval-mcp")

    @mcp.tool()
    def memory_retrieval_brief() -> str:
        """Describe memory retrieval packets."""
        return _json({
            "name": "memory-retrieval-mcp",
            "version": "v6.30",
            "purpose": "build pre-task retrieval packets from keyword, semantic, vector, and consolidated memory",
            "storage": str(PACKET_FILE),
            "external_embedding_api": False,
        })

    @mcp.tool()
    def build_memory_retrieval_packet(project: str, task: str, query: str = "",
                                      layer: str = "", limit: int = 5,
                                      context_json: str = "{}") -> str:
        """Build and store one pre-task memory retrieval packet."""
        return _json(_build_packet(project, task, query, layer, max(1, int(limit)), context_json))

    @mcp.tool()
    def memory_retrieval_report(project: str = "") -> str:
        """Return recent memory retrieval packet stats."""
        rows = _read_packets()
        if project:
            rows = [row for row in rows if row.get("project") == project]
        return _json({
            "project": project or "all",
            "packet_count": len(rows),
            "latest": rows[-1] if rows else None,
            "recent": rows[-10:],
            "storage": str(PACKET_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
