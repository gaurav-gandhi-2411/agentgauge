from __future__ import annotations

# Q6 extended fixture — real server with 23 working tool implementations.
#
# STRUCTURE:
#   Q3 tools (12):  store_family (4), delete_family (4), control_search (2), control_sched (2)
#   New already-passing, non-collision tools (5):
#     compress_file, hash_value, parse_date, count_words, generate_token
#   New already-passing, collision-prone pairs (3 pairs = 6 tools):
#     Pair C1: list_active_users / list_active_sessions
#     Pair C2: close_ticket / close_request
#     Pair C3: reset_pin / reset_password
#
# Schema: all tools use {"type": "object", "properties": {"query": {"type": "string"}}}
#
# INDEPENDENCE RULE: implementations below were written as a real server would write them,
# using real data-structure idioms. Oracle descriptions in q6_catalog.py are DERIVED from
# this code, not its origin.
#
# COLLISION-PRONE PAIR DESIGN: the three collision pairs have structurally similar
# implementations (same operation pattern, different backing stores). Guard-B target-only
# descriptions risk collapsing to the same phrase because the code patterns are identical
# and the distinguishing fact (the store name / credential type) may be omitted when the
# generator describes each tool in isolation. This is the harm vector Q6 tests.
#
# DOC VARIANT — includes honest docstrings. BODY variant not used in Q6 (Guard B uses DOC).

import asyncio
import hashlib
import time
import zlib
from datetime import date

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("q6-real-server")

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

# ── Backing stores — Q3 originals ─────────────────────────────────────────────

_ttl_store: dict[str, dict] = {}  # store_item (TTL cache)
_db: dict[str, str] = {}  # persist_row, save_record
_audit_log: list[dict] = []  # write_entry (append-only)
_records: dict[str, dict] = {}  # delete_record, archive_item, retire_data, remove_entry
_search_store: dict[str, str] = {}  # find_entries, lookup_data (equivalent)
_calendar: dict[str, str] = {}  # book_slot, plan_event (equivalent)

# ── Backing stores — Q6 new tools ─────────────────────────────────────────────

_user_store: dict[str, dict] = {}  # list_active_users
_session_store: dict[str, dict] = {}  # list_active_sessions
_ticket_store: dict[str, dict] = {}  # close_ticket
_request_store: dict[str, dict] = {}  # close_request
_pin_store: dict[str, str] = {}  # reset_pin
_password_store: dict[str, str] = {}  # reset_password


# ── Q3 store_family ────────────────────────────────────────────────────────────


async def _handle_store_item(query: str) -> str:
    """Store the query value in the in-memory TTL cache with a 5-minute expiry.

    Entries are evicted when expires_at passes. Overwrites silently on re-store.
    """
    _ttl_store[query] = {"value": query, "expires_at": time.time() + 300}
    return f"Cached '{query}' in _ttl_store (expires_at={_ttl_store[query]['expires_at']:.0f})"


async def _handle_persist_row(query: str) -> str:
    """Insert a new row keyed by query. Raises if the key already exists.

    Use for insert-only operations where an existing key is an error condition.
    """
    if query in _db:
        raise ValueError(f"Row '{query}' already exists — use save_record to update existing rows")
    _db[query] = query
    return f"Inserted new row '{query}' into _db"


async def _handle_save_record(query: str) -> str:
    """Save a record using upsert semantics — creates or overwrites without raising.

    Tracks whether the key existed before write so callers can distinguish
    create vs update in the return value.
    """
    existed = query in _db
    _db[query] = query
    return f"Record '{query}' {'updated' if existed else 'created'} in _db"


async def _handle_write_entry(query: str) -> str:
    """Append a structured entry to the immutable audit log.

    All entries are retained; nothing in _audit_log is ever deleted or modified.
    Use for compliance records, event trails, and chronological audit entries.
    """
    _audit_log.append({"entry": query, "ts": time.time(), "seq": len(_audit_log)})
    return f"Appended entry #{len(_audit_log)} to _audit_log for '{query}'"


# ── Q3 delete_family ───────────────────────────────────────────────────────────


async def _handle_delete_record(query: str) -> str:
    """Permanently remove a record from the store using del.

    The record is gone immediately. There is no tombstone and no recovery path.
    """
    _records.setdefault(query, {})
    del _records[query]
    return f"Record '{query}' permanently deleted from _records"


async def _handle_archive_item(query: str) -> str:
    """Set the archived flag on a record to exclude it from active queries.

    The record stays in _records and can be restored by clearing the flag.
    """
    _records.setdefault(query, {})
    _records[query]["archived"] = True
    return f"Record '{query}' archived (archived=True; still in _records)"


