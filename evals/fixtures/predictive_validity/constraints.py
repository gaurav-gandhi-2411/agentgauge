from __future__ import annotations

# Fractional call-correctness constraints for the predictive-validity ground truth.
#
# WHY THIS EXISTS: the study's original ground truth
# (`r.success and r.selected_tool == r.task.tool_name`) is degenerate — every example
# server in this repo accepts any well-formed call (the underlying MCP `call_tool`
# literally never raises across the 442 recorded trials), so `success` is always True
# and the metric collapses to pure tool-name matching. 44% of records tied at exact
# 1.0 (ceiling-compressed). The fix: score success as
# (correct tool selected) x (fraction of argument-correctness constraints satisfied),
# a continuous value in [0, 1], not a binary AND.
#
# This module supplies the "fraction of argument-correctness constraints satisfied"
# half. It does NOT replace blind_tasks.py's task text (additive metadata only) and
# does NOT touch selection — selection correctness is still `selected_tool == tool_name`,
# computed by the caller.
#
# DESIGN: `Constraint` here is a superset of `ty2_tasks.Constraint` (same field names
# plus two new kinds + a `tolerance` field). `constraint_satisfaction` dispatches purely
# on `c.kind` via attribute access (no `isinstance` checks), so it transparently accepts
# both `constraints.Constraint` instances (used for all newly-authored entries below)
# and pre-existing `ty2_tasks.Constraint` instances (reused as-is for
# call_constraints_v2_server/_oracle, per the task brief — those are already
# Constraint-shaped and only need re-keying by manifest entry name, not conversion).
import re
from dataclasses import dataclass
from typing import Any

from evals.fixtures.ty2_tasks import TASK_CONSTRAINTS as _TY2_TASK_CONSTRAINTS
from evals.fixtures.ty_tasks import GOLD_CONSTRAINTS as _TY_GOLD_CONSTRAINTS


@dataclass
class Constraint:
    """A single correctness constraint on a constructed call argument.

    kind="enum": value must equal gold_value exactly (case-sensitive).
    kind="format": re.fullmatch(pattern, str(value)) must not be None.
    kind="range": min_val <= int(value) <= max_val.
    kind="contains": str(value).lower() must contain gold_value.lower() (substring,
        case-insensitive). Added for natural-language tasks whose gold argument is a
        free-text fragment (a search phrase, an identifier embedded in prose, a
        filesystem path) rather than an exact schema-literal token — the 3 original
        kinds only fit tasks like ty_tasks.py's telemetry fixture where the whole
        argument value IS the literal. Known limitation: substring matching can
        false-positive on short/ambiguous gold values (e.g. a bare digit or single
        letter) — such cases are deliberately left unconstrained below rather than
        risking a spurious pass; see per-entry skip notes.
    kind="numeric_equals": abs(float(value) - float(gold_value)) <= tolerance. Added
        for the grounded_server/echo_server math fixtures where tasks state exact
        numbers ("Multiply 4.0 by 2.5 and add 0.5") and float/int comparison needs a
        tolerance rather than exact string equality.
    No "one_of" kind was added — every task encountered during authoring had exactly
    one defensible correct value once the schema was read; where a task's phrasing was
    genuinely compatible with multiple correct arguments, the task was left
    unconstrained (see Part B skip notes below) rather than inventing a kind.
    """

    param: str
    kind: str  # "enum" | "format" | "range" | "contains" | "numeric_equals"
    gold_value: str | None = None
    pattern: str | None = None
    min_val: int | None = None
    max_val: int | None = None
    tolerance: float | None = None  # kind="numeric_equals" only; defaults to 1e-6 if unset


_DEFAULT_NUMERIC_TOLERANCE = 1e-6


def _check_constraint(value: Any, c: Any) -> bool:
    """Evaluate one constraint against a single constructed-call argument value.

    Duck-types on `c.kind`/`c.param`/etc. rather than `isinstance`-checking against
    `Constraint`, so it accepts both this module's `Constraint` and `ty2_tasks.Constraint`
    (which lacks the `tolerance` field — never accessed except in the numeric_equals
    branch, which only this module's authored constraints ever use).
    """
    if value is None:
        return False
    if c.kind == "enum":
        return bool(value == c.gold_value)
    if c.kind == "format":
        return c.pattern is not None and re.fullmatch(c.pattern, str(value)) is not None
    if c.kind == "range":
        try:
            v_int = int(value)
        except (TypeError, ValueError):
            return False
        return c.min_val is not None and c.max_val is not None and c.min_val <= v_int <= c.max_val
    if c.kind == "contains":
        return c.gold_value is not None and c.gold_value.lower() in str(value).lower()
    if c.kind == "numeric_equals":
        try:
            v_float = float(value)
            gold_float = float(c.gold_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        tolerance = (
            c.tolerance if getattr(c, "tolerance", None) is not None else _DEFAULT_NUMERIC_TOLERANCE
        )
        return abs(v_float - gold_float) <= tolerance
    raise ValueError(f"Unknown constraint kind: {c.kind!r}")


def constraint_satisfaction(
    constructed_args: dict[str, Any], constraints: list[Any] | None
) -> float:
    """Fraction of `constraints` satisfied by `constructed_args`, in [0.0, 1.0].

    Returns 1.0 if `constraints` is None or empty (future-proof default, matching the
    convention in `run_ty2_oracle_ab.py`'s `_is_correct_call`: a task with no registered
    constraint is counted as fully correct). Unlike `_is_correct_call`, this is a running
    count divided by len(constraints) — a FRACTION, not a boolean AND — so a call that
    satisfies half its constraints scores 0.5, not 0.0.
    """
    if not constraints:
        return 1.0
    satisfied = sum(1 for c in constraints if _check_constraint(constructed_args.get(c.param), c))
    return satisfied / len(constraints)


# =============================================================================
# Part A continued — reuse of existing constraint sources (no new authoring).
# =============================================================================

# call_constraints_server / call_constraints_server_oracle: convert ty_tasks.py's older
# untyped GOLD_CONSTRAINTS (dict[key, dict[param, str]]) into this module's Constraint
# shape (kind="enum"). Same tool catalog for both arms (only descriptions differ) —
# constraints test argument correctness, a property of the TASK, so the identical dict
# is reused for both manifest keys. ty_tasks.py's own header documents: "Easy tasks are
# not listed — no constrained params; always considered correct" (ping_server,
# get_server_info, list_channels, reset_state — all empty-schema tools) — those 16 of
# 32 tasks per arm correctly fall through to the future-proof 1.0 default, not a skip
# decision made here.
_CALL_CONSTRAINTS_SERVER_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    key: [Constraint(param=p, kind="enum", gold_value=v) for p, v in params.items()]
    for key, params in _TY_GOLD_CONSTRAINTS.items()
}

# call_constraints_v2_server / call_constraints_v2_server_oracle: ty2_tasks.TASK_CONSTRAINTS
# is already Constraint-shaped (format/enum/range) — reused as-is (list[ty2_tasks.Constraint]
# instances, handled transparently by constraint_satisfaction via duck typing), just
# re-keyed by manifest entry name below. Covers all 30/30 tasks for both arms.


# =============================================================================
# Part B — newly-authored constraints for the 16 gap fixtures (14 distinct task lists;
# the 4 t18_* arms and the 2 jupyter-mirror arms each reuse one shared dict).
# =============================================================================

# ── echo_server (examples/echo_server.py) ───────────────────────────────────────
# 8 tasks (echo x2, add x2, mystery x2, greet x2).
# add: deterministic arithmetic (same high-value treatment as grounded_server).
# echo: the exact text to echo back is stated verbatim in the task ("send back the
# exact text 'X' unchanged") — directly derivable, constrained via "contains".
# greet: name (and prefix, when given) are stated verbatim — constrained.
# mystery: task explicitly says "arbitrary"/"unlabeled experimental" probe values —
# no correct value exists by design (any two values are valid); SKIPPED (2 tasks),
# not silently — mystery's own schema has no types/description by design (T-fixture
# schema-completeness floor) and its task text intentionally avoids specifying values.
# Total: 6/8 constrained, 2/8 skipped (mystery x2, no derivable gold value).
_ECHO_SERVER_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "echo",
        "Send back the exact text 'system check 42' unchanged so I can confirm round-trip",
    ): [Constraint("message", "contains", gold_value="system check 42")],
    (
        "echo",
        "Repeat this message back to me exactly as given: 'connectivity probe alpha'",
    ): [Constraint("message", "contains", gold_value="connectivity probe alpha")],
    ("add", "What is 17 plus 26?"): [
        Constraint("a", "numeric_equals", gold_value="17"),
        Constraint("b", "numeric_equals", gold_value="26"),
    ],
    ("add", "Give me the sum of 84 and 39"): [
        Constraint("a", "numeric_equals", gold_value="84"),
        Constraint("b", "numeric_equals", gold_value="39"),
    ],
    ("greet", "Produce a friendly welcome message for a person named 'Priya'"): [
        Constraint("name", "contains", gold_value="Priya")
    ],
    (
        "greet",
        "Generate a custom salutation using 'Hey there' as the opening phrase for a "
        "user named 'Sam'",
    ): [
        Constraint("prefix", "contains", gold_value="Hey there"),
        Constraint("name", "contains", gold_value="Sam"),
    ],
    # SKIPPED: mystery x2 — task text explicitly says "arbitrary"/"unlabeled" probe
    # values; no gold value exists to check against.
}

