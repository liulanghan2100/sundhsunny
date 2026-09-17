# agent_runtime_kernel_mcp

Coordinates the AI manual system across MCPs.

Default storage:

```text
09_投研/agent_runtime_kernel/<project>/runtime.json
```

The kernel returns executable plans. It does not bypass manual-gates and does
not call remote GitHub APIs in v5.3.

Primary tools:

- `start_task`
- `resume_task`
- `runtime_next_action`
- `execute_checkpoint`
- `runtime_status`
- `runtime_stop`
- `runtime_report`
- `runtime_export`

