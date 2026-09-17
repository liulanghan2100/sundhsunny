# -*- coding: utf-8 -*-
"""经验蒸馏与晋升链路。

补齐 B.5 描述的完整流程：

    经验JSONL -> 轨迹分析 -> 聚类 -> 提炼 -> 5维评分 -> 初筛
                                                        |
                                     +------------------+------------------+
                                     v                                     v
                              达到自动批准条件                      需 Owner 审核
                                     v                                     v
                              晋升 trusted                      quarantine 待审

三条设计约束：
  1. 纯标准库。包不打包 numpy/sklearn，聚类自己实现。
  2. 只读记忆、只写知识库。不碰宪法保护路径。
  3. 每个环节可单独调用（--stage），便于观察和调试。

用法:
  python distill.py run                     跑完整链路
  python distill.py cluster                 只看聚类结果
  python distill.py score                   只看评分
  python distill.py auto-approve            把达标的自动晋升
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from kb_common import (
    KB_DIR, META_PATH, QUARANTINE_DIR, TRUSTED_DIR,
    append_meta, ensure_dirs, make_entry_id, now_iso, read_meta,
    rebuild_index,
)

# ---------------------------------------------------------------- 记忆读取

MEM_DIR = Path(os.environ.get("AGENTOS_HUB_MEMORY_DIR")
               or (KB_DIR.parent / "memory"))
MEM_JSONL = Path(os.environ.get("AGENTOS_HUB_MEMORY_JSONL")
                 or (MEM_DIR / "memory.jsonl"))

# 可蒸馏的记录类型
SOURCE_TYPES = {"lesson", "failure_case", "outcome", "decision_record"}

# 停用词：中文虚词 + 英文常见词，聚类时不参与
_STOP = set("""
的 了 和 与 及 或 在 是 有 为 对 从 到 把 被 让 使 之 其 则 乃 而 且 但 等
这 那 个 些 就 也 都 很 再 只 我 你 他 它 们 上 下 前 后 里 外 中
一 二 三 不 没 无 会 能 要 可 需 应 该 用 以 于 因 所 如 若 即
the a an and or of to in for on with is are was were be been
this that these those it its as at by from not but if then
""".split())

# 英文技术词保留；中文抽 2-4 字 n-gram
# 文件扩展名：出现在词元里说明是路径片段，不是概念
_EXT = (".json",".jsonl",".py",".md",".txt",".yaml",".yml",".toml",".csv",
        ".db",".sqlite",".log",".cfg",".ini",".xml",".html",".sh",".ps1",".exe")

# 时间戳 / 哈希 / 序列号：连续 4 位以上数字
_LONGNUM = re.compile(r"\d{4,}")


def _looks_like_junk(w: str) -> bool:
    """判断一个词元是不是"路径/文件名/ID"这类无信息量的东西。

    剔除目标：
      traj-canary-campaign-plan-cp-canary-02-20260803142140957210
      dashboard_realtime.json
      run-task-20260803032228665390-outside-workspace
      mem-20260911085419420991

    保留目标：
      dashboard / memory / evidence / 气缸 / 编译 / 受控导入
    """
    if not w or len(w) < 3:
        return True
    low = w.lower()
    # 带扩展名 -> 文件名
    if low.endswith(_EXT):
        return True
    # 含长数字串 -> 时间戳/ID/哈希
    if _LONGNUM.search(low):
        return True
    # 太长且分隔符多 -> 路径片段
    if len(low) > 24 and (low.count("-") + low.count("_")) >= 3:
        return True
    # 纯十六进制 -> 哈希
    if len(low) >= 12 and re.fullmatch(r"[0-9a-f\-_.]+", low):
        return True
    # 全数字
    if low.isdigit():
        return True
    return False


def _terms(text: str) -> set[str]:
    """从文本抽词元，用于聚类和查重。已过滤路径/ID 类噪声。"""
    t = str(text or "").lower()
    out: set[str] = set()
    # 英文/数字
    for w in re.findall(r"[a-z][a-z0-9_.\-]{2,}", t):
        if w not in _STOP and not _looks_like_junk(w):
            out.add(w)
    # 中文 n-gram（2~4 字）
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", t):
        n = len(run)
        for size in (2, 3, 4):
            if size > n:
                continue
            for i in range(n - size + 1):
                g = run[i:i + size]
                if g not in _STOP:
                    out.add(g)
    return out


def _record_text(rec: dict) -> str:
    """取一条记录里最有信息量的文本。"""
    for k in ("lesson", "fix", "why", "result", "summary", "task", "symptom"):
        v = rec.get(k)
        if v:
            return str(v)
    return ""


def load_candidates(project: str = "") -> list[dict]:
    """读取可蒸馏的记录。"""
    if not MEM_JSONL.is_file():
        return []
    rows = []
    for line in MEM_JSONL.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if project and r.get("project") != project:
            continue
        if r.get("type") not in SOURCE_TYPES and not r.get("rule_candidate"):
            continue
        text = _record_text(r)
        if not text:
            continue
        r["_text"] = text
        r["_terms"] = _terms(text)
        rows.append(r)
    return rows


# ---------------------------------------------------------------- 聚类

def cluster_hash(records: list[dict], max_terms: int = 6) -> list[list[dict]]:
    """确定性哈希聚类：取每条记录权重最高的几个词元，哈希成桶。

    优点：结果稳定、可复现、O(n)。
    缺点：相近但不完全相同的记录会分到不同桶。
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        terms = sorted(r.get("_terms") or [], key=len, reverse=True)[:max_terms]
        key = hashlib.sha256("|".join(terms).encode("utf-8")).hexdigest()[:12]
        buckets[key].append(r)
    return [v for v in buckets.values() if v]


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def cluster_overlap(records: list[dict], threshold: float = 0.4,
                    max_size: int = 40) -> list[list[dict]]:
    """代表点聚类：每条记录与"簇中心"比对，够像才进，否则另开新簇。

    为什么不用单链接（并查集）：
      单链接是"任意两点相似就合并"，会链式蔓延 ——
      A~B、B~C 会让 A 和 C 也归一类，实测 368 条里有 257 条被并成一个大簇，
      那种簇没有主题，提炼不出规则。

    代表点做法的好处：
      - 不会链式蔓延（必须与簇中心像，而不只是与某个成员像）
      - 簇有明确主题（中心就是主题）
      - 顺序影响小，结果基本稳定

    代价：O(n·k)，k 是簇数，比 O(n^2) 更省。
    """
    terms = [r.get("_terms") or set() for r in records]
    centers: list[set] = []          # 每簇的词元中心
    groups: list[list[dict]] = []

    for i, r in enumerate(records):
        t = terms[i]
        if not t:
            # 无词元 -> 单独成簇，不参与合并
            groups.append([r])
            centers.append(set())
            continue

        best_j, best_sim = -1, 0.0
        for j, c in enumerate(centers):
            if not c or len(groups[j]) >= max_size:
                continue
            s = _jaccard(t, c)
            if s > best_sim:
                best_j, best_sim = j, s

        if best_j >= 0 and best_sim >= threshold:
            groups[best_j].append(r)
            # 更新中心：并集会让中心越滚越大，改用交集保持主题聚焦
            centers[best_j] = centers[best_j] & t if centers[best_j] else set(t)
            if not centers[best_j]:
                centers[best_j] = set(t)
        else:
            groups.append([r])
            centers.append(set(t))

    return groups


