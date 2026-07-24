from __future__ import annotations

# Spotify Playlists call-correctness fixture — Arm A (vague schemas, no constraints).
#
# 4 tools modeled on real Spotify Web API operations. Arm A schemas show
# type-only ({"type": "string"} / {"type": "integer"}) — no enum, no pattern,
# no description. The agent must rely solely on param names and task text to
# construct valid calls.
#
# Constraint mix (2 tools per type):
#   FORMAT : add_tracks_to_playlist (playlist_id, base62 Spotify ID shape),
#            follow_playlist (playlist_id, same base62 Spotify ID shape)
#   ENUM   : create_playlist (public, "true"/"false" as a string), set_playback_repeat_mode
#            (state, one of "track"/"context"/"off")
#
# Server always echoes success — validation is done by the run script comparing
# result.constructed_args against TASK_CONSTRAINTS, NOT by checking result.success.
#
# See evals/fixtures/v2_4_corpus/spotify_playlists_NOTES.md for which real Spotify
# operations these tools paraphrase.
import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

server = Server("spotify-playlists-arm-a")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Enum-constrained tools ────────────────────────────────────────────
        types.Tool(
            name="create_playlist",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "name": {"type": "string"},
                    "public": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["user_id", "name", "public"],
            },
        ),
        types.Tool(
            name="set_playback_repeat_mode",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "state": {"type": "string"},
                    "device_id": {"type": "string"},
                },
                "required": ["state"],
            },
        ),
        # ── Format-constrained tools ──────────────────────────────────────────
        types.Tool(
            name="add_tracks_to_playlist",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string"},
                    "uris": {"type": "array"},
                    "position": {"type": "integer"},
                },
                "required": ["playlist_id", "uris"],
            },
        ),
        types.Tool(
            name="follow_playlist",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string"},
                    "public": {"type": "string"},
                },
                "required": ["playlist_id"],
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
                server_name="spotify-playlists-arm-a",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
