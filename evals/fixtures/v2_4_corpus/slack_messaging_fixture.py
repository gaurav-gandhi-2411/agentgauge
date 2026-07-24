from __future__ import annotations

# Slack-messaging pre-registered tasks and constraints for the call-correctness
# oracle A/B (v2.4 corpus expansion, Task 4 — real-API domain corpus entry).
#
# 4 tools modeled on real Slack Web API operations (see
# slack_messaging_NOTES.md): post_message, invite_to_channel,
# set_user_presence, set_channel_topic. set_channel_topic has no genuine
# constrained parameter and is deliberately excluded from TASKS/
# TASK_CONSTRAINTS (inert tool, present only to give the fixture a realistic
# 4th operation — mirrors stripe_payments_fixture.py's create_customer).
#
# 15 tasks: 5 per constrained tool x 3 constrained tools — ALL hard, NO inert
# easy tasks (mirrors stripe_payments_fixture.py's design).
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only. They must
# NOT contain the literal enum value ("auto", "away") or the literal format
# shape (an actual "#channel-name"/encoded-channel-ID string, or an actual
# "U..."-shaped user-ID token) that the agent is meant to construct. The agent
# must derive the correct value from the tool's SCHEMA/description (fixed
# variant) or fail correctly (bad variant), not from the task text.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

# Shared FORMAT patterns (simplifications of Slack's real conventions — see
# slack_messaging_NOTES.md for exact provenance/limitations of each).
_CHANNEL_REF_PATTERN = r"#[a-z0-9_-]+|[CGD][A-Z0-9]{8,10}"
_USER_ID_PATTERN = r"U[A-Z0-9]{8,10}"

