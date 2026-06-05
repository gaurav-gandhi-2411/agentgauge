from __future__ import annotations

# Ty2 guessable-constraints fixture — Arm A (vague schemas, no constraints).
#
# 6 tools covering 4 constraint types:
#   ENUM    : update_order_status, create_support_ticket, set_asset_visibility
#   FORMAT  : schedule_callback
#   RANGE   : set_request_timeout
#   PRESENT : charge_customer
# Server echoes success; validation is done in the run script via constructed_args.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("call-constraints-guessable-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── ENUM-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="update_order_status",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["order_id", "status"],
            },
        ),
        types.Tool(
            name="create_support_ticket",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string"},
                },
                "required": ["title", "description", "priority"],
            },
        ),
        types.Tool(
            name="set_asset_visibility",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "visibility": {"type": "string"},
                },
                "required": ["asset_id", "visibility"],
            },
        ),
        # ── FORMAT-constrained tool ───────────────────────────────────────────
        types.Tool(
            name="schedule_callback",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "scheduled_at": {"type": "string"},
                    "topic": {"type": "string"},
                },
                "required": ["customer_id", "scheduled_at", "topic"],
            },
        ),
        # ── RANGE-constrained tool ────────────────────────────────────────────
        types.Tool(
            name="set_request_timeout",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_id": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["service_id", "timeout"],
            },
        ),
        # ── PRESENT-constrained tool ──────────────────────────────────────────
        types.Tool(
            name="charge_customer",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "cart_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "idempotency_key": {"type": "string"},
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
                server_name="call-constraints-guessable-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
