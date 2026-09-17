# -*- coding: utf-8 -*-
"""Backup Integrity MCP server.

v6.23 records SHA-256 manifests for local backup artifacts and verifies that
recorded backups still match their manifest entries.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.state import safe_project

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
BACKUP_DIR = DATA_ROOT / "10_备份"
RESEARCH = DATA_ROOT / "09_投研"
INTEGRITY_DIR = RESEARCH / "backup_integrity"
MANIFEST_FILE = INTEGRITY_DIR / "backup_manifest.jsonl"
REPORT_DIR = INTEGRITY_DIR / "reports"


def _json(data: dict) -> str:
    return shared_json(data)


def _now() -> str:
    return shared_now()


def _safe_project(project: str) -> str:
    return safe_project(project, allowed="-_.", default="manual-agent-os")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _append(record: dict) -> None:
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_manifest() -> list[dict]:
    if not MANIFEST_FILE.exists():
        return []
    rows = []
    for line in MANIFEST_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _backup_entry(path: Path, project: str = "", version: str = "") -> dict:
    resolved = path.resolve()
    if BACKUP_DIR.resolve() not in resolved.parents and resolved != BACKUP_DIR.resolve():
        raise ValueError(f"backup path outside backup dir: {path}")
    stat = resolved.stat()
    return {
        "id": f"backup-manifest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "version": version,
        "name": resolved.name,
        "path": str(resolved),
        "bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "sha256": _sha256(resolved),
    }


def _latest_backups(limit: int) -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[:max(1, limit)]


def _write_report(project: str, rows: list[dict], title: str) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{_safe_project(project)}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.md"
    lines = [
        f"# {title}",
        "",
        f"- Project: {project or 'all'}",
        f"- Generated: {_now()}",
        f"- Records: {len(rows)}",
        "",
        "## Backups",
        "",
    ]
    for row in rows:
        status = row.get("status", "recorded")
        lines.append(f"- {row.get('name')}: status={status} bytes={row.get('bytes')} sha256={row.get('sha256')}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def _create_manifest(project: str, version: str, limit: int) -> dict:
    entries = []
    for path in _latest_backups(limit):
        entry = _backup_entry(path, project, version)
        _append(entry)
        entries.append(entry)
    report = _write_report(project, entries, "Backup Integrity Manifest")
    return {
        "status": "manifest_created",
        "project": project,
        "version": version,
        "count": len(entries),
        "entries": entries,
        "report_path": report,
        "manifest_path": str(MANIFEST_FILE),
    }


def _verify_latest(project: str = "", limit: int = 10) -> dict:
    rows = _read_manifest()
    if project:
        rows = [row for row in rows if row.get("project") == project]
    rows = rows[-max(1, limit):]
    results = []
    for row in rows:
        path = Path(row.get("path", ""))
        if not path.exists():
            results.append({**row, "status": "missing", "passed": False})
            continue
        current_hash = _sha256(path)
        current_size = path.stat().st_size
        passed = current_hash == row.get("sha256") and current_size == row.get("bytes")
        results.append({**row, "status": "verified" if passed else "mismatch", "passed": passed, "current_sha256": current_hash, "current_bytes": current_size})
    report = _write_report(project, results, "Backup Integrity Verification")
    return {
        "status": "verified",
        "project": project or "all",
        "count": len(results),
        "passed": all(item.get("passed") for item in results) if results else False,
        "passed_count": sum(1 for item in results if item.get("passed")),
        "failed_count": sum(1 for item in results if not item.get("passed")),
        "results": results,
        "report_path": report,
        "manifest_path": str(MANIFEST_FILE),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("backup-integrity-mcp")

    @mcp.tool()
    def backup_integrity_brief() -> str:
        """Describe backup integrity manifest."""
        return _json({
            "name": "backup-integrity-mcp",
            "version": "v6.23",
            "backup_dir": str(BACKUP_DIR),
            "manifest": str(MANIFEST_FILE),
        })

    @mcp.tool()
    def create_backup_manifest(project: str = "manual-agent-os", version: str = "",
                               latest_count: int = 5) -> str:
        """Create manifest entries for latest local backup zip files."""
        return _json(_create_manifest(project, version, latest_count))

    @mcp.tool()
    def verify_backup_manifest(project: str = "", latest_count: int = 10) -> str:
        """Verify latest manifest entries still match local files."""
        return _json(_verify_latest(project, latest_count))

    @mcp.tool()
    def backup_integrity_report(project: str = "") -> str:
        """Return manifest summary."""
        rows = _read_manifest()
        if project:
            rows = [row for row in rows if row.get("project") == project]
        return _json({
            "project": project or "all",
            "manifest_count": len(rows),
            "latest": rows[-1] if rows else None,
            "manifest": str(MANIFEST_FILE),
        })

    return mcp


def main() -> None:
    build_server().run()
