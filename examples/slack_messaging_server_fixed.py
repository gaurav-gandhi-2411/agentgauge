from __future__ import annotations

# Slack messaging call-correctness fixture — Arm A (vague schemas, no constraints).
#
# Same 4 tools as slack_messaging_server.py. inputSchema is IDENTICAL to the
# Arm A variant (still type-only — no enum, no pattern keywords) so the only
# difference under test is whether the agent can construct correct calls from
# the Tool.description text alone.
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
            description=(
                "Posts a message into a Slack channel, private group, or direct message. "
                "Parameters: channel (string) — the destination, given either as a "
                "channel name prefixed with '#' (e.g. '#general') or as Slack's internal "
                "encoded channel ID (a 'C', 'G', or 'D' followed by 8-10 uppercase "
                "alphanumeric characters, e.g. 'C0G9QF9GZ'); text (string) — the message "
                "body to post; thread_ts (string, optional) — the timestamp of an "
                "existing message to reply to in a thread, omitted to post a new "
                "top-level message. Unlike invite_to_channel or set_channel_topic, this "
                "tool sends a message rather than changing channel membership or metadata."
            ),
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
            description=(
                "Invites a single user into an existing Slack channel. Parameters: "
                "channel (string) — the channel's name (e.g. '#engineering') or encoded "
                "channel ID; user (string) — the Slack user ID of the person to invite, "
                "given as Slack's internal encoded user ID (a 'U' followed by 8-10 "
                "uppercase alphanumeric characters, e.g. 'U012AB3CDE') rather than a "
                "display name or email address. Unlike post_message, this tool changes "
                "who belongs to a channel; it does not send any message."
            ),
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
            description=(
                "Sets the calling user's own Slack presence. Parameters: presence "
                "(string) — one of 'auto' (let Slack determine active/away status from "
                "the user's real activity, the normal default behavior) or 'away' "
                "(force the user's status to show as away regardless of actual "
                "activity, until explicitly changed back to 'auto'). Unlike the other "
                "tools in this server, this tool affects the caller's own visibility "
                "status, not a channel or message."
            ),
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
            description=(
                "Sets the topic displayed at the top of a Slack channel. Parameters: "
                "channel (string) — the channel's name or encoded channel ID; topic "
                "(string) — the free-text topic line to display, up to 250 characters. "
                "Unlike post_message, the topic is a persistent piece of channel "
                "metadata visible to anyone who opens the channel, not a message in the "
                "conversation history."
            ),
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
