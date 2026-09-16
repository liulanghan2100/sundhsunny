# Agent OS Core

This directory is the slim control-plane index for the local Agent OS.

It does not replace existing runtime directories. It points to the current
working assets and classifies them under the agreed 0-10 structure:

0. Governance Constitution
1. 7 Agent Facade Layer
2. Capability Control Plane
3. Research Intake Gate
4. Runtime Services
5. Failure Recovery
6. Capability Lifecycle Layer
7. Domain Runtime Layer
8. Memory Layer
9. Knowledge Base Layer
10. Lab Archive

## Rule

Keep capabilities centralized. Use labels, inventory, and routing to organize
them. Do not scatter Skill files by business area.

## Current Mode

- Safe closed-loop slimming
- No destructive filesystem action
- No real provider activation
- No paid API call
- No automatic registry writeback
- No automatic Skill/runtime standard writeback

## Files

- `agent_os.py`: top-level daily Agent OS control entry.
- `scripts/build_inventory.py`: read-only workspace inventory builder.
- `scripts/agent_os_control.py`: internal control dispatcher used by `agent_os.py`.

## Commands

Use the top-level entry for daily operations:

```bash
python Agent_OS_Core/agent_os.py status
python Agent_OS_Core/agent_os.py workflow
python Agent_OS_Core/agent_os.py dashboard
python Agent_OS_Core/agent_os.py legacy-usage
python Agent_OS_Core/agent_os.py archive plan
python Agent_OS_Core/agent_os.py archive copy-status
python Agent_OS_Core/agent_os.py reference scan
python Agent_OS_Core/agent_os.py reference candidates
python Agent_OS_Core/agent_os.py reference approval-packet
python Agent_OS_Core/agent_os.py reference rewrite-plan
python Agent_OS_Core/agent_os.py reference post-rescan
python Agent_OS_Core/agent_os.py delegate owner-review list
python Agent_OS_Core/agent_os.py delegate model-adapter plan
python Agent_OS_Core/agent_os.py delegate smoke list --filter task
```

Rebuild inventory:

```bash
python Agent_OS_Core/scripts/agent_os_control.py inventory
```

Show summary:

```bash
python Agent_OS_Core/scripts/agent_os_control.py summary
```

Show duplicate-entry groups:

```bash
python Agent_OS_Core/scripts/agent_os_control.py group owner-review
python Agent_OS_Core/scripts/agent_os_control.py group model-adapter
python Agent_OS_Core/scripts/agent_os_control.py group smoke
python Agent_OS_Core/scripts/agent_os_control.py group gaia
python Agent_OS_Core/scripts/agent_os_control.py group langgraph
```

Show safe consolidation plan:

```bash
python Agent_OS_Core/scripts/agent_os_control.py merge-plan
```

Show unified entrypoints:

```bash
python Agent_OS_Core/scripts/agent_os_control.py entrypoints
```

Delegate through the control-plane entry:

```bash
python Agent_OS_Core/scripts/agent_os_control.py delegate owner-review list
python Agent_OS_Core/scripts/agent_os_control.py delegate model-adapter plan
python Agent_OS_Core/scripts/agent_os_control.py delegate smoke list --filter task
```

## Evidence Outputs

- `09_research/agent-os-structure-slimming-v1/inventory.csv`
- `09_research/agent-os-structure-slimming-v1/inventory_summary.md`
- `09_research/agent-os-structure-slimming-v1/legacy_entrypoint_migration.csv`
- `09_research/agent-os-structure-slimming-v1/legacy_entrypoint_migration.md`

## Compatibility Migration

The first slimming pass converted duplicate old entry scripts into shims:

- owner review: 59 old scripts -> `03_分工MCP/agent_os_owner_review.py`
- model adapter: 13 old scripts -> `03_分工MCP/agent_os_model_adapter_governance.py`
- smoke/test: 54 old scripts -> `03_分工MCP/smoke_suite.py`

Original implementations are preserved under:

```text
03_分工MCP/_legacy_entrypoints/
```

Legacy entrypoints are locked by default. Calling an old path prints the unified
entrypoint to use and exits without running the preserved legacy implementation.
To execute a preserved legacy implementation, the caller must explicitly set:

```bash
AGENT_OS_ALLOW_LEGACY_ENTRYPOINT=1
```

This prevents accidental fallback to old entrypoints while keeping recovery
access available.

Regenerate the migration map:

```bash
python Agent_OS_Core/scripts/migrate_legacy_entrypoints.py
```

## Slimming Workflow

Current workflow status:

1. Entrypoint Consolidation: completed
2. Lab Archive Isolation: completed
3. Skill Registry Tagging: completed
4. Runtime Dashboard View: completed
5. Memory Knowledge Boundary: completed
6. Final Archive Retirement: completed
7. Owner Approval Packet: completed

Show workflow status:

```bash
python Agent_OS_Core/scripts/agent_os_control.py workflow
```

Rebuild Lab Archive mapping:

```bash
python Agent_OS_Core/scripts/build_lab_archive_mapping.py
```

Rebuild sidecar Skill registry tags:

```bash
python Agent_OS_Core/scripts/build_skill_registry_tags.py
```

Rebuild runtime dashboard:

```bash
python Agent_OS_Core/scripts/agent_os_control.py dashboard
```

Rebuild memory / knowledge boundary:

```bash
python Agent_OS_Core/scripts/build_memory_knowledge_boundary.py
```

Rebuild archive / retirement candidates:

```bash
python Agent_OS_Core/scripts/agent_os_control.py retirement
```

Rebuild owner approval packet:

```bash
python Agent_OS_Core/scripts/agent_os_control.py approval-packet
```

Owner decision record:

```text
09_research/agent-os-structure-slimming-v1/owner_decision_record.md
```
