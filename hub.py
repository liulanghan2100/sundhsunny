#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agentos-hub —— 单一任务入口。

一个任务进来，走同一条流水线：

    准入分级(intake) -> 三源检索(经验记忆/知识库/代码图谱) -> 任务简报 -> 门禁 -> 经验回流

设计约束（来自对 agentos-slim 的分析，逐条规避）：
  1. 不打包第三方依赖，只用 requirements.txt 声明版本，pip 标准安装。
     原版把 mcp 1.30 塞进 _runtime_deps（52MB），并被迫改 gate.py 源码，
     只是为了兼容一个本就该换掉的解释器。
  2. 路径一律从 config.yaml 读，不依赖 cwd、不依赖 parents[N] 的层级假设。
     原版 manual-gates 的 PROJECT_ROOT=parents[4] 会把门禁命令的 cwd
     锚在骨架包自身，而不是用户的真实项目目录。
  3. doctor 是只读的，不产生任何副作用。
  4. 技能路由同时匹配 name 与 description（原版只匹配英文名，中文关键词必然失配）。
  5. 每个能力惰性加载：只用基础命令时，不需要装 mcp。

用法:
  python hub.py doctor                     环境自检（只读）
  python hub.py ask "把 A 股日报自动化"      单一任务入口（核心编排）
  python hub.py recall "PLC 代码生成"        记忆检索（4 种检索方式）
  python hub.py kb "agent memory"           知识库检索
  python hub.py graph search_graph ...      代码知识图谱
  python hub.py skills --keyword 仓颉        技能路由
  python hub.py gate strategy plan_next ...  门禁直通
  python hub.py learn                       经验蒸馏
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HUB = Path(__file__).resolve().parent
CONFIG_PATH = HUB / "config.yaml"


# ---------------------------------------------------------------- 配置

def load_config() -> dict[str, Any]:
    """读 config.yaml。不依赖 cwd —— 始终相对 hub.py 自身解析。"""
    if not CONFIG_PATH.exists():
        raise SystemExit(f"缺少配置文件: {CONFIG_PATH}")
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "缺少 PyYAML。请先安装依赖:\n"
            f"  {sys.executable} -m pip install -r requirements.txt"
        )
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


_CFG: dict[str, Any] | None = None


def cfg() -> dict[str, Any]:
    global _CFG
    if _CFG is None:
        _CFG = load_config()
    return _CFG


def path_of(rel: str) -> Path:
    """把配置里的相对路径解析成绝对路径（相对 HUB，不相对 cwd）。"""
    p = Path(rel)
    return p if p.is_absolute() else (HUB / p).resolve()


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- 配置辅助

_COMPAT_CACHE: dict[str, str] | None = None


def _compat_map() -> dict[str, str]:
    """旧目录名 -> 新位置 的映射（config.layers.compat）。

    源库里技能目录叫 `04_技能包`，打包后叫 `skills`。
    任务描述或历史文档里出现旧名时，靠它改写到位，
    否则会出现"指着一个不存在的目录谈事"。
    """
    global _COMPAT_CACHE
    if _COMPAT_CACHE is None:
        try:
            raw = (cfg().get("layers") or {}).get("compat") or {}
            _COMPAT_CACHE = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            _COMPAT_CACHE = {}
    return _COMPAT_CACHE


def compat_rewrite(text: str) -> str:
    """把文本里的旧目录名改成新位置。没有旧名时原样返回。"""
    m = _compat_map()
    if not m or not text:
        return text
    out = str(text)
    for old, new in m.items():
        if old and old in out:
            out = out.replace(old, new)
    return out


def _kb_dirs() -> dict[str, Path]:
    """知识库各目录（config.knowledge）。

    返回 dir / trusted_dir / quarantine_dir 三项的绝对路径。
    trusted 与 quarantine 是两个"证据等级"的存放处：
    新录入的先进 quarantine，人工确认后才晋升到 trusted。
    """
    kd = cfg().get("knowledge") or {}
    out: dict[str, Path] = {}
    for key in ("dir", "trusted_dir", "quarantine_dir", "meta", "index"):
        v = kd.get(key)
        if v:
            out[key] = path_of(v)
    if "dir" not in out:
        out["dir"] = HUB / "data" / "knowledge"
    # 兜底：没配就按约定推导
    out.setdefault("trusted_dir", out["dir"] / "cases")
    out.setdefault("quarantine_dir", out["dir"] / "quarantine")
    return out


def _match_fields() -> tuple[str, ...]:
    """技能路由匹配哪些字段（config.skills_config.match_fields）。

    注意：`aliases`（中文别名表）无论配置怎么写都会保留。
    理由：像 cangjie-thinking-distiller 这种技能，名字和描述都是英文，
    中文用户只能靠别名命中 —— 去掉它等于中文搜索失效
    （实测"仓颉"会从 1 个命中掉到 0 个）。
    """
    fields: list[str] = []
    try:
        v = (cfg().get("skills_config") or {}).get("match_fields")
        if isinstance(v, (list, tuple)) and v:
            fields = [str(x) for x in v]
    except Exception:
        fields = []

    if not fields:
        fields = ["name", "description"]

    # 别名表是中文可用的兜底，永远参与
    if "aliases" not in fields:
        fields.append("aliases")
    return tuple(fields)


def _shadow_category() -> str:
    """shadow 分类在登记表里的键名（config.skills_config.categories.shadow）。"""
    try:
        cats = (cfg().get("skills_config") or {}).get("categories") or {}
        return str(cats.get("shadow") or "shadow")
    except Exception:
        return "shadow"


def _gate_canonical() -> Path:
    """门禁正本目录（config.gates.canonical）。"""
    try:
        v = (cfg().get("gates") or {}).get("canonical")
        if v:
            return path_of(v)
    except Exception:
        pass
    return HUB / "skills" / "manual-gates" / "scripts" / "manual_mcp"


def _graph_provider() -> str:
    """图谱提供方标识（config.graph.provider），用于自检与提示。"""
    try:
        return str((cfg().get("graph") or {}).get("provider") or "codebase-memory-mcp")
    except Exception:
        return "codebase-memory-mcp"


# ---------------------------------------------------------------- 惰性加载

def _load_core():
    """治理核：准入分级 / 风险分类 / 深度策略。纯标准库，无第三方依赖。"""
    if str(HUB / "core") not in sys.path:
        sys.path.insert(0, str(HUB / "core"))
    from Agent_OS_Core.policy.unified_intake import build_intake
    from Agent_OS_Core.policy.risk_classifier import classify_risk
    from Agent_OS_Core.policy.depth_policy import depth_policy
    return build_intake, classify_risk, depth_policy


_MEMORY_MOD = None


def _load_memory():
    """经验记忆引擎。需要 mcp（PyPI 标准安装，不随包分发）。"""
    global _MEMORY_MOD
    if _MEMORY_MOD is not None:
        return _MEMORY_MOD

    m = cfg()["layers"]["engine"]["memory"]
    root = path_of(m)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # 记忆目录改为配置驱动（原实现硬编码 ROOT/09_投研/experience_memory）
    d = cfg()["memory"]
    os.environ.setdefault("AGENTOS_HUB_MEMORY_DIR", str(path_of(d["dir"])))
    for key, val in (("AGENTOS_HUB_MEMORY_JSONL", d["jsonl"]),
                     ("AGENTOS_HUB_MEMORY_INDEX", d["index"]),
                     ("AGENTOS_HUB_MEMORY_VECTOR", d["vector"])):
        os.environ.setdefault(key, str(path_of(val)))

    try:
        from experience_memory_mcp import common as C
    except ImportError as e:
        raise SystemExit(
            f"经验记忆引擎不可用: {e}\n"
            f"请先安装依赖: {sys.executable} -m pip install -r requirements.txt\n"
            "（若已安装 mcp 2.x，需降到 1.x：mcp 2.x 移除了 mcp.server.fastmcp）"
        )
    _MEMORY_MOD = C
    return C


def _memory_tools():
    """拿到记忆引擎的工具表，用于直接调用。"""
    C = _load_memory()
    srv = C.build_server()
    tm = srv._tool_manager
    return tm._tools


def _call_tool(tools, name: str, **kwargs) -> str:
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(tools[name].run(kwargs, None, None))
    finally:
        loop.close()


def _try_json(s: Any) -> Any:
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return s


# ---------------------------------------------------------------- 能力：知识图谱

def graph_candidates() -> list[Path]:
    """按优先级列出 codebase-memory-mcp 可执行文件的位置。

    包内自带优先（tools/ 下捆绑），其次环境变量，最后系统安装。
    这样包可以独立带走，同时兼容目标机器已装好的情况。
    """
    g = cfg().get("graph") or {}
    out: list[Path] = []

    # 1) 包内自带
    bundled = g.get("bundled")
    if bundled:
        out.append(path_of(bundled))
    # 约定位置（即使 config 未写也试）
    for rel in ("tools/codebase-memory-mcp/bin/codebase-memory-mcp.exe",
                "tools/codebase-memory-mcp.exe"):
        out.append(path_of(rel))

    # 2) 环境变量
    env = os.environ.get("CODEBASE_MEMORY_MCP_EXE")
    if env:
        out.append(Path(env))

    # 3) 系统安装（原 config.cli 位置）
    cli = g.get("cli")
    if cli:
        out.append(Path(cli))
    out.append(Path.home() / ".local" / "bin" / "codebase-memory-mcp.exe")

    # 去重保序
    seen, uniq = set(), []
    for p in out:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def graph_available() -> tuple[bool, str]:
    g = cfg().get("graph") or {}
    provider = _graph_provider()
    if not g.get("enabled"):
        return False, f"{provider} 未启用"
    cands = graph_candidates()
    for p in cands:
        if p.exists():
            src = "包内自带" if "tools" in str(p).replace("\\", "/") else "系统安装"
            return True, str(p) + f" ({src})"
    return False, (f"{provider} 未找到可执行文件，位置尝试: "
                   + "; ".join(str(p) for p in cands))


