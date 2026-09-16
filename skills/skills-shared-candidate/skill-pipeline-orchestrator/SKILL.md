---
name: skill-pipeline-orchestrator
description: Orchestrate multiple skills into an execution pipeline. Use when a user problem needs skill selection, ordered execution, gating, retry, feedback, or handoff across intake, routing, distillation, creation, evolution, publishing, and recovery.
---

# Skill Pipeline Orchestrator

Use this skill when one request needs more than one skill.

## Job

Turn a user problem into:

- the right skill set
- the right execution order
- the right gates
- the right fallback path
- the right feedback loop

## Core responsibilities

### 1. Classify the problem

Decide whether the input is mainly:

- intake / risk / source checking
- knowledge distillation
- workflow distillation
- thinking distillation
- skill authoring
- skill evolution
- skill publishing
- skill routing
- registry / registration

### 2. Select the pipeline

Choose the smallest set of skills that can finish the job.

Preferred order:

1. `intake-control-plane`
2. `skill-register`
3. `skill-router`
4. one of `nuwa-runbook` / `metaskill-creator` / `cangjie-thinking-distiller`
5. `skill-creator`
6. `darwin-runbook`
7. `skill-publisher`
8. feedback capture

Do not use every skill by default.

### 3. Enforce sequencing

Use this rule:

- first solve evidence and risk
- then solve routing
- then solve distillation
- then solve authoring
- then solve evolution
- then solve publishing
- then capture feedback

If any earlier gate fails, do not continue downstream.

### 4. Manage state

Track each item through states like:

- `new`
- `quarantined`
- `registered`
- `routed`
- `distilled`
- `drafted`
- `evolved`
- `published`
- `feedbacked`

If a state is missing, infer the safest next state and say why.

### 5. Retry or stop

Retry only when the failure is:

- missing data
- transient tool error
- incomplete evidence

Stop and escalate when the failure is:

- license uncertainty
- source uncertainty
- PII or misuse risk
- wrong domain
- irreversible side effect

### 6. Capture feedback

After execution, record:

- what worked
- what failed
- which skill was unnecessary
- which step should be skipped next time
- what should become a new skill

## Output format

```markdown
## Problem Class
## Selected Skills
## Execution Order
## Gates
## State
## Risks
## Fallbacks
## Feedback
```

## Hard rules

- Do not route to `reject`.
- Do not skip intake on third-party material.
- Do not publish before registry approval.
- Do not distill before problem class is clear.
- Do not call all skills just because they exist.
- Do not hide uncertainty in the pipeline choice.

## Relationship to other skills

- `skill-router`: picks candidate skills
- `skill-register`: records skill facts
- `intake-control-plane`: checks source, license, and risk
- `nuwa-runbook`: distills knowledge
- `metaskill-creator`: distills workflows
- `cangjie-thinking-distiller`: distills judgment
- `skill-creator`: writes the skill artifact
- `darwin-runbook`: improves the skill
- `skill-publisher`: packages and prepares release
