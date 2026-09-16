---
name: trading-decision-workflow
description: 交易决策全流程工作流——把「该不该碰这个标的」拆成 事实包→基本面分析→多空辩论→风控检查→决策综合→复盘登记 六步流水线，串联 research/financial_data.py、graham-dodd-security-analysis、debate-protocol、decision-review-loop 四个技能。蒸馏自 TradingAgents 全链路设计（数据→分析→辩论→风控→决策→复盘，arXiv:2412.20138）。当用户说「分析一下这个股票」「要不要买XX」「帮我研究XX能不能投」「投研流程」「交易决策」「做个投资决策」时触发。
---

# 交易决策全流程工作流（trading-decision-workflow）

把一个投资标的从「听说」走到「经对抗检验的决策 + 可复盘的登记」，共 6 步。蒸馏自 TradingAgents 的 7 角色交易公司模拟——裁剪掉本地跑不动的实盘执行环节，保留决策质量链条。

> 🔴 **红线（不可协商）**：本工作流产出是**研究/分析结论**，不构成投资建议，**绝不输出自动下单指令**（对齐 math-model-selector 红线）。STOCKBENCH/KTD-FIN 实证：LLM 交易决策当前无稳定 alpha，本工作流的价值是**流程完整性与可复盘性**，不是"必胜策略"。

## 触发词

「分析一下这个股票」「要不要买 XX」「帮我研究 XX 能不能投」「投研流程」「交易决策」「投资决策」

## 何时用 / 何时不用

**用**：用户对一个具体标的/资产要做"碰还是不碰"的判断，且愿意走完整流程（不是随口一问）。
**不用**：纯行情查询（直接查报价）；宏观/行业研究无具体标的（用 research）；已有结论只要复盘（直接用 decision-review-loop）；要求实时盯盘/自动交易（红线，拒绝）。

## 核心流程（6 步，逐步落盘）

### 第 0 步：界定议题
- 明确标的（代码/名称）、市场（A股/美股/其他）、决策问题（买/卖/持有/观望）、时间尺度
- 检索历史记忆：若 decision-review-loop 已积累该标的或同类决策的教训，**先读教训再开工**（`experience-memory-mcp` 的 `search_memory`）

### 第 1 步：事实包（research 技能 + financial_data.py）
```powershell
# A股
python 04_技能包/skills-shared-candidate/research/financial_data.py A 600519 --balance
# 美股
python 04_技能包/skills-shared-candidate/research/financial_data.py US AAPL --filings
```
- **依赖现状（2026-08-09 实测）**：美股路径（SEC EDGAR，仅需 requests）在当前托管 Python 可直接跑通；A股路径需 `pip install akshare`（当前托管 Python 与 .venv 均未安装）。A股抓取不可用时降级方案：让用户贴报表/公告关键数字并标注"用户手工提供"，**禁止用模型记忆里的财务数字凑事实包**
- 事实包不足（如行业格局、竞争、新闻面）时调用 research 补全，每条标注来源
- **无事实包不进入下一步**

### 第 2 步：基本面分析（graham-dodd-security-analysis）
- 按该技能 9 步产出分析备忘录：投资 vs 投机定性、资产负债表、盈利质量、内在价值**区间**、安全边际、机会成本
- 结论限定在五档：`pass / watchlist / research more / candidate / avoid`

### 第 3 步：多空辩论（debate-protocol）
- 把第 1-2 步的事实包+备忘录作为辩论输入，走完整 5 步（立场隔离→交叉质询→修订→主持人综合）
- 产出：共识 / 分歧 / 关键风险 / 置信度

### 第 4 步：风控检查（辩论之后、结论之前，独立执行）
- **必须是独立段落**：风控回答不得与辩论综合写在同一段输出里"顺带完成"——分开产出，防止被辩论结论锚定
- 逐项回答：最大可接受回撤是多少？什么条件下此决策**一定错**（失效条件）？仓位假设是否过度集中？结论是否依赖单一假设？
- 任何一项答不上来 → 结论降档（candidate → watchlist，或标注"research more"）

### 第 5 步：决策综合 + 复盘登记
- 输出决策卡（格式见下），并**立即登记**到 decision-review-loop：标的、决策、理由、置信度、失效条件、复盘日期
- **没有登记的决策等于没做**——这是本工作流区别于一次性分析的关键

**决策卡输出格式**：

