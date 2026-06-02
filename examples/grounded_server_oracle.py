from __future__ import annotations

# Tx upside fixture — arm B, ORACLE descriptions (hand-written, step 1).
# Identical to grounded_server.py except descriptions are the pre-registered ORACLE.
# Used for upside step 1: does a good description improve selection vs arm A (empty desc)?

import asyncio
import math

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("transform-pipeline-v1-oracle")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="transform_scale",
            description=(
                "Applies a linear (affine) transformation: result = value * factor + offset "
                "(offset defaults to 0). Use for gain adjustment, attenuation, or unit scaling. "
                "NOT for mapping to [0,1] — use transform_normalize for that."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {},
                    "factor": {},
                    "offset": {"default": 0.0},
                },
                "required": ["value", "factor"],
            },
        ),
        types.Tool(
            name="transform_normalize",
            description=(
                "Maps value to the unit interval [0, 1] using min-max normalization: "
                "result = (value - low) / (high - low). Use when you need a proportional "
                "fraction of a known range."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {},
                    "low": {},
                    "high": {},
                },
                "required": ["value", "low", "high"],
            },
        ),
        types.Tool(
            name="transform_clip",
            description=(
                "Clamps value to [lower, upper]: returns lower if value < lower, upper if "
                "value > upper, else value unchanged. Use to enforce hard bounds on a value."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {},
                    "lower": {},
                    "upper": {},
                },
                "required": ["value", "lower", "upper"],
            },
        ),
        types.Tool(
            name="transform_round",
            description=(
                "Returns value rounded to the specified number of decimal places (default 2). "
                "Use for precision reduction or display formatting."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {},
                    "places": {"default": 2},
                },
                "required": ["value"],
            },
        ),
        types.Tool(
            name="transform_log",
            description=(
                "Computes the logarithm of value in the given base (default e ≈ 2.718, "
                "natural log). Use when the task says 'ln', 'log₂', or 'log base N'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {},
                    "base": {"default": math.e},
                },
                "required": ["value"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "transform_scale":
        value = float(arguments["value"])
        factor = float(arguments["factor"])
        offset = float(arguments.get("offset", 0.0))
        return [types.TextContent(type="text", text=str(value * factor + offset))]

    if name == "transform_normalize":
        value = float(arguments["value"])
        low = float(arguments["low"])
        high = float(arguments["high"])
        if high == low:
            raise ValueError("'high' and 'low' must differ")
        return [types.TextContent(type="text", text=str((value - low) / (high - low)))]

    if name == "transform_clip":
        value = float(arguments["value"])
        lower = float(arguments["lower"])
        upper = float(arguments["upper"])
        return [types.TextContent(type="text", text=str(max(lower, min(upper, value))))]

    if name == "transform_round":
        value = float(arguments["value"])
        places = int(arguments.get("places", 2))
        return [types.TextContent(type="text", text=str(round(value, places)))]

    if name == "transform_log":
        value = float(arguments["value"])
        base = float(arguments.get("base", math.e))
        if value <= 0:
            raise ValueError(f"'value' must be positive for log, got {value}")
        if base <= 0 or base == 1:
            raise ValueError(f"'base' must be > 0 and != 1, got {base}")
        result = math.log(value) / math.log(base)
        return [types.TextContent(type="text", text=str(result))]

    raise ValueError(f"Unknown tool: {name!r}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="transform-pipeline-v1-oracle",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
