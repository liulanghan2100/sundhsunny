# Auto Trigger MCP

`auto-trigger-mcp` turns AI执行手册 v4 rules into explicit trigger decisions.

It recommends, but does not directly execute, these actions:

- `research_required`
- `memory_search_required`
- `memory_record_required`
- `gate_check_required`
- `human_approval_required`

Tools:

- `trigger_brief`
- `evaluate_triggers`
- `record_trigger_event`
- `startup_checklist`

Manual mapping:

- Before implementation: evaluate research and memory triggers.
- After decision/tool/test/review/retro events: record memory triggers.
- Before stage close: gate triggers.
- Before risky filesystem/global config/deploy actions: human approval triggers.
