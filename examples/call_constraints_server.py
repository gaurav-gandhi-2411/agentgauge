from __future__ import annotations

# Ty call-correctness fixture — Arm A (vague schemas, no enum hints).
#
# 8 tools: 4 easy (no constrained params) + 4 hard (enum-constrained params).
# Arm A hard-tool schemas show type-only ({"type": "string"}) — no enum, no description.
# The agent cannot derive correct enum values from the param name or task text alone.
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against GOLD_CONSTRAINTS, NOT by checking result.success.
#
# EASY TOOLS (identical schema in both arms):
#   ping_server       — no params
#   get_server_info   — no params
#   list_channels     — no params
#   reset_state       — no params
#
# HARD TOOLS — Arm A (type-only, no enum):
#   set_acquisition_mode(sensor_id: string, mode: string)
#   configure_output_codec(stream_id: string, codec: string)
#   schedule_maintenance(task_id: string, priority: string)
#   set_channel_routing(channel_id: string, routing: string)
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("call-constraints-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Easy tools (no constrained params) ──────────────────────────────────
        types.Tool(
            name="ping_server",
            description="",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_server_info",
            description="",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="list_channels",
            description="",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="reset_state",
            description="",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        # ── Hard tools — Arm A (type-only schema, no enum) ─────────────────────
        types.Tool(
            name="set_acquisition_mode",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "mode": {"type": "string"},
                },
                "required": ["sensor_id", "mode"],
            },
        ),
        types.Tool(
            name="configure_output_codec",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "stream_id": {"type": "string"},
                    "codec": {"type": "string"},
                },
                "required": ["stream_id", "codec"],
            },
        ),
        types.Tool(
            name="schedule_maintenance",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "priority": {"type": "string"},
                },
                "required": ["task_id", "priority"],
            },
        ),
        types.Tool(
            name="set_channel_routing",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "routing": {"type": "string"},
                },
                "required": ["channel_id", "routing"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    # Always echo success — correctness scoring happens in the run script via constructed_args.
    result = json.dumps({"tool": name, "args": arguments})
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="call-constraints-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
