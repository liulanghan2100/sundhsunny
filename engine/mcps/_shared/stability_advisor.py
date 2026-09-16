# -*- coding: utf-8 -*-
"""Pure helper layer for the Agent OS stability advisor."""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def run_states(runtime_dir) -> list[dict]:
    if not runtime_dir.exists():
        return []
    rows = []
    for path in sorted(runtime_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = read_json(path, {})
        if isinstance(data, dict):
            data["_path"] = str(path)
            rows.append(data)
    return rows


def capability_names(run: dict) -> set[str]:
    names = {"task_queue_mcp"}
    for call in run.get("tool_calls", []) or []:
        tool = str(call.get("tool", ""))
        if "." in tool:
            names.add(tool.split(".", 1)[0])
    if run.get("mandatory"):
        names.add("mandatory_runtime_hook_mcp")
    if run.get("completion_verifier"):
        names.add("completion_verifier_mcp")
    if run.get("dashboard"):
        names.add("dashboard_mcp")
    if run.get("memory_writes"):
        names.add("experience_memory_mcp")
    return names


def expected_fail_closed(run: dict) -> bool:
    project = str(run.get("project", "")).lower()
    task = str(run.get("task", "")).lower()
    verifier = run.get("completion_verifier") or {}
    failed_checks = {str(c.get("name", "")) for c in run.get("checks", []) if not c.get("passed")}
    boundary_terms = [
        "administrator",
        "admin privileges",
        "missing expected artifact",
        "must fail",
        "lacks evidence",
        "string command",
        "outside workspace",
        "pseudo real completion",
    ]
    if any(term in task for term in boundary_terms):
        return True
    if "closed-loop-eval" in project and (run.get("status") in {"failed", "blocked"} or run.get("decision") == "block"):
        return True
    if "smoke-task-queue" in project and "administrator" in task:
        return True
    if verifier and verifier.get("passed") is False and verifier.get("task_class") == "C":
        return True
    if "admin_boundary" in failed_checks:
        return True
    return False


def failure_reason(run: dict) -> str:
    verifier = run.get("completion_verifier") or {}
    if verifier and not verifier.get("passed", True):
        missing = verifier.get("missing", [])
        return "completion_verifier missing=" + ",".join(str(x) for x in missing[:6])
    failed_checks = [c.get("name") for c in run.get("checks", []) if not c.get("passed")]
    if failed_checks:
        return "failed_checks=" + ",".join(str(x) for x in failed_checks)
    return str(run.get("status") or run.get("decision") or "unknown")


def build_metrics(runs: list[dict]) -> dict:
    metrics = defaultdict(lambda: {
        "calls": 0,
        "completed": 0,
        "raw_failed": 0,
        "raw_blocked": 0,
        "failed": 0,
        "blocked": 0,
        "retry": 0,
        "expected_fail_closed": 0,
        "success_rate": 0.0,
        "operational_success_rate": 0.0,
        "last_success": "",
        "last_failure": "",
        "last_failure_reason": "",
        "recent_runs": [],
    })
    for run in runs:
        status = run.get("status", "")
        decision = run.get("decision", "")
        ok = status == "completed" and decision == "complete"
        raw_failed = status == "failed"
        raw_blocked = status == "blocked" or decision == "block"
        retry = status == "retry" or decision == "retry"
        expected_boundary = expected_fail_closed(run)
        failed = raw_failed and not expected_boundary
        blocked = raw_blocked and not expected_boundary
        for name in capability_names(run):
            item = metrics[name]
            item["calls"] += 1
            item["completed"] += 1 if ok else 0
            item["raw_failed"] += 1 if raw_failed else 0
            item["raw_blocked"] += 1 if raw_blocked else 0
            item["failed"] += 1 if failed else 0
            item["blocked"] += 1 if blocked else 0
            item["retry"] += 1 if retry else 0
            item["expected_fail_closed"] += 1 if expected_boundary else 0
            if ok and not item["last_success"]:
                item["last_success"] = run.get("updated", "")
            if (failed or blocked) and not item["last_failure"]:
                item["last_failure"] = run.get("updated", "")
                item["last_failure_reason"] = failure_reason(run)
            if len(item["recent_runs"]) < 10:
                item["recent_runs"].append({
                    "run_id": run.get("run_id"),
                    "project": run.get("project"),
                    "status": status,
                    "decision": decision,
                    "path": run.get("_path", ""),
                })
    for item in metrics.values():
        item["success_rate"] = round(item["completed"] / item["calls"], 4) if item["calls"] else 0.0
        item["operational_success_rate"] = round(
            (item["completed"] + item["expected_fail_closed"]) / item["calls"], 4
        ) if item["calls"] else 0.0
    return {"generated": now(), "capabilities": dict(sorted(metrics.items()))}


def latest_eval_score(eval_runs_path) -> dict:
    runs = [r for r in read_jsonl(eval_runs_path) if r.get("project") == "agent-os-closed-loop-eval"]
    return runs[-1] if runs else {}


def registry_items(path) -> list[dict]:
    return read_json(path, {}).get("items", [])


def registry_advice_items(metrics: dict, registry_dir, core_capabilities: set[str], eval_ok: bool) -> list[dict]:
    capability_metrics = metrics.get("capabilities", {})
    advice = []
    for registry_name in ["mcp_registry.json", "skill_registry.json"]:
        for item in registry_items(registry_dir / registry_name):
            name = item.get("name", "")
            status = item.get("status", "shadow")
            m = capability_metrics.get(name, {})
            calls = int(m.get("calls", 0))
            success_rate = float(m.get("operational_success_rate", m.get("success_rate", 0)))
            blocked = int(m.get("blocked", 0))
            failed = int(m.get("failed", 0))
            recommendation = "hold"
            reason = "insufficient evidence"
            if status == "shadow" and calls >= 3 and success_rate >= 0.95 and eval_ok:
                recommendation = "promote_to_active"
                reason = "shadow capability has successful RunState evidence and latest 30-case eval passed"
            elif status == "active" and calls >= 3 and (success_rate < 0.8 or blocked + failed >= 2):
                recommendation = "demote_to_shadow"
                reason = "active capability has repeated failed or blocked RunStates"
            elif status == "deprecated" and calls == 0:
                recommendation = "consider_retire"
                reason = "deprecated capability has no RunState usage evidence"
            elif name in core_capabilities and status == "active":
                recommendation = "keep_active"
                reason = "core runtime capability"
            advice.append({
                "name": name,
                "type": item.get("type", "unknown"),
                "current_status": status,
                "recommendation": recommendation,
                "reason": reason,
                "calls": calls,
                "success_rate": float(m.get("success_rate", 0)),
                "operational_success_rate": success_rate,
                "failed": failed,
                "blocked": blocked,
                "expected_fail_closed": int(m.get("expected_fail_closed", 0)),
                "last_success": m.get("last_success", ""),
                "last_failure": m.get("last_failure", ""),
                "last_failure_reason": m.get("last_failure_reason", ""),
            })
    return advice


def shadow_score_advice_items(shadow_scoring: dict, review_queue: dict) -> list[dict]:
    review_items = review_queue.get("items", []) if isinstance(review_queue, dict) else []
    review_status = {item.get("capability"): item for item in review_items}
    score_items = shadow_scoring.get("scores", []) if isinstance(shadow_scoring, dict) else []
    advice = []
    for score in score_items:
        recommendation = score.get("promotion_recommendation", "keep_shadow")
        review_item = review_status.get(score.get("capability", ""), {})
        if review_item.get("status") == "applied_or_not_shadow":
            recommendation = "review_resolved"
        elif recommendation == "promote_to_active_candidate" and review_item:
            recommendation = "owner_review_required"
        advice.append({
            "name": score.get("capability", ""),
            "type": "shadow_score",
            "current_status": "shadow",
            "recommendation": recommendation,
            "reason": score.get("promotion_reason", ""),
            "calls": score.get("shadow_run_count", 0),
            "success_rate": score.get("agreement_rate", 0),
            "operational_success_rate": score.get("agreement_rate", 0),
            "failed": score.get("false_positive_count", 0),
            "blocked": score.get("takeover_count", 0),
            "expected_fail_closed": 0,
            "last_success": "",
            "last_failure": "",
            "last_failure_reason": "",
            "shadow_scoring": {
                "agreement_rate": score.get("agreement_rate", 0),
                "warn_rate": score.get("warn_rate", 0),
                "false_positive_rate": score.get("false_positive_rate", 0),
                "evidence_completeness": score.get("evidence_completeness", 0),
                "promotion_candidate": score.get("promotion_candidate", False),
                "no_auto_promotion_guard": score.get("no_auto_promotion_guard", True),
                "review_status": review_item.get("status", ""),
                "review_id": review_item.get("review_id", ""),
                "approval_required": review_item.get("approval_required", True),
            },
        })
    return advice


def active_canary_advice_items(canary: dict) -> list[dict]:
    canary_items = canary.get("items", []) if isinstance(canary, dict) else []
    advice = []
    for item in canary_items:
        recommendation = "canary_pass" if item.get("status") == "canary_pass" else "canary_collecting"
        if item.get("rollback_candidate"):
            recommendation = "rollback_review_required"
        advice.append({
            "name": item.get("capability", ""),
            "type": "active_canary",
            "current_status": item.get("registry_status", ""),
            "recommendation": recommendation,
            "reason": item.get("rollback_reason") or item.get("status", ""),
            "calls": item.get("active_run_count", 0),
            "success_rate": item.get("active_success_rate", 0),
            "operational_success_rate": item.get("active_success_rate", 0),
            "failed": item.get("active_failure_count", 0),
            "blocked": 0,
            "expected_fail_closed": 0,
            "last_success": "",
            "last_failure": "",
            "last_failure_reason": item.get("rollback_reason", ""),
            "active_canary": {
                "canary_active": item.get("canary_active", False),
                "active_run_count": item.get("active_run_count", 0),
                "active_success_rate": item.get("active_success_rate", 0),
                "verifier_failure_count": item.get("verifier_failure_count", 0),
                "rollback_candidate": item.get("rollback_candidate", False),
                "owner_review_required_for_rollback": item.get("rollback_candidate", False),
            },
        })
    return advice


def build_advice(metrics: dict, latest_eval: dict, registry_dir, shadow_scoring: dict,
                 review_queue: dict, canary: dict, core_capabilities: set[str],
                 shadow_scoring_path: str, review_queue_path: str,
                 canary_status_path: str) -> dict:
    eval_ok = latest_eval.get("failed", 1) == 0 and latest_eval.get("case_count", 0) >= 30
    advice = registry_advice_items(metrics, registry_dir, core_capabilities, eval_ok)
    advice.extend(shadow_score_advice_items(shadow_scoring, review_queue))
    advice.extend(active_canary_advice_items(canary))
    return {
        "generated": now(),
        "latest_eval": {
            "id": latest_eval.get("id"),
            "case_count": latest_eval.get("case_count", 0),
            "failed": latest_eval.get("failed", 0),
            "score": latest_eval.get("score", 0),
        },
        "advice": advice,
        "shadow_scoring_path": shadow_scoring_path,
        "promotion_review_queue_path": review_queue_path,
        "active_canary_status_path": canary_status_path,
        "no_auto_promotion_guard": True,
    }


def build_soak_report(runs: list[dict], metrics: dict, advice: dict) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    today_runs = [r for r in runs if str(r.get("updated", r.get("created", ""))).startswith(today)]
    status_counts = Counter(r.get("status", "unknown") for r in today_runs)
    verifier_rejects = sum(1 for r in today_runs if (r.get("completion_verifier") or {}).get("passed") is False)
    expected_boundary = sum(1 for r in today_runs if expected_fail_closed(r))
    unexpected_failed = sum(1 for r in today_runs if r.get("status") == "failed" and not expected_fail_closed(r))
    unexpected_blocked = sum(
        1 for r in today_runs
        if (r.get("status") == "blocked" or r.get("decision") == "block") and not expected_fail_closed(r)
    )
    memory_writes = sum(len(r.get("memory_writes", []) or []) for r in today_runs)
    recommendations = Counter(a.get("recommendation", "hold") for a in advice.get("advice", []))
    return {
        "generated": now(),
        "local_date": today,
        "run_count": len(today_runs),
        "status_counts": dict(status_counts),
        "completion_verifier_rejects": verifier_rejects,
        "expected_fail_closed": expected_boundary,
        "unexpected_failed": unexpected_failed,
        "unexpected_blocked": unexpected_blocked,
        "memory_write_count": memory_writes,
        "capability_count": len(metrics.get("capabilities", {})),
        "promotion_recommendations": dict(recommendations),
        "top_unstable": [
            {"name": name, **m}
            for name, m in sorted(
                metrics.get("capabilities", {}).items(),
                key=lambda kv: (kv[1].get("failed", 0) + kv[1].get("blocked", 0), kv[1].get("calls", 0)),
                reverse=True,
            )[:10]
        ],
    }


def markdown_lines(report: dict, advice: dict) -> list[str]:
    lines = [
        f"# Agent OS Daily Soak Report {report['local_date']}",
        "",
        f"- runs: {report['run_count']}",
        f"- status_counts: `{json.dumps(report['status_counts'], ensure_ascii=False)}`",
        f"- completion_verifier_rejects: {report['completion_verifier_rejects']}",
        f"- expected_fail_closed: {report['expected_fail_closed']}",
        f"- unexpected_failed: {report['unexpected_failed']}",
        f"- unexpected_blocked: {report['unexpected_blocked']}",
        f"- memory_write_count: {report['memory_write_count']}",
        f"- capability_count: {report['capability_count']}",
        f"- promotion_recommendations: `{json.dumps(report['promotion_recommendations'], ensure_ascii=False)}`",
        "",
        "## Top Unstable",
        "",
    ]
    for item in report["top_unstable"]:
        lines.append(
            f"- `{item['name']}` calls={item['calls']} failed={item['failed']} blocked={item['blocked']} "
            f"expected_fail_closed={item['expected_fail_closed']} operational_success_rate={item['operational_success_rate']}"
        )
    lines.extend(["", "## Actionable Advice", ""])
    for item in advice.get("advice", []):
        if item["recommendation"] != "hold":
            lines.append(f"- `{item['name']}` {item['current_status']} -> {item['recommendation']}: {item['reason']}")
    return lines
