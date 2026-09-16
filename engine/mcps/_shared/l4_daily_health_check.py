# -*- coding: utf-8 -*-
"""Pure helpers for L4 daily health-check reports."""
from datetime import datetime, timedelta, timezone


CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def health_check_commands(root, executable: str) -> list[tuple[str, list[str]]]:
    mcp_dir = root / "03_鍒嗗伐MCP"
    return [
        (
            "compileall",
            [
                executable,
                "-m",
                "compileall",
                str(mcp_dir / "task_queue_mcp" / "common.py"),
                str(mcp_dir / "agent_os_l4_daily_guard.py"),
                str(mcp_dir / "agent_os_l4_soak_audit.py"),
                str(mcp_dir / "agent_os_l4_daily_health_check.py"),
            ],
        ),
        ("task_queue", [executable, str(mcp_dir / "smoke_test_task_queue_mcp.py")]),
        ("queue_gate_linkage", [executable, str(mcp_dir / "smoke_test_queue_gate_linkage.py")]),
        ("queue_watchdog", [executable, str(mcp_dir / "smoke_test_queue_watchdog.py")]),
        ("self_initiation_governance", [executable, str(mcp_dir / "smoke_test_self_initiation_governance.py")]),
        ("daily_guard", [executable, str(mcp_dir / "smoke_test_agent_os_l4_daily_guard.py")]),
        ("soak_audit", [executable, str(mcp_dir / "smoke_test_agent_os_l4_soak_audit.py")]),
        ("daily_health_check", [executable, str(mcp_dir / "smoke_test_agent_os_l4_daily_health_check.py")]),
    ]


def health_result_payload(generated_at: str, results: list[dict]) -> dict:
    failed = [item for item in results if item["returncode"] != 0]
    return {
        "generated_at": generated_at,
        "status": "passed" if not failed else "failed",
        "checks": results,
        "failed_checks": [item["name"] for item in failed],
    }


def report_payload(result: dict) -> dict:
    day = datetime.fromisoformat(result["generated_at"]).strftime("%Y-%m-%d")
    lines = [
        f"# {day} Agent OS L4 健康检查",
        "",
        f"- generated_at: `{result['generated_at']}`",
        f"- status: `{result['status']}`",
        "",
        "## Checks",
        "",
    ]
    for check in result["checks"]:
        lines.append(f"- `{check['name']}`: `{check['status']}`")
    if result["failed_checks"]:
        lines.extend(["", "## Failed Checks", ""])
        for name in result["failed_checks"]:
            lines.append(f"- `{name}`")
    return {
        "day": day,
        "json_name": f"{day}_l4_health_check.json",
        "md_name": f"{day}_l4_health_check.md",
        "markdown": "\n".join(lines) + "\n",
    }
