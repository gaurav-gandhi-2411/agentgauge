from __future__ import annotations

# T16 held-out fixture — arm A (degraded). ObsStore API — run #4.
#
# Run history:
#   Run #1 (TaskTracker) VOID: ceiling — semantically obvious param names (title, task_id).
#   Run #2 (ObsStore v1, `rid`/`op` params) VOID: broken manipulation — runner showed only
#     tool names; arms A/B had identical selection prompts; b=0/c=0.
#   Run #3 (ObsStore v1, runner fixed) VOID: ceiling — arm A 90% (> 80% ceiling).
#     Root cause: param names `rid` vs `op` already distinguished confusable pairs, so
#     arm A achieved 90% without needing descriptions. arm B was WORSE (70%) — fixer's
#     verbose, inaccurate descriptions confused the agent more than the terse "Get." + param
#     names. Run is VOID (arm A > 80%), so this finding is not interpretable.
#   Run #4 (this fixture): identical param names (`key`) for all confusable pairs.
#     Now ONLY descriptions can distinguish get_a from get_b, and del_a from del_b.
#     Arm A both pairs described as "Get." and "Del." with identical {sid, key} params
#     → agent CANNOT distinguish from either description or param names → ~50% selection.
#     Arm B: fixer adds disambiguating descriptions → agent should distinguish correctly.
#
# Degradations (pre-registered for T16 A/B, run #4):
#
# 1. put_x: description "Put." (vague).
#    Parameters {sid, key, val, ts} have no type, no description, no required array.
#    PRE-REGISTERED: arm A may omit val/ts (not in task) or pass wrong types.
#
# 2. get_a: description "Get." IDENTICAL to get_b.
#    Parameters {sid, key} — SAME NAMES as get_b. key = record ID (string).
#    PRE-REGISTERED: arm A selection ≈ 50% for get_a/get_b tasks — agent sees identical
#    description AND identical param names; cannot distinguish without descriptions.
#
# 3. get_b: description "Get." IDENTICAL to get_a.
#    Parameters {sid, key} — SAME NAMES as get_a. key = aggregation fn ("sum"/"min"/"max"/"avg").
#    PRE-REGISTERED: arm A selection ≈ 50%; call_correctness headroom from enum constraint
#    on key — agent may pass "average"/"total"/"aggregate" (invalid) without schema guidance.
#
# 4. del_a: description "Del." IDENTICAL to del_b.
#    Parameters {sid, key} — SAME NAMES as del_b. key = record ID to delete.
#    PRE-REGISTERED: arm A selection ≈ 50%; cannot distinguish del_a from del_b by desc or params.
#
# 5. del_b: description "Del." IDENTICAL to del_a.
#    Parameters {sid, key} — SAME NAMES as del_a. key = "hard"/"soft" (delete mode for session).
#    PRE-REGISTERED: arm A selection ≈ 50%; call_correctness headroom from mode enum.
#
# H1 (selection_accuracy): testable — arm A expected ≈ 60-70% (below 80% ceiling).
# H2 (call_correctness): testable if arm A drops below 80% from enum failures; else UNTESTABLE.
#
# Fixed version (arm B): apply `agentgauge fix`. Fixer adds types + descriptions that
# distinguish get_a from get_b and del_a from del_b. Only metadata changes.
import asyncio

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("obsstore-v4")

_store: dict[int, dict[str, dict]] = {}

