from __future__ import annotations

# T16 held-out fixture — arm A (degraded). ObsStore API — run #2.
#
# Previous fixture (TaskTracker, run #1) was VOID: arm A saturated at 100% because parameter
# names (title, task_id, priority) were semantically obvious to gemma2:9b. This fixture is
# hardened with opaque tool names + confusable pairs so arm A actually fails.
#
# Degradations (pre-registered for T16 A/B experiment, run #2):
#
# 1. put_x: description "Put." (vague).
#    Parameters sid/rid/x/t have no type, no description, no required array.
#    - x = numeric measurement value (float); t = unix timestamp (integer).
#    - Names are opaque; without schema guidance the agent may omit x/t entirely
#      (they are not mentioned in the task description) → Required-field failures.
#    PRE-REGISTERED: arm A call_correctness failure from missing x/t.
#
# 2. get_a: description "Get." IDENTICAL to get_b — confusable pair.
#    Parameters sid/rid with no type, no description, no required.
#    - Purpose: retrieve a specific stored data point by record ID.
#    PRE-REGISTERED: arm A selection_accuracy ≈ 50% for get_a/get_b tasks because
#    both tools have the same description and opaque suffixes (a vs b give no signal).
#
# 3. get_b: description "Get." IDENTICAL to get_a — confusable pair.
#    Parameters sid/op with no type, no description, no required.
#    - Purpose: compute an aggregate statistic (op = "mean"/"min"/"max"/"count").
#    - op is strictly validated server-side; without a description listing valid values,
#      the agent may pass "average"/"sum"/"total" → enum validation failure.
#    PRE-REGISTERED: arm A call_correctness failure from invalid op values.
#
# 4. del_a: description "Del." IDENTICAL to del_b — confusable pair.
#    Parameters sid/rid with no type, no description, no required.
#    - Purpose: delete a specific data point by record ID.
#    PRE-REGISTERED: arm A selection_accuracy ≈ 50% for del_a/del_b tasks.
#
# 5. del_b: description "Del." IDENTICAL to del_a — confusable pair.
#    Parameters sid with no type, no description, no required.
#    - Purpose: delete all data points for an entire session.
#    PRE-REGISTERED: arm A selection_accuracy ≈ 50% for del_a/del_b tasks.
#
# Fixed version (arm B): apply `agentgauge fix` on this file with qwen3:8b generator.
# The fixer adds types + descriptions to params and distinct descriptions to each tool.
# Only metadata changes; behavior is identical.
import asyncio

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("obsstore-mediocre")

# In-memory store: {session_id: {record_id: {x, t}}}
_store: dict[int, dict[str, dict]] = {}

