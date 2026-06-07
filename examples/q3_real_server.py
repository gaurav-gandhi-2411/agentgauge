from __future__ import annotations

# Q3 fixture — real server with working tool implementations.
#
# 12 tools in 4 families:
#   store_family:   store_item, persist_row, save_record, write_entry
#   delete_family:  delete_record, archive_item, retire_data, remove_entry
#   control_search: find_entries, lookup_data      (genuinely equivalent)
#   control_sched:  book_slot, plan_event          (genuinely equivalent)
#
# Schema: all tools use {"type": "object", "properties": {"query": {"type": "string"}}}
# (mirrors T18 confusable-catalog schema — names + identical schemas carry no signal)
#
# INDEPENDENCE RULE: implementations below were written as a working server would write
# them — using real data-structure idioms (TTL cache, raise-on-dup, audit log, del, flags).
# The oracle descriptions in q3_catalog.py are DERIVED from this code, not its origin.
#
# DOC VARIANT — this file includes honest docstrings. The BODY variant is the same source
# with docstrings stripped (computed dynamically by q3_catalog.get_body_source()).

import asyncio
import time

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("q3-real-server")

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

# ── Backing stores (in-memory, per-process) ────────────────────────────────────

_ttl_store: dict[str, dict] = {}    # key → {"value": str, "expires_at": float}
_db: dict[str, str] = {}             # key → value (persist_row, save_record)
_audit_log: list[dict] = []          # append-only; write_entry appends here
_records: dict[str, dict] = {}       # record_id → metadata dict (delete/archive/retire/remove)
_search_store: dict[str, str] = {}   # used by find_entries and lookup_data (both equivalent)
_calendar: dict[str, str] = {}       # used by book_slot and plan_event (both equivalent)


# ── store_family ───────────────────────────────────────────────────────────────

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


# ── delete_family ──────────────────────────────────────────────────────────────

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


# ── control_search (genuinely equivalent) ─────────────────────────────────────

async def _handle_find_entries(query: str) -> str:
    """Return all entries whose key contains the query string."""
    matches = [v for k, v in _search_store.items() if query in k]
    return f"find_entries('{query}'): {len(matches)} result(s)"


async def _handle_lookup_data(query: str) -> str:
    """Return all entries whose key contains the query string."""
    matches = [v for k, v in _search_store.items() if query in k]
    return f"lookup_data('{query}'): {len(matches)} result(s)"


# ── control_sched (genuinely equivalent) ──────────────────────────────────────

async def _handle_book_slot(query: str) -> str:
    """Reserve a slot in the calendar identified by the query string."""
    _calendar[query] = "reserved"
    return f"Slot '{query}' reserved in _calendar"


async def _handle_plan_event(query: str) -> str:
    """Reserve a slot in the calendar identified by the query string."""
    _calendar[query] = "reserved"
    return f"Slot '{query}' reserved in _calendar"


# ── MCP server wiring ──────────────────────────────────────────────────────────

_HANDLERS = {
    "store_item": _handle_store_item,
    "persist_row": _handle_persist_row,
    "save_record": _handle_save_record,
    "write_entry": _handle_write_entry,
    "delete_record": _handle_delete_record,
    "archive_item": _handle_archive_item,
    "retire_data": _handle_retire_data,
    "remove_entry": _handle_remove_entry,
    "find_entries": _handle_find_entries,
    "lookup_data": _handle_lookup_data,
    "book_slot": _handle_book_slot,
    "plan_event": _handle_plan_event,
}

_TOOL_ORDER = [
    "store_item", "persist_row", "save_record", "write_entry",
    "delete_record", "archive_item", "retire_data", "remove_entry",
    "find_entries", "lookup_data",
    "book_slot", "plan_event",
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return all 12 Q3 tools with empty descriptions (Arm A baseline)."""
    return [
        types.Tool(name=name, description="", inputSchema=_SCHEMA)
        for name in _TOOL_ORDER
    ]


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
                server_name="q3-real-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
