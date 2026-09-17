# audit_hash_chain_mcp

v6.27 tamper-evident local audit hash chain for Manual Agent OS.

It records append-only JSONL audit events where each event includes:

- previous hash
- canonical event payload
- current SHA-256 hash

This is tamper-evident, not a third-party digital signature.
