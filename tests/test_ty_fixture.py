from __future__ import annotations

from collections import Counter

from evals.fixtures.ty_tasks import (
    ALL_HARD_ENUM_VALUES,
    EASY_TOOL_NAMES,
    GOLD_CONSTRAINTS,
    HARD_TOOL_NAMES,
    TASKS,
)

# ── Stability screen helper (mirrors run_ty_oracle_ab.py — kept standalone) ───


def stability_screen(
    task_successes_run1: list[int],
    task_successes_run2: list[int],
    trials: int,  # noqa: ARG001 — kept for signature symmetry with run script
) -> list[bool]:
    """Return keep-mask. A task is kept if |successes_run1 - successes_run2| <= 1."""
    return [
        abs(s1 - s2) <= 1 for s1, s2 in zip(task_successes_run1, task_successes_run2, strict=True)
    ]


# ── Group 1: Fixture integrity ─────────────────────────────────────────────────


def test_task_count() -> None:
    """Exactly 32 tasks pre-registered (4 easy tools × 4 + 4 hard tools × 4)."""
    assert len(TASKS) == 32


def test_all_tasks_have_valid_tool_name() -> None:
    """Every task's tool_name is in EASY_TOOL_NAMES | HARD_TOOL_NAMES."""
    all_known = EASY_TOOL_NAMES | HARD_TOOL_NAMES
    for task in TASKS:
        assert task.tool_name in all_known, (
            f"Unknown tool_name {task.tool_name!r} — not in easy or hard set"
        )


def test_each_hard_tool_has_four_tasks() -> None:
    """Every hard tool has exactly 4 pre-registered tasks."""
    counts = Counter(t.tool_name for t in TASKS if t.tool_name in HARD_TOOL_NAMES)
    for tool in HARD_TOOL_NAMES:
        assert counts[tool] == 4, f"Expected 4 tasks for {tool!r}, got {counts[tool]}"


def test_gold_constraints_cover_all_hard_tasks() -> None:
    """Every hard task has an entry in GOLD_CONSTRAINTS."""
    hard_tasks = [(t.tool_name, t.description) for t in TASKS if t.tool_name in HARD_TOOL_NAMES]
    for key in hard_tasks:
        assert key in GOLD_CONSTRAINTS, f"No gold constraint for hard task {key}"


# ── Group 2: Stability screen drop logic ──────────────────────────────────────


def test_stability_screen_drops_flaky_task() -> None:
    """Task with |3-1|=2 > 1 is dropped; tasks 1 and 2 are kept."""
    kept = stability_screen([3, 5, 2], [1, 5, 3], trials=5)
    assert kept == [False, True, True]


def test_stability_screen_keeps_stable_tasks() -> None:
    """All tasks with delta <= 1 are kept."""
    kept = stability_screen([3, 4, 2, 5], [3, 3, 3, 5], trials=5)
    assert kept == [True, True, True, True]


def test_stability_screen_drops_all_flaky() -> None:
    """Tasks with |5-0|=5 and |0-5|=5 are both dropped."""
    kept = stability_screen([5, 0], [0, 5], trials=5)
    assert kept == [False, False]


# ── Group 3: Manipulation check ───────────────────────────────────────────────


def test_manipulation_check_arm_a_vs_b_differ() -> None:
    """Arm A (type-only schema) and Arm B (oracle enum+desc) produce different tool listings."""
    from mcp.types import Tool

    from agentgauge.runner import _build_tool_listing

    # Arm A: type-only schema for mode
    arm_a_tools = [
        Tool(
            name="set_acquisition_mode",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "mode": {"type": "string"},
                },
                "required": ["sensor_id", "mode"],
            },
        )
    ]
    # Arm B: oracle schema for mode
    arm_b_tools = [
        Tool(
            name="set_acquisition_mode",
            description="Configure the acquisition mode for a sensor.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sensor_id": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["ACQ_BURST", "ACQ_CONT", "ACQ_SYNC"],
                        "description": (
                            "Acquisition mode code: ACQ_BURST=triggered burst, "
                            "ACQ_CONT=continuous, ACQ_SYNC=synchronized-clock"
                        ),
                    },
                },
                "required": ["sensor_id", "mode"],
            },
        )
    ]
    listing_a = _build_tool_listing(arm_a_tools)
    listing_b = _build_tool_listing(arm_b_tools)
    assert listing_a != listing_b


# ── Group 4: Inferability tests ───────────────────────────────────────────────


def test_inferability_enum_values_absent_from_task_descriptions() -> None:
    """Enum codes must not appear verbatim in any task description (anti-tautology rule).

    Agent must derive the correct code from the schema, not by copying from task text.
    """
    for task in TASKS:
        for enum_val in ALL_HARD_ENUM_VALUES:
            assert enum_val not in task.description, (
                f"Task {task.tool_name!r} contains enum value {enum_val!r} — "
                "anti-tautology: agent would be copying, not reading the schema"
            )


def test_inferability_enum_values_not_substrings_of_constrained_param_names() -> None:
    """Enum codes should not be derivable as case-insensitive substrings of the param name.

    Ensures the agent cannot guess the correct value purely from the parameter name.
    """
    constrained: dict[str, tuple[str, list[str]]] = {
        "set_acquisition_mode": ("mode", ["ACQ_BURST", "ACQ_CONT", "ACQ_SYNC"]),
        "configure_output_codec": ("codec", ["CODEC_R8", "CODEC_R16", "CODEC_R32"]),
        "schedule_maintenance": ("priority", ["PRIO_X1", "PRIO_X2", "PRIO_X3"]),
        "set_channel_routing": ("routing", ["RT_BUS_A", "RT_BUS_B", "RT_BUS_C"]),
    }
    for tool_name, (param, enum_vals) in constrained.items():
        for val in enum_vals:
            assert val.lower() not in param.lower(), (
                f"Enum value {val!r} is a substring of param name {param!r} "
                f"(tool={tool_name!r}) — agent could guess without reading schema"
            )


# ── Group 5: Gold constraints sanity ──────────────────────────────────────────

VALID_ENUMS: dict[str, list[str]] = {
    "mode": ["ACQ_BURST", "ACQ_CONT", "ACQ_SYNC"],
    "codec": ["CODEC_R8", "CODEC_R16", "CODEC_R32"],
    "priority": ["PRIO_X1", "PRIO_X2", "PRIO_X3"],
    "routing": ["RT_BUS_A", "RT_BUS_B", "RT_BUS_C"],
}


def test_gold_constraint_values_are_valid_enum_members() -> None:
    """Every gold value in GOLD_CONSTRAINTS is a member of the declared enum for that param."""
    for (tool, _desc), constraints in GOLD_CONSTRAINTS.items():
        for param, value in constraints.items():
            assert value in VALID_ENUMS[param], (
                f"Gold value {value!r} for param {param!r} (tool={tool!r}) "
                f"not in valid enum {VALID_ENUMS[param]}"
            )
