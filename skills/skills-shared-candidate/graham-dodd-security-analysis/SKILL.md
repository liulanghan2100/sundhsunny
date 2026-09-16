---
name: graham-dodd-security-analysis
description: Apply a Graham-Dodd style security analysis framework for conservative investment research. Use when evaluating a stock, bond, business, or investment memo through intrinsic value, margin of safety, balance sheet strength, earnings quality, and investment-versus-speculation discipline. This skill does not provide personalized financial advice or live trading instructions.
---

# Graham-Dodd Security Analysis

Use this skill to produce conservative security analysis, not trading signals.

## Scope

Analyze:

- common stocks
- bonds or credit-like securities
- business quality
- balance sheet strength
- earnings quality
- margin of safety
- investment versus speculation

Do not provide:

- personalized financial advice
- automatic buy/sell orders
- live trading instructions
- guaranteed return claims

## Core Workflow

### 1. Define the security

Capture:

- ticker or issuer
- security type
- industry
- analysis date
- data source
- user-provided financials

If current market data is required and not provided, state the data gap.

### 2. Separate investment from speculation

Ask:

- Is the analysis grounded in business economics and financial statements?
- Is the expected outcome based on value realization or price momentum?
- Is downside protection explicit?

If downside protection is absent, classify as speculation.

### 3. Understand the business

Assess:

- how the business makes money
- cyclicality
- competitive position
- capital intensity
- reinvestment needs
- management incentives

If the business cannot be explained simply, stop or mark low confidence.

### 4. Analyze financial strength

Review:

- cash and liquidity
- debt maturity and leverage
- interest coverage
- working capital
- tangible assets where relevant
- dilution or off-balance-sheet risks

Balance sheet weakness can override apparent cheapness.

### 5. Analyze earnings quality

Check:

- normalized earnings
- one-time gains/losses
- cash conversion
- margin stability
- accounting aggressiveness
- cyclic peak earnings risk

Do not value a cyclical company only on peak earnings.

### 6. Estimate intrinsic value range

Use conservative ranges rather than a single precise number.

Possible approaches:

- normalized earnings multiple
- asset value / net current asset value
- owner earnings or free cash flow range
- liquidation value where relevant
- comparable business sanity check

Record assumptions explicitly.

### 7. Test margin of safety

Ask:

- How large is the discount to conservative value?
- What must go right?
- What can go wrong?
- Is the downside tolerable?
- Is the upside dependent on speculative re-rating?

No margin of safety means no Graham-Dodd approval.

### 8. Compare opportunity cost

Compare the candidate with:

- cash
- index alternative
- stronger business at fair price
- other known opportunities

Cheap is not enough if a better risk-adjusted opportunity exists.

### 9. Write the conclusion

Use one of:

- `pass`: insufficient evidence or outside competence
- `watchlist`: interesting but no margin of safety
- `research more`: key data missing
- `candidate`: conservative value case exists
- `avoid`: downside or quality risk dominates

Avoid direct buy/sell commands.

## Output Template

```markdown
# Security Analysis Memo

## Security
## Data Used
## Investment vs Speculation
## Business Understanding
## Financial Strength
## Earnings Quality
## Intrinsic Value Range
## Margin of Safety
## Opportunity Cost
## Key Risks
## Verdict
## Missing Evidence
```

## Failure Modes

- confusing cheapness with safety
- using peak earnings as normal earnings
- ignoring leverage or refinancing risk
- relying on story instead of statements
- using precise valuation to hide weak assumptions
- treating market popularity as proof of value

## Evidence Rules

- Cite the source of financial data.
- Mark all unverified assumptions.
- Prefer ranges over false precision.
- Separate facts, assumptions, and judgments.

## Honest Boundary

This skill is an analysis framework. It is not a financial adviser, does not know the user's full financial situation, and must not place trades.