async def _handle_retire_data(query: str) -> str:
    """Mark a record as retired — it becomes read-only and is never removed.

    Retired records accumulate indefinitely for compliance and historical audit.
    """
    _records.setdefault(query, {})
    _records[query]["retired"] = True
    return f"Record '{query}' retired (retired=True; retained indefinitely)"


async def _handle_remove_entry(query: str) -> str:
    """Set the hidden flag to suppress an entry from active query results.

    The entry is excluded from queries but retained in _records for compliance.
    """
    _records.setdefault(query, {})
    _records[query]["hidden"] = True
    return f"Entry '{query}' hidden (hidden=True; retained for compliance)"


# ── Q3 control_search (genuinely equivalent) ──────────────────────────────────


async def _handle_find_entries(query: str) -> str:
    """Return all entries whose key contains the query string."""
    matches = [v for k, v in _search_store.items() if query in k]
    return f"find_entries('{query}'): {len(matches)} result(s)"


async def _handle_lookup_data(query: str) -> str:
    """Return all entries whose key contains the query string."""
    matches = [v for k, v in _search_store.items() if query in k]
    return f"lookup_data('{query}'): {len(matches)} result(s)"


# ── Q3 control_sched (genuinely equivalent) ───────────────────────────────────


async def _handle_book_slot(query: str) -> str:
    """Reserve a slot in the calendar identified by the query string."""
    _calendar[query] = "reserved"
    return f"Slot '{query}' reserved in _calendar"


async def _handle_plan_event(query: str) -> str:
    """Reserve a slot in the calendar identified by the query string."""
    _calendar[query] = "reserved"
    return f"Slot '{query}' reserved in _calendar"


# ── Q6 non-collision already-passing tools ─────────────────────────────────────


async def _handle_compress_file(query: str) -> str:
    """Compress the input string using zlib deflation and return the byte size reduction.

    Uses zlib.compress at the default compression level. Input is UTF-8 encoded before
    compression. Returns original length, compressed length, and bytes saved.
    """
    raw = query.encode("utf-8")
    compressed = zlib.compress(raw)
    saved = len(raw) - len(compressed)
    return f"compress_file: original={len(raw)}B compressed={len(compressed)}B saved={saved}B"


async def _handle_hash_value(query: str) -> str:
    """Hash the input string using SHA-256 and return the hex digest.

    Uses hashlib.sha256. The hash is deterministic: identical inputs always produce
    the same 64-character hex digest. No salt is applied.
    """
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"hash_value: sha256({query!r}) = {digest}"


async def _handle_parse_date(query: str) -> str:
    """Parse an ISO 8601 date string (YYYY-MM-DD) and return year, month, and day.

    Uses datetime.date.fromisoformat. Raises ValueError if the string is not a valid
    ISO date. Returns a structured year/month/day breakdown.
    """
    parsed = date.fromisoformat(query)
    return f"parse_date: year={parsed.year} month={parsed.month} day={parsed.day}"


async def _handle_count_words(query: str) -> str:
    """Count whitespace-delimited words in the input string and return the total.

    Uses str.split() with no arguments, which splits on any whitespace and discards
    empty strings. Returns the word count and the list of words found.
    """
    words = query.split()
    return f"count_words: {len(words)} word(s) in {query!r}"


async def _handle_generate_token(query: str) -> str:
    """Generate a deterministic hex access token by SHA-1 hashing the input.

    Uses hashlib.sha1. The token is derived from the query string, making it
    reproducible given the same input. Returns a 40-character hex string.
    """
    token = hashlib.sha1(query.encode("utf-8")).hexdigest()
    return f"generate_token: sha1({query!r}) = {token}"


# ── Q6 collision-prone Pair C1: list_active_users / list_active_sessions ──────
#
# COLLISION RISK: Both tools filter items where active=True from a separate store and
# return a count. Guard-B target-only descriptions may collapse to "Returns a count of
# active records from the store" for both — identical phrasing despite different stores.
# NAMES disambiguate (users vs sessions); target-only descriptions MIGHT NOT.


async def _handle_list_active_users(query: str) -> str:
    """Return the count of active user records in _user_store matching the query prefix.

    Filters _user_store for items where active=True and whose key starts with the
    query string. Returns the number of matching active users.
    """
    matches = {k: v for k, v in _user_store.items() if v.get("active") and k.startswith(query)}
    return f"list_active_users('{query}'): {len(matches)} active user(s) in _user_store"


async def _handle_list_active_sessions(query: str) -> str:
    """Return the count of active session records in _session_store matching the query prefix.

    Filters _session_store for items where active=True and whose key starts with the
    query string. Returns the number of matching active sessions.
    """
    matches = {k: v for k, v in _session_store.items() if v.get("active") and k.startswith(query)}
    return f"list_active_sessions('{query}'): {len(matches)} active session(s) in _session_store"


