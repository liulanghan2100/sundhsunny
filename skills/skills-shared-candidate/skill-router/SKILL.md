---
name: skill-router
description: Route user tasks to the best local skills using registry metadata, skill descriptions, risk state, and simple scoring. Use when the system needs to choose which skill should handle a task, or when multiple skills are candidates.
---

# Skill Router

Route first from metadata, not from full content.

## Input

- user task
- skill registry
- skill names
- skill descriptions
- risk status
- usage history

## Output

- top-k candidate skills
- routing score
- explanation for selection
- blocked skills and why

## Rules

- Prefer trusted skills
- Downgrade quarantine skills
- Never route to reject
- Do not require full skill content unless metadata is insufficient
- Explain why a skill won and why others lost

## Scoring hints

- lexical match
- domain match
- historical success
- low-risk preference
- freshness / recency

## Relationship

- Reads `skill-register`
- Uses `intake-control-plane` status
- Provides candidates to execution or human review
