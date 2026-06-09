from __future__ import annotations

# RW1 experiment — Arm A (original GitHub docstrings, the shipped baseline).
#
# Unlike previous Q3–Q6 experiments where Arm A used EMPTY descriptions,
# here Arm A uses the REAL GitHub MCP server descriptions as shipped.
# This is the external-validity test: does the real documented server have
# headroom that Guard-B can recover?

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from evals.fixtures.rw1_github_catalog import ARM_A_DESCRIPTIONS, TOOL_SCHEMAS

server = Server("rw1-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=name, description=ARM_A_DESCRIPTIONS[name], inputSchema=schema)
        for name, schema in TOOL_SCHEMAS.items()
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    result = json.dumps({"tool": name, "args": sorted(arguments.keys())})
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="rw1-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
