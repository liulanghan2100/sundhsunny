---
name: market-rehearsal
description: Use when predicting how a market or opinion landscape will react to an event (earnings, policy, price change, news, rumors) via multi-agent rehearsal. Extract scenario, build ontology with A-share stakeholder templates, plan a 2-3 branch-driver simulation, produce a forecast brief with 3+ branches and evidence, interrogate actors with 5+ counterfactual questions, then revise branches. Use when the user asks for market reaction prediction, opinion evolution, PR/crisis rehearsal, policy impact forecast, or what-if scenario rehearsal in investing context.
---
# Market-Rehearsal（市场反应预演）

把「种子事件」变成多利益方群体推演，回答**"事件之后，市场/舆情会怎样演化"**。
与 debate-protocol 分工：debate 管"该不该做"，本技能管"会怎样演化"。

红线：
- **预演 ≠ 预测**：输出为情景推演，非确定性预测
- **不构成投资建议**，不实盘下单
- 分支必须带证据，事实与推断显式分离
- 无数据时不编造数字

## 1. 场景抽取
从种子事件提取：
- 核心实体：公司/大股东/机构/散户/经销商/监管/同行/媒体
- 关系：supports / opposes / depends_on / causes / blocks / influences / allocates
- 时间锚点：已发生/待定/假设/期限约束
- 显式约束：必须发生/禁止发生/时间窗
只保留**能改变结果**的实体关系；保留 <8 个。

## 2. 推理目标识别
标记：决策点、约束违例（会推翻预测的事件）、可观测信号（证实/证伪各分支）、2-3 个翻转变量。
无清晰决策点 → 收窄场景或向用户追问。

## 3. 本体论（Actor 模板 + 关系）
按事件类型启用相关 Actor（不必全 8 类）：

| Actor | 核心激励 | 可观测信号 |
|---|---|---|
| 上市公司/管理层 | 股价/业绩/融资 | 公告/互动易 |
| 大股东/实控人 | 减持窗口/质押安全 | 权益变动 |
| 机构投资者 | 比较基准/申赎压力 | 龙虎榜/持仓披露 |
| 散户 | 情绪/跟风 | 换手率/舆情 |
| 经销商/渠道 | 库存/价差/动销 | 批价/渠道调研 |
| 监管机构 | 合规/舆情压力 | 监管公告 |
| 同行竞争者 | 份额/定价跟随 | 同行公告/价格 |
| 媒体/KOL | 流量/立场 | 文章/热榜 |

关系定义：方向 + 含义 + 可观测/推断/假设分级 + 是否影响推演行为。

## 4. 模拟计划（离线）
- 角色与激励（每类 actor 一句）
- 记忆范围：种子事实 + 上下文 + 分歧驱动信号
- 冲突与联盟模式
- **2-3 个 Branch driver**（候选池）：业绩传导/库存周期/政策限制/情绪指标/流动性/事件催化——每个 driver 给可观测翻转信号
- 停止条件：目标日期 / 稳定收敛 / 明确分裂

## 5. 预测简报（固定结构）
```text
预测目标：<事件>后 <时间窗> 内 <哪方/哪指标> 会怎样
场景摘要：核心张力一句话
Actor 表：启用 actor + 激励 + 信号
分支：
  分支A（最可能）：<路径> ｜ 证据：<事实>
  分支B/C/D（备选）：<路径> ｜ 证据：<事实/推断标注>
置信度：高/中/低 ｜ 不确定性来源：<清单>
```
最低质量线：**≥3 条分支**，每条带证据。

## 6. 预测链抽取
追溯：谁的行动推动了结果 / 哪些约束封死了备选分支 / 哪些假设错了会反转预测。简报必须暴露这条链，而非只给最可能轨迹。

## 7. 世界访谈（反事实，≥5 问）
对关键 actor 提问，暴露：动机/约束/联盟/冲击反应/公开声明与私利差异。
- 问反事实："如果 X 变了你会怎样"
- 问隐藏约束："什么约束会迫使你改变行为"
- 问冲击："如果出现 Y 黑天鹅你会怎么反应"
答案冲突 = 信号，不是噪音。

## 8. 修订规则
访谈结果 → 分支权重调整的显式规则。
**强制：至少 1 条分支在访谈后修订。** 最终输出必须区分 事实 / 推断 / 不确定性。

## 质量门（7 问，全过才交付）
1. 预测的具体结果是什么？
2. 哪些 actor 在该结果上有冲突激励？
3. 哪 2-3 个信号翻转会改变结果？
4. 如何检测稳定收敛或不可逆分裂？
5. 什么场景不适合本技能？（纯技术面→math-model-selector；该不该买→debate-protocol）
6. 计划能否产出 ≥3 条有意义分支？
7. 简报能否用证据支撑每条分支？

## 参考
- mechanism_v0.1.md：上游机制清单与质量门来源
- design_v0.2.md：A股正业化改造设计（Actor/Branch driver/输出模板）