def cluster_density(records: list[dict], min_pts: int = 2,
                    eps: float = 0.28) -> list[list[dict]]:
    """密度聚类（DBSCAN 思路）：词元距离 <= eps 的邻域内点数 >= min_pts 才算核心点。

    与单链接的区别：能识别"噪声点"——落单的记录不强行归类。
    """
    n = len(records)
    terms = [r.get("_terms") or set() for r in records]
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = 1.0 - _jaccard(terms[i], terms[j])
            dist[i][j] = dist[j][i] = d

    neighbors = [[j for j in range(n) if dist[i][j] <= eps] for i in range(n)]
    core = [i for i in range(n) if len(neighbors[i]) >= min_pts]

    labels = [-1] * n          # -1 = 噪声
    cid = 0
    for i in core:
        if labels[i] != -1:
            continue
        labels[i] = cid
        queue = list(neighbors[i])
        while queue:
            j = queue.pop()
            if labels[j] == -1:
                labels[j] = cid
                if j in core:
                    queue.extend(neighbors[j])
        cid += 1

    groups: dict[int, list[dict]] = defaultdict(list)
    noise: list[dict] = []
    for i, r in enumerate(records):
        if labels[i] == -1:
            noise.append(r)
        else:
            groups[labels[i]].append(r)
    out = [v for v in groups.values() if v]
    if noise:
        out.append(noise)      # 噪声单独成组，标记出来
    return out


def cluster(records: list[dict], method: str = "overlap",
            **kw) -> list[list[dict]]:
    if method == "hash":
        return cluster_hash(records, **kw)
    if method == "density":
        return cluster_density(records, **kw)
    return cluster_overlap(records, **kw)


# ---------------------------------------------------------------- 规则提炼

