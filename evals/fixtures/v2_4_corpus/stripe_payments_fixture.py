from __future__ import annotations

# Stripe-payments pre-registered tasks and constraints for the call-correctness
# oracle A/B (v2.4 corpus expansion, Task 4 — real-API domain pilot).
#
# 4 tools modeled on real Stripe Payments API operations (see
# stripe_payments_NOTES.md): create_charge, create_refund, update_subscription,
# create_customer. create_customer has no genuine constrained parameter and is
# deliberately excluded from TASKS/TASK_CONSTRAINTS (inert tool, present only
# to give the fixture a realistic 4th operation).
#
# 15 tasks: 5 per constrained tool x 3 constrained tools — ALL hard, NO inert
# easy tasks (mirrors evals/fixtures/ty2_tasks.py's design).
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only.
# They must NOT contain enum values (e.g. "usd", "fraudulent",
# "always_invoice"), format patterns, unit names, or literal cents amounts.
# The agent must derive the correct value from the SCHEMA (fixed arm) or from
# real-world context clues (e.g. a city implies a country's currency), not
# from a literal value quoted in the task text.
from dataclasses import dataclass, field  # noqa: F401 — field reserved for future extension

from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

TASKS: list[Task] = [
    # ── create_charge (range: amount in cents; enum: currency) — 5 tasks ────
    Task(
        "create_charge",
        "Charge a customer based in New York the standard monthly fee for their software "
        "subscription",
    ),
    Task(
        "create_charge",
        "Bill a customer in Berlin for their standard monthly cloud storage plan",
    ),
    Task(
        "create_charge",
        "Process the recurring monthly charge for a customer based in Manchester's fitness "
        "app subscription",
    ),
    Task(
        "create_charge",
        "Charge a customer in Chicago the regular monthly fee for their video streaming "
        "subscription",
    ),
    Task(
        "create_charge",
        "Bill a customer based in Lyon for their standard monthly project management software plan",
    ),
    # ── create_refund (enum: reason) — 5 tasks ───────────────────────────────
    Task(
        "create_refund",
        "Refund a charge that was accidentally submitted twice for the same order",
    ),
    Task(
        "create_refund",
        "Refund a charge after the customer reported unauthorized activity on their card",
    ),
    Task(
        "create_refund",
        "Process a refund because the customer called in asking to cancel and get their money back",
    ),
    Task(
        "create_refund",
        "Refund a charge that was processed twice due to a checkout page being submitted "
        "twice by mistake",
    ),
    Task(
        "create_refund",
        "Issue a refund because the customer changed their mind and no longer wants the "
        "item they paid for",
    ),
    # ── update_subscription (enum: proration_behavior) — 5 tasks ─────────────
    Task(
        "update_subscription",
        "Upgrade a customer's subscription plan and make sure they're billed immediately "
        "for the prorated difference right now",
    ),
    Task(
        "update_subscription",
        "Change a customer's subscription tier but don't charge or credit them any "
        "prorated amount for the switch",
    ),
    Task(
        "update_subscription",
        "Move a customer to a higher subscription tier partway through their billing "
        "cycle, crediting them fairly for the switch on their next invoice",
    ),
    Task(
        "update_subscription",
        "Downgrade a customer's plan without adjusting their billing for the partial period",
    ),
    Task(
        "update_subscription",
        "Switch a customer to a different subscription plan and invoice them right away "
        "for the price difference instead of waiting for their next billing cycle",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
#
# create_charge tasks carry TWO constraints each: an enum constraint on
# `currency` (derived from the customer's implied country) and a shared range
# constraint on `amount` (1000-15000 cents, i.e. $10.00-$150.00). The range
# tests unit conversion specifically: a vague-schema agent that reads "the
# standard monthly fee" and writes the bare dollar figure (e.g. 20) instead of
# converting to cents (2000) falls outside the range and fails, exactly as a
# fixed-schema agent that reads "amount ... in the smallest unit ... $20.00 is
# expressed as 2000" would not.
_CHARGE_AMOUNT_RANGE = Constraint("amount", "range", min_val=1000, max_val=15000)

TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # create_charge — enum: currency (usd/eur/gbp, implied by city) + range: amount
    (
        "create_charge",
        "Charge a customer based in New York the standard monthly fee for their software "
        "subscription",
    ): [Constraint("currency", "enum", gold_value="usd"), _CHARGE_AMOUNT_RANGE],
    (
        "create_charge",
        "Bill a customer in Berlin for their standard monthly cloud storage plan",
    ): [Constraint("currency", "enum", gold_value="eur"), _CHARGE_AMOUNT_RANGE],
    (
        "create_charge",
        "Process the recurring monthly charge for a customer based in Manchester's fitness "
        "app subscription",
    ): [Constraint("currency", "enum", gold_value="gbp"), _CHARGE_AMOUNT_RANGE],
    (
        "create_charge",
        "Charge a customer in Chicago the regular monthly fee for their video streaming "
        "subscription",
    ): [Constraint("currency", "enum", gold_value="usd"), _CHARGE_AMOUNT_RANGE],
    (
        "create_charge",
        "Bill a customer based in Lyon for their standard monthly project management software plan",
    ): [Constraint("currency", "enum", gold_value="eur"), _CHARGE_AMOUNT_RANGE],
    # create_refund — enum: reason
    (
        "create_refund",
        "Refund a charge that was accidentally submitted twice for the same order",
    ): [Constraint("reason", "enum", gold_value="duplicate")],
    (
        "create_refund",
        "Refund a charge after the customer reported unauthorized activity on their card",
    ): [Constraint("reason", "enum", gold_value="fraudulent")],
    (
        "create_refund",
        "Process a refund because the customer called in asking to cancel and get their money back",
    ): [Constraint("reason", "enum", gold_value="requested_by_customer")],
    (
        "create_refund",
        "Refund a charge that was processed twice due to a checkout page being submitted "
        "twice by mistake",
    ): [Constraint("reason", "enum", gold_value="duplicate")],
    (
        "create_refund",
        "Issue a refund because the customer changed their mind and no longer wants the "
        "item they paid for",
    ): [Constraint("reason", "enum", gold_value="requested_by_customer")],
    # update_subscription — enum: proration_behavior
    (
        "update_subscription",
        "Upgrade a customer's subscription plan and make sure they're billed immediately "
        "for the prorated difference right now",
    ): [Constraint("proration_behavior", "enum", gold_value="always_invoice")],
    (
        "update_subscription",
        "Change a customer's subscription tier but don't charge or credit them any "
        "prorated amount for the switch",
    ): [Constraint("proration_behavior", "enum", gold_value="none")],
    (
        "update_subscription",
        "Move a customer to a higher subscription tier partway through their billing "
        "cycle, crediting them fairly for the switch on their next invoice",
    ): [Constraint("proration_behavior", "enum", gold_value="create_prorations")],
    (
        "update_subscription",
        "Downgrade a customer's plan without adjusting their billing for the partial period",
    ): [Constraint("proration_behavior", "enum", gold_value="none")],
    (
        "update_subscription",
        "Switch a customer to a different subscription plan and invoice them right away "
        "for the price difference instead of waiting for their next billing cycle",
    ): [Constraint("proration_behavior", "enum", gold_value="always_invoice")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_charge", "create_refund", "update_subscription", "create_customer"]
)
CONSTRAINED_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_charge", "create_refund", "update_subscription"]
)
INERT_TOOL_NAMES: frozenset[str] = frozenset(["create_customer"])

# Enum gold values referenced in tasks (for inferability tests — these should
# not appear verbatim in task text).
ENUM_GOLD_VALUES: list[str] = [
    "usd",
    "eur",
    "gbp",
    "duplicate",
    "fraudulent",
    "requested_by_customer",
    "create_prorations",
    "none",
    "always_invoice",
]