# ── Q6 collision-prone Pair C2: close_ticket / close_request ──────────────────
#
# COLLISION RISK: Both tools set a "closed" flag on a record in a separate store and
# return a confirmation. Guard-B target-only descriptions may collapse to "Sets the
# closed flag on the record and returns confirmation" for both — identical phrasing.
# NAMES disambiguate (ticket vs request); target-only descriptions MIGHT NOT.


async def _handle_close_ticket(query: str) -> str:
    """Mark a support ticket as closed in _ticket_store by setting its closed flag.

    Sets _ticket_store[query]["closed"] = True. Creates the ticket entry if it does
    not already exist. Returns a confirmation with the ticket key.
    """
    _ticket_store.setdefault(query, {})
    _ticket_store[query]["closed"] = True
    return f"close_ticket: ticket '{query}' marked closed in _ticket_store"


async def _handle_close_request(query: str) -> str:
    """Mark a service request as closed in _request_store by setting its closed flag.

    Sets _request_store[query]["closed"] = True. Creates the request entry if it does
    not already exist. Returns a confirmation with the request key.
    """
    _request_store.setdefault(query, {})
    _request_store[query]["closed"] = True
    return f"close_request: request '{query}' marked closed in _request_store"


# ── Q6 collision-prone Pair C3: reset_pin / reset_password ────────────────────
#
# COLLISION RISK: Both tools reset a stored credential to a default value in a
# separate store. Guard-B target-only descriptions may collapse to "Resets the stored
# credential to the default value" for both — identical phrasing despite different
# credential types. NAMES disambiguate (pin vs password); target-only descriptions MIGHT NOT.


async def _handle_reset_pin(query: str) -> str:
    """Reset the PIN for the account identified by query to the factory default '0000'.

    Writes '0000' into _pin_store[query], overwriting any existing PIN.
    Use when a user needs to unlock their account with a known initial PIN.
    """
    _pin_store[query] = "0000"
    return f"reset_pin: PIN for '{query}' reset to '0000' in _pin_store"


async def _handle_reset_password(query: str) -> str:
    """Reset the password for the account identified by query to 'changeme'.

    Writes 'changeme' into _password_store[query], overwriting any existing password.
    Use when a user needs a temporary password before setting their own.
    """
    _password_store[query] = "changeme"
    return f"reset_password: password for '{query}' reset to 'changeme' in _password_store"


# ── MCP server wiring ──────────────────────────────────────────────────────────

_HANDLERS = {
    # Q3 store_family
    "store_item": _handle_store_item,
    "persist_row": _handle_persist_row,
    "save_record": _handle_save_record,
    "write_entry": _handle_write_entry,
    # Q3 delete_family
    "delete_record": _handle_delete_record,
    "archive_item": _handle_archive_item,
    "retire_data": _handle_retire_data,
    "remove_entry": _handle_remove_entry,
    # Q3 control_search
    "find_entries": _handle_find_entries,
    "lookup_data": _handle_lookup_data,
    # Q3 control_sched
    "book_slot": _handle_book_slot,
    "plan_event": _handle_plan_event,
    # Q6 non-collision already-passing
    "compress_file": _handle_compress_file,
    "hash_value": _handle_hash_value,
    "parse_date": _handle_parse_date,
    "count_words": _handle_count_words,
    "generate_token": _handle_generate_token,
    # Q6 collision-prone pairs
    "list_active_users": _handle_list_active_users,
    "list_active_sessions": _handle_list_active_sessions,
    "close_ticket": _handle_close_ticket,
    "close_request": _handle_close_request,
    "reset_pin": _handle_reset_pin,
    "reset_password": _handle_reset_password,
}

_TOOL_ORDER = [
    # Q3 tools
    "store_item",
    "persist_row",
    "save_record",
    "write_entry",
    "delete_record",
    "archive_item",
    "retire_data",
    "remove_entry",
    "find_entries",
    "lookup_data",
    "book_slot",
    "plan_event",
    # Q6 non-collision
    "compress_file",
    "hash_value",
    "parse_date",
    "count_words",
    "generate_token",
    # Q6 collision-prone pairs
    "list_active_users",
    "list_active_sessions",
    "close_ticket",
    "close_request",
    "reset_pin",
    "reset_password",
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return all 23 Q6 tools with empty descriptions (Arm A baseline)."""
    return [types.Tool(name=name, description="", inputSchema=_SCHEMA) for name in _TOOL_ORDER]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
    query = arguments.get("query", "")
    try:
        result = await handler(query)
    except Exception as exc:
        result = f"Error: {exc}"
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="q6-real-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
