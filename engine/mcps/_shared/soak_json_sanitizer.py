# -*- coding: utf-8 -*-
"""Pure helpers for L4 soak JSON sanitizer."""
import json
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def strip_illegal_controls(text: str) -> tuple[str, int]:
    cleaned = []
    removed = 0
    for char in text:
        if ord(char) < 32 and char not in "\t\r\n":
            removed += 1
            continue
        cleaned.append(char)
    return "".join(cleaned), removed


def parse_cleaned_json(cleaned: str) -> tuple[dict, str]:
    try:
        payload = json.loads(cleaned)
    except Exception as exc:
        return {}, str(exc)
    return payload if isinstance(payload, dict) else {}, ""


def report_payload(schema_version: str, soak_json_path: str, original_exists: bool,
                   raw_bytes: int, illegal_control_count: int, parse_error: str,
                   canonical_written: bool, payload: dict) -> dict:
    return {
        "schema_version": schema_version,
        "generated": now(),
        "status": "sanitized" if canonical_written else "parse_failed",
        "soak_json": soak_json_path,
        "original_exists": original_exists,
        "raw_bytes": raw_bytes,
        "illegal_control_count": illegal_control_count,
        "parse_error": parse_error,
        "canonical_written": canonical_written,
        "soak_status": payload.get("status", "") if isinstance(payload, dict) else "",
        "completed_days": payload.get("completed_days", 0) if isinstance(payload, dict) else 0,
        "soak_days_required": payload.get("soak_days_required", 0) if isinstance(payload, dict) else 0,
        "read_only_governance": True,
        "canonical_json_rewrite_only": True,
        "no_decisions_applied": True,
        "no_model_api_calls": True,
        "no_provider_activation": True,
        "no_routing_auto_switch": True,
        "no_runtime_mutation": True,
        "no_registry_lifecycle_mutation": True,
        "no_skill_or_runtime_standard_writeback": True,
    }
