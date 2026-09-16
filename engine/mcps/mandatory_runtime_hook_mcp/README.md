# mandatory_runtime_hook_mcp

v6.16 mandatory runtime hook layer for Manual Agent OS.

Default path:

```text
task -> cognitive_intake -> preflight_bundle -> mandatory_runtime_hook -> hook_runtime_policy -> control_plane -> runtime_integration
```

The route fails closed when `preflight_bundle.go` is false. Successful
compliance requires `preflight_bundle_required=true` and `preflight_go=true`
in `mandatory_state.json`.

Tools:

- `mandatory_brief`
- `plan_mandatory_route`
- `start_mandatory_task`
- `mandatory_status`
- `verify_mandatory_compliance`
