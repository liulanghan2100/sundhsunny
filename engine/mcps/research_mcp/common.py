# -*- coding: utf-8 -*-
"""Research MCP server.

This MCP supports the AI execution manual's early research gates. It does not
replace browsing or source review; it standardizes scope, source plans,
candidate comparison, risk checks, and report artifacts.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from _shared.io import _json as shared_json
from _shared.time import _now as shared_now
from _shared.io import _loads as shared_loads

ROOT = Path(__file__).resolve().parents[3]        # 包根（打包后层级比源库多一层 engine/mcps）
# 运行时数据统一落 data/mcps/，避免污染包根
DATA_ROOT = ROOT / "data" / "mcps"
REPORT_DIR = DATA_ROOT / "07_流程调研"
DEFAULT_SOURCES = ("pypi", "npm", "github", "pi", "web")


def _loads(value: str | list | dict | None, default: Any) -> Any:
    return shared_loads(value, default)


def _split_csv(value: str) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _json(data: dict) -> str:
    return shared_json(data)


def _url(url: str) -> dict:
    return {"url": url, "status": "manual_review_required"}


def _fetch_json(url: str, timeout: int = 10) -> tuple[dict | None, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "research-mcp/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace")), "ok"
    except Exception as exc:  # network is optional in this MCP
        return None, f"unavailable: {exc}"


def _source_urls(query: str) -> dict:
    q = urllib.parse.quote_plus(query)
    return {
        "pypi": f"https://pypi.org/search/?q={q}",
        "npm": f"https://www.npmjs.com/search?q={q}",
        "github": f"https://github.com/search?q={q}&type=repositories",
        "pi": f"https://pi.dev/search?q={q}",
        "web": f"https://www.google.com/search?q={q}",
    }


def _candidate_score(c: dict) -> int:
    score = 0
    if c.get("official"):
        score += 3
    if c.get("recent"):
        score += 2
    if c.get("maintained"):
        score += 2
    if c.get("license_ok", True):
        score += 1
    if c.get("fits_scope", True):
        score += 2
    if c.get("security_risk"):
        score -= 3
    if c.get("maintenance_risk"):
        score -= 2
    return score


def build_server() -> FastMCP:
    mcp = FastMCP("research-mcp")

    @mcp.tool()
    def research_brief(project: str, goal: str, context: str = "", sources: str = "pypi,npm,github,pi,web") -> str:
        """Generate the research scope required before technical selection or implementation."""
        source_list = _split_csv(sources) or list(DEFAULT_SOURCES)
        return _json({
            "project": project,
            "goal": goal,
            "context": context,
            "manual_nodes": [2, 8, 11, 15],
            "required_questions": [
                "外部是否已有成熟工具/库/Agent规则可复用？",
                "官方文档或主仓库是否仍在维护？",
                "自研相对复用的必要性是什么？",
                "许可证、安全、维护风险是否可接受？",
                "哪些方案明确不做，为什么？",
            ],
            "sources": source_list,
            "source_urls": {k: v for k, v in _source_urls(goal).items() if k in source_list},
            "output_contract": {
                "candidates": [],
                "recommended_option": "reuse | build | defer | hybrid",
                "why_not_others": [],
                "risks": [],
                "next_action": "进入节点8选型 | 打回重新调研 | 进入节点15实现",
            },
        })

    @mcp.tool()
    def pyp_search(query: str, packages: str = "", live: bool = False) -> str:
        """Plan PyPI research and optionally fetch exact package metadata via PyPI JSON API."""
        names = _split_csv(packages)
        found = []
        for name in names:
            item = {"name": name, "url": f"https://pypi.org/project/{urllib.parse.quote(name)}/"}
            if live:
                data, status = _fetch_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
                item["live_status"] = status
                if data:
                    info = data.get("info", {})
                    item.update({
                        "version": info.get("version"),
                        "summary": info.get("summary"),
                        "license": info.get("license"),
                        "project_urls": info.get("project_urls"),
                    })
            found.append(item)
        return _json({
            "source": "PyPI",
            "query": query,
            "search_url": _source_urls(query)["pypi"],
            "exact_packages": found,
            "manual_review": ["版本更新时间", "维护者/主页", "许可证", "下载量或社区采用", "是否有安全公告"],
        })

    @mcp.tool()
    def npm_search(query: str, packages: str = "", live: bool = False) -> str:
        """Plan npm research and optionally fetch exact package metadata from the npm registry."""
        names = _split_csv(packages)
        found = []
        for name in names:
            encoded = urllib.parse.quote(name, safe="")
            item = {"name": name, "url": f"https://www.npmjs.com/package/{encoded}"}
            if live:
                data, status = _fetch_json(f"https://registry.npmjs.org/{encoded}")
                item["live_status"] = status
                if data:
                    latest = data.get("dist-tags", {}).get("latest")
                    info = data.get("versions", {}).get(latest, {}) if latest else {}
                    item.update({
                        "latest": latest,
                        "description": info.get("description"),
                        "license": info.get("license"),
                        "homepage": info.get("homepage"),
                        "repository": info.get("repository"),
                    })
            found.append(item)
        return _json({
            "source": "npm",
            "query": query,
            "search_url": _source_urls(query)["npm"],
            "exact_packages": found,
            "manual_review": ["版本更新时间", "维护者", "许可证", "依赖树风险", "下载趋势"],
        })

    @mcp.tool()
    def github_search(query: str, repos: str = "", live: bool = False) -> str:
        """Plan GitHub research and optionally fetch exact public repo metadata."""
        repo_list = _split_csv(repos)
        found = []
        for repo in repo_list:
            item = {"repo": repo, "url": f"https://github.com/{repo}"}
            if live:
                data, status = _fetch_json(f"https://api.github.com/repos/{repo}")
                item["live_status"] = status
                if data:
                    item.update({
                        "stars": data.get("stargazers_count"),
                        "forks": data.get("forks_count"),
                        "updated_at": data.get("updated_at"),
                        "license": (data.get("license") or {}).get("spdx_id"),
                        "description": data.get("description"),
                    })
            found.append(item)
        return _json({
            "source": "GitHub",
            "query": query,
            "search_url": _source_urls(query)["github"],
            "exact_repos": found,
            "manual_review": ["README质量", "最近提交", "issue活跃度", "许可证", "是否有release/测试/CI"],
        })

    @mcp.tool()
    def pi_search(query: str) -> str:
        """Plan Pi/Agent Skills research for AI-agent rules, MCPs, and skills."""
        q = urllib.parse.quote_plus(query)
        return _json({
            "source": "Pi / Agent Skills",
            "query": query,
            "search_urls": [
                f"https://pi.dev/search?q={q}",
                f"https://mcpservers.org/search?q={q}",
            ],
            "manual_review": ["适用Agent", "安装方式", "规则边界", "是否可移植到Codex", "是否会覆盖手册门禁"],
        })

    @mcp.tool()
    def web_scan(query: str, domains: str = "") -> str:
        """Create a general web scan plan with concrete URLs and review criteria."""
        domain_list = _split_csv(domains)
        q = urllib.parse.quote_plus(query)
        urls = [_url(_source_urls(query)["web"])]
        for domain in domain_list:
            urls.append(_url(f"https://www.google.com/search?q=site%3A{urllib.parse.quote_plus(domain)}+{q}"))
        return _json({
            "source": "web",
            "query": query,
            "domains": domain_list,
            "urls": urls,
            "manual_review": ["官方来源优先", "发布日期", "版本号", "作者/组织可信度", "是否有反例或争议"],
        })

    @mcp.tool()
    def compare_options(problem: str, candidates_json: str) -> str:
        """Compare build/reuse/defer candidates. candidates_json is a list of candidate dicts."""
        candidates = _loads(candidates_json, [])
        ranked = []
        for c in candidates:
            item = dict(c)
            item["score"] = _candidate_score(item)
            if item["score"] >= 6:
                item["fit"] = "strong"
            elif item["score"] >= 3:
                item["fit"] = "possible"
            else:
                item["fit"] = "weak"
            ranked.append(item)
        ranked.sort(key=lambda x: x["score"], reverse=True)
        recommendation = "defer"
        if ranked:
            top = ranked[0]
            recommendation = "reuse" if top["fit"] == "strong" else "hybrid" if top["fit"] == "possible" else "build"
        return _json({
            "problem": problem,
            "ranked_candidates": ranked,
            "recommended_option": recommendation,
            "why_not_others": [
                {"name": c.get("name") or c.get("repo") or c.get("url", "candidate"), "reason": c.get("reject_reason", "score lower than recommended option")}
                for c in ranked[1:]
            ],
        })

    @mcp.tool()
    def risk_check(candidates_json: str) -> str:
        """Check candidate risks for license, maintenance, security, lock-in, and scope fit."""
        candidates = _loads(candidates_json, [])
        risks = []
        for c in candidates:
            name = c.get("name") or c.get("repo") or c.get("url", "candidate")
            item_risks = []
            if not c.get("license_ok", True):
                item_risks.append("license")
            if c.get("maintenance_risk"):
                item_risks.append("maintenance")
            if c.get("security_risk"):
                item_risks.append("security")
            if c.get("lock_in"):
                item_risks.append("lock_in")
            if not c.get("fits_scope", True):
                item_risks.append("scope_mismatch")
            risks.append({"candidate": name, "risks": item_risks or ["none_flagged"], "action": "mitigate_or_reject" if item_risks else "usable"})
        return _json({"risk_matrix": risks, "manual_gate": "节点8选型前必须处置 high/unknown 风险"})

    @mcp.tool()
    def write_research_report(project: str, title: str, goal: str, findings_json: str,
                              recommendation: str, next_action: str = "进入节点8选型") -> str:
        """Write a manual-gates-compatible research report into 07_流程调研."""
        findings = _loads(findings_json, [])
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in project if c.isalnum() or c in "-_") or "research"
        path = REPORT_DIR / f"{safe}_research_report.md"
        lines = [
            f"# {title}",
            "",
            f"- 项目：{project}",
            f"- 目标：{goal}",
            f"- 生成时间：{datetime.now(timezone.utc).isoformat()}",
            "",
            "## 调研发现",
            "",
        ]
        if findings:
            for idx, item in enumerate(findings, 1):
                lines.append(f"{idx}. {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append("暂无结构化发现；需补充候选方案后重跑。")
        lines.extend([
            "",
            "## 推荐结论",
            "",
            recommendation,
            "",
            "## 下一步",
            "",
            next_action,
            "",
            "## 手册门禁映射",
            "",
            "- 节点2：外部方案扫描",
            "- 节点8：技术选型证据",
            "- 节点11：基线/主流方案参考",
            "- 节点15：开发前复用优先检查",
        ])
        path.write_text("\n".join(lines), encoding="utf-8")
        return _json({"report_path": str(path), "status": "written", "next_action": next_action})

    return mcp


def main() -> None:
    build_server().run()

