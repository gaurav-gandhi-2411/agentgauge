from __future__ import annotations

# Google Calendar call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools, all hard — no inert easy tools. Modeled on real Google Calendar API v3
# operations: events.insert, events.attendees[].responseStatus (via events.patch),
# events.recurrence RRULE FREQ (RFC 5545), and calendars.insert.
# Arm A schemas show type-only ({"type": "string"}) — no enum, no pattern,
# no description. The agent must rely solely on param names and task text to
# construct valid calls.
#
# Constraint mix (2 tools per type):
#   FORMAT : create_event (start_time, RFC 3339 / ISO 8601 datetime),
#            create_calendar (time_zone, IANA Time Zone Database name)
#   ENUM   : update_event_response_status (response_status),
#            set_event_recurrence (frequency, RFC 5545 RRULE FREQ)
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

server = Server("gcal-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format-constrained tools ─────────────────────────────────────────
        types.Tool(
            name="create_event",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "visibility": {"type": "string"},
                },
                "required": ["calendar_id", "summary", "start_time", "end_time"],
            },
        ),
        types.Tool(
            name="create_calendar",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "time_zone": {"type": "string"},
                },
                "required": ["summary", "time_zone"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="update_event_response_status",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "attendee_email": {"type": "string"},
                    "response_status": {"type": "string"},
                },
                "required": ["event_id", "attendee_email", "response_status"],
            },
        ),
        types.Tool(
            name="set_event_recurrence",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "frequency": {"type": "string"},
                },
                "required": ["event_id", "frequency"],
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
                server_name="gcal-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
