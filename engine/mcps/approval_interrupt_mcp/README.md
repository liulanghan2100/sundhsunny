# approval-interrupt-mcp

v6.29 provides a local approval interrupt queue for actions that cannot proceed
under autonomous execution. It does not request administrator privileges,
perform remote approvals, or store secrets.

Tools:

- `approval_interrupt_brief`
- `request_or_interrupt`
- `approve_interrupt`
- `reject_interrupt`
- `resume_with_approval`
- `interrupt_report`
