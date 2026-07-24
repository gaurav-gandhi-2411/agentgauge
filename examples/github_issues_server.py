from __future__ import annotations

# GitHub Issues call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real GitHub Issues REST API operations.
# Arm A schemas show type-only ({"type": "string"} / {"type": "integer"}) —
# no enum, no pattern, no description. The agent must rely solely on param
# names and task text to construct valid calls.
#
# Constraint mix (2 tools per type):
#   FORMAT : create_issue (repo, "owner/repo" shape), add_assignee (assignee,
#            GitHub username shape)
#   ENUM   : update_issue_state (state, state_reason), add_label (label, one
#            of GitHub's standard default repository labels)
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

server = Server("github-issues-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format-constrained tools ─────────────────────────────────────────
        types.Tool(
            name="create_issue",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "labels": {"type": "array"},
                    "assignee": {"type": "string"},
                },
                "required": ["repo", "title"],
            },
        ),
        types.Tool(
            name="add_assignee",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                    "assignee": {"type": "string"},
                },
                "required": ["repo", "issue_number", "assignee"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="update_issue_state",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                    "state": {"type": "string"},
                    "state_reason": {"type": "string"},
                },
                "required": ["repo", "issue_number", "state"],
            },
        ),
        types.Tool(
            name="add_label",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "issue_number": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["repo", "issue_number", "label"],
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
                server_name="github-issues-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