_VALID_AGG: frozenset[str] = frozenset({"sum", "min", "max", "avg"})
_VALID_DEL_MODE: frozenset[str] = frozenset({"hard", "soft"})


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="put_x",
            description="Put.",  # DEGRADED
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {"type": "string", "description": "Session identifier for tracking the context"},  # DEGRADED: integer session ID
                    "key": {"type": "string", "description": "Key associated with the value to be stored"},  # DEGRADED: string record key
                    "val": {"type": "string", "description": "The value to be stored"},  # DEGRADED: float measurement value (required)
                    "ts": {"type": "number", "description": "Timestamp indicating when the value was recorded"},  # DEGRADED: integer unix timestamp (required)
                },
                "required": ["key", "sid", "ts", "val"],
                # DEGRADED: missing required
            },
        ),
        types.Tool(
            name="get_a",
            description="Get.",  # DEGRADED: IDENTICAL to get_b
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {"type": "string", "description": "Unique session identifier for tracking requests"},  # DEGRADED: integer session ID
                    "key": {"type": "string", "description": "Authentication token or API key for request validation"},  # DEGRADED: string record key — SAME NAME as get_b
                },
                "required": ["key", "sid"],
                # DEGRADED: missing required
            },
        ),
        types.Tool(
            name="get_b",
            description="Get.",  # DEGRADED: IDENTICAL to get_a
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {"type": "string", "description": "Unique session identifier for tracking the request"},  # DEGRADED: integer session ID
                    "key": {"type": "string", "description": "Authentication key for accessing the service"},  # DEGRADED: aggregation fn ("sum"/"min"/"max"/"avg") — SAME NAME as get_a
                },
                "required": ["key", "sid"],
                # DEGRADED: missing required; key enum not exposed
            },
        ),
        types.Tool(
            name="del_a",
            description="Del.",  # DEGRADED: IDENTICAL to del_b
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {"type": "string", "description": "Session identifier for tracking user context"},  # DEGRADED: integer session ID
                    "key": {"type": "string", "description": "Authentication key or API token for authorization"},  # DEGRADED: record key to delete — SAME NAME as del_b
                },
                "required": ["key", "sid"],
                # DEGRADED: missing required
            },
        ),
        types.Tool(
            name="del_b",
            description="Del.",  # DEGRADED: IDENTICAL to del_a
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {"type": "string", "description": "Unique identifier for the session or record to be deleted"},  # DEGRADED: integer session ID
                    "key": {"type": "string", "description": "Authentication key or API token required for authorization"},  # DEGRADED: delete mode ("hard"/"soft") — SAME NAME as del_a
                },
                "required": ["key", "sid"],
                # DEGRADED: missing required; key enum not exposed
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "put_x":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        key = arguments.get("key")
        if not isinstance(key, str) or not key:
            raise TypeError(f"'key' must be a non-empty string, got {type(key).__name__!r}")
        val = arguments.get("val")
        if val is None:
            raise ValueError("Required field 'val' (measurement value) is missing")
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise TypeError(f"'val' must be a number, got {type(val).__name__!r}")
        ts = arguments.get("ts")
        if ts is None:
            raise ValueError("Required field 'ts' (unix timestamp) is missing")
        if not isinstance(ts, int) or isinstance(ts, bool):
            raise TypeError(f"'ts' must be an integer unix timestamp, got {type(ts).__name__!r}")
        _store.setdefault(sid, {})[key] = {"val": val, "ts": ts}
        return [types.TextContent(type="text", text=f"stored key={key!r} val={val} ts={ts}")]

    if name == "get_a":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        key = arguments.get("key")
        if not isinstance(key, str) or not key:
            raise TypeError(f"'key' must be a non-empty string, got {type(key).__name__!r}")
        entry = _store.get(sid, {}).get(key)
        if entry is None:
            return [types.TextContent(type="text", text=f"not found: sid={sid} key={key!r}")]
        return [types.TextContent(type="text", text=str(entry))]

    if name == "get_b":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        key = arguments.get("key")
        if key is None:
            raise ValueError(
                f"Required field 'key' is missing. Valid values: {sorted(_VALID_AGG)!r}"
            )
        if key not in _VALID_AGG:
            raise ValueError(
                f"'key' must be one of {sorted(_VALID_AGG)!r} for aggregation, got {key!r}"
            )
        records = list(_store.get(sid, {}).values())
        if not records:
            return [types.TextContent(type="text", text="no records")]
        vals = [r["val"] for r in records]
        if key == "sum":
            result: float | int = sum(vals)
        elif key == "min":
            result = min(vals)
        elif key == "max":
            result = max(vals)
        else:  # avg
            result = sum(vals) / len(vals)
        return [types.TextContent(type="text", text=f"{key}={result}")]

    if name == "del_a":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        key = arguments.get("key")
        if not isinstance(key, str) or not key:
            raise TypeError(
                f"'key' must be a non-empty string record key, got {type(key).__name__!r}"
            )
        removed = _store.get(sid, {}).pop(key, None)
        return [
            types.TextContent(
                type="text",
                text=f"deleted key={key!r}" if removed else f"not found: {key!r}",
            )
        ]

    if name == "del_b":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        key = arguments.get("key")
        if key is None:
            raise ValueError(
                f"Required field 'key' (delete mode) is missing. Valid: {sorted(_VALID_DEL_MODE)!r}"
            )
        if key not in _VALID_DEL_MODE:
            raise ValueError(
                f"'key' must be one of {sorted(_VALID_DEL_MODE)!r} for delete mode, got {key!r}"
            )
        n = len(_store.pop(sid, {}))
        return [
            types.TextContent(
                type="text", text=f"deleted session {sid} ({n} records, mode={key!r})"
            )
        ]

    raise ValueError(f"Unknown tool: {name!r}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="obsstore-v4",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