def _resolve_project_arg(args: dict) -> dict:
    """把 args["project"] 从路径/片段解析成真实项目名。

    只在给的值"不是已知项目名"时才去查表 —— 精确命中就直接放行，
    省掉一次 list_projects 子进程调用。
    """
    spec = args.get("project")
    if not spec:
        return args

    # project 也可能是列表（跨项目查询工具）
    if isinstance(spec, (list, tuple)):
        resolved = []
        for s in spec:
            r = _resolve_one_project(str(s))
            if r:
                resolved.append(r)
        if resolved:
            args["project"] = resolved[0] if len(resolved) == 1 else resolved
        return args

    r = _resolve_one_project(str(spec))
    if r:
        args["project"] = r
    return args


def _resolve_one_project(spec: str) -> str:
    """解析单个项目标识；解析不出就原样返回（让对方自己报错，别吞掉）。"""
    try:
        pros = graph_projects()
    except Exception:
        return spec
    if not pros:
        return spec

    # 精确命中已知项目名 -> 直接用，不查表
    for p in pros:
        if str(p.get("name", "")) == spec:
            return spec

    try:
        res = graph_resolve_project(spec, pros)
    except Exception:
        return spec

    ms = res.get("matches") or []
    if ms:
        return ms[0].get("name") or spec
    return spec


def graph_call(tool: str, args: dict | None = None, timeout: int = 60) -> dict[str, Any]:
    """调用代码知识图谱 CLI。失败时返回结构化错误，不抛异常打断流水线。"""
    ok, detail = graph_available()
    if not ok:
        return {"ok": False, "error": detail}
    # detail 形如 "<path> (来源)"，取路径部分
    exe = detail.rsplit(" (", 1)[0]

    # 项目名解析：图谱的项目名是动态派生的（给了 --name 就是那个名字，
    # 没给就是绝对路径 slug），换机器/换目录就变。所以这里把
    # "路径 / 名字片段 / 精确名字" 统一换成当前机器上的真实项目名。
    args = _resolve_project_arg(dict(args or {}))

    payload = json.dumps(args, ensure_ascii=False)
    # 缓存目录：优先用包内自带（CBM_CACHE_DIR 是实测有效的重定向变量）。
    # 包内没有则用默认 ~/.cache/codebase-memory-mcp。
    env = dict(os.environ)
    g = cfg().get("graph") or {}
    cache = g.get("cache")
    if cache:
        cp = path_of(cache)
        if cp.exists():
            env["CBM_CACHE_DIR"] = str(cp)
    try:
        r = subprocess.run(
            [exe, "cli", tool, payload],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{tool} 超时({timeout}s)"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    out = (r.stdout or "").strip()
    # CLI 会先打一行 level=info 日志，取最后一个 JSON 行
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            return {"ok": True, "data": _try_json(line)}
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or out)[-300:]}
    return {"ok": True, "data": out}


def graph_projects() -> list[dict]:
    r = graph_call("list_projects")
    if not r.get("ok"):
        return []
    d = r["data"]
    return d.get("projects", []) if isinstance(d, dict) else []


def _norm_path(p) -> str:
    """路径归一化：统一分隔符、去尾斜杠、小写（Windows 不区分大小写）。"""
    s = str(p or "").strip().replace("\\", "/").rstrip("/")
    return s.lower()


def _slug_path(p) -> str:
    """按图谱的派生规则把路径转成项目名。

    没给 --name 建索引时，图谱就是这么派生的：
      C:/a/b/MyProject  ->  C-a-b-MyProject
    用于反查"这个名字是不是我这台机器上那个路径派生的"。
    """
    s = str(p or "").strip().replace("\\", "/")
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        elif ch in "/:.":
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.lower()


def graph_resolve_project(spec: str, projects: list[dict] | None = None) -> dict:
    """把"路径 或 名字"解析成图谱里的真实项目名。

    为什么需要它：图谱项目名是动态派生的（给了 --name 就是那个名字，
    没给就是绝对路径 slug 化），换机器必变，写死名字必然失效。
    所以调用方应该给路径，由这里查表换算出当前机器上的项目名。

    返回 {"matches": [项目dict...], "by": 命中方式, "spec": 原始输入}
    matches 为空表示图谱里没有这个项目（可能尚未建索引）。
    """
    if not spec:
        return {"matches": [], "by": "empty", "spec": spec}

    pros = projects if projects is not None else graph_projects()
    if not pros:
        return {"matches": [], "by": "no_projects", "spec": spec}

    raw = str(spec).strip()
    norm = _norm_path(raw)
    slug = _slug_path(raw)

    # 1) 路径完全相等
    m = [p for p in pros if _norm_path(p.get("root_path")) == norm]
    if m:
        return {"matches": m, "by": "path_exact", "spec": raw}

    # 2) 目录包含关系（哪边是父都算，取最接近的）
    m = []
    for p in pros:
        rp = _norm_path(p.get("root_path"))
        if rp and (norm.startswith(rp + "/") or rp.startswith(norm + "/")):
            m.append(p)
    if m:
        m.sort(key=lambda p: len(_norm_path(p.get("root_path"))), reverse=True)
        return {"matches": m, "by": "path_contains", "spec": raw}

    # 3) 名字完全相等（忽略大小写）
    m = [p for p in pros if str(p.get("name", "")).lower() == raw.lower()]
    if m:
        return {"matches": m, "by": "name_exact", "spec": raw}

    # 4) slug 相等 —— 兜住"名字就是这条路径派生出来的"情况
    m = [p for p in pros if _slug_path(p.get("root_path")) == slug
         or str(p.get("name", "")).lower() == slug]
    if m:
        return {"matches": m, "by": "slug", "spec": raw}

    # 5) 名字包含片段（模糊，可能多个）
    m = [p for p in pros if raw.lower() in str(p.get("name", "")).lower()]
    if m:
        return {"matches": m, "by": "name_partial", "spec": raw}

    return {"matches": [], "by": "not_found", "spec": raw}


# 图谱检索时忽略的常见虚词（避免把 "how to fix the thing" 拆成一堆无意义词元）
_GRAPH_STOPWORDS = frozenset({
    "the", "and", "for", "with", "how", "what", "this", "that", "from",
    "into", "then", "else", "not", "all", "any", "can", "use", "using",
})


def _graph_terms(pattern: str, max_terms: int = 6) -> list[str]:
    """从自由文本里抽取可用于匹配代码符号的词元。

    为什么需要这一步：符号名是英文/数字标识符，而任务描述往往是整句话。
    原实现把整句直接当正则（'.*Openness 硬件配置怎么改.*'），
    符号名里不可能出现整句话 —— 中文任务因此 100% 零命中。

    这里改成：抽出长度 >= 3 的英文/数字词元，去重、限量，
    再用 (a|b|c) 组合成一次查询。中文词元对符号名无意义，直接丢弃
    （中文符号名会被下面的原样回退覆盖）。
    """
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", pattern or "")
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        low = t.lower()
        if low in _GRAPH_STOPWORDS or low in seen:
            continue
        seen.add(low)
        out.append(t)
        if len(out) >= max_terms:
            break

    # 没有英文词元（纯中文任务）：退回原名，至少让图谱有机会匹配中文符号
    if not out:
        raw = " ".join((pattern or "").split())
        return [raw] if raw else []
    return out


def _graph_name_pattern(pattern: str) -> str:
    """把自由文本转成 name_pattern 正则。"""
    terms = _graph_terms(pattern)
    if not terms:
        return ".*"
    if len(terms) == 1:
        return f".*{re.escape(terms[0])}.*"
    return ".*(" + "|".join(re.escape(t) for t in terms) + ").*"


def _interleave(groups: list[list], limit: int) -> list:
    """把多个列表轮转合并，避免某一个大列表独占前 limit 个名额。

    例：A=[a1,a2,a3] B=[b1] C=[c1,c2]
        结果 = a1,b1,c1,a2,c2,a3
    这样即便 A 命中很多，B、C 也能出现在结果里。
    """
    out: list = []
    i = 0
    while len(out) < limit:
        progressed = False
        for g in groups:
            if i < len(g):
                out.append(g[i])
                progressed = True
                if len(out) >= limit:
                    return out
        if not progressed:
            break
        i += 1
    return out


def graph_search(pattern: str, limit: int = 8, per_project: int = 0) -> dict[str, Any]:
    """在所有已索引项目里按名字模式搜符号。

    pattern 可以是自由文本（会被拆成关键词，见 _graph_terms），
    也可以是调用方已经写好的正则。

    为什么每个项目都要查：
      旧实现凑够 limit 条就 break，导致排在后面的项目从未被搜索 ——
      实测搜 "Applier" 只返回第一个项目的结果，主库 39430 节点从未命中。
      现在改为全部查完，再按轮转方式公平取前 limit 条。
    """
    # 每个项目最多取多少条：默认跟随 limit（至少 20），
    # 避免 limit 放大时反而因为上限太低而少给结果。
    cap = per_project if per_project > 0 else max(20, limit)

    projects = graph_projects()
    if not projects:
        return {"ok": False, "error": "图谱中没有已索引的项目"}

    name_pattern = _graph_name_pattern(pattern)

    # 项目按节点数降序：截断时优先保留主库（大项目）的结果
    ordered = sorted(projects, key=lambda p: -(p.get("nodes") or 0))

    groups: list[list] = []
    per_counts: dict[str, int] = {}
    scanned = 0
    for p in ordered:
        name = p.get("name")
        if not name:
            continue
        scanned += 1
        r = graph_call("search_graph",
                       {"project": name, "name_pattern": name_pattern})
        if not r.get("ok"):
            per_counts[name] = -1        # 标记查询失败
            continue
        d = r["data"]
        items = d.get("results") or d.get("matches") or d.get("nodes") or []
        if isinstance(d, list):
            items = d
        got = [{"project": name, "item": it} for it in items[:cap]]
        per_counts[name] = len(got)
        if got:
            groups.append(got)

    hits = _interleave(groups, limit)
    return {
        "ok": True,
        "hits": hits,
        "scanned_projects": scanned,
        "projects_with_hits": len(groups),
        "per_project_counts": per_counts,
        "terms": _graph_terms(pattern),
        "name_pattern": name_pattern,
    }

# ---------------------------------------------------------------- 能力：三源检索

