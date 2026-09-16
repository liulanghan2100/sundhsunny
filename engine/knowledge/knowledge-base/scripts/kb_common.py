# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# --- agentos-hub 适配：路径全部来自 config.yaml，经环境变量传入 ---
#
# 单一真相源：config.yaml 定义所有路径 -> hub.py 读取后用环境变量传给本脚本。
# 本文件只在"拿不到环境变量"时才自己兜底（比如直接命令行调用）。
#
# 注意 parents[4]：本文件在
#   <包根>/engine/knowledge/knowledge-base/scripts/kb_common.py
# 所以包根要往上数 4 层。写成 parents[3] 会得到 engine/，
# 兜底路径就成了 engine/data/knowledge（不存在）——
# 这是打包时引入的偏差，已修正。
ROOT = Path(__file__).resolve().parents[4]

_ENV_KB = os.environ.get("AGENTOS_HUB_KB_DIR")
KB_DIR = Path(_ENV_KB) if _ENV_KB else (ROOT / "data" / "knowledge")
META_PATH = Path(os.environ.get("AGENTOS_HUB_KB_META") or (KB_DIR / "meta.jsonl"))
INDEX_PATH = Path(os.environ.get("AGENTOS_HUB_KB_INDEX") or (KB_DIR / "index.sqlite"))

# 证据等级目录：新录入进 quarantine，人工确认后晋升到 trusted
_ENV_TRUSTED = os.environ.get("AGENTOS_HUB_KB_TRUSTED")
_ENV_QUARANTINE = os.environ.get("AGENTOS_HUB_KB_QUARANTINE")
TRUSTED_DIR = Path(_ENV_TRUSTED) if _ENV_TRUSTED else (KB_DIR / "cases")
QUARANTINE_DIR = Path(_ENV_QUARANTINE) if _ENV_QUARANTINE else (KB_DIR / "quarantine")

TYPE_DIRS = {
    "skill": "skills",
    "skills": "skills",
    "playbook": "playbooks",
    "playbooks": "playbooks",
    "case": "cases",
    "cases": "cases",
    "reference": "references",
    "references": "references",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    text = text.strip("-")
    return text[:80] or "entry"


def ensure_dirs() -> None:
    for name in ["skills", "playbooks", "references", "reports"]:
        (KB_DIR / name).mkdir(parents=True, exist_ok=True)
    # 两个证据等级目录以配置为准（可能不在 KB_DIR 下）
    TRUSTED_DIR.mkdir(parents=True, exist_ok=True)
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    if not META_PATH.exists():
        META_PATH.write_text("", encoding="utf-8")


def read_meta() -> list[dict]:
    ensure_dirs()
    rows = []
    for line in META_PATH.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_meta(rows: list[dict]) -> None:
    ensure_dirs()
    text = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
    META_PATH.write_text(text + ("\n" if text else ""), encoding="utf-8")


def append_meta(row: dict) -> None:
    ensure_dirs()
    with META_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_type(value: str) -> str:
    key = (value or "playbook").strip().lower()
    if key not in TYPE_DIRS:
        raise SystemExit(f"Unknown type: {value}. Use skill/playbook/case/reference.")
    return key[:-1] if key.endswith("s") else key


def target_dir(entry_type: str, status: str) -> Path:
    """待审条目放 quarantine，已采信条目按类型分目录存到 trusted 下。"""
    if status == "quarantine":
        return QUARANTINE_DIR
    return TRUSTED_DIR / TYPE_DIRS[entry_type]


def make_entry_id(title: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"kb-{stamp}-{slugify(title)}"


def init_db() -> sqlite3.Connection:
    ensure_dirs()
    con = sqlite3.connect(INDEX_PATH)
    con.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS entries USING fts5("
        "id UNINDEXED, title, summary, body, tags, status UNINDEXED, type UNINDEXED, path UNINDEXED, source_url UNINDEXED)"
    )
    return con


def rebuild_index() -> int:
    rows = read_meta()
    con = init_db()
    con.execute("DELETE FROM entries")
    count = 0
    for row in rows:
        path = ROOT / row["path"]
        body = path.read_text(encoding="utf-8") if path.exists() else ""
        con.execute(
            "INSERT INTO entries(id,title,summary,body,tags,status,type,path,source_url) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                row.get("id", ""),
                row.get("title", ""),
                row.get("summary", ""),
                body,
                ",".join(row.get("tags", [])),
                row.get("status", ""),
                row.get("type", ""),
                row.get("path", ""),
                row.get("source_url", ""),
            ),
        )
        count += 1
    con.commit()
    con.close()
    return count


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", required=True)
    parser.add_argument("--type", default="playbook", choices=["skill", "playbook", "case", "reference"])
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-path", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--content", default="")
    parser.add_argument("--file", default="")
    parser.add_argument("--status", default="quarantine", choices=["quarantine", "trusted"])