# ── grounded_server / grounded_server_oracle (examples/grounded_server*.py) ────
# 5 deterministic math tools, every task states exact numbers — high-value fixture,
# every task gets numeric_equals on every stated parameter (10/10 constrained).
# Params confirmed identical between arm A and B (transform_scale{value,factor,offset},
# transform_normalize{value,low,high}, transform_clip{value,lower,upper},
# transform_round{value,places}, transform_log{value,base}) — reused for both entries.
# transform_log tasks only constrain `value`: both tasks either want the default base
# (ln = natural log, base defaults to e) or state the base as part of the task text
# already covered by a separate numeric_equals on `base` where given.
_GROUNDED_SERVER_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    ("transform_scale", "Multiply 4.0 by 2.5 and add 0.5 to the result"): [
        Constraint("value", "numeric_equals", gold_value="4.0"),
        Constraint("factor", "numeric_equals", gold_value="2.5"),
        Constraint("offset", "numeric_equals", gold_value="0.5"),
    ],
    (
        "transform_scale",
        "Apply a 50% amplitude reduction and subtract 3.0 from value 8.0",
    ): [
        Constraint("value", "numeric_equals", gold_value="8.0"),
        Constraint("factor", "numeric_equals", gold_value="0.5"),
        Constraint("offset", "numeric_equals", gold_value="-3.0"),
    ],
    ("transform_normalize", "Express 7.0 as a fraction of the range [0, 10]"): [
        Constraint("value", "numeric_equals", gold_value="7.0"),
        Constraint("low", "numeric_equals", gold_value="0"),
        Constraint("high", "numeric_equals", gold_value="10"),
    ],
    (
        "transform_normalize",
        "Rescale 25.0 to fit between 0 and 1, given original bounds 0 and 50",
    ): [
        Constraint("value", "numeric_equals", gold_value="25.0"),
        Constraint("low", "numeric_equals", gold_value="0"),
        Constraint("high", "numeric_equals", gold_value="50"),
    ],
    ("transform_clip", "Ensure value 105 does not exceed 100 and is at least 0"): [
        Constraint("value", "numeric_equals", gold_value="105"),
        Constraint("lower", "numeric_equals", gold_value="0"),
        Constraint("upper", "numeric_equals", gold_value="100"),
    ],
    (
        "transform_clip",
        "Cap measurement -2.5 so it stays within the valid range [0, 50]",
    ): [
        Constraint("value", "numeric_equals", gold_value="-2.5"),
        Constraint("lower", "numeric_equals", gold_value="0"),
        Constraint("upper", "numeric_equals", gold_value="50"),
    ],
    ("transform_round", "Express 3.14159265 to 4 decimal places"): [
        Constraint("value", "numeric_equals", gold_value="3.14159265"),
        Constraint("places", "numeric_equals", gold_value="4"),
    ],
    ("transform_round", "Reduce precision of 99.9999 to at most 2 decimal places"): [
        Constraint("value", "numeric_equals", gold_value="99.9999"),
        Constraint("places", "numeric_equals", gold_value="2"),
    ],
    ("transform_log", "What is ln(10.0)?"): [
        Constraint("value", "numeric_equals", gold_value="10.0"),
    ],
    ("transform_log", "Compute log base 2 of 8.0"): [
        Constraint("value", "numeric_equals", gold_value="8.0"),
        Constraint("base", "numeric_equals", gold_value="2.0"),
    ],
}

# ── mediocre_server (examples/mediocre_server.py) ───────────────────────────────
# 5 tools, 12 tasks — high-value fixture, all params stated in task text.
# put_x{sid,key,val,ts}: val/ts numeric, key enum (exact record id string), sid numeric.
# get_a/del_a{sid,key=record id}: key enum, sid numeric.
# get_b{sid,key=agg fn in sum/min/max/avg}: key enum (inferred from task intent, task
#   text never says the literal word), sid numeric.
# del_b{sid,key=delete mode in hard/soft}: key enum (inferred), sid numeric.
# put_x task 2 does not state a specific timestamp value ("recording when it was
# captured" — no concrete ts given) — ts left unconstrained for that one task only.
# Total: 12/12 tasks constrained (at least one constraint each).
_MEDIOCRE_SERVER_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "put_x",
        "Store a new sensor measurement of 23.5 recorded at unix time 1700000000 "
        "under record key 'temp-01' in session 42",
    ): [
        Constraint("val", "numeric_equals", gold_value="23.5"),
        Constraint("ts", "numeric_equals", gold_value="1700000000"),
        Constraint("key", "enum", gold_value="temp-01"),
        Constraint("sid", "numeric_equals", gold_value="42"),
    ],
    (
        "put_x",
        "Save a reading of 88.2 for session 7, tagging it with key 'pressure-03' and "
        "recording when it was captured",
    ): [
        Constraint("val", "numeric_equals", gold_value="88.2"),
        Constraint("key", "enum", gold_value="pressure-03"),
        Constraint("sid", "numeric_equals", gold_value="7"),
    ],
    (
        "get_a",
        "Look up the individual measurement stored under record key 'temp-01' in session 42",
    ): [
        Constraint("key", "enum", gold_value="temp-01"),
        Constraint("sid", "numeric_equals", gold_value="42"),
    ],
    (
        "get_a",
        "Retrieve the exact reading that was saved earlier under key 'pressure-03' for session 7",
    ): [
        Constraint("key", "enum", gold_value="pressure-03"),
        Constraint("sid", "numeric_equals", gold_value="7"),
    ],
    ("get_b", "Get the total of every measurement recorded in session 42"): [
        Constraint("key", "enum", gold_value="sum"),
        Constraint("sid", "numeric_equals", gold_value="42"),
    ],
    ("get_b", "Find the smallest measurement value recorded across session 7"): [
        Constraint("key", "enum", gold_value="min"),
        Constraint("sid", "numeric_equals", gold_value="7"),
    ],
    ("get_b", "Find the largest reading recorded in session 42"): [
        Constraint("key", "enum", gold_value="max"),
        Constraint("sid", "numeric_equals", gold_value="42"),
    ],
    ("get_b", "Get the average value across all measurements recorded in session 7"): [
        Constraint("key", "enum", gold_value="avg"),
        Constraint("sid", "numeric_equals", gold_value="7"),
    ],
    (
        "del_a",
        "Remove the single stored record with key 'temp-01' from session 42",
    ): [
        Constraint("key", "enum", gold_value="temp-01"),
        Constraint("sid", "numeric_equals", gold_value="42"),
    ],
    (
        "del_a",
        "Delete just the entry under key 'pressure-03' in session 7, leaving other "
        "records untouched",
    ): [
        Constraint("key", "enum", gold_value="pressure-03"),
        Constraint("sid", "numeric_equals", gold_value="7"),
    ],
    (
        "del_b",
        "Erase all of session 42's records completely, with no way to recover them afterward",
    ): [
        Constraint("key", "enum", gold_value="hard"),
        Constraint("sid", "numeric_equals", gold_value="42"),
    ],
    (
        "del_b",
        "Deactivate session 7's records but keep them recoverable in case they're needed later",
    ): [
        Constraint("key", "enum", gold_value="soft"),
        Constraint("sid", "numeric_equals", gold_value="7"),
    ],
}

# ── confusable_server / confusable_server_oracle (examples/confusable_server*.py) ──
# 16 tools (8 clusters x 2), 32 tasks (reused from t17_tasks.py). Best-effort tier:
# `contains` on the most obviously-implied param, schema-grounded (read directly from
# confusable_server.py). Reused identically for both arms — same tool catalog and
# param schemas confirmed identical between arm A/B, only descriptions differ.
#
# Per-cluster skip notes (documented, not silent):
# - C4 register_user (both tasks): task text describes an onboarding *intent* but
#   states no concrete email/password value — SKIPPED (2 tasks).
# - C5 update_record ("Overwrite the product record with the fully corrected
#   version"): no record id stated — SKIPPED (1 task). patch_fields tasks keep
#   `fields` constraints but the id is only stated for the first (order #882).
# - C6 delete_record / archive_record (all 4 tasks): none of the 4 tasks states a
#   concrete record id ("a user account", "a duplicate product entry", "an old
#   campaign", "a user's access") — genuinely no derivable `id` — SKIPPED (4 tasks).
# - C8 extract_data ("Get the underlying data so I can run my own aggregations on
#   it"): no specific dataset name stated — SKIPPED (1 task).
# - C1 query_records ("Retrieve customers from the enterprise tier"): `value` is
#   derivable ("enterprise") but the real `field` name is not stated by the task and
#   is ambiguous (could be "tier", "customer_tier", "plan", "segment") — `field` left
#   unconstrained for this one task, `value` still constrained.
# Total: 24/32 constrained, 8/32 skipped.
_CONFUSABLE_SERVER_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    ("search_documents", "Find all documents that mention the word 'overdue'"): [
        Constraint("query", "contains", gold_value="overdue")
    ],
    (
        "search_documents",
        "Locate entries whose content includes the phrase 'budget exceeded'",
    ): [Constraint("query", "contains", gold_value="budget exceeded")],
    (
        "query_records",
        "Get all orders where the status field is set to 'pending'",
    ): [
        Constraint("field", "contains", gold_value="status"),
        Constraint("value", "contains", gold_value="pending"),
    ],
    ("query_records", "Retrieve customers from the enterprise tier"): [
        Constraint("value", "contains", gold_value="enterprise")
    ],
    ("send_message", "Tell user #102 that their subscription renewal went through"): [
        Constraint("user_id", "contains", gold_value="102")
    ],
    (
        "send_message",
        "Let the customer with ID 55 know their refund has been approved",
    ): [Constraint("user_id", "contains", gold_value="55")],
    (
        "dispatch_event",
        "Trigger the fulfillment pipeline after a new order is placed",
    ): [Constraint("event_type", "contains", gold_value="order")],
    (
        "dispatch_event",
        "Signal downstream services that a batch upload has finished",
    ): [Constraint("event_type", "contains", gold_value="upload")],
    (
        "list_items",
        "Show me the third page of results with 10 items per page",
    ): [
        Constraint("offset", "numeric_equals", gold_value="20"),
        Constraint("limit", "numeric_equals", gold_value="10"),
    ],
    ("list_items", "Get items 21 through 40 from the product catalog"): [
        Constraint("offset", "numeric_equals", gold_value="20"),
        Constraint("limit", "numeric_equals", gold_value="20"),
    ],
    (
        "enumerate_all",
        "Retrieve every country code available for the address form dropdown",
    ): [Constraint("collection", "contains", gold_value="country")],
    (
        "enumerate_all",
        "Pull the complete list of supported currencies for the settings page",
    ): [Constraint("collection", "contains", gold_value="currenc")],
    ("create_record", "Add a new product to the catalog with its price and SKU"): [
        Constraint("type", "contains", gold_value="product")
    ],
    (
        "create_record",
        "Store a new support ticket with a subject and description",
    ): [Constraint("type", "contains", gold_value="ticket")],
    # SKIPPED: register_user x2 — intent described, no concrete email/password stated.
    (
        "update_record",
        "Replace the full configuration of project #3 with a new complete spec",
    ): [Constraint("id", "contains", gold_value="3")],
    # SKIPPED: update_record "Overwrite the product record with the fully corrected
    # version" — no record id stated.
    (
        "patch_fields",
        "Change only the shipping address on order #882 without touching other fields",
    ): [
        Constraint("id", "contains", gold_value="882"),
        Constraint("fields", "contains", gold_value="address"),
    ],
    (
        "patch_fields",
        "Update just the expiry date on a credential, leaving everything else alone",
    ): [Constraint("fields", "contains", gold_value="expiry")],
    # SKIPPED: delete_record x2, archive_record x2 — none of the 4 tasks states a
    # concrete record id.
    ("get_record", "Pull up the order whose ID is ord-77231"): [
        Constraint("id", "contains", gold_value="ord-77231")
    ],
    ("get_record", "Look up the user profile with identifier usr-00991"): [
        Constraint("id", "contains", gold_value="usr-00991")
    ],
    ("fetch_latest", "Get whichever log entry was written most recently"): [
        Constraint("type", "contains", gold_value="log")
    ],
    ("fetch_latest", "Show me the last notification that came in"): [
        Constraint("type", "contains", gold_value="notification")
    ],
    (
        "export_report",
        "Produce a PDF summary of last month's invoices for the accounting team",
    ): [
        Constraint("format", "enum", gold_value="pdf"),
        Constraint("dataset", "contains", gold_value="invoice"),
    ],
    (
        "export_report",
        "Generate a CSV file of all active users for an external audit",
    ): [
        Constraint("format", "enum", gold_value="csv"),
        Constraint("dataset", "contains", gold_value="user"),
    ],
    (
        "extract_data",
        "Pull the raw transaction records as structured data for my ETL script",
    ): [Constraint("dataset", "contains", gold_value="transaction")],
    # SKIPPED: extract_data "Get the underlying data so I can run my own aggregations
    # on it" — no specific dataset name stated.
}