_VALID_OPS: frozenset[str] = frozenset({"mean", "min", "max", "count"})


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="put_x",
            description="Put.",  # DEGRADED: vague, no param guidance
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {},  # DEGRADED: should be integer session ID
                    "rid": {},  # DEGRADED: should be string record ID
                    "x": {},  # DEGRADED: should be float measurement value (required)
                    "t": {},  # DEGRADED: should be integer unix timestamp (required)
                },
                # DEGRADED: missing required — agent has no signal x and t are required
            },
        ),
        types.Tool(
            name="get_a",
            description="Get.",  # DEGRADED: identical to get_b — confusable pair
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {},  # DEGRADED: integer session ID
                    "rid": {},  # DEGRADED: string record ID
                },
                # DEGRADED: missing required
            },
        ),
        types.Tool(
            name="get_b",
            description="Get.",  # DEGRADED: identical to get_a — confusable pair
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {},  # DEGRADED: integer session ID
                    "op": {},  # DEGRADED: string enum "mean"/"min"/"max"/"count" — no hint
                },
                # DEGRADED: missing required; op enum not exposed
            },
        ),
        types.Tool(
            name="del_a",
            description="Del.",  # DEGRADED: identical to del_b — confusable pair
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {},  # DEGRADED: integer session ID
                    "rid": {},  # DEGRADED: string record ID
                },
                # DEGRADED: missing required
            },
        ),
        types.Tool(
            name="del_b",
            description="Del.",  # DEGRADED: identical to del_a — confusable pair
            inputSchema={
                "type": "object",
                "properties": {
                    "sid": {},  # DEGRADED: integer session ID
                },
                # DEGRADED: missing required
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
            raise TypeError(
                f"'sid' must be an integer session ID, got {type(sid).__name__!r}. "
                'Example: {"sid": 1}'
            )
        rid = arguments.get("rid")
        if not isinstance(rid, str) or not rid:
            raise TypeError(
                f"'rid' must be a non-empty string record ID, got {type(rid).__name__!r}. "
                'Example: {"rid": "r-001"}'
            )
        x = arguments.get("x")
        if x is None:
            raise ValueError(
                "Required field 'x' (numeric measurement value) is missing. Example: {\"x\": 4.2}"
            )
        if not isinstance(x, (int, float)) or isinstance(x, bool):
            raise TypeError(
                f"'x' must be a number (int or float), got {type(x).__name__!r}. "
                'Example: {"x": 4.2}'
            )
        t = arguments.get("t")
        if t is None:
            raise ValueError(
                "Required field 't' (unix timestamp integer) is missing. "
                'Example: {"t": 1717200000}'
            )
        if not isinstance(t, int) or isinstance(t, bool):
            raise TypeError(
                f"'t' must be an integer unix timestamp, got {type(t).__name__!r}. "
                'Example: {"t": 1717200000}'
            )
        _store.setdefault(sid, {})[rid] = {"x": x, "t": t}
        return [types.TextContent(type="text", text=f"Stored: sid={sid} rid={rid!r} x={x} t={t}")]

    if name == "get_a":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        rid = arguments.get("rid")
        if not isinstance(rid, str) or not rid:
            raise TypeError(f"'rid' must be a non-empty string, got {type(rid).__name__!r}")
        entry = _store.get(sid, {}).get(rid)
        if entry is None:
            return [types.TextContent(type="text", text=f"Not found: sid={sid} rid={rid!r}")]
        return [types.TextContent(type="text", text=str(entry))]

    if name == "get_b":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        op = arguments.get("op")
        if op is None:
            raise ValueError(
                f"Required field 'op' is missing. Valid values: {sorted(_VALID_OPS)!r}"
            )
        if op not in _VALID_OPS:
            raise ValueError(
                f"'op' must be one of {sorted(_VALID_OPS)!r}, got {op!r}. "
                "Use 'mean', 'min', 'max', or 'count'."
            )
        records = list(_store.get(sid, {}).values())
        if not records:
            return [types.TextContent(type="text", text="No records found")]
        vals = [r["x"] for r in records]
        if op == "mean":
            result: float | int = sum(vals) / len(vals)
        elif op == "min":
            result = min(vals)
        elif op == "max":
            result = max(vals)
        else:  # count
            result = len(vals)
        return [types.TextContent(type="text", text=f"{op}={result}")]

    if name == "del_a":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        rid = arguments.get("rid")
        if not isinstance(rid, str) or not rid:
            raise TypeError(f"'rid' must be a non-empty string, got {type(rid).__name__!r}")
        removed = _store.get(sid, {}).pop(rid, None)
        return [
            types.TextContent(
                type="text",
                text=f"Deleted: sid={sid} rid={rid!r}" if removed else f"Not found: {rid!r}",
            )
        ]

    if name == "del_b":
        sid = arguments.get("sid")
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise TypeError(f"'sid' must be an integer, got {type(sid).__name__!r}")
        n = len(_store.pop(sid, {}))
        return [types.TextContent(type="text", text=f"Deleted session {sid} ({n} records)")]

    raise ValueError(f"Unknown tool: {name!r}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="obsstore-mediocre",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
