# -*- coding: utf-8 -*-
"""Pure helpers for GAIA dataset setup."""
import json
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_example(example: dict, base_dir: str) -> dict:
    file_path = str(example.get("file_path") or "")
    resolved = file_path
    if file_path and not Path(file_path).is_absolute():
        candidate = Path(base_dir) / file_path.lstrip("/")
        resolved = str(candidate) if candidate.exists() else file_path
    return {
        "task_id": str(example.get("task_id") or example.get("task id") or ""),
        "question": str(example.get("Question") or example.get("question") or ""),
        "level": int(example.get("Level") or example.get("level") or 0),
        "final_answer": str(example.get("Final answer") or example.get("final_answer") or ""),
        "file_name": str(example.get("file_name") or ""),
        "file_path": resolved,
        "annotator_metadata": example.get("Annotator Metadata") or example.get("annotator_metadata") or {},
    }


def read_existing_index(index_path: Path) -> dict:
    if index_path.exists():
        return json.loads(index_path.read_text(encoding="utf-8"))
    return {"validation": [], "test": []}


def write_index_payload(schema_version: str, repo: str, validation: list[dict], test: list[dict]) -> dict:
    return {
        "schema_version": schema_version,
        "generated": now(),
        "repo": repo,
        "counts": {
            "validation": len(validation),
            "test": len(test),
            "total": len(validation) + len(test),
        },
        "validation": validation,
        "test": test,
    }


def snapshot_payload(index: dict, split: str, limit: int | None, index_path: str, smoke_dir: Path) -> dict:
    smoke_dir.mkdir(parents=True, exist_ok=True)
    return {
        "ts": now(),
        "split": split,
        "limit": limit,
        "counts": index["counts"],
        "first_validation_ids": [row["task_id"] for row in index["validation"][:3]],
        "first_test_ids": [row["task_id"] for row in index["test"][:3]],
        "index_path": index_path,
    }
