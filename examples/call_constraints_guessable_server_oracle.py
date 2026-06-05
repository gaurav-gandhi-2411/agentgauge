from __future__ import annotations

# Ty2 guessable-constraints fixture — Arm B (oracle schemas, full constraints).
#
# Identical to Arm A EXCEPT the constrained params carry oracle schemas:
#   ENUM    : update_order_status (status), create_support_ticket (priority),
#             set_asset_visibility (visibility)
#   FORMAT  : schedule_callback (scheduled_at) — RFC 3339 with timezone offset required
#   RANGE   : set_request_timeout (timeout) — milliseconds, min=100, max=120000
#   PRESENT : charge_customer (idempotency_key) — described as deduplication key
#
# Server always echoes success — validation is done by the run script.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("call-constraints-guessable-arm-b")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── ENUM-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="update_order_status",
            description="Update the status of an existing order.",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "processing", "settled", "voided", "disputed"],
                        "description": (
                            "Order lifecycle status: pending=awaiting payment, "
                            "processing=in fulfillment, settled=payment complete and order fulfilled, "
                            "voided=cancelled before fulfillment, disputed=under payment dispute."
                        ),
                    },
                },
                "required": ["order_id", "status"],
            },
        ),
        types.Tool(
            name="create_support_ticket",
            description="Create a new customer support ticket.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["P1", "P2", "P3", "P4"],
                        "description": (
                            "Ticket severity: P1=critical service outage (immediate), "
                            "P2=major degradation (4 h SLA), P3=minor issue (24 h SLA), "
                            "P4=enhancement request (best-effort)."
                        ),
                    },
                },
                "required": ["title", "description", "priority"],
            },
        ),
        types.Tool(
            name="set_asset_visibility",
            description="Set the visibility of a digital asset.",
            inputSchema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "visibility": {
                        "type": "string",
                        "enum": ["public", "unlisted", "internal", "archived"],
                        "description": (
                            "Access scope: public=visible to all, "
                            "unlisted=accessible only via direct link (not indexed), "
                            "internal=restricted to organisation members, "
                            "archived=read-only historical record."
                        ),
                    },
                },
                "required": ["asset_id", "visibility"],
            },
        ),
        # ── FORMAT-constrained tool ───────────────────────────────────────────
        types.Tool(
            name="schedule_callback",
            description="Schedule a callback appointment with a customer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "scheduled_at": {
                        "type": "string",
                        "format": "date-time",
                        "description": (
                            "RFC 3339 datetime with timezone offset. Include full date, time, "
                            "and UTC offset. Example: 2026-06-15T14:30:00+00:00 or "
                            "2026-06-15T09:00:00Z. Naive datetimes without an offset are rejected."
                        ),
                    },
                    "topic": {"type": "string"},
                },
                "required": ["customer_id", "scheduled_at", "topic"],
            },
        ),
        # ── RANGE-constrained tool ────────────────────────────────────────────
        types.Tool(
            name="set_request_timeout",
            description="Set the request timeout for a service.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_id": {"type": "string"},
                    "timeout": {
                        "type": "integer",
                        "minimum": 100,
                        "maximum": 120000,
                        "description": (
                            "Request timeout in milliseconds (integer). "
                            "1000 ms = 1 second. For a 5-second timeout use 5000; "
                            "for 30 seconds use 30000."
                        ),
                    },
                },
                "required": ["service_id", "timeout"],
            },
        ),
        # ── PRESENT-constrained tool ──────────────────────────────────────────
        types.Tool(
            name="charge_customer",
            description="Charge a customer's cart.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cart_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "idempotency_key": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Unique key to prevent duplicate charges. Each distinct charge request "
                            "must use a different value. Use a UUID v4 or a client-generated "
                            "request ID. Example: req-a1b2c3d4."
                        ),
                    },
                },
                "required": ["cart_id", "amount", "currency", "idempotency_key"],
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
                server_name="call-constraints-guessable-arm-b",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
