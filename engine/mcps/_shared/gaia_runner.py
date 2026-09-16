# -*- coding: utf-8 -*-
"""Pure text/protocol helpers for agent_os_gaia_runner."""
import json
import re
import urllib.parse
from pathlib import Path


_JUNK_TITLE_PAT = (
    r"WebMD|Find a Doctor|Find Doctors|doctor directory|physician directory|"
    r"MD\.com|Search for doctors|doctor ratings|Book Appointments|Doctors Near You"
)
_SEARCH_STOP = {"the", "and", "for", "with", "what", "where", "when", "which",
                "that", "this", "from", "into", "about", "series", "season",
                "episode", "official", "first", "question", "give", "exactly"}
_SERP_NETLOCS = (
    "www.bing.com", "bing.com", "www.google.com", "google.com",
    "html.duckduckgo.com", "duckduckgo.com", "search.yahoo.com",
    "www.baidu.com", "baidu.com",
)

def validate_chat_response(data) -> None:
    """Reject an LLM payload whose shape the callers read, before it can crash
    them outside the retry loop.

    The _chat retry budget covers network/HTTP errors; a 200 with a malformed
    body (top-level list, missing choices, message not an object) would
    otherwise surface as an AttributeError/KeyError in reason_step/solve.
    Raising here makes a bad body retry within budget, then fail fast with a
    bounded error that the caller can persist as api_error.
    """
    if not isinstance(data, dict):
        raise ValueError(f"LLM API returned non-object JSON: {type(data).__name__}")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM API response missing non-empty 'choices' list")
    choice0 = choices[0]
    if not isinstance(choice0, dict) or not isinstance(choice0.get("message"), dict):
        raise ValueError("LLM API response 'choices[0].message' is not an object")
    usage = data.get("usage")
    if usage is not None and not isinstance(usage, dict):
        raise ValueError("LLM API response 'usage' is not an object")


def tool_call_name(tc) -> str:
    """Safely read a tool_call's function name.

    LLM tool_calls are attacker-free here, but a malformed payload (missing
    'function', or 'function' not a dict) must not crash the loop with a
    KeyError; the caller logs and skips such entries instead.
    """
    fn = tc.get("function") if isinstance(tc, dict) else None
    if isinstance(fn, dict):
        name = fn.get("name")
        if isinstance(name, str):
            return name
    return ""


def tool_call_args(tc) -> str:
    fn = tc.get("function") if isinstance(tc, dict) else None
    if isinstance(fn, dict):
        args = fn.get("arguments")
        if isinstance(args, str):
            return args
    return ""


def tool_call_id(tc) -> str:
    tid = tc.get("id") if isinstance(tc, dict) else None
    return tid if isinstance(tid, str) else ""


def is_junk_search(out: str, query: str) -> bool:
    """True when top results are unrelated to the query.

    Either a medical-directory title pattern, or zero overlap between the
    query's significant tokens and the top three results' titles.
    """
    import re

    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip().startswith(("1. ", "2.", "3."))]
    if not lines:
        return False
    if re.search(_JUNK_TITLE_PAT, "\n".join(lines), re.I):
        return True
    tokens = {w for w in re.findall(r"[A-Za-z]{4,}", query.lower()) if w not in _SEARCH_STOP}
    if not tokens:
        return False
    hits = sum(1 for ln in lines if any(t in ln.lower() for t in tokens))
    return hits == 0


