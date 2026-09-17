# Workflow Runtime MCP

`workflow-runtime-mcp` adds checkpointed execution state to the AI执行手册.

It stores workflow files under:

`09_投研/workflow_runtime/<project>/workflow.json`

Tools:

- `runtime_brief`
- `create_workflow`
- `workflow_next`
- `checkpoint_step`
- `complete_step`
- `reopen_step`
- `workflow_report`
- `export_workflow`

It complements manual-gates. It does not replace `submit_check`,
`review_challenge`, or `gate_report`.
