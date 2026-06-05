from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Allow importing run_ty_guessable_oracle_ab from scripts/ (not on default sys.path)
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from evals.fixtures.ty_guessable_tasks import (
    ALL_TOOL_NAMES,
    ENUM_GOLD_VALUES,
    FORMAT_PATTERN_SAMPLES,
    ORACLE_ENUMS,
    PRESENT_TOOL_NAMES,
    RANGE_TOOL_NAMES,
    TASK_CONSTRAINTS,
    TASKS,
    UNIT_HINTS,  # noqa: E402 — sys.path manipulation required before this import
)

# ── Stability screen helper (mirrors run_ty_guessable_oracle_ab.py — kept standalone) ──


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
    """Arm A (type-only) and Arm B (oracle) produce different tool listings for set_asset_visibility."""
    from mcp.types import Tool

    from agentgauge.runner import _build_tool_listing

    arm_a = [
        Tool(
            name="set_asset_visibility",
            description="",
            inputSchema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "visibility": {"type": "string"},
                },
                "required": ["asset_id", "visibility"],
            },
        )
    ]
    arm_b = [
        Tool(
            name="set_asset_visibility",
            description="Set the visibility of a digital asset.",
            inputSchema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "visibility": {
                        "type": "string",
                        "enum": ["public", "unlisted", "internal", "archived"],
                        "description": (
                            "Access scope: public=visible to all, "
                            "unlisted=accessible only via direct link (not indexed), "
                            "internal=restricted to organisation members, "
                            "archived=read-only historical record."
                        ),
                    },
                },
                "required": ["asset_id", "visibility"],
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
        for sample in FORMAT_PATTERN_SAMPLES:
            assert sample not in task.description, (
                f"Format sample {sample!r} appears in task description for {task.tool_name!r}"
            )


def test_no_unit_hints_in_timeout_task_descriptions() -> None:
    """Timeout task descriptions must not mention milliseconds or ms."""
    range_tasks = [t for t in TASKS if t.tool_name in RANGE_TOOL_NAMES]
    for task in range_tasks:
        desc_lower = task.description.lower()
        for hint in UNIT_HINTS:
            assert hint.lower() not in desc_lower, (
                f"Unit hint {hint!r} found in range task {task.tool_name!r}: {task.description!r}"
            )


def test_idempotency_key_absent_from_charge_task_descriptions() -> None:
    """charge_customer task descriptions must not contain 'idempotency' (case-insensitive)."""
    charge_tasks = [t for t in TASKS if t.tool_name in PRESENT_TOOL_NAMES]
    for task in charge_tasks:
        assert "idempotency" not in task.description.lower(), (
            f"'idempotency' found in charge_customer task: {task.description!r}"
        )


# ── Group 5: Gold validity ─────────────────────────────────────────────────────


def test_enum_gold_values_are_valid_oracle_members() -> None:
    """Each enum constraint's gold_value must be in ORACLE_ENUMS for that tool+param."""
    for (tool_name, _desc), constraints in TASK_CONSTRAINTS.items():
        for c in constraints:
            if c.kind == "enum":
                key = f"{tool_name}.{c.param}"
                assert key in ORACLE_ENUMS, f"No ORACLE_ENUMS entry for {key!r}"
                assert c.gold_value in ORACLE_ENUMS[key], (
                    f"gold_value {c.gold_value!r} not in ORACLE_ENUMS[{key!r}]"
                )


def test_constraint_kinds_are_valid() -> None:
    valid_kinds = {"enum", "format", "range", "present"}
    for _key, constraints in TASK_CONSTRAINTS.items():
        for c in constraints:
            assert c.kind in valid_kinds, f"Invalid kind {c.kind!r}"


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


def test_range_constraints_have_valid_bounds() -> None:
    for _key, constraints in TASK_CONSTRAINTS.items():
        for c in constraints:
            if c.kind == "range":
                assert c.min_val is not None and c.max_val is not None
                assert c.min_val < c.max_val


def test_present_constraints_have_no_gold_value() -> None:
    for _key, constraints in TASK_CONSTRAINTS.items():
        for c in constraints:
            if c.kind == "present":
                assert c.gold_value is None


# ── Group 6: _is_correct_call unit tests ─────────────────────────────────────
# TASKS layout:
#   [0..4]   update_order_status
#   [5..9]   create_support_ticket
#   [10..14] set_asset_visibility
#   [15..19] schedule_callback
#   [20..24] set_request_timeout
#   [25..29] charge_customer


def test_is_correct_call_enum_correct() -> None:
    """_is_correct_call returns True when enum matches gold exactly."""
    from run_ty_guessable_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[0]  # "Mark order O-1001 as completed and fully paid" -> gold "settled"
    result = RunResult(
        task=task,
        selected_tool="update_order_status",
        constructed_args={"order_id": "O-1001", "status": "settled"},
        success=True,
    )
    assert _is_correct_call(result, task, TASK_CONSTRAINTS) is True


def test_is_correct_call_enum_wrong_synonym() -> None:
    """Agent uses a natural synonym 'completed' instead of oracle value 'settled'."""
    from run_ty_guessable_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[0]  # gold is "settled"
    result = RunResult(
        task=task,
        selected_tool="update_order_status",
        constructed_args={"order_id": "O-1001", "status": "completed"},
        success=True,
    )
    assert _is_correct_call(result, task, TASK_CONSTRAINTS) is False


def test_is_correct_call_format_valid_rfc3339() -> None:
    """RFC3339 datetime with Z suffix passes."""
    from run_ty_guessable_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[15]  # "Book a billing callback for customer C-501 next Monday at 9 AM UTC"
    result = RunResult(
        task=task,
        selected_tool="schedule_callback",
        constructed_args={
            "customer_id": "C-501",
            "scheduled_at": "2026-06-16T09:00:00Z",
            "topic": "billing",
        },
        success=True,
    )
    assert _is_correct_call(result, task, TASK_CONSTRAINTS) is True


def test_is_correct_call_format_invalid_no_offset() -> None:
    """Naive datetime without timezone offset fails format constraint."""
    from run_ty_guessable_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[15]
    result = RunResult(
        task=task,
        selected_tool="schedule_callback",
        constructed_args={
            "customer_id": "C-501",
            "scheduled_at": "2026-06-16T09:00:00",
            "topic": "billing",
        },
        success=True,
    )
    assert _is_correct_call(result, task, TASK_CONSTRAINTS) is False


def test_is_correct_call_range_in_bounds() -> None:
    """5000 ms is in the valid range for a 5-second timeout."""
    from run_ty_guessable_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[20]  # "Set a 5-second request timeout for service api-gateway"
    result = RunResult(
        task=task,
        selected_tool="set_request_timeout",
        constructed_args={"service_id": "api-gateway", "timeout": 5000},
        success=True,
    )
    assert _is_correct_call(result, task, TASK_CONSTRAINTS) is True


def test_is_correct_call_range_seconds_wrong() -> None:
    """Agent uses 5 (seconds) instead of 5000 (milliseconds) — fails range check."""
    from run_ty_guessable_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[20]  # min_val=4500, max_val=5500 — value 5 < 4500
    result = RunResult(
        task=task,
        selected_tool="set_request_timeout",
        constructed_args={"service_id": "api-gateway", "timeout": 5},
        success=True,
    )
    assert _is_correct_call(result, task, TASK_CONSTRAINTS) is False


def test_is_correct_call_present_included() -> None:
    """idempotency_key present in args — passes present constraint."""
    from run_ty_guessable_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[25]  # "Process a $49.99 monthly subscription charge for cart C-601"
    result = RunResult(
        task=task,
        selected_tool="charge_customer",
        constructed_args={
            "cart_id": "C-601",
            "amount": 49.99,
            "currency": "USD",
            "idempotency_key": "req-abc",
        },
        success=True,
    )
    assert _is_correct_call(result, task, TASK_CONSTRAINTS) is True


def test_is_correct_call_present_missing() -> None:
    """idempotency_key absent from args — fails present constraint."""
    from run_ty_guessable_oracle_ab import _is_correct_call

    from agentgauge.runner import RunResult

    task = TASKS[25]
    result = RunResult(
        task=task,
        selected_tool="charge_customer",
        constructed_args={"cart_id": "C-601", "amount": 49.99, "currency": "USD"},
        success=True,
    )
    assert _is_correct_call(result, task, TASK_CONSTRAINTS) is False
