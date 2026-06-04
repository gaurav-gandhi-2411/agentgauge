from __future__ import annotations

# Ty pre-registered tasks and gold constraints for the call-correctness oracle A/B.
#
# 32 tasks: 4 per tool (4 easy × 4 + 4 hard × 4 = 32).
#
# ANTI-TAUTOLOGY RULE: task descriptions express user intent only.
# They must NOT contain the enum value strings (ACQ_BURST, CODEC_R8, etc.).
# The agent must get the correct value from the SCHEMA, not from the task text.

from agentgauge.tasks import Task

TASKS: list[Task] = [
    # ── ping_server (easy — 4 tasks) ────────────────────────────────────────────
    Task("ping_server", "Check that the telemetry server is reachable"),
    Task("ping_server", "Verify the server is responding to requests"),
    Task("ping_server", "Test the connection to the data acquisition system"),
    Task("ping_server", "Confirm the data pipeline endpoint is live"),
    # ── get_server_info (easy — 4 tasks) ────────────────────────────────────────
    Task("get_server_info", "Retrieve the current server status and version information"),
    Task("get_server_info", "Get metadata about the running telemetry service"),
    Task("get_server_info", "Show me what version of the firmware is running"),
    Task("get_server_info", "Pull the server build details"),
    # ── list_channels (easy — 4 tasks) ──────────────────────────────────────────
    Task("list_channels", "List all channels registered in the system"),
    Task("list_channels", "Show which measurement channels are currently configured"),
    Task("list_channels", "Get the full inventory of available input channels"),
    Task("list_channels", "Display every channel the acquisition system knows about"),
    # ── reset_state (easy — 4 tasks) ────────────────────────────────────────────
    Task("reset_state", "Clear all temporary state and reset the system to defaults"),
    Task("reset_state", "Restart the acquisition state machine"),
    Task("reset_state", "Flush any buffered data and reset the system"),
    Task("reset_state", "Wipe the current run state so a fresh acquisition can start"),
    # ── set_acquisition_mode (hard — 4 tasks) ───────────────────────────────────
    Task(
        "set_acquisition_mode",
        "Configure sensor S01 to capture a rapid cluster of readings on each incoming trigger event",
    ),
    Task(
        "set_acquisition_mode",
        "Set sensor S02 to continuously stream data as fast as possible without any timing constraints",
    ),
    Task(
        "set_acquisition_mode",
        "Configure sensor S03 so its output is locked to an external reference clock",
    ),
    Task(
        "set_acquisition_mode",
        "Reconfigure sensor S04 to fire a grouped burst of samples whenever a start pulse arrives",
    ),
    # ── configure_output_codec (hard — 4 tasks) ─────────────────────────────────
    Task(
        "configure_output_codec",
        "Set stream S01 to output the most compact single-byte integer samples",
    ),
    Task(
        "configure_output_codec",
        "Configure stream S02 to use two-byte signed integer encoding",
    ),
    Task(
        "configure_output_codec",
        "Apply full floating-point precision encoding to stream S03",
    ),
    Task(
        "configure_output_codec",
        "Set stream S04 to output samples in the minimal single-byte format",
    ),
    # ── schedule_maintenance (hard — 4 tasks) ───────────────────────────────────
    Task(
        "schedule_maintenance",
        "Run maintenance task M09 only when the system has nothing else to do",
    ),
    Task(
        "schedule_maintenance",
        "Execute maintenance task M14 immediately, pausing everything else if necessary",
    ),
    Task(
        "schedule_maintenance",
        "Schedule maintenance task M21 to weave in between active jobs without stopping them",
    ),
    Task(
        "schedule_maintenance",
        "Start maintenance task M33 at the lowest urgency, filling only idle time",
    ),
    # ── set_channel_routing (hard — 4 tasks) ────────────────────────────────────
    Task("set_channel_routing", "Route channel CH01 through the highest-throughput main path"),
    Task(
        "set_channel_routing",
        "Configure channel CH03 to use the low-latency auxiliary pathway",
    ),
    Task(
        "set_channel_routing",
        "Assign channel CH05 to the redundant path that only activates if both main buses are down",
    ),
    Task(
        "set_channel_routing",
        "Direct channel CH07 through the primary main bus connection",
    ),
]

