from __future__ import annotations

# Spotify Playlists call-correctness fixture — Arm F (same schemas as Arm A, real
# descriptions restored).
#
# Same 4 tools as spotify_playlists_server.py. inputSchema is IDENTICAL to the Arm
# A variant (still type-only — no enum, no pattern keywords) so the only
# difference under test is whether the agent can construct correct calls from
# the Tool.description text alone.
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
            description=(
                "Creates a new, empty playlist owned by the given Spotify user. Requires "
                "user_id (the owning user's Spotify user ID), name (the playlist's display "
                "name), and public — the string 'true' if the playlist should be visible on "
                "the owner's public profile and discoverable by other users, or 'false' if it "
                "should be private and visible only to the owner. Optionally accepts "
                "description (shown under the playlist's name). Unlike add_tracks_to_playlist "
                "or follow_playlist, this tool creates a brand-new, empty playlist rather than "
                "modifying or following one that already exists."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "name": {"type": "string"},
                    "public": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name", "user_id", "public"],
            },
        ),
        types.Tool(
            name="set_playback_repeat_mode",
            description=(
                "Sets the repeat behavior for the user's current playback session. Requires "
                "state, one of: 'track' (repeat the single currently playing track "
                "indefinitely), 'context' (repeat the current playlist or album as a whole, "
                "cycling through its tracks), or 'off' (disable repeat entirely and let "
                "playback stop normally at the end). Optionally accepts device_id to target a "
                "specific device instead of the user's currently active one. Unlike "
                "create_playlist or add_tracks_to_playlist, this tool changes live playback "
                "behavior rather than a playlist's contents or metadata."
            ),
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
            description=(
                "Adds one or more tracks to an existing playlist. Requires playlist_id (the "
                "target playlist's Spotify ID — a 22-character base62 string, e.g. "
                "'3cEYpjA9oz9GiPac4AsH4n') and uris (a list of Spotify track URIs, each in "
                "the form 'spotify:track:{track_id}'). Optionally accepts position (the "
                "zero-based index at which to insert the new tracks; omitted means append to "
                "the end). Unlike follow_playlist, this tool changes a playlist's track "
                "listing rather than the calling user's relationship to the playlist."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "playlist_id": {"type": "string"},
                    "uris": {"type": "array"},
                    "position": {"type": "integer"},
                },
                "required": ["uris", "playlist_id"],
            },
        ),
        types.Tool(
            name="follow_playlist",
            description=(
                "Makes the current user a follower of an existing playlist, adding it to "
                "their library the same way clicking 'Follow' in the Spotify app would. "
                "Requires playlist_id (the target playlist's Spotify ID — a 22-character "
                "base62 string, the same ID shape used by add_tracks_to_playlist). "
                "Optionally accepts public (the string 'true' or 'false') to control whether "
                "this playlist shows up in the user's public list of followed playlists. "
                "Unlike add_tracks_to_playlist, this tool does not modify the playlist's "
                "contents at all — it only changes whether the calling user follows it."
            ),
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
