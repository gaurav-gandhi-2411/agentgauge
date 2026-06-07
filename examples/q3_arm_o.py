from __future__ import annotations

# Q3 source-aware experiment — Arm O (oracle descriptions, ceiling).
# Oracle descriptions are derived from reading q3_real_server.py implementations.

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from evals.fixtures.q3_catalog import ARM_O_DESCRIPTIONS, FAMILIES

server = Server("q3-arm-o")

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=name, description=ARM_O_DESCRIPTIONS[name], inputSchema=_SCHEMA)
        for names in FAMILIES.values()
        for name in names
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    result = json.dumps({"tool": name, "query": arguments.get("query", "")})
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="q3-arm-o",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
