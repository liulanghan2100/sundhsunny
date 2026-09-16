---
name: cangjie-thinking-distiller
description: Distill a person's real decision samples into a reusable, testable, and feedback-driven thinking protocol. Use when the user wants to capture how someone thinks, judges, prioritizes, rejects, escalates, or makes decisions, and turn that reasoning style into an Agent OS skill or decision playbook.
---

# Cangjie Thinking Distiller

Use this skill to distill a thinking style, not a writing style.

Nuwa distills how someone expresses. Cangjie distills how someone decides.

## Goal

Turn real decision samples into:

- judgment order
- evidence standard
- tradeoff rules
- rejection rules
- escalation rules
- feedback loop

## Input

Use real samples whenever possible:

- decisions
- rejected options
- review comments
- planning notes
- postmortems
- chat excerpts
- acceptance decisions
- examples of “do this” and “do not do this”

Do not rely only on personality descriptions or slogans.

## Workflow

### 1. Define the person and domain

Specify:

- whose thinking is being distilled
- what domain this thinking applies to
- what problem types are in scope
- what problem types are out of scope

Do not create a universal thinking clone.

### 2. Collect decision samples

For each sample, capture:

- context
- options considered
- final decision
- rejected alternatives
- evidence used
- risk tolerance
- tradeoff made
- result if known

Mark weak samples as `low_confidence`.

### 3. Break down the decision chain

Extract:

- what was checked first
- what was ignored
- what was treated as blocking
- what was treated as optional
- what caused escalation
- what caused rejection
- what caused approval

### 4. Distill the thinking protocol

Write the protocol as executable rules:

```markdown
## Input contract
## First questions
## Evidence standard
## Priority order
## Tradeoff rules
## Rejection rules
## Escalation rules
## Output format
```

Rules should be specific enough to test.

### 5. Build contrast tests

Create test cases:

- same-domain easy case
- same-domain hard case
- ambiguous case
- risk case
- out-of-scope case
- adversarial case

For each test, compare:

- expected human-like judgment
- protocol judgment
- difference
- required correction

### 6. Fix drift

Classify mismatches:

- missing knowledge
- wrong priority
- wrong risk tolerance
- weak evidence standard
- unclear rejection rule
- bad output structure

Update only the smallest rule needed.

### 7. Freeze the artifact

Produce one of:

- decision protocol
- thinking playbook
- Cangjie-style Skill
- review rubric
- routing policy

Include:

- version
- source sample list
- confidence level
- known blind spots
- feedback path

### 8. Feed back new cases

After use, record:

- success case
- failure case
- surprising decision
- user correction
- revised rule

No feedback loop means the thinking protocol will drift or freeze too early.

## Output Template

```markdown
# <Name> Thinking Protocol

## Scope
## Sample Evidence
## Judgment Order
## Evidence Standard
## Tradeoff Rules
## Rejection Rules
## Escalation Rules
## Output Format
## Contrast Tests
## Failure Modes
## Feedback Loop
```

## Hard Rules

- Do not imitate private identity or claim to be the person.
- Do not infer thinking style from one sample.
- Do not confuse tone with judgment.
- Do not hide low-confidence rules.
- Do not apply the protocol outside its declared domain.
- Do not skip contrast tests.

## Relationship to other skills

- `nuwa-runbook`: distills knowledge or expression into a skill.
- `metaskill-creator`: distills task execution traces into workflow skills.
- `darwin-runbook`: improves an existing skill.
- `cangjie-thinking-distiller`: distills decision style into a thinking protocol.
