# -*- coding: utf-8 -*-
"""Small pure helpers for the LangGraph GAIA adapter."""
import re
from typing import Pattern


def recent_tool_failures(steps: list[dict], window: int = 4) -> int:
    tool_steps = [s for s in steps if s.get("event") == "tool_call"]
    recent = tool_steps[-window:]
    fail_keys = ("ERROR", "WARNING", "Timeout", "timed out", "failed")
    return sum(1 for s in recent if any(k in str(s.get("result", "")) for k in fail_keys))


def compact_list_answer(question: str, answer: str) -> str:
    q = question.lower()
    if "comma separated list" in q and "no whitespace" in q:
        return re.sub(r"\s+", "", answer)
    return answer


def has_run_code(steps: list) -> bool:
    return any(s.get("event") == "tool_call" and s.get("tool") == "run_code" for s in steps)


def needs_compute(question: str, compute_signal_re: Pattern[str]) -> bool:
    return bool(question and compute_signal_re.search(question))


def search_query_variants(query: str, stopwords: frozenset[str]) -> list:
    """Build 1-2 degraded variants of a failed query."""
    base = query.strip()
    if not base or len(base) < 6:
        return []
    words = re.split(r"\s+", base)
    core = [w for w in words if w.lower() not in stopwords]
    v1 = " ".join(core) if core and core != words else ""
    v1 = v1[:120]
    m = re.match(r"^([A-Za-z][\w\-']*(\s+[A-Za-z][\w\-']*){0,3})", base)
    v2 = '"%s"' % m.group(1) if m else ""
    variants = []
    if v1 and v1 != base:
        variants.append(v1)
    if v2 and v2 != base:
        variants.append(v2)
    return variants[:2]
