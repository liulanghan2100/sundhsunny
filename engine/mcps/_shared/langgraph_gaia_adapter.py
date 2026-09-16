# -*- coding: utf-8 -*-
"""Pure answer/recovery helpers for the LangGraph GAIA adapter."""
import json
import re
import urllib.parse

from _shared.gaia_answer import (
    DATE_RE,
    YEAR_RE,
    _is_junk_answer,
    _looks_like_prose,
    _normalize_listish_answer,
    _strip_answer_noise,
)
from _shared.gaia_runner import (
    clean_answer,
    extract_answer_from_text,
    is_protocol_artifact,
)
from _shared.gaia_small_helpers import (
    compact_list_answer,
    has_run_code,
    needs_compute,
    recent_tool_failures,
)

LONG_ANALYSIS_THRESHOLD = 800
EVIDENCE_RESULT_HEADERS = ("ocr_result", "layout_result", "vision_result", "image_meta")
EVIDENCE_FIELD_PREFIXES = (
    "engine:", "status:", "source_path:", "language:", "text:",
    "blocks:", "color_grid:", "normalized_lines:",
    "spatial_problem_rows:", "answer_extraction_candidates:",
)

def finalize_answer(text: str) -> str:
    """Clean and verify a candidate final answer before writeout."""
    raw_lower = (text or "").strip().lower()
    if raw_lower in {"# row", "row", "moves =", "likely a small number."}:
        return ""
    if raw_lower.startswith(EVIDENCE_FIELD_PREFIXES):
        return ""
    if raw_lower.startswith((
        "arxiv_list_summary",
        "arxiv_atom_summary",
        *EVIDENCE_RESULT_HEADERS,
    )):
        return ""
    if any(raw_lower.startswith(prefix) for prefix in (
        "i need ", "need to ", "unable to ", "cannot answer",
        "the attachment is ", "this is not ", "i cannot ", "cannot access ",
        "i'll look ", "i will look ", "let me try ", "let me check ",
    )):
        return ""
    if any(phrase in raw_lower for phrase in (
        "search tool is failing",
        "let me",
        "try to",
        "trying to",
        "i need to see",
        "i'll try",
        "i will try",
        "i can try",
        "failing.",
        "local files in sandbox",
        "cannot access local",
        "can't access",
        "i'll look",
        "let me look",
    )):
        return ""
    t = _strip_answer_noise(text)
    if _is_junk_answer(t):
        return ""
    if re.match(r"^\d+\.\s+\S|^\d+\)\s*\S", t):
        return ""
    if not t or is_protocol_artifact(t):
        return ""
    if t.lower().startswith(("likely ", "probably ", "maybe ", "let me ", "i think ", "wait,")):
        return ""
    if len(t) > LONG_ANALYSIS_THRESHOLD or _looks_like_prose(t):
        original = t
        extracted = _clean_answer(_extract_answer_from_text(t))
        extracted = _strip_answer_noise(extracted)
        if extracted and not _is_protocol_artifact(extracted):
            t = extracted
        # Prose fallback: the model often names the literal value inside
        # quotes while reasoning (e.g. "the removed joke was '<value>'"). A
        # short quoted phrase beats the surrounding sentence shell as the
        # bare-value candidate. Search the ORIGINAL text (the extracted
        # sentence may have dropped the quoted phrase).
        qm = re.search(r"['\"]([^'\"]{1,60})['\"]", original)
        if qm and not _is_junk_answer(qm.group(1)) and not _looks_like_prose(qm.group(1)):
            t = qm.group(1)
    if DATE_RE.search(t):
        date = DATE_RE.search(t).group(0)
        if len(t) > len(date) or _looks_like_prose(t):
            t = date
        if DATE_RE.fullmatch(t):
            return t
    if YEAR_RE.search(t) and any(h in t.lower() for h in ("year", "date", "latest")):
        t = YEAR_RE.search(t).group(0)
    t = _normalize_listish_answer(t)
    t = re.sub(r"\s+", " ", t).strip(" ,;:-")
    if not t or is_protocol_artifact(t):
        return ""
    if _is_junk_answer(t):
        return ""
    return t


