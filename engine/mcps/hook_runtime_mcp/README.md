# Hook Runtime MCP

`hook-runtime-mcp` is the lifecycle policy layer for `manual-agent-os-v5.1`.

It decides what should happen before/after tool calls and on stop:

- call research
- search memory
- record memory
- request human approval
- finalize gate and backup

Tools:

- `hook_brief`
- `pre_tool_use`
- `post_tool_use`
- `stop_hook`
- `evaluate_chain`
- `record_hook_event`
