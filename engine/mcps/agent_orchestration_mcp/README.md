# Agent Orchestration MCP

`agent-orchestration-mcp` defines multi-agent roles and handoff contracts for
AI执行手册 projects.

Agents:

- `research-agent`
- `planning-agent`
- `dev-agent`
- `qa-agent`
- `security-agent`
- `review-agent`
- `memory-agent`

Tools:

- `orchestration_brief`
- `agent_roster`
- `assign_task`
- `handoff_contract`
- `review_matrix`
- `export_agent_config`

All agents remain under manual-gates. They cannot bypass `submit_check`,
`review_challenge`, or `gate_report`.
