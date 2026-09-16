---
name: repo-agent-workflow
description: 仓库级 agent 工作流契约——给任意代码仓库建立「SSOT 只读清单 + 实现面 truth + 安全红线 + 验证命令 + 锚点表」五件套，让 coding agent（Cursor/Claude Code/Codex）进仓库就知道改什么、不许碰什么、怎么自验。蒸馏自 QuantDinger 的 .cursor/skills/quantdinger-agent-workflow。当用户说「给这个仓库建 agent 工作流」「蒸馏仓库机制」「怎么让 AI 安全地改这个大仓库」「建立仓库契约」或开始一个会持续多轮改动的中大型项目时触发。
---

# 仓库级 agent 工作流契约（repo-agent-workflow）

蒸馏自 QuantDinger 的 `quantdinger-agent-workflow` 技能（一个 6k+ stars 的 AI 量化交易平台为编码 agent 写的工作流规范）。它的价值不在量化，而在**机制**：用一份技能文件把"agent 进仓库怎么干活"的边界钉死，防止 agent 改错层、碰红线、绕过验证。

## 触发词

「给这个仓库建立 agent 工作流」「蒸馏仓库机制」「让 AI 安全地改这个仓库」「建立仓库契约」「怎么约束 coding agent 改动范围」；或进入一个多模块、有安全边界（实盘/密钥/生产环境）的中大型仓库开始多轮改动之前。

## 何时用 / 何时不用

**用**：
- 新建中大型项目，开工前先立契约（几行代码的小项目不必，契约为零改动的边缘场景失效）
- 进入陌生大仓库（多后端、多前端、Docker、文档体系）准备做多轮改动
- 仓库含不可逆操作（实盘交易、生产部署、密钥管理、支付），必须给 agent 画红线
- 团队/自己希望不同 agent 工具（Cursor/Codex/Claude Code）对同一仓库行为一致

**不用**：
- 单文件、一次性小改动（契约成本 > 收益）
- 纯阅读/查询仓库（只读不改，无边界风险）
- 已有成熟契约的仓库（读它的契约，别另立）

## 核心机制（八件套）

### ① 触发边界（When this applies）
写清楚**动哪些目录/文件才算触发本契约**。QuantDinger 原版写法是列出 `backend_api_python/`、策略/回测逻辑、`docker-compose.yml`、`scripts/`、`env.example`、`docs/agent/`。要点：边界要指到具体路径，不是"改代码时"这种废话。

### ② SSOT 只读清单（Read first）
按**阅读优先级**排好源文件，作为 agent 动工前的强制前置。QuantDinger 原版顺序：环境设计 → AI 集成设计 → 快速上手 → 机器可读契约（OpenAPI）→ 索引。要点：
- 每份标注"为什么先读它"（SSOT 的定位）
- 带 `docs/agent/agent-openapi.json` 这类机器可读契约，并注明"改了 `/api/...` 就必须同步它"
- 明确**哪份文档才是 truth**（原版特意警告：营销味的根 README 不是 onboarding 主文档）

### ③ 实现面 truth（Implemented surface）
用"已经实现的事实"而不是"设计意图"来写：网关挂在哪、鉴权在哪、密钥如何存、哪些是默认安全的。QuantDinger 原版五个硬事实：
- 网关路径 `/api/agent/v1` + 鉴权装饰器位置
- token 哈希落盘，**禁止记日志/持久化明文 token**
- 异步任务走 job 表 + SSE 推送
- **paper-only 默认**：实盘要 token 参数 + 环境变量**双开关**才放开
- MCP 层是 REST 的薄包装，加工具必须先有 REST 能力

> 机制提炼：每个安全不变量都写"默认值是什么 + 放开它的条件是什么"。

### ④ 红线（Red Lines）
只写"绝不"级规则，QuantDinger 原版三条：不提交真密钥/生产 `.env`；不添加绕过人工审查的实盘自动化；不在 agent 文档里复制长策略文档（链接代替复制）。要点：红线要**具体到可被审查**（"不提交 secrets"要写成"用 env.example + 占位符"）。

