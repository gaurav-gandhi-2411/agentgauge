"""AgentGauge demo server (BEFORE variant).

Vague descriptions: tools in each of three pairs share the SAME description text.

Same six tool names and parameters as its sibling; only the descriptions (tool and parameter) differ. This pair was
designed to show a large gap and is illustrative, not a benchmark. Tool calls are no-ops that
return a canned acknowledgement (the demo measures tool selection and argument quality).
"""

from __future__ import annotations

import asyncio
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("agentgauge-demo-before")

TOOLS: list[dict[str, Any]] = [
    {
        "name": "ticket_comment",
        "description": "Add text to a ticket.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["ticket_id", "text"],
        },
    },
    {
        "name": "ticket_remark",
        "description": "Add text to a ticket.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["ticket_id", "text"],
        },
    },
    {
        "name": "ticket_assign",
        "description": "Set who is on a ticket.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "assignee": {"type": "string"}},
            "required": ["ticket_id", "assignee"],
        },
    },
    {
        "name": "ticket_delegate",
        "description": "Set who is on a ticket.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "assignee": {"type": "string"}},
            "required": ["ticket_id", "assignee"],
        },
    },
    {
        "name": "ticket_close",
        "description": "Finish a ticket.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "resolution": {"type": "string"}},
            "required": ["ticket_id"],
        },
    },
    {
        "name": "ticket_retire",
        "description": "Finish a ticket.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["ticket_id"],
        },
    },
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [types.Tool(**t) for t in TOOLS]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name not in {t["name"] for t in TOOLS}:
        raise ValueError(f"Unknown tool: {name}")
    return [types.TextContent(type="text", text=f"ok: {name}({arguments})")]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="agentgauge-demo-before",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(), experimental_capabilities={}
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
