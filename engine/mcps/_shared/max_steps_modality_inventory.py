# -*- coding: utf-8 -*-
"""Pure helpers for max-steps modality inventory."""
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


MODALITY_ORDER = [
    "image_attachment",
    "audio_transcript",
    "pdf_table_attachment",
    "spreadsheet_or_structured_file",
    "api_truncation_or_fetch",
    "video_web_transcript",
    "web_navigation_research",
    "computation_or_symbolic",
    "unknown",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tools(run: dict) -> Counter:
    counts = Counter()
    for step in run.get("steps", []):
        if step.get("event") == "tool_call":
            counts[step.get("tool", "")] += 1
    return counts


def trace_text(run: dict) -> str:
    chunks = []
    for step in run.get("steps", [])[-8:]:
        chunks.append(str(step.get("content", "")))
        chunks.append(str(step.get("result", "")))
    return "\n".join(chunks).lower()


def question_text(item: dict, run: dict) -> str:
    q = ""
    run_question = run.get("question")
    if isinstance(run_question, dict):
        q = run_question.get("question", "") or ""
    elif isinstance(run_question, str):
        q = run_question
    return f"{q}\n{item.get('question_snippet', '')}".lower()


def file_suffix(run: dict) -> str:
    q = run.get("question") or {}
    fp = ""
    if isinstance(q, dict):
        fp = q.get("file_path") or q.get("file_name") or ""
    return Path(str(fp)).suffix.lower()


def classify(item: dict, run: dict) -> tuple[str, str, str]:
    question = question_text(item, run)
    trace = trace_text(run)
    suffix = file_suffix(run)
    tool_counts = tools(run)
    combined = f"{question}\n{trace}"
    if suffix in {".mp3", ".wav", ".m4a", ".ogg", ".flac"} or "audio recording" in combined or "voice memo" in combined:
        return ("audio_transcript", "Needs local audio transcription before answer extraction.", "Add dry-run-safe local transcription adapter or transcript extraction gate.")
    if any(k in question for k in ("youtube", "video", "two-minute mark", "gamegrumps", "transcript")):
        return ("video_web_transcript", "Needs transcript/video-source lookup and timestamp handling.", "Add transcript-first search pattern and timestamp evidence contract.")
    if "goldfinger" in question or ("film" in question and "what color" in question and "concealed" in question):
        return ("web_navigation_research", "Needs source-pivot web navigation and film-fact lookup rather than image OCR.", "Add a movie-scene fact recipe and source pivot rule; keep it out of image bucket.")
    if suffix in {".xlsx", ".xls", ".csv", ".tsv", ".json", ".jsonld", ".xml", ".zip"} or re.search(r"\b(spreadsheet|xls|xlsx|csv|xml|jsonld|attached spreadsheet)\b", combined):
        return ("spreadsheet_or_structured_file", "Needs structured parser workflow rather than open-ended web search.", "Route file tasks to parser-first plan and run_code verification.")
    if suffix == ".pdf" or re.search(r"\b(the|a|attached|in the) pdf\b", question):
        return ("pdf_table_attachment", "Needs reliable PDF text/table extraction and page-level evidence.", "Add PDF extractor fallback and table-focused recovery prompt.")
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"} or re.search(r"\b(image|photo|picture|visible|color|hand visible|attached pic|look at the attached image)\b", question):
        return ("image_attachment", "Needs visual extraction/OCR/image understanding before reasoning.", "Add image attachment reader/OCR preprocessor in the LangGraph tool layer.")
    if any(k in question for k in ("compute", "integer", "check digit", "rounded", "percentage", "anagram", "final numeric output", "python code")):
        return ("computation_or_symbolic", "Needs deterministic compute path after facts are gathered.", "Force run_code with extracted facts and reject continued search loops.")
    if any(k in combined for k in ("api", "truncated", "incompleteread", "fetch_json", "orcid", "pubchem", "crossref", "arxiv", "wikidata", "cdx", "wayback", "openreview", "usgs", "database")) or tool_counts.get("fetch_json", 0) >= 2:
        return ("api_truncation_or_fetch", "Needs API pagination/chunking/fetch fallback instead of repeating failing calls.", "Add source-specific fetch recipes and truncation-aware continuation.")
    if tool_counts.get("search", 0) + tool_counts.get("web_fetch", 0) >= 5:
        return ("web_navigation_research", "Needs better source selection and stop rules for web navigation.", "Add search-result scoring, source pivot rules, and earlier synthesis.")
    return ("unknown", "Insufficient evidence to select a recovery path.", "Manually inspect trace and assign modality before retry.")


def short(text: str, n: int = 110) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text[: n - 3] + "..." if len(text) > n else text


def inventory_payload(source: str, rows: list[dict]) -> dict:
    counts = Counter(row["modality"] for row in rows)
    levels = defaultdict(Counter)
    for row in rows:
        levels[row["modality"]][str(row.get("level"))] += 1
    return {
        "schema_version": "agent-os-max-steps-modality-inventory/v0.1",
        "generated": now(),
        "source": source,
        "total": len(rows),
        "counts": {k: counts.get(k, 0) for k in MODALITY_ORDER if counts.get(k, 0)},
        "levels_by_modality": {k: dict(levels[k]) for k in MODALITY_ORDER if counts.get(k, 0)},
        "items": rows,
    }


def markdown_report(payload: dict, failure_inventory: str) -> str:
    counts = Counter(payload.get("counts", {}))
    lines = [
        "# Max Steps Modality Inventory v0.1",
        "",
        f"Generated: `{payload['generated']}`",
        f"Source: `{failure_inventory}`",
        "",
        "## Summary",
        "",
        f"- Total max_steps items: `{payload['total']}`",
    ]
    for modality in MODALITY_ORDER:
        if counts.get(modality, 0):
            lines.append(f"- {modality}: `{counts[modality]}`")
    lines += [
        "",
        "## Recovery Order",
        "",
        "1. `image_attachment`: highest leverage if image/OCR failures dominate.",
        "2. `api_truncation_or_fetch`: reduce repeated web/API loops.",
        "3. `pdf_table_attachment` and `spreadsheet_or_structured_file`: parser-first recovery.",
        "4. `audio_transcript` and `video_web_transcript`: transcript-first recovery.",
        "5. `web_navigation_research`: source selection and stop-rule tuning.",
        "",
        "## Items",
        "",
        "| # | Task | L | Reason | Modality | Tool fails | Truth | Next action |",
        "|---:|---|---:|---|---|---:|---|---|",
    ]
    for row in payload.get("items", []):
        truth = short(row["truth"], 55).replace("|", "\\|")
        next_action = short(row["next_action"], 70).replace("|", "\\|")
        lines.append(
            f"| {row['rank']} | `{row['task_id'][:8]}` | {row['level']} | {row['reason']} | "
            f"{row['modality']} | {row['tool_fail_count']} | `{truth}` | {next_action} |"
        )
    lines += [
        "",
        "## Decision",
        "",
        "- This inventory does not justify a 40-question retry yet.",
        "- Build one recovery patch per dominant modality, then run a small targeted sample per bucket.",
    ]
    return "\n".join(lines) + "\n"
