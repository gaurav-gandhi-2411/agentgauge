from __future__ import annotations

# Tx upside fixture — arm A (grounded names, empty descriptions).
#
# Tools: numeric transform pipeline. All tool names have meaningful domain tokens
# so the grounding detector passes and the fixer generates (no ABSTAIN).
#
# Pre-registered ORACLE descriptions (arm B for upside step 1):
#   transform_scale:
#     "Applies a linear (affine) transformation: result = value * factor + offset
#      (offset defaults to 0). Use for gain adjustment, attenuation, or unit scaling.
#      NOT for mapping to [0,1] — use transform_normalize for that."
#   transform_normalize:
#     "Maps value to the unit interval [0, 1] using min-max normalization:
#      result = (value - low) / (high - low). Use when you need a proportional
#      fraction of a known range."
#   transform_clip:
#     "Clamps value to [lower, upper]: returns lower if value < lower, upper if
#      value > upper, else value unchanged. Use to enforce hard bounds on a value."
#   transform_round:
#     "Returns value rounded to the specified number of decimal places (default 2).
#      Use for precision reduction or display formatting."
#   transform_log:
#     "Computes the logarithm of value in the given base (default e ≈ 2.718,
#      natural log). Use when the task says 'ln', 'log₂', or 'log base N'."
#
# Pre-registered A/B tasks (10 tasks, 2 per tool):
#   ("transform_scale", "Multiply 4.0 by 2.5 and add 0.5 to the result")
#   ("transform_scale", "Apply a 50% amplitude reduction and subtract 3.0 from value 8.0")
#   ("transform_normalize", "Express 7.0 as a fraction of the range [0, 10]")
#   ("transform_normalize", "Rescale 25.0 to fit between 0 and 1, given original bounds 0 and 50")
#   ("transform_clip", "Ensure value 105 does not exceed 100 and is at least 0")
#   ("transform_clip", "Cap measurement -2.5 so it stays within the valid range [0, 50]")
#   ("transform_round", "Express 3.14159265 to 4 decimal places")
#   ("transform_round", "Reduce precision of 99.9999 to at most 2 decimal places")
#   ("transform_log", "What is ln(10.0)?")
#   ("transform_log", "Compute log base 2 of 8.0")
#
# Pre-registered expected direction (all): arm B (oracle/fixer) > arm A on selection_accuracy
# when descriptions resolve normalize-vs-scale and log ambiguity.
# Global-abstain branch activated if oracle cannot beat arm A (see spec.md).

import asyncio
import math

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("transform-pipeline-v1")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="transform_scale",
            description="The transform_scale tool scales a value by a specified factor and adds an optional offset (default 0.0). It requires 'value' and 'factor' parameters, with 'offset' being optional.",  # DEGRADED: empty
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "The value to be transformed by scaling"},
                    "factor": {"type": "number", "description": "The factor by which to multiply the value"},
                    "offset": {"default": 0.0},
                },
                "required": ["factor", "value"],
            },
        ),
        types.Tool(
            name="transform_normalize",
            description="Normalizes a single value to a specified range [low, high] by linearly scaling it between the given minimum and maximum values. Key parameters: 'value' (input value to normalize), 'low' (target minimum), 'high' (target maximum); differs from similar tools by focusing on individual value scaling rather than batch data normalization.",  # DEGRADED: empty
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "The value to be normalized"},
                    "low": {"type": "number", "description": "The lower bound of the target range"},
                    "high": {"type": "number", "description": "The upper bound of the target range"},
                },
                "required": ["high", "low", "value"],
            },
        ),
        types.Tool(
            name="transform_clip",
            description="Clips a numerical value to a specified range defined by lower and upper bounds. Takes 'value' (input number), 'lower' (minimum allowed value), and 'upper' (maximum allowed value) to ensure output stays within the range, unlike tools that handle strings or non-numeric data.",  # DEGRADED: empty
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "The value to be clipped"},
                    "lower": {"type": "number", "description": "The lower bound for clipping"},
                    "upper": {"type": "number", "description": "The upper bound for clipping"},
                },
                "required": ["lower", "upper", "value"],
            },
        ),
        types.Tool(
            name="transform_round",
            description="The transform_round tool rounds a numerical value to a specified number of decimal places, using 'value' as the input number and 'places' (defaulting to 2) to determine precision, offering customizable rounding for precise decimal control.",  # DEGRADED: empty
            inputSchema={
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "The numeric value to be rounded"},
                    "places": {"default": 2},
                },
                "required": ["value"],
            },
        ),
        types.Tool(
            name="transform_log",
            description="The transform_log tool calculates the logarithm of a given value using a specified base, with a default base of e (Euler's number). It accepts 'value' (the input number) and 'base' (the logarithm base, defaulting to e), offering flexibility for natural or other logarithmic transformations.",  # DEGRADED: empty
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
                server_name="transform-pipeline-v1",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
