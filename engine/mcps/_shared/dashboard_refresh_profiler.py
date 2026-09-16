# -*- coding: utf-8 -*-
"""Pure helpers for dashboard refresh profiling."""
import json
import time
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def research_dirs(root) -> list:
    return [path for path in root.iterdir() if path.is_dir() and path.name.startswith("09_")]


def canonical_research_dir(root):
    candidates = [
        path for path in research_dirs(root)
        if (path / "dashboard").exists() and (path / "agent_os_owner_decisions").exists()
    ]
    if candidates:
        return candidates[0]
    candidates = [path for path in research_dirs(root) if (path / "dashboard").exists()]
    return candidates[0] if candidates else root / "09_research"


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def write_json(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def append_jsonl(path, payload: dict, ts: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = ts or now()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": stamp, **payload}, ensure_ascii=True) + "\n")


def profile_status(total_ms: int) -> str:
    if total_ms > 30000:
        return "slow_over_30s"
    if total_ms > 10000:
        return "moderate_over_10s"
    return "profiled"


def profile_payload(schema_version: str, started: str, total_ms: int, collect_ms: int,
                    write_ms: int, write_result: dict, data: dict) -> dict:
    return {
        "schema_version": schema_version,
        "generated": now(),
        "started": started,
        "status": profile_status(total_ms),
        "total_ms": total_ms,
        "collect_ms": collect_ms,
        "write_dashboard_ms": write_ms,
        "write_result": write_result,
        "project_count": len(data.get("manual_projects", [])),
        "mcp_count": len(data.get("mcp_inventory", [])),
        "owner_decision_sections": len(data.get("owner_decision", {})),
        "model_adapter_sections": len(data.get("model_adapter", {})),
        "knowledge_trust_sections": len(data.get("knowledge_trust", {})),
        "read_only_dashboard_refresh_profiler": True,
        "owner_approval_required": False,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