def best_history_answer(messages: list[dict]) -> str:
    """Recover an answer-like history item, preferring explicit FINAL ANSWER."""
    best = ""
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if "FINAL ANSWER:" in content:
            cand = content.split("FINAL ANSWER:", 1)[1]
            cand = finalize_answer(cand)
            if cand:
                return cand
        cand = finalize_answer(content)
        if cand and not _looks_like_prose(content):
            best = cand
    return best


def last_tool_result_candidate(steps: list[dict]) -> str:
    """Extract a short answer-like candidate from recent tool output."""
    for step in reversed(steps or []):
        if step.get("event") != "tool_call":
            continue
        result = str(step.get("result", "")).strip()
        if not result or result.startswith(("ERROR", "WARNING", "BLOCKED")):
            continue
        if result.lower().startswith(EVIDENCE_RESULT_HEADERS):
            continue
        lines = [ln.strip(" -\t") for ln in result.splitlines() if ln.strip()]
        for line in lines[-8:]:
            if len(line) > 120 or line.lower().startswith(("http", "www.", "error", "warning")):
                continue
            if line.lower().startswith(EVIDENCE_FIELD_PREFIXES):
                continue
            if any(bad in line.lower() for bad in (
                "cannot access",
                "can't access",
                "sandbox",
                "tool failed",
                "attachment is binary",
                "arxiv.org e-print archive",
                "total_results=",
                "total_entries=",
                "entries_returned=",
                "entries_seen=",
                "formats=",
                "ps_or_other_markers=",
                "arxiv_list_summary",
                "arxiv_atom_summary",
                "image_meta",
                "ocr_result",
                "layout_result",
                "vision_result",
                "note: arxiv list pages",
            )):
                continue
            if re.match(r"^\d+\.\s+\S|^\d+\)\s*\S", line):
                continue
            cand = finalize_answer(line)
            if cand and not _looks_like_prose(line):
                return cand
    return ""


