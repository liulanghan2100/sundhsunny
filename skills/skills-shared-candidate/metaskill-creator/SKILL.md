---
name: metaskill-creator
description: Distill execution traces, replay logs, gate reports, and repeated task protocols into reusable workflow skills or MetaSkill candidates. Use when a task is best learned from how it was executed rather than from static domain knowledge, or when the user wants skill composition, trace-to-skill extraction, or workflow protocol reuse.
---

# MetaSkill Creator

Turn a repeated execution pattern into a reusable workflow skill.

## Use when

- a task has stable steps but is still being executed manually
- you have `state.json`, `execution.json`, replay logs, or gate records
- multiple smaller skills need to be composed into one workflow
- you want to extract a task protocol from successful runs and failures

## Do not use when

- the task is mainly domain knowledge to be written into a single skill
- the task is only about editing an existing skill
- the task is only about intake, licensing, or bug triage

## Core job

Convert execution history into a candidate workflow skill with:

- trigger conditions
- input contract
- step sequence
- decision points
- failure branches
- acceptance checks
- evidence requirements

## Workflow

### 1. Collect traces

Gather:

- successful runs
- failed runs
- replay logs
- gate reports
- manual notes
- stable task outputs

Prefer real execution records over recollection.

### 2. Identify repetition

Extract:

- repeated steps
- stable branching points
- common inputs
- common outputs
- common failure modes
- common recovery paths

If the pattern only happened once, do not promote it to a MetaSkill.

### 3. Separate layers

Classify each piece as one of:

- orchestration
- tool choice
- domain knowledge
- policy / gate logic
- error recovery
- verification

Only orchestration, gate logic, and reusable recovery belong in the MetaSkill layer.

### 4. Compose from existing skills

If the workflow already uses smaller skills, record:

- which skills are called
- in what order
- with what handoff conditions
- with what failure fallback

Prefer composition over rewriting.

### 5. Draft the candidate

Write the candidate with these sections:

```markdown
---
name: <meta-skill-name>
description: <what repeated workflow it executes and when to use it>
---

# <name>

## Trigger
## Input contract
## Core workflow
## Decision points
## Failure modes
## Acceptance checks
## Evidence to record
## Related skills
```

### 6. Validate

Check:

- is the workflow stable enough to reuse?
- is the trigger clear?
- are failure branches explicit?
- are acceptance checks measurable?
- does it overlap too much with an existing skill?

If the answer is unclear, keep it as a workflow note instead of a new skill.

## Output

Produce one of:

- `MetaSkill candidate`
- `workflow protocol`
- `composition map`
- `replay-derived template`

## Hard rules

- Do not turn one-off behavior into a skill.
- Do not hide uncertainty about unstable steps.
- Do not merge domain knowledge with orchestration logic.
- Do not replace `nuwa-runbook`; this skill sits beside it.
- Do not invent execution evidence.

## Relationship to other skills

- `nuwa-runbook`: knowledge or method distillation
- `skill-creator`: general skill authoring
- `darwin-runbook`: improve an existing skill
- `manual-gates`: enforce stepwise execution
- `intake-control-plane`: external intake and risk gating

This skill is for trace-to-skill transformation, not for source intake or generic skill editing.