def extract_rule(group: list[dict], max_terms: int = 8) -> dict:
    """从一个簇提炼一条规则候选。"""
    # 共同词元 = 该簇的"主题"
    common: set[str] = None
    for r in group:
        t = r.get("_terms") or set()
        common = t if common is None else (common & t)
    common = common or set()

    # 关键词：优先"看起来像概念"的词元
    # 排序依据：长度适中（4-14）+ 不含分隔符 > 其他
    def _kw_rank(w: str) -> tuple:
        sep = w.count("-") + w.count("_")
        good_len = 4 <= len(w) <= 14
        return (sep, not good_len, -len(w))
    keywords = sorted(common, key=_kw_rank)[:max_terms]

    # 代表文本：取 importance 最高那条
    def imp(r):
        return (1.0 if r.get("rule_candidate") else 0.0,
                {"failure_case": 0.8, "lesson": 0.8, "outcome": 0.8,
                 "decision_record": 0.65}.get(r.get("type", ""), 0.45))
    lead = max(group, key=imp)

    projects = sorted({r.get("project", "") for r in group if r.get("project")})
    types = sorted({r.get("type", "") for r in group if r.get("type")})
    statuses = [r.get("status", "") for r in group if r.get("status")]

    return {
        "supporting_count": len(group),
        "keywords": keywords,
        "lead_text": _record_text(lead)[:600],
        "lead_id": lead.get("id", ""),
        "memory_ids": [r.get("id", "") for r in group if r.get("id")],
        "projects": projects,
        "types": types,
        "success_ratio": (sum(1 for s in statuses if s == "success") / len(statuses)
                          if statuses else 0.0),
        "has_actionable": any(r.get("next_retrieval_query") or r.get("fix")
                              for r in group),
    }


# ---------------------------------------------------------------- 5 维评分

# 阈值：达到即自动批准；低于则进待审
AUTO_APPROVE_THRESHOLD = 3.6     # 满分 5.0
MIN_EVIDENCE = 2                 # 至少几条记录支撑

DIM_NAMES = (
    "证据强度",    # 多少条记录支撑
    "可复用性",    # 是否跨项目/泛化
    "新颖性",      # 与现有知识库的重合度（越低越新）
    "可执行性",    # 有没有具体动作
    "来源可靠",    # 支撑记录的成功率
)


def score_rule(rule: dict, existing_kb: list[dict] | None = None) -> dict:
    """5 维评分，每维 0-1，返回明细与总分。"""
    # 1) 证据强度：2 条起步，5 条满分
    n = rule.get("supporting_count", 0)
    evidence = min(1.0, max(0.0, (n - 1) / 4.0))

    # 2) 可复用性：跨项目 + 关键词够泛化
    npj = len(rule.get("projects") or [])
    kw = len(rule.get("keywords") or [])
    reuse = min(1.0, 0.5 * min(1.0, npj / 2.0) + 0.5 * min(1.0, kw / 5.0))

    # 3) 新颖性：与知识库现有条目比对，重合越低越新
    novelty = 1.0
    if existing_kb:
        mine = set(rule.get("keywords") or [])
        best = 0.0
        for e in existing_kb:
            other = _terms(f"{e.get('title','')} {e.get('summary','')}")
            if other:
                best = max(best, _jaccard(mine, other))
        novelty = max(0.0, 1.0 - best)

    # 4) 可执行性
    action = 1.0 if rule.get("has_actionable") else (0.5 if rule.get("lead_text") else 0.0)

    # 5) 来源可靠：有状态的记录里成功占比；无状态给中性分
    sr = rule.get("success_ratio", 0.0)
    has_status = bool(rule.get("success_ratio") is not None)
    reliable = sr if sr > 0 else 0.6

    dims = {
        "证据强度": round(evidence, 3),
        "可复用性": round(reuse, 3),
        "新颖性": round(novelty, 3),
        "可执行性": round(action, 3),
        "来源可靠": round(reliable, 3),
    }
    total = round(sum(dims.values()), 3)

    # 自动批准条件：总分达标 + 证据够
    auto_ok = (total >= AUTO_APPROVE_THRESHOLD and n >= MIN_EVIDENCE)

    return {
        "dims": dims,
        "total": total,
        "max": 5.0,
        "auto_approve": auto_ok,
        "reason": (
            f"总分 {total}/5.0 >= {AUTO_APPROVE_THRESHOLD}，证据 {n} 条 >= {MIN_EVIDENCE}"
            if auto_ok else
            f"总分 {total}/5.0（阈值 {AUTO_APPROVE_THRESHOLD}），证据 {n} 条（需 >= {MIN_EVIDENCE}）"
        ),
    }


