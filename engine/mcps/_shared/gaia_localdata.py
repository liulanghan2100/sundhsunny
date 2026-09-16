# -*- coding: utf-8 -*-
"""Pure helpers for GAIA local synthetic data."""
import json
from datetime import datetime, timezone
from pathlib import Path


QUESTIONS = [
    {"task_id": "local_eval_0001", "question": "What is 17 multiplied by 23?", "level": 1, "final_answer": "391", "file_name": "", "file_path": ""},
    {"task_id": "local_eval_0002", "question": "What is the capital city of France?", "level": 1, "final_answer": "Paris", "file_name": "", "file_path": ""},
    {"task_id": "local_eval_0003", "question": "The attachment is available at the local path 09_投研/agent_os_gaia/gaia_dataset/2023/validation/sales.txt . It contains three daily sales figures. What is their sum? Use the read_attachment tool to inspect it.", "level": 1, "final_answer": "300", "file_name": "sales.txt", "file_path": "09_投研/agent_os_gaia/gaia_dataset/2023/validation/sales.txt"},
    {"task_id": "local_eval_0004", "question": "The attachment is available at the local path 09_投研/agent_os_gaia/gaia_dataset/2023/validation/units.csv . It is a CSV of product shipments. What is the total quantity shipped for product alpha? Use the read_attachment tool.", "level": 2, "final_answer": "50", "file_name": "units.csv", "file_path": "09_投研/agent_os_gaia/gaia_dataset/2023/validation/units.csv"},
    {"task_id": "local_eval_0005", "question": "A train covers 180 km in 3 hours. What is its average speed in km per hour?", "level": 2, "final_answer": "60", "file_name": "", "file_path": ""},
    {"task_id": "local_eval_0006", "question": "A jacket costs 120 dollars and is discounted by 25 percent. What is the final price in dollars?", "level": 2, "final_answer": "90", "file_name": "", "file_path": ""},
    {"task_id": "local_eval_0007", "question": "The attachment is available at the local path 09_投研/agent_os_gaia/gaia_dataset/2023/validation/notes.txt . It says a recipe for 2 people needs 300 grams of flour. How many grams are needed for 5 people? Use the read_attachment tool.", "level": 2, "final_answer": "750", "file_name": "notes.txt", "file_path": "09_投研/agent_os_gaia/gaia_dataset/2023/validation/notes.txt"},
    {"task_id": "local_eval_0008", "question": "The attachment is available at the local path 09_投研/agent_os_gaia/gaia_dataset/2023/validation/units.csv . Compute the total quantity shipped across all products, then subtract the quantity shipped for product beta. What is the result? Use the read_attachment tool.", "level": 3, "final_answer": "80", "file_name": "units.csv", "file_path": "09_投研/agent_os_gaia/gaia_dataset/2023/validation/units.csv"},
    {"task_id": "local_eval_0009", "question": "Compute the following expression: 12 times 7, plus 100 divided by 4, minus 9.", "level": 3, "final_answer": "100", "file_name": "", "file_path": ""},
    {"task_id": "local_eval_0010", "question": "The attachment is available at the local path 09_投研/agent_os_gaia/gaia_dataset/2023/validation/sales.txt . It contains three daily sales figures. What is their average, rounded to the nearest integer? Use the read_attachment tool.", "level": 3, "final_answer": "100", "file_name": "sales.txt", "file_path": "09_投研/agent_os_gaia/gaia_dataset/2023/validation/sales.txt"},
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def questions_payload() -> list[dict]:
    return QUESTIONS


def attachment_payloads() -> dict[str, str]:
    return {
        "sales.txt": "Daily sales report\n120\n85\n95\n",
        "units.csv": "product,quantity\nalpha,10\nalpha,15\nalpha,25\nbeta,20\ngamma,30\n",
        "notes.txt": "Recipe serves 2 people.\nFlour required: 300 grams.\n",
    }


def index_payload(rows: list[dict]) -> dict:
    return {
        "schema_version": "agent-os-gaia-index/v0.1",
        "generated": now(),
        "repo": "SYNTHETIC-LOCAL-SMOKE (offline, no HF download)",
        "counts": {"validation": len(rows), "test": 0, "total": len(rows)},
        "validation": rows,
        "test": [],
    }


def write_parquet_rows(rows: list[dict], out_dir: Path) -> None:
    import pandas as pd
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{
        "task_id": r["task_id"],
        "Question": r["question"],
        "Level": r["level"],
        "Final answer": r["final_answer"],
        "file_name": r["file_name"],
        "file_path": r["file_path"],
    } for r in rows])
    df.to_parquet(out_dir / "metadata.level1.parquet", index=False)


def status_payload(questions: list[dict], attachments: list[str], index_path: str, counts: dict) -> dict:
    return {
        "status": "local_data_ready",
        "rows": len(questions),
        "by_level": {lv: sum(1 for row in questions if row["level"] == lv) for lv in (1, 2, 3)},
        "attachments": sorted(attachments),
        "index_path": index_path,
        "counts": counts,
    }
