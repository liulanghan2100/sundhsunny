# offline_upgrade_mcp

User-space offline upgrade planner for the Manual Agent OS.

It does not install a system service, request administrator privileges, push to
remote Git, or run high-risk tasks automatically. It writes a local plan and
enqueues only allowlisted upgrade tasks through `task_queue_mcp`.

Tools:
- `offline_upgrade_brief`
- `write_upgrade_plan`
- `enqueue_safe_upgrade_tasks`
- `offline_upgrade_status`
- `write_approval_item`

