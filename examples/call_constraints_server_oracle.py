from __future__ import annotations

# Ty call-correctness fixture — Arm B (oracle schemas with enum + description).
#
# Identical to call_constraints_server.py (Arm A) EXCEPT:
#   - Hard-tool schemas include explicit enum values and descriptions for the constrained param.
#   - Hard-tool tool.description fields carry the oracle explanation.
#   - Easy tools are unchanged.
#
# The agent that reads the oracle enum can pick the correct code; Arm A's agent must guess.
# Manipulation check: _build_tool_listing(arm_b_tools) != _build_tool_listing(arm_a_tools).

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("call-constraints-arm-b")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Easy tools (identical to Arm A) ─────────────────────────────────────
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
        # ── Hard tools — Arm B (oracle: enum + description on constrained param) ─
        types.Tool(
            name="set_acquisition_mode",
            description=(
                "Configure the acquisition mode for a sensor. "
                "Use ACQ_BURST for edge-triggered bursts, "
                "ACQ_CONT for continuous streaming, "
                "ACQ_SYNC for external-clock synchronization."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["ACQ_BURST", "ACQ_CONT", "ACQ_SYNC"],
                        "description": (
                            "Acquisition mode code: "
                            "ACQ_BURST=triggered burst (capture samples on each rising edge), "
                            "ACQ_CONT=continuous free-running (samples stream without trigger), "
                            "ACQ_SYNC=synchronized-clock (output clocked to external reference)"
                        ),
                    },
                },
                "required": ["sensor_id", "mode"],
            },
        ),
        types.Tool(
            name="configure_output_codec",
            description="Configure the output encoding codec for a data stream.",
            inputSchema={
                "type": "object",
                "properties": {
                    "stream_id": {"type": "string"},
                    "codec": {
                        "type": "string",
                        "enum": ["CODEC_R8", "CODEC_R16", "CODEC_R32"],
                        "description": (
                            "Codec identifier: "
                            "CODEC_R8=8-bit unsigned integer samples, "
                            "CODEC_R16=16-bit signed integer samples, "
                            "CODEC_R32=32-bit IEEE 754 float samples"
                        ),
                    },
                },
                "required": ["stream_id", "codec"],
            },
        ),
        types.Tool(
            name="schedule_maintenance",
            description="Schedule a maintenance task with a specified execution priority.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["PRIO_X1", "PRIO_X2", "PRIO_X3"],
                        "description": (
                            "Scheduling tier: "
                            "PRIO_X1=preemptive (suspends all ongoing operations), "
                            "PRIO_X2=interleaved (runs between active operations without suspending), "
                            "PRIO_X3=background (executes only when system is fully idle)"
                        ),
                    },
                },
                "required": ["task_id", "priority"],
            },
        ),
        types.Tool(
            name="set_channel_routing",
            description="Set the output routing bus for a measurement channel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "routing": {
                        "type": "string",
                        "enum": ["RT_BUS_A", "RT_BUS_B", "RT_BUS_C"],
                        "description": (
                            "Output routing path: "
                            "RT_BUS_A=main high-bandwidth bus (always active), "
                            "RT_BUS_B=auxiliary low-latency bus (active when RT_BUS_A is at capacity), "
                            "RT_BUS_C=redundant fallback bus "
                            "(activated only on RT_BUS_A and RT_BUS_B failure)"
                        ),
                    },
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
                server_name="call-constraints-arm-b",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
