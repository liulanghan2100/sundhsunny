# -*- coding: utf-8 -*-
"""分工 MCP 服务器工厂：每个阶段一个 MCP 服务，共用同一套手册数据与项目状态。"""
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import learning
from . import state as store
from .manual_data import (AUTONOMY_LEVELS, DEFAULT_AUTONOMY, DEFAULT_TRACK,
                          MCKINSEY_STEPS, SCHEDULE, STAGE_BY_KEY, STAGES,
                          TRACKS, track_node_ids)


def _project_track(st: dict) -> str:
    return st.get("track", DEFAULT_TRACK)


def _filtered_nodes(st: dict, nodes: list) -> list:
    """按项目轨道过滤节点列表。"""
    ids = track_node_ids(_project_track(st), [n["id"] for n in nodes])
    return [n for n in nodes if n["id"] in ids]


def _quality_metrics(st: dict) -> dict:
    """v3 六西格玛 Measure：过程质量指标（历史数据可复算）。"""
    nodes = st.get("nodes", {})
    hist = st.get("history", [])
    passed_ids = {k for k, v in nodes.items() if v.get("status") == "passed"}
    reopened_ids = {str(h["node_id"]) for h in hist if h.get("type") == "reopen"}
    flaky = passed_ids & reopened_ids
    reviews = [h for h in hist if h.get("type") == "review"]
    revoked = [h for h in reviews if h.get("verdict") == "revoked"]
    otp = 1 - len(flaky) / max(len(passed_ids), 1)
    return {
        "提交节点数": len(nodes),
        "一次通过率": f"{otp:.1%}" if passed_ids else "—",
        "被 reopen 的通过节点": sorted(int(x) for x in flaky),
        "对抗评审": len(reviews),
        "评审撤销率": f"{len(revoked)/max(len(reviews),1):.0%}" if reviews else "—",
        "迭代轮次": st.get("iteration", 1),
        "打回次数": sum(1 for h in hist if h.get("type") == "reopen"),
    }


def _merged_stage(stage_key: str) -> dict:
    """基线阶段元信息 + 合并后的节点列表。"""
    base = STAGE_BY_KEY[stage_key]
    for s in learning.get_stages():
        if s["key"] == stage_key:
            merged = dict(base)
            merged["nodes"] = s["nodes"]
            return merged
    return base


def _fmt_node(n: dict, status: str = None) -> dict:
    d = {
        "节点": n["id"],
        "名称": n["name"],
        "核心动作": n["action"],
        "关键产出": n["output"],
        "验收标准": n["acceptance"],
    }
    if status:
        d["当前状态"] = status
    return d


