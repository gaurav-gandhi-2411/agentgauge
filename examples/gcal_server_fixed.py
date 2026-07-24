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
            description=(
                "Creates a new event on the specified Google Calendar. calendar_id identifies "
                'the target calendar (use "primary" for the authenticated user\'s default '
                "calendar). summary is the event title. start_time and end_time must be RFC "
                '3339 / ISO 8601 datetime strings including a UTC offset or a "Z" suffix (e.g. '
                '"2026-08-01T14:00:00-07:00"), matching the Calendar API\'s events.start.dateTime '
                "and events.end.dateTime fields. visibility is optional and controls who can see "
                'the event: "default" (inherits the calendar\'s own default visibility), '
                '"public", or "private". Unlike update_event_response_status, this tool creates '
                "a new event rather than modifying an attendee's RSVP on an existing one."
            ),
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
            description=(
                "Creates a new secondary Google Calendar owned by the authenticated user. "
                "summary is the calendar's display name (required). time_zone must be an IANA "
                'Time Zone Database identifier in "Area/Location" format (e.g. '
                '"America/New_York", "Europe/London", "Asia/Tokyo"), matching the Calendar '
                "API's calendars.timeZone field. Unlike create_event, this tool provisions a "
                "brand-new calendar container rather than adding an event to an existing one."
            ),
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
            description=(
                "Updates a single attendee's RSVP on an existing event, mirroring the Calendar "
                "API's events.attendees[].responseStatus field. event_id identifies the target "
                "event and attendee_email identifies which attendee's response is being set. "
                'response_status must be exactly one of: "accepted" (attending), "declined" '
                '(not attending), "tentative" (maybe attending), or "needsAction" (has not yet '
                "responded). Unlike set_event_recurrence, this tool changes an attendee's own "
                "RSVP status, not the event's repeat schedule."
            ),
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
            description=(
                "Sets a recurrence rule on an existing event, mirroring the RFC 5545 RRULE "
                "FREQ property used in the Calendar API's events.recurrence field. event_id "
                'identifies the target event. frequency must be exactly one of: "DAILY", '
                '"WEEKLY", "MONTHLY", or "YEARLY" — sub-daily frequencies (SECONDLY, MINUTELY, '
                "HOURLY) are not supported by this tool. Unlike update_event_response_status, "
                "this tool changes how often the event repeats, not an attendee's RSVP."
            ),
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
