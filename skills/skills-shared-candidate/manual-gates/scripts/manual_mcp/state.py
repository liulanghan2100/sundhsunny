# -*- coding: utf-8 -*-
"""项目状态持久化：每个项目一个 state.json，记录 25 节点的通过情况。"""
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parent / "projects"


def _state_path(project: str) -> Path:
    safe = "".join(c for c in project if c.isalnum() or c in "-_").strip() or "default"
    return PROJECTS_DIR / safe / "state.json"


def _lock_path(project: str) -> Path:
    return _state_path(project).with_suffix(".lock")


@contextmanager
def _project_lock(project: str, timeout: float = 10.0):
    lock = _lock_path(project)
    lock.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
        except FileExistsError:
            if time.time() - start > timeout:
                raise TimeoutError(f"manual-gates state lock timeout: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def load(project: str) -> dict:
    p = _state_path(project)
    if p.exists():
        state = json.loads(p.read_text(encoding="utf-8"))
        state.setdefault("iteration", 1)   # 迭代轮次：有节点被打回重开时 +1
        state.setdefault("history", [])    # 事件流：reopen / review 记录
        state.setdefault("track", "standard")     # v3：规模自适应轨道，旧项目默认标准轨
        state.setdefault("autonomy", "L2")        # v3：授权级别，旧项目默认阶段请示
        return state
    return {
        "project": project,
        "created": datetime.now(timezone.utc).isoformat(),
        "iteration": 1,
        "history": [],
        "nodes": {},  # node_id(str) -> {status, artifact, notes, ts, reviews: []}
        "track": "standard",
        "autonomy": "L2",
    }


def set_mode(project: str, track: str = "", autonomy: str = "", reason: str = "") -> dict:
    """v3：设置项目轨道与授权级别（reason 必填，事件留痕）。"""
    with _project_lock(project):
        state = load(project)
        if track:
            state["track"] = track
        if autonomy:
            state["autonomy"] = autonomy
        state.setdefault("history", []).append({
            "type": "set_mode",
            "track": state["track"],
            "autonomy": state["autonomy"],
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        save(project, state)
        return state


def _degrade_autonomy(state: dict, why: str) -> None:
    """v3：X-Y 校准——打回即降级授权（L3→L2→L1）。"""
    order = ["L1", "L2", "L3"]
    cur = state.get("autonomy", "L2")
    idx = max(order.index(cur) - 1, 0) if cur in order else 1
    new = order[idx]
    if new != cur:
        state["autonomy"] = new
        state.setdefault("history", []).append({
            "type": "autonomy_degrade",
            "from": cur, "to": new, "reason": why,
            "ts": datetime.now(timezone.utc).isoformat(),
        })


def save(project: str, state: dict) -> None:
    p = _state_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def record(project: str, node_id: int, status: str, artifact: str, notes: str) -> dict:
    with _project_lock(project):
        state = load(project)
        old = state["nodes"].get(str(node_id), {})
        state["nodes"][str(node_id)] = {
            "status": status,  # passed / failed
            "artifact": artifact,
            "notes": notes,
            "ts": datetime.now(timezone.utc).isoformat(),
            "reviews": old.get("reviews", []),
        }
        save(project, state)
        return state


def reopen(project: str, node_id: int, reason: str) -> dict:
    """把节点打回 pending，迭代轮次 +1，并记录事件。"""
    with _project_lock(project):
        state = load(project)
        key = str(node_id)
        prev = state["nodes"].get(key, {}).get("status", "pending")
        old = state["nodes"].get(key, {})
        state["nodes"][key] = {**old, "status": "pending", "ts": datetime.now(timezone.utc).isoformat()}
        state["iteration"] = state.get("iteration", 1) + 1
        state.setdefault("history", []).append({
            "type": "reopen",
            "node_id": node_id,
            "prev_status": prev,
            "reason": reason,
            "iteration": state["iteration"],
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        _degrade_autonomy(state, f"节点 {node_id} 打回：{reason}")
        save(project, state)
        return state


def add_review(project: str, node_id: int, verdict: str, notes: str) -> dict:
    """记录一条对抗评审结论（sustained 维持 / revoked 撤销）。"""
    with _project_lock(project):
        state = load(project)
        key = str(node_id)
        node = state["nodes"].setdefault(key, {"status": "pending", "reviews": []})
        review = {
            "verdict": verdict,
            "notes": notes,
            "iteration": state.get("iteration", 1),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        node.setdefault("reviews", []).append(review)
        state.setdefault("history", []).append({"type": "review", "node_id": node_id, **review})
        save(project, state)
        return state


def node_status(state: dict, node_id: int) -> str:
    return state.get("nodes", {}).get(str(node_id), {}).get("status", "pending")