# ── t18_vague_server / t18_fixer_server / t18_q2b_server / t18_oracle_server ────
# All 4 arms share the identical 12-tool, single-param schema
# ({"query": {"type": "string"}}) and identical T18_SUBSET_TASKS task list (confirmed:
# t18_vague_server.py, t18_fixer_server.py, t18_q2b_server.py, t18_oracle_server.py all
# define _SCHEMA = {"query": string} — verified by direct grep). One dict, reused for
# all 4 manifest keys.
#
# Constraint design: the entire task's identifying value (an order id, filename, event
# name, service name) becomes a `contains` check on the single `query` param.
#
# Skipped (6 of 24 tasks) — no concrete identifier stated in task text, only a
# described intent with no derivable specific value:
#   load_item "checkout flow needs the cart contents for the active session..." (x1,
#     catalog-sourced) and load_item "recommendation engine needs the last-viewed
#     items..." (x1, gap-sourced) — both describe "current session" with no id.
#   alert_contact "Dispatch an urgent text message to the on-call engineer's mobile
#     number" and alert_contact "Send an urgent text alert to the on-site
#     technician's registered phone number about the outage" — no phone number/contact
#     id stated in either.
#   send_notification "Push a pop-up reminder to the user's phone for their upcoming
#     appointment" and send_notification "Push a mobile alert to the user's phone
#     letting them know their ride has arrived" — no user id stated in either.
# Total: 18/24 constrained, 6/24 skipped, applied identically across all 4 arms.
_T18_QUERY_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "get_record",
        "The inventory service needs the warehouse product with item_id=9812 from the primary database.",
    ): [Constraint("query", "contains", gold_value="9812")],
    (
        "fetch_record",
        "Retrieve order status for #TX-991 by calling the fulfilment partner's external HTTP endpoint.",
    ): [Constraint("query", "contains", gold_value="TX-991")],
    (
        "read_entry",
        "The startup routine needs the server's settings from disk at /etc/app/settings.ini.",
    ): [Constraint("query", "contains", gold_value="settings.ini")],
    # SKIPPED: load_item "The checkout flow needs the cart contents for the active
    # session without touching the database." — no session/cart id stated.
    (
        "notify_user",
        "Show an alert inside the application interface to user_id=1002.",
    ): [Constraint("query", "contains", gold_value="1002")],
    # SKIPPED: alert_contact "Dispatch an urgent text message to the on-call
    # engineer's mobile number." — no phone number/contact id stated.
    # SKIPPED: send_notification "Push a pop-up reminder to the user's phone for
    # their upcoming appointment." — no user id stated.
    (
        "trigger_event",
        "Fire the 'order_shipped' signal into the event log so handlers can react.",
    ): [Constraint("query", "contains", gold_value="order_shipped")],
    (
        "get_record",
        "The billing service needs account ACCT-4471's data fetched straight from "
        "the primary datastore using its unique key",
    ): [Constraint("query", "contains", gold_value="ACCT-4471")],
    (
        "fetch_record",
        "Pull the shipping status for order #55219 by calling the courier partner's remote web API",
    ): [Constraint("query", "contains", gold_value="55219")],
    (
        "read_entry",
        "The deployment script needs the feature-flags entry from the local config "
        "file at /opt/app/flags.yaml",
    ): [Constraint("query", "contains", gold_value="flags.yaml")],
    # SKIPPED: load_item "The recommendation engine needs the last-viewed items list
    # for this browser session, served instantly without a database round-trip" —
    # no item/session id stated.
    (
        "retrieve_row",
        "Pull the customer row from the accounts SQL table where email equals 'j.doe@example.com'",
    ): [Constraint("query", "contains", gold_value="j.doe@example.com")],
    (
        "retrieve_row",
        "Get the shipment row from the logistics table whose tracking_number is 'TRK-88213'",
    ): [Constraint("query", "contains", gold_value="TRK-88213")],
    (
        "pull_document",
        "Fetch the user profile document stored in the document-store collection "
        "for user_id 'u-7734'",
    ): [Constraint("query", "contains", gold_value="u-7734")],
    (
        "pull_document",
        "Retrieve the product listing document from the catalog collection by its "
        "document id 'doc-2291'",
    ): [Constraint("query", "contains", gold_value="doc-2291")],
    (
        "notify_user",
        "Show a reminder banner inside the app for the user with account number "
        "8834 about their expiring trial",
    ): [Constraint("query", "contains", gold_value="8834")],
    # SKIPPED: alert_contact "Send an urgent text alert to the on-site technician's
    # registered phone number about the outage" — no contact id stated.
    # SKIPPED: send_notification "Push a mobile alert to the user's phone letting
    # them know their ride has arrived" — no user id stated.
    (
        "trigger_event",
        "Record the 'payment_failed' occurrence in the internal event log so other "
        "services can react",
    ): [Constraint("query", "contains", gold_value="payment_failed")],
    (
        "broadcast_message",
        "Send the same announcement simultaneously to everyone currently subscribed "
        "to the #incidents channel",
    ): [Constraint("query", "contains", gold_value="incidents")],
    (
        "broadcast_message",
        "Blast a maintenance-window notice out to every subscriber of the "
        "status-updates channel at once",
    ): [Constraint("query", "contains", gold_value="status-updates")],
    (
        "ping_service",
        "Check whether the billing microservice's health endpoint is currently responding",
    ): [Constraint("query", "contains", gold_value="billing")],
    (
        "ping_service",
        "Verify that the downstream inventory service is up and reachable right now",
    ): [Constraint("query", "contains", gold_value="inventory")],
}

# ── exp1_datalayer_jupyter_mcp_server_mirror / _oracle ──────────────────────────
# 17 tools, 34 tasks. Real-world mirror, best-effort tier — schemas were fully
# derivable (TOOL_SCHEMAS read directly from the mirror file) so coverage ended up
# fairly thorough. Params identical between arm/oracle (verified: TOOL_SCHEMAS dict
# byte-identical via diff) — one dict reused for both manifest keys.
#
# Skipped (8/34 tasks), documented:
#   list_files x2 — task text never states a path/pattern value ("every file...",
#     "locate a specific dataset file" — no filename given).
#   list_kernels x2 — tool has zero schema properties (empty TOOL_SCHEMAS entry).
#   list_notebooks x2 — same, zero schema properties.
#   read_notebook x2 — both tasks refer to "the currently active notebook" generically,
#     no specific notebook_name stated.
# Ambiguous sub-values also deliberately left unconstrained rather than guessed:
#   insert_cell task 2's cell_index ("right after the second cell" — off-by-one
#     ambiguous), move_cell task 2's target_index ("becomes the very first cell" —
#     0-indexed vs 1-indexed ambiguous), execute_cell task 2's timeout ("generous
#     timeout" has no numeric value), connect_to_jupyter task 2's jupyter_token (task
#     says "requires no authentication token" — not a positive value to check).
# Total: 26/34 constrained, 8/34 skipped.
_JUPYTER_MIRROR_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # SKIPPED: list_files x2 — no path/pattern value stated.
    # SKIPPED: list_kernels x2 — zero schema properties.
    (
        "use_notebook",
        "Set 'analysis.ipynb' at path /work/analysis.ipynb as the active notebook "
        "for the cell operations I'm about to do",
    ): [
        Constraint("notebook_name", "contains", gold_value="analysis.ipynb"),
        Constraint("notebook_path", "contains", gold_value="/work/analysis.ipynb"),
    ],
    (
        "use_notebook",
        "Switch my working context over to the notebook called 'report_gen' so I "
        "can start editing its cells",
    ): [Constraint("notebook_name", "contains", gold_value="report_gen")],
    # SKIPPED: list_notebooks x2 — zero schema properties.
    (
        "restart_notebook",
        "The kernel for 'training_run.ipynb' seems stuck — restart it",
    ): [Constraint("notebook_name", "contains", gold_value="training_run.ipynb")],
    (
        "restart_notebook",
        "Reboot the kernel backing the 'etl_pipeline' notebook so I can start fresh",
    ): [Constraint("notebook_name", "contains", gold_value="etl_pipeline")],
    (
        "unuse_notebook",
        "I'm done working with 'scratch.ipynb' for now — release it and free up its resources",
    ): [Constraint("notebook_name", "contains", gold_value="scratch.ipynb")],
    (
        "unuse_notebook",
        "Deactivate the 'old_experiment' notebook I was using so it stops holding onto memory",
    ): [Constraint("notebook_name", "contains", gold_value="old_experiment")],
    # SKIPPED: read_notebook x2 — refers to "currently active notebook" generically.
    (
        "insert_cell",
        "Add a new markdown cell at position 3 in the currently active notebook "
        "with a section header",
    ): [
        Constraint("cell_index", "contains", gold_value="3"),
        Constraint("cell_type", "contains", gold_value="markdown"),
    ],
    (
        "insert_cell",
        "Insert a fresh empty code cell right after the second cell in the current notebook",
    ): [Constraint("cell_type", "contains", gold_value="code")],
    (
        "overwrite_cell_source",
        "Completely rewrite cell 5 in the active notebook to import pandas and "
        "load a CSV instead of what's there now",
    ): [
        Constraint("cell_index", "contains", gold_value="5"),
        Constraint("cell_source", "contains", gold_value="pandas"),
    ],
    (
        "overwrite_cell_source",
        "Replace the whole contents of cell 2 with a fresh implementation of the training loop",
    ): [Constraint("cell_index", "contains", gold_value="2")],
    (
        "edit_cell_source",
        "In cell 4 of the active notebook, change every occurrence of the variable "
        "name 'df_old' to 'df_new' without touching anything else",
    ): [
        Constraint("cell_index", "contains", gold_value="4"),
        Constraint("old_string", "contains", gold_value="df_old"),
        Constraint("new_string", "contains", gold_value="df_new"),
    ],
    (
        "edit_cell_source",
        "Find the string 'learning_rate=0.01' in cell 7 and swap it for "
        "'learning_rate=0.001', leaving the rest of the cell untouched",
    ): [
        Constraint("cell_index", "contains", gold_value="7"),
        Constraint("old_string", "contains", gold_value="learning_rate=0.01"),
        Constraint("new_string", "contains", gold_value="learning_rate=0.001"),
    ],
    (
        "execute_cell",
        "Run cell 6 in the currently active notebook and show me its output",
    ): [Constraint("cell_index", "contains", gold_value="6")],
    (
        "execute_cell",
        "Execute the cell at index 3 with a generous timeout since it trains a model",
    ): [Constraint("cell_index", "contains", gold_value="3")],
    (
        "insert_execute_code_cell",
        "Add a new code cell at the end of the notebook that prints the "
        "dataframe's shape, and run it immediately",
    ): [Constraint("cell_source", "contains", gold_value="shape")],
    (
        "insert_execute_code_cell",
        "Insert a quick cell at position 2 that imports numpy, and run it right "
        "away so I can use it in later cells",
    ): [
        Constraint("cell_index", "contains", gold_value="2"),
        Constraint("cell_source", "contains", gold_value="numpy"),
    ],
    (
        "read_cell",
        "Show me the source code and any output from cell 8 in the currently active notebook",
    ): [Constraint("cell_index", "contains", gold_value="8")],
    (
        "read_cell",
        "What's currently in cell 1 of the open notebook, including its execution count?",
    ): [Constraint("cell_index", "contains", gold_value="1")],
    (
        "delete_cell",
        "Remove cell 9 from the active notebook and show me what was in it before it's gone",
    ): [Constraint("cell_indices", "contains", gold_value="9")],
    ("delete_cell", "Delete cells 2 and 3 from the currently open notebook"): [
        Constraint("cell_indices", "contains", gold_value="2"),
        Constraint("cell_indices", "contains", gold_value="3"),
    ],
    (
        "move_cell",
        "Move the cell currently at position 1 down to position 4 in the active "
        "notebook, shifting the others up",
    ): [
        Constraint("source_index", "contains", gold_value="1"),
        Constraint("target_index", "contains", gold_value="4"),
    ],
    (
        "move_cell",
        "Relocate the cell at index 5 so it becomes the very first cell in the notebook",
    ): [Constraint("source_index", "contains", gold_value="5")],
    (
        "execute_code",
        "Quickly run `df.head()` in the active notebook's kernel just to peek at "
        "the data, without adding a cell to the notebook",
    ): [Constraint("code", "contains", gold_value="df.head()")],
    (
        "execute_code",
        "Install the 'seaborn' package into the current kernel with a one-off "
        "command, without saving anything to the notebook",
    ): [Constraint("code", "contains", gold_value="seaborn")],
    (
        "connect_to_jupyter",
        "Point this session at a different Jupyter server running at "
        "http://localhost:8890 using the access token 'xyz789'",
    ): [
        Constraint("jupyter_url", "contains", gold_value="localhost:8890"),
        Constraint("jupyter_token", "contains", gold_value="xyz789"),
    ],
    (
        "connect_to_jupyter",
        "Switch over to a freshly started Jupyter instance on port 8888 that "
        "requires no authentication token",
    ): [Constraint("jupyter_url", "contains", gold_value="8888")],
}

