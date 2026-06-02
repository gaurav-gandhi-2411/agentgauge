from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import Tool

from agentgauge.ab_harness import (
    assert_agent_ne_judge_ne_generator,
    compute_mcnemar,
    run_paired_ab,
)
from agentgauge.client import MCPClient
from agentgauge.providers import MockProvider
from agentgauge.runner import RunResult
from agentgauge.tasks import Task

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_mock_client(tool_name: str = "echo", *, call_success: bool = True) -> MCPClient:
    """Mock MCPClient that serves one tool and returns call_success on call_tool."""
    session = MagicMock()

    tools_resp = MagicMock()
    tools_resp.tools = [
        Tool(
            name=tool_name,
            description="Test tool",
            inputSchema={
                "type": "object",
                "properties": {"x": {"type": "string", "description": "Input"}},
                "required": ["x"],
            },
        )
    ]
    resources_resp = MagicMock()
    resources_resp.resources = []
    prompts_resp = MagicMock()
    prompts_resp.prompts = []

    session.list_tools = AsyncMock(return_value=tools_resp)
    session.list_resources = AsyncMock(return_value=resources_resp)
    session.list_prompts = AsyncMock(return_value=prompts_resp)

    if call_success:
        call_resp = MagicMock()
        call_resp.content = [MagicMock(type="text", text="ok")]
        session.call_tool = AsyncMock(return_value=call_resp)
    else:
        session.call_tool = AsyncMock(side_effect=RuntimeError("bad args"))

    return MCPClient(session)


def _make_run_results(correct: list[bool], success: list[bool]) -> list[RunResult]:
    """Build RunResult list for McNemar tests."""
    assert len(correct) == len(success)
    return [
        RunResult(
            task=Task(tool_name="echo", description="d"),
            selected_tool="echo" if c else "wrong",
            constructed_args={},
            success=s,
        )
        for c, s in zip(correct, success, strict=True)
    ]


# ── assert_agent_ne_judge_ne_generator ───────────────────────────────────────


def test_assert_agent_rejects_llama_family() -> None:
    with pytest.raises(ValueError, match="llama3.1"):
        assert_agent_ne_judge_ne_generator("llama3.1:8b")


def test_assert_agent_rejects_llama_variant() -> None:
    with pytest.raises(ValueError, match="llama3.1"):
        assert_agent_ne_judge_ne_generator("llama3.1:70b")


def test_assert_agent_rejects_qwen_family() -> None:
    with pytest.raises(ValueError, match="qwen3"):
        assert_agent_ne_judge_ne_generator("qwen3:8b")


def test_assert_agent_accepts_gemma() -> None:
    assert_agent_ne_judge_ne_generator("gemma2:9b")  # no raise


def test_assert_agent_accepts_mistral() -> None:
    assert_agent_ne_judge_ne_generator("mistral:7b")  # no raise


# ── compute_mcnemar ───────────────────────────────────────────────────────────


def test_mcnemar_no_discordant_pairs() -> None:
    ra = _make_run_results([True, True], [True, True])
    rb = _make_run_results([True, True], [True, True])
    r = compute_mcnemar(ra, rb, key="selection")
    assert r.b == 0
    assert r.c == 0
    assert r.statistic == 0.0
    assert "b+c=0" in r.p_approx


def test_mcnemar_small_sample_returns_raw_b_minus_c() -> None:
    # b=2, c=0, b+c=2 < 10
    ra = _make_run_results([False, False, True], [True, True, True])
    rb = _make_run_results([True, True, True], [True, True, True])
    r = compute_mcnemar(ra, rb, key="selection")
    assert r.b == 2
    assert r.c == 0
    assert r.statistic == 2.0
    assert "exact binomial" in r.p_approx


def test_mcnemar_large_sample_significant() -> None:
    # b=15, c=0 → chi2 = (14)^2/15 = 13.07 > 3.841
    ra = _make_run_results([False] * 15 + [True] * 5, [True] * 20)
    rb = _make_run_results([True] * 20, [True] * 20)
    r = compute_mcnemar(ra, rb, key="selection")
    assert r.b == 15
    assert r.c == 0
    assert r.statistic > 3.841
    assert "p<0.05" in r.p_approx


def test_mcnemar_large_sample_not_significant() -> None:
    # b=6, c=5, b+c=11 → chi2 = 0/11 = 0
    ra = _make_run_results([False] * 6 + [True] * 5 + [True] * 9, [True] * 20)
    rb = _make_run_results([True] * 6 + [False] * 5 + [True] * 9, [True] * 20)
    r = compute_mcnemar(ra, rb, key="selection")
    assert r.b == 6
    assert r.c == 5
    assert "p≥0.05" in r.p_approx