def visual_evidence_candidate(state: dict) -> str:
    """Prefer deterministic candidates emitted by OCR/layout evidence."""
    question = str((state.get("question") or {}).get("question") or "").lower()
    blobs = []
    for msg in reversed(state.get("messages", []) or []):
        if msg.get("role") == "tool":
            blobs.append(str(msg.get("content", "")).strip())
    for step in reversed(state.get("steps", []) or []):
        if step.get("event") == "tool_call":
            blobs.append(str(step.get("result", "")).strip())
    for result in blobs:
        if "answer_extraction_candidates:" not in result:
            continue
        try:
            payload_text = result.split("answer_extraction_candidates:", 1)[1]
            start = payload_text.find("{")
            if start < 0:
                continue
            depth = 0
            end = -1
            for idx, ch in enumerate(payload_text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = idx + 1
                        break
            payload = json.loads(payload_text[start:end]) if end > start else {}
        except Exception:
            continue
        worksheet = payload.get("worksheet_answer_candidates") or {}
        quiz = payload.get("quiz_grading_candidates") or {}
        if "comma separated list" in question and isinstance(worksheet, dict):
            candidate = str(worksheet.get("ordered_list_candidate") or "").strip()
            if candidate:
                return finalize_answer(candidate)
        if ("how many points" in question or "how many points would the student have earned" in question) and isinstance(quiz, dict):
            candidate = quiz.get("total_with_bonus_candidate")
            if candidate is not None:
                return finalize_answer(str(candidate))
    return ""


def recovery_candidate(state: dict) -> str:
    return (
        visual_evidence_candidate(state)
        or
        finalize_answer(state.get("last_content", ""))
        or best_history_answer(state.get("messages", []))
        or last_tool_result_candidate(state.get("steps", []))
    )


def recovery_candidate_source(state: dict, candidate: str) -> str:
    if not candidate:
        return ""
    if visual_evidence_candidate(state) == candidate:
        return "visual_evidence"
    if finalize_answer(state.get("last_content", "")) == candidate:
        return "last_content"
    if best_history_answer(state.get("messages", [])) == candidate:
        return "message_history"
    if last_tool_result_candidate(state.get("steps", [])) == candidate:
        return "tool_result"
    return "unknown"


def recover_answer_from_history(messages: list[dict]) -> str:
    """P4: recover a FINAL ANSWER the model already produced inside the loop.

    When the step budget runs out the runner's _forced_submit fires one more
    API call, but (a) it can fail/return artifact -> blank answer, and (b) it
    is skipped entirely when the token budget is nearly exhausted. Before
    giving up, scan the transcript: the model often DID emit a clean
    FINAL ANSWER earlier but kept looping on tool calls. Take the FIRST such
    explicit marker only.

    Deliberately NO fuzzy fallback: acceptance run showed that extracting a
    "last non-empty assistant reply" recovers the model's mid-loop rambling
    ("Let me try to find...") as the answer, which scored 0/9 matched (0%
    quality < 50% gate). Only an explicit FINAL ANSWER marker is trustworthy.
    Returns "" when nothing recoverable.
    """
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content") or ""
        if "FINAL ANSWER:" in content:
            cand = finalize_answer(content.split("FINAL ANSWER:", 1)[1])
            if cand and not _is_protocol_artifact(cand):
                return cand
        cand = finalize_answer(content)
        if cand and len(cand) <= 80 and not _looks_like_prose(content) and not _is_protocol_artifact(cand):
            return cand
    return ""


# -*- coding: utf-8 -*-
"""Pure local document parsing helpers for the LangGraph GAIA adapter."""
import re
from pathlib import Path

FETCH_MAX_CHARS = 8000

def extract_pdf_text(raw: bytes, max_chars: int = FETCH_MAX_CHARS) -> str:
    """Extract text from raw PDF bytes (pypdf, fallback to a minimal stdlib
    FlateDecode pass). Returns '' if no extractable text (scanned/image PDF)."""
    import re as _re

    try:
        import pypdf
        reader = pypdf.PdfReader(__import__("io").BytesIO(raw))
        parts = []
        for page in reader.pages[:20]:
            try:
                t = (page.extract_text() or "").strip()
            except Exception:
                t = ""
            if t:
                parts.append(t)
        text = "\n".join(parts).strip()
        if text:
            return (text[:max_chars] + "\n[TRUNCATED]") if len(text) > max_chars else text
    except Exception:
        pass
    # Minimal stdlib fallback: pull decompressed streams and strip PDF syntax.
    try:
        import zlib

        chunks = []
        for m in _re.finditer(rb"stream(?:\r?\n)?(.*?)(?:\r?\n)?endstream", raw, _re.S):
            data = m.group(1)
            try:
                data = zlib.decompress(data)
            except Exception:
                continue
            try:
                text = data.decode("utf-8", errors="replace")
            except Exception:
                continue
            # Keep only streams that look like text, not binary blobs (images,
            # fonts). Ratio of printable/whitespace chars >= 0.9 wins.
            printable = sum(1 for ch in text if ch.isprintable() or ch.isspace())
            if not text or printable < 0.9 * len(text):
                continue
            if "\x00" in text:
                continue
            chunks.append(text)
        text = "\n".join(chunks).strip()
        if text:
            return (text[:max_chars] + "\n[TRUNCATED]") if len(text) > max_chars else text
    except Exception:
        pass
    return ""


def read_docx_stdlib(fp: Path) -> str:
    """Extract .docx text via the stdlib (zipfile + elementtree), no python-docx."""
    import zipfile
    import xml.etree.ElementTree as ET

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(str(fp)) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    parts = []
    for para in root.iter(ns + "p"):
        line = "".join(t.text or "" for t in para.iter(ns + "t")).strip()
        if line:
            parts.append(line)
    for table in root.iter(ns + "tbl"):
        rows = []
        for tr in table.iter(ns + "tr"):
            cells = []
            for tc in tr.iter(ns + "tc"):
                cell = " ".join(
                    "".join(t.text or "" for t in p.iter(ns + "t"))
                    for p in tc.iter(ns + "p")
                ).strip()
                cells.append(cell)
            rows.append(" | ".join(cells))
        if rows:
            parts.append("\n".join(rows))
    text = "\n".join(parts)
    return (text[:4000] + "\n[TRUNCATED]") if len(text) > 4000 else text


def image_meta_lines(
    *,
    width: int,
    height: int,
    average_rgb: tuple[int, int, int],
    brightness: float,
    sample_points: dict[str, tuple[int, int, int]],
    dominant_pixels: list[tuple[tuple[int, int, int], int]],
    center_crop_pixels: list[tuple[int, int, int]] | None = None,
) -> list[str]:
    """Format image metadata lines from precomputed local pixel values."""
    lines = [
        f"IMAGE_META size={width}x{height} mode=RGB",
        f"IMAGE_META average_rgb={average_rgb[0]},{average_rgb[1]},{average_rgb[2]} brightness={brightness:.1f}",
        "IMAGE_META sample_points="
        + ", ".join(f"{k}={v[0]},{v[1]},{v[2]}" for k, v in sample_points.items()),
        "IMAGE_META dominant_pixels="
        + "; ".join(f"{px[0]},{px[1]},{px[2]} x{count}" for px, count in dominant_pixels[:5]),
    ]
    if center_crop_pixels:
        lines.append(
            "IMAGE_META center_crop="
            + "; ".join(f"{px[0]},{px[1]},{px[2]}" for px in center_crop_pixels[:16])
        )
    return lines


def is_http_url(url: str) -> bool:
    return str(url or "").startswith(("http://", "https://"))


def append_query_params(url: str, params=None) -> str:
    if not params:
        return url
    return url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)


