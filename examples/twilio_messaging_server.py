from __future__ import annotations

# Twilio Messaging/Voice call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real Twilio Programmable Messaging/Voice REST API
# operations. Arm A schemas show type-only ({"type": "string"}) — no enum, no
# pattern, no description. The agent must rely solely on param names and task
# text to construct valid calls.
#
# Constraint mix (2 tools per type):
#   FORMAT : send_sms (to, E.164 phone number shape), lookup_phone_number
#            (country_code, ISO 3166-1 alpha-2 shape)
#   ENUM   : make_call (method, HTTP method Twilio uses to request the TwiML
#            webhook — "GET"/"POST"), set_call_status_callback (status_event,
#            call lifecycle stage — "initiated"/"ringing"/"answered"/"completed")
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

server = Server("twilio-messaging-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format-constrained tools ─────────────────────────────────────────
        types.Tool(
            name="send_sms",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "from_number": {"type": "string"},
                    "body": {"type": "string"},
                    "media_url": {"type": "string"},
                },
                "required": ["to", "from_number", "body"],
            },
        ),
        types.Tool(
            name="lookup_phone_number",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string"},
                    "country_code": {"type": "string"},
                    "fields": {"type": "string"},
                },
                "required": ["phone_number"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="make_call",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "from_number": {"type": "string"},
                    "url": {"type": "string"},
                    "method": {"type": "string"},
                },
                "required": ["to", "from_number", "url"],
            },
        ),
        types.Tool(
            name="set_call_status_callback",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "call_sid": {"type": "string"},
                    "status_callback_url": {"type": "string"},
                    "status_event": {"type": "string"},
                },
                "required": ["call_sid", "status_callback_url", "status_event"],
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
                server_name="twilio-messaging-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
