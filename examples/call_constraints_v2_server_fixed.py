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
            description="Registers a channel with a specified site, using site_id to identify the site and channel_ref as the channel's reference identifier. This tool specifically handles channel registration, distinguishing it from tools that manage or track channels.",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_id": {"type": "string"},
                    "channel_ref": {"type": "string"},
                },
                "required": ["channel_ref", "site_id"],
            },
        ),
        types.Tool(
            name="log_fault",
            description='Logs fault information for a specific unit, including unit ID, fault code, and an associated message. This tool is designed for detailed fault tracking by associating each fault with a unique unit identifier and standardized code, distinguishing it from general logging tools that may lack these structured parameters.',
            inputSchema={
                "type": "object",
                "properties": {
                    "unit_id": {"type": "string"},
                    "fault_code": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["fault_code", "message", "unit_id"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="set_output_encoding",
            description='Configures the output encoding for a specified pipeline, requiring pipeline_id (identifies the target pipeline) and encoding (defines the output format, e.g., UTF-8). Unlike similar tools, it specifically targets output data encoding rather than input or processing parameters.',
            inputSchema={
                "type": "object",
                "properties": {
                    "pipeline_id": {"type": "string"},
                    "encoding": {"type": "string"},
                },
                "required": ["encoding", "pipeline_id"],
            },
        ),
        types.Tool(
            name="set_trigger_mode",
            description="Sets the trigger mode for a specified sensor, requiring a sensor_id (unique identifier) and trigger (mode like 'on', 'off', or 'auto'). Unlike general sensor tools, this focuses exclusively on configuring trigger behavior.",
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
            description='Sets the debounce delay (in clock cycles) for a specified sensor to filter noisy input signals. Requires sensor_id (target sensor) and delay_cs (debounce duration in clock cycles). This tool is specifically for configuring sensor input debounce, distinguishing it from general delay settings.',
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "delay_cs": {"type": "integer"},
                },
                "required": ["delay_cs", "sensor_id"],
            },
        ),
        types.Tool(
            name="configure_watchdog",
            description='Configures a watchdog for a specified node with a defined timeout duration in data seconds. Parameters: node_id (string, node identifier), timeout_ds (integer, timeout duration in data seconds). Uses data seconds for timeout, distinguishing it from tools that use standard seconds.',
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
