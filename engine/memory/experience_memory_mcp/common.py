# -*- coding: utf-8 -*-
"""Experience Memory MCP server.

Records structured execution experience:
task -> decision -> action -> result -> failure/pass -> lesson -> next retrieval.

v5.5 keeps JSONL as the source of truth and adds a rebuildable SQLite FTS5
index for faster project/type filtered retrieval. This is external memory, not
neural-network weight training.
"""
import json
import os
import hashlib
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads
from _shared.state import safe_project

# --- agentos-hub 适配：记忆目录环境变量驱动（原实现硬编码 ROOT/09_投研）。
# 未设置时回退自身目录，不依赖 cwd。
ROOT = Path(__file__).resolve().parents[2]
_ENV_DIR = os.environ.get("AGENTOS_HUB_MEMORY_DIR")
MEMORY_DIR = Path(_ENV_DIR) if _ENV_DIR else (ROOT / "data" / "memory")
MEMORY_FILE = Path(os.environ.get("AGENTOS_HUB_MEMORY_JSONL") or (MEMORY_DIR / "memory.jsonl"))
INDEX_FILE = Path(os.environ.get("AGENTOS_HUB_MEMORY_INDEX") or (MEMORY_DIR / "memory_index.sqlite"))
VECTOR_FILE = Path(os.environ.get("AGENTOS_HUB_MEMORY_VECTOR") or (MEMORY_DIR / "memory_vector.sqlite"))
VECTOR_DIM = 128


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | list | dict | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_", default="default")


def _read_all() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    rows = []
    for line in MEMORY_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"type": "corrupt_line", "raw": line})
    return rows


def _tokens(text: str) -> set[str]:
    text = text.lower()
    for ch in "\r\n\t,.;:，。；：、?？!！\\|()[]{}<>\"'`":
        text = text.replace(ch, " ")
    raw = [t.strip() for t in text.split() if t.strip()]
    grams = set(raw)
    compact = "".join(raw)
    if compact:
        grams.update(compact[i:i + 2] for i in range(max(0, len(compact) - 1)))
        grams.update(compact[i:i + 3] for i in range(max(0, len(compact) - 2)))
    return {t for t in grams if t}


def _vector_tokens(text: str) -> list[str]:
    tokens = sorted(_tokens(text))
    expanded = []
    for token in tokens:
        expanded.append(token)
        if len(token) > 3:
            expanded.extend(token[i:i + 3] for i in range(len(token) - 2))
    return expanded


def _embedding(text: str, dim: int = VECTOR_DIM) -> list[float]:
    """Deterministic hashing embedding; replaceable with model embeddings later."""
    vec = [0.0] * dim
    for token in _vector_tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + min(len(token), 12) / 12.0
        vec[idx] += sign * weight
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return vec
    return [round(x / norm, 6) for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    return round(sum(a[i] * b[i] for i in range(size)), 6)


def _record_text(record: dict) -> str:
    keys = [
        "task", "decision", "why", "action", "tool", "result", "symptom",
        "cause", "fix", "prevention", "lesson", "applies_to",
        "next_retrieval_query", "preference", "evidence", "tags",
    ]
    parts = []
    for key in keys:
        value = record.get(key)
        if value:
            parts.append(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))
    parts.append(json.dumps(record, ensure_ascii=False))
    return "\n".join(parts)


def _age_days(record: dict) -> float:
    try:
        ts = datetime.fromisoformat(str(record.get("ts", "")).replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400)
    except Exception:
        return 365.0


def _importance(record: dict) -> float:
    if record.get("rule_candidate"):
        return 1.0
    if record.get("type") in {"failure_case", "lesson", "outcome"}:
        return 0.8
    if record.get("type") == "decision_record":
        return 0.65
    return 0.45


