from __future__ import annotations

# P2-A experiment — Arm O (oracle descriptions, human-derived ceiling).
#
# Oracle descriptions encode the behavioral distinctions each contested tool has
# vs its confusable neighbors. Derived exclusively from reading the mirror handler
# docstrings in p2a_internal_proxy_mirror.py — no distinction is asserted that the
# mirror body or docstring does not support.
# Represents the maximum recoverable selection accuracy on this 48-tool catalog.

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from evals.fixtures.p2a_internal_proxy_catalog import ARM_O_DESCRIPTIONS, TOOL_SCHEMAS

server = Server("p2a-arm-oracle")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=name, description=ARM_O_DESCRIPTIONS[name], inputSchema=schema)
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
                server_name="p2a-arm-oracle",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