TASKS: list[Task] = [
    # ── post_message (format constraint on `channel`) — 5 tasks ─────────────
    Task(
        "post_message",
        "Post a message in the engineering team's channel announcing that the "
        "nightly deployment finished successfully.",
    ),
    Task(
        "post_message",
        "Send an update to the marketing team's channel saying the new landing "
        "page just went live.",
    ),
    Task(
        "post_message",
        "Drop a note in the general company channel welcoming a new hire named Priya to the team.",
    ),
    Task(
        "post_message",
        "Notify the on-call channel that the database failover completed without any issues.",
    ),
    Task(
        "post_message",
        "Post a reminder in the design team's channel about tomorrow's design review meeting.",
    ),
    # ── invite_to_channel (format constraint on `user`) — 5 tasks ───────────
    Task(
        "invite_to_channel",
        "Add the new backend engineer, Wei Zhang, to the engineering team's channel.",
    ),
    Task(
        "invite_to_channel",
        "Bring the contractor who just joined the redesign project into the design team's channel.",
    ),
    Task(
        "invite_to_channel",
        "Invite the customer support lead into the incident-response channel "
        "so she can follow live updates.",
    ),
    Task(
        "invite_to_channel",
        "Get the newly onboarded sales rep added to the sales team's channel.",
    ),
    Task(
        "invite_to_channel",
        "Add the intern shadowing the platform team to the platform team's channel.",
    ),
    # ── set_user_presence (enum constraint on `presence`) — 5 tasks ─────────
    Task(
        "set_user_presence",
        "Mark my Slack status so people can see I've stepped out from my desk for a long lunch.",
    ),
    Task(
        "set_user_presence",
        "Set my status to show I'm not around for the rest of the day — I'm "
        "heading into an all-day offsite with no laptop.",
    ),
    Task(
        "set_user_presence",
        "Switch my status back so Slack figures out whether I'm active or idle "
        "based on what I'm actually doing, instead of keeping me pinned to one state.",
    ),
    Task(
        "set_user_presence",
        "Force my Slack status to show I'm unavailable for the afternoon while "
        "I'm in an in-person meeting.",
    ),
    Task(
        "set_user_presence",
        "Stop manually holding my status in place and let Slack track my real activity again.",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Format tasks: no gold value — any value matching the pattern counts.
# Enum tasks: gold_value is the specific expected enum member.
TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # post_message — format: Slack channel reference ("#name" or encoded ID)
    (
        "post_message",
        "Post a message in the engineering team's channel announcing that the "
        "nightly deployment finished successfully.",
    ): [Constraint("channel", "format", pattern=_CHANNEL_REF_PATTERN)],
    (
        "post_message",
        "Send an update to the marketing team's channel saying the new landing "
        "page just went live.",
    ): [Constraint("channel", "format", pattern=_CHANNEL_REF_PATTERN)],
    (
        "post_message",
        "Drop a note in the general company channel welcoming a new hire named Priya to the team.",
    ): [Constraint("channel", "format", pattern=_CHANNEL_REF_PATTERN)],
    (
        "post_message",
        "Notify the on-call channel that the database failover completed without any issues.",
    ): [Constraint("channel", "format", pattern=_CHANNEL_REF_PATTERN)],
    (
        "post_message",
        "Post a reminder in the design team's channel about tomorrow's design review meeting.",
    ): [Constraint("channel", "format", pattern=_CHANNEL_REF_PATTERN)],
    # invite_to_channel — format: Slack user ID ("U" + 8-10 uppercase alphanumeric)
    (
        "invite_to_channel",
        "Add the new backend engineer, Wei Zhang, to the engineering team's channel.",
    ): [Constraint("user", "format", pattern=_USER_ID_PATTERN)],
    (
        "invite_to_channel",
        "Bring the contractor who just joined the redesign project into the design team's channel.",
    ): [Constraint("user", "format", pattern=_USER_ID_PATTERN)],
    (
        "invite_to_channel",
        "Invite the customer support lead into the incident-response channel "
        "so she can follow live updates.",
    ): [Constraint("user", "format", pattern=_USER_ID_PATTERN)],
    (
        "invite_to_channel",
        "Get the newly onboarded sales rep added to the sales team's channel.",
    ): [Constraint("user", "format", pattern=_USER_ID_PATTERN)],
    (
        "invite_to_channel",
        "Add the intern shadowing the platform team to the platform team's channel.",
    ): [Constraint("user", "format", pattern=_USER_ID_PATTERN)],
    # set_user_presence — enum: presence ("auto" / "away")
    (
        "set_user_presence",
        "Mark my Slack status so people can see I've stepped out from my desk for a long lunch.",
    ): [Constraint("presence", "enum", gold_value="away")],
    (
        "set_user_presence",
        "Set my status to show I'm not around for the rest of the day — I'm "
        "heading into an all-day offsite with no laptop.",
    ): [Constraint("presence", "enum", gold_value="away")],
    (
        "set_user_presence",
        "Switch my status back so Slack figures out whether I'm active or idle "
        "based on what I'm actually doing, instead of keeping me pinned to one state.",
    ): [Constraint("presence", "enum", gold_value="auto")],
    (
        "set_user_presence",
        "Force my Slack status to show I'm unavailable for the afternoon while "
        "I'm in an in-person meeting.",
    ): [Constraint("presence", "enum", gold_value="away")],
    (
        "set_user_presence",
        "Stop manually holding my status in place and let Slack track my real activity again.",
    ): [Constraint("presence", "enum", gold_value="auto")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    ["post_message", "invite_to_channel", "set_user_presence", "set_channel_topic"]
)
CONSTRAINED_TOOL_NAMES: frozenset[str] = frozenset(
    ["post_message", "invite_to_channel", "set_user_presence"]
)
INERT_TOOL_NAMES: frozenset[str] = frozenset(["set_channel_topic"])
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["post_message", "invite_to_channel"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(["set_user_presence"])

# Enum gold values referenced in tasks (for inferability tests — these should
# not appear verbatim in task text).
ENUM_GOLD_VALUES: list[str] = ["auto", "away"]

# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    _CHANNEL_REF_PATTERN,
    _USER_ID_PATTERN,
    "#engineering",
    "U012AB3CDE",
]