def test_mcnemar_invalid_key() -> None:
    ra = _make_run_results([True], [True])
    with pytest.raises(ValueError, match="key must be"):
        compute_mcnemar(ra, ra, key="bogus")


def test_mcnemar_mismatched_lengths() -> None:
    ra = _make_run_results([True, True], [True, True])
    rb = _make_run_results([True], [True])
    with pytest.raises(ValueError, match="must match"):
        compute_mcnemar(ra, rb, key="selection")


# ── run_paired_ab ─────────────────────────────────────────────────────────────


async def test_ab_mismatched_tool_names_raises() -> None:
    client_a = _make_mock_client("echo")
    client_b = _make_mock_client("other_tool")  # different name!
    p = MockProvider(["echo", "{}"])
    with pytest.raises(AssertionError, match="identical tool names"):
        await run_paired_ab(client_a, client_b, p, p, p)


async def test_ab_a_vs_a_zero_noise() -> None:
    """A-vs-A: same server, deterministic mock → noise floor = 0."""
    client = _make_mock_client("echo", call_success=True)
    # Both arm A runs get the same responses → identical results → noise = 0
    p_a = MockProvider(["echo", '{"x": "hi"}'])
    p_noise = MockProvider(["echo", '{"x": "hi"}'])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    result = await run_paired_ab(client, client, p_a, p_a, p_noise, tasks=tasks)

    assert result.noise_floor_selection == 0.0
    assert result.noise_floor_correctness == 0.0


async def test_ab_selection_delta() -> None:
    """Arm A provider picks wrong tool; arm B provider picks correct tool.
    Expected: selection_delta = +100 (0% → 100%).
    """
    client_a = _make_mock_client("echo", call_success=False)
    client_b = _make_mock_client("echo", call_success=True)
    # arm A: wrong selection
    p_a = MockProvider(["WRONG_TOOL", "{}"])
    # arm B: correct selection and valid args
    p_b = MockProvider(["echo", '{"x": "hello"}'])
    p_noise = MockProvider(["WRONG_TOOL", "{}"])
    tasks = [Task(tool_name="echo", description="Call echo: Test tool", sample_args={})]

    result = await run_paired_ab(client_a, client_b, p_a, p_b, p_noise, tasks=tasks)

    assert result.arm_a.selection_accuracy == 0.0
    assert result.arm_b.selection_accuracy == 100.0
    assert result.selection_delta == 100.0
    assert result.noise_floor_selection == 0.0
    assert result.mcnemar_selection.b == 1
    assert result.mcnemar_selection.c == 0


async def test_ab_correctness_delta() -> None:
    """Arm A call fails (bad schema → bad args); arm B call succeeds (good schema → valid args).
    Provider picks correct tool on both arms (selection stays constant).
    Expected: correctness_delta = +100 (0% → 100%).
    """
    client_a = _make_mock_client("echo", call_success=False)
    client_b = _make_mock_client("echo", call_success=True)
    # Same provider for both — selection is identical on both arms
    p = MockProvider(["echo", '{"x": "value"}'])
    p_noise = MockProvider(["echo", '{"x": "value"}'])
    tasks = [Task(tool_name="echo", description="Call echo: Test tool", sample_args={})]

    result = await run_paired_ab(client_a, client_b, p, p, p_noise, tasks=tasks)

    assert result.arm_a.call_correctness == 0.0
    assert result.arm_b.call_correctness == 100.0
    assert result.correctness_delta == 100.0
    assert result.selection_delta == 0.0  # same provider → same selection
    assert result.mcnemar_correctness.b == 1
    assert result.mcnemar_correctness.c == 0


async def test_ab_tasks_generated_from_arm_a() -> None:
    """When tasks=None, harness generates from arm A's tools (identical task set)."""
    client_a = _make_mock_client("echo", call_success=True)
    client_b = _make_mock_client("echo", call_success=True)
    p = MockProvider(["echo", '{"x": "value"}'])
    p_noise = MockProvider(["echo", '{"x": "value"}'])

    result = await run_paired_ab(client_a, client_b, p, p, p_noise)

    assert len(result.tasks) == 1
    assert result.tasks[0].tool_name == "echo"


async def test_ab_multiple_trials() -> None:
    """N trials = 3 on 1 task → 3 results per arm."""
    client_a = _make_mock_client("echo", call_success=True)
    client_b = _make_mock_client("echo", call_success=True)
    p_a = MockProvider(["echo", "{}"] * 3)
    p_b = MockProvider(["echo", "{}"] * 3)
    p_noise = MockProvider(["echo", "{}"] * 3)
    tasks = [Task(tool_name="echo", description="d", sample_args={})]

    result = await run_paired_ab(client_a, client_b, p_a, p_b, p_noise, tasks=tasks, trials=3)

    assert result.trials == 3
    assert len(result.arm_a.run_results) == 3
    assert len(result.arm_b.run_results) == 3
