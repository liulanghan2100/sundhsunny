# -*- coding: utf-8 -*-
"""Pure helper layer for the shadow runner."""
import json
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def shadow_run_id() -> str:
    return f"shadow-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def latest_task_card(runtime_dir) -> dict:
    card_dir = runtime_dir / "task_cards"
    cards = sorted(card_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not cards:
        raise FileNotFoundError("no task cards available for shadow run")
    data = read_json(cards[0], {})
    data["_path"] = str(cards[0])
    return data


def registry_item(registry_dir, name: str) -> dict:
    for file in ["skill_registry.json", "mcp_registry.json"]:
        payload = read_json(registry_dir / file, {})
        for item in payload.get("items", []):
            if item.get("name") == name:
                return item
    return {}


def choose_shadow_capability(registry_dir, preferred: str = "bug-intake") -> dict:
    item = registry_item(registry_dir, preferred)
    if item and item.get("status") == "shadow":
        return item
    payload = read_json(registry_dir / "skill_registry.json", {})
    for candidate in payload.get("items", []):
        if candidate.get("status") == "shadow":
            return candidate
    raise ValueError("no shadow capability available")


def shadow_capabilities(registry_dir, limit: int = 3, preferred: str = "bug-intake") -> list[dict]:
    capabilities = []
    preferred_item = registry_item(registry_dir, preferred)
    if preferred_item and preferred_item.get("status") == "shadow":
        capabilities.append(preferred_item)
    for file in ["skill_registry.json", "mcp_registry.json"]:
        payload = read_json(registry_dir / file, {})
        for candidate in payload.get("items", []):
            if candidate.get("status") != "shadow":
                continue
            if candidate.get("name") in {item.get("name") for item in capabilities}:
                continue
            capabilities.append(candidate)
            if len(capabilities) >= limit:
                return capabilities
    if not capabilities:
        raise ValueError("no shadow capability available")
    return capabilities[:limit]


def analyze_shadow(task_card: dict, capability: dict) -> dict:
    task = str(task_card.get("task", ""))
    criteria = task_card.get("acceptance_criteria", []) or []
    expected_artifacts = task_card.get("expected_artifacts", []) or []
    findings = []
    if not criteria:
        findings.append("acceptance criteria missing or empty")
    if task_card.get("risk") in {"high", "critical"}:
        findings.append("high risk task should require explicit approval evidence")
    if "bug" in capability.get("name", "") and expected_artifacts:
        findings.append("expected artifacts should be checked before closure")
    if not task.strip():
        findings.append("task text missing")
    recommendation = "no_promote"
    if not findings and capability.get("risk") == "normal":
        recommendation = "candidate_for_more_shadow_runs"
    return {
        "mode": "read_only_shadow",
        "capability": capability.get("name"),
        "capability_type": capability.get("type"),
        "task_card_id": task_card.get("id"),
        "task": task,
        "findings": findings,
        "shadow_result": "pass" if not findings else "warn",
        "promotion_signal": recommendation,
    }


def diff_summary(primary: dict, shadow: dict) -> dict:
    return {
        "primary_status": primary.get("status"),
        "primary_task_class": primary.get("task_class"),
        "shadow_result": shadow.get("shadow_result"),
        "finding_count": len(shadow.get("findings", [])),
        "agreement": primary.get("status") in {"queued", "completed", "running"}
        and shadow.get("shadow_result") in {"pass", "warn"},
    }


def expected_shadow_warning(task_card: dict, shadow: dict) -> bool:
    task = str(task_card.get("task", "")).lower()
    criteria = task_card.get("acceptance_criteria", []) or []
    expected_artifacts = task_card.get("expected_artifacts", []) or []
    boundary_terms = [
        "artifact missing",
        "missing artifact",
        "verifier warn",
        "evidence insufficient",
        "must fail",
        "fail-closed",
        "admin",
        "retry",
    ]
    if not criteria or not str(task_card.get("task", "")).strip():
        return True
    if expected_artifacts and "bug" in str(shadow.get("capability", "")):
        return True
    if task_card.get("risk") in {"high", "critical"}:
        return True
    return any(term in task for term in boundary_terms)


def evidence_completeness(record: dict) -> float:
    checks = [
        bool(record.get("schema_version")),
        bool(record.get("shadow_run_id")),
        bool(record.get("primary", {}).get("task_card_id")),
        bool(record.get("shadow_capability", {}).get("name")),
        bool(record.get("task_card", {}).get("id")),
        bool(record.get("shadow_result", {}).get("shadow_result")),
        "promotion_signal" in record.get("shadow_result", {}),
        "agreement" in record.get("diff", {}),
        record.get("takeover") is False,
        record.get("safety") == "read_only_no_side_effects",
    ]
    return round(sum(1 for check in checks if check) / len(checks), 4)


def false_positive(record: dict) -> bool:
    shadow = record.get("shadow_result", {})
    if shadow.get("shadow_result") != "warn":
        return False
    return not expected_shadow_warning(record.get("task_card", {}), shadow)


def scoring_recommendation(score: dict, thresholds: dict) -> tuple[str, str]:
    if score["takeover_count"]:
        return "keep_shadow", "takeover guard violation"
    if score["shadow_run_count"] < thresholds["min_shadow_run_count"]:
        return "keep_shadow", "insufficient shadow run count"
    if score["evidence_completeness"] < thresholds["min_evidence_completeness"]:
        return "keep_shadow", "evidence completeness below threshold"
    if score["false_positive_rate"] > thresholds["max_false_positive_rate"]:
        return "keep_shadow", "false positive rate above threshold"
    if score["agreement_rate"] < thresholds["min_agreement_rate"]:
        return "keep_shadow", "agreement rate below threshold"
    if score["warn_rate"] > thresholds["max_warn_rate"]:
        return "keep_shadow", "warning rate above threshold"
    return "promote_to_active_candidate", "shadow scoring thresholds met; owner approval required"


def score_capability(capability: str, records: list[dict], thresholds: dict) -> dict:
    run_count = len(records)
    agreement_count = sum(1 for r in records if r.get("diff", {}).get("agreement") is True)
    warn_count = sum(1 for r in records if r.get("shadow_result", {}).get("shadow_result") == "warn")
    pass_count = sum(1 for r in records if r.get("shadow_result", {}).get("shadow_result") == "pass")
    false_positive_count = sum(1 for r in records if false_positive(r))
    takeover_count = sum(1 for r in records if r.get("takeover") is not False)
    evidence_avg = round(sum(evidence_completeness(r) for r in records) / run_count, 4) if run_count else 0.0
    score = {
        "capability": capability,
        "shadow_run_count": run_count,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "agreement_rate": round(agreement_count / run_count, 4) if run_count else 0.0,
        "warn_rate": round(warn_count / run_count, 4) if run_count else 0.0,
        "false_positive_rate": round(false_positive_count / run_count, 4) if run_count else 0.0,
        "false_positive_count": false_positive_count,
        "evidence_completeness": evidence_avg,
        "takeover_count": takeover_count,
        "latest_run": records[-1].get("shadow_run_id", "") if records else "",
        "latest_path": records[-1].get("_path", "") if records else "",
        "no_auto_promotion_guard": True,
    }
    recommendation, reason = scoring_recommendation(score, thresholds)
    score["promotion_candidate"] = recommendation == "promote_to_active_candidate"
    score["promotion_recommendation"] = recommendation
    score["promotion_reason"] = reason
    return score


def promotion_scoring_payload(groups: dict[str, list[dict]], thresholds: dict) -> dict:
    return {
        "schema_version": "shadow-promotion-scoring/v0.2",
        "generated": now(),
        "thresholds": thresholds,
        "no_auto_promotion_guard": True,
        "scores": [
            score_capability(capability, records, thresholds)
            for capability, records in sorted(groups.items())
        ],
    }


def run_summary_entry(path, data: dict) -> dict:
    return {
        "shadow_run_id": data.get("shadow_run_id", path.stem),
        "capability": data.get("shadow_capability", {}).get("name", ""),
        "task_card_id": data.get("task_card", {}).get("id", ""),
        "shadow_result": data.get("shadow_result", {}).get("shadow_result", ""),
        "promotion_signal": data.get("shadow_result", {}).get("promotion_signal", ""),
        "finding_count": len(data.get("shadow_result", {}).get("findings", [])),
        "path": str(path),
    }


def shadow_summary_payload(runs: list[dict], scoring: dict, scoring_path: str) -> dict:
    return {
        "generated": now(),
        "run_count": len(runs),
        "runs": runs,
        "scoring_path": scoring_path,
        "promotion_candidate_count": sum(1 for score in scoring.get("scores", []) if score.get("promotion_candidate")),
    }


def shadow_record_payload(run_id: str, created: str, task_card: dict, capability: dict,
                          shadow: dict, diff: dict) -> dict:
    return {
        "schema_version": "shadow-run/v0.1",
        "shadow_run_id": run_id,
        "created": created,
        "primary": {
            "task_card_id": task_card.get("id"),
            "run_id": task_card.get("run_id"),
            "task_card_path": task_card.get("_path"),
            "status": task_card.get("status"),
        },
        "shadow_capability": capability,
        "task_card": task_card,
        "shadow_result": shadow,
        "diff": diff,
        "takeover": False,
        "safety": "read_only_no_side_effects",
    }


def eval_summary_payload(capabilities: list[dict], records: list[dict], scoring: dict,
                         scoring_path: str) -> dict:
    return {
        "schema_version": "shadow-eval/v0.2",
        "generated": now(),
        "case_count": len({item["record"].get("task_card", {}).get("id") for item in records}),
        "capability_count": len(capabilities),
        "shadow_record_count": len(records),
        "capabilities": [c.get("name") for c in capabilities],
        "records": [{
            "shadow_run_id": item["record"].get("shadow_run_id"),
            "capability": item["record"].get("shadow_capability", {}).get("name"),
            "task_card_id": item["record"].get("task_card", {}).get("id"),
            "shadow_result": item["record"].get("shadow_result", {}).get("shadow_result"),
            "promotion_signal": item["record"].get("shadow_result", {}).get("promotion_signal"),
            "path": item["path"],
        } for item in records],
        "promotion_scoring_path": scoring_path,
        "promotion_candidate_count": sum(1 for score in scoring.get("scores", []) if score.get("promotion_candidate")),
        "no_auto_promotion_guard": True,
    }


def sample_collection_result_payload(selected: list[dict], task_cards: list[dict], records: list[dict],
                                     summary: dict, scoring: dict, scoring_path: str) -> dict:
    return {
        "status": "generated",
        "capabilities": [item.get("name") for item in selected],
        "task_count": len(task_cards),
        "record_count": len(records),
        "summary": summary,
        "promotion_candidate_count": sum(1 for score in scoring.get("scores", []) if score.get("promotion_candidate")),
        "scoring_path": scoring_path,
    }
