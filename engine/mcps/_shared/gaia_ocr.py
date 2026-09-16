# -*- coding: utf-8 -*-
"""Pure OCR formatting helpers for the LangGraph GAIA adapter."""
import json
from pathlib import Path

def _poly_to_bbox(poly) -> str:
    try:
        pts = poly.tolist() if hasattr(poly, "tolist") else list(poly)
        xs = [int(p[0]) for p in pts if p and len(p) >= 2]
        ys = [int(p[1]) for p in pts if p and len(p) >= 2]
        if not xs or not ys:
            return "unknown"
        return f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}"
    except Exception:
        return "unknown"

def _format_ocr_block(item, page_index: int | None = None) -> dict:
    rec_texts = list(item.get("rec_texts") or [])
    rec_scores = list(item.get("rec_scores") or [])
    rec_polys = list(item.get("rec_polys") or item.get("dt_polys") or [])
    blocks = []
    for idx, text in enumerate(rec_texts):
        score = rec_scores[idx] if idx < len(rec_scores) else None
        poly = rec_polys[idx] if idx < len(rec_polys) else None
        blocks.append({
            "text": str(text),
            "confidence": round(float(score), 4) if score is not None else "unknown",
            "bbox": _poly_to_bbox(poly) if poly is not None else "unknown",
        })
    return {
        "page_index": page_index,
        "blocks": blocks,
        "text": "\n".join(block["text"] for block in blocks).strip(),
    }

def _format_ocr_payload(fp: Path, payload: dict, pdf_exts: set[str]) -> str:
    pages = list(payload.get("pages") or [])
    combined_text = str(payload.get("text") or "").strip()
    if fp.suffix.lower() in pdf_exts or len(pages) > 1:
        page_rows = []
        for idx, page in enumerate(pages):
            page_rows.append({
                "page": idx + 1,
                "text_blocks": len(page.get("blocks") or []),
                "tables": 0,
                "figures": 0,
            })
        return "\n".join([
            "LAYOUT_RESULT",
            "engine: paddleocr",
            "status: ok",
            f"source_path: {fp}",
            "pages:",
            *[f"  - page: {page['page']}\n    text_blocks: {page['text_blocks']}\n    tables: {page['tables']}\n    figures: {page['figures']}" for page in page_rows],
            "markdown:",
            combined_text,
            "json:",
            json.dumps({"pages": page_rows, "blocks": pages}, ensure_ascii=False),
        ]).strip()
    blocks = pages[0].get("blocks") if pages else []
    color_grid = pages[0].get("color_grid") if pages else []
    normalized_lines = pages[0].get("normalized_lines") if pages else []
    fraction_candidates = pages[0].get("fraction_candidates") if pages else []
    mixed_number_candidates = pages[0].get("mixed_number_candidates") if pages else []
    equation_like_lines = pages[0].get("equation_like_lines") if pages else []
    problem_rows = pages[0].get("problem_rows") if pages else []
    spatial_problem_rows = pages[0].get("spatial_problem_rows") if pages else []
    answer_extraction_candidates = pages[0].get("answer_extraction_candidates") if pages else {}
    compact_blocks = []
    for block in (blocks or [])[:20]:
        compact_blocks.append({
            "text": block.get("text", ""),
            "confidence": block.get("confidence", "unknown"),
            "bbox": block.get("bbox", "unknown"),
            "color": block.get("color", "unknown"),
        })
    return "\n".join([
        "OCR_RESULT",
        "engine: paddleocr",
        "status: ok",
        f"source_path: {fp}",
        "language: configured=en",
        f"text: {combined_text}",
        "color_grid:",
        *(color_grid or []),
        "normalized_lines:",
        *(normalized_lines or []),
        "fraction_candidates:",
        *(fraction_candidates or []),
        "mixed_number_candidates:",
        *(mixed_number_candidates or []),
        "equation_like_lines:",
        *(equation_like_lines or []),
        "problem_rows:",
        *(problem_rows or []),
        "spatial_problem_rows:",
        *(spatial_problem_rows or []),
        "answer_extraction_candidates:",
        json.dumps(answer_extraction_candidates or {}, ensure_ascii=False),
        f"blocks_count: {len(blocks or [])}",
        f"blocks_first20: {json.dumps(compact_blocks, ensure_ascii=False)}",
    ]).strip()
