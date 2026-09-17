# -*- coding: utf-8 -*-
"""Audit Hash Chain MCP server.

v6.27 creates a local tamper-evident audit chain. It is not a cryptographic
signature or third-party attestation; it detects local chain inconsistencies by
hashing each record with the previous hash.
"""
import hashlib
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
RESEARCH = DATA_ROOT / "09_投研"
CHAIN_DIR = RESEARCH / "audit_hash_chain"
CHAIN_FILE = CHAIN_DIR / "audit_chain.jsonl"
REPORT_DIR = CHAIN_DIR / "reports"
GENESIS = "0" * 64


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _canonical(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prev_hash: str, payload: dict) -> str:
    text = prev_hash + "\n" + _canonical(payload)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_chain() -> list[dict]:
    if not CHAIN_FILE.exists():
        return []
    rows = []
    for line in CHAIN_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _latest_hash() -> str:
    rows = _read_chain()
    return rows[-1].get("hash", GENESIS) if rows else GENESIS


def _append(record: dict) -> None:
    shared_append_jsonl(CHAIN_FILE, record)


def _record_event(project: str, event_type: str, evidence: dict) -> dict:
    prev = _latest_hash()
    payload = {
        "id": f"audit-event-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "event_type": event_type,
        "evidence": evidence,
    }
    record = {
        **payload,
        "prev_hash": prev,
        "hash": _hash(prev, payload),
    }
    _append(record)
    return record


def _verify_chain(project: str = "") -> dict:
    rows = _read_chain()
    prev = GENESIS
    checks = []
    for idx, row in enumerate(rows):
        payload = {k: row[k] for k in ["id", "ts", "project", "event_type", "evidence"] if k in row}
        expected_prev = prev
        expected_hash = _hash(expected_prev, payload)
        passed = row.get("prev_hash") == expected_prev and row.get("hash") == expected_hash
        checks.append({
            "index": idx,
            "id": row.get("id"),
            "project": row.get("project"),
            "passed": passed,
            "expected_prev_hash": expected_prev,
            "actual_prev_hash": row.get("prev_hash"),
            "expected_hash": expected_hash,
            "actual_hash": row.get("hash"),
        })
        prev = row.get("hash", "")
    visible_checks = [item for item in checks if item.get("project") == project] if project else checks
    report = _write_report(project, visible_checks)
    return {
        "project": project or "all",
        "record_count": len(visible_checks),
        "global_record_count": len(rows),
        "passed": all(item["passed"] for item in checks) if checks else True,
        "failed_count": sum(1 for item in checks if not item["passed"]),
        "latest_hash": prev if rows else GENESIS,
        "checks": visible_checks[-20:],
        "report_path": report,
        "chain_path": str(CHAIN_FILE),
    }


def _write_report(project: str, checks: list[dict]) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in (project or "all") if c.isalnum() or c in "-_.")
    path = REPORT_DIR / f"{safe}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.md"
    lines = [
        "# Audit Hash Chain Verification",
        "",
        f"- Project: {project or 'all'}",
        f"- Generated: {_now()}",
        f"- Records: {len(checks)}",
        f"- Passed: {all(item['passed'] for item in checks) if checks else True}",
        "",
        "## Checks",
        "",
    ]
    for item in checks[-20:]:
        lines.append(f"- {item['id']}: passed={item['passed']}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def build_server() -> FastMCP:
    mcp = FastMCP("audit-hash-chain-mcp")

    @mcp.tool()
    def audit_hash_chain_brief() -> str:
        """Describe audit hash chain."""
        return _json({
            "name": "audit-hash-chain-mcp",
            "version": "v6.27",
            "chain": str(CHAIN_FILE),
            "note": "tamper-evident hash chain, not third-party signature",
        })

    @mcp.tool()
    def record_audit_event(project: str, event_type: str, evidence_json: str = "{}") -> str:
        """Append one audit event to the hash chain."""
        return _json(_record_event(project, event_type, _loads(evidence_json, {})))

    @mcp.tool()
    def verify_audit_chain(project: str = "") -> str:
        """Verify audit hash chain consistency."""
        return _json(_verify_chain(project))

    @mcp.tool()
    def audit_chain_report(project: str = "") -> str:
        """Return audit chain summary."""
        rows = _read_chain()
        if project:
            rows = [row for row in rows if row.get("project") == project]
        return _json({
            "project": project or "all",
            "record_count": len(rows),
            "latest": rows[-1] if rows else None,
            "chain": str(CHAIN_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