# Gold constraint for each hard task: {param_name: expected_value}.
# Key: (tool_name, task_description) — exact string match required.
# Easy tasks are not listed — no constrained params; always considered correct.
GOLD_CONSTRAINTS: dict[tuple[str, str], dict[str, str]] = {
    (
        "set_acquisition_mode",
        "Configure sensor S01 to capture a rapid cluster of readings on each incoming trigger event",
    ): {"mode": "ACQ_BURST"},
    (
        "set_acquisition_mode",
        "Set sensor S02 to continuously stream data as fast as possible without any timing constraints",
    ): {"mode": "ACQ_CONT"},
    (
        "set_acquisition_mode",
        "Configure sensor S03 so its output is locked to an external reference clock",
    ): {"mode": "ACQ_SYNC"},
    (
        "set_acquisition_mode",
        "Reconfigure sensor S04 to fire a grouped burst of samples whenever a start pulse arrives",
    ): {"mode": "ACQ_BURST"},
    (
        "configure_output_codec",
        "Set stream S01 to output the most compact single-byte integer samples",
    ): {"codec": "CODEC_R8"},
    (
        "configure_output_codec",
        "Configure stream S02 to use two-byte signed integer encoding",
    ): {"codec": "CODEC_R16"},
    (
        "configure_output_codec",
        "Apply full floating-point precision encoding to stream S03",
    ): {"codec": "CODEC_R32"},
    (
        "configure_output_codec",
        "Set stream S04 to output samples in the minimal single-byte format",
    ): {"codec": "CODEC_R8"},
    (
        "schedule_maintenance",
        "Run maintenance task M09 only when the system has nothing else to do",
    ): {"priority": "PRIO_X3"},
    (
        "schedule_maintenance",
        "Execute maintenance task M14 immediately, pausing everything else if necessary",
    ): {"priority": "PRIO_X1"},
    (
        "schedule_maintenance",
        "Schedule maintenance task M21 to weave in between active jobs without stopping them",
    ): {"priority": "PRIO_X2"},
    (
        "schedule_maintenance",
        "Start maintenance task M33 at the lowest urgency, filling only idle time",
    ): {"priority": "PRIO_X3"},
    (
        "set_channel_routing",
        "Route channel CH01 through the highest-throughput main path",
    ): {"routing": "RT_BUS_A"},
    (
        "set_channel_routing",
        "Configure channel CH03 to use the low-latency auxiliary pathway",
    ): {"routing": "RT_BUS_B"},
    (
        "set_channel_routing",
        "Assign channel CH05 to the redundant path that only activates if both main buses are down",
    ): {"routing": "RT_BUS_C"},
    (
        "set_channel_routing",
        "Direct channel CH07 through the primary main bus connection",
    ): {"routing": "RT_BUS_A"},
}

EASY_TOOL_NAMES: frozenset[str] = frozenset(
    ["ping_server", "get_server_info", "list_channels", "reset_state"]
)
HARD_TOOL_NAMES: frozenset[str] = frozenset(
    ["set_acquisition_mode", "configure_output_codec", "schedule_maintenance", "set_channel_routing"]
)

# All known enum values across hard tools — used by inferability tests.
ALL_HARD_ENUM_VALUES: list[str] = [
    "ACQ_BURST",
    "ACQ_CONT",
    "ACQ_SYNC",
    "CODEC_R8",
    "CODEC_R16",
    "CODEC_R32",
    "PRIO_X1",
    "PRIO_X2",
    "PRIO_X3",
    "RT_BUS_A",
    "RT_BUS_B",
    "RT_BUS_C",
]