# ---------------------------------------------------------------- 落库

def write_rule(rule: dict, score: dict, auto: bool = True) -> dict:
    """把规则候选写入知识库。

    达标 -> trusted（已采信）
    未达标 -> quarantine（待审）
    """
    ensure_dirs()
    status = "trusted" if (auto and score["auto_approve"]) else "quarantine"
    title = " / ".join(rule.get("keywords", [])[:3]) or "未命名规则"
    entry_id = make_entry_id(f"rule-{title}")

    body = [
        f"# {title}",
        "",
        f"- 来源：记忆蒸馏（{rule.get('supporting_count')} 条支撑）",
        f"- 评分：{score['total']}/5.0",
        f"- 判定：{score['reason']}",
        "",
        "## 评分明细",
        "",
    ]
    for k, v in score["dims"].items():
        body.append(f"- {k}：{v}")
    body += [
        "",
        "## 规则内容",
        "",
        rule.get("lead_text", ""),
        "",
        "## 关键词",
        "",
        ", ".join(rule.get("keywords", [])) or "（无）",
        "",
        "## 支撑记录",
        "",
    ]
    for mid in rule.get("memory_ids", [])[:20]:
        body.append(f"- {mid}")
    body.append("")

    out_dir = TRUSTED_DIR / "playbooks" if status == "trusted" else QUARANTINE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{entry_id}.md"
    out_path.write_text("\n".join(body), encoding="utf-8")

    row = {
        "id": entry_id,
        "title": title,
        "type": "playbook",
        "status": status,
        "trust_level": "reviewed" if status == "trusted" else "unreviewed",
        "source_url": "",
        "source_path": f"memory://distill/{rule.get('lead_id','')}",
        "tags": rule.get("keywords", [])[:8],
        "summary": rule.get("lead_text", "")[:200],
        "path": str(out_path.relative_to(Path(out_path.anchor))),
        "collected_at": now_iso(),
        "reviewed_at": now_iso() if status == "trusted" else "",
        "score": score["total"],
    }
    # path 用相对 KB 根的形式，与 add.py 保持一致
    try:
        row["path"] = str(out_path.relative_to(KB_DIR.parent.parent))
    except ValueError:
        row["path"] = str(out_path)

    append_meta(row)
    return {"id": entry_id, "status": status, "path": str(out_path),
            "score": score["total"]}


# ---------------------------------------------------------------- 主流程

def run(project: str = "", method: str = "overlap", limit: int = 20,
        auto: bool = True, write: bool = True) -> dict:
    """跑完整链路：加载 -> 聚类 -> 提炼 -> 评分 -> 初筛 -> 落库。"""
    records = load_candidates(project)
    if not records:
        return {"status": "empty", "message": "没有可蒸馏的记录"}

    groups = cluster(records, method=method)
    # 大簇优先
    groups.sort(key=len, reverse=True)

    existing = read_meta()
    results = []
    for g in groups[:limit]:
        rule = extract_rule(g)
        score = score_rule(rule, existing)
        item = {"rule": rule, "score": score}
        if write:
            item["written"] = write_rule(rule, score, auto=auto)
        results.append(item)

    if write:
        rebuild_index()

    auto_n = sum(1 for r in results if r["score"]["auto_approve"])
    return {
        "status": "ok",
        "source_records": len(records),
        "clusters": len(groups),
        "processed": len(results),
        "auto_approved": auto_n,
        "pending_review": len(results) - auto_n,
        "threshold": AUTO_APPROVE_THRESHOLD,
        "results": results,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="经验蒸馏与晋升链路")
    ap.add_argument("stage", nargs="?", default="run",
                    choices=["run", "cluster", "score", "auto-approve"])
    ap.add_argument("--project", default="")
    ap.add_argument("--method", default="overlap",
                    choices=["overlap", "hash", "density"])
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--no-write", action="store_true", help="只算不落库")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.stage == "cluster":
        recs = load_candidates(args.project)
        gs = cluster(recs, method=args.method)
        out = {"records": len(recs), "clusters": len(gs),
               "sizes": sorted((len(g) for g in gs), reverse=True)[:20]}
    elif args.stage == "score":
        r = run(args.project, args.method, args.limit, auto=False, write=False)
        out = {"processed": r.get("processed", 0),
               "results": [{"keywords": x["rule"]["keywords"],
                            "total": x["score"]["total"],
                            "auto": x["score"]["auto_approve"]}
                           for x in r.get("results", [])]}
    else:
        out = run(args.project, args.method, args.limit,
                  auto=True, write=not args.no_write)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
