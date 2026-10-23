"""AgentGauge demo server (AFTER variant).

Same names and parameters, but each description says what the tool does, when to use it and when not to.

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

server = Server("agentgauge-demo-after")

TOOLS: list[dict[str, Any]] = [
    {
        "name": "ticket_comment",
        "description": "Post a reply on a ticket that the CUSTOMER (the requester) will see and receive by email. Use to communicate with the person who reported the problem. Never for private staff discussion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "Numeric ticket id, e.g. 4812"},
                "text": {"type": "string", "description": "The message to show the customer"},
            },
            "required": ["ticket_id", "text"],
        },
    },
    {
        "name": "ticket_remark",
        "description": "Add an INTERNAL, staff-only remark to a ticket. It is never shown to or emailed to the customer. Use for private reminders, diagnoses and hand-off context for colleagues.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "Numeric ticket id, e.g. 4812"},
                "text": {"type": "string", "description": "The internal remark for staff"},
            },
            "required": ["ticket_id", "text"],
        },
    },
    {
        "name": "ticket_assign",
        "description": "Give an UNOWNED ticket its first owner. Use only when nobody is currently responsible for the ticket. If it already has an owner, use ticket_delegate instead.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "Numeric ticket id, e.g. 4812"},
                "assignee": {
                    "type": "string",
                    "description": "Person or team who becomes the owner",
                },
            },
            "required": ["ticket_id", "assignee"],
        },
    },
    {
        "name": "ticket_delegate",
        "description": "Hand a ticket that ALREADY has an owner over to someone else; the previous owner is notified that it left their plate. Use for reassignment, leave cover or workload shifting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "Numeric ticket id, e.g. 4812"},
                "assignee": {
                    "type": "string",
                    "description": "Person or team who takes over the ticket",
                },
            },
            "required": ["ticket_id", "assignee"],
        },
    },
    {
        "name": "ticket_close",
        "description": "Mark a ticket as SOLVED: the problem was fixed or answered. The requester is notified that it was resolved. Do not use for stale or abandoned tickets; use ticket_retire.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "Numeric ticket id, e.g. 4812"},
                "resolution": {"type": "string", "description": "What fixed the problem"},
            },
            "required": ["ticket_id"],
        },
    },
    {
        "name": "ticket_retire",
        "description": "Shelve a ticket that was NOT solved (stale, abandoned, never going to be worked): it disappears from active queues but the record is kept, and nobody is notified. Never implies the problem was fixed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string", "description": "Numeric ticket id, e.g. 4812"},
                "reason": {"type": "string", "description": "Why the ticket is being shelved"},
            },
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
                server_name="agentgauge-demo-after",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(), experimental_capabilities={}
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
