# policy_consistency_auditor_mcp

v6.19 policy consistency auditor for Manual Agent OS.

It checks local policy drift between:

- `policy.json`
- mandatory runtime route
- runtime middleware stack
- completion certificate evidence
- local regression gate policy

It is read-only except for writing audit reports under
`09_投研/policy_consistency_auditor/`.
