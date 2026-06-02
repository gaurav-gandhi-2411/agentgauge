from __future__ import annotations

from collections import Counter

import pytest

from evals.fixtures.t17_tasks import CLUSTER_MAP, TASKS


# ── stability screen helper ───────────────────────────────────────────────────


def stability_screen(
    task_successes_run1: list[int],
    task_successes_run2: list[int],
    trials: int,  # noqa: ARG001 — kept for signature symmetry with scripts/run_t17_oracle_ab.py
) -> list[bool]:
    """Return keep-mask. A task is kept if |successes_run1 - successes_run2| <= 1."""
    return [abs(s1 - s2) <= 1 for s1, s2 in zip(task_successes_run1, task_successes_run2)]


# ── Group 1: Fixture integrity ────────────────────────────────────────────────


def test_all_tasks_have_valid_gold_tool() -> None:
    """Every task's tool_name is in CLUSTER_MAP (i.e., a known confusable-server tool)."""
    for task in TASKS:
        assert task.tool_name in CLUSTER_MAP


def test_task_count() -> None:
    """Exactly 32 tasks pre-registered."""
    assert len(TASKS) == 32


def test_each_cluster_has_both_tools_represented() -> None:
    """Every cluster has >=1 task per tool, ensuring both cluster members are gold for some task."""
    counts = Counter(t.tool_name for t in TASKS)
    for tool in CLUSTER_MAP:
        assert counts[tool] >= 1, f"No task targets tool '{tool}'"


# ── Group 2: Stability screen drop logic ──────────────────────────────────────


def test_stability_screen_drops_flaky_task() -> None:
    """Task with |3-1|=2 > 1 is dropped."""
    kept = stability_screen([3, 5, 2], [1, 5, 3], trials=5)
    # task 0: |3-1|=2 -> drop; task 1: |5-5|=0 -> keep; task 2: |2-3|=1 -> keep
    assert kept == [False, True, True]


def test_stability_screen_keeps_stable_tasks() -> None:
    kept = stability_screen([3, 4, 2, 5], [3, 3, 3, 5], trials=5)
    # |3-3|=0, |4-3|=1, |2-3|=1, |5-5|=0 -> all keep
    assert kept == [True, True, True, True]


def test_stability_screen_drops_all_flaky() -> None:
    kept = stability_screen([5, 0], [0, 5], trials=5)
    # |5-0|=5 > 1, |0-5|=5 > 1 -> all drop
    assert kept == [False, False]


# ── Group 3: Manipulation check ───────────────────────────────────────────────


def test_manipulation_check_arm_a_vs_b_differ() -> None:
    """Arm A (empty desc) and Arm B (oracle desc) produce different tool listings."""
    from mcp.types import Tool

    from agentgauge.runner import _build_tool_listing

    arm_a_tools = [
        Tool(
            name="search_documents",
            description="",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="query_records",
            description="",
            inputSchema={
                "type": "object",
                "properties": {"field": {"type": "string"}, "value": {"type": "string"}},
                "required": ["field", "value"],
            },
        ),
    ]
    arm_b_tools = [
        Tool(
            name="search_documents",
            description=(
                "Performs full-text search across all document content. Use when you have a word "
                "or phrase to match against document bodies. NOT for field-based filtering."
            ),
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="query_records",
            description=(
                "Executes a structured filter query using field conditions (e.g. field='value'). "
                "Use when you know which field to filter on. NOT for body text or keyword search."
            ),
            inputSchema={
                "type": "object",
                "properties": {"field": {"type": "string"}, "value": {"type": "string"}},
                "required": ["field", "value"],
            },
        ),
    ]

    listing_a = _build_tool_listing(arm_a_tools)
    listing_b = _build_tool_listing(arm_b_tools)
    assert listing_a != listing_b
    # Arm A has "(no description)" placeholders; Arm B has oracle text
    assert "(no description)" in listing_a
    assert "full-text search" in listing_b


def test_manipulation_check_identical_arms_equal() -> None:
    from mcp.types import Tool

    from agentgauge.runner import _build_tool_listing

    tools = [
        Tool(
            name="echo",
            description="Echo tool",
            inputSchema={"type": "object", "properties": {}, "required": []},
        )
    ]
    assert _build_tool_listing(tools) == _build_tool_listing(tools)
