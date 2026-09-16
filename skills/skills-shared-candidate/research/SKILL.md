---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** — official docs, source code, specs, first-party APIs — not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.

## 一手财报数据源（投资标的事实包）

调研投资标的时，先跑配套抓取工具 `financial_data.py` 自动生成「事实包」Markdown（输出到本目录 `facts/`），再据此分析。事实包可直接作为 debate-protocol 第 1 步的输入。

```powershell
# A股：财务摘要 + 近三年财务指标（AkShare/东财，无需 key）
python 04_技能包/skills-shared-candidate/research/financial_data.py A 600519
# A股加抓三大报表
python 04_技能包/skills-shared-candidate/research/financial_data.py A 600519 --balance
# 美股：SEC EDGAR XBRL 公司事实（营收/净利/资产/负债/经营现金流，一手申报）
python 04_技能包/skills-shared-candidate/research/financial_data.py US AAPL
# 美股加最近 10-K/10-Q 申报链接（可进一步下载原文解析）
python 04_技能包/skills-shared-candidate/research/financial_data.py US AAPL --filings
```

**数据源口径（按一手性排序）**：
- 美股：SEC EDGAR companyfacts（XBRL，公司向 SEC 的原始申报）→ **一手**。10-K/10-Q 原文在 EDGAR 档案，可下载解析。
- A股：AkShare 的东方财富接口 → 财报数字来自交易所披露，属接近一手；如需绝对一手，抓巨潮资讯（cninfo）公告原文。
- ⚠️ 禁用：新闻摘要/自媒体/二手研报里的财务数字（如「营收大增」），必须回溯到报表原文再引用。

**接入自动化的方式**：在 manual-gates 调研门（N10）或 debate-protocol 第 1 步，先执行上述命令生成事实包文件，再让 LLM 基于文件内容分析——不要把抓取与分析混在一步，保证事实包可落盘、可复核、可溯源。