def build_server(stage_key: str) -> FastMCP:
    stage = _merged_stage(stage_key)
    mcp = FastMCP(f"manual-{stage_key}")

    @mcp.tool()
    def role_brief() -> str:
        """查看本 MCP 对应分工的职责、输入与产出（我负责什么）。"""
        return json.dumps({
            "分工": stage["name"],
            "核心问题": stage["question"],
            "使命": stage["mission"],
            "输入（上阶段交付）": stage["inputs"],
            "我的产出": stage["outputs"],
            "节点数": len(stage["nodes"]),
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def checklist(project: str = "default") -> str:
        """获取本阶段的节点清单（核心动作/关键产出/验收标准），并带上当前项目里每个节点的通过状态。开发前先看它。"""
        st = store.load(project)
        nodes = _filtered_nodes(st, stage["nodes"])
        return json.dumps({
            "阶段": stage["name"],
            "项目": project,
            "轨道": TRACKS[_project_track(st)]["name"],
            "节点清单": [_fmt_node(n, store.node_status(st, n["id"])) for n in nodes],
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def plan_next(project: str = "default") -> str:
        """边规划：根据项目当前状态，返回全局下一个该做的节点（跨阶段），以及本阶段内未完成的节点。"""
        st = store.load(project)
        # 全局下一个节点（按合并后的阶段树 + 项目轨道过滤）
        next_global = None
        for s in learning.get_stages():
            for n in _filtered_nodes(st, s["nodes"]):
                if store.node_status(st, n["id"]) != "passed":
                    next_global = (s, n)
                    break
            if next_global:
                break
        mine_todo = [
            _fmt_node(n, store.node_status(st, n["id"]))
            for n in _filtered_nodes(st, stage["nodes"])
            if store.node_status(st, n["id"]) != "passed"
        ]
        if next_global is None:
            total = len(track_node_ids(_project_track(st), list(learning.get_node_index())))
            return json.dumps({"项目": project, "结论": f"当前轨道全部 {total} 个节点已通过，项目闭环完成。可以做下阶段规划或新项目立项。"}, ensure_ascii=False, indent=2)
        s, n = next_global
        return json.dumps({
            "项目": project,
            "轨道": TRACKS[_project_track(st)]["name"],
            "授权级别": f"{st.get('autonomy', DEFAULT_AUTONOMY)} {AUTONOMY_LEVELS.get(st.get('autonomy', DEFAULT_AUTONOMY), '')}",
            "全局下一节点": {"所属阶段": s["name"], **_fmt_node(n)},
            "是否我的分工": s["key"] == stage_key,
            "本阶段未完成节点": mine_todo or "本阶段节点已全部通过",
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def submit_check(project: str, node_id: int, artifact_path: str, passed: bool, notes: str = "") -> str:
        """边检查：提交一个节点的验收结果。
        artifact_path 为本节点关键产出物的文件路径（会做存在性与非空校验）；
        passed 由 AI 对照该节点的『验收标准』逐条判断后给出结论；
        notes 记录验收说明（哪条达标、哪条待补）。"""
        idx = learning.get_node_index()
        if node_id not in idx:
            return json.dumps({"错误": f"节点 {node_id} 不存在，合法范围 1-{max(idx)}"}, ensure_ascii=False)
        st = store.load(project)
        track = _project_track(st)
        allowed = track_node_ids(track, list(idx))
        if node_id not in allowed:
            return json.dumps({
                "错误": f"节点 {node_id} 不在当前轨道（{TRACKS[track]['name']}）范围内",
                "轨内节点": allowed,
                "提示": "小改动请保持 quick 轨只走关键节点；如需全流程请先用 set_mode 切换 standard/enterprise",
            }, ensure_ascii=False)
        s, n = idx[node_id]
        p = Path(artifact_path)
        file_ok = p.exists() and p.is_file() and p.stat().st_size > 0
        verdict = "passed" if (passed and file_ok) else "failed"
        store.record(project, node_id, verdict, artifact_path, notes)
        return json.dumps({
            "节点": n["id"],
            "名称": n["name"],
            "验收标准": n["acceptance"],
            "文件校验": "通过（存在且非空）" if file_ok else f"未通过（{artifact_path} 不存在或为空）",
            "AI判断": "达标" if passed else "不达标",
            "最终结论": "✅ 通过" if verdict == "passed" else "❌ 未通过（文件校验与AI判断需同时满足）",
            "备注": notes,
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def gate_report(project: str = "default") -> str:
        """门禁报告：全项目 7 阶段通过情况总览，标明当前卡在哪、本阶段能否放行进入下一阶段。"""
        st = store.load(project)
        track = _project_track(st)
        report = []
        for s in learning.get_stages():
            nodes = _filtered_nodes(st, s["nodes"])
            total = len(nodes)
            passed = sum(1 for n in nodes if store.node_status(st, n["id"]) == "passed")
            failed = [n["id"] for n in nodes if store.node_status(st, n["id"]) == "failed"]
            missing_review = []
            gate_ok = passed == total
            if gate_ok and track == "enterprise":
                # enterprise 轨：每个通过节点须至少有 1 次 sustained 对抗评审
                missing_review = [
                    n["id"] for n in nodes
                    if not any(r.get("verdict") == "sustained"
                               for r in st.get("nodes", {}).get(str(n["id"]), {}).get("reviews", []))
                ]
                gate_ok = not missing_review
            report.append({
                "阶段": s["name"],
                "进度": f"{passed}/{total}",
                "门禁": "✅ 放行" if gate_ok else "⛔ 未达标",
                "未通过节点": failed or None,
                "缺审节点": missing_review or None,
                "是我": s["key"] == stage_key,
            })
        idx = learning.get_node_index()
        allowed = track_node_ids(track, list(idx))
        overall = sum(1 for nid in allowed if store.node_status(st, nid) == "passed")
        return json.dumps({
            "项目": project,
            "轨道": TRACKS[track]["name"],
            "授权级别": f"{st.get('autonomy', DEFAULT_AUTONOMY)} {AUTONOMY_LEVELS.get(st.get('autonomy', DEFAULT_AUTONOMY), '')}",
            "总进度": f"{overall}/{len(allowed)}",
            "过程质量": _quality_metrics(st),
            "各阶段门禁": report,
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def reopen_node(project: str, node_id: int, reason: str) -> str:
        """回退重开：当新发现推翻了之前的验收（如数据探索推翻问题定义、UAT 暴露架构缺陷），把已通过/未通过的节点打回 pending。
        迭代轮次自动 +1。回退不是失败，是 AI 项目的常态；门禁会随之重新关闭，直到节点重新验收通过。"""
        idx = learning.get_node_index()
        if node_id not in idx:
            return json.dumps({"错误": f"节点 {node_id} 不存在，合法范围 1-{max(idx)}"}, ensure_ascii=False)
        s, n = idx[node_id]
        st = store.reopen(project, node_id, reason)
        return json.dumps({
            "节点": n["id"],
            "名称": n["name"],
            "所属阶段": s["name"],
            "新状态": "pending（已打回）",
            "当前迭代轮次": st["iteration"],
            "原因": reason,
            "下一步": f"重新产出后再次调用 submit_check 验收；验收标准不变：{n['acceptance']}",
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def review_challenge(project: str, node_id: int, verdict: str = "", challenge_notes: str = "") -> str:
        """对抗评审：以独立评审视角质疑某节点的验收结论，防止"自己给自己打分"。
        两步用法：
        1) 不带 verdict 调用——返回该节点的验收记录 + 对抗性质疑清单，逐条逼问证据；
        2) 逐条回答后带 verdict 调用——verdict="sustained" 维持通过 / "revoked" 撤销（节点自动打回 pending，迭代+1）。
        阶段门禁前，至少对关键节点执行一次。"""
        idx = learning.get_node_index()
        if node_id not in idx:
            return json.dumps({"错误": f"节点 {node_id} 不存在，合法范围 1-{max(idx)}"}, ensure_ascii=False)
        s, n = idx[node_id]
        st = store.load(project)
        rec = st.get("nodes", {}).get(str(node_id), {})

        if not verdict:
            return json.dumps({
                "节点": n["id"],
                "名称": n["name"],
                "验收标准": n["acceptance"],
                "当前验收记录": rec or "尚未提交验收",
                "对抗性质疑清单": [
                    f"证据链：产出物 {rec.get('artifact', '?')} 是本轮真实产出的，还是拼凑/套模板凑数的？打开它，指出哪一段能证明「{n['name']}」的核心动作真的做了。",
                    f"标准逐条：把验收标准拆开——「{n['acceptance']}」——每一条是「有证据」「只是声称」还是「根本没覆盖」？",
                    "反例测试：在什么场景下这个产出会失效或被推翻？产出里有没有承认并处理这个场景？",
                    "独立性：验收理由是执行者视角（我做了什么）还是评审者视角（证据表明什么）？把 notes 里的形容词全部删掉，剩下的还是证据吗？",
                    "下游风险：如果此节点实际是错的，哪个下游节点最先爆炸？现在的产出有没有把风险传给下游？",
                ],
                "用法": "逐条写下回答，然后带 verdict 再调本工具：sustained=维持通过，revoked=撤销并打回",
            }, ensure_ascii=False, indent=2)

        if verdict not in ("sustained", "revoked"):
            return json.dumps({"错误": "verdict 只能是 sustained 或 revoked"}, ensure_ascii=False)
        store.add_review(project, node_id, verdict, challenge_notes)
        result = {"节点": n["id"], "名称": n["name"], "评审结论": verdict, "评审记录": challenge_notes}
        if verdict == "revoked":
            st2 = store.reopen(project, node_id, f"对抗评审撤销：{challenge_notes}")
            result["后续"] = f"节点已打回 pending，迭代轮次升至 {st2['iteration']}，需重新产出并验收"
        else:
            result["后续"] = "验收结论维持，评审记录已归档（可追溯）"
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    def mckinsey(step: int = 0) -> str:
        """麦肯锡结构化思维五步法。step=0 返回总览，step=1..5 返回对应步骤的行动清单。遇到拿不准的方向先过一遍。"""
        if step == 0:
            return json.dumps([{"step": s["step"], "name": s["name"]} for s in MCKINSEY_STEPS], ensure_ascii=False, indent=2)
        for s in MCKINSEY_STEPS:
            if s["step"] == step:
                return json.dumps(s, ensure_ascii=False, indent=2)
        return json.dumps({"错误": "step 取值 0-5"}, ensure_ascii=False)

    @mcp.tool()
    def full_map(project: str = "default") -> str:
        """全局作战图：7 阶段全部节点（含回流新增）一览 + 12 周 MVP 参考排期，并叠加当前项目进度。"""
        st = store.load(project)
        stages_view = []
        for s in learning.get_stages():
            nodes = _filtered_nodes(st, s["nodes"])
            stages_view.append({
                "阶段": s["name"],
                "节点": [{"id": n["id"], "名称": n["name"], "状态": store.node_status(st, n["id"])} for n in nodes],
            })
        return json.dumps({
            "项目": project,
            "轨道": TRACKS[_project_track(st)]["name"],
            "阶段地图": stages_view,
            "参考排期": SCHEDULE,
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    def feedback_loop(project: str, action: str, node_id: int = 0, stage_key: str = "",
                      name: str = "", action_desc: str = "", output: str = "",
                      acceptance: str = "", rationale: str = "") -> str:
        """经验回流：把复盘洞察写回手册，让体系随项目进化（对所有项目生效）。
        action="update_node"：更新已有节点的验收标准/核心动作/关键产出（node_id 必填，acceptance/action_desc/output/name 至少给一个）；
        action="add_node"：新增自定义节点（stage_key + name + acceptance 必填，id 自动分配，挂到对应阶段末尾）；
        action="list"：查看全部已回流的经验与日志。
        rationale 必填——每次回流必须留下"为什么"，可追溯、可审计。基线 25 节点永不删除，只会被增补。"""
        if action == "list":
            d = learning.load_learned()
            return json.dumps({
                "已更新节点": d["node_updates"],
                "新增节点": d["new_nodes"],
                "回流日志": d["log"],
            }, ensure_ascii=False, indent=2)
        if not rationale:
            return json.dumps({"错误": "rationale 必填：每次回流必须记录为什么"}, ensure_ascii=False)
        try:
            if action == "update_node":
                fields = {"name": name, "action": action_desc, "output": output, "acceptance": acceptance}
                diff = learning.apply_update(project, node_id, fields, rationale)
                return json.dumps({
                    "结果": f"✅ 节点 {node_id} 已更新（对所有项目生效）",
                    "旧 → 新对照": diff,
                    "rationale": rationale,
                }, ensure_ascii=False, indent=2)
            if action == "add_node":
                if not (stage_key and name and acceptance):
                    return json.dumps({"错误": "add_node 需要 stage_key + name + acceptance"}, ensure_ascii=False)
                node = learning.apply_new_node(project, stage_key, name, action_desc, output, acceptance, rationale)
                return json.dumps({
                    "结果": f"✅ 新节点 {node['id']} 已加入 {stage_key} 阶段（对所有项目生效）",
                    "节点": node,
                    "rationale": rationale,
                    "提示": "各阶段门禁分母已 +1，用 gate_report 查看",
                }, ensure_ascii=False, indent=2)
            return json.dumps({"错误": "action 只能是 update_node / add_node / list"}, ensure_ascii=False)
        except ValueError as e:
            return json.dumps({"错误": str(e)}, ensure_ascii=False)

    @mcp.tool()
    def set_mode(project: str, track: str = "", autonomy: str = "", reason: str = "") -> str:
        """v3 规模自适应：设置项目轨道与授权级别（立项时或规模变化时调用）。
        track：quick=5 个关键节点（小改/补丁）/ standard=全部节点（默认）/ enterprise=全部节点 + 每个通过节点须有一次 sustained 对抗评审；
        autonomy：L1=逐步请示 / L2=阶段请示（默认） / L3=全程自主。被打回会自动降级授权。
        reason 必填——每次切换留痕可审计。"""
        if not reason:
            return json.dumps({"错误": "reason 必填：每次切换必须留下为什么"}, ensure_ascii=False)
        if track and track not in TRACKS:
            return json.dumps({"错误": f"track 只能是 {list(TRACKS)}"}, ensure_ascii=False)
        if autonomy and autonomy not in AUTONOMY_LEVELS:
            return json.dumps({"错误": f"autonomy 只能是 {list(AUTONOMY_LEVELS)}"}, ensure_ascii=False)
        if not track and not autonomy:
            return json.dumps({"错误": "track 与 autonomy 至少给一个"}, ensure_ascii=False)
        st = store.set_mode(project, track, autonomy, reason)
        t = st.get("track", DEFAULT_TRACK)
        a = st.get("autonomy", DEFAULT_AUTONOMY)
        return json.dumps({
            "项目": project,
            "轨道": f"{t} {TRACKS[t]['name']}",
            "轨内节点": track_node_ids(t, list(learning.get_node_index())),
            "授权级别": f"{a} {AUTONOMY_LEVELS[a]}",
            "注意": "打回（reopen）将自动降级授权级别" if a != "L1" else "已是最低授权级别",
        }, ensure_ascii=False, indent=2)

    return mcp


def main(stage_key: str) -> None:
    build_server(stage_key).run()
