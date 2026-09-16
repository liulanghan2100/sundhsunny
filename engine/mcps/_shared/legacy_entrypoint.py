# -*- coding: utf-8 -*-
"""Helpers for thin legacy entrypoint shims."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Tuple


def build_legacy_entrypoint(
    legacy_file: Path,
    root: Path,
    unified_filename: str,
    command: str,
    group: str,
) -> tuple[Callable[[bool], None], Callable[[], int]]:
    unified = root / unified_filename
    usage_log = root.parent / "09_research" / "agent-os-structure-slimming-v1" / "legacy_entrypoint_usage.jsonl"

    def record_usage(allowed: bool) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "legacy_entrypoint": str(legacy_file.resolve().relative_to(root.parent)),
            "group": group,
            "command": command,
            "unified_cli": str(unified.relative_to(root.parent)),
            "argv": sys.argv[1:],
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "allowed": allowed,
            "action": "delegated" if allowed else "locked",
        }
        try:
            usage_log.parent.mkdir(parents=True, exist_ok=True)
            with usage_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def main() -> int:
        allowed = os.environ.get("AGENT_OS_ALLOW_LEGACY_ENTRYPOINT") == "1"
        record_usage(allowed)
        if not allowed:
            print(
                "Legacy entrypoint is locked. Use the unified entrypoint instead:\n"
                f"  python Agent_OS_Core/agent_os.py delegate {group} run {command}\n"
                "To execute the preserved legacy implementation, set "
                "AGENT_OS_ALLOW_LEGACY_ENTRYPOINT=1 explicitly."
            )
            return 2
        return subprocess.run(
            [sys.executable, str(unified), "run", command, "--execute", *sys.argv[1:]],
            cwd=root.parent,
            check=False,
        ).returncode

    return record_usage, main
