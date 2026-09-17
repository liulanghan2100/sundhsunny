# -*- coding: utf-8 -*-
"""Evaluation Harness MCP server.

v6.7 converts failure cases and acceptance rules into regression eval cases.
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

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
EVAL_DIR = DATA_ROOT / "09_投研" / "evaluation_harness"
CASE_FILE = EVAL_DIR / "eval_cases.jsonl"
RUN_FILE = EVAL_DIR / "eval_runs.jsonl"
FAILURE_FILE = DATA_ROOT / "09_投研" / "failure_replay" / "failures.jsonl"


def _json(data: dict) -> str:
    return shared_json(data)


def _loads(value: str | dict | list | None, default: Any) -> Any:
    return shared_loads(value, default)


def _now() -> str:
    return shared_now()


def _append(path: Path, record: dict) -> dict:
    shared_append_jsonl(path, record)
    return record


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"type": "corrupt_line", "raw": line})
    return rows


def _case_id() -> str:
    return f"evalcase-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def _run_id() -> str:
    return f"evalrun-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def _text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).lower() if isinstance(value, (dict, list)) else str(value).lower()


def _evaluate_case(case: dict, candidate: dict | str) -> dict:
    text = _text(candidate)
    required = case.get("required_terms", [])
    forbidden = case.get("forbidden_terms", [])
    required_hits = [term for term in required if str(term).lower() in text]
    forbidden_hits = [term for term in forbidden if str(term).lower() in text]
    passed = len(required_hits) == len(required) and not forbidden_hits
    return {
        "case_id": case.get("id"),
        "name": case.get("name"),
        "passed": passed,
        "required_hits": required_hits,
        "missing_required": [term for term in required if term not in required_hits],
        "forbidden_hits": forbidden_hits,
        "weight": case.get("weight", 1.0),
    }


def build_server() -> FastMCP:
    mcp = FastMCP("evaluation-harness-mcp")

    @mcp.tool()
    def evaluation_harness_brief() -> str:
        """Describe the evaluation harness."""
        return _json({
            "name": "evaluation-harness-mcp",
            "version": "v6.7",
            "purpose": "把失败样本、验收规则和执行卡要求转成可重复回归评估",
            "storage": {"cases": str(CASE_FILE), "runs": str(RUN_FILE)},
        })

    @mcp.tool()
    def create_eval_case(project: str, name: str, task_pattern: str,
                         required_terms_json: str = "[]", forbidden_terms_json: str = "[]",
                         source: str = "manual", weight: float = 1.0) -> str:
        """Create one deterministic eval case."""
        case = {
            "id": _case_id(),
            "ts": _now(),
            "type": "eval_case",
            "project": project,
            "name": name,
            "task_pattern": task_pattern,
            "required_terms": _loads(required_terms_json, []),
            "forbidden_terms": _loads(forbidden_terms_json, []),
            "source": source,
            "weight": weight,
        }
        _append(CASE_FILE, case)
        return _json({"status": "created", "case": case})

    @mcp.tool()
    def generate_cases_from_failures(project: str = "", limit: int = 20) -> str:
        """Generate regression eval cases from failure replay samples."""
        failures = _read_jsonl(FAILURE_FILE)
        if project:
            failures = [f for f in failures if f.get("project") in {project, "", "global"}]
        created = []
        for failure in failures[:max(1, limit)]:
            required = ["execution card", "historical failure"]
            prevention = failure.get("prevention", "")
            if "避免" in prevention or "avoid" in prevention.lower():
                required.append("avoid")
            forbidden = ["已真实完成", "生产已部署"] if "真实" in failure.get("symptom", "") else []
            case = {
                "id": _case_id(),
                "ts": _now(),
                "type": "eval_case",
                "project": project or failure.get("project", "global"),
                "name": f"regression: {failure.get('symptom', '')[:60]}",
                "task_pattern": failure.get("task", ""),
                "required_terms": required,
                "forbidden_terms": forbidden,
                "source": "failure_replay",
                "source_failure_id": failure.get("id"),
                "weight": 1.5 if failure.get("severity") in {"critical", "high"} else 1.0,
            }
            _append(CASE_FILE, case)
            created.append(case)
        return _json({"status": "generated", "count": len(created), "cases": created})

    @mcp.tool()
    def run_eval_suite(project: str, candidate_json: str, suite: str = "default") -> str:
        """Run eval cases against a candidate execution card/result JSON."""
        candidate = _loads(candidate_json, candidate_json)
        cases = [c for c in _read_jsonl(CASE_FILE) if c.get("project") in {project, "", "global"}]
        results = [_evaluate_case(case, candidate) for case in cases]
        total_weight = sum(float(r.get("weight", 1.0)) for r in results) or 1.0
        passed_weight = sum(float(r.get("weight", 1.0)) for r in results if r["passed"])
        run = {
            "id": _run_id(),
            "ts": _now(),
            "type": "eval_run",
            "project": project,
            "suite": suite,
            "case_count": len(cases),
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
            "score": round(passed_weight / total_weight, 4),
            "results": results,
        }
        _append(RUN_FILE, run)
        return _json(run)

    @mcp.tool()
    def eval_report(project: str = "") -> str:
        """Return evaluation cases and recent run metrics."""
        cases = _read_jsonl(CASE_FILE)
        runs = _read_jsonl(RUN_FILE)
        if project:
            cases = [c for c in cases if c.get("project") in {project, "", "global"}]
            runs = [r for r in runs if r.get("project") == project]
        latest = runs[-1] if runs else None
        return _json({
            "project": project or "all",
            "case_count": len(cases),
            "run_count": len(runs),
            "latest_run": latest,
            "storage": {"cases": str(CASE_FILE), "runs": str(RUN_FILE)},
        })

    return mcp


def main() -> None:
    build_server().run()
