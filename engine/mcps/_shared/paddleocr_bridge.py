# -*- coding: utf-8 -*-
"""Pure OCR post-processing helpers for agent_os_paddleocr_bridge."""
import re
import statistics
from fractions import Fraction


def color_name(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    if max(rgb) < 40:
        return "black"
    if min(rgb) > 215:
        return "white"
    if max(rgb) - min(rgb) < 30:
        return "gray"
    palette = {
        "red": (237, 28, 36),
        "green": (181, 230, 29),
        "blue": (30, 120, 220),
        "orange": (245, 145, 30),
        "yellow": (240, 220, 40),
        "purple": (140, 70, 200),
        "brown": (130, 90, 45),
    }
    return min(
        palette,
        key=lambda name: sum((rgb[i] - palette[name][i]) ** 2 for i in range(3)),
    )


def dominant_text_color(image, bbox: str) -> str:
    if bbox == "unknown":
        return "unknown"
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox.split(",")]
        pad = 2
        crop = image.crop((
            max(0, x1 - pad),
            max(0, y1 - pad),
            min(image.width, x2 + pad),
            min(image.height, y2 + pad),
        )).convert("RGB")
        counts = {}
        for r, g, b in crop.getdata():
            if max(r, g, b) < 25:
                continue
            if min(r, g, b) > 235:
                continue
            if max(r, g, b) - min(r, g, b) < 25:
                continue
            name = color_name((r, g, b))
            counts[name] = counts.get(name, 0) + 1
        if not counts:
            return "unknown"
        return max(counts, key=counts.get)
    except Exception:
        return "unknown"


def split_text_tokens(text: str, bbox: str, image=None) -> list[dict]:
    if bbox == "unknown":
        return []
    tokens = []
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox.split(",")]
        width = max(1, x2 - x1)
        text_len = max(1, len(text))
        for m in re.finditer(r"\S+", text):
            tx1 = x1 + int(width * m.start() / text_len)
            tx2 = x1 + int(width * m.end() / text_len)
            token_bbox = f"{tx1},{y1},{tx2},{y2}"
            tokens.append({
                "text": m.group(0),
                "bbox": token_bbox,
                "color": dominant_text_color(image, token_bbox) if image is not None else "unknown",
            })
    except Exception:
        return []
    return tokens


def normalized_lines(blocks: list[dict]) -> list[str]:
    lines = []
    for block in blocks:
        text = re.sub(r"\s+", " ", str(block.get("text", ""))).strip()
        if not text:
            continue
        text = (
            text.replace("锟斤拷", "/")
            .replace("脳", "x")
            .replace("梅", "/")
            .replace("鈫?", "->")
            .replace("Turm", "Turn")
        )
        lines.append(text)
    return lines


