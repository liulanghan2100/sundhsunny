# -*- coding: utf-8 -*-
"""经验回流（learning overlay）：复盘洞察写回手册，让体系随项目进化。

设计契约（见 06_演进记录/manual-gates-v2/01_战略与设计.md）：
- 基线 manual_data.py 永不修改；回流内容存 learned.json，读取时合并。
- learned.json 损坏时回退为空覆盖层（= 纯基线），绝不白屏。
- 新节点 id 从 max(id)+1 自动分配；仅 action/output/acceptance/name 四字段可被回流修改。
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from .manual_data import STAGES

LEARNED_PATH = Path(__file__).resolve().parent / "learned.json"
MUTABLE_FIELDS = ("name", "action", "output", "acceptance")


def load_learned() -> dict:
    empty = {"node_updates": {}, "new_nodes": [], "log": []}
    if not LEARNED_PATH.exists():
        return empty
    try:
        d = json.loads(LEARNED_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty  # 损坏回退：纯基线
    for k, v in empty.items():
        d.setdefault(k, v)
    return d


def _save(d: dict) -> None:
    LEARNED_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def get_stages() -> list:
    """基线 + 覆盖层合并后的阶段树。无 learned.json 时与基线完全等价。"""
    learned = load_learned()
    stages = copy.deepcopy(STAGES)
    by_id = {n["id"]: n for s in stages for n in s["nodes"]}
    for nid, upd in learned["node_updates"].items():
        node = by_id.get(int(nid))
        if node:
            node.update({k: v for k, v in upd.items() if k in MUTABLE_FIELDS})
    stage_by_key = {s["key"]: s for s in stages}
    for nn in learned["new_nodes"]:
        s = stage_by_key.get(nn.get("stage"))
        if s and all(k in nn for k in ("id", "name", "action", "output", "acceptance")):
            s["nodes"].append({k: nn[k] for k in ("id", "name", "action", "output", "acceptance")})
    return stages


def get_node_index() -> dict:
    return {n["id"]: (s, n) for s in get_stages() for n in s["nodes"]}


def _log(d: dict, entry: dict) -> None:
    d["log"].append({**entry, "ts": datetime.now(timezone.utc).isoformat()})


def apply_update(project: str, node_id: int, fields: dict, rationale: str) -> dict:
    """更新已有节点的可写字段。返回 {old, new} 对照。"""
    idx = get_node_index()
    if node_id not in idx:
        raise ValueError(f"节点 {node_id} 不存在")
    _, node = idx[node_id]
    fields = {k: v for k, v in fields.items() if k in MUTABLE_FIELDS and v}
    if not fields:
        raise ValueError("没有可更新的字段（仅 name/action/output/acceptance）")
    old = {k: node[k] for k in fields}
    d = load_learned()
    d["node_updates"].setdefault(str(node_id), {}).update(fields)
    _log(d, {"type": "update_node", "project": project, "node_id": node_id, "fields": list(fields), "rationale": rationale})
    _save(d)
    return {"old": old, "new": fields}


def apply_new_node(project: str, stage_key: str, name: str, action: str, output: str, acceptance: str, rationale: str) -> dict:
    """新增自定义节点，id 自动分配（max+1），挂到指定阶段末尾。"""
    valid = {s["key"] for s in STAGES}
    if stage_key not in valid:
        raise ValueError(f"非法 stage_key：{stage_key}，合法值 {sorted(valid)}")
    idx = get_node_index()
    new_id = max(idx.keys(), default=25) + 1
    node = {
        "id": new_id, "stage": stage_key, "name": name,
        "action": action, "output": output, "acceptance": acceptance,
        "source_project": project,
    }
    d = load_learned()
    d["new_nodes"].append(node)
    _log(d, {"type": "add_node", "project": project, "node_id": new_id, "name": name, "rationale": rationale})
    _save(d)
    return node
