from __future__ import annotations

# Ty Run 2 call-correctness fixture — Arm B (oracle schemas, full constraints).
#
# Identical to Arm A EXCEPT the constrained params carry oracle schemas:
#   - FORMAT tools: pattern + description on the constrained param
#   - ENUM tools: enum list + description on the constrained param
#   - RANGE tools: minimum + maximum + description on the constrained param
#
# Tool descriptions are also populated with a brief one-liner.
# Server always echoes success — validation is done by the run script.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("call-constraints-v2-arm-b")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format-constrained tools ─────────────────────────────────────────
        types.Tool(
            name="register_channel",
            description="Register a measurement channel at a site. channel_ref must be 2 uppercase letters + 2 digits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_id": {"type": "string"},
                    "channel_ref": {
                        "type": "string",
                        "pattern": "[A-Z]{2}[0-9]{2}",
                        "description": (
                            "Channel reference code: exactly 2 uppercase letters followed by "
                            "2 zero-padded digits (e.g. PH04, TM07, FL12). No separator."
                        ),
                    },
                },
                "required": ["site_id", "channel_ref"],
            },
        ),
        types.Tool(
            name="log_fault",
            description="Log a fault event for a unit. fault_code must be ERR followed by 3 digits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "unit_id": {"type": "string"},
                    "fault_code": {
                        "type": "string",
                        "pattern": "ERR[0-9]{3}",
                        "description": (
                            "Fault reference code: ERR followed by exactly 3 zero-padded digits "
                            "(e.g. ERR001, ERR042, ERR100). No spaces or separators."
                        ),
                    },
                    "message": {"type": "string"},
                },
                "required": ["unit_id", "fault_code", "message"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="set_output_encoding",
            description="Set the output encoding for a data pipeline.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pipeline_id": {"type": "string"},
                    "encoding": {
                        "type": "string",
                        "enum": ["utf-8", "ascii", "base64", "XOR16"],
                        "description": (
                            "Output encoding: utf-8=Unicode variable-width (default for most APIs), "
                            "ascii=7-bit ASCII only, base64=MIME-safe binary-to-text, "
                            "XOR16=proprietary 16-bit XOR obfuscation for legacy device compatibility"
                        ),
                    },
                },
                "required": ["pipeline_id", "encoding"],
            },
        ),
        types.Tool(
            name="set_trigger_mode",
            description="Configure the trigger edge mode for a sensor.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "trigger": {
                        "type": "string",
                        "enum": ["rising", "falling", "both", "XP7"],
                        "description": (
                            "Trigger edge condition: rising=detect low-to-high transition, "
                            "falling=detect high-to-low transition, "
                            "both=detect any edge transition, "
                            "XP7=firmware-defined proprietary pattern "
                            "(vendor-specific, requires firmware >=2.4)"
                        ),
                    },
                },
                "required": ["sensor_id", "trigger"],
            },
        ),
        # ── Range-constrained tools ───────────────────────────────────────────
        types.Tool(
            name="set_debounce_delay",
            description="Set the debounce delay for a sensor input in centiseconds.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "delay_cs": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 25,
                        "description": (
                            "Debounce delay in centiseconds (1 cs = 10 ms). "
                            "Valid range: 1 to 25 (10 ms to 250 ms)."
                        ),
                    },
                },
                "required": ["sensor_id", "delay_cs"],
            },
        ),
        types.Tool(
            name="configure_watchdog",
            description="Configure the watchdog timeout for a node in deciseconds.",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "timeout_ds": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 60,
                        "description": (
                            "Watchdog timeout in deciseconds (1 ds = 100 ms). "
                            "Valid range: 5 to 60 (0.5 s to 6 s)."
                        ),
                    },
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
                server_name="call-constraints-v2-arm-b",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
