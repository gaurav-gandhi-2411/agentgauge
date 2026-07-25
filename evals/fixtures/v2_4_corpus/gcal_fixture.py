from __future__ import annotations

# Google Calendar pre-registered tasks and constraints for the call-correctness
# oracle A/B (v2.4 corpus expansion — new gold-constraint fixture pair, domain:
# Google Calendar API v3, modeled on examples/gcal_server.py and
# examples/gcal_server_fixed.py).
#
# 20 tasks: 5 per tool x 4 tools — ALL hard, NO inert easy tasks.
# Headroom design: Arm A (type-only schema, no description) expected 40-70% so
# the description/schema-fix oracle effect can be measured against Arm B
# (examples/gcal_server_fixed.py).
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only.
# They must NOT contain enum values (DAILY/WEEKLY/MONTHLY/YEARLY,
# accepted/declined/tentative/needsAction) or format pattern strings/example
# literals (no literal ISO 8601 timestamps, no literal IANA time zone names).
# The agent must get the correct value from the SCHEMA (Arm B), not from the
# task text.
from agentgauge.constraints import Constraint
from agentgauge.tasks import Task

TASKS: list[Task] = [
    # create_event (format constraint: start_time, RFC 3339 / ISO 8601 datetime) — 5 tasks
    Task(
        "create_event",
        "Schedule a product demo on calendar C-eng for next Tuesday at 2pm Pacific time",
    ),
    Task(
        "create_event",
        "Create an event for the quarterly board meeting on calendar C-board starting "
        "at 9am Eastern next Monday",
    ),
    Task(
        "create_event",
        "Add a dentist appointment to my primary calendar for tomorrow morning at 8:30",
    ),
    Task(
        "create_event",
        "Set up a team standup on calendar C-dev for tomorrow at 10am UTC",
    ),
    Task(
        "create_event",
        "Book a client call on calendar C-sales starting at 4pm this Friday",
    ),
    # create_calendar (format constraint: time_zone, IANA Time Zone Database name) — 5 tasks
    Task("create_calendar", "Create a new calendar for our New York office"),
    Task("create_calendar", "Set up a shared calendar for the London engineering team"),
    Task("create_calendar", "Create a calendar for the Tokyo support desk"),
    Task("create_calendar", "Add a new calendar for the Sydney sales office"),
    Task("create_calendar", "Create a calendar for the Los Angeles marketing team"),
    # update_event_response_status (enum constraint: response_status) — 5 tasks
    Task(
        "update_event_response_status",
        "Confirm that jane@example.com will attend the budget review event evt-101",
    ),
    Task(
        "update_event_response_status",
        "Mark that bob@example.com cannot make it to the sprint planning event evt-102",
    ),
    Task(
        "update_event_response_status",
        "Note that carol@example.com is not yet sure whether she can join the offsite "
        "event evt-103",
    ),
    Task(
        "update_event_response_status",
        "Reset dave@example.com's RSVP for the town hall event evt-104 back to awaiting a reply",
    ),
    Task(
        "update_event_response_status",
        "Record that erin@example.com has confirmed her attendance at the product "
        "launch event evt-105",
    ),
    # set_event_recurrence (enum constraint: frequency, RFC 5545 RRULE FREQ) — 5 tasks
    Task("set_event_recurrence", "Make the team standup event evt-201 repeat every day"),
    Task("set_event_recurrence", "Set the book club event evt-202 to repeat every week"),
    Task("set_event_recurrence", "Make the rent payment reminder event evt-203 repeat every month"),
    Task("set_event_recurrence", "Set the company anniversary event evt-204 to repeat every year"),
    Task(
        "set_event_recurrence",
        "Make the daily medication reminder event evt-205 recur once each day",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Format tasks: no gold value — any syntactically valid format counts (matches
# the checking discipline used in evals/fixtures/ty2_tasks.py's format tools).
# Enum tasks: gold_value is the specific expected enum member.
TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # create_event — format: RFC 3339 / ISO 8601 datetime with offset or Z suffix
    (
        "create_event",
        "Schedule a product demo on calendar C-eng for next Tuesday at 2pm Pacific time",
    ): [
        Constraint(
            "start_time",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?",
        )
    ],
    (
        "create_event",
        "Create an event for the quarterly board meeting on calendar C-board starting "
        "at 9am Eastern next Monday",
    ): [
        Constraint(
            "start_time",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?",
        )
    ],
    (
        "create_event",
        "Add a dentist appointment to my primary calendar for tomorrow morning at 8:30",
    ): [
        Constraint(
            "start_time",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?",
        )
    ],
    (
        "create_event",
        "Set up a team standup on calendar C-dev for tomorrow at 10am UTC",
    ): [
        Constraint(
            "start_time",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?",
        )
    ],
    (
        "create_event",
        "Book a client call on calendar C-sales starting at 4pm this Friday",
    ): [
        Constraint(
            "start_time",
            "format",
            pattern=r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?",
        )
    ],
    # create_calendar — format: IANA Time Zone Database name, "Area/Location"
    (
        "create_calendar",
        "Create a new calendar for our New York office",
    ): [Constraint("time_zone", "format", pattern=r"[A-Za-z_]+/[A-Za-z_]+(/[A-Za-z_]+)?")],
    (
        "create_calendar",
        "Set up a shared calendar for the London engineering team",
    ): [Constraint("time_zone", "format", pattern=r"[A-Za-z_]+/[A-Za-z_]+(/[A-Za-z_]+)?")],
    (
        "create_calendar",
        "Create a calendar for the Tokyo support desk",
    ): [Constraint("time_zone", "format", pattern=r"[A-Za-z_]+/[A-Za-z_]+(/[A-Za-z_]+)?")],
    (
        "create_calendar",
        "Add a new calendar for the Sydney sales office",
    ): [Constraint("time_zone", "format", pattern=r"[A-Za-z_]+/[A-Za-z_]+(/[A-Za-z_]+)?")],
    (
        "create_calendar",
        "Create a calendar for the Los Angeles marketing team",
    ): [Constraint("time_zone", "format", pattern=r"[A-Za-z_]+/[A-Za-z_]+(/[A-Za-z_]+)?")],
    # update_event_response_status — enum, gold values specified
    (
        "update_event_response_status",
        "Confirm that jane@example.com will attend the budget review event evt-101",
    ): [Constraint("response_status", "enum", gold_value="accepted")],
    (
        "update_event_response_status",
        "Mark that bob@example.com cannot make it to the sprint planning event evt-102",
    ): [Constraint("response_status", "enum", gold_value="declined")],
    (
        "update_event_response_status",
        "Note that carol@example.com is not yet sure whether she can join the offsite "
        "event evt-103",
    ): [Constraint("response_status", "enum", gold_value="tentative")],
    (
        "update_event_response_status",
        "Reset dave@example.com's RSVP for the town hall event evt-104 back to awaiting a reply",
    ): [Constraint("response_status", "enum", gold_value="needsAction")],
    (
        "update_event_response_status",
        "Record that erin@example.com has confirmed her attendance at the product "
        "launch event evt-105",
    ): [Constraint("response_status", "enum", gold_value="accepted")],
    # set_event_recurrence — enum, gold values specified
    (
        "set_event_recurrence",
        "Make the team standup event evt-201 repeat every day",
    ): [Constraint("frequency", "enum", gold_value="DAILY")],
    (
        "set_event_recurrence",
        "Set the book club event evt-202 to repeat every week",
    ): [Constraint("frequency", "enum", gold_value="WEEKLY")],
    (
        "set_event_recurrence",
        "Make the rent payment reminder event evt-203 repeat every month",
    ): [Constraint("frequency", "enum", gold_value="MONTHLY")],
    (
        "set_event_recurrence",
        "Set the company anniversary event evt-204 to repeat every year",
    ): [Constraint("frequency", "enum", gold_value="YEARLY")],
    (
        "set_event_recurrence",
        "Make the daily medication reminder event evt-205 recur once each day",
    ): [Constraint("frequency", "enum", gold_value="DAILY")],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    [
        "create_event",
        "create_calendar",
        "update_event_response_status",
        "set_event_recurrence",
    ]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["create_event", "create_calendar"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(
    ["update_event_response_status", "set_event_recurrence"]
)

# Enum gold values referenced in tasks (for inferability tests)
ENUM_GOLD_VALUES: list[str] = [
    "accepted",
    "declined",
    "tentative",
    "needsAction",
    "DAILY",
    "WEEKLY",
    "MONTHLY",
    "YEARLY",
]
# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?",
    "2026-08-01T14:00:00-07:00",
    r"[A-Za-z_]+/[A-Za-z_]+(/[A-Za-z_]+)?",
    "America/New_York",
]
