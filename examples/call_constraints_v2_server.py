from __future__ import annotations

# Ty Run 2 call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 6 tools, all hard — no inert easy tasks.
# Arm A schemas show type-only ({"type": "string"} or {"type": "integer"}) —
# no enum, no pattern, no minimum/maximum, no description.
# The agent must rely solely on param names and task text to construct valid calls.
#
# Constraint mix (2 tools per type):
#   FORMAT  : register_channel (channel_ref), log_fault (fault_code)
#   ENUM    : set_output_encoding (encoding), set_trigger_mode (trigger)
#   RANGE   : set_debounce_delay (delay_cs), configure_watchdog (timeout_ds)
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against TASK_CONSTRAINTS, NOT by checking result.success.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("call-constraints-v2-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format-constrained tools ─────────────────────────────────────────
        types.Tool(
            name="register_channel",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_id": {"type": "string"},
                    "channel_ref": {"type": "string"},
                },
                "required": ["site_id", "channel_ref"],
            },
        ),
        types.Tool(
            name="log_fault",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "unit_id": {"type": "string"},
                    "fault_code": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["unit_id", "fault_code", "message"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="set_output_encoding",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "pipeline_id": {"type": "string"},
                    "encoding": {"type": "string"},
                },
                "required": ["pipeline_id", "encoding"],
            },
        ),
        types.Tool(
            name="set_trigger_mode",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "trigger": {"type": "string"},
                },
                "required": ["sensor_id", "trigger"],
            },
        ),
        # ── Range-constrained tools ───────────────────────────────────────────
        types.Tool(
            name="set_debounce_delay",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "delay_cs": {"type": "integer"},
                },
                "required": ["sensor_id", "delay_cs"],
            },
        ),
        types.Tool(
            name="configure_watchdog",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "timeout_ds": {"type": "integer"},
                },
                "required": ["node_id", "timeout_ds"],
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
                server_name="call-constraints-v2-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