def normalize_arxiv_listing_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not (parsed.netloc.lower().endswith("arxiv.org") and parsed.path.startswith("/list/")):
        return url
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("show", [""])[0] in {"100", "250", "500", "1000", "2000"}:
        return url
    query["show"] = ["2000"]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))


def is_pdf_bytes(raw: bytes) -> bool:
    return bool(raw and raw.lstrip().startswith(b"%PDF"))


def html_to_text(raw_text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw_text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def truncate_text(text: str, max_chars: int = 8000) -> str:
    return (text[:max_chars] + "\n[TRUNCATED]") if len(text) > max_chars else text


def format_http_error(code: int, reason: str, detail: str) -> bytes:
    return f"HTTP_ERROR {code}: {reason} {detail}".encode("utf-8", errors="replace")


def build_step_reminder(remaining: int) -> str:
    if remaining <= 2:
        return f"[URGENT: {remaining} step(s) left. STOP researching. If you can answer at all, reply immediately with your best answer: FINAL ANSWER: <value>. No tool calls, no analysis, no prose.]"
    if remaining <= 4:
        return (
            f"[Steps left: {remaining}. Converge now: stop exploring new sources. "
            "Synthesize what you already have and get ready to submit FINAL ANSWER: <value>.]"
        )
    return f"[Steps left: {remaining}. You must converge soon.]"


def classify_recovery_candidate(
    state: dict,
    *,
    remaining: int,
    max_step_recovery_prompt: str,
) -> dict:
    question = str((state.get("question") or {}).get("question") or "").lower()
    visual_candidate = visual_evidence_candidate(state)
    if visual_candidate and ("comma separated list" in question or "how many points" in question):
        compact = compact_list_answer(question, visual_candidate)
        return {
            "kind": "visual_submit",
            "event": {"event": "visual_candidate", "answer": compact[:200]},
            "final_answer": compact,
        }
    if remaining <= 2:
        candidate = recovery_candidate(state)
        if candidate:
            source = recovery_candidate_source(state, candidate)
            if source in ("tool_result", "last_content") and remaining == 2:
                return {
                    "kind": "prompt",
                    "event": {"event": "max_step_recovery_prompt", "remaining": remaining, "candidate_source": source},
                    "reminder": max_step_recovery_prompt,
                }
            return {
                "kind": "direct_submit",
                "event": {"event": "max_step_recovery", "answer": candidate[:200], "remaining": remaining, "candidate_source": source},
                "final_answer": candidate,
            }
        return {
            "kind": "prompt",
            "event": {"event": "max_step_recovery_prompt", "remaining": remaining, "candidate_source": ""},
            "reminder": max_step_recovery_prompt,
        }
    if remaining <= 4:
        return {
            "kind": "prompt",
            "event": None,
            "reminder": build_step_reminder(remaining),
        }
    return {
        "kind": "continue",
        "reminder": build_step_reminder(remaining),
    }


def should_inject_compute_hint(state: dict, compute_signal_re) -> bool:
    return (
        state.get("step", 0) <= 2
        and not state.get("compute_hint_injected")
        and not has_run_code(state.get("steps", []))
        and needs_compute(state.get("question", {}).get("question", ""), compute_signal_re)
    )


def parse_tool_call_payload(tc) -> dict:
    fn = tc.get("function") if isinstance(tc, dict) else None
    name = ""
    args = ""
    if isinstance(fn, dict):
        raw_name = fn.get("name")
        if isinstance(raw_name, str):
            name = raw_name
        raw_args = fn.get("arguments")
        if isinstance(raw_args, str):
            args = raw_args
    tid = tc.get("id") if isinstance(tc, dict) else None
    return {"name": name, "id": tid if isinstance(tid, str) else "", "args": args}


def classify_tool_action(name: str, sig: str, repeat: int, block_tools: bool) -> dict:
    if block_tools:
        return {
            "kind": "blocked",
            "result": (
                "BLOCKED: tool call suppressed by max-step recovery. "
                "Stop using tools and reply with FINAL ANSWER using existing evidence."
            ),
        }
    if repeat >= 1:
        return {
            "kind": "repeat_warning",
            "result": (
                f"WARNING: you already performed this exact action ({sig}). "
                "Its result will not change. Choose a different action, a "
                "different source, or reply FINAL ANSWER."
            ),
        }
    return {"kind": "execute"}


def build_web_fetch_domain_note(netloc: str, count: int) -> str:
    return (
        f"\n[NOTE: you have fetched {netloc} {count} times. "
        "If the results are not helpful, try another site.]"
    )


def build_model_call_record(step: int, content: str, tool_calls: list, tokens_total: int) -> dict:
    return {
        "step": step,
        "event": "model_call",
        "content": content[:500],
        "tool_calls": tool_calls,
        "tokens_total": tokens_total,
    }


def parse_reason_step_response(resp: dict, previous_tokens: int) -> dict:
    usage = resp.get("usage") or {}
    try:
        total_tokens = int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError):
        total_tokens = 0
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content") or ""
    tool_calls = msg.get("tool_calls") or []
    return {
        "tokens_used": max(previous_tokens, total_tokens),
        "message": msg,
        "content": content,
        "tool_calls": tool_calls,
    }


