from __future__ import annotations

# T18 discoverability-at-scale fixture — Arm A (vague/empty descriptions).
#
# 60 tools in 10 families of 6 near-neighbors each.
# Arm A: all descriptions empty — agent must rely on tool names alone.
# Server name: t18-discoverability-arm-a
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from evals.fixtures.t18_catalog import ARM_A_DESCRIPTIONS, FAMILIES

server = Server("t18-discoverability-arm-a")

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return all 60 tools with empty descriptions (Arm A)."""
    tools: list[types.Tool] = []
    for _family, tool_names in FAMILIES.items():
        for name in tool_names:
            tools.append(
                types.Tool(
                    name=name,
                    description=ARM_A_DESCRIPTIONS[name],
                    inputSchema=_SCHEMA,
                )
            )
    return tools


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Echo tool name and query back as JSON."""
    result = json.dumps({"tool": name, "query": arguments.get("query", "")})
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="t18-discoverability-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