# ── exp1_blazickjp_arxiv_mcp_server_mirror ───────────────────────────────────────
# 8 tools, 16 tasks. SKIPPED IN FULL (0/16 constrained) — every one of the 8 tools'
# TOOL_SCHEMAS entries in exp1_blazickjp_arxiv_mcp_server_mirror.py is
# {"type": "object", "properties": {}, "required": []} (confirmed by direct read):
# the mirror's schema-extraction pass produced no parameter placeholders for this
# server at all, so there is no argument to constrain regardless of how specific the
# task text is (e.g. "arXiv paper 2301.12345" has an obviously-derivable gold value,
# but no schema property exists to hold it). Left as an empty dict — all 16 tasks
# correctly fall through to the future-proof 1.0 default.
_ARXIV_MIRROR_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {}

# ── exp1_stickerdaniel_linkedin_mcp_server_mirror ────────────────────────────────
# 17 tools, 34 tasks. Real-world mirror, best-effort tier.
#
# Skipped (6/34 tasks), documented:
#   close_session x2 — zero schema properties.
#   get_feed "Pull up what's currently showing on my personal LinkedIn feed" — no
#     post count stated (task 1 for this tool does state "15" and is constrained).
#   get_inbox x2 — neither task states a conversation count.
#   get_my_profile "Pull up my personal LinkedIn profile page as it currently
#     stands" — no extra sections requested (task 1 for this tool does name
#     "experience"/"skills" and is constrained).
# One ambiguous value deliberately left unconstrained: search_people task 1's
# `network` filter ("first-degree connections" -> docstring says the encoding is
# "F") was NOT constrained — a single-character gold value under a `contains` check
# is too prone to spurious substring matches (e.g. any answer containing the letter
# "f" would false-positive-pass) to be a reliable signal; `keywords` is still
# constrained for that task.
# Total: 28/34 constrained, 6/34 skipped.
_LINKEDIN_MIRROR_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # SKIPPED: close_session x2 — zero schema properties.
    (
        "get_company_profile",
        "Pull up Docker's LinkedIn company page, including their recent job postings",
    ): [
        Constraint("company_name", "contains", gold_value="docker"),
        Constraint("sections", "contains", gold_value="jobs"),
    ],
    (
        "get_company_profile",
        "Get Anthropic's LinkedIn company overview along with their recent posts",
    ): [
        Constraint("company_name", "contains", gold_value="anthropic"),
        Constraint("sections", "contains", gold_value="posts"),
    ],
    (
        "get_company_posts",
        "Show me the most recent posts published on Microsoft's LinkedIn company feed",
    ): [Constraint("company_name", "contains", gold_value="microsoft")],
    (
        "get_company_posts",
        "What has the company Anthropic posted recently on their LinkedIn feed?",
    ): [Constraint("company_name", "contains", gold_value="anthropic")],
    ("search_companies", "Find LinkedIn companies related to the fintech industry"): [
        Constraint("keywords", "contains", gold_value="fintech")
    ],
    (
        "search_companies",
        "Search LinkedIn for companies working in electric vehicles",
    ): [Constraint("keywords", "contains", gold_value="electric vehicles")],
    (
        "get_company_employees",
        "Show me the people who work at Docker on LinkedIn, along with where "
        "they're based and what they studied",
    ): [Constraint("company_name", "contains", gold_value="docker")],
    (
        "get_company_employees",
        "Get the employee roster and team-function breakdown for the company at "
        "the 'anthropicresearch' LinkedIn page",
    ): [Constraint("company_name", "contains", gold_value="anthropicresearch")],
    ("get_feed", "Show me the latest 15 posts from my own LinkedIn home feed"): [
        Constraint("num_posts", "contains", gold_value="15")
    ],
    # SKIPPED: get_feed "Pull up what's currently showing on my personal LinkedIn
    # feed" — no post count stated.
    (
        "get_job_details",
        "Get the full details for the LinkedIn job posting with ID 4252026496",
    ): [Constraint("job_id", "contains", gold_value="4252026496")],
    ("get_job_details", "Show me everything about job listing 3856789012 on LinkedIn"): [
        Constraint("job_id", "contains", gold_value="3856789012")
    ],
    (
        "search_jobs",
        "Find remote software engineer job postings on LinkedIn located anywhere",
    ): [
        Constraint("keywords", "contains", gold_value="software engineer"),
        Constraint("work_type", "contains", gold_value="remote"),
    ],
    (
        "search_jobs",
        "Look for data scientist openings on LinkedIn based in San Francisco",
    ): [
        Constraint("keywords", "contains", gold_value="data scientist"),
        Constraint("location", "contains", gold_value="San Francisco"),
    ],
    # SKIPPED: get_inbox x2 — neither task states a conversation count.
    (
        "get_conversation",
        "Open my LinkedIn message thread with the user 'williamhgates' and show me what was said",
    ): [Constraint("linkedin_username", "contains", gold_value="williamhgates")],
    (
        "get_conversation",
        "Show me the contents of LinkedIn message thread ID 'thr-88213'",
    ): [Constraint("thread_id", "contains", gold_value="thr-88213")],
    (
        "search_conversations",
        "Search through my LinkedIn messages for any conversation mentioning 'contract renewal'",
    ): [Constraint("keywords", "contains", gold_value="contract renewal")],
    (
        "search_conversations",
        "Find any LinkedIn conversations in my inbox that mention 'interview scheduling'",
    ): [Constraint("keywords", "contains", gold_value="interview scheduling")],
    (
        "send_message",
        "Send a LinkedIn message to 'stickerdaniel' saying 'Great meeting you at "
        "the conference!' and confirm it actually goes out",
    ): [
        Constraint("linkedin_username", "contains", gold_value="stickerdaniel"),
        Constraint("message", "contains", gold_value="Great meeting you at the conference"),
        Constraint("confirm_send", "contains", gold_value="true"),
    ],
    (
        "send_message",
        "Message the LinkedIn user 'williamhgates' with 'Following up on our "
        "conversation' and make sure it's actually delivered, not just drafted",
    ): [
        Constraint("linkedin_username", "contains", gold_value="williamhgates"),
        Constraint("message", "contains", gold_value="Following up on our conversation"),
        Constraint("confirm_send", "contains", gold_value="true"),
    ],
    (
        "get_person_profile",
        "Pull up the LinkedIn profile for the user 'stickerdaniel', including "
        "their work experience and education history",
    ): [
        Constraint("linkedin_username", "contains", gold_value="stickerdaniel"),
        Constraint("sections", "contains", gold_value="experience"),
        Constraint("sections", "contains", gold_value="education"),
    ],
    (
        "get_person_profile",
        "Show me williamhgates' LinkedIn profile along with their certifications and skills",
    ): [
        Constraint("linkedin_username", "contains", gold_value="williamhgates"),
        Constraint("sections", "contains", gold_value="certifications"),
        Constraint("sections", "contains", gold_value="skills"),
    ],
    (
        "search_people",
        "Find LinkedIn users with the title 'software engineer' who are "
        "first-degree connections of mine",
    ): [Constraint("keywords", "contains", gold_value="software engineer")],
    ("search_people", "Search LinkedIn for recruiters at Google"): [
        Constraint("keywords", "contains", gold_value="recruiter")
    ],
    (
        "connect_with_person",
        "Send a LinkedIn connection invite to 'stickerdaniel' with a short personal note",
    ): [Constraint("linkedin_username", "contains", gold_value="stickerdaniel")],
    (
        "connect_with_person",
        "Accept the incoming LinkedIn connection request from 'williamhgates'",
    ): [Constraint("linkedin_username", "contains", gold_value="williamhgates")],
    (
        "get_sidebar_profiles",
        "Show me the 'People you may know' and similar suggested-profile links "
        "from stickerdaniel's LinkedIn page",
    ): [Constraint("linkedin_username", "contains", gold_value="stickerdaniel")],
    (
        "get_sidebar_profiles",
        "Get the recommended-profiles sidebar links shown on williamhgates' LinkedIn page",
    ): [Constraint("linkedin_username", "contains", gold_value="williamhgates")],
    (
        "get_my_profile",
        "Show me my own LinkedIn profile, including my work experience and skills sections",
    ): [
        Constraint("sections", "contains", gold_value="experience"),
        Constraint("sections", "contains", gold_value="skills"),
    ],
    # SKIPPED: get_my_profile "Pull up my personal LinkedIn profile page as it
    # currently stands" — no extra sections requested.
}


