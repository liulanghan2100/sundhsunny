# cognitive_intake_mcp

v6.2 的“认知入口内核”，作为 AI 执行手册的节点 0。

## 作用

- 在执行前把任务分为 A/B/C/D：
  - A：普通问答，直接回答。
  - B：小任务，Quick 路径。
  - C：重要项目，必须调研、工作流、验证、门禁、备份。
  - D：高风险或硬阻塞，停止并说明恢复路径。
- 输出意图、交付物、完成标准、最小验证、风险、算力预算、禁止伪闭环声明。
- 为后续 control-plane、auto-trigger、manual-gates 提供统一前置判断。

## 工具

- `cognitive_intake_brief`
- `classify_task`
- `build_execution_card`
- `assess_response_consequence`
- `intake_decision`
- `intake_report`
