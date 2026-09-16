---
name: skill-register
description: Register and maintain skill metadata for the local Skill Platform. Use when a new skill, repo, or distilled capability needs registry status, source/license evidence, risk state, or version tracking.
---

# Skill Register

Register skills as facts, not promotions.

## Input

- skill directory
- intake report
- source evidence
- license inventory
- risk review

## Output

- `skill_registry.tsv`
- `skill_status.json`
- registry entry with source, license, risk, and version

## Rules

- Do not register unvetted skills as `trusted`
- Do not mark proprietary material as MIT or Apache without evidence
- Do not merge source, license, and risk into one field
- Do not publish from the registry layer

## Fields

- name
- path
- source_url
- source_locator
- license
- status
- version
- risk
- notes

## Status values

- `trusted`
- `candidate`
- `quarantine`
- `reject`

## Relationship

- Feeds `skill-router`
- Receives evidence from `intake-control-plane`
- Can be used by `skill-publisher` for release gating
