# -*- coding: utf-8 -*-
"""Mathematical Reasoning MCP server.

v6.33 turns selected mathematical thinking models into executable local tools:
Bayesian update, expected value, information gain, dependency graph checks,
simple anomaly detection, and Monte Carlo-style project risk simulation.
"""
import json
import math
import random
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
REASONING_DIR = DATA_ROOT / "09_投研" / "mathematical_reasoning"
REASONING_FILE = REASONING_DIR / "reasoning_events.jsonl"
REPORT_DIR = REASONING_DIR / "reports"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _append(record: dict) -> dict:
    REASONING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REASONING_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _read_events() -> list[dict]:
    if not REASONING_FILE.exists():
        return []
    rows = []
    for line in REASONING_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _event(project: str, model: str, payload: dict) -> dict:
    return _append({
        "id": f"math-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "ts": _now(),
        "project": project,
        "type": "mathematical_reasoning_event",
        "model": model,
        **payload,
    })


def _bayesian(project: str, hypothesis: str, prior: float,
              likelihood_if_true: float, likelihood_if_false: float,
              evidence: str = "") -> dict:
    p_h = _clamp01(prior)
    p_e_h = _clamp01(likelihood_if_true)
    p_e_not_h = _clamp01(likelihood_if_false)
    denom = p_e_h * p_h + p_e_not_h * (1.0 - p_h)
    posterior = p_h if denom == 0 else (p_e_h * p_h) / denom
    return _event(project, "bayesian_update", {
        "hypothesis": hypothesis,
        "evidence": evidence,
        "prior": round(p_h, 6),
        "likelihood_if_true": round(p_e_h, 6),
        "likelihood_if_false": round(p_e_not_h, 6),
        "posterior": round(_clamp01(posterior), 6),
        "delta": round(_clamp01(posterior) - p_h, 6),
    })


def _score_actions(project: str, actions: list[dict]) -> dict:
    scored = []
    for action in actions:
        value = float(action.get("value", 0.0))
        success_prob = _clamp01(action.get("success_prob", 0.5))
        cost = float(action.get("cost", 0.0))
        risk = float(action.get("risk", 0.0))
        info_gain = float(action.get("information_gain", 0.0))
        score = value * success_prob + info_gain - cost - risk
        item = dict(action)
        item["expected_value_score"] = round(score, 6)
        scored.append(item)
    scored.sort(key=lambda x: x["expected_value_score"], reverse=True)
    return _event(project, "expected_value_ranking", {
        "actions": scored,
        "recommended": scored[0] if scored else None,
    })


def _rank_info_gain(project: str, questions: list[dict]) -> dict:
    ranked = []
    for q in questions:
        uncertainty_reduction = float(q.get("uncertainty_reduction", 0.0))
        decision_impact = float(q.get("decision_impact", 0.0))
        cost = max(0.000001, float(q.get("cost", 1.0)))
        score = (uncertainty_reduction * decision_impact) / cost
        item = dict(q)
        item["information_gain_score"] = round(score, 6)
        ranked.append(item)
    ranked.sort(key=lambda x: x["information_gain_score"], reverse=True)
    return _event(project, "information_gain_ranking", {
        "questions": ranked,
        "recommended": ranked[0] if ranked else None,
    })


def _dependency_graph(project: str, nodes: list[str], edges: list[list[str]]) -> dict:
    node_set = set(nodes)
    graph = {node: [] for node in nodes}
    missing = []
    for edge in edges:
        if len(edge) != 2:
            continue
        src, dst = edge
        if src not in node_set or dst not in node_set:
            missing.append(edge)
            continue
        graph[src].append(dst)
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: list[str] = []

    def dfs(node: str, path: list[str]) -> bool:
        if node in visiting:
            cycle.extend(path[path.index(node):] + [node] if node in path else [node])
            return True
        if node in visited:
            return False
        visiting.add(node)
        for nxt in graph[node]:
            if dfs(nxt, path + [nxt]):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for n in nodes:
        if dfs(n, [n]):
            break
    indegree = {node: 0 for node in nodes}
    for src in graph:
        for dst in graph[src]:
            indegree[dst] += 1
    ready = sorted([node for node, deg in indegree.items() if deg == 0])
    return _event(project, "dependency_graph", {
        "nodes": nodes,
        "edges": edges,
        "missing_edges": missing,
        "has_cycle": bool(cycle),
        "cycle": cycle,
        "ready_nodes": ready,
        "node_count": len(nodes),
        "edge_count": len(edges),
    })


def _detect_anomaly(project: str, metric: str, values: list[float],
                    latest_value: float | None = None, z_threshold: float = 2.5) -> dict:
    series = [float(v) for v in values]
    latest = float(latest_value if latest_value is not None else (series[-1] if series else 0.0))
    baseline = series[:-1] if latest_value is None and len(series) > 1 else series
    mean = sum(baseline) / max(len(baseline), 1)
    variance = sum((x - mean) ** 2 for x in baseline) / max(len(baseline), 1)
    std = math.sqrt(variance)
    z = 0.0 if std == 0 else (latest - mean) / std
    return _event(project, "metric_anomaly_detection", {
        "metric": metric,
        "values": series,
        "latest_value": latest,
        "mean": round(mean, 6),
        "std": round(std, 6),
        "z_score": round(z, 6),
        "threshold": z_threshold,
        "anomaly": abs(z) >= float(z_threshold) if std > 0 else False,
    })