# =============================================================================
# Part C — 22 new manifest entries (18 -> 40 expansion). Same discipline as Part B:
# "contains" is used almost everywhere (robust to int/str/bool argument types, since
# it stringifies before matching — see _check_constraint), reserving "numeric_equals"
# only for tasks stating an exact number and "enum" only for a truly closed-vocabulary
# field. Tasks with no concrete, unambiguous literal in their text are left
# unconstrained (documented SKIPPED, not silently), same as Part B.
# =============================================================================

# ── rw1_github_mirror / rw1_arm_a / rw1_arm_guardb / rw1_arm_oracle ─────────────
# 21 tasks, all 4 arms share the identical 21-tool catalog and schemas (only served
# descriptions differ) — one dict reused for all 4 manifest keys. Nearly every task
# states owner/repo/id literals explicitly (RW1's tasks were written that way in
# rw1_github_catalog.py) — high constrainability, no skips.
_RW1_GITHUB_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "get_pull_request",
        "Show me the title, description, and whether PR #142 in acme-corp/backend-api "
        "has been merged or is still open.",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("pullNumber", "contains", gold_value="142"),
    ],
    (
        "get_pull_request_diff",
        "Show the exact code changes line by line introduced by PR #142 in acme-corp/backend-api.",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("pullNumber", "contains", gold_value="142"),
    ],
    (
        "get_pull_request_files",
        "Which files did PR #142 in acme-corp/backend-api touch, and how many lines "
        "were added or removed in each file?",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("pullNumber", "contains", gold_value="142"),
    ],
    (
        "get_pull_request_reviews",
        "Has anyone approved or requested changes on PR #142 in acme-corp/backend-api?",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("pullNumber", "contains", gold_value="142"),
    ],
    (
        "get_pull_request_comments",
        "What inline comments have reviewers left on specific lines of code "
        "in PR #142 of acme-corp/backend-api?",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("pullNumber", "contains", gold_value="142"),
    ],
    (
        "merge_pull_request",
        "Squash-merge PR #142 into main in acme-corp/backend-api.",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("pullNumber", "contains", gold_value="142"),
        Constraint("mergeMethod", "enum", gold_value="squash"),
    ],
    (
        "search_repositories",
        "Find public GitHub repositories related to transformer-based language models.",
    ): [Constraint("query", "contains", gold_value="transformer")],
    (
        "search_code",
        "Find all places in GitHub where the Python function calculate_discount is defined.",
    ): [Constraint("query", "contains", gold_value="calculate_discount")],
    (
        "search_issues",
        "Search for open GitHub issues mentioning 'null pointer exception' in the last month.",
    ): [Constraint("query", "contains", gold_value="null pointer exception")],
    (
        "search_users",
        "Find GitHub users named Alex Chen who work at data science companies.",
    ): [Constraint("query", "contains", gold_value="Alex Chen")],
    (
        "get_file_contents",
        "Read the current content of src/config/database.yaml from the main branch "
        "of acme-corp/backend-api.",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("path", "contains", gold_value="src/config/database.yaml"),
    ],
    (
        "create_or_update_file",
        "Update docs/changelog.md in acme-corp/backend-api on the docs branch with "
        "the v2.1 release notes; commit message should be 'docs: add v2.1 changelog'.",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("path", "contains", gold_value="docs/changelog.md"),
        Constraint("message", "contains", gold_value="docs: add v2.1 changelog"),
    ],
    (
        "push_files",
        "Push three updated files to the feature/auth branch of acme-corp/backend-api "
        "in a single commit: app/auth.py, app/tokens.py, and tests/test_auth.py.",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("branch", "contains", gold_value="feature/auth"),
    ],
    (
        "list_pull_requests",
        "Show all open pull requests targeting the main branch of acme-corp/backend-api.",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("base", "contains", gold_value="main"),
    ],
    (
        "list_issues",
        "What open issues in acme-corp/backend-api are currently labeled 'bug'?",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
        Constraint("labels", "contains", gold_value="bug"),
    ],
    (
        "list_commits",
        "Show the ten most recent commits on the main branch of acme-corp/backend-api.",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
    ],
    (
        "list_branches",
        "What branches exist in the acme-corp/backend-api repository right now?",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
    ],
    (
        "get_repository",
        "What is the default branch and visibility setting of the acme-corp/backend-api "
        "repository?",
    ): [
        Constraint("owner", "contains", gold_value="acme-corp"),
        Constraint("repo", "contains", gold_value="backend-api"),
    ],
    (
        "list_repositories",
        "What repositories does the GitHub user jsmith currently have?",
    ): [Constraint("username", "contains", gold_value="jsmith")],
    (
        "create_repository",
        "Create a new private repository named data-pipeline under the acme-corp organization.",
    ): [
        Constraint("name", "contains", gold_value="data-pipeline"),
        Constraint("private", "contains", gold_value="true"),
        Constraint("org", "contains", gold_value="acme-corp"),
    ],
    (
        "fork_repository",
        "Fork the tensorflow/tensorflow repository into the acme-corp organization.",
    ): [
        Constraint("owner", "contains", gold_value="tensorflow"),
        Constraint("repo", "contains", gold_value="tensorflow"),
        Constraint("organization", "contains", gold_value="acme-corp"),
    ],
}

# ── rw2_aws_iam_mirror / rw2_arm_a / rw2_arm_guardb ─────────────────────────────
# 29 tasks, all 3 arms share the identical 29-tool catalog and schemas.
# Skipped (3/29): list_users, list_groups, list_roles — no concrete filter value
# stated in the task text (each task asks for the entire unfiltered listing).
_RW2_AWS_IAM_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "attach_user_policy",
        "The deploy service account (a user, not a group) needs read-only S3 access. "
        "Apply the managed policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess to "
        "that individual account.",
    ): [Constraint("policy_arn", "contains", gold_value="AmazonS3ReadOnlyAccess")],
    (
        "attach_group_policy",
        "All members of the data-team group need read-only S3 access. Apply the managed "
        "policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess to the group so every "
        "member inherits it.",
    ): [Constraint("policy_arn", "contains", gold_value="AmazonS3ReadOnlyAccess")],
    (
        "detach_user_policy",
        "The billing managed policy (arn:aws:iam::aws:policy/Billing) was mistakenly "
        "assigned directly to the finance service account (an individual user). "
        "Remove it from that user account without deleting the policy itself.",
    ): [Constraint("policy_arn", "contains", gold_value="Billing")],
    (
        "detach_group_policy",
        "The billing managed policy (arn:aws:iam::aws:policy/Billing) was mistakenly "
        "assigned to the finance IAM group. Remove it from the group without deleting "
        "the policy itself.",
    ): [Constraint("policy_arn", "contains", gold_value="Billing")],
    (
        "list_policies",
        "Show me what managed IAM policies (both AWS-managed and customer-managed) "
        "exist in the account at the account level, regardless of whether they're "
        "attached to anyone.",
    ): [Constraint("scope", "contains", gold_value="all")],
    (
        "list_user_policies",
        "What inline policies are embedded directly inside the deploy-bot service "
        "account (a user)? I need the policy names, not the managed ones.",
    ): [Constraint("user_name", "contains", gold_value="deploy-bot")],
    (
        "list_role_policies",
        "What inline policies are embedded directly inside the ec2-reader execution "
        "role? Give me their names.",
    ): [Constraint("role_name", "contains", gold_value="ec2-reader")],
    # SKIPPED: list_users — no filter value stated (full unfiltered listing requested).
    # SKIPPED: list_groups — no filter value stated.
    # SKIPPED: list_roles — no filter value stated.
    (
        "delete_user_policy",
        "Permanently remove the legacy-access inline policy from the audit-bot "
        "service account (a user). This inline policy is no longer needed and "
        "should be destroyed.",
    ): [
        Constraint("policy_name", "contains", gold_value="legacy-access"),
        Constraint("user_name", "contains", gold_value="audit-bot"),
    ],
    (
        "delete_role_policy",
        "Permanently remove the legacy-access inline policy from the ec2-scanner "
        "execution role. This inline policy is no longer needed and should be "
        "destroyed.",
    ): [
        Constraint("policy_name", "contains", gold_value="legacy-access"),
        Constraint("role_name", "contains", gold_value="ec2-scanner"),
    ],
    (
        "create_user",
        "Create a new IAM user account named pagerduty-bot for the on-call automation service.",
    ): [Constraint("user_name", "contains", gold_value="pagerduty-bot")],
    (
        "get_user",
        "What groups, attached policies, and access keys does the deploy-bot service account have?",
    ): [Constraint("user_name", "contains", gold_value="deploy-bot")],
    (
        "delete_user",
        "Remove the decommissioned test-automation IAM user account from the account.",
    ): [Constraint("user_name", "contains", gold_value="test-automation")],
    (
        "create_role",
        "Create a new IAM role named lambda-executor with a trust policy allowing "
        "the Lambda service to assume it.",
    ): [Constraint("role_name", "contains", gold_value="lambda-executor")],
    (
        "get_managed_policy_document",
        "Show me the actual permission statements (actions, resources, conditions) "
        "in the managed policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess.",
    ): [Constraint("policy_arn", "contains", gold_value="AmazonS3ReadOnlyAccess")],
    (
        "put_user_policy",
        "Embed an inline policy named monthly-reports-access directly in the "
        "billing-reporter user, granting only s3:GetObject on the reports bucket.",
    ): [
        Constraint("policy_name", "contains", gold_value="monthly-reports-access"),
        Constraint("user_name", "contains", gold_value="billing-reporter"),
    ],
    (
        "get_user_policy",
        "Show me the inline policy named session-logger that is embedded in the audit-bot user.",
    ): [
        Constraint("policy_name", "contains", gold_value="session-logger"),
        Constraint("user_name", "contains", gold_value="audit-bot"),
    ],
    (
        "put_role_policy",
        "Embed an inline policy named describe-ec2-access directly in the "
        "ec2-scanner role, allowing ec2:DescribeInstances on all resources.",
    ): [
        Constraint("policy_name", "contains", gold_value="describe-ec2-access"),
        Constraint("role_name", "contains", gold_value="ec2-scanner"),
    ],
    (
        "get_role_policy",
        "Show me the inline policy named describe-ec2-access that is embedded in "
        "the ec2-scanner role.",
    ): [
        Constraint("policy_name", "contains", gold_value="describe-ec2-access"),
        Constraint("role_name", "contains", gold_value="ec2-scanner"),
    ],
    (
        "create_group",
        "Create a new IAM group named data-engineers.",
    ): [Constraint("group_name", "contains", gold_value="data-engineers")],
    (
        "get_group",
        "Who are the members of the data-engineers IAM group, and what policies does it have?",
    ): [Constraint("group_name", "contains", gold_value="data-engineers")],
    (
        "add_user_to_group",
        "Add the new hire jsmith to the data-engineers IAM group.",
    ): [
        Constraint("user_name", "contains", gold_value="jsmith"),
        Constraint("group_name", "contains", gold_value="data-engineers"),
    ],
    (
        "remove_user_from_group",
        "Remove jsmith from the data-engineers group — they transferred to another team.",
    ): [
        Constraint("user_name", "contains", gold_value="jsmith"),
        Constraint("group_name", "contains", gold_value="data-engineers"),
    ],
    (
        "delete_group",
        "Remove the deprecated temp-contractors IAM group from the account.",
    ): [Constraint("group_name", "contains", gold_value="temp-contractors")],
    (
        "simulate_principal_policy",
        "Check whether the deploy-bot service account "
        "(arn:aws:iam::123456789012:user/deploy-bot) would be allowed to call "
        "s3:PutObject on the uploads bucket.",
    ): [
        Constraint("policy_source_arn", "contains", gold_value="deploy-bot"),
        Constraint("action_names", "contains", gold_value="s3:PutObject"),
    ],
    (
        "create_access_key",
        "Generate a new programmatic access key for the deploy-bot service account.",
    ): [Constraint("user_name", "contains", gold_value="deploy-bot")],
    (
        "delete_access_key",
        "Revoke the access key AKIAIOSFODNN7EXAMPLE belonging to the deploy-bot service account.",
    ): [
        Constraint("access_key_id", "contains", gold_value="AKIAIOSFODNN7EXAMPLE"),
        Constraint("user_name", "contains", gold_value="deploy-bot"),
    ],
}

