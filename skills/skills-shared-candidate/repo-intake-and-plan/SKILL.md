---
name: repo-intake-and-plan
description: Ingest a repository, skill pack, or codebase snapshot; extract provenance, license, PII, and misuse risk; classify the intake verdict; and turn the findings into a concrete remediation plan or bug tickets. Use when evaluating new repos/skills, checking source evidence, licenses, or safety risk, or when converting scan results into an actionable repair plan.
---

# Repo Intake and Plan

Use this skill to turn a raw repo or skill package into a controlled intake decision.

## Goal

Separate four jobs that must not blur together:

1. Inventory what exists
2. Verify where it came from
3. Classify the legal/safety risk
4. Turn gaps into an execution plan or bug work items

## Workflow

### 1. Inventory

- List every target directory or package.
- Capture file counts, key entry files, and any bundled resources.
- Record the scan output in a machine-readable table.

### 2. Provenance

- Find `source_url` and `source_locator` from the skill header, repo metadata, or source docs.
- Prefer primary sources over summaries.
- If provenance cannot be traced back to an original source, mark the item `quarantine`.

### 3. License

- Detect local `LICENSE*` files first.
- Read the license text and record the exact family, not a guess.
- If the item is vendor-owned or platform-owned, mark it `proprietary` unless a real upstream open-source license is confirmed.

### 4. PII and misuse

- Flag emails, phone numbers, addresses, tokens, credentials, cookies, keys, or secrets.
- Flag live-action patterns such as download-and-execute, auto-order, live trading, or remote instruction execution.
- If the item can cause harm without a guardrail, keep it out of `trusted`.

### 5. Verdict

Use this ladder:

- `trusted`: source, license, and risk evidence are complete
- `candidate`: low risk, but still needs human confirmation
- `quarantine`: evidence is incomplete or mixed
- `reject`: unsafe, missing core files, or clearly out of policy

### 6. Plan or bug intake

If the item is not `trusted`:

- Write the missing evidence as explicit checklist items
- Convert each gap into a repair task
- If the gap is technical, write a bug-style work item
- If the gap is source or legal, write a sourcing task

## Required output

Produce, at minimum:

- inventory table
- provenance table
- license table
- PII / misuse table
- verdict summary
- next-step plan or bug list

## Output rules

- Do not invent source URLs.
- Do not infer a license from a vague project description.
- Do not upgrade a verdict without evidence.
- Do not convert quarantine to trusted just because the repo looks clean.

## Good next actions

- `repo-intake` when you only need inventory and evidence capture
- `repo-intake-and-plan` when you also need the repair sequence
- `bug-intake` when the next step is a concrete defect backlog
