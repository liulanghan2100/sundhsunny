# 跨核集成测试（不参与 hub.py selftest）

`test_unified_entrypoint.py` 原本位于 `core/Agent_OS_Core/policy/tests/`，
但它依赖两样本包不含的东西：

1. `AutoRobot/13_mcp_bridge/agent_os_task_planner.py` —— 自治核的桥接件
2. 把 `Agent_OS_Core` 放在仓库根、`03_分工MCP` 平级的历史目录布局

它验证的是「治理核 ↔ 自治核」的跨核衔接，不是治理核自身的自包含性。
因此移到这里，并在 `hub.py selftest` 中排除。

如需运行，需要一并提供 AutoRobot 自治核。
