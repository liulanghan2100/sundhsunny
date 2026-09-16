from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ALLOWED_LEVELS = {"direct", "supported", "engineering_inference"}
ALLOWED_TYPES = {"formula", "assumption", "failure_mode"}
EMPTY = {"", "-", "TBD", "待补", "待定"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def is_empty(value: object) -> bool:
    return not isinstance(value, str) or value.strip() in EMPTY


def split_cards(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^##\s+\d+\.\s+(.+)$", text, re.MULTILINE))
    cards: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        cards.append((match.group(1).strip(), text[start:end]))
    return cards


def field_value(card_body: str, field: str) -> str:
    pattern = re.compile(rf"^\|\s*{re.escape(field)}\s*\|\s*(.*?)\s*\|$", re.MULTILINE)
    match = pattern.search(card_body)
    return match.group(1).strip() if match else ""


def split_claim_items(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[；;]", value) if item.strip()]


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    path = root / "claim_evidence.json"
    if not path.exists():
        path = root / "references" / "claim_evidence.json"
    data = load_json(path)
    status = data.get("status")
    if status not in {"quarantine", "review", "trusted"}:
        print("CLAIM EVIDENCE VALIDATION FAILED")
        print(f"- claim_evidence.json: invalid status {status}")
        return 1

    claims = data.get("claims", [])
    errors: list[str] = []
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    covered_claims: set[tuple[str, str, str]] = set()

    if not isinstance(claims, list) or not claims:
        errors.append("claim_evidence.json: claims must be a non-empty list")
    else:
        for index, claim in enumerate(claims, start=1):
            if not isinstance(claim, dict):
                errors.append(f"claim #{index}: must be object")
                continue

            model_id = claim.get("model_id")
            claim_type = claim.get("claim_type")
            evidence_level = claim.get("evidence_level")

            for field in [
                "model_id",
                "claim_type",
                "claim_text",
                "evidence_level",
                "source_url",
                "source_locator",
                "reviewer_status",
            ]:
                if is_empty(claim.get(field)):
                    errors.append(f"claim #{index}: empty field {field}")

            if claim_type not in ALLOWED_TYPES:
                errors.append(f"claim #{index}: invalid claim_type {claim_type}")
            if evidence_level not in ALLOWED_LEVELS:
                errors.append(f"claim #{index}: invalid evidence_level {evidence_level}")

            source_url = claim.get("source_url", "")
            if evidence_level == "engineering_inference":
                if source_url not in {"engineering_inference", "engineering://inference"}:
                    errors.append(
                        f"claim #{index}: engineering_inference must not point at S/A source_url"
                    )
            elif not isinstance(source_url, str) or not re.search(r"https?://", source_url):
                errors.append(f"claim #{index}: source_url must contain http(s) URL")

            source_locator = claim.get("source_locator", "")
            if not isinstance(source_locator, str) or len(source_locator.strip()) < 30:
                errors.append(f"claim #{index}: source_locator too vague")

            if isinstance(model_id, str):
                by_model[model_id].append(claim)
            if isinstance(model_id, str) and isinstance(claim_type, str) and isinstance(claim.get("claim_text"), str):
                covered_claims.add((model_id, claim_type, claim["claim_text"].strip()))

    for model_id, model_claims in sorted(by_model.items()):
        counts = Counter(claim["claim_type"] for claim in model_claims)
        levels = Counter(claim["evidence_level"] for claim in model_claims)

        if counts["formula"] < 1:
            errors.append(f"{model_id}: missing formula claim")
        if counts["assumption"] < 3:
            errors.append(f"{model_id}: fewer than 3 assumption claims")
        if counts["failure_mode"] < 3:
            errors.append(f"{model_id}: fewer than 3 failure_mode claims")

        formula_claims = [claim for claim in model_claims if claim["claim_type"] == "formula"]
        if not any(claim["evidence_level"] in {"direct", "supported"} for claim in formula_claims):
            errors.append(f"{model_id}: no source-backed formula claim")
        direct_formula = [claim for claim in formula_claims if claim["evidence_level"] == "direct"]
        if model_id != "agent-based-model" and not direct_formula:
            errors.append(f"{model_id}: formula must be direct unless model has no unified formula")

        assumption_backed = [
            claim
            for claim in model_claims
            if claim["claim_type"] == "assumption"
            and claim["evidence_level"] in {"direct", "supported"}
        ]
        if len(assumption_backed) < 2:
            errors.append(f"{model_id}: fewer than 2 source-backed assumptions")

        if levels["engineering_inference"]:
            for claim in model_claims:
                if claim["evidence_level"] == "engineering_inference":
                    locator = claim["source_locator"].lower()
                    if "not directly" not in locator and "inferred" not in locator and "inference" not in locator:
                        errors.append(
                            f"{model_id}: engineering inference claim must state it is not direct: {claim['claim_text']}"
                        )

    model_card_path = root / "04_S层模型详卡_Batch01.md"
    if not model_card_path.exists():
        model_card_path = root / "references" / "model-cards-s-batch01.md"
    if model_card_path.exists():
        for _name, body in split_cards(model_card_path.read_text(encoding="utf-8")):
            model_id = field_value(body, "model_id")
            for claim_type, field in [("assumption", "核心假设"), ("failure_mode", "失效模式")]:
                for item in split_claim_items(field_value(body, field)):
                    if (model_id, claim_type, item) not in covered_claims:
                        errors.append(f"{model_id}: card field {field} not covered by claim evidence: {item}")

    if errors:
        print("CLAIM EVIDENCE VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    model_count = len(by_model)
    claim_count = len(claims)
    level_counts = Counter(claim["evidence_level"] for claim in claims)
    print(f"CLAIM EVIDENCE VALIDATION PASSED: models={model_count}, claims={claim_count}")
    print(
        "levels="
        + ", ".join(f"{level}={level_counts[level]}" for level in ["direct", "supported", "engineering_inference"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