```text
标的：{代码/名称，市场}
议题：{买/卖/持有/观望}
事实包：{文件路径}
基本面结论：{pass|watchlist|research more|candidate|avoid}
辩论共识：...
辩论分歧：...
关键风险：...
失效条件：{什么发生时此决策被证伪}
综合结论：{candidate|watchlist|research more|avoid|pass}
置信度：{高|中|低}（低时说明主要不确定性）
复盘登记：{decision-review-loop 记录 ID / 路径}
```

## 统一产物（每次投研必落盘 5 个固定文件）

本工作流每个标的的完整输出**必须落盘为 5 个固定文件**（统一命名、统一格式），否则不可复盘、不可对比、不可蒸馏经验。落盘根目录约定 `runs/<标的>_<as-of>/`。

| 文件 | 内容 | 生成方 | 硬性要求 |
|---|---|---|---|
| `facts.md` | 事实包：行情/财务/新闻/政策 | research + financial_data.py | 每条事实带来源；**无事实包不进入下一步** |
| `fundamental_memo.md` | 基本面分析备忘录 | graham-dodd-security-analysis | 含内在价值**区间** + 安全边际；无安全边际不得给 candidate |
| `bull_bear_debate.md` | 多空辩论记录 | debate-protocol（5 步） | 含 共识/分歧/关键风险/置信度 |
| `risk_check.md` | 风控检查（独立段落） | 工作流第 4 步 | 回撤/失效条件/集中度/单一假设 逐项作答 |
| `decision_card.md` | 最终决策卡 | 工作流第 5 步 | 五档结论 + 置信度 + 复盘登记 ID |

自动/半自动路径：`multi_agent_flow_test.py`（信号层）产出 `run.json`，`artifact_builder.py` 一键生成 5 文件 + 自动检查报告；手工 LLM 路径按上表同样落盘。**任何产物缺失 → 该标的不能算跑完。**

## 检查清单

- [ ] 历史教训已检索（同标的/同类决策）
- [ ] 5 个产物文件（facts/fundamental_memo/bull_bear_debate/risk_check/decision_card）已全部落盘到 `runs/<标的>_<as-of>/`
- [ ] 事实包已落盘且每条有来源
- [ ] graham-dodd 备忘录含内在价值区间与安全边际（无安全边际不得给 candidate）
- [ ] 辩论完成 ≥1 轮交叉质询，未回答质询已标注
- [ ] 风控四问逐项作答，答不上来的已降档
- [ ] 决策卡已登记到 decision-review-loop，含失效条件与复盘日期
- [ ] 全程无下单指令、无收益承诺措辞

## 反模式黑名单

- ❌ 跳过事实包直接开辩（空谈）
- ❌ 把 graham-dodd 的 candidate 当最终结论，不走辩论和风控
- ❌ 风控四问走过场（"风险已考虑"不算回答）
- ❌ 决策完不登记，复盘环节断链
- ❌ 输出"建议买入/卖出"指令式措辞（红线）
- ❌ 把流程跑完当作结论正确的证据（流程只保证可复盘，不保证正确）

## 诚实边界（≥3 条）

1. **不预测价格**：本工作流评估的是"决策质量"，不是"未来走势"；即便流程完整，结论仍可能错——KTD-FIN 实证 LLM 收益主要来自市场 beta 而非选股 alpha。
2. **数据时效性**：financial_data.py 抓的是最近披露报表，重大事项（停牌、暴雷、重组）可能在报表之外，需用户在第 1 步补充。
3. **单模型局限**：本地执行时多空两方、分析、风控都由同一 LLM 扮演，立场隔离靠流程纪律而非真正的模型隔离，对抗强度弱于 TradingAgents 原生多模型混配。
4. **不构成投资建议**：产出仅供研究参考，实盘决策与盈亏由用户自负；不得用于自动交易。

## 参考来源

- TradingAgents 论文（一手）：Y. Xiao et al., arXiv:2412.20138 —— 全链路角色设计（分析师→辩论→交易员→风控→组合经理）
- STOCKBENCH（一手）：arXiv:2510.02209 —— 实证边界
- KTD-FIN（一手）：arXiv:2605.28359 —— alpha/beta 归因与泄露控制
- 调研报告：`09_投研/TradingAgentResearch/pre_research_report.md`（2026-08-09，模式 2）
- 依赖技能：`research`、`graham-dodd-security-analysis`、`debate-protocol`、`decision-review-loop`