def recall_memory(query: str, limit: int = 5, project: str = "") -> dict[str, Any]:
    """经验记忆检索：先尝试向量（语义），失败回退关键词。"""
    try:
        tools = _memory_tools()
    except SystemExit as e:
        return {"ok": False, "error": str(e)}

    for name in ("vector_search_memory", "search_memory"):
        try:
            raw = _call_tool(tools, name, query=query, limit=limit, project=project)
            d = _try_json(raw)
            if isinstance(d, dict) and d.get("hits"):
                return {"ok": True, "via": name, "count": d.get("count", len(d["hits"])),
                        "hits": d["hits"][:limit]}
        except Exception:
            continue
    return {"ok": True, "via": "none", "count": 0, "hits": []}


def _kb_query_text(query: str, max_terms: int = 12) -> str:
    """把自由文本转成知识库可用的全文检索式。

    底层是 SQLite FTS，多个词之间默认按 AND 处理，而且中文不会自动分词。
    实测：
      'PLC 代码'            -> 0 条（要求同篇含两词）
      'PLC OR 代码'         -> 4 条
      '数学模型选型怎么做'   -> 0 条（整段含虚词，库里没有这个串）
      '数学模型选型'         -> 1 条（剥虚词后命中）
      '数学 OR 模型 OR 选型' -> 3 条（二字词召回最广）

    所以策略是三层 OR：剥虚词片段 + 该片段的 2 字滑窗 + 英文词元。
    精确片段排前面（BM25 会自然给它更高分），二字词负责兜底召回。
    """
    text = " ".join(str(query or "").split())
    if not text:
        return ""

    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        low = term.lower()
        if term and low not in seen and len(terms) < max_terms:
            seen.add(low)
            terms.append(term)

    # 1) 英文/数字词元（原样，不拆）
    for t in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{1,}", text):
        add(t)

    # 2) 中文：剥虚词 -> 连续片段 -> 整段 + 2 字滑窗
    cleaned = text
    for w in sorted(_CN_SPLIT, key=len, reverse=True):
        cleaned = cleaned.replace(w, "|")
    cleaned = "".join(
        "|" if (ch in _CN_SPLIT_CHARS or ch == "|") else ch
        for ch in cleaned
    )

    for run in re.findall(r"[\u4e00-\u9fff]{2,}", cleaned):
        add(run)                      # 整段（最精确）
        for i in range(len(run) - 1):  # 2 字滑窗（兜底召回）
            add(run[i:i + 2])

    if not terms:
        return ""
    if len(terms) == 1:
        return terms[0]
    return " OR ".join(f'"{t}"' for t in terms)


