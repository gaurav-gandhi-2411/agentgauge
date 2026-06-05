from __future__ import annotations

# Ty Run 2 pre-registered tasks and constraints for the call-correctness oracle A/B.
#
# 30 tasks: 5 per tool × 6 tools — ALL hard, NO inert easy tasks.
# Headroom design: Arm A expected 40-70% so oracle effect can be measured.
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only.
# They must NOT contain enum values, format pattern strings, or unit names
# (no "centiseconds", "deciseconds", etc.).
# The agent must get the correct value from the SCHEMA, not from the task text.
from dataclasses import dataclass, field  # noqa: F401 — field reserved for future extension

from agentgauge.tasks import Task


@dataclass
class Constraint:
    """A single correctness constraint on a constructed call argument."""

    param: str
    kind: str  # "enum" | "format" | "range"
    # kind="enum": value must equal gold_value exactly (case-sensitive)
    gold_value: str | None = None
    # kind="format": re.fullmatch(pattern, str(value)) must not be None
    pattern: str | None = None
    # kind="range": min_val <= int(value) <= max_val
    min_val: int | None = None
    max_val: int | None = None


TASKS: list[Task] = [
    # register_channel (format constraint) — 5 tasks
    Task("register_channel", "Register the primary pressure sensor channel at facility site F1"),
    Task("register_channel", "Add a new temperature monitoring channel for site S3"),
    Task("register_channel", "Register the flow rate measurement channel at site A2"),
    Task("register_channel", "Set up a humidity sensor channel for site H9"),
    Task("register_channel", "Register a voltage measurement channel at site V5"),
    # log_fault (format constraint) — 5 tasks
    Task("log_fault", "Log an overtemperature fault on unit U7"),
    Task("log_fault", "Record an undervoltage fault detected on unit U2"),
    Task("log_fault", "Report a sensor communication timeout on unit U11"),
    Task("log_fault", "Log a calibration failure for unit U5"),
    Task("log_fault", "Record a watchdog expiry fault on unit U8"),
    # set_output_encoding (semi-conventional enum) — 5 tasks
    Task(
        "set_output_encoding",
        "Encode pipeline P1 output for international text including non-ASCII characters",
    ),
    Task(
        "set_output_encoding",
        "Set pipeline P2 to use 7-bit encoding only, rejecting multi-byte characters",
    ),
    Task(
        "set_output_encoding",
        "Configure pipeline P3 to output binary data safely over a text-only channel",
    ),
    Task(
        "set_output_encoding",
        "Apply the encoding required for compatibility with the legacy TRS-80 protocol on pipeline P4",
    ),
    Task(
        "set_output_encoding",
        "Set pipeline P5 to the encoding that handles all Unicode code points",
    ),
    # set_trigger_mode (semi-conventional enum) — 5 tasks
    Task(
        "set_trigger_mode",
        "Configure sensor S01 to fire whenever its input signal transitions from low to high",
    ),
    Task("set_trigger_mode", "Set sensor S02 to trigger on the downward edge of the input signal"),
    Task(
        "set_trigger_mode",
        "Configure sensor S03 to react to signal changes in either direction",
    ),
    Task(
        "set_trigger_mode",
        "Enable the special firmware-level detection mode on sensor S04 that requires firmware 2.4",
    ),
    Task(
        "set_trigger_mode",
        "Configure sensor S05 to detect only when the voltage rises above threshold",
    ),
    # set_debounce_delay (unit/bound constraint) — 5 tasks
    Task(
        "set_debounce_delay",
        "Suppress mechanical bounce on the reed switch input for sensor S01",
    ),
    Task(
        "set_debounce_delay",
        "Filter out rapid false triggers on the vibration sensor S02",
    ),
    Task(
        "set_debounce_delay",
        "Add a debounce interval to prevent multiple registrations from the door sensor S03",
    ),
    Task(
        "set_debounce_delay",
        "Reduce noise on the contact sensor S04 caused by spring oscillation",
    ),
    Task(
        "set_debounce_delay",
        "Apply signal filtering to eliminate chatter on the limit switch for sensor S05",
    ),
    # configure_watchdog (unit/bound constraint) — 5 tasks
    Task(
        "configure_watchdog",
        "Set a short watchdog on node N1 that will restart it if it stops responding quickly",
    ),
    Task(
        "configure_watchdog",
        "Configure a generous watchdog timeout for node N2 which runs slow background tasks",
    ),
    Task(
        "configure_watchdog",
        "Set a medium-length watchdog for node N3 that balances responsiveness and stability",
    ),
    Task(
        "configure_watchdog",
        "Apply a conservative watchdog to node N4 to allow for slow initialization",
    ),
    Task(
        "configure_watchdog",
        "Configure the tightest acceptable watchdog on node N5 for a real-time loop",
    ),
]

