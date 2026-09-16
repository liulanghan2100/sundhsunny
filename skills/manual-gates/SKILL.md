---
name: manual-gates
description: 按《个人AI项目执行手册》（7阶段27节点、规模自适应三轨）驱动开发节奏：在 AI 项目开发、写代码、做功能、冲刺规划、节点验收、阶段评审时使用。触发词包括"边开发边检查""按手册执行""节点验收""阶段门禁""plan_next""gate_report""set_mode""快速轨""开发前先看验收标准"以及任何围绕该手册节点的规划/检查/复盘请求。通过 7 个分工 MCP（strategy/design/data_ai/planning/dev/qa/ops）完成规划、验收与门禁判断，让开发始终带着验收标准进行。
---

# Manual Gates：带着验收标准开发

用手册的 27 个节点验收标准驱动每一次开发。核心原则：**先看标准再动手，做完立即验收，门禁不过不进入下一阶段。**

## 何时不用本技能

以下场景不进入门禁流程，直接完成即可：

- **纯问答与查询**：回答问题、解释概念、查资料做总结，不产生项目产物（文件/代码/报告）时。
- **探索性讨论**：还在与 owner 商量「要不要做、做什么」；定了要做事，再从 `full_map` 开始。
- **单点微修**：错别字、措辞、格式等不改变行为与语义的修改（单文件、几行以内、无逻辑变化）。
- **只读操作**：查看状态、`gate_report` / `plan_next` 查询、复盘历史记录——查询动作本身不是项目。
- **owner 明示豁免**：owner 说「不用走手册/直接做」时按其口令执行，但在回复中留一句「owner 口令豁免门禁」留痕。

判断原则：**不产生可验收产物的动作，不立项目**；产生产物就按规模选轨（小改 quick、新项目 standard、高风险 enterprise）。改动类型拿不准时仍从高（Core 从严）——本表豁免的是「走不走门禁」，不是「走多重」。

调研动作的例外另见 v6.1 节 `research_exception`（它只豁免联网调研，不豁免门禁本身）。

## 调用方式

优先走桥接脚本（不依赖客户端 MCP 注册），用 Bash 运行：

```bash
python "<skill_dir>/scripts/gate.py" <role> <tool> '<json-args>'
```

`<skill_dir>` 为本技能所在目录。需要 `mcp` 包（托管 Python 已装）。

若客户端已注册 7 个 `manual-*` MCP，也可直接调用同名工具，效果相同。

## 分工速查（role 参数）

| role | 阶段 | 节点 |
|---|---|---|
| `strategy` | 战略与定义 | 1-5, 27 |
| `design` | 需求与设计 | 6-9 |
| `data_ai` | 数据与基线模型 | 10-11 |
| `planning` | 计划与拆解 | 12-13 |
| `dev` | 开发与测试 | 14-17 |
| `qa` | 测试与验收 | 18-21, 26 |
| `ops` | 部署上线与运营 | 22-25 |

每个 role 提供 11 个工具：`role_brief`、`checklist`、`plan_next`、`submit_check`、`gate_report`、`mckinsey`、`full_map`、`reopen_node`、`review_challenge`、`feedback_loop`、`set_mode`。

## 规模自适应（v3）：按改动大小选轨道

立项或接手时先定轨道（不定则默认 standard 全流程）：

```bash
python scripts/gate.py strategy set_mode '{"project": "<项目名>", "track": "quick", "reason": "为什么这个规模够用"}'
```

| track | 节点范围 | 适用 | 额外约束 |
|---|---|---|---|
| `quick` | 4 / 9 / 17 / 19 / 24 五个关键节点 | 小改小修、补丁、文档更新 | 轨外节点提交会被拒绝 |
| `standard` | 全部 27 节点（默认） | 新项目全流程 | — |
| `enterprise` | 全部 27 节点 | 高风险 / 合规项目 | 每个通过节点须 ≥1 次 sustained 对抗评审，否则阶段门禁 ⛔ 并列出缺审节点 |