# ── p2a_internal_proxy_mirror / p2a_arm_a / p2a_arm_guardb / p2a_arm_oracle ────
# 48 tasks, all 4 arms share the identical 48-tool catalog and schemas.
# Skipped (4/48): schedule_invoice, queue_invoice, stage_invoice, draft_invoice —
# their schema holds the invoice under an opaque `invoice_data` object (not an
# `invoice_id` string field), so the task's stated literal ("invoice INV-2301") has
# no single scalar field to check against without guessing the object's internal
# shape — left unconstrained rather than assuming a nested key that isn't in the schema.
_P2A_INTERNAL_PROXY_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "get_order",
        "What's the current status and total amount for order ORD-44812? "
        "I just need the summary, not all the details.",
    ): [Constraint("order_id", "contains", gold_value="ORD-44812")],
    (
        "fetch_order",
        "Pull up everything on order ORD-44812 — the individual line items, "
        "shipping address, and billing info.",
    ): [Constraint("order_id", "contains", gold_value="ORD-44812")],
    (
        "load_order",
        "I need a quick look at order ORD-44812 to check its status. "
        "A cached result is fine if it's faster.",
    ): [Constraint("order_id", "contains", gold_value="ORD-44812")],
    (
        "retrieve_order",
        "What is the final price for order ORD-44812 once discounts and taxes have been applied?",
    ): [Constraint("order_id", "contains", gold_value="ORD-44812")],
    ("create_order", "Create a new order for customer CUST-901."): [
        Constraint("customer_id", "contains", gold_value="CUST-901")
    ],
    ("cancel_order", "Cancel order ORD-44812."): [
        Constraint("order_id", "contains", gold_value="ORD-44812")
    ],
    ("list_orders", "Show all orders placed by customer CUST-901."): [
        Constraint("customer_id", "contains", gold_value="CUST-901")
    ],
    (
        "update_invoice",
        "Change the due date on invoice INV-2201 to next Friday. "
        "Leave all other fields exactly as they are.",
    ): [Constraint("invoice_id", "contains", gold_value="INV-2201")],
    (
        "upsert_invoice",
        "Make sure invoice INV-2201 exists with these details: "
        "if it's already there update it, if not create it.",
    ): [Constraint("invoice_id", "contains", gold_value="INV-2201")],
    (
        "patch_invoice",
        "Apply this JSON Patch to invoice INV-2201: add a line item "
        "at /line_items/- and change the total at /total.",
    ): [Constraint("invoice_id", "contains", gold_value="INV-2201")],
    (
        "replace_invoice",
        "Overwrite invoice INV-2201 completely with this new data. "
        "Any fields I don't provide should be cleared.",
    ): [Constraint("invoice_id", "contains", gold_value="INV-2201")],
    (
        "amend_invoice",
        "Invoice INV-2201 had an incorrect tax rate. Correct it — "
        "the original version needs to stay in the audit trail.",
    ): [Constraint("invoice_id", "contains", gold_value="INV-2201")],
    ("create_invoice", "Create a new invoice for customer CUST-901 for $450."): [
        Constraint("customer_id", "contains", gold_value="CUST-901"),
        Constraint("amount", "numeric_equals", gold_value="450"),
    ],
    ("delete_invoice", "Delete invoice INV-2201."): [
        Constraint("invoice_id", "contains", gold_value="INV-2201")
    ],
    (
        "delete_ticket",
        "Delete ticket TKT-5503. We may need to look it up later "
        "so don't destroy the data permanently.",
    ): [Constraint("ticket_id", "contains", gold_value="TKT-5503")],
    (
        "archive_ticket",
        "Move ticket TKT-5503 to the archive — it's resolved and "
        "we don't want it cluttering the active queue, but we want it recoverable.",
    ): [Constraint("ticket_id", "contains", gold_value="TKT-5503")],
    (
        "purge_ticket",
        "Permanently destroy ticket TKT-5503 and all associated data immediately. "
        "This cannot be undone.",
    ): [Constraint("ticket_id", "contains", gold_value="TKT-5503")],
    (
        "expire_ticket",
        "Mark ticket TKT-5503 as expired because the customer's trial period ended. "
        "Keep it visible and queryable in reporting.",
    ): [Constraint("ticket_id", "contains", gold_value="TKT-5503")],
    (
        "create_ticket",
        "Open a new support ticket for customer CUST-901 about a billing issue.",
    ): [
        Constraint("customer_id", "contains", gold_value="CUST-901"),
        Constraint("subject", "contains", gold_value="billing"),
    ],
    ("close_ticket", "Close ticket TKT-5503 — the issue is resolved."): [
        Constraint("ticket_id", "contains", gold_value="TKT-5503")
    ],
    (
        "reopen_ticket",
        "Reopen ticket TKT-5503, the customer says the problem came back.",
    ): [Constraint("ticket_id", "contains", gold_value="TKT-5503")],
    (
        "search_accounts",
        "Find all accounts that mention 'enterprise tier' anywhere in their "
        "name, notes, or contact email.",
    ): [Constraint("q", "contains", gold_value="enterprise tier")],
    (
        "filter_accounts",
        "Show me all active enterprise accounts in the EMEA region, page 2.",
    ): [
        Constraint("status", "contains", gold_value="active"),
        Constraint("region", "contains", gold_value="EMEA"),
        Constraint("page", "numeric_equals", gold_value="2"),
    ],
    (
        "query_accounts",
        "Get all accounts where status = 'TRIAL' AND created_at > '2026-01-01' "
        "AND account_type != 'INTERNAL'.",
    ): [Constraint("where_clause", "contains", gold_value="TRIAL")],
    (
        "find_account",
        "Look up the account that has external Salesforce ID SF-00028811.",
    ): [Constraint("external_ref", "contains", gold_value="SF-00028811")],
    ("lookup_account", "Get the account record for account_id ACC-10042."): [
        Constraint("account_id", "contains", gold_value="ACC-10042")
    ],
    (
        "create_account",
        "Create a new account for Acme Corp with type 'ENTERPRISE'.",
    ): [
        Constraint("name", "contains", gold_value="Acme Corp"),
        Constraint("account_type", "enum", gold_value="ENTERPRISE"),
    ],
    ("deactivate_account", "Deactivate account ACC-10042."): [
        Constraint("account_id", "contains", gold_value="ACC-10042")
    ],
    (
        "notify_customer",
        "Send customer CUST-901 an email letting them know their order has shipped.",
    ): [Constraint("customer_id", "contains", gold_value="CUST-901")],
    (
        "push_update",
        "Send a push notification to CUST-901's phone that their order is on the way.",
    ): [Constraint("customer_id", "contains", gold_value="CUST-901")],
    (
        "dispatch_sms",
        "Text CUST-901 a message that their delivery is arriving today.",
    ): [Constraint("customer_id", "contains", gold_value="CUST-901")],
    (
        "message_customer",
        "Post an in-app message to CUST-901's notification inbox about their order status.",
    ): [Constraint("customer_id", "contains", gold_value="CUST-901")],
    (
        "contact_customer",
        "Reach out to CUST-901 about their delayed shipment using whatever channel they prefer.",
    ): [Constraint("customer_id", "contains", gold_value="CUST-901")],
    (
        "create_notification_rule",
        "Create a notification rule that emails customers when an order ships.",
    ): [Constraint("channel", "contains", gold_value="email")],
    ("delete_notification_rule", "Delete notification rule NR-14."): [
        Constraint("rule_id", "contains", gold_value="NR-14")
    ],
    (
        "confirm_order",
        "Order ORD-44812 is ready — confirm it and let the customer know.",
    ): [Constraint("order_id", "contains", gold_value="ORD-44812")],
    (
        "approve_order",
        "Approve order ORD-44812 internally so it can move to the next "
        "fulfillment stage. The customer doesn't need to be notified.",
    ): [Constraint("order_id", "contains", gold_value="ORD-44812")],
    (
        "fulfill_order",
        "Trigger fulfillment for order ORD-44812 so the warehouse knows "
        "to pick and ship the physical items.",
    ): [Constraint("order_id", "contains", gold_value="ORD-44812")],
    (
        "process_order",
        "Run order ORD-44812 through the full payment and inventory "
        "pipeline and update its status in a single atomic operation.",
    ): [Constraint("order_id", "contains", gold_value="ORD-44812")],
    ("submit_order", "Submit order ORD-44812 on behalf of the customer."): [
        Constraint("order_id", "contains", gold_value="ORD-44812")
    ],
    ("void_order", "Void order ORD-44812 and release the reserved stock."): [
        Constraint("order_id", "contains", gold_value="ORD-44812")
    ],
    # SKIPPED: schedule_invoice, queue_invoice, stage_invoice, draft_invoice — the
    # stated invoice id has no scalar schema field to check (schema holds an opaque
    # invoice_data object, not an invoice_id string).
    ("send_invoice", "Send invoice INV-2301 to the customer now."): [
        Constraint("invoice_id", "contains", gold_value="INV-2301")
    ],
    ("preview_invoice", "Preview how invoice INV-2301 will look before sending."): [
        Constraint("invoice_id", "contains", gold_value="INV-2301")
    ],
    ("download_invoice", "Download invoice INV-2301 as a PDF."): [
        Constraint("invoice_id", "contains", gold_value="INV-2301")
    ],
}

