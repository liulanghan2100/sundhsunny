---
name: math-model-selector
description: Use when selecting mathematical models for engineering, industrial software, Agent OS governance, operations research, control, queueing, ranking, optimization, simulation, or decision workflows. Produces candidate models, assumptions, failure modes, validation tests, source-backed evidence boundaries, and misuse warnings; never use it to provide live financial trading advice, direct PLC/industrial-control actions, or a single best model without validation.
---

# Math Model Selector

## Core Rule

Use this skill to produce model-selection evidence, not final production decisions.

Always output:

1. Candidate models, not a single best model.
2. Key assumptions.
3. Failure modes.
4. Minimum validation tests.
5. Data or site information still needed.
6. Risk boundaries for finance, industrial control, PLC, medical, legal, or other high-impact contexts.

Do not output:

1. Live buy/sell recommendations.
2. Direct PLC or industrial-control commands.
3. Trusted promotion based only on a source grade.
4. A unique best model without alternatives and validation.

## Workflow

1. Classify the problem type: prediction, diagnosis, ranking, optimization, control, queueing, simulation, sequential decision, or multi-agent governance.
2. Choose 2-5 candidate models from `references/model-cards-s-batch01.md` first.
3. For each candidate, report assumptions and failure modes from the model card.
4. If the user needs auditability, read `references/claim_evidence.json` and distinguish:
   - `direct`: source directly supports the claim.
   - `supported`: source supports the logic, but the wording is summarized.
   - `engineering_inference`: engineering transfer; do not treat as source-backed.
5. Give minimum validation tests before recommending implementation.
6. For high-risk contexts, state the safety boundary and require human/site validation.

## Model Hints

- Evidence update or uncertainty: Bayesian inference.
- Sensor fusion or state estimation: Kalman filter.
- Backlog, latency, worker sizing: M/M/1 queue.
- Conditional autonomy or staged decision: MDP/POMDP.
- Multi-stage planning: dynamic programming.
- Knowledge or dependency ranking: PageRank.
- Multi-agent conflict or leader/follower coordination: Nash/Stackelberg.
- Constraint tradeoffs: convex optimization/KKT.
- Exploration vs exploitation: multi-armed bandit.
- Multi-actor emergent behavior: agent-based model.

## Resources

- `references/model-cards-s-batch01.md`: 10 S-layer model cards with formulas, assumptions, failure modes, validation methods, and source locators.
- `references/claim_evidence.json`: machine-readable claim evidence map with `direct/supported/engineering_inference`.
- `scripts/validate_claim_evidence.py`: validates the claim evidence map and checks coverage against the model cards.
- `scripts/eval_misuse_cases.py`: minimal misuse regression for finance, industrial control, fake source-grade promotion, and unique-best-model requests.

## Validation

When updating the bundled model cards or claim evidence, run:

```powershell
python scripts/validate_claim_evidence.py .
python scripts/eval_misuse_cases.py
```

Keep outputs honest: if a claim is `engineering_inference`, say so directly.