# Constraints per task: (tool_name, task_description) -> list[Constraint]
# Format/range tasks: no gold value — any valid format/range counts.
# Enum tasks: gold_value is the specific expected enum member.
TASK_CONSTRAINTS: dict[tuple[str, str], list[Constraint]] = {
    # register_channel — format: [A-Z]{2}[0-9]{2}
    (
        "register_channel",
        "Register the primary pressure sensor channel at facility site F1",
    ): [Constraint("channel_ref", "format", pattern=r"[A-Z]{2}[0-9]{2}")],
    (
        "register_channel",
        "Add a new temperature monitoring channel for site S3",
    ): [Constraint("channel_ref", "format", pattern=r"[A-Z]{2}[0-9]{2}")],
    (
        "register_channel",
        "Register the flow rate measurement channel at site A2",
    ): [Constraint("channel_ref", "format", pattern=r"[A-Z]{2}[0-9]{2}")],
    (
        "register_channel",
        "Set up a humidity sensor channel for site H9",
    ): [Constraint("channel_ref", "format", pattern=r"[A-Z]{2}[0-9]{2}")],
    (
        "register_channel",
        "Register a voltage measurement channel at site V5",
    ): [Constraint("channel_ref", "format", pattern=r"[A-Z]{2}[0-9]{2}")],
    # log_fault — format: ERR[0-9]{3}
    (
        "log_fault",
        "Log an overtemperature fault on unit U7",
    ): [Constraint("fault_code", "format", pattern=r"ERR[0-9]{3}")],
    (
        "log_fault",
        "Record an undervoltage fault detected on unit U2",
    ): [Constraint("fault_code", "format", pattern=r"ERR[0-9]{3}")],
    (
        "log_fault",
        "Report a sensor communication timeout on unit U11",
    ): [Constraint("fault_code", "format", pattern=r"ERR[0-9]{3}")],
    (
        "log_fault",
        "Log a calibration failure for unit U5",
    ): [Constraint("fault_code", "format", pattern=r"ERR[0-9]{3}")],
    (
        "log_fault",
        "Record a watchdog expiry fault on unit U8",
    ): [Constraint("fault_code", "format", pattern=r"ERR[0-9]{3}")],
    # set_output_encoding — semi-conventional enum, gold values specified
    (
        "set_output_encoding",
        "Encode pipeline P1 output for international text including non-ASCII characters",
    ): [Constraint("encoding", "enum", gold_value="utf-8")],
    (
        "set_output_encoding",
        "Set pipeline P2 to use 7-bit encoding only, rejecting multi-byte characters",
    ): [Constraint("encoding", "enum", gold_value="ascii")],
    (
        "set_output_encoding",
        "Configure pipeline P3 to output binary data safely over a text-only channel",
    ): [Constraint("encoding", "enum", gold_value="base64")],
    (
        "set_output_encoding",
        "Apply the encoding required for compatibility with the legacy TRS-80 protocol on pipeline P4",
    ): [Constraint("encoding", "enum", gold_value="XOR16")],
    (
        "set_output_encoding",
        "Set pipeline P5 to the encoding that handles all Unicode code points",
    ): [Constraint("encoding", "enum", gold_value="utf-8")],
    # set_trigger_mode — semi-conventional enum, gold values specified
    (
        "set_trigger_mode",
        "Configure sensor S01 to fire whenever its input signal transitions from low to high",
    ): [Constraint("trigger", "enum", gold_value="rising")],
    (
        "set_trigger_mode",
        "Set sensor S02 to trigger on the downward edge of the input signal",
    ): [Constraint("trigger", "enum", gold_value="falling")],
    (
        "set_trigger_mode",
        "Configure sensor S03 to react to signal changes in either direction",
    ): [Constraint("trigger", "enum", gold_value="both")],
    (
        "set_trigger_mode",
        "Enable the special firmware-level detection mode on sensor S04 that requires firmware 2.4",
    ): [Constraint("trigger", "enum", gold_value="XP7")],
    (
        "set_trigger_mode",
        "Configure sensor S05 to detect only when the voltage rises above threshold",
    ): [Constraint("trigger", "enum", gold_value="rising")],
    # set_debounce_delay — range [1, 25] cs
    (
        "set_debounce_delay",
        "Suppress mechanical bounce on the reed switch input for sensor S01",
    ): [Constraint("delay_cs", "range", min_val=1, max_val=25)],
    (
        "set_debounce_delay",
        "Filter out rapid false triggers on the vibration sensor S02",
    ): [Constraint("delay_cs", "range", min_val=1, max_val=25)],
    (
        "set_debounce_delay",
        "Add a debounce interval to prevent multiple registrations from the door sensor S03",
    ): [Constraint("delay_cs", "range", min_val=1, max_val=25)],
    (
        "set_debounce_delay",
        "Reduce noise on the contact sensor S04 caused by spring oscillation",
    ): [Constraint("delay_cs", "range", min_val=1, max_val=25)],
    (
        "set_debounce_delay",
        "Apply signal filtering to eliminate chatter on the limit switch for sensor S05",
    ): [Constraint("delay_cs", "range", min_val=1, max_val=25)],
    # configure_watchdog — range [5, 60] ds
    (
        "configure_watchdog",
        "Set a short watchdog on node N1 that will restart it if it stops responding quickly",
    ): [Constraint("timeout_ds", "range", min_val=5, max_val=60)],
    (
        "configure_watchdog",
        "Configure a generous watchdog timeout for node N2 which runs slow background tasks",
    ): [Constraint("timeout_ds", "range", min_val=5, max_val=60)],
    (
        "configure_watchdog",
        "Set a medium-length watchdog for node N3 that balances responsiveness and stability",
    ): [Constraint("timeout_ds", "range", min_val=5, max_val=60)],
    (
        "configure_watchdog",
        "Apply a conservative watchdog to node N4 to allow for slow initialization",
    ): [Constraint("timeout_ds", "range", min_val=5, max_val=60)],
    (
        "configure_watchdog",
        "Configure the tightest acceptable watchdog on node N5 for a real-time loop",
    ): [Constraint("timeout_ds", "range", min_val=5, max_val=60)],
}

ALL_TOOL_NAMES: frozenset[str] = frozenset(
    [
        "register_channel",
        "log_fault",
        "set_output_encoding",
        "set_trigger_mode",
        "set_debounce_delay",
        "configure_watchdog",
    ]
)
FORMAT_TOOL_NAMES: frozenset[str] = frozenset(["register_channel", "log_fault"])
ENUM_TOOL_NAMES: frozenset[str] = frozenset(["set_output_encoding", "set_trigger_mode"])
RANGE_TOOL_NAMES: frozenset[str] = frozenset(["set_debounce_delay", "configure_watchdog"])

# Enum gold values referenced in tasks (for inferability tests)
ENUM_GOLD_VALUES: list[str] = [
    "utf-8",
    "ascii",
    "base64",
    "XOR16",
    "rising",
    "falling",
    "both",
    "XP7",
]
# Format patterns (for inferability tests — these should not appear verbatim in task text)
FORMAT_PATTERNS_SAMPLE: list[str] = [
    "[A-Z]{2}[0-9]{2}",
    "ERR[0-9]{3}",
    "ERR001",
    "PH04",
    "TM07",
]