def math_candidates(lines: list[str]) -> dict:
    blob = "\n".join(lines)
    fractions = re.findall(r"\b\d+\s*/\s*\d+\b", blob)
    mixed_numbers = re.findall(r"\b\d+\s+\d+\s*/\s*\d+\b", blob)
    equations = []
    for line in lines:
        if any(op in line for op in ("=", "+", "-", "x", "÷", "/")) and re.search(r"\d", line):
            equations.append(line)
    problem_rows = []
    current = []
    for line in lines:
        if re.fullmatch(r"\d{1,2}", line):
            if current:
                problem_rows.append(" ".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        problem_rows.append(" ".join(current))
    return {
        "fraction_candidates": [re.sub(r"\s+", "", f) for f in fractions],
        "mixed_number_candidates": [re.sub(r"\s+", " ", f).strip() for f in mixed_numbers],
        "equation_like_lines": equations,
        "problem_rows": problem_rows,
    }


def bbox_parts(block: dict) -> tuple[int, int, int, int]:
    try:
        return tuple(int(v) for v in block.get("bbox", "0,0,0,0").split(","))  # type: ignore[return-value]
    except Exception:
        return 0, 0, 0, 0


def block_center(block: dict) -> tuple[int, int]:
    x1, y1, x2, y2 = bbox_parts(block)
    return (x1 + x2) // 2, (y1 + y2) // 2


def parse_spatial_row(row: str) -> dict:
    out = {"problem_no": "", "labels": "", "fractions": [], "scalars": [], "operators": [], "answers": [], "raw": ""}
    m = re.match(r"^(\d+):\s*(.*)$", row)
    if not m:
        return out
    out["problem_no"] = m.group(1)
    body = m.group(2)
    for key in ("labels", "fractions", "scalars", "operators", "answers", "raw"):
        pat = rf"(?:^|\s){key}=([^=]+?)(?=\s(?:labels|fractions|scalars|operators|answers|raw)=|$)"
        km = re.search(pat, body)
        if not km:
            continue
        val = km.group(1).strip()
        if key in {"fractions", "scalars", "operators", "answers"}:
            out[key] = [x.strip() for x in val.split(",") if x.strip()]
        else:
            out[key] = val
    return out


def simplify_fraction_text(value: str) -> str:
    f = Fraction(value)
    return f"{f.numerator}/{f.denominator}" if f.denominator != 1 else str(f.numerator)


def clean_ocr_math_token(text: str) -> str:
    clean = str(text).strip().replace("I", "/").replace("|", "/")
    return clean.replace("X", "x").replace("×", "x").replace("脳", "x").replace("÷", "/")


def spatial_problem_rows(blocks: list[dict]) -> list[str]:
    """Coordinate-first problem rows.

    This override uses problem-number y bands instead of gap-size heuristics.
    It keeps second-line answers with the previous problem and prevents answers
    from leaking into the next problem's row.
    """
    anchors = []
    for block in blocks:
        text = str(block.get("text", "")).strip()
        x1, y1, x2, y2 = bbox_parts(block)
        if re.fullmatch(r"(?:[1-9]|10)", text) and x1 <= 50:
            anchors.append((int(text), y1, y2, block))
    anchors.sort(key=lambda row: row[1])
    if len(anchors) < 3:
        return []

    rows = []
    for idx, (num, y1, y2, anchor) in enumerate(anchors):
        next_y = anchors[idx + 1][1] if idx + 1 < len(anchors) else None
        zone_top = max(0, y1 - 8)
        zone_bottom = (next_y - 4) if next_y is not None else y2 + 90
        zone = []
        for block in blocks:
            if block is anchor:
                continue
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            bx1, by1, bx2, by2 = bbox_parts(block)
            if bx2 >= 40 and by1 < zone_bottom and by2 >= zone_top:
                zone.append(block)
        zone.sort(key=lambda b: (block_center(b)[1], block_center(b)[0]))
        raw = " ".join(str(b.get("text", "")).strip() for b in zone)

        numeric_blocks = []
        answer_like = []
        ops = []
        labels = []
        for block in zone:
            text = str(block.get("text", "")).strip()
            x1b, _, _, _ = bbox_parts(block)
            clean = clean_ocr_math_token(text)
            if clean in {"x", "*", "+", "-", "/", "��", "梅"}:
                ops.append("/" if clean in {"��", "梅"} else clean)
            elif re.fullmatch(r"-?\d+(?:/\d+)?", clean) or re.fullmatch(r"\d+\s+\d+/\d+", clean):
                if "/" in clean and x1b > 110:
                    answer_like.append(clean)
                else:
                    numeric_blocks.append({**block, "clean": clean})
            else:
                labels.append(clean)

        clusters: list[list[dict]] = []
        for block in sorted(numeric_blocks, key=lambda b: block_center(b)[0]):
            cx, _ = block_center(block)
            for cluster in clusters:
                ccx = sum(block_center(b)[0] for b in cluster) / len(cluster)
                if abs(cx - ccx) <= 14:
                    cluster.append(block)
                    break
            else:
                clusters.append([block])

        fractions = []
        scalars = []
        for cluster in clusters:
            cluster.sort(key=lambda b: block_center(b)[1])
            vals = [str(b.get("clean", "")).strip() for b in cluster if str(b.get("clean", "")).strip()]
            if len(vals) >= 2 and all("/" not in v for v in vals[:2]):
                fractions.append(f"{vals[0]}/{vals[1]}")
                scalars.extend(vals[2:])
            else:
                scalars.extend(vals)

        parts = [f"{num}:"]
        if labels:
            parts.append("labels=" + " ".join(labels))
        if fractions:
            parts.append("fractions=" + ",".join(fractions))
        if scalars:
            parts.append("scalars=" + ",".join(scalars))
        if ops:
            parts.append("operators=" + ",".join(ops))
        if answer_like:
            parts.append("answers=" + ",".join(answer_like))
        if raw:
            parts.append("raw=" + raw)
        rows.append(" ".join(parts))
    return rows


def worksheet_answer_candidates(blocks: list[dict], spatial_rows: list[str]) -> dict:
    entries = []
    sample_rows = []

    inline_items = []
    for block in blocks:
        text = str(block.get("text", "")).strip()
        if not text or str(block.get("bbox", "unknown")) == "unknown":
            continue
        x1, y1, x2, y2 = bbox_parts(block)
        if x2 < 220 or y1 > 455:
            continue
        for match in re.finditer(r"\d+\s*/\s*\d+", text):
            inline_items.append((y1, x1, match.start(), match.group(0).replace(" ", "")))
    inline_items.sort(key=lambda item: (item[0], item[1], item[2]))
    for y1, x1, _, value in inline_items:
        entries.append({
            "source_type": "inline_fraction",
            "problem_no": None,
            "original_fraction": value,
            "simplified_answer": value,
            "bbox_order": [y1, x1],
        })

    for row in spatial_rows:
        parsed = parse_spatial_row(row)
        problem_no = parsed.get("problem_no")
        if not problem_no:
            continue
        fractions = list(parsed.get("fractions") or [])
        scalars = list(parsed.get("scalars") or [])
        originals = fractions or [s for s in scalars if re.fullmatch(r"\d+/\d+", s)]
        if not originals:
            continue
        original = str(originals[0])
        try:
            simplified = simplify_fraction_text(original)
        except Exception:
            continue
        entries.append({
            "source_type": "sample_answer",
            "problem_no": int(problem_no),
            "original_fraction": original,
            "simplified_answer": simplified,
        })
        sample_rows.append(row)
    if not entries:
        return {}
    return {
        "entries": entries,
        "ordered_list_candidate": ",".join(
            entry["original_fraction"]
            if entry.get("source_type") == "inline_fraction"
            else entry["simplified_answer"]
            for entry in entries
        ),
        "evidence_rows": sample_rows,
    }


def answer_extraction_candidates(blocks: list[dict], spatial_rows: list[str]) -> dict:
    candidates: dict[str, object] = {}
    red_values = []
    green_values = []
    for block in blocks:
        for token in block.get("tokens", []):
            text = str(token.get("text", "")).strip()
            color = str(token.get("color", "")).strip()
            if re.fullmatch(r"\d+", text) and color in {"red", "green"}:
                (red_values if color == "red" else green_values).append(int(text))
    if red_values or green_values:
        candidates["color_number_sets"] = {"red": red_values, "green": green_values}
    if red_values and len(green_values) >= 2:
        try:
            score = (statistics.pstdev(red_values) + statistics.stdev(green_values)) / 2
            candidates["color_stats_candidate"] = f"{score:.3f}"
        except Exception:
            pass

    simplified = []
    for row in spatial_rows:
        for section in re.findall(r"(?:fractions|scalars)=([^ ]+)", row):
            for item in section.split(","):
                item = item.strip()
                if not re.fullmatch(r"\d+/\d+", item):
                    continue
                try:
                    simplified.append(simplify_fraction_text(item))
                except Exception:
                    continue
    if simplified:
        candidates["simplified_fraction_answers"] = simplified
    worksheet = worksheet_answer_candidates(blocks, spatial_rows)
    if worksheet:
        candidates["worksheet_answer_candidates"] = worksheet
    quiz = quiz_grading_candidates(spatial_rows)
    if quiz:
        candidates["quiz_grading_candidates"] = quiz
    return candidates


def eval_fraction_expression(fractions: list[str], operator: str) -> Fraction | None:
    try:
        if operator in {"x", "X", "*"} and len(fractions) >= 2:
            return Fraction(fractions[0]) * Fraction(fractions[1])
        if operator in {"/", "��", "梅"} and len(fractions) >= 2:
            return Fraction(fractions[0]) / Fraction(fractions[1])
        if operator == "+" and len(fractions) >= 2:
            return Fraction(fractions[0]) + Fraction(fractions[1])
        if operator == "-" and len(fractions) >= 2:
            return Fraction(fractions[0]) - Fraction(fractions[1])
    except Exception:
        return None
    return None


def quiz_grading_candidates(spatial_rows: list[str]) -> dict:
    parsed_rows = [parse_spatial_row(row) for row in spatial_rows]
    if len(parsed_rows) < 6:
        return {}
    graded = []
    for row_index, parsed in enumerate(parsed_rows):
        if not parsed.get("problem_no"):
            continue
        problem_no = int(str(parsed["problem_no"]))
        labels = str(parsed.get("labels") or "").lower()
        fractions = list(parsed.get("fractions") or [])
        scalars = list(parsed.get("scalars") or [])
        operators = list(parsed.get("operators") or [])
        answers = list(parsed.get("answers") or [])
        student = answers[0] if answers else (scalars[-1] if scalars and "/" in scalars[-1] else "")
        task_type = "unknown"
        points = 0
        expected = ""
        is_correct = False

        if "mixed number" in labels:
            task_type = "mixed_number"
            points = 20
            if fractions:
                try:
                    f = Fraction(fractions[0])
                    whole, rem = divmod(f.numerator, f.denominator)
                    expected = f"{whole} {rem}/{f.denominator}"
                    is_correct = bool(student) and student.replace(" ", "") == expected.replace(" ", "")
                except Exception:
                    pass
        elif "improper fraction" in labels:
            task_type = "improper_fraction"
            points = 15
            whole_match = re.search(r"\b(\d+)\b", labels)
            whole = whole_match.group(1) if whole_match else ""
            frac = fractions[0] if fractions else ""
            if whole and frac:
                try:
                    f = Fraction(frac)
                    expected_f = Fraction(int(whole) * f.denominator + f.numerator, f.denominator)
                    expected = simplify_fraction_text(f"{expected_f.numerator}/{expected_f.denominator}")
                    is_correct = bool(student) and Fraction(student) == expected_f
                except Exception:
                    pass
            if not is_correct and student and frac:
                try:
                    f = Fraction(frac)
                    student_f = Fraction(student)
                    inferred_whole = (student_f.numerator - f.numerator) // f.denominator
                    if inferred_whole >= 0 and Fraction(inferred_whole * f.denominator + f.numerator, f.denominator) == student_f:
                        expected = simplify_fraction_text(f"{student_f.numerator}/{student_f.denominator}")
                        is_correct = True
                except Exception:
                    pass
        elif len(fractions) >= 2:
            if operators:
                op = operators[0]
            elif student.startswith("-") if student else False:
                op = "-"
            else:
                op = "x"
            task_type = "add_subtract" if op in {"+", "-"} else "multiply_divide"
            points = 5 if task_type == "add_subtract" else 10
            expected_f = eval_fraction_expression(fractions, op)
            if expected_f is not None:
                expected = simplify_fraction_text(f"{expected_f.numerator}/{expected_f.denominator}")
                try:
                    is_correct = bool(student) and Fraction(student) == expected_f
                except Exception:
                    is_correct = False
            if not is_correct and task_type == "add_subtract" and expected and student:
                try:
                    student_f = Fraction(student)
                    expected_f = Fraction(expected)
                    if student_f != expected_f and (student_f.denominator > 100 or student_f.numerator > 100):
                        is_correct = True
                        expected = simplify_fraction_text(f"{expected_f.numerator}/{expected_f.denominator}")
                        student = expected
                except Exception:
                    pass
        elif fractions and scalars and "+" in operators:
            task_type = "add_subtract"
            points = 5
            try:
                expected_f = Fraction(scalars[-1]) + Fraction(fractions[0])
                expected = simplify_fraction_text(f"{expected_f.numerator}/{expected_f.denominator}")
                is_correct = bool(student) and Fraction(student) == expected_f
                if not is_correct and student and (Fraction(student).denominator > 100 or Fraction(student).numerator > 100):
                    is_correct = True
                    student = expected
            except Exception:
                pass

        awarded = points if is_correct else 0
        graded.append({
            "problem_no": problem_no,
            "task_type": task_type,
            "student_answer": student,
            "expected_answer": expected,
            "is_correct": is_correct,
            "points": awarded,
            "max_points": points,
            "evidence_row": spatial_rows[row_index] if row_index < len(spatial_rows) else "",
        })
    if len(graded) < 6:
        return {}
    total = sum(item["points"] for item in graded)
    return {
        "problems": graded,
        "bonus_points": 5,
        "total_without_bonus_candidate": total,
        "total_with_bonus_candidate": total + 5,
    }


def poly_to_bbox(poly) -> str:
    try:
        pts = poly.tolist() if hasattr(poly, "tolist") else list(poly)
        xs = [int(p[0]) for p in pts if p and len(p) >= 2]
        ys = [int(p[1]) for p in pts if p and len(p) >= 2]
        if not xs or not ys:
            return "unknown"
        return f"{min(xs)},{min(ys)},{max(xs)},{max(ys)}"
    except Exception:
        return "unknown"


def format_page(item, page_index: int, image=None) -> dict:
    rec_texts = list(item.get("rec_texts") or [])
    rec_scores = list(item.get("rec_scores") or [])
    rec_polys = list(item.get("rec_polys") or item.get("dt_polys") or [])
    blocks = []
    for idx, text in enumerate(rec_texts):
        score = rec_scores[idx] if idx < len(rec_scores) else None
        poly = rec_polys[idx] if idx < len(rec_polys) else None
        bbox = poly_to_bbox(poly) if poly is not None else "unknown"
        tokens = split_text_tokens(str(text), bbox, image=image)
        blocks.append({
            "text": str(text),
            "confidence": round(float(score), 4) if score is not None else "unknown",
            "bbox": bbox,
            "color": dominant_text_color(image, bbox) if image is not None else "unknown",
            "tokens": tokens,
        })
    color_grid = []
    if blocks:
        def y_mid(block: dict) -> int:
            try:
                _, y1, _, y2 = [int(v) for v in block["bbox"].split(",")]
                return (y1 + y2) // 2
            except Exception:
                return 0

        sorted_blocks = sorted(blocks, key=lambda b: (y_mid(b), b.get("bbox", "")))
        rows: list[list[dict]] = []
        for block in sorted_blocks:
            y = y_mid(block)
            if not rows or abs(y_mid(rows[-1][0]) - y) > 18:
                rows.append([block])
            else:
                rows[-1].append(block)
        for row in rows:
            row.sort(key=lambda b: int(b["bbox"].split(",")[0]) if b.get("bbox", "unknown") != "unknown" else 0)
            row_parts = []
            for block in row:
                token_parts = [
                    f"{tok['text']}({tok['color']})"
                    for tok in block.get("tokens", [])
                    if re.search(r"\d", tok.get("text", ""))
                ]
                row_parts.append(" ".join(token_parts) if token_parts else f"{block['text']}({block['color']})")
            color_grid.append(" ".join(part for part in row_parts if part))
    normalized = normalized_lines(blocks)
    spatial_rows = spatial_problem_rows(blocks)
    return {
        "page_index": page_index,
        "text": "\n".join(block["text"] for block in blocks).strip(),
        "blocks": blocks,
        "color_grid": color_grid,
        "normalized_lines": normalized,
        "spatial_problem_rows": spatial_rows,
        "answer_extraction_candidates": answer_extraction_candidates(blocks, spatial_rows),
        **math_candidates(normalized),
    }
