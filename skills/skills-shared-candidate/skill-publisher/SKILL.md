---
name: skill-publisher
description: Package and prepare skills for release to local or external destinations. Use when a skill needs packaging, release notes, README/license checks, or a publication checklist for GitHub or a marketplace.
---

# Skill Publisher

Package only after the registry says the skill is allowed to leave the local workspace.

## Input

- skill directory
- registry status
- README
- LICENSE
- changelog or release notes
- destination target

## Output

- publish package
- release checklist
- destination-specific submission notes

## Rules

- Default to packaging, not auto-publishing
- Do not publish unvetted or rejected skills
- Do not publish proprietary content without permission
- Do not auto-use credentials or login sessions
- Do not cross red-line destinations without approval

## Checks

- frontmatter present
- license present
- source evidence recorded
- risk state acceptable
- packaging shape valid

## Relationship

- Reads `skill-register`
- Uses `intake-control-plane` gates
- Emits artifacts for GitHub, marketplace, or local distribution
