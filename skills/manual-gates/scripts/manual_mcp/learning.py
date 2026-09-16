# -*- coding: utf-8 -*-
"""经验回流（learning overlay）：复盘洞察写回手册，让体系随项目进化。

设计契约（见 06_演进记录/manual-gates-v2/01_战略与设计.md）：
- 基线 manual_data.py 永不修改；回流内容存 learned.json，读取时合并。
- learned.json 损坏时回退为空覆盖层（= 纯基线），绝不白屏。
- 新节点 id 从 max(id)+1 自动分配；仅 action/output/acceptance/name 四字段可被回流修改。
- 新经验先进入 learned_candidates.json，必须经过 shadow -> review -> owner approval
  后才允许晋升到 learned.json，避免单项目经验立即污染全局手册。
"""
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .manual_data import STAGES

LEARNED_PATH = Path(__file__).resolve().parent / "learned.json"
CANDIDATES_PATH = Path(__file__).resolve().parent / "learned_candidates.json"
MUTABLE_FIELDS = ("name", "action", "output", "acceptance")
CANDIDATE_STATUSES = (
    "candidate",
    "review_required",
    "owner_review_required",
    "owner_approved",
    "promoted",
    "rejected",
)


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_candidates(d: dict) -> None:
    CANDIDATES_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def load_candidates() -> dict:
    empty = {"candidates": [], "log": []}
    if not CANDIDATES_PATH.exists():
        return empty
    try:
        d = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty
    for k, v in empty.items():
        d.setdefault(k, v)
    return d


def _candidate_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _find_candidate(d: dict, candidate_id: str) -> dict:
    for item in d["candidates"]:
        if item.get("candidate_id") == candidate_id:
            return item
    raise ValueError(f"候选不存在：{candidate_id}")


def _log_candidate(d: dict, candidate_id: str, event: str, detail: dict | None = None) -> None:
    d["log"].append({
        "candidate_id": candidate_id,
        "event": event,
        "detail": detail or {},
        "ts": _now(),
    })


def create_candidate(project: str, action: str, node_id: int = 0, stage_key: str = "",
                     name: str = "", action_desc: str = "", output: str = "",
                     acceptance: str = "", rationale: str = "") -> dict:
    """创建项目级经验候选；不写 learned.json。"""
    if action not in ("update_node", "add_node"):
        raise ValueError("候选 action 只能是 update_node 或 add_node")
    if not rationale:
        raise ValueError("rationale 必填：候选必须记录来源原因")

    if action == "update_node":
        idx = get_node_index()
        if node_id not in idx:
            raise ValueError(f"节点 {node_id} 不存在")
        fields = {"name": name, "action": action_desc, "output": output, "acceptance": acceptance}
        proposed_change = {k: v for k, v in fields.items() if k in MUTABLE_FIELDS and v}
        if not proposed_change:
            raise ValueError("没有可更新的字段（仅 name/action/output/acceptance）")
    else:
        valid = {s["key"] for s in STAGES}
        if stage_key not in valid:
            raise ValueError(f"非法 stage_key：{stage_key}，合法值 {sorted(valid)}")
        if not (name and acceptance):
            raise ValueError("add_node 需要 stage_key + name + acceptance")
        proposed_change = {
            "stage": stage_key,
            "name": name,
            "action": action_desc,
            "output": output,
            "acceptance": acceptance,
        }

    created_at = _now()
    base = {
        "source_project": project,
        "change_type": action,
        "target_node": node_id or None,
        "proposed_change": proposed_change,
        "rationale": rationale,
        "created_at": created_at,
    }
    candidate = {
        "candidate_id": f"lc-{_candidate_hash(base)}",
        **base,
        "status": "candidate",
        "shadow_result": None,
        "review": None,
        "owner_decision": None,
        "promoted_at": None,
    }
    d = load_candidates()
    d["candidates"].append(candidate)
    _log_candidate(d, candidate["candidate_id"], "candidate_created", {
        "project": project,
        "change_type": action,
        "target_node": node_id or None,
    })
    _save_candidates(d)
    return candidate