def xml_to_text(raw: str) -> str:
    """Strip XML markup down to its visible text content.

    Word-processing XML (w:wordDocument / docx) is dominated by namespace and
    style boilerplate; keeping only text nodes shrinks it by orders of
    magnitude so the model can actually read the semantic content (e.g. the
    CATEGORIES entries). One element per line preserves row/cell separation.
    """
    import re

    text = re.sub(r"<\?xml[\s\S]*?\?>", "", raw)
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    text = re.sub(r">\s*<", ">\n<", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def read_docx_stdlib_text(fp: Path) -> str:
    """Extract .docx text via zipfile + ElementTree only."""
    import xml.etree.ElementTree as ET
    import zipfile

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


def read_zip_text(fp: Path, xml_to_text_fn=xml_to_text) -> str:
    """Extract readable members from a zip attachment."""
    import io
    import zipfile

    text_parts = []
    with zipfile.ZipFile(str(fp)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            suffix = Path(name).suffix.lower()
            if suffix in {".xml", ".html", ".htm"}:
                text = xml_to_text_fn(zf.read(info).decode("utf-8", errors="replace"))
                if len(text) > 8000:
                    text = text[:8000] + "\n[TRUNCATED]"
                text_parts.append(f"--- {name} ---\n{text}")
            elif suffix in {".csv", ".txt", ".md", ".json", ".jsonld"}:
                raw = zf.read(info)
                text = raw.decode("utf-8", errors="replace")
                if len(text) > 8000:
                    text = text[:8000] + "\n[TRUNCATED]"
                text_parts.append(f"--- {name} ---\n{text}")
            elif suffix in {".xlsx", ".xls", ".ods"}:
                try:
                    import pandas as pd
                    sheets = pd.read_excel(io.BytesIO(zf.read(info)), sheet_name=None)
                    parts = []
                    for sheet_name, df in sheets.items():
                        parts.append(f"--- sheet: {sheet_name} ({len(df)} rows) ---\n" + df.to_csv(index=False))
                    blob = "\n".join(parts)
                    if len(blob) > 4000:
                        blob = blob[:4000] + "\n[TRUNCATED]"
                    text_parts.append(f"--- {name} ---\n{blob}")
                except Exception as exc:
                    text_parts.append(f"--- {name} ---\nERROR: could not parse spreadsheet: {exc}")
            else:
                text_parts.append(f"--- {name} --- (binary member, skipped)")
    if not text_parts:
        return "ERROR: zip contains no readable members."
    return "\n\n".join(text_parts)


def is_serp_url(url: str) -> bool:
    """True if the URL is a search-engine results page (SERP).

    P1 tool discipline: fetching SERPs wastes steps and is always better done
    via the search tool (which returns clean titles/URLs/snippets). Blocked
    before any network I/O.
    """
    p = urllib.parse.urlparse(url)
    if p.netloc.lower() not in _SERP_NETLOCS:
        return False
    path = p.path.lower()
    return path.startswith("/search") or path.startswith("/html")


def action_signature(name: str, args: dict) -> str:
    """Normalize a tool action into a repeat-detection signature.

    - web_fetch: scheme://netloc + path, dropping the query, so that re-fetching
      the same endpoint with only different query params counts as the same
      action (this was the exact loop pattern in the ORCID question).
    - read_attachment: the resolved path itself.
    """
    if name == "web_fetch":
        url = str(args.get("url") or "")
        p = urllib.parse.urlparse(url)
        return f"web_fetch|{p.scheme}://{p.netloc}{p.path}".lower()
    if name == "read_attachment":
        return f"read_attachment|{str(args.get('path') or '').lower().replace(chr(92), '/')}"
    if name == "search":
        return f"search|{str(args.get('query') or '').strip().lower()}"
    if name == "fetch_json":
        # Normalize param order so identical API queries in different param
        # order still count as the same repeat action.
        url = str(args.get("url") or "")
        p = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qsl(p.query)
        qs = urllib.parse.urlencode(sorted(q))
        return f"fetch_json|{p.scheme}://{p.netloc}{p.path}?{qs}".lower()
    if name == "run_code":
        return f"run_code|{str(args.get('code') or '')}"
    return f"{name}|{json.dumps(args, sort_keys=True)}"


def extract_answer_from_text(text: str) -> str:
    """Best-effort conclusion extraction.

    Used only as a loop bail-out when the model keeps emitting long analysis
    without a FINAL ANSWER marker. Prefers an explicit conclusion phrase, then
    falls back to the last sentence.
    """
    import re

    text = text.strip()
    if not text:
        return ""
    patterns = [
        r"final answer\s*[:：]?\s*(.+)",
        r"(?:the |so )?answer (?:is|should be)\s*[:：]?\s*(.+)",
        r"therefore[,\s]+(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            cand = m.group(1).strip().strip("\"'`").strip()
            if cand:
                return cand
    sentences = [s.strip() for s in re.split(r"[.!?]\s+|\n+", text) if s.strip()]
    return sentences[-1] if sentences else text


def clean_answer(text: str) -> str:
    """Reduce an extracted answer to its bare value (P0 answer contract).

    Strips markdown formatting and leading filler ('The answer is ...') so the
    exact-match grader receives the value itself, not a prose shell around it.
    Whitespace is collapsed because the grader normalizes the same way.
    """
    import re
    text = (text or "").strip()
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"^(the\s+)?(final\s+)?answer\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(the\s+)?answer\s+(is|should\s+be)\s+", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def is_protocol_artifact(text: str) -> bool:
    """True if the model replied with tool-protocol markup instead of an answer.

    Observed in the 2026-08-05 smoke: under forced submission the model
    sometimes emits a hallucinated closing tag. The real bytes were
    "</‖‖DSML‖‖tool_calls>" (full-width bars U+FF5C, DeepSeek's own
    tool-call marker), which ASCII-based checks missed. Angle brackets and
    the "dsml" marker are never legit bare answers on GAIA.
    """
    t = (text or "").strip().lower()
    if not t:
        return True
    if any(a in t for a in ("dsml", "\uff5c", "<", ">")):
        return True
    return t in {"tool_calls", "tool call"}