def recall_knowledge(query: str, limit: int = 5) -> dict[str, Any]:
    """知识库检索（quarantine + trusted）。"""
    base = path_of(cfg()["layers"]["engine"]["knowledge"]) / "knowledge-base" / "scripts"
    q = base / "query.py"
    if not q.exists():
        return {"ok": False, "error": f"未找到 query.py: {q}"}
    # 知识库目录：全部来自 config.knowledge（含 trusted/quarantine）
    kd = _kb_dirs()
    env = dict(os.environ)
    env["AGENTOS_HUB_KB_DIR"] = str(kd["dir"])
    env["AGENTOS_HUB_KB_META"] = str(kd.get("meta") or (kd["dir"] / "meta.jsonl"))
    env["AGENTOS_HUB_KB_INDEX"] = str(kd.get("index") or (kd["dir"] / "index.sqlite"))
    # 这两个目录原本只在 config 里写着、没人读；脚本自己拼 KB_DIR/xxx。
    # 现在显式传下去，改配置就能改位置。
    env["AGENTOS_HUB_KB_TRUSTED"] = str(kd["trusted_dir"])
    env["AGENTOS_HUB_KB_QUARANTINE"] = str(kd["quarantine_dir"])
    fts = _kb_query_text(query)
    if not fts:
        return {"ok": True, "count": 0, "entries": []}
    try:
        r = subprocess.run(
            [sys.executable, str(q), fts],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, cwd=str(HUB), env=env,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out = (r.stdout or "").strip()
    if r.returncode != 0 and not out:
        return {"ok": False, "error": (r.stderr or "")[-300:]}
    # 输出是若干 YAML 文档，按 --- 切块统计
    blocks = [b.strip() for b in out.split("\n---\n") if b.strip()]
    entries = []
    for b in blocks[:limit]:
        e = {}
        for line in b.splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                e[k.strip()] = v.strip()
        if e:
            entries.append(e)
    return {"ok": True, "count": len(entries), "entries": entries}


def recall(query: str, limit: int = 5, use_graph: bool = True) -> dict[str, Any]:
    """三源合并检索：经验记忆 + 知识库 + 代码图谱。任一源失败不影响其它源。"""
    result: dict[str, Any] = {"query": query}
    result["memory"] = recall_memory(query, limit=limit)
    result["knowledge"] = recall_knowledge(query, limit=limit)
    if use_graph:
        r = graph_search(query, limit=limit)
        result["graph"] = r
    # 汇总
    m = len(result["memory"].get("hits") or [])
    k = result["knowledge"].get("count", 0)
    g = len(result.get("graph", {}).get("hits") or [])
    result["summary"] = {"memory_hits": m, "knowledge_hits": k, "graph_hits": g,
                         "total": m + k + g}
    return result


# ---------------------------------------------------------------- 检索结果压缩

def _clip(value, width):
    """压成单行短文本。原文往往很长，直接进简报会挤爆上下文。"""
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text if len(text) <= width else text[: max(0, width - 1)] + "..."


def _num(value):
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _short_ts(value):
    """时间戳压成 'YYYY-MM-DD HH:MM'。

    直接按字符数截会切出 '2026-09-12T14:42:2...' 这种残缺值，
    既不好读也丢了信息。这里解析出需要的部分再拼。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    # ISO 形如 2026-09-12T14:42:21.918251+00:00
    if len(text) >= 16 and text[4] == "-" and text[10] in ("T", " "):
        return f"{text[:10]} {text[11:16]}"
    return text[:16]


def _brief_evidence(recall_result, limit=3, width=160):
    """把三源检索的原始命中压成简报可读的摘要。

    为什么要这一步：recall() 返回的是完整原始记录（单条经验可能有上千字），
    直接塞进简报既读不动也挤爆上下文。这里只保留"能据此判断要不要深挖"的字段，
    并给出取回全文的命令 —— 想看细节再去拿。

    三个源各自计取 limit 条，互不挤占；任一源为空不影响其它源。
    """
    shown_any = False
    out = {}

    # --- 经验记忆 ---
    mem = recall_result.get("memory") or {}
    mem_hits = []
    for h in (mem.get("hits") or [])[:limit]:
        if not isinstance(h, dict):
            continue
        item = {
            "id": h.get("id"),
            "ts": _short_ts(h.get("ts")),
            "type": h.get("type"),
            "project": h.get("project"),
            "summary": _clip(h.get("action") or h.get("task"), width),
        }
        if h.get("status"):
            item["status"] = h["status"]
        score = _num(h.get("_hybrid_score") or h.get("_vector_score"))
        if score is not None:
            item["score"] = score
        mem_hits.append(item)
    out["memory"] = {
        "via": mem.get("via"),
        "count": mem.get("count", 0),
        "shown": len(mem_hits),
        "hits": mem_hits,
    }
    shown_any = shown_any or bool(mem_hits)

    # --- 知识库 ---
    kb = recall_result.get("knowledge") or {}
    kb_entries = []
    for e in (kb.get("entries") or [])[:limit]:
        if not isinstance(e, dict):
            continue
        kb_entries.append({
            "title": _clip(e.get("title") or e.get("name") or e.get("id"), width),
            "status": _clip(e.get("status") or e.get("trust"), 24),
            "path": _clip(e.get("path") or e.get("file"), 120),
        })
    out["knowledge"] = {
        "count": kb.get("count", 0),
        "shown": len(kb_entries),
        "entries": kb_entries,
    }
    shown_any = shown_any or bool(kb_entries)

    # --- 代码图谱 ---
    gr = recall_result.get("graph") or {}
    g_hits = []
    for h in (gr.get("hits") or [])[:limit]:
        it = h.get("item") if isinstance(h, dict) else None
        if not isinstance(it, dict):
            continue
        g_hits.append({
            "project": h.get("project"),
            "name": it.get("name"),
            "label": it.get("label"),
            "file": _clip(it.get("file_path"), 120),
        })
    out["graph"] = {
        "scanned_projects": gr.get("scanned_projects", 0),
        "shown": len(g_hits),
        "hits": g_hits,
    }
    shown_any = shown_any or bool(g_hits)

    if shown_any:
        out["full_text_hint"] = "以上为压缩摘要；取全文: hub.py recall \"<关键词>\" --limit N"
    return out



def _brief_skills(request: str, limit: int = 5) -> dict[str, Any]:
    """把任务描述反查成可用技能清单（简报用，失败不影响主流程）。"""
    try:
        hits = route_skills_for_task(request, scope="active", limit=limit)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}

    total = 0
    try:
        reg = json.loads(path_of(cfg()["skills_config"]["registry"]).read_text(encoding="utf-8"))
        total = len(reg.get("active") or [])
    except Exception:
        pass

    return {
        "ok": True,
        "active_total": total,
        "matched": len(hits),
        "skills": hits,
    }


# ---------------------------------------------------------------- 能力：技能路由

def route_skills(scope: str = "active", keyword: str = "",
                 query: str = "") -> list[dict[str, Any]]:
    """技能路由。

    与原版的关键差异：同时匹配 name 和 description。
    原版只做 `keyword in 英文技能名`，中文关键词（如「仓颉」）必然失配。
    """
    s = cfg()["skills_config"]
    reg_path = path_of(s["registry"])
    if not reg_path.exists():
        return []
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    # 分类名从配置取（过去 shadow 只在 config 里写着，代码不认）
    cats = s.get("categories") or {}
    if scope == "shadow":
        cat = _shadow_category()
    else:
        cat = cats.get(scope, scope)
    names = list(reg.get(cat) or [])
    if not names and isinstance(reg.get("overrides"), dict):
        # 回退：从 overrides 里按 enabled 推导
        for k, v in reg["overrides"].items():
            if isinstance(v, dict) and v.get("enabled") and scope == "active":
                names.append(k)

    # 取描述：优先 skill_registry.tsv（含 description 列）
    desc: dict[str, str] = {}
    tsv = HUB / "skills" / "skill_registry.tsv"
    if tsv.exists():
        try:
            rows = tsv.read_text(encoding="utf-8", errors="replace").splitlines()
            if rows:
                head = rows[0].split("\t")
                if "name" in head and "description" in head:
                    ni, di = head.index("name"), head.index("description")
                    for row in rows[1:]:
                        cols = row.split("\t")
                        if len(cols) > max(ni, di):
                            desc[cols[ni]] = cols[di]
        except Exception:
            pass

    # 中文别名表：上游数据里有 23 个技能的描述全是英文，
    # 若只匹配 name/description，中文关键词（如「仓颉」）必然失配。
    alias_path = HUB / "skills" / "skill_aliases.json"
    alias: dict[str, str] = {}
    if alias_path.exists():
        try:
            alias = json.loads(alias_path.read_text(encoding="utf-8"))
        except Exception:
            alias = {}

    # 匹配哪些字段由 config 决定（原来写死 name+description+aliases）
    fields = _match_fields()

    kw = (keyword or query or "").strip().lower()
    out = []
    for n in names:
        d = desc.get(n, "")
        a = alias.get(n, "")
        pool = {
            "name": n,
            "description": d,
            "aliases": a,
        }
        hay = " ".join(pool.get(f, "") for f in fields).lower()
        if not kw or kw in hay:
            out.append({"name": n, "description": (d or a)[:180], "aliases": a[:120]})
    return out[: s.get("max_results", 20)]


# 中文虚词黑名单：这些 n-gram 命中纯属噪声，会让无关技能排到前面
_CN_STOP = frozenset({
    "一下", "这个", "那个", "这些", "那些", "一个", "一段", "一次", "一些",
    "帮我", "我们", "他们", "你们", "我的", "你的", "他的", "它的",
    "什么", "怎么", "怎样", "如何", "可以", "需要", "进行", "使用",
    "就是", "还是", "或者", "以及", "之后", "之前", "时候", "问题",
    "现在", "已经", "因为", "所以", "但是", "如果", "这样", "那样",
    "并且", "而且", "然后", "其中", "关于", "对于", "通过", "根据",
    "这段", "那段", "部分", "方面", "东西", "事情", "一下的",
})
# 片段里只要含这些单字，整个片段都不要
_CN_STOP_PARTS = ("的", "了", "着", "吗", "呢", "吧", "啊", "么")


# 多字虚词：整体删除（给它们两侧切出边界，避免跨词片段）
_CN_SPLIT = (
    "一下", "这个", "那个", "这些", "那些", "一个", "一段", "一次", "一些",
    "帮我", "我们", "他们", "你们", "我的", "你的", "他的", "它的", "什么",
    "怎么", "怎样", "如何", "可以", "需要", "进行", "使用", "就是", "还是",
    "或者", "以及", "之后", "之前", "时候", "问题", "现在", "已经", "因为",
    "所以", "但是", "如果", "这样", "那样", "并且", "而且", "然后", "其中",
    "关于", "对于", "通过", "根据", "这段", "那段", "部分", "方面", "东西",
    "事情", "一下的", "这个的", "帮我看看", "能不能", "要不要", "有没有",
)

# 单字虚词：几乎不参与技术术语，可安全删除
_CN_SPLIT_CHARS = frozenset("的了着吗呢吧啊么这那个些就也都很再只我你他它是和与及或把被让使之于而且其则乃")


def _task_terms(text, max_len=6):
    """从任务描述里抽取候选词元，用于撞技能别名表。

    中文没有分词库可用，改用三步近似：
      1. 剥掉虚词，用分隔符切断，避免 "一下这" 这类跨词片段
      2. 在剩下的实义片段上做 2~4 字 n-gram
      3. 英文抽长度 >= 3 的词元
    """
    text = " ".join(str(text or "").split())
    if not text:
        return []

    out, seen = [], set()

    # 英文/数字词元
    for t in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text):
        low = t.lower()
        if low not in seen:
            seen.add(low)
            out.append(low)

    # 剥离虚词（多字优先，再删单字），用竖线切断
    cleaned = text
    for w in sorted(_CN_SPLIT, key=len, reverse=True):
        cleaned = cleaned.replace(w, "|")
    cleaned = "".join(
        "|" if (ch in _CN_SPLIT_CHARS or ch in "|") else ch
        for ch in cleaned
    )

    # 在实义片段上做 n-gram
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", cleaned):
        n = len(run)
        for size in (2, 3, 4):
            if size > n:
                continue
            for i in range(n - size + 1):
                g = run[i:i + size]
                if g not in seen:
                    seen.add(g)
                    out.append(g)

    return out[:4000]


def _maximal_terms(terms):
    """只保留不被更长命中包住的词元。

    "把方法蒸馏成技能" 会同时命中 蒸馏成 / 馏成 / 蒸馏 / 方法，
    其中 馏成 和 蒸馏 都被 蒸馏成 包住 —— 丢掉，避免重复计数与噪声展示。
    """
    uniq = sorted(set(terms), key=len, reverse=True)
    kept = []
    for t in uniq:
        if not any(t != k and t in k for k in kept):
            kept.append(t)
    return kept


def route_skills_for_task(text, scope="active", limit=5):
    """从任务描述反查可用技能。

    与 route_skills 的区别：那个是「一个关键词 -> 多个技能」，
    这个是「一段任务描述 -> 相关技能」。ask 需要的是后者。
    """
    s = cfg()["skills_config"]
    reg_path = path_of(s["registry"])
    if not reg_path.exists():
        return []
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    cats = s.get("categories") or {}
    cat = _shadow_category() if scope == "shadow" else cats.get(scope, scope)
    names = list(reg.get(cat) or [])
    if not names:
        return []

    # 收集每个技能的可匹配文本：名字 + 描述 + 别名
    desc = {}
    tsv = HUB / "skills" / "skill_registry.tsv"
    if tsv.exists():
        try:
            rows = tsv.read_text(encoding="utf-8", errors="replace").splitlines()
            if rows:
                head = rows[0].split("\t")
                if "name" in head and "description" in head:
                    ni, di = head.index("name"), head.index("description")
                    for row in rows[1:]:
                        cols = row.split("\t")
                        if len(cols) > max(ni, di):
                            desc[cols[ni]] = cols[di]
        except Exception:
            pass

    alias = {}
    alias_path = HUB / "skills" / "skill_aliases.json"
    if alias_path.exists():
        try:
            alias = json.loads(alias_path.read_text(encoding="utf-8"))
        except Exception:
            alias = {}

    terms = _task_terms(text)
    if not terms:
        return []

    scored = []
    for n in names:
        hay_parts = [n.replace("-", " ").replace("_", " ").lower(),
                     (desc.get(n) or "").lower(),
                     (alias.get(n) or "").lower()]
        blob = " ".join(hay_parts)
        if not blob.strip():
            continue

        hits = []
        for t in terms:
            # 太短的英文词元误命中率高，要求长度 >= 4 或含连字符
            if len(t) < 4 and not any(ch in t for ch in "-_"):
                if not ("\u4e00" <= t[0] <= "\u9fff"):
                    continue
            if t in blob:
                hits.append(t)
        if hits:
            hits = _maximal_terms(hits)
            # 命中的词元越长越具体，权重更高
            score = sum(len(h) for h in hits)
            scored.append((score, n, sorted(hits, key=len, reverse=True)[:4]))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"name": n, "matched_terms": h, "score": sc} for sc, n, h in scored[:limit]]


# ---------------------------------------------------------------- 能力：门禁

def gate_cli() -> Path:
    return path_of(cfg()["gates"]["cli"])


def gate_available() -> tuple[bool, str]:
    """门禁是否可用：CLI 与正本目录都要在。

    正本目录（config.gates.canonical）是 7 阶段 27 节点的定义所在；
    CLI 只是调用它的桥。两者缺一都不能正常跑门禁。
    """
    cli = gate_cli()
    canon = _gate_canonical()
    missing = []
    if not cli.exists():
        missing.append(f"CLI 缺失: {cli}")
    if not canon.is_dir():
        missing.append(f"正本目录缺失: {canon}")
    if missing:
        return False, "；".join(missing)
    return True, f"{cli} (正本 {canon.name})"


def gate_call(role: str, tool: str, args: dict) -> dict[str, Any]:
    g = gate_cli()
    if not g.exists():
        return {"ok": False, "error": f"未找到 gate.py: {g}"}
    payload = json.dumps(args, ensure_ascii=False)
    try:
        # 门禁命令的 cwd 必须是用户项目根（PROJECT_ROOT），而不是本工具目录。
        # 由 config 的 gates.project_root 指定；默认取当前工作目录。
        cwd = path_of(cfg()["gates"].get("project_root", "."))
        r = subprocess.run(
            [sys.executable, str(g), role, tool, payload],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, cwd=str(cwd),
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out = (r.stdout or "").strip()
    # 门禁输出是多行 JSON：从第一个 '{' 开始整块取，
    # 不能只取单行（否则只得到一个 '{'）。
    start = out.find("{")
    if start >= 0:
        whole = out[start:]
        try:
            return {"ok": True, "data": json.loads(whole)}
        except Exception:
            return {"ok": True, "data": out}
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or out)[-400:]}
    return {"ok": True, "data": out}


# ---------------------------------------------------------------- 宪法层（只读）

_CONST_MOD = None


def _load_constitution():
    """加载宪法校验器（只读）。

    validator.py 里的导入写法是 `from constitution.validator import ...`，
    所以要把 Agent_OS_Core 目录本身加进 sys.path，
    而不能像 _load_core 那样只加 HUB/core。
    """
    global _CONST_MOD
    if _CONST_MOD is not None:
        return _CONST_MOD

    core_dir = path_of(cfg()["layers"]["core"])          # .../core/Agent_OS_Core
    if not core_dir.is_dir():
        raise SystemExit(f"未找到治理核目录: {core_dir}")
    if str(core_dir) not in sys.path:
        sys.path.insert(0, str(core_dir))

    from constitution import validator as v
    _CONST_MOD = v
    return v


# 受保护的关键词：任务描述里出现这些，说明可能在动宪法层
_CONST_KEYWORDS = (
    "宪法", "constitution", "charter", "红线", "hard_prohibition",
    "02_执行手册", "回滚基线", "证据链",
)

# 点开头的受保护/敏感文件：没有常规后缀，单独列出
# 常见的受保护目录名（任务描述里往往只写目录名，不带文件名）
# 来源：config.constitution.protected_paths + 手册相关目录
_PROTECTED_DIR_HINTS = (
    "02_执行手册", "10_知识储备库", "Agent_OS_Core", "constitution",
    "manual-gates", "manual_mcp", "cases", "quarantine",
)
_DOTFILES = (
    ".env", ".env.local", ".env.production", ".gitignore", ".gitattributes",
)

_SUFFIXES = (
    # 文档/数据
    ".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".toml", ".csv",
    ".xlsx", ".docx", ".pptx", ".pdf", ".log", ".ini", ".cfg", ".conf", ".xml",
    # 数据库
    ".db", ".sqlite", ".sql",
    # 代码
    ".py", ".js", ".ts", ".tsx", ".jsx", ".cs", ".java", ".go", ".rs",
    ".cpp", ".cc", ".c", ".h", ".hpp", ".rb", ".php", ".kt",
    ".html", ".css", ".scss",
    # 脚本/可执行
    ".sh", ".ps1", ".bat", ".cmd", ".exe", ".dll",
)


def _paths_in_text(text: str, limit: int = 8) -> list[str]:
    """从任务描述里挑出可能指向文件或目录的路径。

    四类：
      1) 带目录分隔符的路径（core/x.json、09_投研/a/b.cs）
      2) 裸文件名（charter.json）
      3) 点开头的敏感文件（.env）
      4) 纯目录名（02_执行手册、skills/manual-gates）—— 受保护路径常是目录，
         不抽的话"更新 02_执行手册"就完全漏判

    踩过的坑：
      - 只写 A-Za-z0-9 会漏掉中文目录名（"09_投研"）
      - 后缀不把点吃进去，会把 "charter.json" 切成 "charter" 和 "js"
      - 后缀不按长度降序排，".jsonl" 会被 ".json" 先吃掉，截成 "memory.json"
      - 只认多段路径会漏掉单层目录名
    """
    text = str(text or "")
    out: list[str] = []
    seen: set[str] = set()

    def add(t: str) -> bool:
        t = t.strip().strip(",，。；;:：")
        if t and t not in seen and not _is_noise(t):
            seen.add(t)
            out.append(t)
        return len(out) >= limit

    # 后缀必须按长度降序，否则 .json 会截断 .jsonl
    suf_sorted = sorted(_SUFFIXES, key=len, reverse=True)
    tail = "(?:" + "|".join(re.escape(s) for s in suf_sorted) + \
           "|" + "|".join(re.escape(s) for s in _DOTFILES) + ")"
    # 目录名候选：已知的受保护根名，或中文名
    dir_alt = "|".join(re.escape(d.strip("/")) for d in _PROTECTED_DIR_HINTS)

    # 路径片段：允许中文等非 ASCII；排除空白、分隔符与标点
    seg = r"[^\s/:*?\"<>|,，。；;]+"
    SEP = r"[/\\]"

    # 1) 多层路径 + 后缀
    pat_path = seg + "(?:" + SEP + seg + ")*" + SEP + seg + tail
    for m in re.finditer(pat_path, text):
        if add(m.group(0)):
            return out

    # 2) 裸文件名
    for m in re.finditer(r"[A-Za-z0-9_\-]+" + tail, text):
        if add(m.group(0)):
            break

    # 3) 点开头的敏感文件
    for m in re.finditer("(?:" + "|".join(re.escape(s) for s in _DOTFILES) + ")", text):
        if add(m.group(0)):
            break

    # 4) 纯目录名：已知受保护目录，或"某段/某段"这种两段以上但无后缀的
    # 用捕获组拿到目录名本身（前面用非捕获组吃掉前导标点）
    pat_dir = r"""(?:^|[\s"（(【])(""" + dir_alt + r""")(?=[\s"）)】]|$)"""
    for m in re.finditer(pat_dir, text):
        if add(m.group(1)):
            break
    for m in re.finditer(seg + SEP + seg, text):
        cand = m.group(0)
        if not any(cand.endswith(s) for s in _SUFFIXES):
            add(cand)

    return out


def _is_noise(t: str) -> bool:
    """过滤明显不是路径的碎片。

    "js"/"py"/"json" 这种孤立后缀没有意义（来自把 .json 切开），
    真正的文件名至少要有主名 + 后缀。
    """
    low = t.lower()
    if low in _DOTFILES or low.startswith("."):
        return False
    for s in _SUFFIXES:
        if low == s[1:]:
            return True
    return len(low) < 4

def _hub_protected(path: Path) -> str:
    """按 HUB 根判定受保护路径。命中则返回命中的规则，否则空串。

    这段存在的理由：宪法校验器内部按 CORE_DIR.parent 判定，
    打包后基准少了一层（core/ 而非 HUB 根），导致 02_执行手册 这类
    保护全部失效。这里按 config.constitution.protected_paths 补一遍。
    """
    try:
        rules = (cfg().get("constitution") or {}).get("protected_paths") or []
    except Exception:
        rules = []
    if not rules:
        return ""

    try:
        p = path if path.is_absolute() else (HUB / path)
        p = p.resolve()
        rel = p.relative_to(HUB).as_posix()
    except (OSError, ValueError):
        return ""   # 不在 HUB 内，交给校验器判断

    for rule in rules:
        r = str(rule).strip().replace("\\", "/")
        if not r:
            continue
        if r.endswith("/"):
            if rel == r.rstrip("/") or rel.startswith(r):
                return r
        elif rel == r:
            return r
    return ""


def constitution_check(text: str, paths: list[str] | None = None,
                       limit: int = 8) -> dict[str, Any]:
    """宪法层预检（纯只读）。

    返回三个东西：
      integrity —— 宪法文件完整性（指纹 + 有无缺失）
      checked   —— 逐个路径的写入判定（ALLOW/BLOCK）
      verdict   —— 汇总：任一 BLOCK 即 BLOCK
    """
    try:
        v = _load_constitution()
    except SystemExit as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}

    try:
        integ = v.verify_constitution_integrity()
        integrity = {
            "status": integ.get("status"),
            "hash": (integ.get("current_hash") or "")[:16],
            "missing_files": integ.get("missing_files") or [],
            "file_count": len(v.CONSTITUTION_FILES),
        }
    except Exception as e:
        integrity = {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:120]}"}

    # 候选路径 = 显式传入的 + 从任务描述里抽的
    cands = list(paths or [])
    if text:
        for p in _paths_in_text(text, limit=limit):
            if p not in cands:
                cands.append(p)

    checked: list[dict[str, Any]] = []
    for raw in cands[:limit]:
        target = Path(raw)
        # 裸文件名若命中宪法文件表，就锚到宪法目录 —— 否则会被误判成 ALLOW
        if target.parent == Path(".") and target.name in v.CONSTITUTION_FILES:
            target = v.CONSTITUTION_DIR / target.name
        elif not target.is_absolute():
            target = HUB / target
        try:
            r = v.validate_write(target)
            action = r.get("action")
            reason = r.get("reason")
            vtype = r.get("violation_type")

            # HUB 侧补判：校验器的 PROTECTED_PATHS 因打包层级变化而失效，
            # 这里按 HUB 根再判一次，取并集（任一 BLOCK 即 BLOCK）。
            hit = _hub_protected(target)
            if hit and action != "BLOCK":
                action = "BLOCK"
                reason = f"受保护路径（HUB 规则: {hit}），禁止写入"
                vtype = "hub_protected_path"

            checked.append({
                "path": raw,
                "resolved": str(target),
                "action": action,
                "reason": reason,
                "violation_type": vtype,
            })
        except Exception as e:
            checked.append({"path": raw, "action": "ERROR",
                            "reason": f"{type(e).__name__}: {str(e)[:100]}"})

    kw_hits = [k for k in _CONST_KEYWORDS if k.lower() in str(text or "").lower()]
    blocked = [c for c in checked if c.get("action") == "BLOCK"]

    # 三档：BLOCK（有路径被拦）> REVIEW（命中受保护关键词但没抽到路径）> ALLOW
    # REVIEW 存在的理由：像 "02_执行手册" 这类目录不在 HUB 内（打包没带），
    # 路径判定必然为空，但任务提它说明可能要动源库那边的受保护内容，不能当没事。
    if blocked:
        verdict = "BLOCK"
    elif kw_hits:
        verdict = "REVIEW"
    else:
        verdict = "ALLOW"

    out: dict[str, Any] = {
        "ok": True,
        "integrity": integrity,
        "checked": checked,
        "keyword_hits": kw_hits,
        "verdict": verdict,
    }
    if blocked:
        out["blocked_paths"] = [c["path"] for c in blocked]
        out["note"] = ("目标路径受宪法层保护，禁止写入；该操作必须由 owner 处理，"
                       "不可自动执行")
    elif kw_hits:
        out["note"] = (f"命中受保护关键词（{'、'.join(kw_hits)}），"
                       "但未定位到具体受保护路径；若涉及源库中的受保护目录，"
                       "请先确认再动手")
    else:
        out["note"] = "只读预检；宪法层未拦截本次任务涉及的路径"
    return out