**改动类型 × 最低轨道（硬标准，源自 v3→v7 复盘实测：Core 改动 87% 曾误走 quick）**：

| 改动类型 | 判定 | 最低轨道 |
|---|---|---|
| **Core**：内核 / 运行时 / 门禁 / 状态结构 / 手册自升级 | 涉及 `manual_mcp` 内核、`run_*` 入口、state 结构、SKILL.md、README 骨架 | **standard（禁走 quick）** |
| **Capability**：新增 MCP / 技能 / 外部集成 | 新组件目录或新 MCP 注册 | standard |
| **App**：实战项目 / 内容生产 | 有独立业务产物 | quick 可用 |
| **Doc**：纯文档 / 调研 | 仅 md | quick 可用 |

拿不准类型时从高（Core 从严）；立项时在 `set_mode` 的 `reason` 里声明改动类型与匹配理由。

- 授权级别 `autonomy`：L1 逐步请示 / L2 阶段请示（默认）/ L3 全程自主；**被打回（reopen）自动降级** L3→L2→L1，切换必须填 `reason` 留痕。
- 存量项目零迁移：从未调用 `set_mode` 的项目一律按 standard + L2 解释，只读操作不改写状态文件。
- `gate_report` 新增「轨道 / 授权级别 / 过程质量」三块：一次通过率、评审撤销率、迭代轮次、打回次数，历史项目可复算。

## Ponytail 反过度工程规则（开发阶段内嵌）

Ponytail 只作为节点 15/16 的编码与评审约束，不替代手册门禁、证据链、对抗评审和复盘回流。冲突时以本手册、业务约束、安全合规为先。

- Quick 轨默认启用 Ponytail 思维；Standard 轨建议启用；Enterprise 轨仅作参考，合规、审计、安全冗余优先。
- 开发实现前先过决策阶梯：不需要存在就不写；代码库已有就复用；标准库能做就用标准库；原生平台能力能做就用原生能力；已安装依赖能做就用现有依赖；最后才写最小可行实现。
- 节点 15（并行开发）：新增代码、依赖或抽象前，必须能说明为什么不能复用现有能力。
- 节点 16（单元测试与代码评审）：必须检查是否存在可删除的包装层、重复实现、无必要依赖。

## Research MCP（外部调研前置）

涉及新项目、技术选型、模型/框架选择、开发前复用判断时，优先调用 `research-mcp` 形成外部调研证据，再进入手册节点验收。它服务节点 2/8/11/15：

- 节点 2：查竞品、替代品、开源项目、Agent 规则。
- 节点 8：对比自研 / 复用 / 接入现成工具，列出为什么不用备选方案。
- 节点 11：查主流 baseline、公开 benchmark、常见评估口径。
- 节点 15：开发前查 PyPI/npm/GitHub/Pi/Web，确认没有成熟方案再自研。

`research-mcp` 输出的调研报告必须包含：调研范围、来源 URL、候选方案、推荐方案、为什么不用其他方案、风险与下一步。

## Experience Memory MCP（经验样本记忆）

当任务涉及 Agent 自主学习、跨项目经验复用、失败模式沉淀、用户偏好记录时，使用 `experience-memory-mcp` 记录结构化经验：

`任务 → 决策 → 动作 → 结果 → 失败/通过 → 教训 → 下次检索`

它服务节点 15/16/17/19/24：

- 节点 15：开发动作前后记录任务快照、决策理由、工具调用结果。
- 节点 16：把评审发现记录为失败案例或修复模式。
- 节点 17：把冒烟/集成结果记录为 outcome。
- 节点 19：把评估结论和样本独立性记录为可检索经验。
- 节点 24：把复盘教训标记为 `rule_candidate`，进入项目级候选队列；只有完成
  `candidate -> shadow -> review_challenge -> owner approval -> promote` 后，才允许写回手册。