def build_api_error_record(step: int, exc: Exception, event: str = "api_error") -> dict:
    return {"step": step, "event": event, "error": str(exc)}


def classify_step_gate_state(
    state: dict,
    max_tokens_budget: int,
    wall_clock_guard_s: dict,
    wall_clock_guard_default: int,
    elapsed_s: float,
) -> dict:
    step = state.get("step", 0) + 1
    tokens_used = state.get("tokens_used", 0)
    if tokens_used > max_tokens_budget:
        return {"kind": "budget_exceeded", "step": step, "status": "budget_exceeded"}
    level = (state.get("question") or {}).get("level")
    guard_s = wall_clock_guard_s.get(level, wall_clock_guard_default)
    if elapsed_s >= guard_s:
        return {
            "kind": "wall_clock_forced_submit",
            "step": step,
            "status": "wall_clock_guard",
            "elapsed_s": round(elapsed_s, 1),
            "guard_s": guard_s,
        }
    if step > state.get("max_steps", 0):
        return {"kind": "forced_submit", "step": step, "status": "max_steps_reached"}
    return {"kind": "continue", "step": step, "status": state.get("status", "solving"), "remaining": state.get("max_steps", 0) - step + 1}


def parse_tool_args(raw_args: str) -> dict:
    try:
        return json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        return {}


