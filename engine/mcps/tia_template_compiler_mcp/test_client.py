import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "OPENNISS"
    / "Nexteer Lead frame Test Line_ST10_20240423(HourlyNG)_V21"
)


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("run_tia_template_compiler.py"))],
        cwd=str(Path(__file__).parent),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            required = {
                "scan_template",
                "validate_project_spec",
                "build_change_spec",
                "preview_change",
                "stage_runner_bundle",
                "verify_change",
            }
            missing = sorted(required - set(names))
            if missing:
                raise RuntimeError(f"missing MCP tools: {missing}")
            result = await session.call_tool(
                "scan_template",
                {"template_root": str(TEMPLATE)},
            )
            payload = json.loads(result.content[0].text)
            if not payload.get("ok"):
                raise RuntimeError(payload)
            print(json.dumps({
                "ok": True,
                "tool_count": len(names),
                "tools": names,
                "template_project": payload.get("project_file"),
                "semantic_catalog_status": payload.get("semantic_catalog_status"),
            }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