边界：它是外部经验记忆，不是神经网络训练器；不会自动改模型权重；不会自动修改手册标准。
`feedback_loop` 默认只创建项目级候选，`learned.json` 只有在 Shadow 通过、对抗评审
`sustained` 且 Owner 明确 `approve` 后，才能由显式 `promote` 写入。

## 技能路由检查点（自动触发）

C 类任务在节点 0（认知入口）分类后、开工第一个动作（full_map）之前，先跑统一技能调度器确定本次技能链：

```bash
python "09_投研/skill_os_mvp/scripts/dispatch.py" "<任务描述>" --stage <strategy|design|data_ai|planning|dev|qa|ops> --project <项目名>
```

- 返回的 `chain` 即本次应携带执行的技能清单（按评分排序，只从 `04_技能包/active_skills.json` 启用集挑选）。
- `suggest_promote` 列出场景/阶段需要但未启用的技能：如需启用由 owner 决策，走 `python "09_投研/skill_os_mvp/scripts/curate_skills.py" --enable <skill> --reason <准入理由>`。
- 每真正使用一个技能，调用 `python "09_投研/skill_os_mvp/scripts/record_usage.py" <skill> <项目名> <note>` 回写使用度量，让闲置可见、越用越准。
- 本检查点不替代门禁：manual-gates 仍是节奏与验收的唯一裁判，技能只是执行手段。

## 标准循环

**1. 开工/接手时**——先看全局与分工：

```bash
python scripts/gate.py strategy full_map '{"project": "<项目名>"}'
python scripts/gate.py <当前阶段role> role_brief
```

**2. 做某个节点前**——拿验收标准，带着标准开发：

```bash
python scripts/gate.py <role> checklist '{"project": "<项目名>"}'
```

**3. 节点产出后**——立即验收。把产出物写成文件，再调用 `submit_check`：

```bash
python scripts/gate.py <role> submit_check '{"project": "<项目名>", "node_id": 15, "artifact_path": "<产出文件绝对路径>", "passed": true, "notes": "哪条标准达标、哪条待补"}'
```

- `passed` 由你（AI）对照该节点"验收标准"逐条判断后给出；文件校验由 MCP 自动完成（存在且非空）。
- 结论 ❌ 时，按 notes 补齐后重新提交，不要带着未通过节点往下走。

**4. 规划下一步**：

```bash
python scripts/gate.py <role> plan_next '{"project": "<项目名>"}'
```

**5. 阶段收尾**——门禁判断，全过才进入下一阶段：

```bash
python scripts/gate.py <role> gate_report '{"project": "<项目名>"}'
```

**6. 阶段门禁前**——对关键节点做一次对抗评审（防止"自己给自己打分"）：

```bash
# 先取质疑清单，逐条写下回答
python scripts/gate.py <role> review_challenge '{"project": "<项目名>", "node_id": 15}'
# 再提交评审结论：sustained=维持通过；revoked=撤销（节点自动打回 pending，迭代+1）
python scripts/gate.py <role> review_challenge '{"project": "<项目名>", "node_id": 15, "verdict": "sustained", "challenge_notes": "五条质疑的回答"}'
```

**7. 新发现推翻旧验收时**——主动打回，不要带病前进：

```bash
python scripts/gate.py <role> reopen_node '{"project": "<项目名>", "node_id": 4, "reason": "数据探索推翻了问题定义"}'
```

**8. 方向拿不准时**——回到思维框架：

```bash
python scripts/gate.py strategy mckinsey '{"step": 1}'   # 0=总览, 1..5=各步骤
```

## 纪律

