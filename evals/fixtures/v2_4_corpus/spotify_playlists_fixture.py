from __future__ import annotations

# Spotify Playlists call-correctness fixture — pre-registered tasks and gold constraints.
#
# Corpus-expansion effort (v2_4_corpus): a real-domain sibling to the synthetic
# call_constraints_v2 fixture (evals/fixtures/ty2_tasks.py), modeled on Spotify's
# real Web API instead of an invented industrial-sensor domain.
#
# 4 tools, all constrained — 5 tasks each = 20 tasks.
# Constraint mix (2 tools per type), mirroring ty2_tasks.py's "2 per type" design:
#   ENUM   : create_playlist (public, "true"/"false" as a string)
#            set_playback_repeat_mode (state, "track"/"context"/"off")
#   FORMAT : add_tracks_to_playlist (playlist_id, base62 Spotify ID shape)
#            follow_playlist (playlist_id, same base62 Spotify ID shape)
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only. They must NOT
# contain the literal enum value (e.g. "true", "off") or the literal format
# shape (e.g. an actual 22-character playlist ID) that the agent is meant to
# construct. The agent must derive the correct value from the tool's
# SCHEMA/description (fixed variant) or fail correctly (bad variant), not from
# the task text.
#
# See spotify_playlists_NOTES.md for provenance of the real Spotify API fields used.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