# ---------------------------------------------------------------- 门禁状态（只读）

_GATE_MODS = None


def _load_gate_modules():
    """按包加载门禁模块。

    common.py 里用的是相对导入（from .manual_data import ...），
    必须把 scripts 目录加进 sys.path 再以 manual_mcp 包名导入，
    直接按文件路径 import 会报 "attempted relative import"。
    """
    global _GATE_MODS
    if _GATE_MODS is not None:
        return _GATE_MODS

    g = gate_cli()
    if not g.exists():
        raise SystemExit(f"未找到门禁 CLI: {g}")
    scripts_dir = g.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from manual_mcp import state as store
    from manual_mcp import learning
    from manual_mcp import manual_data as mdata
    _GATE_MODS = (store, learning, mdata)
    return _GATE_MODS


def gate_status(project: str, max_todo: int = 3) -> dict[str, Any]:
    """查一个项目在门禁手册里走到哪了（纯只读）。

    这是"只读预览"：只读 state.json 和静态节点表，不创建项目、不写状态。
    真正的节点验收（submit_check）会写盘，必须由人确认后另外执行。
    """
    if not project:
        return {"ok": False, "error": "未指定项目名"}
    try:
        store, learning, mdata = _load_gate_modules()
    except SystemExit as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}

    try:
        st = store.load(project)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}

    # store.load 对不存在的项目会返回一份新 state（不落盘），
    # 用 nodes 是否为空 + 目录是否存在来判断"这个项目是否有过记录"。
    state_path = store._state_path(project)
    found = state_path.exists()

    try:
        track = st.get("track", "standard")
        idx = learning.get_node_index()
        passed = [nid for nid in (st.get("nodes") or {})
                  if store.node_status(st, nid) == "passed"]

        # 按项目轨道过滤出该走的节点（quick 轨只看 5 个关键节点，
        # 不过滤会把已完成的 quick 项目误报成"还差节点1"）。
        allowed = set(mdata.track_node_ids(track, list(idx.keys())))

        # 找全局下一个待办节点（按阶段顺序）
        next_node = None
        for s in learning.get_stages():
            for n in s.get("nodes", []):
                if n["id"] not in allowed:
                    continue
                if store.node_status(st, n["id"]) != "passed":
                    next_node = {
                        "stage": s.get("name"),
                        "node_id": n.get("id"),
                        "name": n.get("name"),
                        "output": n.get("output"),
                        "acceptance": _clip(n.get("acceptance"), 160),
                    }
                    break
            if next_node:
                break

        total = len(allowed)
        return {
            "ok": True,
            "found": found,
            "project": project,
            "track": track,
            "autonomy": st.get("autonomy", ""),
            "total_nodes": total,
            "passed_count": len(passed),
            "next_node": next_node,
            "note": "只读预览，未写入任何状态；节点验收需人工确认后另行执行",
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}


