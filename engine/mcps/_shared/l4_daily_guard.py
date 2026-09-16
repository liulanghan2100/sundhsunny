# -*- coding: utf-8 -*-
"""Pure helpers for the guarded L4 daily entrypoint."""
import json
from datetime import datetime, timedelta, timezone


CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
NOT_BEFORE = datetime(2026, 8, 1, 7, 0, 0, tzinfo=CHINA_TZ)


def write_state_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def subprocess_result(proc, success_status: str = "completed", failure_status: str = "failed", tail: int = 2000) -> dict:
    return {
        "status": success_status if proc.returncode == 0 else failure_status,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-tail:],
        "stderr_tail": (proc.stderr or "")[-tail:],
    }
