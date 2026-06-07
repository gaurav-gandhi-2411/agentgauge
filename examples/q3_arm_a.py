from __future__ import annotations

# Q3 source-aware experiment — Arm A (empty descriptions, baseline).
# Serves the same 12 Q3 tools with no descriptions.
# call_tool echoes tool+query; selection_accuracy is what the A/B measures.

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from evals.fixtures.q3_catalog import ARM_A_DESCRIPTIONS, FAMILIES

server = Server("q3-arm-a")

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=name, description=ARM_A_DESCRIPTIONS[name], inputSchema=_SCHEMA)
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
                server_name="q3-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