def _semantic_score(record: dict, query: str, project: str = "", record_type: str = "") -> float:
    q = _tokens(query)
    r = _tokens(_record_text(record))
    lexical = len(q & r) / max(len(q), 1) if q else 0.0
    scope = 0.2 if project and record.get("project") == project else 0.0
    type_boost = 0.15 if record_type and record.get("type") == record_type else 0.0
    importance = _importance(record) * 0.2
    recency = max(0.0, 1.0 - min(_age_days(record), 180.0) / 180.0) * 0.15
    return round(lexical * 0.5 + scope + type_boost + importance + recency, 4)


def _connect_vector() -> sqlite3.Connection:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(VECTOR_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_vectors (
            id TEXT PRIMARY KEY,
            ts TEXT,
            project TEXT,
            type TEXT,
            dim INTEGER,
            embedding TEXT NOT NULL,
            payload TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_vectors_project ON memory_vectors(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_vectors_type ON memory_vectors(type)")
    return conn


def _index_vector_record(record: dict) -> None:
    if not record.get("id"):
        return
    conn = _connect_vector()
    try:
        embedding = _embedding(_record_text(record))
        conn.execute(
            """
            INSERT OR REPLACE INTO memory_vectors(id, ts, project, type, dim, embedding, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("id"),
                record.get("ts"),
                record.get("project", ""),
                record.get("type", ""),
                VECTOR_DIM,
                json.dumps(embedding),
                json.dumps(record, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _rebuild_vector_index() -> dict:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if VECTOR_FILE.exists():
        VECTOR_FILE.unlink()
    conn = _connect_vector()
    rows = _read_all()
    indexed = 0
    try:
        for record in rows:
            if not record.get("id"):
                continue
            embedding = _embedding(_record_text(record))
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_vectors(id, ts, project, type, dim, embedding, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("id"),
                    record.get("ts"),
                    record.get("project", ""),
                    record.get("type", ""),
                    VECTOR_DIM,
                    json.dumps(embedding),
                    json.dumps(record, ensure_ascii=False),
                ),
            )
            indexed += 1
        conn.commit()
    finally:
        conn.close()
    return {
        "indexed": indexed,
        "source_records": len(rows),
        "vector_path": str(VECTOR_FILE),
        "embedding": "deterministic_hashing",
        "dim": VECTOR_DIM,
    }


def _vector_search(query: str, project: str = "", record_type: str = "",
                   limit: int = 10, min_score: float = 0.05) -> dict:
    if not VECTOR_FILE.exists():
        _rebuild_vector_index()
    query_vec = _embedding(query)
    conn = _connect_vector()
    try:
        where = []
        params: list[Any] = []
        if project:
            where.append("project = ?")
            params.append(project)
        if record_type:
            where.append("type = ?")
            params.append(record_type)
        sql = "SELECT payload, embedding FROM memory_vectors"
        if where:
            sql += " WHERE " + " AND ".join(where)
        hits = []
        for row in conn.execute(sql, params):
            item = json.loads(row["payload"])
            score = _cosine(query_vec, json.loads(row["embedding"]))
            hybrid = round(score * 0.7 + _semantic_score(item, query, project, record_type) * 0.3, 6)
            if hybrid >= min_score:
                item["_vector_score"] = score
                item["_hybrid_score"] = hybrid
                item["_embedding"] = "deterministic_hashing"
                hits.append(item)
        hits.sort(key=lambda x: x["_hybrid_score"], reverse=True)
        return {
            "query": query,
            "project": project,
            "record_type": record_type,
            "embedding": "deterministic_hashing",
            "dim": VECTOR_DIM,
            "count": len(hits),
            "hits": hits[:max(1, limit)],
        }
    finally:
        conn.close()


def _connect() -> sqlite3.Connection:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INDEX_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            ts TEXT,
            project TEXT,
            type TEXT,
            importance REAL,
            payload TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
        USING fts5(id UNINDEXED, project, type, content, tokenize='unicode61')
    """)
    return conn


def _index_record(record: dict) -> None:
    conn = _connect()
    try:
        payload = json.dumps(record, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO memories(id, ts, project, type, importance, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (record.get("id"), record.get("ts"), record.get("project", ""), record.get("type", ""), _importance(record), payload),
        )
        conn.execute("DELETE FROM memories_fts WHERE id = ?", (record.get("id"),))
        conn.execute(
            "INSERT INTO memories_fts(id, project, type, content) VALUES (?, ?, ?, ?)",
            (record.get("id"), record.get("project", ""), record.get("type", ""), _record_text(record)),
        )
        conn.commit()
    finally:
        conn.close()


def _rebuild_index() -> dict:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if INDEX_FILE.exists():
        INDEX_FILE.unlink()
    conn = _connect()
    rows = _read_all()
    indexed = 0
    try:
        for record in rows:
            if not record.get("id"):
                continue
            payload = json.dumps(record, ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO memories(id, ts, project, type, importance, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (record.get("id"), record.get("ts"), record.get("project", ""), record.get("type", ""), _importance(record), payload),
            )
            conn.execute(
                "INSERT INTO memories_fts(id, project, type, content) VALUES (?, ?, ?, ?)",
                (record.get("id"), record.get("project", ""), record.get("type", ""), _record_text(record)),
            )
            indexed += 1
        conn.commit()
    finally:
        conn.close()
    return {"indexed": indexed, "source_records": len(rows), "index_path": str(INDEX_FILE)}


def _append(record: dict) -> dict:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "id": f"mem-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        **record,
    }
    with MEMORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    _index_record(record)
    _index_vector_record(record)
    return record


def _contains(record: dict, terms: list[str]) -> bool:
    text = json.dumps(record, ensure_ascii=False).lower()
    return all(t.lower() in text for t in terms if t)


def _project_records(project: str) -> list[dict]:
    return [r for r in _read_all() if r.get("project") == project]


def _fts_query(query: str) -> str:
    terms = [t for t in query.replace('"', " ").replace("'", " ").split() if t.strip()]
    return " OR ".join(terms) if terms else query


def build_server() -> FastMCP:
    mcp = FastMCP("experience-memory-mcp")

    @mcp.tool()
    def memory_brief() -> str:
        """Describe the memory schema and manual-gates mapping."""
        return _json({
            "name": "experience-memory-mcp",
            "version": "v5.12",
            "purpose": "record task-decision-action-result-lesson memory and retrieve it across sessions",
            "not_for": "does not train model weights or automatically rewrite manual standards",
            "manual_nodes": [15, 16, 17, 19, 24],
            "storage": str(MEMORY_FILE),
            "sqlite_fts_index": str(INDEX_FILE),
            "sqlite_vector_index": str(VECTOR_FILE),
            "embedding": {
                "provider": "deterministic_hashing",
                "dim": VECTOR_DIM,
                "upgrade_path": "replace _embedding with Chroma/LanceDB/FAISS-backed model embeddings",
            },
            "record_types": [
                "task_snapshot",
                "decision_record",
                "action_result",
                "outcome",
                "failure_case",
                "fix_pattern",
                "user_preference",
                "lesson",
            ],
        })

    @mcp.tool()
    def record_task_snapshot(project: str, task: str, context_json: str = "{}", tags: str = "") -> str:
        """Record a task and its starting context."""
        rec = _append({
            "type": "task_snapshot",
            "project": project,
            "task": task,
            "context": _loads(context_json, {}),
            "tags": [x.strip() for x in tags.split(",") if x.strip()],
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def record_decision(project: str, decision: str, why: str, alternatives_json: str = "[]",
                        confidence: str = "medium", tags: str = "") -> str:
        """Record a decision, alternatives, and rationale."""
        rec = _append({
            "type": "decision_record",
            "project": project,
            "decision": decision,
            "why": why,
            "alternatives": _loads(alternatives_json, []),
            "confidence": confidence,
            "tags": [x.strip() for x in tags.split(",") if x.strip()],
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def record_action_result(project: str, action: str, tool: str = "", result: str = "",
                             files_json: str = "[]", status: str = "unknown", tags: str = "") -> str:
        """Record an executed action/tool call and its result."""
        rec = _append({
            "type": "action_result",
            "project": project,
            "action": action,
            "tool": tool,
            "result": result,
            "files": _loads(files_json, []),
            "status": status,
            "tags": [x.strip() for x in tags.split(",") if x.strip()],
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def record_outcome(project: str, task: str, status: str, tests_json: str = "[]",
                       issues_json: str = "[]", gate_status: str = "") -> str:
        """Record final task outcome: passed/failed/reopened/deferred."""
        rec = _append({
            "type": "outcome",
            "project": project,
            "task": task,
            "status": status,
            "tests": _loads(tests_json, []),
            "issues": _loads(issues_json, []),
            "gate_status": gate_status,
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def record_failure_case(project: str, symptom: str, cause: str = "", fix: str = "",
                            prevention: str = "", tags: str = "") -> str:
        """Record a failure-fix-prevention sample."""
        rec = _append({
            "type": "failure_case",
            "project": project,
            "symptom": symptom,
            "cause": cause,
            "fix": fix,
            "prevention": prevention,
            "tags": [x.strip() for x in tags.split(",") if x.strip()],
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def record_lesson(project: str, lesson: str, applies_to: str = "", next_retrieval_query: str = "",
                      rule_candidate: bool = False) -> str:
        """Record a reusable lesson. rule_candidate=true means consider feedback_loop later."""
        rec = _append({
            "type": "lesson",
            "project": project,
            "lesson": lesson,
            "applies_to": applies_to,
            "next_retrieval_query": next_retrieval_query,
            "rule_candidate": rule_candidate,
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def record_user_preference(project: str, preference: str, evidence: str = "",
                               scope: str = "project") -> str:
        """Record a user preference with evidence and scope."""
        rec = _append({
            "type": "user_preference",
            "project": project,
            "preference": preference,
            "evidence": evidence,
            "scope": scope,
        })
        return _json({"status": "recorded", "record": rec})

    @mcp.tool()
    def search_memory(query: str, project: str = "", record_type: str = "", limit: int = 10) -> str:
        """Search local experience memory by simple keyword matching."""
        terms = [t for t in query.replace("，", " ").replace(",", " ").split() if t]
        rows = _read_all()
        if project:
            rows = [r for r in rows if r.get("project") == project]
        if record_type:
            rows = [r for r in rows if r.get("type") == record_type]
        hits = [r for r in rows if _contains(r, terms)]
        return _json({"query": query, "count": len(hits), "hits": hits[:max(1, limit)]})

    @mcp.tool()
    def semantic_search_memory(query: str, project: str = "", record_type: str = "",
                               limit: int = 10, min_score: float = 0.15) -> str:
        """Search memory with local semantic-style scoring: overlap + scope + importance + recency."""
        rows = _read_all()
        scored = []
        for r in rows:
            if project and r.get("project") != project:
                continue
            if record_type and r.get("type") != record_type:
                continue
            score = _semantic_score(r, query, project, record_type)
            if score >= min_score:
                item = dict(r)
                item["_semantic_score"] = score
                item["_importance"] = _importance(r)
                item["_age_days"] = round(_age_days(r), 2)
                scored.append(item)
        scored.sort(key=lambda x: x["_semantic_score"], reverse=True)
        return _json({
            "query": query,
            "project": project,
            "record_type": record_type,
            "scoring": "0.5 lexical + 0.2 project_scope + 0.15 type + 0.2 importance + 0.15 recency",
            "count": len(scored),
            "hits": scored[:max(1, limit)],
            })

    @mcp.tool()
    def vector_search_memory(query: str, project: str = "", record_type: str = "",
                             limit: int = 10, min_score: float = 0.05) -> str:
        """Search memory with local vector embeddings and hybrid score."""
        return _json(_vector_search(query, project, record_type, limit, min_score))

    @mcp.tool()
    def fts_search_memory(query: str, project: str = "", record_type: str = "",
                          limit: int = 10) -> str:
        """Search memory through SQLite FTS5 index with project/type filters."""
        if not INDEX_FILE.exists():
            _rebuild_index()
        conn = _connect()
        try:
            where = ["memories_fts MATCH ?"]
            params: list[Any] = [_fts_query(query)]
            if project:
                where.append("m.project = ?")
                params.append(project)
            if record_type:
                where.append("m.type = ?")
                params.append(record_type)
            params.append(max(1, limit))
            sql = f"""
                SELECT m.payload, bm25(memories_fts) AS rank
                FROM memories_fts
                JOIN memories m ON m.id = memories_fts.id
                WHERE {' AND '.join(where)}
                ORDER BY rank
                LIMIT ?
            """
            hits = []
            for row in conn.execute(sql, params):
                item = json.loads(row["payload"])
                item["_fts_rank"] = row["rank"]
                item["_semantic_score"] = _semantic_score(item, query, project, record_type)
                hits.append(item)
            return _json({"query": query, "project": project, "record_type": record_type, "count": len(hits), "hits": hits})
        except sqlite3.OperationalError as exc:
            return _json({"error": str(exc), "hint": "try rebuild_memory_index, or simplify query terms"})
        finally:
            conn.close()

    @mcp.tool()
    def rebuild_memory_index() -> str:
        """Rebuild SQLite FTS index from JSONL source of truth."""
        return _json({"status": "rebuilt", **_rebuild_index()})

    @mcp.tool()
    def rebuild_vector_index() -> str:
        """Rebuild SQLite vector index from JSONL source of truth."""
        return _json({"status": "rebuilt", **_rebuild_vector_index()})

    @mcp.tool()
    def memory_vector_stats() -> str:
        """Return vector index stats."""
        if not VECTOR_FILE.exists():
            return _json({
                "index_exists": False,
                "vector_path": str(VECTOR_FILE),
                "source_records": len(_read_all()),
                "embedding": "deterministic_hashing",
                "dim": VECTOR_DIM,
            })
        conn = _connect_vector()
        try:
            count = conn.execute("SELECT COUNT(*) AS c FROM memory_vectors").fetchone()["c"]
            by_project = [dict(r) for r in conn.execute("SELECT project, COUNT(*) AS count FROM memory_vectors GROUP BY project ORDER BY count DESC")]
            by_type = [dict(r) for r in conn.execute("SELECT type, COUNT(*) AS count FROM memory_vectors GROUP BY type ORDER BY count DESC")]
            return _json({
                "index_exists": True,
                "vector_path": str(VECTOR_FILE),
                "record_count": count,
                "embedding": "deterministic_hashing",
                "dim": VECTOR_DIM,
                "by_project": by_project,
                "by_type": by_type,
            })
        finally:
            conn.close()

    @mcp.tool()
    def memory_index_stats() -> str:
        """Return SQLite FTS index stats."""
        if not INDEX_FILE.exists():
            return _json({"index_exists": False, "index_path": str(INDEX_FILE), "source_records": len(_read_all())})
        conn = _connect()
        try:
            count = conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
            by_project = [dict(r) for r in conn.execute("SELECT project, COUNT(*) AS count FROM memories GROUP BY project ORDER BY count DESC")]
            by_type = [dict(r) for r in conn.execute("SELECT type, COUNT(*) AS count FROM memories GROUP BY type ORDER BY count DESC")]
            return _json({
                "index_exists": True,
                "index_path": str(INDEX_FILE),
                "record_count": count,
                "by_project": by_project,
                "by_type": by_type,
            })
        finally:
            conn.close()

    @mcp.tool()
    def score_memory(query: str, memory_id: str) -> str:
        """Score one memory record against a query."""
        rows = _read_all()
        for r in rows:
            if r.get("id") == memory_id:
                return _json({
                    "memory_id": memory_id,
                    "query": query,
                    "score": _semantic_score(r, query, r.get("project", ""), r.get("type", "")),
                    "record": r,
                })
        return _json({"error": f"memory_id not found: {memory_id}"})

    @mcp.tool()
    def memory_stats(project: str = "") -> str:
        """Return memory quality stats for process review."""
        rows = _read_all()
        if project:
            rows = [r for r in rows if r.get("project") == project]
        by_type: dict[str, int] = {}
        rule_candidates = 0
        for r in rows:
            by_type[r.get("type", "unknown")] = by_type.get(r.get("type", "unknown"), 0) + 1
            if r.get("rule_candidate"):
                rule_candidates += 1
        return _json({
            "project": project or "all",
            "record_count": len(rows),
            "by_type": by_type,
            "rule_candidates": rule_candidates,
            "storage": str(MEMORY_FILE),
            "sqlite_fts_index": str(INDEX_FILE),
            "sqlite_vector_index": str(VECTOR_FILE),
        })

    @mcp.tool()
    def distill_memory_lessons(project: str = "", limit: int = 10,
                               output_path: str = "") -> str:
        """Distill reusable lessons from high-value memory records."""
        rows = _read_all()
        if project:
            rows = [r for r in rows if r.get("project") == project]
        candidates = []
        for record in rows:
            if record.get("type") in {"lesson", "failure_case", "outcome", "decision_record"} or record.get("rule_candidate"):
                text = record.get("lesson") or record.get("fix") or record.get("why") or record.get("result") or record.get("task") or ""
                if text:
                    candidates.append({
                        "memory_id": record.get("id"),
                        "project": record.get("project", ""),
                        "type": record.get("type", ""),
                        "importance": _importance(record),
                        "lesson": text,
                        "rule_candidate": bool(record.get("rule_candidate")),
                        "next_retrieval_query": record.get("next_retrieval_query", ""),
                    })
        candidates.sort(key=lambda x: (x["rule_candidate"], x["importance"]), reverse=True)
        distilled = candidates[:max(1, limit)]
        if not output_path:
            safe = _safe_project(project or "all")
            output_path = str(MEMORY_DIR / f"{safe}_distilled_lessons.json")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "project": project or "all",
            "generated": _now(),
            "source_records": len(rows),
            "distilled_count": len(distilled),
            "lessons": distilled,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return _json({"status": "written", "path": str(out), "distilled_count": len(distilled), "lessons": distilled})

    @mcp.tool()
    def summarize_project(project: str) -> str:
        """Summarize memory records for a project."""
        rows = _project_records(project)
        by_type: dict[str, int] = {}
        for r in rows:
            by_type[r.get("type", "unknown")] = by_type.get(r.get("type", "unknown"), 0) + 1
        lessons = [r for r in rows if r.get("type") == "lesson"]
        failures = [r for r in rows if r.get("type") == "failure_case"]
        outcomes = [r for r in rows if r.get("type") == "outcome"]
        return _json({
            "project": project,
            "record_count": len(rows),
            "by_type": by_type,
            "latest_outcome": outcomes[-1] if outcomes else None,
            "lesson_candidates": lessons[-5:],
            "failure_patterns": failures[-5:],
        })

    @mcp.tool()
    def export_training_samples(project: str = "", output_path: str = "") -> str:
        """Export memories as JSONL training/retrieval samples."""
        rows = _read_all()
        if project:
            rows = [r for r in rows if r.get("project") == project]
        if not output_path:
            safe = _safe_project(project or "all")
            output_path = str(MEMORY_DIR / f"{safe}_samples.jsonl")
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for r in rows:
                sample = {
                    "input": {
                        "project": r.get("project"),
                        "type": r.get("type"),
                        "context": r,
                    },
                    "label": r.get("status") or r.get("gate_status") or r.get("rule_candidate"),
                    "lesson": r.get("lesson") or r.get("fix") or r.get("why") or r.get("result"),
                }
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        return _json({"status": "written", "path": str(p), "samples": len(rows)})

    return mcp


def main() -> None:
    build_server().run()