# ── q3_real_server / q3_arm_a / q3_arm_o ────────────────────────────────────────
# 12 tasks (10 reused from q3_catalog.TASKS + 2 new gap tasks for lookup_data/
# plan_event — see blind_tasks.py's Q3_SUBSET_TASKS). Single shared "query" param.
# Skipped (4/12): write_entry, archive_item, retire_data, remove_entry — none of
# q3_catalog's own task text for these 4 states a concrete literal identifier
# (only generic phrases like "the administrator's configuration change" or "the
# Q2 analytics record"), consistent with that catalog's own authoring style.
_Q3_SUBSET_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "store_item",
        "Hold the recommendation results for session_id=4821 for a few minutes to avoid "
        "recomputing them on every request.",
    ): [Constraint("query", "contains", gold_value="4821")],
    (
        "persist_row",
        "Add a new invoice entry for order_id=9988 — this must fail if that invoice already exists.",
    ): [Constraint("query", "contains", gold_value="9988")],
    (
        "save_record",
        "Update the user profile for account_id=2201, creating it if this is their first visit.",
    ): [Constraint("query", "contains", gold_value="2201")],
    # SKIPPED: write_entry — no concrete literal in "Record the administrator's
    # configuration change permanently for the compliance audit trail."
    (
        "delete_record",
        "Permanently erase user account 5519 — it must not be recoverable after this operation.",
    ): [Constraint("query", "contains", gold_value="5519")],
    # SKIPPED: archive_item — no concrete literal in "Move the Q2 analytics record
    # out of active results while keeping it accessible for audits."
    # SKIPPED: retire_data — no concrete literal in "Mark the legacy product catalog
    # as no longer editable..."
    # SKIPPED: remove_entry — no concrete literal in "Take the draft log event off
    # the visible stream but preserve it for compliance records."
    ("find_entries", "Retrieve the records where the key contains 'invoice-2024'."): [
        Constraint("query", "contains", gold_value="invoice-2024")
    ],
    ("book_slot", "Reserve the Friday 2 PM slot for the team standup."): [
        Constraint("query", "contains", gold_value="team standup")
    ],
    (
        "lookup_data",
        "Search for every entry whose key includes the substring 'sess-4471'.",
    ): [Constraint("query", "contains", gold_value="sess-4471")],
    (
        "plan_event",
        "Add the 'team-retro' block to the shared calendar for Monday morning.",
    ): [Constraint("query", "contains", gold_value="team-retro")],
}

# ── q6_real_server / q6_arm_a / q6_arm_f_doc_guarded ────────────────────────────
# 23 tasks (19 reused from q6_catalog.TASKS + 4 new gap tasks — see blind_tasks.py's
# Q6_SUBSET_TASKS). Same "query"-only schema as Q3. Reuses the same skip reasoning
# as Q3 for the 6 tasks shared verbatim with q3_catalog (write_entry, archive_item*,
# retire_data, remove_entry skipped for the same no-literal reason; *archive_item
# is not in Q6's structural-contested subset at all — see catalog note — but its
# gap task below IS constrained since it was authored fresh for this expansion).
_Q6_SUBSET_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "store_item",
        "Hold the recommendation results for session_id=4821 for a few minutes to avoid "
        "recomputing them on every request.",
    ): [Constraint("query", "contains", gold_value="4821")],
    (
        "persist_row",
        "Add a new invoice entry for order_id=9988 — this must fail if that invoice already exists.",
    ): [Constraint("query", "contains", gold_value="9988")],
    # SKIPPED: write_entry — no concrete literal (same Q3 task text, same reasoning).
    (
        "delete_record",
        "Permanently erase user account 5519 — it must not be recoverable after this operation.",
    ): [Constraint("query", "contains", gold_value="5519")],
    # SKIPPED: retire_data — no concrete literal (same Q3 task text).
    # SKIPPED: remove_entry — no concrete literal (same Q3 task text).
    ("find_entries", "Retrieve the records where the key contains 'invoice-2024'."): [
        Constraint("query", "contains", gold_value="invoice-2024")
    ],
    ("book_slot", "Reserve the Friday 2 PM slot for the team standup."): [
        Constraint("query", "contains", gold_value="team standup")
    ],
    # SKIPPED: compress_file, generate_token, list_active_users, list_active_sessions,
    # reset_pin, reset_password — none of Q6_ALREADY_PASSING_TASKS' text for these
    # states a concrete literal identifier.
    (
        "hash_value",
        "Generate a cryptographic fingerprint for the API secret key 'sk-prod-9812'.",
    ): [Constraint("query", "contains", gold_value="sk-prod-9812")],
    (
        "parse_date",
        "Break down the date string '2024-03-15' into its year, month, and day components.",
    ): [Constraint("query", "contains", gold_value="2024-03-15")],
    (
        "count_words",
        "How many words are in the text 'The quick brown fox jumps over the lazy dog'?",
    ): [Constraint("query", "contains", gold_value="quick brown fox")],
    ("close_ticket", "Mark support ticket TKT-9921 as closed and resolved."): [
        Constraint("query", "contains", gold_value="TKT-9921")
    ],
    ("close_request", "Close the pending service request REQ-4402."): [
        Constraint("query", "contains", gold_value="REQ-4402")
    ],
    (
        "save_record",
        "Update the customer profile for account 'CUST-6612', creating it fresh if "
        "this is their first record.",
    ): [Constraint("query", "contains", gold_value="CUST-6612")],
    (
        "archive_item",
        "Move the outdated marketing record 'promo-2024-q1' out of active results "
        "while keeping it accessible for later reference.",
    ): [Constraint("query", "contains", gold_value="promo-2024-q1")],
    (
        "lookup_data",
        "Search for every entry whose key includes the substring 'ticket-8827'.",
    ): [Constraint("query", "contains", gold_value="ticket-8827")],
    (
        "plan_event",
        "Add the 'quarterly-planning' block to the shared calendar for Thursday afternoon.",
    ): [Constraint("query", "contains", gold_value="quarterly-planning")],
}

# ── t18_vague_server_set2 / t18_fixer_server_set2 / t18_q2b_server_set2 /
#    t18_oracle_server_set2 ────────────────────────────────────────────────────
# All 4 arms share the identical 12-tool, single-param {"query": string} schema and
# T18_SUBSET_TASKS_SET2 task list — one dict reused for all 4 manifest keys.
# The 8 tasks reused verbatim from t18_catalog.TASKS mostly lack concrete literals
# (consistent with that catalog's own data_write/validate task style — see
# blind_tasks.py note); only check_permission's catalog task has one. All 16
# newly-authored gap tasks were deliberately written with a concrete literal, so
# they are fully constrained.
_T18_QUERY_CONSTRAINTS_SET2: dict[tuple[str, str], list[Constraint]] = {
    # SKIPPED: save_record catalog task "Upsert a customer profile: create it if
    # new, overwrite it if found by key." — no concrete literal.
    # SKIPPED: write_entry catalog task "Record the user login event in the
    # application audit trail." — no concrete literal.
    # SKIPPED: store_item catalog task "Hold the API response for this user in fast
    # temporary storage for 5 minutes." — no concrete literal.
    # SKIPPED: persist_row catalog task "Add a new invoice line item to the orders
    # table as a brand-new row." — no concrete literal.
    # SKIPPED: validate_schema catalog task "Confirm the incoming request body
    # matches the required data contract structure." — no concrete literal.
    (
        "check_permission",
        "Verify whether user_id=5501 is allowed to perform the 'report:export' action.",
    ): [Constraint("query", "contains", gold_value="5501")],
    # SKIPPED: verify_token catalog task "Confirm the credential in the
    # Authorization header has not expired." — no concrete literal.
    # SKIPPED: validate_format catalog task "Ensure the submitted phone number
    # string matches the E.164 pattern." — no concrete literal.
    (
        "save_record",
        "Update the shipping preferences on file for repeat customer 'CUST-7734', "
        "creating a fresh record if this is their first order.",
    ): [Constraint("query", "contains", gold_value="CUST-7734")],
    (
        "write_entry",
        "Append today's system health check result for service 'checkout-api' to "
        "the audit trail as a permanent record.",
    ): [Constraint("query", "contains", gold_value="checkout-api")],
    (
        "store_item",
        "Keep the dashboard summary for widget 'quarterly-revenue' readily "
        "available for quick access without hitting the database again.",
    ): [Constraint("query", "contains", gold_value="quarterly-revenue")],
    (
        "persist_row",
        "Insert a brand-new subscription-renewal row for subscription 'SUB-88213' "
        "into the billing table — this should only succeed if no such row exists yet.",
    ): [Constraint("query", "contains", gold_value="SUB-88213")],
    (
        "commit_data",
        "Flush the batch of pending updates queued under batch id 'BATCH-5591' so "
        "they're written to the database all at once.",
    ): [Constraint("query", "contains", gold_value="BATCH-5591")],
    (
        "commit_data",
        "Finalize the queued set of inventory adjustments tagged 'INV-ADJ-220' as "
        "a single atomic write to the database.",
    ): [Constraint("query", "contains", gold_value="INV-ADJ-220")],
    (
        "insert_document",
        "Add a brand-new customer profile document with id 'doc-cust-4471' to the "
        "NoSQL collection — the operation must fail if that id already exists.",
    ): [Constraint("query", "contains", gold_value="doc-cust-4471")],
    (
        "insert_document",
        "Create a fresh order-history document with id 'doc-ord-9012' in the "
        "document store, only if no document with that id already exists.",
    ): [Constraint("query", "contains", gold_value="doc-ord-9012")],
    (
        "validate_schema",
        "Check that the payload submitted by mobile client request 'REQ-3391' "
        "matches the registered data contract before accepting it.",
    ): [Constraint("query", "contains", gold_value="REQ-3391")],
    (
        "check_permission",
        "Confirm whether support agent account 'agent-2209' is allowed to issue "
        "refunds under the current access policy.",
    ): [Constraint("query", "contains", gold_value="agent-2209")],
    (
        "verify_token",
        "Make sure the bearer credential 'tok_9f8e7d' attached to this API "
        "request is still within its valid lifetime and correctly formed.",
    ): [Constraint("query", "contains", gold_value="tok_9f8e7d")],
    (
        "validate_format",
        "Check that the entered postal code '94107-1234' matches the required "
        "regional formatting pattern.",
    ): [Constraint("query", "contains", gold_value="94107-1234")],
    (
        "check_quota",
        "Find out how close account 'ACC-5502' is to hitting its monthly API call limit.",
    ): [Constraint("query", "contains", gold_value="ACC-5502")],
    (
        "check_quota",
        "Check whether team 'team-data-eng' storage allotment has been used up "
        "before allowing another upload.",
    ): [Constraint("query", "contains", gold_value="team-data-eng")],
    (
        "verify_signature",
        "Confirm that incoming webhook payload 'wh-8834' cryptographic signature "
        "actually matches what the sender's shared secret would produce.",
    ): [Constraint("query", "contains", gold_value="wh-8834")],
    (
        "verify_signature",
        "Make sure update package 'pkg-2.4.1' signature checks out against the "
        "publisher's public key before installing it.",
    ): [Constraint("query", "contains", gold_value="pkg-2.4.1")],
}