# ---------------------------------------------------------------- 单一任务入口

def ask(request: str, project: str = "", use_graph: bool = True,
        record: bool = True, evidence_limit: int = 3,
        skill_limit: int = 5) -> dict[str, Any]:
    """单一任务入口：一个任务进来，走完整条流水线。

    步骤：
      1. 准入分级（风险 L1-L3 + 处理深度）
      2. 三源检索（同类经验 / 已知知识 / 相关代码）
      3. 生成任务简报（含建议轨道与下一步）
      4. 经验回流（把这次任务登记进记忆）
    """
    build_intake, classify_risk, depth_policy = _load_core()

    # 1) 准入分级
    intake = build_intake(request, llm_actions=None, task_profile="general", context=None)
    level_raw = intake["risk"]["risk_level"]
    level = level_raw
    depth = intake["depth"]

    # 1.5) 宪法层预检 + 强制升级
    #
    # 为什么必须放在这里：原实现把宪法检查留在"拼简报"那一步，
    # 于是 "帮我改 charter.json 的红线" 判成 L1（免审批、免复核），
    # 同一份简报里又写着 "verdict: BLOCK，禁止写入须 owner 处理" ——
    # 一个说随便做、一个说禁止，自相矛盾。
    # 分级是后续审批/复核/门禁的唯一依据，宪法一旦拦下就必须先回馈到等级。
    #
    # 这里只做"升级"，不做"降级"：宪法判定永远不能把风险改低。
    cc = constitution_check(request)
    constitution_escalated = False
    if cc.get("verdict") == "BLOCK":
        if level != "L3":
            constitution_escalated = True
        level = "L3"
        depth = depth_policy("L3")

    # 1.8) 兼容层：把任务里的旧目录名改成新位置
    # 源库叫 04_技能包，包内叫 skills。历史文档或口述里常出现旧名，
    # 不改写的话后续检索会指着一个不存在的目录。
    request = compat_rewrite(request)

    # 2) 三源检索
    recall_result = recall(request, limit=5, use_graph=use_graph)

    # 3) 项目名：显式给出优先，否则由风险等级+时间派生稳定名
    if not project:
        import hashlib
        h = hashlib.sha1(request.encode("utf-8")).hexdigest()[:8]
        project = f"task-{h}"

    brief = {
        "request": request,
        "project": project,
        "intake": {
            "intake_id": intake["intake_id"],
            "risk_level": level,
            # 原始等级：便于看清"是不是被宪法顶上来的"
            "risk_level_before_constitution": level_raw,
            "constitution_escalated": constitution_escalated,
            "status": intake["status"],
            "no_silent_downgrade": intake["no_silent_downgrade"],
            "depth": depth,
        },
        "recall": recall_result["summary"],
        # 检索结果回传：把三源命中的原文压成可读摘要，直接放进简报。
        # 之前这里只有计数，检索等于白做 —— 得再手动跑一次 recall 才看得到内容。
        "evidence": _brief_evidence(recall_result, limit=evidence_limit),
        # 技能汇入：把任务描述反查成可用技能清单。
        # 之前 ask 完全不碰技能路由 —— 35 个 active 技能等于隐形。
        "skills": _brief_skills(request, limit=skill_limit),
        # 门禁联动：带上"这个项目在手册里卡在哪"。只读预览，不写状态。
        "gate": gate_status(project),
        # 宪法层预检：完整性 + 路径可否写入。纯只读，不写状态。
        # 复用上面算好的 cc，避免同一件事跑两遍。
        "constitution": cc,
        "next": _suggest_next(level, depth, recall_result, request, cc),
    }

    # 4) 经验回流：登记任务快照（失败不影响主流程）
    if record:
        try:
            tools = _memory_tools()
            _call_tool(tools, "record_task_snapshot", project=project, task=request,
                       context_json=json.dumps({"risk_level": level,
                                                "via": "hub.ask"}, ensure_ascii=False))
            brief["memory_recorded"] = True
        except Exception as e:
            brief["memory_recorded"] = False
            brief["memory_error"] = f"{type(e).__name__}: {str(e)[:120]}"

    return brief


def _suggest_next(level: str, depth: dict, recall_result: dict,
                  request: str = "", cc: dict | None = None) -> dict[str, Any]:
    """按风险等级给出建议轨道与下一步动作。"""
    owner_gate = bool(depth.get("owner_gate"))
    # 治理核只产生 L1/L2/L3（depth_policy 明确拒绝 L4）。
    # L3 已是最高档：需审批 + 需复核 + 真实调用需门 + 超时即阻断。
    track = "standard" if level == "L3" else "quick"

    steps = []

    # 宪法层拦截优先级最高：违宪的操作谈都不用谈，直接置顶。
    # 放在最前面，否则会被"先读经验""先看技能"挤到末尾，容易被漏看。
    # cc 由 ask 传入（已在那一步用于强制升级），这里不再重算。
    cc = cc or {}
    if cc.get("verdict") == "BLOCK":
        blocked = "、".join(cc.get("blocked_paths") or [])
        steps.append(f"⛔ 宪法层拦截：{blocked} 属保护范围，禁止写入，须 owner 处理")
        return {"track": "standard", "owner_gate_required": True,
                "constitution_blocked": True, "steps": steps}

    if cc.get("verdict") == "REVIEW":
        kw = "、".join(cc.get("keyword_hits") or [])
        steps.append(f"⚠ 提到受保护内容（{kw}）：源库对应目录不可改，动手前先确认")

    # 指向"具体哪一条"经验，而不是笼统说一句"先读经验"。
    mem_hits = ((recall_result.get("memory") or {}).get("hits") or [])
    if mem_hits:
        first = mem_hits[0]
        ref = first.get("id") or "(无 id)"
        proj = first.get("project") or "?"
        head = _clip(first.get("action") or first.get("task"), 60)
        steps.append(f"先读同类经验 {ref} [{proj}]：{head}")

    kb_entries = ((recall_result.get("knowledge") or {}).get("entries") or [])
    if kb_entries:
        steps.append(f"知识库有 {len(kb_entries)} 条相关条目，先过一遍再动手")

    graph_hits = ((recall_result.get("graph") or {}).get("hits") or [])
    if graph_hits:
        it = graph_hits[0].get("item") or {}
        steps.append(f"代码里已有 {it.get('name')}（{it.get('file_path')}），先看再改")

    # 有现成技能就先走技能，别重新造轮子
    if request:
        try:
            sk = route_skills_for_task(request, limit=3)
            if sk:
                names = "、".join(x["name"] for x in sk)
                steps.append(f"可直接用现成技能：{names}")
        except Exception:
            pass

    if owner_gate:
        steps.append("本任务需 Owner 审批后才能执行（不可自行放行）")
    steps.append(f"在本项目根目录跑门禁立项: hub.py gate strategy plan_next project={_safe(recall_result.get('query',''))}")
    return {"track": track, "owner_gate_required": owner_gate, "steps": steps}


