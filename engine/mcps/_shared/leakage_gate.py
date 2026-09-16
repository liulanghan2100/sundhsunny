# -*- coding: utf-8 -*-
"""Pure scanners for GAIA benchmark leakage detection."""
import json
import re


RUNTIME_FILES = {
    "agent_os_gaia_runner.py",
    "agent_os_langgraph_gaia_adapter.py",
    "agent_os_paddleocr_bridge.py",
}

GLOBAL_FORBIDDEN = [
    re.compile(r"def\s+_benchmark_hints_enabled\s*\("),
    re.compile(r"def\s+_api_recovery_hint\s*\("),
    re.compile(r"def\s+_source_specific_hint\s*\("),
    re.compile(r"def\s+_source_candidate_seen\s*\("),
    re.compile(r"AGENT_OS_ALLOW_BENCHMARK_HINTS"),
]

RUNTIME_FORBIDDEN = [
    re.compile(r"source_candidate"),
    re.compile(r"\[SOURCE RECIPE"),
    re.compile(r"visible_hand_count_candidate"),
    re.compile(r"contaminated_replay"),
    re.compile(r"directed_task_hint"),
    re.compile(r"api_recovery_hint|source_specific_hint"),
]

RUNTIME_ANSWER_VALUES = [
    "80GSFC21M0002",
    "101.376, 84.348",
    "Five Hundred Things To Eat",
    "Russian-German Legion",
    "Out of the Silent Planet",
    "The World of the Twenty First Century",
    "Here be dragons",
    "eberzit",
    "Louvrier",
    "visible_hand_count",
    "hand count candidate",
]


def scan_file(path) -> list[str]:
    hits: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"  UNREADABLE: {exc}"]
    lines = text.splitlines()
    name = path.name
    is_runtime = name in RUNTIME_FILES
    rules = list(GLOBAL_FORBIDDEN)
    if is_runtime:
        rules += RUNTIME_FORBIDDEN
    for lineno, line in enumerate(lines, 1):
        for rx in rules:
            if rx.search(line):
                hits.append(f"  {path.name}:{lineno}: {rx.pattern}  ->  {line.strip()[:120]}")
        if is_runtime:
            for value in RUNTIME_ANSWER_VALUES:
                if value.lower() in line.lower():
                    hits.append(f"  {path.name}:{lineno}: hardcoded answer value {value!r}")
    return hits


def scan_evidence(runs_dirs: list) -> list[str]:
    hits: list[str] = []
    markers = (
        "source_candidate:",
        "[SOURCE RECIPE",
        "visible_hand_count_candidate",
        "directed_task_hint",
        "api_recovery_hint",
        "source_specific_hint",
    )
    for runs_dir in runs_dirs:
        if not runs_dir.exists():
            continue
        for run_json in sorted(runs_dir.glob("*/run.json")):
            try:
                data = json.loads(run_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            blob = "\n".join(
                str(step.get("prompt", "")) + "\n" + str(step.get("result", "")) + "\n" + str(step.get("content", ""))
                for step in data.get("steps", [])
            )
            for marker in markers:
                if marker in blob:
                    hits.append(f"  {run_json}: contains {marker!r}")
    return hits


def scan_python_files(scan_dir, gate_filename: str = "agent_os_leakage_gate.py") -> list:
    return [
        path for path in sorted(scan_dir.glob("agent_os*.py"))
        if path.name != gate_filename
    ]


def evidence_runs_dirs(scan_dir) -> list:
    adapter_runs = None
    for research_dir in scan_dir.parent.glob("09_*"):
        candidate = research_dir / "agent_os_langgraph_runtime_adapter" / "runs"
        if candidate.exists():
            adapter_runs = candidate
            break
    runs_dirs = [scan_dir / "runs"]
    if adapter_runs:
        runs_dirs.append(adapter_runs)
    return runs_dirs