TASKS: list[Task] = [
    # create_playlist (enum constraint on `public`, "true"/"false" as a string) — 5 tasks
    Task(
        "create_playlist",
        "Create a playlist for Jordan's road trip mix that anyone browsing his profile "
        "can find and listen to.",
    ),
    Task(
        "create_playlist",
        "Set up a playlist for Mia's personal workout mix that she wants to keep just "
        "for her own listening, not shown to anyone else.",
    ),
    Task(
        "create_playlist",
        "Make a playlist for the office holiday party that the whole team can discover "
        "and share with friends outside the company.",
    ),
    Task(
        "create_playlist",
        "Start a study-music playlist for Sam that he'd rather keep off his profile "
        "entirely, just for himself.",
    ),
    Task(
        "create_playlist",
        "Build a playlist of the podcast's weekly picks that listeners can find by "
        "browsing the show's profile.",
    ),
    # set_playback_repeat_mode (enum constraint on `state`) — 5 tasks
    Task(
        "set_playback_repeat_mode",
        "Sam just found a song he can't stop listening to — set playback so it loops "
        "over and over indefinitely.",
    ),
    Task(
        "set_playback_repeat_mode",
        "Get the current album cycling through all its tracks continuously during the "
        "dinner party.",
    ),
    Task(
        "set_playback_repeat_mode",
        "Turn off any looping behavior for the current playback session.",
    ),
    Task(
        "set_playback_repeat_mode",
        "Priya wants this one track to keep playing again and again while she's cooking.",
    ),
    Task(
        "set_playback_repeat_mode",
        "Keep the whole playlist cycling round for the entire length of the road trip.",
    ),
    # add_tracks_to_playlist (format constraint on `playlist_id`, base62 shape) — 5 tasks
    Task(
        "add_tracks_to_playlist",
        "Add the new single from Tame Impala to Elena's Friday night playlist.",
    ),
    Task(
        "add_tracks_to_playlist",
        "Drop three tracks off Kendrick Lamar's latest album into the office workout playlist.",
    ),
    Task(
        "add_tracks_to_playlist",
        "Add that live acoustic version of a Bon Iver song to Marcus's chill evening playlist.",
    ),
    Task(
        "add_tracks_to_playlist",
        "Queue up the extended remix of a Daft Punk track into the summer road trip playlist.",
    ),
    Task(
        "add_tracks_to_playlist",
        "Add the title track from Billie Eilish's new album to the study focus playlist.",
    ),
    # follow_playlist (format constraint on `playlist_id`, base62 shape) — 5 tasks
    Task(
        "follow_playlist",
        "Save that curated indie playlist a friend just shared with Diego to his own library.",
    ),
    Task(
        "follow_playlist",
        "Have Sofia follow the running crew's shared workout playlist so it shows up in "
        "her library.",
    ),
    Task(
        "follow_playlist",
        "Add the record label's official new-release playlist to Marcus's followed playlists.",
    ),
    Task(
        "follow_playlist",
        "Get Priya following the neighborhood jazz cafe's ambient background playlist.",
    ),
    Task(
        "follow_playlist",
        "Follow the community-curated best-of-the-decade playlist for Tom.",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Enum tasks: gold_value is the specific expected enum member.
# Format tasks: no gold value — any value matching the pattern counts.
TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # create_playlist — enum: public ("true"/"false" as a string)
    (
        "create_playlist",
        "Create a playlist for Jordan's road trip mix that anyone browsing his profile "
        "can find and listen to.",
    ): [Constraint("public", "enum", gold_value="true")],
    (
        "create_playlist",
        "Set up a playlist for Mia's personal workout mix that she wants to keep just "
        "for her own listening, not shown to anyone else.",
    ): [Constraint("public", "enum", gold_value="false")],
    (
        "create_playlist",
        "Make a playlist for the office holiday party that the whole team can discover "
        "and share with friends outside the company.",
    ): [Constraint("public", "enum", gold_value="true")],
    (
        "create_playlist",
        "Start a study-music playlist for Sam that he'd rather keep off his profile "
        "entirely, just for himself.",
    ): [Constraint("public", "enum", gold_value="false")],
    (
        "create_playlist",
        "Build a playlist of the podcast's weekly picks that listeners can find by "
        "browsing the show's profile.",
    ): [Constraint("public", "enum", gold_value="true")],
    # set_playback_repeat_mode — enum: state (track/context/off)
    (
        "set_playback_repeat_mode",
        "Sam just found a song he can't stop listening to — set playback so it loops "
        "over and over indefinitely.",
    ): [Constraint("state", "enum", gold_value="track")],
    (
        "set_playback_repeat_mode",
        "Get the current album cycling through all its tracks continuously during the "
        "dinner party.",
    ): [Constraint("state", "enum", gold_value="context")],
    (
        "set_playback_repeat_mode",
        "Turn off any looping behavior for the current playback session.",
    ): [Constraint("state", "enum", gold_value="off")],
    (
        "set_playback_repeat_mode",
        "Priya wants this one track to keep playing again and again while she's cooking.",
    ): [Constraint("state", "enum", gold_value="track")],
    (
        "set_playback_repeat_mode",
        "Keep the whole playlist cycling round for the entire length of the road trip.",
    ): [Constraint("state", "enum", gold_value="context")],
    # add_tracks_to_playlist — format: base62 Spotify playlist ID
    (
        "add_tracks_to_playlist",
        "Add the new single from Tame Impala to Elena's Friday night playlist.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    (
        "add_tracks_to_playlist",
        "Drop three tracks off Kendrick Lamar's latest album into the office workout playlist.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    (
        "add_tracks_to_playlist",
        "Add that live acoustic version of a Bon Iver song to Marcus's chill evening playlist.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    (
        "add_tracks_to_playlist",
        "Queue up the extended remix of a Daft Punk track into the summer road trip playlist.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    (
        "add_tracks_to_playlist",
        "Add the title track from Billie Eilish's new album to the study focus playlist.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    # follow_playlist — format: base62 Spotify playlist ID
    (
        "follow_playlist",
        "Save that curated indie playlist a friend just shared with Diego to his own library.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    (
        "follow_playlist",
        "Have Sofia follow the running crew's shared workout playlist so it shows up in "
        "her library.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    (
        "follow_playlist",
        "Add the record label's official new-release playlist to Marcus's followed playlists.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    (
        "follow_playlist",
        "Get Priya following the neighborhood jazz cafe's ambient background playlist.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
    (
        "follow_playlist",
        "Follow the community-curated best-of-the-decade playlist for Tom.",
    ): [Constraint("playlist_id", "format", pattern=r"[A-Za-z0-9]{22}")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["create_playlist", "set_playback_repeat_mode", "add_tracks_to_playlist", "follow_playlist"]
)
ENUM_TOOL_NAMES: frozenset[str] = frozenset(["create_playlist", "set_playback_repeat_mode"])
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["add_tracks_to_playlist", "follow_playlist"])

# Enum gold values referenced in tasks (for inferability tests)
ENUM_GOLD_VALUES: list[str] = ["true", "false", "track", "context", "off"]
# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    r"[A-Za-z0-9]{22}",
    "3cEYpjA9oz9GiPac4AsH4n",
]
