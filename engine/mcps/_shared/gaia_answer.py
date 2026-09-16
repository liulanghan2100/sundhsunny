# -*- coding: utf-8 -*-
"""Pure answer cleanup helpers for the LangGraph GAIA adapter."""
import re

FINAL_ANSWER_HINTS = (
    "wait, actually", "wait, but", "let me", "i think", "likely",
    "probably", "maybe", "the latest year", "row ", "moves =",
    "here is", "here's", "answer is", "answer should be", "i need",
    "need to", "unable to", "cannot answer", "the attachment is",
    "i'll look", "i will look", "let me try", "let me check",
)
FINAL_ANSWER_CUT_RE = re.compile(
    r"(wait,?\s*actually|wait,?\s*but|let me(?:\s+just)?|i think|likely|"
    r"probably|maybe|the latest year|row\s+\d+|moves\s*=|here is|here's)",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    r"\d{1,2}\s+[A-Z][a-z]+\s+\d{2,4})\b"
)
YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}\b")
NUMBER_RE = re.compile(r"[+-]?\d+(?:,\d{3})*(?:\.\d+)?(?:/\d+)?")
COMMA_NUMBER_RE = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
ANSWER_WORD_RE = re.compile(r"\b(answer|final answer|therefore|conclusion)\b", re.IGNORECASE)


def _looks_like_prose(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "\n" in t:
        return True
    if len(t) > 120:
        return True
    lower = t.lower()
    return any(h in lower for h in FINAL_ANSWER_HINTS) or bool(ANSWER_WORD_RE.search(t))


def _strip_answer_noise(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = t.replace("\u00a0", " ")
    t = re.sub(r"^[#>\-\*\s]+", "", t)
    t = re.sub(r"\*\*|__|`", "", t)
    t = re.sub(r"^(?:the\s+)?(?:final\s+)?answer\s*[:：]\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:the\s+)?answer\s+(?:is|should\s+be)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:final\s+answer\s*[:：]\s*)", "", t, flags=re.IGNORECASE)
    m = FINAL_ANSWER_CUT_RE.search(t)
    if m and m.start() > 0:
        t = t[:m.start()].strip(" ,;:-")
    if "\n" in t:
        first_line = t.splitlines()[0].strip(" ,;:-")
        if first_line:
            t = first_line
    t = re.sub(r"\s+", " ", t).strip(" ,;:-")
    return t


def _normalize_listish_answer(text: str) -> str:
    """Normalize obvious list answers without inventing new content."""
    t = (text or "").strip()
    if not t:
        return ""
    if DATE_RE.fullmatch(t):
        return t
    if COMMA_NUMBER_RE.fullmatch(t):
        return t
    if ":" in t:
        return t
    if any(sep in t for sep in (",", ";")) or re.search(r"\s+\band\b\s+", t, re.IGNORECASE):
        parts = [p.strip() for p in re.split(r"\s*(?:,|;|\band\b)\s*", t) if p.strip()]
        if len(parts) >= 2:
            return ", ".join(parts)
    return t


def _is_junk_answer(text: str) -> bool:
    """True when a candidate final answer is tool-output residue / page noise."""
    t = (text or "").strip()
    if not t:
        return True
    lower = t.lower()
    if t in {"{", "}", "[", "]", "{ }", "{}", "[]", "{,}"}:
        return True
    if t.startswith(("{", "[")) or (t.endswith(("}", "]")) and re.search(r'":', t)):
        return True
    if re.match(r'^"?[a-zA-Z_][a-zA-Z0-9_]*"?\s*:', t):
        return True
    if any(k in lower for k in (
        "security check", "cloudflare", "access denied", "permission denied", "hcaptcha",
        "verify you are human", "404 not found", "404: not found", "429 too many requests",
        "too many requests", "server error", "service unavailable", "site unavailable",
        "not found", "could not be found", "the requested page", "the requested url was not found",
        "you have been blocked", "javascript is required", "enable javascript",
        "requested response format was not found",
        "logout", "login", "sign in", "accept all", "reject all", "accept cookies",
    )):
        return True
    if lower == "404" or lower.startswith("404 ") or lower.startswith("403"):
        return True
    if re.match(r"^(watch (reels|short videos|more)|more by |close banner|browse |skip to |search\b)", lower):
        return True
    if any(k in lower for k in ("cookies", "privacy policy", "sign in", "subscribe", "related videos", "views", "youtube", "tiktok", "reels")):
        return True
    if re.match(r"^(now i (need|will)|the document|i'll (search|read|try|look|check|start)|this paper|let me |i will |i need to|this item|i'm going)", lower):
        return True
    if lower.startswith(("i'll", "i will", "i can", "let me", "need to", "unable to", "cannot")):
        return True
    if "$(document)" in lower or "function ()" in lower or "words loaded:" in lower:
        return True
    if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?", lower) and lower.count(".") >= 2:
        return True
    if re.fullmatch(r"[a-z0-9-]+\.(?:com|org|net|io|gov|edu|co|ai)", lower):
        return True
    if re.search(r"&(?:quot|#x27|#39|amp|gt|lt|#\d+)[,;:]", lower) or re.search(r"&(?:quot|#x27|#39|amp|gt|lt);", lower):
        return True
    if re.match(r"^\d+\s+\.\.", lower):
        return True
    if re.match(r"^\d+[\.\)]\s+&(?:quot|#x27|#39|amp)", t):
        return True
    if re.search(r"benchmarking general ai agents viewer|contribute to .* by creating an account", lower):
        return True
    if lower.startswith(("thermodynamic properties of saturated", "p-v-t- data and", "native and nonnative")):
        return True
    if " • " in t and len(t) > 25:
        return True
    if t.startswith("|") or t == "END":
        return True
    if t == '"' or (t.startswith('"') and not t.endswith('"')) or re.fullmatch(r'"[^"]{1,12}"', t):
        return True
    if re.match(r'^"?[a-zA-Z_][a-zA-Z0-9_-]*"?\s*:', t):
        return True
    if "ray id" in lower or "request-id" in lower:
        return True
    if "cannot be found" in lower or "the file you are looking for" in lower:
        return True
    if "you are human" in lower or "you're human" in lower or "are you a human" in lower or "captcha" in lower or "verify your browser" in lower:
        return True
    if re.fullmatch(r"about [a-z0-9 .'\-]{1,60}", lower):
        return True
    if re.match(r'^[a-z][a-z ()]{1,50}:\s*\d', lower):
        return True
    if re.match(r'^\d{2,}:\s', t):
        return True
    if re.match(r"^a \d{4} study (found|showed)", lower):
        return True
    if re.match(r"^[a-z][a-z ]* was a (german|british|american|french|dutch|italian|swiss|austrian|russian|belgian|spanish|portuguese|swedish|norwegian|danish|polish|canadian|australian|japanese|chinese|indian) ", lower):
        return True
    if t.isupper() and len(t) > 25:
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?(?:\s+\d+(?:\.\d+)?)+", t):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?\.?(?:\s+\d+(?:\.\d+)?\.?)+", t):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?\.?(?:\s+\d+(?:\.\d+)?\.?)+\s*[a-z]+", lower):
        return True
    if t in {"ht", "htt"}:
        return True
    if (re.fullmatch(r"the [a-z]{1,4}", lower)
            or re.fullmatch(r"the [a-z]+ly", lower)
            or (re.match(r"the \d+(?:st|nd|rd|th)\b[a-z0-9' -]*", lower)
                and len(t) <= 40 and not lower.endswith((".", "?", "!")))):
        return True
    return False