def _simulate_risk(project: str, tasks: list[dict], runs: int = 1000, seed: int = 42) -> dict:
    rng = random.Random(int(seed))
    runs = max(1, min(int(runs), 10000))
    successes = 0
    durations = []
    costs = []
    for _ in range(runs):
        ok = True
        duration = 0.0
        cost = 0.0
        for task in tasks:
            p = _clamp01(task.get("success_prob", 0.8))
            optimistic = float(task.get("optimistic", task.get("duration", 1.0)))
            most_likely = float(task.get("most_likely", task.get("duration", optimistic)))
            pessimistic = float(task.get("pessimistic", most_likely))
            expected = (optimistic + 4 * most_likely + pessimistic) / 6.0
            duration += max(0.0, rng.gauss(expected, max((pessimistic - optimistic) / 6.0, 0.0001)))
            cost += float(task.get("cost", 0.0))
            if rng.random() > p:
                ok = False
        if ok:
            successes += 1
        durations.append(duration)
        costs.append(cost)
    durations.sort()
    costs.sort()
    p95_idx = min(len(durations) - 1, int(0.95 * len(durations)))
    return _event(project, "monte_carlo_project_risk", {
        "runs": runs,
        "task_count": len(tasks),
        "success_probability": round(successes / runs, 6),
        "mean_duration": round(sum(durations) / runs, 6),
        "p95_duration": round(durations[p95_idx], 6),
        "mean_cost": round(sum(costs) / runs, 6),
        "p95_cost": round(costs[p95_idx], 6),
    })


def _report(project: str = "") -> dict:
    rows = _read_events()
    if project:
        rows = [row for row in rows if row.get("project") == project]
    by_model: dict[str, int] = {}
    for row in rows:
        model = row.get("model", "unknown")
        by_model[model] = by_model.get(model, 0) + 1
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"reasoning_report_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.md"
    lines = [
        "# Mathematical Reasoning Report",
        "",
        f"- Project: {project or 'all'}",
        f"- Generated: {_now()}",
        f"- Events: {len(rows)}",
        "",
        "## By Model",
        "",
    ]
    for model, count in sorted(by_model.items()):
        lines.append(f"- {model}: {count}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "project": project or "all",
        "event_count": len(rows),
        "by_model": by_model,
        "recent": rows[-10:],
        "storage": str(REASONING_FILE),
        "report_path": str(path),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("mathematical-reasoning-mcp")

    @mcp.tool()
    def mathematical_reasoning_brief() -> str:
        """Describe executable mathematical reasoning models."""
        return _json({
            "name": "mathematical-reasoning-mcp",
            "version": "v6.33",
            "models": [
                "bayesian_update",
                "expected_value",
                "information_gain",
                "dependency_graph",
                "anomaly_detection",
                "monte_carlo_risk",
            ],
            "storage": str(REASONING_FILE),
        })

    @mcp.tool()
    def bayesian_update(project: str, hypothesis: str, prior: float,
                        likelihood_if_true: float, likelihood_if_false: float,
                        evidence: str = "") -> str:
        """Update belief in a hypothesis from evidence likelihoods."""
        return _json(_bayesian(project, hypothesis, prior, likelihood_if_true, likelihood_if_false, evidence))

    @mcp.tool()
    def score_expected_value(project: str, actions_json: str) -> str:
        """Rank actions by value * success_prob + information_gain - cost - risk."""
        return _json(_score_actions(project, _loads(actions_json, [])))

    @mcp.tool()
    def rank_information_gain(project: str, questions_json: str) -> str:
        """Rank questions/tests by uncertainty reduction and decision impact per cost."""
        return _json(_rank_info_gain(project, _loads(questions_json, [])))

    @mcp.tool()
    def build_dependency_graph(project: str, nodes_json: str, edges_json: str = "[]") -> str:
        """Build a dependency graph and report cycles/ready nodes."""
        return _json(_dependency_graph(project, _loads(nodes_json, []), _loads(edges_json, [])))

    @mcp.tool()
    def detect_metric_anomaly(project: str, metric: str, values_json: str,
                              latest_value: float | None = None, z_threshold: float = 2.5) -> str:
        """Detect metric anomaly by z-score against historical values."""
        return _json(_detect_anomaly(project, metric, _loads(values_json, []), latest_value, z_threshold))

    @mcp.tool()
    def simulate_project_risk(project: str, tasks_json: str, runs: int = 1000, seed: int = 42) -> str:
        """Simulate project success probability, duration, and cost."""
        return _json(_simulate_risk(project, _loads(tasks_json, []), runs, seed))

    @mcp.tool()
    def reasoning_report(project: str = "") -> str:
        """Return recent mathematical reasoning events."""
        return _json(_report(project))

    return mcp


def main() -> None:
    build_server().run()