def should_block_tools(remaining: int, recent_failures: int, threshold: int = 4) -> bool:
    return remaining <= 1 or recent_failures >= threshold


def build_tool_malformed_record(step: int, tool_call) -> dict:
    return {"step": step, "event": "tool_call_malformed", "tool_call": str(tool_call)[:200]}


def build_tool_blocked_record(step: int, name: str, args: dict, remaining: int, recent_failures: int) -> dict:
    return {
        "step": step,
        "event": "tool_blocked_near_deadline",
        "tool": name,
        "args": args,
        "remaining": remaining,
        "recent_tool_failures": recent_failures,
    }


def build_tool_call_record(step: int, name: str, args: dict, result: str) -> dict:
    return {"step": step, "event": "tool_call", "tool": name, "args": args, "result": result[:500]}


def build_tool_message(tool_call_id: str, result: str) -> dict:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": result}


def parse_web_fetch_netloc(url: str) -> str:
    return urllib.parse.urlparse(str(url or "")).netloc.lower()


def execution_mode_from_state(state: dict, default: str) -> str:
    mode = state.get("execution_mode")
    return mode if isinstance(mode, str) and mode else default


def is_validation_mode(mode: str) -> bool:
    return mode in {"validation_only", "validation_stub"}


def is_controlled_dry_run_mode(mode: str) -> bool:
    return mode == "controlled_dry_run"


def validate_run_dir_allowed(run_dir: str, allowed_root: str) -> bool:
    if not run_dir:
        return False
    try:
        return str(Path(run_dir).resolve()).startswith(str(Path(allowed_root).resolve()))
    except Exception:
        return False


def build_boundary_block_result(boundary: str, mode: str, tool: str | None = None, reason: str = "") -> str:
    tool_part = f" tool={tool}" if tool else ""
    return f"BLOCKED_BY_EXECUTION_BOUNDARY: {boundary} mode={mode}{tool_part} reason={reason}"


def build_write_evidence_guard(path: str, allowed_root: str, schema: dict) -> dict:
    try:
        resolved = Path(path).resolve()
        allowed = Path(allowed_root).resolve()
    except Exception as exc:
        return {"allowed": False, "reason": f"path_resolution_failed: {exc}"}
    if not str(resolved).startswith(str(allowed)):
        return {"allowed": False, "reason": "path_outside_allowlist"}
    required = ["schema_version", "task_id", "status", "runtime", "provider_id", "steps", "evidence_path"]
    missing = [key for key in required if key not in schema]
    if missing:
        return {"allowed": False, "reason": f"schema_missing:{','.join(missing)}"}
    return {"allowed": True, "reason": "ok"}


def normalize_solve_task_input(task: dict) -> dict:
    task_id = task.get("task_id")
    if task_id:
        return {"kind": "gaia", "task_id": task_id}
    goal = (task.get("goal") or "").strip()
    if not goal:
        raise ValueError("solve_task requires 'task_id' or 'goal'")
    import hashlib
    task_id = f"generic-{hashlib.md5(goal.encode('utf-8')).hexdigest()[:10]}"
    question = {
        "task_id": task_id,
        "question": goal,
        "level": int(task.get("level") or 1),
        "file_path": (task.get("context") or {}).get("attachment", ""),
    }
    constraints = task.get("constraints") or []
    if constraints:
        question["question"] += "\n\n[Constraints]\n" + "\n".join(f"- {c}" for c in constraints)
    return {
        "kind": "generic",
        "task_id": task_id,
        "question": question,
        "goal": goal,
        "skills": list(task["skills"]) if task.get("skills") else [],
        "auto_route": bool(task.get("auto_route")),
        "max_steps": task.get("max_steps"),
        "run_dir": str(Path(task["run_dir"])) if task.get("run_dir") else "",
    }


