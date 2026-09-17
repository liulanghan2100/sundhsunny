# Research MCP：开工前外部调研工具

Research MCP 是《个人 AI 项目执行手册》的外部情报扫描器，服务节点 2、8、11、15。

它负责：

- 生成调研范围和固定输出契约。
- 给出 PyPI / npm / GitHub / Pi / Web 的检索入口和人工复核清单。
- 对候选方案做 reuse / build / hybrid / defer 对比。
- 检查许可证、维护、安全、锁定、范围匹配风险。
- 写出可被 manual-gates 验收的调研报告。

它不负责：

- 不替代浏览器和官方文档阅读。
- 不替代 AI 执行手册门禁。
- 不在网络不可用时伪造包元数据。

## MCP 注册

```json
{
  "mcpServers": {
    "research-mcp": {
      "command": "C:\\Users\\sundh\\AppData\\Roaming\\kimi-desktop\\daimon-share\\daimon\\runtime\\python\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\sundh\\Documents\\KIMI_MODE\\createMCP\\MCPCreate20260719\\03_分工MCP\\research_mcp\\run_research.py"
      ]
    }
  }
}
```

## 工具

- `research_brief`
- `pyp_search`
- `npm_search`
- `github_search`
- `pi_search`
- `web_scan`
- `compare_options`
- `risk_check`
- `write_research_report`

