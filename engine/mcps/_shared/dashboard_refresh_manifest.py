# -*- coding: utf-8 -*-
"""Pure helpers for dashboard refresh manifest construction."""
import hashlib
import json
from datetime import datetime, timezone


SCHEMA_VERSION = "agent-os-dashboard-refresh-manifest/v0.2"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_digest(path) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False, "size": 0, "mtime_ns": 0, "sha256": ""}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {"path": str(path), "exists": True, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest.hexdigest()}


def module_digest(files: list[dict]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(json.dumps({
            "path": item["path"],
            "exists": item["exists"],
            "size": item["size"],
            "sha256": item["sha256"],
        }, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def manifest_payload(research_dir, module_inputs: dict, previous_manifest: dict | None = None) -> dict:
    previous_modules = {
        item.get("module"): item
        for item in (previous_manifest or {}).get("modules", [])
        if isinstance(item, dict) and item.get("module")
    } if isinstance(previous_manifest, dict) else {}
    modules = []
    for module, rel_paths in module_inputs.items():
        files = [file_digest(research_dir / rel_path) for rel_path in rel_paths]
        digest = module_digest(files)
        previous_digest = previous_modules.get(module, {}).get("input_hash", "")
        changed = bool(previous_digest and previous_digest != digest)
        unchanged = bool(previous_digest and previous_digest == digest)
        modules.append({
            "module": module,
            "input_hash": digest,
            "previous_input_hash": previous_digest,
            "status": "unchanged" if unchanged else ("changed" if changed else "new"),
            "file_count": len(files),
            "present_count": sum(1 for item in files if item["exists"]),
            "missing_count": sum(1 for item in files if not item["exists"]),
            "total_bytes": sum(item["size"] for item in files),
            "files": files,
            "cache_observation_only": True,
            "skip_allowed": False,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "generated": now(),
        "research_dir": str(research_dir),
        "modules": modules,
        "summary": {
            "module_count": len(modules),
            "unchanged_count": sum(1 for item in modules if item["status"] == "unchanged"),
            "changed_count": sum(1 for item in modules if item["status"] == "changed"),
            "new_count": sum(1 for item in modules if item["status"] == "new"),
            "missing_file_count": sum(item["missing_count"] for item in modules),
        },
        "read_only_manifest": True,
        "owner_approval_required": False,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
        "next_safe_step": "Use repeated unchanged module observations to justify a conservative skip-unchanged cache layer.",
    }
