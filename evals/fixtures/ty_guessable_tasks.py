from __future__ import annotations

# Ty2 guessable-constraints pre-registered tasks and constraints.
#
# 30 tasks: 5 per tool × 6 tools — ALL contested, no inert easy tasks.
# Guessable-but-error-prone design: agent's conventional prior is right 40-70%
# of the time, but wrong often enough to measure oracle effect.
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only.
# They must NOT contain enum values, format pattern strings, unit names, or
# "idempotency" keywords. The agent must get the correct value from the SCHEMA.
from dataclasses import dataclass

from agentgauge.tasks import Task


@dataclass
class Constraint:
    """A single correctness constraint on a constructed call argument."""

    param: str
    kind: str  # "enum" | "format" | "range" | "present"
    gold_value: str | None = None  # enum kind: exact expected value (compare with str(actual))
    pattern: str | None = None  # format kind: re.fullmatch pattern
    min_val: int | None = None  # range kind
    max_val: int | None = None  # range kind
    # present kind: just checks param is in constructed_args (non-None)


TASKS: list[Task] = [
    # update_order_status — near-miss enum — 5 tasks
    Task("update_order_status", "Mark order O-1001 as completed and fully paid"),
    Task("update_order_status", "Cancel order O-1002 after the customer changed their mind"),
    Task(
        "update_order_status", "Flag order O-1003 as under investigation by the payment processor"
    ),
    Task("update_order_status", "Indicate that order O-1004 is actively being worked on"),
    Task("update_order_status", "Return order O-1005 to the initial queue while we await approval"),
    # create_support_ticket — near-miss P-notation — 5 tasks
    Task("create_support_ticket", "Open a ticket: production database is completely unavailable"),
    Task(
        "create_support_ticket",
        "Report consistent slow loading on the checkout page for many users",
    ),
    Task("create_support_ticket", "Log a cosmetic bug: button text overflows on small screens"),
    Task("create_support_ticket", "Request a new keyboard shortcut for the power-user dashboard"),
    Task(
        "create_support_ticket",
        "Escalate a security issue: unauthenticated endpoint exposing user IDs",
    ),
    # set_asset_visibility — near-miss enum (unlisted/internal) — 5 tasks
    Task("set_asset_visibility", "Publish the product launch video for all visitors to see"),
    Task("set_asset_visibility", "Share the roadmap exclusively with company employees"),
    Task(
        "set_asset_visibility",
        "Make the beta release notes accessible via direct link without appearing in search",
    ),
    Task(
        "set_asset_visibility",
        "Retire the v1 API docs but keep them readable for existing users",
    ),
    Task(
        "set_asset_visibility",
        "Distribute the conference recording only to people who have the URL",
    ),
    # schedule_callback — RFC3339 + offset — 5 tasks
    Task("schedule_callback", "Book a billing callback for customer C-501 next Monday at 9 AM UTC"),
    Task(
        "schedule_callback",
        "Schedule a product demo for customer C-502 on December 1st at 2 PM UTC",
    ),
    Task(
        "schedule_callback",
        "Arrange a check-in for customer C-503 on January 15th at 10 AM UTC",
    ),
    Task(
        "schedule_callback",
        "Set up a renewal discussion with customer C-504 on the 30th at 3 PM UTC",
    ),
    Task(
        "schedule_callback",
        "Plan a technical review call with customer C-505 next Friday at noon UTC",
    ),
    # set_request_timeout — unit-magnitude ms — 5 tasks
    Task("set_request_timeout", "Set a 5-second request timeout for service api-gateway"),
    Task("set_request_timeout", "Apply a 30-second timeout to service db-proxy"),
    Task("set_request_timeout", "Configure a 1-second response limit for service load-balancer"),
    Task("set_request_timeout", "Use a 10-second query timeout for service auth-svc"),
    Task("set_request_timeout", "Set a 2-second abort threshold for service payment-svc"),
    # charge_customer — commonly-omitted required field — 5 tasks
    Task("charge_customer", "Process a $49.99 monthly subscription charge for cart C-601"),
    Task("charge_customer", "Charge cart C-602 for a one-time setup fee of $199"),
    Task("charge_customer", "Collect a $29.00 add-on payment from cart C-603"),
    Task("charge_customer", "Apply a $99.00 annual renewal charge to cart C-604"),
    Task("charge_customer", "Charge cart C-605 for a $15.00 usage overage fee"),
]

TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # update_order_status — near-miss enum
    # Conventional prior: "completed", "cancelled", "flagged", "active", "waiting"
    # Oracle enum: settled/voided/disputed/processing/pending — agent's synonym is plausible but wrong
    (
        "update_order_status",
        "Mark order O-1001 as completed and fully paid",
    ): [Constraint("status", "enum", gold_value="settled")],
    (
        "update_order_status",
        "Cancel order O-1002 after the customer changed their mind",
    ): [Constraint("status", "enum", gold_value="voided")],
    (
        "update_order_status",
        "Flag order O-1003 as under investigation by the payment processor",
    ): [Constraint("status", "enum", gold_value="disputed")],
    (
        "update_order_status",
        "Indicate that order O-1004 is actively being worked on",
    ): [Constraint("status", "enum", gold_value="processing")],
    (
        "update_order_status",
        "Return order O-1005 to the initial queue while we await approval",
    ): [Constraint("status", "enum", gold_value="pending")],
    # create_support_ticket — near-miss P-notation
    # Conventional prior: "critical/urgent/high", "high/medium", "low/minor", "enhancement"
    # Oracle enum: P1/P2/P3/P4 — IT priority notation, agent may use English words instead
    (
        "create_support_ticket",
        "Open a ticket: production database is completely unavailable",
    ): [Constraint("priority", "enum", gold_value="P1")],
    (
        "create_support_ticket",
        "Report consistent slow loading on the checkout page for many users",
    ): [Constraint("priority", "enum", gold_value="P2")],
    (
        "create_support_ticket",
        "Log a cosmetic bug: button text overflows on small screens",
    ): [Constraint("priority", "enum", gold_value="P3")],
    (
        "create_support_ticket",
        "Request a new keyboard shortcut for the power-user dashboard",
    ): [Constraint("priority", "enum", gold_value="P4")],
    (
        "create_support_ticket",
        "Escalate a security issue: unauthenticated endpoint exposing user IDs",
    ): [Constraint("priority", "enum", gold_value="P1")],
    # set_asset_visibility — near-miss enum
    # Conventional prior: "public" ✓, "private/restricted", "hidden/link-only", "deprecated/removed"
    # Oracle enum: public/internal/unlisted/archived — "internal" and "unlisted" are not first guesses
    (
        "set_asset_visibility",
        "Publish the product launch video for all visitors to see",
    ): [Constraint("visibility", "enum", gold_value="public")],
    (
        "set_asset_visibility",
        "Share the roadmap exclusively with company employees",
    ): [Constraint("visibility", "enum", gold_value="internal")],
    (
        "set_asset_visibility",
        "Make the beta release notes accessible via direct link without appearing in search",
    ): [Constraint("visibility", "enum", gold_value="unlisted")],
    (
        "set_asset_visibility",
        "Retire the v1 API docs but keep them readable for existing users",
    ): [Constraint("visibility", "enum", gold_value="archived")],
    (
        "set_asset_visibility",
        "Distribute the conference recording only to people who have the URL",
    ): [Constraint("visibility", "enum", gold_value="unlisted")],
    # schedule_callback — RFC3339 with timezone offset
    # Arm A: {"type": "string"} — agent often produces naive datetime like "2026-12-01T14:00:00" (no offset)
    # Arm B oracle: format="date-time" + description requiring offset — agent produces "...Z" or "+00:00"
    # Gold: re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)', value)
    (
        "schedule_callback",
        "Book a billing callback for customer C-501 next Monday at 9 AM UTC",
    ): [
        Constraint(
            "scheduled_at",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)",
        )
    ],
    (
        "schedule_callback",
        "Schedule a product demo for customer C-502 on December 1st at 2 PM UTC",
    ): [
        Constraint(
            "scheduled_at",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)",
        )
    ],
    (
        "schedule_callback",
        "Arrange a check-in for customer C-503 on January 15th at 10 AM UTC",
    ): [
        Constraint(
            "scheduled_at",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)",
        )
    ],
    (
        "schedule_callback",
        "Set up a renewal discussion with customer C-504 on the 30th at 3 PM UTC",
    ): [
        Constraint(
            "scheduled_at",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)",
        )
    ],
    (
        "schedule_callback",
        "Plan a technical review call with customer C-505 next Friday at noon UTC",
    ): [
        Constraint(
            "scheduled_at",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)",
        )
    ],
    # set_request_timeout — unit-magnitude (ms)
    # Arm A: {"type": "integer"} no unit hint — agent often uses seconds (5, 30, 1, 10, 2)
    # Arm B oracle: minimum=100, maximum=120000, description says milliseconds explicitly
    # Gold: value in [N*1000 - tolerance, N*1000 + tolerance] — captures ms, rejects seconds
    (
        "set_request_timeout",
        "Set a 5-second request timeout for service api-gateway",
    ): [Constraint("timeout", "range", min_val=4500, max_val=5500)],
    (
        "set_request_timeout",
        "Apply a 30-second timeout to service db-proxy",
    ): [Constraint("timeout", "range", min_val=29000, max_val=31000)],
    (
        "set_request_timeout",
        "Configure a 1-second response limit for service load-balancer",
    ): [Constraint("timeout", "range", min_val=900, max_val=1100)],
    (
        "set_request_timeout",
        "Use a 10-second query timeout for service auth-svc",
    ): [Constraint("timeout", "range", min_val=9500, max_val=10500)],
    (
        "set_request_timeout",
        "Set a 2-second abort threshold for service payment-svc",
    ): [Constraint("timeout", "range", min_val=1900, max_val=2100)],
    # charge_customer — commonly-omitted required field (idempotency_key)
    # Arm A: idempotency_key present in schema as {"type": "string"}, no description
    # Arm B oracle: description explains it's for deduplication — agent includes it with a value
    # Gold: idempotency_key is present in constructed_args (any non-None value)
    (
        "charge_customer",
        "Process a $49.99 monthly subscription charge for cart C-601",
    ): [Constraint("idempotency_key", "present")],
    (
        "charge_customer",
        "Charge cart C-602 for a one-time setup fee of $199",
    ): [Constraint("idempotency_key", "present")],
    (
        "charge_customer",
        "Collect a $29.00 add-on payment from cart C-603",
    ): [Constraint("idempotency_key", "present")],
    (
        "charge_customer",
        "Apply a $99.00 annual renewal charge to cart C-604",
    ): [Constraint("idempotency_key", "present")],
    (
        "charge_customer",
        "Charge cart C-605 for a $15.00 usage overage fee",
    ): [Constraint("idempotency_key", "present")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    [
        "update_order_status",
        "create_support_ticket",
        "set_asset_visibility",
        "schedule_callback",
        "set_request_timeout",
        "charge_customer",
    ]
)