def _safe(s: str) -> str:
    import hashlib
    return "task-" + hashlib.sha1(str(s).encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------- 学习 / 蒸馏

def learn(project: str = "", limit: int = 10) -> dict[str, Any]:
    """经验蒸馏：把散落的经验提炼成可复用教训。"""
    try:
        tools = _memory_tools()
    except SystemExit as e:
        return {"ok": False, "error": str(e)}
    try:
        raw = _call_tool(tools, "distill_memory_lessons", project=project, limit=limit)
        return {"ok": True, "data": _try_json(raw)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def memory_stats() -> dict[str, Any]:
    try:
        tools = _memory_tools()
    except SystemExit as e:
        return {"ok": False, "error": str(e)}
    out = {}
    for name in ("memory_index_stats", "memory_vector_stats"):
        try:
            out[name] = _try_json(_call_tool(tools, name))
        except Exception as e:
            out[name] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    return {"ok": True, **out}


# ---------------------------------------------------------------- 治理核单测

def core_selftest(verbose: bool = True) -> int:
    """跑治理核自带的单元测试（只读，不写任何状态）。

    治理核代码以 `Agent_OS_Core` 为顶层包名，而它位于 `core/` 下，
    因此需要把 `core/` 加进 sys.path 才能 import。这里显式处理，
    而不是把包结构迁就路径。
    """
    import unittest
    core = path_of(cfg()["layers"]["core"])
    root = core.parent
    mcps = path_of("engine/mcps")
    for p in (str(root), str(core), str(mcps), str(path_of("engine/memory"))):
        if p not in sys.path:
            sys.path.insert(0, p)

    # 注：test_unified_entrypoint 是跨核集成测试（需 AutoRobot 桥接），
    # 已移至 core/_tests-integration/，不参与这里的自身体检。
    mods = [
        "Agent_OS_Core.policy.tests.test_policy_controls",
        "Agent_OS_Core.policy.tests.test_queue_admission",
    ]
    total = errors = failures = 0
    for m in mods:
        try:
            suite = unittest.TestLoader().loadTestsFromName(m)
            r = unittest.TextTestRunner(verbosity=2 if verbose else 0,
                                        stream=sys.stdout if verbose else open(os.devnull, "w")).run(suite)
            total += r.testsRun
            errors += len(r.errors)
            failures += len(r.failures)
            if verbose:
                print(f"  [{m.split('.')[-1]}] {r.testsRun} 项, "
                      f"errors {len(r.errors)}, failures {len(r.failures)}")
        except Exception as e:
            errors += 1
            if verbose:
                print(f"  [{m}] 无法加载: {type(e).__name__}: {str(e)[:120]}")
    if verbose:
        ok = errors == 0 and failures == 0
        print(f"\n[治理核单测] 共 {total} 项, 失败 {errors + failures} 项"
              + (" —— 全部通过" if ok else ""))
    return 0 if (errors == 0 and failures == 0) else 1

# ---------------------------------------------------------------- 环境自检（只读）

def doctor(verbose: bool = True) -> int:
    """环境自检。严格只读：不建项目、不写记忆、不跑门禁命令。

    与原版的差异：
      - 原版 doctor 会跑 gate plan_next 做「冒烟」，那会创建项目状态，
        与其自称的「只读」相矛盾；这里改为静态检查文件是否齐备。
      - 原版计数有 bug（异常分支 append 了 (False, False) 元组，
        导致 FAIL 重复计数），这里统一用 _chk() 返回值。
    """
    checks: list[tuple[str, bool, str]] = []

    def _chk(name: str, ok: bool, detail: str = "") -> bool:
        checks.append((name, ok, detail))
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))
        return ok

    if verbose:
        print("[agentos-hub] 环境自检（只读）\n")

    # --- 基础 ---
    v = sys.version_info
    _chk("Python >= 3.10", (v.major, v.minor) >= (3, 10), f"{v.major}.{v.minor}.{v.micro}")
    _chk("config.yaml", CONFIG_PATH.exists())
    if not CONFIG_PATH.exists():
        _finish(checks, verbose)
        return 1

    # --- 依赖 ---
    try:
        import yaml  # noqa: F401
        _chk("PyYAML", True)
    except ImportError:
        _chk("PyYAML", False, "pip install -r requirements.txt")

    mcp_state = ""
    try:
        import importlib.metadata as md
        try:
            ver = md.version("mcp")
        except Exception:
            ver = "未安装"
        ok = ver.startswith("1.")
        mcp_state = f"mcp {ver}"
        try:
            from mcp.server.fastmcp import FastMCP  # noqa: F401
            has_fast = True
        except Exception:
            has_fast = False
        _chk("mcp 1.x + fastmcp", ok and has_fast,
             mcp_state if (ok and has_fast)
             else f"{mcp_state}（需 >=1.28,<2；2.x 已移除 fastmcp）")
    except Exception as e:
        _chk("mcp 1.x + fastmcp", False, str(e)[:80])

    # --- 治理核 ---
    core_dir = path_of(cfg()["layers"]["core"])
    _chk("治理核目录", core_dir.exists(), str(core_dir))
    if core_dir.exists():
        try:
            build_intake, _, _ = _load_core()
            r = build_intake("自检探针", llm_actions=None)
            _chk("治理核 intake 可用", bool(r.get("risk", {}).get("risk_level")),
                 f"探针分级 {r['risk']['risk_level']}")
        except Exception as e:
            _chk("治理核 intake 可用", False, f"{type(e).__name__}: {str(e)[:90]}")
    for sub in ("policy", "constitution", "schemas", "governance", "knowledge", "recovery"):
        p = core_dir / sub
        _chk(f"  core/{sub}", p.exists())

    # --- 记忆引擎（静态检查，不建库）---
    mem_dir = path_of(cfg()["layers"]["engine"]["memory"])
    _chk("记忆引擎目录", mem_dir.exists(), str(mem_dir))
    _chk("  experience_memory_mcp", (mem_dir / "experience_memory_mcp" / "common.py").exists())
    _chk("  _shared 依赖", all((mem_dir / "_shared" / f).exists()
                              for f in ("io.py", "time.py", "state.py")))
    d = cfg()["memory"]
    jl = path_of(d["jsonl"])
    if jl.exists():
        n = sum(1 for _ in jl.open(encoding="utf-8", errors="replace"))
        _chk("记忆数据", True, f"{n} 条")
    else:
        _chk("记忆数据", True, "尚未建立（首次记录时自动创建）")

    # --- 知识库 ---
    kb = path_of(cfg()["layers"]["engine"]["knowledge"]) / "knowledge-base" / "scripts"
    _chk("知识库脚本", (kb / "query.py").exists(), str(kb))

    # --- 门禁 ---
    g = gate_cli()
    _chk("门禁 gate.py", g.exists(), str(g))
    if g.exists():
        mm = g.parent / "manual_mcp"
        _chk("  manual_mcp 正本", (mm / "common.py").exists())
        roles = cfg()["gates"]["roles"]
        missing = [r for r in roles if not (mm / f"run_{r}.py").exists()]
        _chk(f"  角色壳({len(roles)})", not missing, f"缺失 {missing}" if missing else "")
        _chk("  节点数据", (mm / "manual_data.py").exists())

    # --- 技能 ---
    sk = path_of(cfg()["skills_config"]["registry"])
    _chk("技能注册表", sk.exists(), str(sk))
    if sk.exists():
        try:
            reg = json.loads(sk.read_text(encoding="utf-8"))
            na = len(reg.get("active") or [])
            _chk("  技能路由可用", na > 0, f"active {na} 个")
        except Exception as e:
            _chk("  技能路由可用", False, str(e)[:80])

    # --- 知识图谱（可选）---
    ok, detail = graph_available()
    if ok:
        ps = graph_projects()
        _chk("代码知识图谱", bool(ps),
             f"{detail} | {len(ps)} 个已索引项目" if ps else f"{detail} | 无已索引项目")
    else:
        _chk("代码知识图谱（可选）", True, f"降级运行: {detail}")

    return _finish(checks, verbose)


def _finish(checks: list[tuple[str, bool, str]], verbose: bool) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    failed = total - passed
    if verbose:
        print(f"\n[agentos-hub] PASS {passed} / FAIL {failed} / 共 {total} 项")
        if failed:
            print("存在未通过项。核心功能可用的前提是：治理核 + 记忆引擎 + 依赖齐全。")
        else:
            print("环境就绪。")
    return 1 if failed else 0


# ---------------------------------------------------------------- 备用能力（engine/mcps）

# 每个模块的用途（从代码里的工具定义归纳，不是 README 抄的）
_MCP_PURPOSE = {
    "capability_profile_mcp": ("能力画像", "定义能力画像、检查某动作是否被允许"),
    "cognitive_intake_mcp": ("任务准入", "把请求分类成 A/B/C/D，建执行卡"),
    "compiled_correction_mcp": ("纠正编译", "记录用户纠正并编译成检查规则"),
    "completion_verifier_mcp": ("完成验证", "按证据验证完成度，签发证书"),
    "control_plane_mcp": ("控制平面", "策略检查、自主权决策、审计事件"),
    "dashboard_mcp": ("运行看板", "采集数据、生成看板 HTML"),
    "failure_replay_mcp": ("失败复盘", "记录失败、蒸馏教训、建规避计划"),
    "hook_runtime_mcp": ("钩子运行时", "工具调用前后、停止时的钩子链"),
    "mandatory_runtime_hook_mcp": ("强制路由", "强制路由规划与合规校验"),
    "memory_consolidation_mcp": ("记忆整理", "记忆分层、冲突检测、健康报告"),
    "preflight_bundle_mcp": ("执行前检查", "统一预检并记录检查包"),
    "runtime_integration_mcp": ("运行集成", "集成任务环、导出状态、建备份"),
    "runtime_middleware_mcp": ("运行中间件", "按任务类别搭中间件栈"),
    "side_effect_admission_mcp": ("副作用准入", "申请/校验准入票"),
    "task_queue_mcp": ("任务队列", "队列状态、入队、自启动治理（20 个工具）"),

    # --- 以下为 2026-09-16 从源库补齐的 27 个 ---
    "agent_orchestration_mcp": ("Agent 编排", "多 Agent 协调与编排"),
    "agent_runtime_kernel_mcp": ("Agent 运行时内核", "Agent 执行内核"),
    "agentops_dashboard_mcp": ("AgentOps 看板", "运维看板数据"),
    "approval_interrupt_mcp": ("审批中断", "审批中断与恢复"),
    "audit_hash_chain_mcp": ("审计哈希链", "证据链完整性（哈希串联）"),
    "auto_trigger_mcp": ("自动触发", "条件触发的自动动作"),
    "autonomy_level_assessor_mcp": ("自主权评估", "评估可自主到什么程度"),
    "backup_integrity_mcp": ("备份完整性", "校验备份是否完好"),
    "cost_budget_mcp": ("成本预算", "成本预算与断路器"),
    "decision_workbench_mcp": ("决策工作台", "决策记录与分析"),
    "evaluation_harness_mcp": ("评测框架", "跑评测用例并记分"),
    "git_ci_mcp": ("Git / CI", "版本与持续集成"),
    "health_check_mcp": ("健康检查", "系统健康巡检"),
    "local_regression_gate_mcp": ("本地回归门禁", "回归测试放行判断"),
    "long_running_session_mcp": ("长会话", "长任务的会话保持与恢复"),
    "mathematical_reasoning_mcp": ("数学推理", "数学建模与推演"),
    "memory_retrieval_mcp": ("记忆检索", "专门的记忆检索"),
    "offline_upgrade_mcp": ("离线升级", "无网环境下的升级"),
    "policy_consistency_auditor_mcp": ("策略一致性审计", "检查策略之间有无冲突"),
    "product_os_mcp": ("产品 OS", "产品级运行框架"),
    "production_readiness_mcp": ("生产就绪度", "上线前的就绪评估"),
    "research_mcp": ("研究", "资料检索与调研"),
    "tia_template_compiler_mcp": ("TIA 模板编译", "西门子 TIA 工程模板编译"),
    "tool_lifecycle_tracing_mcp": ("工具生命周期追踪", "工具调用的全链路记录"),
    "trace_observability_mcp": ("链路可观测", "执行链路追踪与诊断"),
    "video_generation_mcp": ("视频生成", "视频内容生成"),
    "workflow_runtime_mcp": ("工作流运行时", "工作流定义与执行"),
}

