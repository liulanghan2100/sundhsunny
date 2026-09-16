# Experience Memory MCP：经验样本记忆

`experience-memory-mcp` 用于把 Agent 执行经验结构化保存为外部记忆：

```text
任务 -> 决策 -> 动作 -> 结果 -> 失败/通过 -> 教训 -> 下次检索
```

它服务《个人 AI 项目执行手册》的节点 15/16/17/19/24。

## 作用

- 记录任务快照、决策理由、动作结果、失败案例、修复模式、用户偏好和教训。
- 支持按关键词、项目、记录类型检索经验。
- 支持导出 JSONL 训练/检索样本。
- 支持把高价值经验标记为 `rule_candidate`，后续再通过 `feedback_loop` 写回手册。

## 边界

- 它不是神经网络训练器。
- 它不会自动修改模型权重。
- 它不会自动修改 AI 执行手册，规则更新仍必须走 `feedback_loop` 和门禁。

## MCP 注册

```json
{
  "mcpServers": {
    "experience-memory-mcp": {
      "command": "C:\\Users\\sundh\\AppData\\Roaming\\kimi-desktop\\daimon-share\\daimon\\runtime\\python\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\sundh\\Documents\\KIMI_MODE\\createMCP\\MCPCreate20260719\\03_分工MCP\\experience_memory_mcp\\run_memory.py"
      ]
    }
  }
}
```

## 工具

- `memory_brief`
- `record_task_snapshot`
- `record_decision`
- `record_action_result`
- `record_outcome`
- `record_failure_case`
- `record_lesson`
- `record_user_preference`
- `search_memory`
- `summarize_project`
- `export_training_samples`

