# -*- coding: utf-8 -*-
"""manual-gates 桥接 CLI：不依赖客户端 MCP 注册，直接通过 stdio 调用分工 MCP 的工具。

用法:
  python gate.py <role> <tool> [json-args]

  role: strategy | design | data_ai | planning | dev | qa | ops
  tool: role_brief | checklist | plan_next | submit_check | gate_report | mckinsey | full_map

示例:
  python gate.py strategy plan_next "{\"project\": \"myapp\"}"
  python gate.py dev submit_check "{\"project\": \"myapp\", \"node_id\": 15, \"artifact_path\": \"C:/proj/api.py\", \"passed\": true, \"notes\": \"核心链路已通\"}"
"""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
ROLES = ["strategy", "design", "data_ai", "planning", "dev", "qa", "ops"]


async def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    role, tool = sys.argv[1], sys.argv[2]
    if role not in ROLES:
        print(f"未知分工: {role}，可选: {', '.join(ROLES)}")
        sys.exit(2)
    args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}

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