# ── exp1_dataojitori_nocturne_memory_mirror ─────────────────────────────────────
# 7 tools, 14 tasks. Best-effort tier — most tasks state a concrete URI or literal
# word that maps directly to a schema field.
# Skipped (2/14): read_memory task 2 ("recently modified memories from the last
# session") — no specific URI stated (a generic "recent" browse, several valid
# URIs would satisfy it — e.g. "system://recent" or "system://recent/N" with any
# N); create_memory task 2 ("brand-new note under the 'writer://' root...") — no
# concrete title/content stated, only a topic description.
_EXP1_NOCTURNE_MEMORY_MIRROR_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    (
        "read_memory",
        "Load the memory stored at 'core://agent/my_user' so I can see what it "
        "currently contains before deciding what to change.",
    ): [Constraint("uri", "contains", gold_value="core://agent/my_user")],
    # SKIPPED: read_memory "Show me the recently modified memories..." — no
    # concrete URI stated (several valid answers).
    (
        "create_memory",
        "Add a new memory under 'core://agent' with the content 'always confirm "
        "before deleting user data', high retrieval priority, a disclosure "
        "condition of 'when I am about to run a delete operation', and the title "
        "'delete_confirmation_rule'.",
    ): [
        Constraint("parent_uri", "contains", gold_value="core://agent"),
        Constraint("title", "contains", gold_value="delete_confirmation_rule"),
    ],
    # SKIPPED: create_memory "Record a brand-new note under the 'writer://' root..."
    # — no concrete title/content stated, only a topic description.
    (
        "update_memory",
        "In the memory at 'core://agent/worldview', replace the sentence 'trust is "
        "earned slowly' with 'trust is earned through consistent action' — leave "
        "everything else in that memory unchanged.",
    ): [
        Constraint("uri", "contains", gold_value="core://agent/worldview"),
        Constraint("old_string", "contains", gold_value="trust is earned slowly"),
        Constraint(
            "new_string", "contains", gold_value="trust is earned through consistent action"
        ),
    ],
    (
        "update_memory",
        "Append a new paragraph to the end of the existing memory at "
        "'writer://chapter_2' without touching what's already there.",
    ): [Constraint("uri", "contains", gold_value="writer://chapter_2")],
    (
        "delete_memory",
        "Permanently remove the obsolete memory at 'core://agent/old_note' — I've "
        "already read it and confirmed it's no longer relevant.",
    ): [Constraint("uri", "contains", gold_value="core://agent/old_note")],
    (
        "delete_memory",
        "Cut the outdated draft path 'writer://draft_v1' from the memory tree for good.",
    ): [Constraint("uri", "contains", gold_value="writer://draft_v1")],
    (
        "add_alias",
        "Create a second entry point at 'core://timeline/2024/05/20' that points "
        "to the same existing memory as 'core://agent/my_user/first_meeting', with "
        "its own priority and its own disclosure condition for this new path.",
    ): [
        Constraint("new_uri", "contains", gold_value="core://timeline/2024/05/20"),
        Constraint("target_uri", "contains", gold_value="core://agent/my_user/first_meeting"),
    ],
    (
        "add_alias",
        "I want 'core://hazards/network_outage' to also be reachable from a new "
        "path under 'core://agent/infra_notes' without duplicating the content — "
        "set a priority and disclosure condition for the new path.",
    ): [
        Constraint("target_uri", "contains", gold_value="core://hazards/network_outage"),
        Constraint("new_uri", "contains", gold_value="core://agent/infra_notes"),
    ],
    (
        "manage_triggers",
        "Bind the word 'Nginx' as a glossary keyword to the memory node at "
        "'core://hazards/spa_fallback' so a link to it surfaces automatically "
        "whenever that word appears elsewhere.",
    ): [
        Constraint("uri", "contains", gold_value="core://hazards/spa_fallback"),
        Constraint("add", "contains", gold_value="Nginx"),
    ],
    (
        "manage_triggers",
        "Unbind the keyword 'deprecated' from whatever memory node it's currently "
        "attached to, without deleting the memory itself.",
    ): [Constraint("remove", "contains", gold_value="deprecated")],
    (
        "search_memory",
        "Find every memory whose path or content mentions the word 'job', across all domains.",
    ): [Constraint("query", "contains", gold_value="job")],
    (
        "search_memory",
        "Look only within the 'writer' domain for any memory mentioning the word 'chapter'.",
    ): [
        Constraint("query", "contains", gold_value="chapter"),
        Constraint("domain", "contains", gold_value="writer"),
    ],
}

# =============================================================================
# Manifest-keyed lookup — outer key matches ToolSetEntry.name in manifest.py,
# inner dict matches ty2_tasks.py's (tool_name, task.description) convention.
# =============================================================================
TASK_CONSTRAINTS: dict[str, dict[tuple[str, str], list[Any]]] = {
    "echo_server": _ECHO_SERVER_CONSTRAINTS,
    "confusable_server": _CONFUSABLE_SERVER_CONSTRAINTS,
    "confusable_server_oracle": _CONFUSABLE_SERVER_CONSTRAINTS,
    "grounded_server": _GROUNDED_SERVER_CONSTRAINTS,
    "grounded_server_oracle": _GROUNDED_SERVER_CONSTRAINTS,
    "mediocre_server": _MEDIOCRE_SERVER_CONSTRAINTS,
    "call_constraints_server": _CALL_CONSTRAINTS_SERVER_CONSTRAINTS,
    "call_constraints_server_oracle": _CALL_CONSTRAINTS_SERVER_CONSTRAINTS,
    "call_constraints_v2_server": _TY2_TASK_CONSTRAINTS,
    "call_constraints_v2_server_oracle": _TY2_TASK_CONSTRAINTS,
    "t18_vague_server": _T18_QUERY_CONSTRAINTS,
    "t18_fixer_server": _T18_QUERY_CONSTRAINTS,
    "t18_q2b_server": _T18_QUERY_CONSTRAINTS,
    "t18_oracle_server": _T18_QUERY_CONSTRAINTS,
    "exp1_datalayer_jupyter_mcp_server_mirror": _JUPYTER_MIRROR_CONSTRAINTS,
    "exp1_datalayer_jupyter_mcp_server_mirror_oracle": _JUPYTER_MIRROR_CONSTRAINTS,
    "exp1_blazickjp_arxiv_mcp_server_mirror": _ARXIV_MIRROR_CONSTRAINTS,
    "exp1_stickerdaniel_linkedin_mcp_server_mirror": _LINKEDIN_MIRROR_CONSTRAINTS,
    # ── Tier 1: RW1 / RW2 / P2A (22 new entries start here) ────────────────────
    "rw1_github_mirror": _RW1_GITHUB_CONSTRAINTS,
    "rw1_arm_a": _RW1_GITHUB_CONSTRAINTS,
    "rw1_arm_guardb": _RW1_GITHUB_CONSTRAINTS,
    "rw1_arm_oracle": _RW1_GITHUB_CONSTRAINTS,
    "rw2_aws_iam_mirror": _RW2_AWS_IAM_CONSTRAINTS,
    "rw2_arm_a": _RW2_AWS_IAM_CONSTRAINTS,
    "rw2_arm_guardb": _RW2_AWS_IAM_CONSTRAINTS,
    "p2a_internal_proxy_mirror": _P2A_INTERNAL_PROXY_CONSTRAINTS,
    "p2a_arm_a": _P2A_INTERNAL_PROXY_CONSTRAINTS,
    "p2a_arm_guardb": _P2A_INTERNAL_PROXY_CONSTRAINTS,
    "p2a_arm_oracle": _P2A_INTERNAL_PROXY_CONSTRAINTS,
    # ── Tier 2: Q3 / Q6 ─────────────────────────────────────────────────────────
    "q3_real_server": _Q3_SUBSET_CONSTRAINTS,
    "q3_arm_a": _Q3_SUBSET_CONSTRAINTS,
    "q3_arm_o": _Q3_SUBSET_CONSTRAINTS,
    "q6_real_server": _Q6_SUBSET_CONSTRAINTS,
    "q6_arm_a": _Q6_SUBSET_CONSTRAINTS,
    "q6_arm_f_doc_guarded": _Q6_SUBSET_CONSTRAINTS,
    # ── Tier 3: T18 2nd family subset (data_write + validate) ──────────────────
    "t18_vague_server_set2": _T18_QUERY_CONSTRAINTS_SET2,
    "t18_fixer_server_set2": _T18_QUERY_CONSTRAINTS_SET2,
    "t18_q2b_server_set2": _T18_QUERY_CONSTRAINTS_SET2,
    "t18_oracle_server_set2": _T18_QUERY_CONSTRAINTS_SET2,
    # ── Tier 4: new real-world mirror ───────────────────────────────────────────
    "exp1_dataojitori_nocturne_memory_mirror": _EXP1_NOCTURNE_MEMORY_MIRROR_CONSTRAINTS,
    # ── Phase 3: LLM-fixer-improved variants (5 new entries) ───────────────────
    # Constraints test argument correctness against the tool's real schema — a
    # property of the TASK, not of which description arm is served — so each
    # "_fixed" entry reuses its "before" counterpart's constraint dict verbatim,
    # same convention as the oracle-pair entries above. Schema-change check (per
    # the task brief): run_fixer's accepted schema_completeness changes for these
    # 5 pairs only ADD "type"/"description" metadata to previously-untyped ({})
    # params (verified in-process: every property name in every fixed tool's
    # inputSchema matches its "before" counterpart 1:1 — no renames, no removals,
    # no new required params that would change which args a correct call needs).
    # constraint_satisfaction (see _check_constraint above) evaluates the ACTUAL
    # constructed call argument value via Python-level coercion (float()/int()/
    # str()) — it never reads the tool's declared JSON-Schema type — so declaring
    # a param's type for the first time cannot invalidate a constraint already
    # keyed on that param name. One cosmetic mismatch worth flagging: in
    # mediocre_server_fixed, the fixer typed put_x.val as "string" and put_x.sid /
    # get_a.sid / get_b.sid / del_a.sid / del_b.sid as "string" even though every
    # constraint on those params is "numeric_equals" (the params really are
    # numeric at the call-semantics level) — a fixer schema-quality artifact, not
    # a constraint-correctness problem, since numeric_equals coerces the actual
    # value with float() regardless of the schema's declared type.
    "grounded_server_fixed": _GROUNDED_SERVER_CONSTRAINTS,
    "confusable_server_fixed": _CONFUSABLE_SERVER_CONSTRAINTS,
    "mediocre_server_fixed": _MEDIOCRE_SERVER_CONSTRAINTS,
    "call_constraints_server_fixed": _CALL_CONSTRAINTS_SERVER_CONSTRAINTS,
    "call_constraints_v2_server_fixed": _TY2_TASK_CONSTRAINTS,
}
