from __future__ import annotations

# Stripe-payments call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real Stripe Payments API operations, 3 hard (constrained
# params) + 1 easy (no constrained param). Arm A schemas show type-only
# ({"type": "string"} or {"type": "integer"}) — no enum, no pattern, no
# minimum/maximum, no description. The agent must rely solely on param names
# and task text to construct valid calls.
#
# Constraint mix:
#   RANGE + ENUM : create_charge (amount in cents, currency)
#   ENUM         : create_refund (reason), update_subscription (proration_behavior)
#   (inert)      : create_customer (no constrained param — not used in tasks)
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against TASK_CONSTRAINTS, NOT by checking result.success.
#
# See evals/fixtures/v2_4_corpus/stripe_payments_NOTES.md for which real Stripe
# operations these tools paraphrase.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("stripe-payments-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Range + enum constrained tool ────────────────────────────────────
        types.Tool(
            name="create_charge",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "amount": {"type": "integer"},
                    "currency": {"type": "string"},
                    "customer_id": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["amount", "currency", "customer_id"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="create_refund",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "charge_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["charge_id"],
            },
        ),
        types.Tool(
            name="update_subscription",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string"},
                    "proration_behavior": {"type": "string"},
                },
                "required": ["subscription_id"],
            },
        ),
        # ── Inert tool (no constrained param — not used in TASKS) ────────────
        types.Tool(
            name="create_customer",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["email"],
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
                server_name="stripe-payments-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
