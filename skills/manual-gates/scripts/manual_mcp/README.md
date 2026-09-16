# Manual MCP Core

This directory is the canonical source of truth for `manual_mcp`.

It owns:
- `common.py`
- `state.py`
- `manual_data.py`
- `learning.py`
- `run_*.py`
- `projects/`

Compatibility note:
- `03_分工MCP/manual_mcp` is now a thin launcher layer.
- Runtime execution should resolve through this directory so project state,
  learned overlays, and the v6.22 state-lock fix stay unified.

Primary workflow:
1. Inspect `manual_data.py` for stage/node contracts.
2. Use `run_*.py` for the specific role entry.
3. Read/write `projects/<project>/state.json` through `state.py`.
4. Use `learning.py` for the controlled learning lifecycle:
   `candidate -> shadow -> review -> owner approval -> promote`.
   Project experience is stored in `learned_candidates.json`; `learned.json`
   is changed only by an explicit promotion after Owner approval.