# 依赖额外的 sys.path 才能导入的模块
_MCP_EXTRA_PATH = {
    "task_queue_mcp": ("engine/memory", "core"),
}


def list_mcps(name: str = "") -> dict[str, Any]:
    """列出 engine/mcps 下的备用模块（只读）。

    这些模块主流程不经过，但都能独立启动。需要某个能力时，
    先在这里查有没有现成的，再决定接入还是借鉴。
    细节见 CAPABILITIES.md。
    """
    base = path_of("engine/mcps")
    if not base.is_dir():
        return {"ok": False, "error": f"未找到目录: {base}"}

    items = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name == "_shared" or d.name.startswith("."):
            continue
        if name and name.lower() not in d.name.lower():
            continue

        nfiles = sum(1 for f in d.rglob("*") if f.is_file())
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        label, desc = _MCP_PURPOSE.get(d.name, ("", ""))

        # 统计工具数（数 @mcp.tool 装饰的 def，避免真正 import）
        ntools = 0
        common = d / "common.py"
        if common.is_file():
            try:
                txt = common.read_text(encoding="utf-8", errors="replace")
                ntools = txt.count("@mcp.tool")
            except Exception:
                pass

        item = {
            "name": d.name,
            "label": label,
            "purpose": desc,
            "tools": ntools,
            "files": nfiles,
            "kb": round(size / 1024, 1),
            "used_by_entry": False,
        }
        extra = _MCP_EXTRA_PATH.get(d.name)
        if extra:
            item["extra_sys_path"] = list(extra)
        items.append(item)

    return {
        "ok": True,
        "note": "备用模块，主流程不经过；需要时独立启动，详见 CAPABILITIES.md",
        "count": len(items),
        "mcps": items,
    }


# ---------------------------------------------------------------- 版本管理

def _git(args, cwd=None):
    """跑一条 git 命令，返回 (是否成功, 输出)。"""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd or HUB),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
    except FileNotFoundError:
        return False, "未找到 git，请先安装 Git for Windows"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, out


def version_info() -> dict[str, Any]:
    """看当前版本与仓库状态（只读）。"""
    try:
        v = cfg().get("version", "")
    except Exception:
        v = ""

    is_repo = (HUB / ".git").is_dir()
    if not is_repo:
        return {"ok": False, "version": v, "error": "尚未启用版本管理",
                "hint": "在包根目录执行: git init"}

    out: dict[str, Any] = {"ok": True, "version": v, "repo": str(HUB)}

    ok, log = _git(["log", "--oneline", "-8"])
    out["recent_commits"] = log.splitlines() if ok else []

    ok, cnt = _git(["rev-list", "--count", "HEAD"])
    out["commit_count"] = int(cnt) if (ok and cnt.isdigit()) else 0

    ok, st = _git(["status", "--short"])
    changed = [l for l in st.splitlines() if l.strip()] if ok else []
    out["pending_changes"] = len(changed)
    out["pending_files"] = changed[:15]

    ok, br = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    out["branch"] = br if ok else ""

    return out


def version_record(message: str, add_all: bool = True) -> dict[str, Any]:
    """把当前改动提交，记录一次迭代。

    只做本地提交，不推送远程——推送需要你明确决定。
    不是 git 仓库时给提示，不自动初始化（那是你的决定）。
    """
    msg = (message or "").strip()
    if not msg:
        return {"ok": False, "error": '需要一句说明，例如 -m "修复图谱检索中文匹配"'}

    if not (HUB / ".git").is_dir():
        return {"ok": False, "error": "尚未启用版本管理"}

    if add_all:
        ok, out = _git(["add", "-A"])
        if not ok:
            return {"ok": False, "error": f"暂存失败: {out[-200:]}"}

    ok, st = _git(["status", "--short"])
    staged = [l for l in st.splitlines() if l.strip()]
    if not staged:
        return {"ok": True, "recorded": False,
                "note": "没有待记录的改动（工作区是干净的）"}

    ok, out = _git(["commit", "-m", msg])
    if not ok:
        return {"ok": False, "error": f"提交失败: {out[-300:]}"}

    ok2, cnt = _git(["rev-list", "--count", "HEAD"])
    ok3, head = _git(["log", "--oneline", "-1"])
    return {
        "ok": True,
        "recorded": True,
        "files_changed": len(staged),
        "commit": head,
        "total_commits": int(cnt) if (ok2 and cnt.isdigit()) else None,
    }


# ---------------------------------------------------------------- CLI

def _print(obj: Any, as_json: bool = False) -> None:
    if as_json or not isinstance(obj, str):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(obj)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hub.py",
        description="agentos-hub —— 单一任务入口（准入 / 三源检索 / 门禁 / 经验回流）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    sub = ap.add_subparsers(dest="cmd")

    p_doc = sub.add_parser("doctor", help="环境自检（只读）")
    p_doc.set_defaults(func=lambda a: doctor())

    p_cst = sub.add_parser("selftest", help="治理核单元测试（只读）")
    p_cst.set_defaults(func=lambda a: core_selftest())

    p_ask = sub.add_parser("ask", help="单一任务入口")
    p_ask.add_argument("request", help="任务描述")
    p_ask.add_argument("--project", default="", help="项目名（默认按任务派生）")
    p_ask.add_argument("--no-graph", action="store_true", help="跳过代码图谱检索")
    p_ask.add_argument("--no-record", action="store_true", help="不写入记忆")
    p_ask.add_argument("--evidence-limit", type=int, default=3,
                       help="每个来源在简报里回传几条摘要（默认 3，0=不回传）")
    p_ask.add_argument("--skill-limit", type=int, default=5,
                       help="简报里回传几条相关技能（默认 5）")
    p_ask.set_defaults(func=lambda a: _print(ask(
        a.request, project=a.project, use_graph=not a.no_graph,
        record=not a.no_record, evidence_limit=a.evidence_limit,
        skill_limit=a.skill_limit), a.json))

    p_rec = sub.add_parser("recall", help="三源检索（记忆/知识/图谱）")
    p_rec.add_argument("query")
    p_rec.add_argument("--limit", type=int, default=5)
    p_rec.add_argument("--no-graph", action="store_true")
    p_rec.set_defaults(func=lambda a: _print(
        recall(a.query, limit=a.limit, use_graph=not a.no_graph), a.json))

    p_mem = sub.add_parser("memory", help="仅记忆检索（4 种方式）")
    p_mem.add_argument("query")
    p_mem.add_argument("--limit", type=int, default=5)
    p_mem.add_argument("--project", default="")
    p_mem.set_defaults(func=lambda a: _print(
        recall_memory(a.query, limit=a.limit, project=a.project), a.json))

    p_kb = sub.add_parser("kb", help="知识库检索")
    p_kb.add_argument("query")
    p_kb.add_argument("--limit", type=int, default=5)
    p_kb.set_defaults(func=lambda a: _print(recall_knowledge(a.query, limit=a.limit), a.json))

    p_g = sub.add_parser("graph", help="代码知识图谱")
    p_g.add_argument("tool", nargs="?", default="list_projects")
    p_g.add_argument("args", nargs="*", help="key=value 或 JSON")
    p_g.set_defaults(func=lambda a: _print(
        {"ok": True, "data": graph_call(a.tool, _kv(a.args)).get("data")}, a.json))

    p_s = sub.add_parser("skills", help="技能路由")
    p_s.add_argument("--scope", default="active")
    p_s.add_argument("--keyword", default="")
    p_s.set_defaults(func=lambda a: _print(route_skills(a.scope, a.keyword), a.json))

    p_gt = sub.add_parser("gate", help="门禁直通")
    p_gt.add_argument("role")
    p_gt.add_argument("tool")
    p_gt.add_argument("args", nargs="*")
    p_gt.set_defaults(func=lambda a: _print(gate_call(a.role, a.tool, _kv(a.args)), a.json))

    p_l = sub.add_parser("learn", help="经验蒸馏")
    p_l.add_argument("--project", default="")
    p_l.add_argument("--limit", type=int, default=10)
    p_l.set_defaults(func=lambda a: _print(learn(a.project, a.limit), a.json))

    p_cs = sub.add_parser("constitution", help="宪法层检查（只读）")
    p_cs.add_argument("--path", action="append", default=[],
                      help="要检查的路径，可重复；不给则只做完整性自检")
    p_cs.set_defaults(func=lambda a: _print(
        constitution_check("", paths=a.path), a.json))

    p_mc = sub.add_parser("mcps", help="备用能力模块（主流程不经过）")
    p_mc.add_argument("name", nargs="?", default="", help="按名字过滤，如 queue")
    p_mc.set_defaults(func=lambda a: _print(list_mcps(a.name), a.json))

    p_v = sub.add_parser("version", help="版本与迭代记录")
    p_v.add_argument("-m", "--message", default="",
                     help="记录一次迭代：把当前改动提交，附上这句说明")
    p_v.set_defaults(func=lambda a: _print(
        version_record(a.message) if a.message else version_info(), a.json))

    p_st = sub.add_parser("stats", help="记忆统计")
    p_st.set_defaults(func=lambda a: _print(memory_stats(), a.json))

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    try:
        r = args.func(args)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return r if isinstance(r, int) else 0


def _kv(items: list[str]) -> dict[str, Any]:
    """把 key=value / JSON 参数转成 dict。"""
    if not items:
        return {}
    if len(items) == 1 and items[0].strip().startswith("{"):
        return _try_json(items[0])
    out: dict[str, Any] = {}
    for it in items:
        if "=" not in it:
            continue
        k, v = it.split("=", 1)
        low = v.lower()
        if low == "true":
            out[k] = True
        elif low == "false":
            out[k] = False
        elif low in ("null", "none"):
            out[k] = None
        else:
            try:
                out[k] = int(v)
            except ValueError:
                out[k] = v
    return out


if __name__ == "__main__":
    sys.exit(main())
