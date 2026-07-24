from __future__ import annotations

# Docker Engine API call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real Docker Engine API operations.
# Arm A schemas show type-only ({"type": "string"} / {"type": "integer"}) —
# no enum, no pattern, no description. The agent must rely solely on param
# names and task text to construct valid calls.
#
# Constraint mix:
#   FORMAT : create_container (image, "name:tag" shape), tag_image (tag, Docker
#            tag-name shape)
#   ENUM   : create_container (restart_policy, Docker's real RestartPolicy.Name
#            values), create_network (driver, a subset of Docker's real
#            built-in network drivers)
#   RANGE  : stop_container (timeout_seconds, graceful-shutdown grace period)
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against TASK_CONSTRAINTS, NOT by checking result.success.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("docker-containers-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format + enum constrained tool ───────────────────────────────────
        types.Tool(
            name="create_container",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "image": {"type": "string"},
                    "name": {"type": "string"},
                    "restart_policy": {"type": "string"},
                    "env": {"type": "array"},
                },
                "required": ["image", "restart_policy"],
            },
        ),
        # ── Range-constrained tool ────────────────────────────────────────────
        types.Tool(
            name="stop_container",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "container_id": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                },
                "required": ["container_id", "timeout_seconds"],
            },
        ),
        # ── Enum-constrained tool ─────────────────────────────────────────────
        types.Tool(
            name="create_network",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "driver": {"type": "string"},
                    "internal": {"type": "boolean"},
                },
                "required": ["name", "driver"],
            },
        ),
        # ── Format-constrained tool ───────────────────────────────────────────
        types.Tool(
            name="tag_image",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_image": {"type": "string"},
                    "repo": {"type": "string"},
                    "tag": {"type": "string"},
                },
                "required": ["source_image", "repo", "tag"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    # Always echo success — correctness scoring happens in the run script via constructed_args.
    result = json.dumps({"tool": name, "args": arguments})
    return [types.TextContent(type="text", text=result)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="docker-containers-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
