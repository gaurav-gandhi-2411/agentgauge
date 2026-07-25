from __future__ import annotations

# Twilio Messaging/Voice call-correctness fixture — Arm F (same schemas as Arm A, real
# descriptions restored).
#
# Same 4 tools as twilio_messaging_server.py. inputSchema is IDENTICAL to the Arm
# A variant (still type-only — no enum, no pattern keywords) so the only
# difference under test is whether the agent can construct correct calls from
# the Tool.description text alone.
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
            description=(
                "Sends an SMS text message from a Twilio phone number to a recipient. "
                "Requires to (the recipient's phone number in E.164 format, e.g. "
                "'+14155552671' — a leading '+' followed by the country code and "
                "subscriber number, digits only, no spaces or punctuation), from_number "
                "(the sending Twilio phone number, also in E.164 format), and body (the "
                "message text; Twilio auto-segments messages over 160 characters into "
                "multiple parts). Optionally accepts media_url (a publicly reachable URL "
                "for an image or file attachment, turning the message into an MMS). "
                "Unlike make_call, this tool sends a one-way text message rather than "
                "placing a live voice call."
            ),
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
            description=(
                "Looks up metadata about a phone number using Twilio's Lookup API, such "
                "as whether it's a currently valid, in-service line and what type of line "
                "it is (mobile, landline, or VoIP). Requires phone_number (the number to "
                "look up). Optionally accepts country_code (the ISO 3166-1 alpha-2 country "
                "code, e.g. 'US' or 'GB' — required when phone_number is given in "
                "national/local format rather than full E.164, so Twilio knows which "
                "country's numbering plan to apply) and fields (a comma-separated list of "
                "additional data packages to include in the response, such as "
                "'line_type_intelligence'). Unlike send_sms or make_call, this tool never "
                "contacts the recipient — it only queries Twilio's own number database."
            ),
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
            description=(
                "Places an outbound voice call from a Twilio phone number and instructs "
                "Twilio to fetch call-handling instructions (TwiML) from a webhook URL. "
                "Requires to (the recipient's phone number in E.164 format), from_number "
                "(the calling Twilio phone number, also in E.164 format), and url (the "
                "webhook Twilio will request once the call connects, to get instructions "
                "for what to say or do). Optionally accepts method ('GET' or 'POST', "
                "defaulting to 'POST') — the HTTP method Twilio uses to request url: use "
                "'GET' when url points to a static, unchanging TwiML document that "
                "doesn't need any call data submitted to it, and use 'POST' when your "
                "endpoint needs to receive the call's parameters (like the caller's "
                "number) as form-encoded data so it can decide what to say dynamically. "
                "Unlike send_sms, this tool places a live voice call rather than sending "
                "a text."
            ),
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
            description=(
                "Configures a status callback on a Twilio voice call so that Twilio "
                "notifies your application's webhook when the call reaches a particular "
                "lifecycle stage. Requires call_sid (the unique identifier of the call to "
                "configure), status_callback_url (the webhook URL Twilio will request when "
                "the event fires), and status_event (which lifecycle event triggers the "
                "callback: 'initiated' — the call has been created but dialing hasn't "
                "started yet; 'ringing' — the callee's phone is alerting them but they "
                "haven't picked up; 'answered' — the callee has picked up and the call is "
                "connected; or 'completed' — the call has ended and both parties have "
                "disconnected). Unlike make_call, this tool doesn't start a new call — it "
                "attaches monitoring to a call that's already in progress or about to "
                "begin."
            ),
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
