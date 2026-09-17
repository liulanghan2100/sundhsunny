# Decision Workbench MCP

把十个外部 skill 的核心方法蒸馏成 Agent OS 的辅助能力：

- `grilling` / `grill-me` / `grill-with-docs` -> DecisionTree
- `triage` -> AgentBrief 和 verify-before-ready
- `prototype` -> ExperimentCard
- `tdd` -> TddFit
- `improve-codebase-architecture` -> ArchitectureCandidate
- `handoff` / `teach` -> CheckpointView 与来源记录
- `setup-matt-pocock-skills` -> 仅借鉴 Project Profile 思路

## 边界

本 MCP 不拥有或修改：

- Agent OS 的 L1/L2/L3；
- task queue；
- approval；
- runtime；
- memory；
- completion verifier；
- manual-gates；
- 外部 tracker 正本。

产物写入：

```text
09_投研/decision_workbench/<project>/
```

首版采用显式调用，不自动接入主路由。

## 启动

```powershell
python 03_分工MCP/decision_workbench_mcp/run_decision_workbench.py
```

## 工具

- `decision_workbench_brief`
- `recommend_capabilities`
- `create_decision_tree`
- `update_decision_node`
- `create_agent_brief`
- `verify_ready`
- `create_experiment_card`
- `assess_tdd_fit`
- `create_architecture_candidate`
- `create_checkpoint_view`
- `get_artifact`
- `list_artifacts`
