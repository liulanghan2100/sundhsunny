# -*- coding: utf-8 -*-
"""manual-gates 桥接 CLI：不依赖客户端 MCP 注册，直接通过 stdio 调用分工 MCP 的工具。

用法:
  python gate.py <role> <tool> [json-args]
  python gate.py <role> <tool> key=value key=value ...

  role: strategy | design | data_ai | planning | dev | qa | ops
  tool: role_brief | checklist | plan_next | submit_check | gate_report | mckinsey | full_map

示例:
  python gate.py strategy plan_next "{\"project\": \"myapp\"}"
  python gate.py dev submit_check "{\"project\": \"myapp\", \"node_id\": 15, \"artifact_path\": \"C:/proj/api.py\", \"passed\": true, \"notes\": \"核心链路已通\"}"
  python gate.py dev submit_check project=myapp node_id=15 artifact_path=C:/proj/api.py passed=true notes=核心链路已通
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
ROLES = ["strategy", "design", "data_ai", "planning", "dev", "qa", "ops"]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


def _parse_value(value: str):
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in ("null", "none"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_args(argv: list[str]) -> dict:
    if not argv:
        return {}
    if len(argv) == 1:
        text = argv[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            if "=" not in text:
                raise SystemExit(f"参数不是合法 JSON，也不是 key=value：{e}") from e
    args = {}
    for item in argv:
        if "=" not in item:
            raise SystemExit(f"参数格式错误，应为 key=value：{item}")
        key, value = item.split("=", 1)
        if not key:
            raise SystemExit(f"参数 key 为空：{item}")
        args[key] = _parse_value(value)
    return args


async def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    role, tool = sys.argv[1], sys.argv[2]
    if role not in ROLES:
        print(f"未知分工: {role}，可选: {', '.join(ROLES)}")
        sys.exit(2)
    args = parse_args(sys.argv[3:])

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "manual_mcp" / f"run_{role}.py")],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            for c in result.content:
                text = getattr(c, "text", None)
                if text:
                    print(text)


asyncio.run(main())