ENUM_TOOL_NAMES: frozenset[str] = frozenset(
    [
        "update_order_status",
        "create_support_ticket",
        "set_asset_visibility",
    ]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["schedule_callback"])
RANGE_TOOL_NAMES: frozenset[str] = frozenset(["set_request_timeout"])
PRESENT_TOOL_NAMES: frozenset[str] = frozenset(["charge_customer"])

# Oracle enum definitions — used in gold-validity CI tests
ORACLE_ENUMS: dict[str, list[str]] = {
    "update_order_status.status": ["pending", "processing", "settled", "voided", "disputed"],
    "create_support_ticket.priority": ["P1", "P2", "P3", "P4"],
    "set_asset_visibility.visibility": ["public", "unlisted", "internal", "archived"],
}

# All enum gold values — used in inferability tests (must not appear in task descriptions)
ENUM_GOLD_VALUES: list[str] = [
    "settled",
    "voided",
    "disputed",
    "processing",
    "pending",
    "P1",
    "P2",
    "P3",
    "P4",
    "public",
    "unlisted",
    "internal",
    "archived",
]

# Format pattern string samples — must not appear verbatim in task descriptions
FORMAT_PATTERN_SAMPLES: list[str] = [
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    "+00:00",
    "RFC3339",
    "RFC 3339",
]

# Unit hint strings — must not appear in timeout task descriptions
UNIT_HINTS: list[str] = ["millisecond", "ms", " ms", "ms "]
