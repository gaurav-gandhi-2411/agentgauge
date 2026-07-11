from __future__ import annotations

# T18 fixture integrity tests — pure unit tests, no network, no LLM.
from evals.fixtures.t18_catalog import (
    ARM_A_DESCRIPTIONS,
    ARM_B_DESCRIPTIONS,
    FAMILIES,
    FAMILY_MAP,
    TASKS,
)

# ── stability_screen helper (duplicated from scripts/run_t18_oracle_ab.py) ─────


def stability_screen(
    task_successes_run1: list[int],
    task_successes_run2: list[int],
    trials: int,  # noqa: ARG001 — kept for signature symmetry
) -> list[bool]:
    """Return keep-mask. Task is kept if |successes_run1 - successes_run2| <= 1."""
    return [
        abs(s1 - s2) <= 1 for s1, s2 in zip(task_successes_run1, task_successes_run2, strict=True)
    ]


# ── Fixture integrity ──────────────────────────────────────────────────────────


def test_t18_catalog_size() -> None:
    """Total tool count across all families must be exactly 60."""
    all_tools = [tool for tools in FAMILIES.values() for tool in tools]
    assert len(all_tools) == 60


def test_t18_families_count() -> None:
    """Exactly 10 families pre-registered."""
    assert len(FAMILIES) == 10


def test_t18_family_sizes() -> None:
    """Each family must have exactly 6 tools."""
    for family, tools in FAMILIES.items():
        assert len(tools) == 6, f"Family '{family}' has {len(tools)} tools, expected 6"


def test_t18_tasks_count() -> None:
    """Exactly 40 tasks pre-registered (4 per family)."""
    assert len(TASKS) == 40


def test_t18_one_gold_per_task() -> None:
    """Every task's gold tool name exists in the catalog."""
    all_tools = {tool for tools in FAMILIES.values() for tool in tools}
    for task in TASKS:
        assert task.tool_name in all_tools, f"Gold tool '{task.tool_name}' not in catalog"


def test_t18_arm_a_all_empty() -> None:
    """All Arm A descriptions must be empty strings."""
    for tool, desc in ARM_A_DESCRIPTIONS.items():
        assert desc == "", f"Arm A tool '{tool}' has non-empty description: {desc!r}"


def test_t18_arm_b_all_nonempty() -> None:
    """All Arm B descriptions must be non-empty strings."""
    for tool, desc in ARM_B_DESCRIPTIONS.items():
        assert desc and len(desc.strip()) > 0, f"Arm B tool '{tool}' has empty description"


def test_t18_manipulation_check() -> None:
    """Arm A and Arm B descriptions must differ (manipulation is real)."""
    assert ARM_A_DESCRIPTIONS != ARM_B_DESCRIPTIONS


def test_t18_anti_tautology() -> None:
    """Task descriptions must not contain gold tool name or first token of oracle description.

    Guarding against accidentally including oracle wording in the task prompt.
    """
    for task in TASKS:
        task_lower = task.description.lower()
        tool_lower = task.tool_name.lower()
        # Tool name must not appear in task description
        assert tool_lower not in task_lower, (
            f"Task for '{task.tool_name}' contains the tool name: {task.description!r}"
        )
        # First token of oracle description must not appear in task description
        oracle_desc = ARM_B_DESCRIPTIONS[task.tool_name]
        first_token = oracle_desc.split()[0].lower().rstrip(".,;:") if oracle_desc else ""
        if first_token and len(first_token) > 3:  # skip short words like "Run", "Add"
            assert first_token not in task_lower, (
                f"Task for '{task.tool_name}' contains oracle first token '{first_token}': "
                f"{task.description!r}"
            )


def test_t18_family_map_complete() -> None:
    """Every tool in FAMILIES must also appear in FAMILY_MAP."""
    for family, tools in FAMILIES.items():
        for tool in tools:
            assert tool in FAMILY_MAP, f"Tool '{tool}' missing from FAMILY_MAP"
            assert FAMILY_MAP[tool] == family, (
                f"FAMILY_MAP['{tool}'] = {FAMILY_MAP[tool]!r}, expected {family!r}"
            )


# ── stability_screen logic ─────────────────────────────────────────────────────


def test_t18_stability_screen_logic() -> None:
    """Verify stability_screen drop logic across all boundary cases."""
    # All same → all kept
    kept = stability_screen([5, 3, 0], [5, 3, 0], trials=5)
    assert kept == [True, True, True], f"All-same case: {kept}"

    # |diff| == 1 → kept
    kept = stability_screen([4, 2], [3, 3], trials=5)
    assert kept == [True, True], f"|diff|==1 case: {kept}"

    # |diff| == 2 → dropped
    kept = stability_screen([5, 0], [3, 2], trials=5)
    assert kept == [False, False], f"|diff|==2 case: {kept}"

    # |diff| == 3 → dropped
    kept = stability_screen([5, 0], [2, 3], trials=5)
    assert kept == [False, False], f"|diff|==3 case: {kept}"

    # Mixed: keep, drop, keep
    kept = stability_screen([3, 5, 2], [2, 0, 3], trials=5)
    # |3-2|=1 keep, |5-0|=5 drop, |2-3|=1 keep
    assert kept == [True, False, True], f"Mixed case: {kept}"


# ── Distribution across families ─────────────────────────────────────────────


def test_t18_tasks_distributed_across_families() -> None:
    """All 10 families must have at least one task."""
    families_with_tasks = {FAMILY_MAP[task.tool_name] for task in TASKS}
    for family in FAMILIES:
        assert family in families_with_tasks, f"Family '{family}' has no tasks"
