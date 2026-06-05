from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Allow importing run_ty2_oracle_ab from scripts/ (not on default sys.path)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from evals.fixtures.ty2_tasks import (
    ALL_TOOL_NAMES,
    ENUM_GOLD_VALUES,
    FORMAT_PATTERNS_SAMPLE,
    RANGE_TOOL_NAMES,
    TASK_CONSTRAINTS,
    TASKS,
)

# ── Stability screen helper (mirrors run_ty2_oracle_ab.py — kept standalone) ──


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
    assert len(TASKS) == 30


def test_all_tasks_have_valid_tool_name() -> None:
    for task in TASKS:
        assert task.tool_name in ALL_TOOL_NAMES


def test_each_tool_has_five_tasks() -> None:
    counts = Counter(t.tool_name for t in TASKS)
    for tool in ALL_TOOL_NAMES:
        assert counts[tool] == 5


def test_all_tasks_have_constraints() -> None:
    for task in TASKS:
        key = (task.tool_name, task.description)
        assert key in TASK_CONSTRAINTS, f"No constraint for {key}"


# ── Group 2: Stability screen drop logic ──────────────────────────────────────


def test_stability_screen_drops_flaky_task() -> None:
    kept = stability_screen([3, 5, 2], [1, 5, 3], trials=5)
    assert kept == [False, True, True]


def test_stability_screen_keeps_stable_tasks() -> None:
    kept = stability_screen([3, 4, 2, 5], [3, 3, 3, 5], trials=5)
    assert kept == [True, True, True, True]


# ── Group 3: Manipulation check ───────────────────────────────────────────────


def test_manipulation_check_arm_a_vs_b_differ() -> None:
    """Arm A (type-only) and Arm B (oracle) produce different tool listings."""
    from mcp.types import Tool

    from agentgauge.runner import _build_tool_listing

    arm_a = [
        Tool(
            name="set_output_encoding",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "pipeline_id": {"type": "string"},
                    "encoding": {"type": "string"},
                },
                "required": ["pipeline_id", "encoding"],
            },
        )
    ]
    arm_b = [
        Tool(
            name="set_output_encoding",
            description="Set the output encoding for a data pipeline.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pipeline_id": {"type": "string"},
                    "encoding": {
                        "type": "string",
                        "enum": ["utf-8", "ascii", "base64", "XOR16"],
                        "description": "Output encoding: ...",
                    },
                },
                "required": ["pipeline_id", "encoding"],
            },
        )
    ]
    assert _build_tool_listing(arm_a) != _build_tool_listing(arm_b)


# ── Group 4: Inferability ─────────────────────────────────────────────────────


def test_enum_gold_values_absent_from_task_descriptions() -> None:
    for task in TASKS:
        for val in ENUM_GOLD_VALUES:
            assert val not in task.description, (
                f"Enum gold value {val!r} appears in task description for {task.tool_name!r}"
            )


def test_format_pattern_samples_absent_from_task_descriptions() -> None:
    for task in TASKS:
        for sample in FORMAT_PATTERNS_SAMPLE:
            assert sample not in task.description, (
                f"Format sample {sample!r} appears in task description for {task.tool_name!r}"
            )


def test_no_unit_names_in_range_task_descriptions() -> None:
    """Range task descriptions must not mention centiseconds or deciseconds."""
    unit_hints = ["centisecond", "decisecond", " cs ", " ds ", "cs)", "ds)"]
    range_tasks = [t for t in TASKS if t.tool_name in RANGE_TOOL_NAMES]
    for task in range_tasks:
        desc_lower = task.description.lower()
        for hint in unit_hints:
            assert hint.lower() not in desc_lower, (
                f"Unit hint {hint!r} found in range task {task.tool_name!r}: {task.description!r}"
            )


# ── Group 5: Constraint structure sanity ──────────────────────────────────────


def test_constraint_kinds_are_valid() -> None:
    valid_kinds = {"enum", "format", "range"}
    for _key, constraints in TASK_CONSTRAINTS.items():
        for c in constraints:
            assert c.kind in valid_kinds


def test_enum_constraints_have_gold_value() -> None:
    for _key, constraints in TASK_CONSTRAINTS.items():
        for c in constraints:
            if c.kind == "enum":
                assert c.gold_value is not None and len(c.gold_value) > 0


def test_format_constraints_have_pattern() -> None:
    for _key, constraints in TASK_CONSTRAINTS.items():
        for c in constraints:
            if c.kind == "format":
                assert c.pattern is not None and len(c.pattern) > 0


def test_range_constraints_have_bounds() -> None:
    for _key, constraints in TASK_CONSTRAINTS.items():
        for c in constraints:
            if c.kind == "range":
                assert c.min_val is not None and c.max_val is not None
                assert c.min_val < c.max_val


def test_is_correct_call_enum_correct_case() -> None:
    """_is_correct_call returns True when enum matches gold exactly."""
    from run_ty2_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[10]  # "Encode pipeline P1 output..." -> gold utf-8
    result_correct = RunResult(
        task=task,
        selected_tool="set_output_encoding",
        constructed_args={"pipeline_id": "P1", "encoding": "utf-8"},
        success=True,
    )
    assert _is_correct_call(result_correct, task, TASK_CONSTRAINTS) is True


def test_is_correct_call_enum_wrong() -> None:
    from run_ty2_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[10]  # gold is "utf-8" — case-sensitive
    result_wrong = RunResult(
        task=task,
        selected_tool="set_output_encoding",
        constructed_args={"pipeline_id": "P1", "encoding": "UTF-8"},
        success=True,
    )
    assert _is_correct_call(result_wrong, task, TASK_CONSTRAINTS) is False


def test_is_correct_call_format_valid() -> None:
    from run_ty2_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[0]  # "Register the primary pressure sensor channel at facility site F1"
    result_valid = RunResult(
        task=task,
        selected_tool="register_channel",
        constructed_args={"site_id": "F1", "channel_ref": "PH04"},
        success=True,
    )
    assert _is_correct_call(result_valid, task, TASK_CONSTRAINTS) is True


def test_is_correct_call_format_invalid() -> None:
    from run_ty2_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[0]
    result_bad = RunResult(
        task=task,
        selected_tool="register_channel",
        constructed_args={"site_id": "F1", "channel_ref": "pressure_01"},
        success=True,
    )
    assert _is_correct_call(result_bad, task, TASK_CONSTRAINTS) is False


def test_is_correct_call_range_in_bounds() -> None:
    from run_ty2_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[20]  # "Suppress mechanical bounce..."
    result_in = RunResult(
        task=task,
        selected_tool="set_debounce_delay",
        constructed_args={"sensor_id": "S01", "delay_cs": 10},
        success=True,
    )
    assert _is_correct_call(result_in, task, TASK_CONSTRAINTS) is True


def test_is_correct_call_range_out_of_bounds() -> None:
    from run_ty2_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[20]
    result_out = RunResult(
        task=task,
        selected_tool="set_debounce_delay",
        constructed_args={"sensor_id": "S01", "delay_cs": 5000},
        success=True,
    )
    assert _is_correct_call(result_out, task, TASK_CONSTRAINTS) is False


# ── Group 6: _is_correct_call missing required param ──────────────────────────


def test_is_correct_call_missing_param() -> None:
    from run_ty2_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[
        15
    ]  # "Configure sensor S01 to fire whenever its input signal transitions from low to high"
    result_missing = RunResult(
        task=task,
        selected_tool="set_trigger_mode",
        constructed_args={"sensor_id": "S01"},  # missing trigger
        success=True,
    )
    assert _is_correct_call(result_missing, task, TASK_CONSTRAINTS) is False
