---
name: agent-os-decision-workbench
description: 将复杂需求转化为可验证的决策树、Agent Brief、实验卡、TDD 适配建议、架构候选和续跑检查点；按现有 Agent OS 的 L1/L2/L3 路由按需调用，不新增风险等级。触发词：决策澄清、任务分诊、Agent Brief、原型实验、TDD 适配、架构候选、handoff、续跑检查点、decision workbench。
---

# Agent OS Decision Workbench

## 定位

这是现有 Agent OS 的决策与证据辅助层，不是新的任务队列、审批系统、运行时、记忆系统或完成验证器。

## 路由

- `L1`：默认不调用；只有用户明确要求澄清、比较或交接时调用。
- `L2`：按问题类型选择性调用。
- `L3`：生成必要的决策、简报和证据输入，但仍由现有审批、queue、manual-gates 和 completion verifier 负责治理。
- 不重新定义、覆盖或推断 Agent OS 的 `L1/L2/L3`。

## 能力选择

| 任务信号 | MCP 工具 |
|---|---|
| 目标、范围或关键约束有歧义 | `create_decision_tree` |
| issue/PR 尚未验证或需要明确执行边界 | `create_agent_brief`、`verify_ready` |
| UI、交互或算法方案未决 | `create_experiment_card` |
| 有稳定行为 oracle 和公共接口 | `assess_tdd_fit` |
| 可能存在重复、浅模块或高认知负担 | `create_architecture_candidate` |
| 需要跨会话或跨 Agent 续跑 | `create_checkpoint_view` |

先调用 `recommend_capabilities`，再调用被选中的工具。简单任务不调用。

## 使用规则

1. 把可查证事实和 owner 决策分开。
2. DecisionTree 的 frontier 未清空时，不开始依赖该决策的执行。
3. Agent Brief 必须明确当前行为、目标行为、验收标准、out-of-scope 和证据。
4. `verify_ready` 通过也不等于已经进入 queue；仍需现有 Agent OS owner/queue 流程。
5. ExperimentCard 只证明一个实验问题；生产实现必须新建正式 TaskCard。
6. TDD 是适配建议，不是所有变更的强制规则。
7. ArchitectureCandidate 只读记录候选，不自动改代码。
8. CheckpointView 是 RunState/TaskCard/EvidenceRecord 的可读视图，不是正本。

## 禁止事项

- 不新增第二套 L1/L2/L3、queue、approval、memory、runtime 或 verifier。
- 不自动修改 `AGENTS.md`、`CLAUDE.md`、registry、manual-gates 或核心路由。
- 不把对象文件存在等同于事实已验证。
- 不把原型直接当生产代码。
- 不自动写外部 tracker、正式知识或长期记忆。

## 诚实边界

1. 这些工具生成结构化辅助产物，不保证决策本身正确。
2. `TddFit` 不能证明测试覆盖充分。
3. `ArchitectureCandidate` 依赖调用图、历史、运行和失败证据的质量。
4. `CheckpointView` 不能替代现有 RunState、TaskCard 或 EvidenceRecord。
5. 首版不自动读取 Codebase Memory；架构证据必须由调用方显式传入。
