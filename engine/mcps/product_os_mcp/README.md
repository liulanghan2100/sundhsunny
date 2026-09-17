# product-os-mcp

`product-os-mcp` is the v5.19 product autonomy layer for the local Manual Agent OS.

It does not replace existing MCP modules. It orchestrates product work above them:

```text
product idea -> intent -> PRD -> design -> architecture -> plan -> local cycle
-> acceptance -> feedback backlog -> report
```

Safety boundary:

- local user-space only
- no administrator privileges
- no system service registration
- no secret use
- no public deployment or real GitHub PR/CI writes

Main tools:

- `product_os_brief`
- `parse_product_idea`
- `create_prd`
- `generate_product_design`
- `propose_architecture`
- `create_product_plan`
- `run_product_cycle`
- `product_acceptance`
- `record_product_feedback`
- `product_status`
- `export_product_report`

