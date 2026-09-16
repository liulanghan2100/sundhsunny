---
name: intake-control-plane
description: Unified intake control plane for external skills, repositories, and bug findings. Use when evaluating a third-party Skill or repo, generating license/source/PII/misuse inventory, planning remediation, or converting intake gaps into executable bug tickets. Combines skill-intake-scanner, repo-intake-and-plan, and bug-intake behavior in one workflow.
---

# Intake Control Plane

Use this skill when one task needs the full intake chain:

1. scan what exists
2. verify source and license
3. classify risk
4. plan remediation
5. create bug tickets

Keep the three smaller skills available for narrow tasks. Use this skill when the user wants the whole chain or does not know which intake layer is needed.

## Modes

### Mode A: Scan Only

Use when the user asks to inspect a skill pack or repo.

Output:

- inventory table
- source/license table
- PII and misuse findings
- verdict per item

Verdicts:

- `trusted`: complete source, license, and risk evidence
- `candidate`: low risk, but still needs human confirmation
- `quarantine`: incomplete evidence or mixed risk
- `reject`: unsafe, missing core files, or clearly out of policy

### Mode B: Intake and Plan

Use when the user asks what to do next after a scan.

Output:

- gap list
- recommended remediation sequence
- owner decision points
- items safe to fix automatically
- items that require source/legal/owner confirmation

### Mode C: Bug Intake

Use when findings must become executable work.

Output one ticket per real defect or evidence gap:

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

Severity:

- `S0`: security exposure, unsafe action, live money movement, destructive behavior, or data loss
- `S1`: core workflow blocked
- `S2`: important workflow degraded, workaround exists
- `S3`: minor cleanup, docs, or polish

Types:

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

## Full Workflow

### 1. Define target

Identify whether the target is:

- a Skill directory
- a repository
- a repo snapshot
- a scan report
- a review report
- a user bug report

If the target path is unclear and cannot be inferred, ask for the path.

### 2. Inventory

For every item, capture:

- name
- path
- file count
- entry files
- bundled scripts/references/assets
- existing report files

### 3. Provenance

Find:

- `source_url`
- `source_locator`
- upstream repository
- upstream file path
- evidence level

Evidence levels:

- `direct`: exact upstream source found
- `supported`: source family found but exact file not verified
- `engineering_inference`: reasoned classification, not direct proof
- `missing`: no source evidence

### 4. License

Check in this order:

1. local `LICENSE`, `LICENSE.txt`, `LICENCE`, or `COPYING`
2. `license:` field in `SKILL.md`
3. upstream repository license
4. package metadata

Never invent a license. If vendor-owned or platform-owned, mark `vendor_proprietary` unless a real open-source license is confirmed.

### 5. PII and misuse

Flag:

- email
- phone
- address
- token
- secret
- credential
- cookie
- password
- ssh key
- live trading
- auto order
- download-and-execute
- remote instruction execution

Keyword hits are not automatically failures. Mark them as `needs-review` unless they expose real credentials or unsafe actions.

### 6. Verdict

Assign one verdict per item and explain the blocking reason.

Do not upgrade to `trusted` unless source, license, PII, misuse, and verification evidence are all complete.

### 7. Remediation plan

For each non-trusted item, write:

- missing evidence
- how to obtain it
- whether the agent can fix it
- whether owner/legal confirmation is required
- estimated effort
- acceptance condition

### 8. Bug tickets

Convert actionable gaps into tickets only when:

- affected path is known
- expected outcome is clear
- acceptance and verification can be written

If not, create a sourcing task instead of a bug.

## Standard Outputs

When the task is broad, produce these files or sections:

- `inventory.tsv`
- `license_inventory.tsv`
- `source_evidence.tsv`
- `risk_review.tsv`
- `remediation_plan.md`
- `bug_tickets.md`

## Automation Hook

If a local scanner exists, prefer running it instead of manually retyping the same checks. In this workspace, the existing scanner is:

```powershell
python "09_投研\skill-intake-scanner\scan_directory.py" "<target_dir>" "09_投研\skill-intake-scanner\reports"
```

Use scanner output as evidence, not as final truth. Review false positives and missing source evidence manually.

## Hard Rules

- Do not modify runtime skill directories during intake.
- Do not install third-party skills during intake.
- Do not label unknown material as MIT or Apache.
- Do not collapse `source_gap`, `license_gap`, and `runtime_bug` into one ticket.
- Do not mark `quarantine` resolved without evidence.
- Do not hide uncertainty. Use `engineering_inference` when the conclusion is inferred.

## Relationship To Smaller Skills

- `skill-intake-scanner`: the scan engine role
- `repo-intake-and-plan`: the planning role
- `bug-intake`: the ticketing role

This skill is the orchestrator that calls all three behaviors in one controlled sequence.