- 全程使用**同一个 project 名**；多项目并行时用不同项目名隔离状态。状态落盘在 `scripts/manual_mcp/projects/<项目>/state.json`。
- 节点顺序允许并行（如阶段二与阶段三），但**阶段门禁是硬约束**：本阶段节点未全过，不开始下一阶段的主体工作。
- 验收证据必须是真实文件（文档/代码/报告），不允许空 notes 空文件糊弄通过。
- 开工第一个动作永远是 `full_map` 或 `plan_next`，收尾最后一个动作永远是 `gate_report`。
- **每个阶段至少对 1 个关键节点执行 `review_challenge`**；评审撤销不丢人，带病通过才丢人。
- **规模匹配**：小改小修先 `set_mode track=quick`（5 个关键节点，分钟级闭环）；高风险项目用 `enterprise`（每个通过节点强制 sustained 评审）。轨道选小了会被轨外提交拦截，选大了徒增成本。
- **回退是常态不是失败**：`reopen_node` 打回后迭代轮次 +1、授权级别自动降一级，`gate_report` 会展示迭代数与评审数——迭代多说明体系在真工作。
- **复盘必须回流**：阶段七复盘后，至少把 1 条洞察通过 `feedback_loop` 创建为项目级候选
  （`update_node` 改标准或 `add_node` 补节点），`rationale` 必填；候选必须完成 Shadow、
  对抗评审和 Owner 审批后才能对**所有项目**生效。

## 🔴 人审检查点（owner 专属）

🔴 = **必须停下等 owner 明确口令才能继续，不得自查自过**；继续时在 submit/notes 里留一句「owner 口令：<原话摘要>」备查。以下既有动作均为 🔴（🔴 是 L1/L2/L3 三档授权**之上**的绝对人审点，即使 L3 全程自主也不得自过）：

- **`feedback_loop` 的全局晋升**（`promote`）：候选对所有项目生效，必须具备通过的
  Shadow、`sustained` 对抗评审和 Owner 明确批准；Agent 不得代替 Owner 审批。
- **授权级别上调**（L1→L2→L3）：`set_mode` 提权是 owner 专属；降级（含 reopen 自动降级）不需要。
- **轨道降级**（standard / enterprise → quick）：降轨等于主动减少验收节点，必须 owner 确认理由；升轨不需要。
- **enterprise 轨通过节点的 sustained 评审结论**：`review_challenge` 提交 `verdict` 前，逐条答辩内容须经 owner 过目。
- **owner 口令豁免门禁**（见「何时不用本技能」）：执行后留痕一句「owner 口令豁免门禁」。

不在清单内的动作按授权级别自主执行；拿不准某动作是否 🔴 时，按 🔴 处理（停等口令的成本远低于越权）。

## 实战证据（本文件规则的真实验证记录）

以下案例均在磁盘上可复算，每条注明它验证了本文件的哪条规则：

- `darwin-run-001-manual-gates`：quick 轨 5 节点分钟级闭环的活样本，状态见 `04_技能包/manual-gates/scripts/manual_mcp/projects/darwin-run-001-manual-gates/state.json`——验证「规模自适应」节的 quick 轨定义与「纪律」节的规模匹配规则。
- `evolution-review-v3-v7`：「Core 改动 87% 曾误走 quick」统计的数据源，复算入口 `04_技能包/manual-gates/scripts/manual_mcp/projects/evolution-review-v3-v7/state.json`——验证「改动类型 × 最低轨道」硬标准的实证依据。
- `nuwa-darwin-runbooks`：quick 轨 5/5 一次通过率 100%，独立评审 81.5/73.7、10 条缺陷全修，记录在 `06_演进记录/nuwa-darwin-runbooks/`——验证「双重验收 + 独立评审」流程可落地。

`gate_report` 正常返回长这样（nuwa-darwin-runbooks 真实输出截选）：

```json
{"总进度": "5/5", "过程质量": {"一次通过率": "100.0%", "打回次数": 0, "迭代轮次": 1}}
```

## v4 Agent升级强制规则

本节是 `02_执行手册/AI执行手册_v4_Agent升级附录.md` 的技能入口摘要，后续按手册执行时必须优先应用。

