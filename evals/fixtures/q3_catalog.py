from __future__ import annotations

# Q3 pre-registered catalog, tasks, and gold mapping.
# 12-tool catalog in 4 families:
#   store_family (4 contested), delete_family (4 contested),
#   control_search (2 genuinely-equivalent), control_sched (2 genuinely-equivalent).
#
# Two source conditions:
#   DOC — real server source with honest docstrings (q3_real_server.py as-is)
#   BODY — same source with triple-quoted docstrings stripped
#
# INDEPENDENCE RULE: The tool implementations in q3_real_server.py were written first,
# as a working server would. Oracle descriptions below are DERIVED from reading the code,
# not from the T18 oracle text. Each contested tool's independence token is a real code
# construct (not prose) that a generator can read in the source.

import re
from pathlib import Path

from agentgauge.tasks import Task

_REAL_SERVER_PATH = Path(__file__).parent.parent.parent / "examples" / "q3_real_server.py"

# ── Tool families ──────────────────────────────────────────────────────────────

FAMILIES: dict[str, list[str]] = {
    "store_family": ["store_item", "persist_row", "save_record", "write_entry"],
    "delete_family": ["delete_record", "archive_item", "retire_data", "remove_entry"],
    "control_search": ["find_entries", "lookup_data"],
    "control_sched": ["book_slot", "plan_event"],
}

# ── Arm A descriptions (all empty — baseline) ──────────────────────────────────

ARM_A_DESCRIPTIONS: dict[str, str] = {
    tool: "" for tools in FAMILIES.values() for tool in tools
}

# ── Arm O descriptions (oracle — derived from reading the implementation code) ──
# Contested tools: each description encodes the distinguishing behavior.
# Control tools: descriptions are intentionally non-distinguishing (implementations are equal).

ARM_O_DESCRIPTIONS: dict[str, str] = {
    # store_family: distinguishing dimension = storage backend + semantics
    "store_item": (
        "Store the query value in the in-memory TTL cache with a fixed 5-minute expiry. "
        "Use for ephemeral fast-access data that should auto-expire."
    ),
    "persist_row": (
        "Insert a new database row keyed by query. Raises an error if the key already exists — "
        "use save_record to overwrite an existing row."
    ),
    "save_record": (
        "Save a record using upsert semantics: creates a new entry or overwrites the existing "
        "value without raising. Returns whether the key was created or updated."
    ),
    "write_entry": (
        "Append a structured entry to the immutable audit log. "
        "All entries are retained indefinitely; nothing in the log is ever modified or removed. "
        "Use for compliance records and event trails."
    ),
    # delete_family: distinguishing dimension = permanence / recoverability
    "delete_record": (
        "Permanently delete a record from the store using del. "
        "The record is gone immediately with no tombstone and no recovery path."
    ),
    "archive_item": (
        "Set the archived flag on a record to exclude it from active queries. "
        "The record stays in the store and can be restored by clearing the flag."
    ),
    "retire_data": (
        "Mark a record as retired — it becomes read-only and is retained indefinitely. "
        "Retired records are never physically removed. Use for compliance and historical audit."
    ),
    "remove_entry": (
        "Set the hidden flag to suppress an entry from active query results. "
        "The entry is retained in the store for compliance; it is not deleted."
    ),
    # control_search: genuinely equivalent — oracle does NOT distinguish them
    "find_entries": (
        "Return all entries whose key contains the query string."
    ),
    "lookup_data": (
        "Return all entries whose key contains the query string."
    ),
    # control_sched: genuinely equivalent — oracle does NOT distinguish them
    "book_slot": (
        "Reserve a slot in the calendar identified by the query string."
    ),
    "plan_event": (
        "Reserve a slot in the calendar identified by the query string."
    ),
}

# ── Independence tokens (one per contested tool) ───────────────────────────────
# CI asserts each token is present in the DOC source AND the BODY source.
# Tokens are real code constructs in q3_real_server.py — NOT prose paraphrases.

