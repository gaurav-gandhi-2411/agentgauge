from __future__ import annotations

# Jira Issues call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real Atlassian Jira REST API (v3) Issues operations.
# Arm A schemas show type-only ({"type": "string"}) — no enum, no pattern, no
# description. The agent must rely solely on param names and task text to
# construct valid calls.
#
# Constraint mix:
#   FORMAT : create_issue (project_key, 2-10 uppercase-letter Jira project key
#            shape), add_issue_comment (issue_key, "PROJ-123" issue-key shape)
#   ENUM   : create_issue (issue_type, one of Jira's default issue types),
#            transition_issue (transition, one of a default Jira workflow's
#            status names), set_issue_priority (priority, Jira's default
#            priority scheme)
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

server = Server("jira-issues-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format + enum constrained tool ───────────────────────────────────
        types.Tool(
            name="create_issue",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string"},
                    "issue_type": {"type": "string"},
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["project_key", "issue_type", "summary"],
            },
        ),
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="transition_issue",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "transition": {"type": "string"},
                },
                "required": ["issue_key", "transition"],
            },
        ),
        types.Tool(
            name="set_issue_priority",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "priority": {"type": "string"},
                },
                "required": ["issue_key", "priority"],
            },
        ),
        # ── Format-constrained tool ───────────────────────────────────────────
        types.Tool(
            name="add_issue_comment",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "comment_body": {"type": "string"},
                },
                "required": ["issue_key", "comment_body"],
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
                server_name="jira-issues-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
