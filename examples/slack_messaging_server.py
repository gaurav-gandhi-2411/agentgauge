from __future__ import annotations

# Slack messaging call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real Slack Web API operations, 3 hard (constrained params)
# + 1 easy (no constrained param). Arm A schemas show type-only
# ({"type": "string"}) — no enum, no pattern, no description. The agent must
# rely solely on param names and task text to construct valid calls.
#
# Constraint mix:
#   FORMAT : post_message (channel, Slack channel-reference shape),
#            invite_to_channel (user, Slack user-ID shape)
#   ENUM   : set_user_presence (presence, "auto"/"away")
#   (inert): set_channel_topic (no constrained param — not used in tasks)
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against TASK_CONSTRAINTS, NOT by checking result.success.
#
# See evals/fixtures/v2_4_corpus/slack_messaging_NOTES.md for which real Slack
# Web API operations these tools paraphrase.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("slack-messaging-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Format-constrained tools ─────────────────────────────────────────
        types.Tool(
            name="post_message",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "text": {"type": "string"},
                    "thread_ts": {"type": "string"},
                },
                "required": ["channel", "text"],
            },
        ),
        types.Tool(
            name="invite_to_channel",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "user": {"type": "string"},
                },
                "required": ["channel", "user"],
            },
        ),
        # ── Enum-constrained tool ─────────────────────────────────────────────
        types.Tool(
            name="set_user_presence",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "presence": {"type": "string"},
                },
                "required": ["presence"],
            },
        ),
        # ── Inert tool (no constrained param — not used in TASKS) ────────────
        types.Tool(
            name="set_channel_topic",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "topic": {"type": "string"},
                },
                "required": ["channel", "topic"],
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
                server_name="slack-messaging-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
