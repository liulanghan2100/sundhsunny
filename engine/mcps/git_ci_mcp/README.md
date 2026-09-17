# Git / PR / CI MCP

`git-ci-mcp` adds local branch, PR, CI, and release evidence planning.

It does not push code or create a remote PR. In a non-git directory it uses this
fallback:

`zip backup + manual-gates state.json + validation report`

Tools:

- `git_ci_brief`
- `repo_status`
- `branch_plan`
- `ci_plan`
- `pr_checklist`
- `release_evidence`