def record_shadow(candidate_id: str, passed: bool, notes: str = "", result: dict | None = None) -> dict:
    """记录 shadow 影子运行结果；通过后进入对抗评审。"""
    d = load_candidates()
    candidate = _find_candidate(d, candidate_id)
    if candidate.get("status") not in ("candidate", "review_required"):
        raise ValueError(f"当前状态不允许记录 shadow：{candidate.get('status')}")
    candidate["shadow_result"] = {
        "passed": bool(passed),
        "notes": notes,
        "result": result or {},
        "ts": _now(),
    }
    candidate["status"] = "review_required" if passed else "rejected"
    _log_candidate(d, candidate_id, "shadow_recorded", {"passed": bool(passed), "notes": notes})
    _save_candidates(d)
    return candidate


def record_review(candidate_id: str, verdict: str, notes: str = "") -> dict:
    """记录候选级对抗评审；sustained 后等待 Owner 审批。"""
    if verdict not in ("sustained", "revoked"):
        raise ValueError("verdict 只能是 sustained 或 revoked")
    d = load_candidates()
    candidate = _find_candidate(d, candidate_id)
    if candidate.get("status") != "review_required":
        raise ValueError(f"当前状态不允许对抗评审：{candidate.get('status')}")
    candidate["review"] = {
        "verdict": verdict,
        "notes": notes,
        "ts": _now(),
    }
    candidate["status"] = "owner_review_required" if verdict == "sustained" else "rejected"
    _log_candidate(d, candidate_id, "review_recorded", {"verdict": verdict, "notes": notes})
    _save_candidates(d)
    return candidate


def record_owner_decision(candidate_id: str, decision: str, owner: str, reason: str = "") -> dict:
    """记录 Owner 决策。只有 approve 才进入 owner_approved，仍需显式 promote。"""
    if decision not in ("approve", "reject"):
        raise ValueError("decision 只能是 approve 或 reject")
    if not owner:
        raise ValueError("owner 必填：Owner 审批不能由系统匿名完成")
    d = load_candidates()
    candidate = _find_candidate(d, candidate_id)
    if candidate.get("status") != "owner_review_required":
        raise ValueError(f"当前状态不允许 Owner 决策：{candidate.get('status')}")
    candidate["owner_decision"] = {
        "decision": decision,
        "owner": owner,
        "reason": reason,
        "ts": _now(),
    }
    candidate["status"] = "owner_approved" if decision == "approve" else "rejected"
    _log_candidate(d, candidate_id, "owner_decision_recorded", {
        "decision": decision,
        "owner": owner,
        "reason": reason,
    })
    _save_candidates(d)
    return candidate


def promote_candidate(candidate_id: str) -> dict:
    """把 Owner 已批准的候选晋升为全局 learned overlay。"""
    d = load_candidates()
    candidate = _find_candidate(d, candidate_id)
    if candidate.get("status") != "owner_approved":
        raise ValueError(f"候选未获 Owner 批准，不能晋升：{candidate.get('status')}")
    if not candidate.get("shadow_result", {}).get("passed"):
        raise ValueError("候选缺少通过的 shadow 影子运行")
    if candidate.get("review", {}).get("verdict") != "sustained":
        raise ValueError("候选缺少 sustained 对抗评审")
    if candidate["change_type"] == "update_node":
        result = apply_update(
            candidate["source_project"],
            int(candidate["target_node"]),
            candidate["proposed_change"],
            candidate["rationale"],
        )
    elif candidate["change_type"] == "add_node":
        change = candidate["proposed_change"]
        result = apply_new_node(
            candidate["source_project"],
            change["stage"],
            change["name"],
            change.get("action", ""),
            change.get("output", ""),
            change["acceptance"],
            candidate["rationale"],
        )
    else:
        raise ValueError(f"未知候选类型：{candidate['change_type']}")
    candidate["status"] = "promoted"
    candidate["promoted_at"] = _now()
    _log_candidate(d, candidate_id, "candidate_promoted", {"result": result})
    _save_candidates(d)
    return {"candidate": candidate, "promotion_result": result}


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