### ⑤ 仓库锚点表（Repository Anchors）
一张"区域 → 路径"表，让 agent 秒定位：后端、前端、Compose 栈、策略文档。原版还加了一行"文档链接放哪"。

### ⑥ 验证命令（Verification）
给 agent 可自验的命令：`pytest tests/ -q`、专门的网关测试文件等。**没有验证命令的契约是空文**。

### ⑦ 语言策略（Language）
多 locale 团队/工具下，agent 面向文档强制单一语言（QuantDinger 用英文），避免术语漂移。

### ⑧ 实例化清单（Instantiation，蒸馏新增）
新项目套用时逐项填空（见下）。

## 新项目实例化清单（填空模板）

```text
## ① 触发边界
动这些路径才算触发：____（列出目录/文件）
## ② SSOT 只读清单（按优先级）
1. ____（SSOT：为什么先读）
2. ____
3. ____（机器可读契约：改了 X 就同步它）
## ③ 实现面 truth
- 入口/网关：____
- 鉴权：____（默认值：____；放开条件：____）
- 密钥存储：____（明文禁令：____）
- 异步机制：____
- 安全默认：____（双开关：____）
## ④ 红线
- 绝不：____
- 绝不：____
## ⑤ 锚点表
| 区域 | 路径 |
| 后端 | ____ |
| 前端 | ____ |
| 部署 | ____ |
## ⑥ 验证命令
- 单测：____
- 接口测试：____
## ⑦ 语言
- agent 文档语言：____
```

## 检查清单

- [ ] 触发边界写到具体路径，不是"改代码时"
- [ ] SSOT 清单有阅读优先级，且标注了"哪份是 truth"
- [ ] 机器可读契约（OpenAPI/JSON Schema）已纳入同步义务
- [ ] 每个安全不变量写了"默认值 + 放开条件"
- [ ] 红线可被审查（具体到模式，不是口号）
- [ ] 锚点表覆盖后端/前端/部署/文档
- [ ] 至少一条可执行的验证命令
- [ ] 已声明文档语言策略
- [ ] 新建仓库时完成了实例化填空，并把结果落进仓库自己的文档

## 反模式黑名单

- ❌ 契约只写"要遵守规范"不写具体路径/命令（无法执行）
- ❌ 把营销 README 当 SSOT（它讲怎么用，不讲边界）
- ❌ 安全不变量只写"默认 paper-only"不写放开条件（agent 不知道能不能动）
- ❌ 红线写"注意安全"这种不可审查的废话
- ❌ 加新接口不同步机器可读契约（契约失血）
- ❌ 文档语言混用（术语漂移，agent 行为不一致）
- ❌ 给一次性小改动上全套契约（过拟合，agent 会无视它）

## 诚实边界

1. **契约约束的是流程，不是能力**：红线能挡住越权，挡不住 agent 在授权范围内做错设计；验证命令只保证"没改坏"，不保证"改对了"。
2. **契约有维护成本**：仓库演进后 SSOT 和实现面 truth 会过期，需要人工同步；过期契约比没有更危险（agent 会信任错误信息）。
3. **跨工具一致性有限**：不同 agent 工具对技能/契约的加载机制不同（Cursor 的 .cursor/skills、Claude Code 的 .claude/skills、本仓库的 04_技能包），同一份内容在不同宿主下触发时机可能不一致。
4. **安全不变量依赖文档纪律**：双开关、密钥哈希这类约束，最终靠人写进代码并审查，契约只是前置提醒，不替代代码层的强制。

## 参考来源

- QuantDinger `quantdinger-agent-workflow`（一手）：github.com/brokermr810/QuantDinger 仓库 `.cursor/skills/quantdinger-agent-workflow/SKILL.md`（v3.0.3，2026-05）
- QuantDinger 平台（语境）：AI 量化交易平台，Docker 自托管，MCP server `@quantdinger/mcp-server`；官方站 www.quantdinger.com
- 本仓库同类技能参考：`trading-decision-workflow`、`decision-review-loop`（同一蒸馏-适配-注册体系）
