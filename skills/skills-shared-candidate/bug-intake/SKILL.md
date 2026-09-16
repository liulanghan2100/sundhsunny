---
name: bug-intake
description: Convert scan findings, review failures, intake gaps, user bug reports, or failed acceptance checks into structured bug tickets with severity, reproduction evidence, owner path, acceptance criteria, and verification steps. Use after repo-intake-and-plan, skill-intake-scanner, code review, gate failures, or when the user asks to turn problems into actionable bug work.
---

# Bug Intake

Use this skill to convert a loose problem report into bug work that another agent can execute without re-interviewing the user.

## Input

Accept any of these:

- `repo-intake-and-plan` gap list
- `skill-intake-scanner` report
- code review findings
- failed gate or test output
- user-described bug
- screenshots or logs

## Workflow

### 1. Normalize the finding

For each issue, capture:

- title
- source artifact
- exact file or path
- observed behavior
- expected behavior
- evidence

If evidence is missing, mark `evidence_gap` instead of guessing.

### 2. Classify severity

Use this ladder:

- `S0`: data loss, security exposure, unsafe action, live money movement, or destructive behavior
- `S1`: core workflow blocked
- `S2`: important workflow degraded, workaround exists
- `S3`: polish, docs, minor cleanup

### 3. Classify type

Use one primary type:

- `source_gap`
- `license_gap`
- `pii_risk`
- `misuse_risk`
- `security_risk`
- `test_gap`
- `runtime_bug`
- `docs_gap`
- `ux_bug`
- `build_packaging_bug`

### 4. Write the ticket

Each bug must include:

```markdown
## Bug: <short title>

- severity:
- type:
- source:
- affected_path:
- evidence:
- observed:
- expected:
- likely_cause:
- fix_plan:
- acceptance:
- verification:
- out_of_scope:
```

### 5. Batch output

When multiple issues are present:

- group by severity first
- then by affected component
- deduplicate identical root causes
- keep separate tickets when acceptance criteria differ

## Intake Rules

- Do not hide evidence gaps.
- Do not merge legal/license gaps with runtime bugs.
- Do not mark a bug fixed until verification steps are defined.
- Do not create a ticket that has no acceptance condition.

## Handoff Contract

For `repo-intake-and-plan`, map findings like this:

- missing `source_url` or `source_locator` -> `source_gap`
- missing or unverified `LICENSE` -> `license_gap`
- PII keyword hit -> `pii_risk`
- live-action or credential pattern -> `misuse_risk` or `security_risk`
- scanner false positive -> `test_gap`

## Good Output Shape

Finish with:

- total bugs
- S0/S1/S2/S3 counts
- blockers
- first three recommended fixes