INDEPENDENCE_TOKENS: dict[str, str] = {
    "store_item": "_ttl_store",       # unique backing store name for TTL cache
    "persist_row": "raise ValueError", # insert-only guard raises on duplicate
    "save_record": "existed",          # upsert tracks whether key existed before write
    "write_entry": "_audit_log",       # appends to append-only audit log
    "delete_record": "del _records",   # uses del statement for permanent removal
    "archive_item": '"archived"',      # sets _records[query]["archived"] = True
    "retire_data": '"retired"',        # sets _records[query]["retired"] = True
    "remove_entry": '"hidden"',        # sets _records[query]["hidden"] = True
}

# Control tools have no independence token (implementations are truly equivalent)
CONTROL_TOOLS: frozenset[str] = frozenset(
    t for ts in [FAMILIES["control_search"], FAMILIES["control_sched"]] for t in ts
)

# ── Source access ──────────────────────────────────────────────────────────────


def get_doc_source() -> str:
    """Return the DOC-variant source (q3_real_server.py with docstrings)."""
    return _REAL_SERVER_PATH.read_text(encoding="utf-8")


def get_body_source() -> str:
    """Return the BODY-variant source (same file, triple-quoted docstrings stripped).

    Strips triple-quoted string literals that appear as standalone statements
    (i.e., function/class docstrings). Inline triple-quoted strings in expressions
    are left intact but none exist in q3_real_server.py.
    """
    source = get_doc_source()
    # Match triple-quoted strings at line-start (possibly indented), used as docstrings.
    # Pattern: optional whitespace, triple-quote, content (non-greedy), triple-quote,
    # optional trailing whitespace+newline.
    body = re.sub(
        r'[ \t]*"""[\s\S]*?"""[ \t]*\n?',
        "\n",
        source,
    )
    return body


# ── Tasks (12 pre-registered, 3 per contested family + 2 control) ──────────────
# Anti-tautology: task descriptions do NOT contain gold tool names or oracle tokens.

TASKS: list[Task] = [
    # store_family
    Task(
        "store_item",
        "Hold the recommendation results for session_id=4821 for a few minutes to avoid "
        "recomputing them on every request.",
    ),
    Task(
        "persist_row",
        "Add a new invoice entry for order_id=9988 — this must fail if that invoice already exists.",
    ),
    Task(
        "save_record",
        "Update the user profile for account_id=2201, creating it if this is their first visit.",
    ),
    Task(
        "write_entry",
        "Record the administrator's configuration change permanently for the compliance audit trail.",
    ),
    # delete_family
    Task(
        "delete_record",
        "Permanently erase user account 5519 — it must not be recoverable after this operation.",
    ),
    Task(
        "archive_item",
        "Move the Q2 analytics record out of active results while keeping it accessible for audits.",
    ),
    Task(
        "retire_data",
        "Mark the legacy product catalog as no longer editable — "
        "it should remain readable and retained indefinitely.",
    ),
    Task(
        "remove_entry",
        "Take the draft log event off the visible stream but preserve it for compliance records.",
    ),
    # control_search (ambiguous — either tool is valid; gold label is find_entries)
    Task(
        "find_entries",
        "Retrieve the records where the key contains 'invoice-2024'.",
    ),
    # control_sched (ambiguous — either tool is valid; gold label is book_slot)
    Task(
        "book_slot",
        "Reserve the Friday 2 PM slot for the team standup.",
    ),
]

# Tasks where both tools in the pair are valid (no real distinction)
CONTROL_TASK_PAIRS: list[tuple[str, str]] = [
    ("find_entries", "lookup_data"),
    ("book_slot", "plan_event"),
]

# ── Family map ─────────────────────────────────────────────────────────────────

FAMILY_MAP: dict[str, str] = {
    tool: family for family, tools in FAMILIES.items() for tool in tools
}
