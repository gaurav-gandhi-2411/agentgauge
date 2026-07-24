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
            description=(
                "Creates a new charge to bill a customer's payment method a one-time amount. "
                "Parameters: amount (integer) — the amount to charge expressed in the smallest "
                "unit of the currency (e.g. cents for usd/eur, pence for gbp; $20.00 is "
                "expressed as 2000); currency (string) — the three-letter ISO currency code "
                "for the charge, one of 'usd', 'eur', or 'gbp'; customer_id (string) — the ID "
                "of the existing customer being charged; description (string, optional) — an "
                "arbitrary internal note attached to the charge, shown in the Dashboard but not "
                "to the customer. Unlike tools that update or reverse existing subscriptions or "
                "charges, this tool always creates a brand-new, one-time payment."
            ),
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
            description=(
                "Refunds all or part of a previously created charge, returning funds to the "
                "customer's original payment method. Parameters: charge_id (string) — the ID "
                "of the charge to refund; reason (string, optional) — why the refund is being "
                "issued, one of 'duplicate' (the charge was an accidental duplicate of another "
                "charge), 'fraudulent' (the charge was unauthorized or the result of fraud), or "
                "'requested_by_customer' (the customer asked for their money back for any other "
                "reason). Unlike tools that create new charges or modify subscriptions, this "
                "tool only reverses money already collected."
            ),
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
            description=(
                "Updates an existing subscription, such as changing its plan, quantity, or "
                "billing behavior. Parameters: subscription_id (string) — the ID of the "
                "subscription to update; proration_behavior (string, optional) — how to handle "
                "the prorated difference in price when a plan changes mid-cycle, one of "
                "'create_prorations' (the default; adds a proration line item to the "
                "customer's next invoice), 'none' (disables proration entirely — no credit or "
                "extra charge for the partial period), or 'always_invoice' (creates the "
                "proration and invoices the customer for it immediately, rather than waiting "
                "for the next regular billing cycle). Unlike tools that create brand-new "
                "charges or refunds, this tool only modifies an existing subscription."
            ),
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
            description=(
                "Creates a new customer record to represent a person or organization that can "
                "be charged or subscribed to a plan. Parameters: email (string) — the "
                "customer's email address, used for receipts and Dashboard search; name "
                "(string, optional) — the customer's full name or business name; description "
                "(string, optional) — an arbitrary internal note about the customer, not shown "
                "to them. Unlike tools that create charges or subscriptions, this tool only "
                "creates the underlying customer object with no payment attached."
            ),
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
