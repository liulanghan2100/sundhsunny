# -*- coding: utf-8 -*-
"""Pure web/API response summarizers for the LangGraph GAIA adapter."""
import json
import re

_PUBCHEM_KEY_SECTION_RE = re.compile(
    r"(food|additive|classification|interaction|interactions|toxicity|toxicology|safety|metabolism|pharmacology)",
    re.IGNORECASE,
)

def _pugview_value_text(v) -> str:
    """Pull the human-readable string out of a pug_view Value dict. Returns ''
    for pure-structure values (Boolean toggles, empty containers) that would
    only waste the fetch budget."""
    if not isinstance(v, dict):
        return str(v) if v else ""
    for key in ("StringWithMarkup", "String", "Number", "Date", "ExternalTableName"):
        if v.get(key):
            val = v[key]
            if isinstance(val, list):
                parts = []
                for item in val:
                    if isinstance(item, dict) and item.get("String"):
                        parts.append(item["String"])
                    elif isinstance(item, (str, int, float)):
                        parts.append(str(item))
                if parts:
                    return " ".join(parts)
            elif isinstance(val, (str, int, float)):
                return str(val)
    if v.get("Boolean"):
        return ""
    return ""

def _summarize_arxiv_atom(raw: str) -> str:
    """Compress arXiv Atom API XML so the model sees all entries, not a truncation."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(raw)
    except Exception:
        return ""
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    }
    total = root.findtext("opensearch:totalResults", default="", namespaces=ns)
    entries = root.findall("atom:entry", ns)
    if not entries:
        return ""
    lines = [f"ARXIV_ATOM_SUMMARY total_results={total or '?'} entries_returned={len(entries)}"]
    for i, entry in enumerate(entries, 1):
        arxiv_id = (entry.findtext("atom:id", default="", namespaces=ns).rsplit("/", 1)[-1])
        title = re.sub(r"\s+", " ", entry.findtext("atom:title", default="", namespaces=ns)).strip()
        formats = []
        for link in entry.findall("atom:link", ns):
            label = link.get("title") or link.get("type") or link.get("rel") or ""
            if label:
                formats.append(label)
        lines.append(f"{i}. {arxiv_id} formats={','.join(sorted(set(formats))) or '-'} title={title[:120]}")
    return "\n".join(lines)

def _summarize_arxiv_listing(text: str) -> str:
    """Compress arXiv list pages and preserve entry format markers."""
    if "arxiv:" not in text.lower() or "high energy physics" not in text.lower():
        return ""
    total = ""
    m = re.search(r"Total of\s+(\d+)\s+entries", text, re.IGNORECASE)
    if m:
        total = m.group(1)
    pattern = re.compile(
        r"(\[\d+\]\s+arXiv:[^\s]+)\s+\[\s*([^\]]+?)\s*\]\s+Title:\s+(.+?)(?=\s+\[\d+\]\s+arXiv:|\Z)",
        re.IGNORECASE | re.S,
    )
    entries = []
    for ident, formats, title_blob in pattern.findall(text):
        title = re.sub(r"\s+", " ", title_blob).strip()
        title = re.split(r"\s+(?:Authors?|Comments?|Journal-ref|Subjects?):", title)[0].strip()
        entries.append((ident, re.sub(r"\s+", " ", formats).strip(), title[:120]))
    if not entries:
        return ""
    ps_like = sum(1 for _, formats, _ in entries if "ps" in formats.lower() or "other" in formats.lower())
    lines = [
        f"ARXIV_LIST_SUMMARY total_entries={total or '?'} entries_seen={len(entries)} ps_or_other_markers={ps_like}",
        "Note: arXiv list pages use 'other' for additional formats; inspect /format/<id> pages only if exact PS availability is required.",
    ]
    for i, (ident, formats, title) in enumerate(entries, 1):
        lines.append(f"{i}. {ident} formats=[{formats}] title={title}")
    return "\n".join(lines)

def _summarize_ecfr_results(raw: str, fetch_max_chars: int) -> str:
    """Compress an eCFR search API response into per-section one-liners.

    The eCFR search endpoint returns every historical version of a section as
    its own record with starts_on/ends_on. ends_on non-null marks a section
    that has been superseded/removed since — exactly the 'superseded by a new
    version' signal the model needs for CFR-standards questions. Raw JSON is
    large and repeats headings; this keeps only the useful fields.
    """
    try:
        d = json.loads(raw)
    except Exception:
        return ""
    results = d.get("results") or []
    if not results:
        return ""
    lines = [f"ECFR_SEARCH_SUMMARY results={len(results)}"]
    for x in results:
        h = x.get("hierarchy") or {}
        part = h.get("part")
        sec = h.get("section")
        subp = h.get("subpart")
        if x.get("removed"):
            status = "removed"
        elif x.get("ends_on"):
            status = "superseded"
        else:
            status = "current"
        lines.append(
            f"{part or '?'}.{sec or '?'} subpart={subp or '-'} status={status} "
            f"ends={str(x.get('ends_on'))[:10] or '-'} | "
            f"{(x.get('headline') or '')[:80]} | {(x.get('snippet') or '')[:70]}")
    out = "\n".join(lines)
    return (out[:fetch_max_chars] + "\n[TRUNCATED]") if len(out) > fetch_max_chars else out

def _summarize_pubchem_pugview(raw: str, fetch_max_chars: int) -> str:
    """Compress a PubChem pug_view Record (often 1-35 MB) into its TOC heading
    tree + short information values.

    Raw pug_view JSON dwarfs the 8000-char fetch cap, so without compression
    the model only ever sees the opening JSON noise (Record metadata) and never
    the classification / interactions sections it actually needs. The full
    heading tree is kept verbatim (so the model can re-query a specific heading
    via ?heading=); information values are only rendered for key sections
    (food-additive/classification/interactions/toxicity/...), which keeps the
    budget for what answers the question.
    """
    try:
        d = json.loads(raw)
    except Exception:
        return ""
    rec = d.get("Record") or {}
    lines = [f"PUBCHEM_PUGVIEW cid={rec.get('RecordNumber', '')} "
             f"title={rec.get('RecordTitle', '')}"]
    budget = fetch_max_chars

    def walk(section, depth):
        nonlocal budget
        if budget <= 0:
            return
        name = (section.get("TOCHeading") or "").strip()
        is_key = bool(_PUBCHEM_KEY_SECTION_RE.search(name))
        if name:
            budget -= len(name) + 2 + 2 * depth
            lines.append("  " * depth + "## " + name)
        if is_key:
            for info in section.get("Information", []) or []:
                s = re.sub(r"\s+", " ", _pugview_value_text(info.get("Value", {}))).strip()
                if len(s) > 160:
                    s = s[:160] + "..."
                if s:
                    budget -= len(s) + 4 + 2 * depth
                    lines.append("  " * (depth + 1) + f"{info.get('Name', '')}: {s}")
        for sub in section.get("Section", []) or []:
            walk(sub, depth + 1)

    for s in rec.get("Section", []) or []:
        walk(s, 0)
    out = "\n".join(lines)
    return (out[:fetch_max_chars] + "\n[TRUNCATED]") if len(out) > fetch_max_chars else out
