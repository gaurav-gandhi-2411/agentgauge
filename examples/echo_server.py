from __future__ import annotations

import asyncio

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("echo-demo")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="echo",
            description=(
                "Echo a message back to the caller. "
                "Useful for testing connectivity and round-trip latency."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The text to echo back",
                    }
                },
                "required": ["message"],
            },
        ),
        types.Tool(
            name="add",
            description="Add two integers and return their sum.",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {
                        "type": "integer",
                        "description": "First operand",
                    },
                    "b": {
                        "type": "integer",
                        "description": "Second operand",
                    },
                },
                "required": ["a", "b"],
            },
        ),
        # Intentionally poor schema — no descriptions, no types — to show the scorer working
        types.Tool(
            name="mystery",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {},
                    "y": {},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "echo":
        return [types.TextContent(type="text", text=arguments.get("message", ""))]
    if name == "add":
        result = int(arguments.get("a", 0)) + int(arguments.get("b", 0))
        return [types.TextContent(type="text", text=str(result))]
    if name == "mystery":
        return [types.TextContent(type="text", text="???")]
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="echo-demo",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(), experimental_capabilities={}
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
