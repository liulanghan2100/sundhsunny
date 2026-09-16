# -*- coding: utf-8 -*-
"""Time helpers shared by MCP common modules."""
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