- 开工第一步必须判定 `track` 与 `autonomy`：小改用 `quick`，普通项目用 `standard`，高风险/合规/生产关键链路用 `enterprise`；未设置时按 `standard + L2`。
- 涉及新项目、技术选型、模型/框架/库选择、外部变化信息、用户明确要求搜索或 PyPI/PYP 检索时，必须先使用 `research-mcp` 或等价联网调研，形成调研范围、来源、候选方案、推荐方案、风险和下一步。
- 节点 15 开发前必须做复用检查：先查现有代码、标准库、已装依赖、PyPI/npm/GitHub/Web；确认无成熟方案后再自研。
- 涉及关键决策、工具动作、测试结果、失败/打回、评审结论、复盘教训时，必须使用 `experience-memory-mcp` 或等价结构化记录，格式为 `任务 -> 决策 -> 动作 -> 结果 -> 失败/通过 -> 教训 -> 下次检索关键词`。
- 节点 17 不只检查文档存在，必须验证实现行为符合节点 9 的接口、数据和验收契约。
- 节点 24 复盘必须引用过程质量数据：节点一次通过率、平均迭代轮数、打回次数、评审撤销率、缺陷发现阶段、经验复用次数或调研命中率至少一项。
- 任何要写回手册的新规则，必须经过
  `rule_candidate -> feedback_loop(candidate) -> shadow -> review_challenge -> owner approval -> promote -> gate_report`，
  不能由 Agent 静默改写核心标准。

## v6.1 Important Project Research Gate

For important projects, external research is not optional. Before design or
implementation, the agent must search the web and comparable public sources,
match similar solutions, and record what can be reused or borrowed.

An important project includes any new product, new system, new Agent, new MCP,
plugin, real delivery, EXE/package build, AI video/audio/content production,
PLC/industrial-control work, technical/model/framework/API selection, or any
task the user asks to complete as a closed-loop result.

Required evidence before nodes 2, 8, or 15 can pass:

- research goal and keywords;
- source URLs or local source paths;
- at least three comparable or alternative solutions, unless fewer exist;
- match score table covering functionality, stack fit, maintenance, license,
  integration cost, and risk;
- reusable/borrowable information list;
- why rejected options are not used;
- recommended route: reuse, borrow, integrate, or build from scratch;
- risks and next action.

Default artifact path:

```text
09_投研/<project>/pre_research_report.md
```

Exception is allowed only when the user explicitly says not to browse, the
project is confidential/sensitive, or the task is a tiny fix with no new
technology, dependency, architecture, or external behavior. The exception must
be recorded as `research_exception: true` with a reason.

## v6.34 ExpertDev Orchestrator P0

重要开发项目在进入主体设计或开发前，必须先产出三张卡：

- `竞品拆解卡`：凡是“类似 XX / 对标 XX / 做成 XX 那样”的需求，先拆竞品核心交互、信息架构、对象模型、可借鉴项和不采用项。
- `验收矩阵卡`：需求阶段先写验收项、验证方式、通过标准和证据路径；开发完成定义是矩阵全绿。
- `执行卡`：记录本轮目标、不做范围、工作流、当前决策和续跑提示；跨会话恢复先读执行卡。

模板正本：

```text
04_技能包/expert-dev-p0/templates/
```

打包前运行交付门禁：

```text
04_技能包/expert-dev-p0/scripts/gate_check.ps1
```

最低检查项：编译 0 warning / 0 error、smoke test 通过、发布目录存在 EXE、备份 zip 存在且非空、关键文档 UTF-8 可读且无 U+FFFD。

有 UI 的项目必须补用户视角 UI 冒烟：菜单可点击、下拉可展开、弹窗可打开/保存/取消、关键属性修改后预览和输出同步。P0 可人工记录，P2 再自动化。

P0 红线：不写新的大型 orchestrator 框架，不替换 manual-gates，不为流程本身制造新系统。
