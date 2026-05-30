from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool

from agentgauge.client import MCPClient
from agentgauge.providers import MockProvider
from agentgauge.runner import RunResult
from agentgauge.scorer import (
    DIMENSION_WEIGHTS,
    DimensionScore,
    score_all,
    score_call_correctness,
    score_description_quality,
    score_schema_completeness,
    score_selection_accuracy,
)
from agentgauge.tasks import Task


def _make_tool(name: str, description: str, schema: dict) -> Tool:
    return Tool(name=name, description=description, inputSchema=schema)


GOOD_TOOL = _make_tool(
    "echo",
    "Echo a message back",
    {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Text to echo"},
        },
        "required": ["message"],
    },
)

BAD_TOOL = _make_tool(
    "mystery",
    "",
    {"type": "object", "properties": {"x": {}, "y": {}}},
)


def test_schema_completeness_good_tool() -> None:
    result = score_schema_completeness([GOOD_TOOL])
    assert isinstance(result, DimensionScore)
    assert result.score > 80.0


def test_schema_completeness_bad_tool() -> None:
    result = score_schema_completeness([BAD_TOOL])
    assert result.score < 40.0
    assert len(result.fix_hints) > 0


def test_schema_completeness_no_tools() -> None:
    result = score_schema_completeness([])
    assert result.score == 0.0


async def test_description_quality_with_mock_provider() -> None:
    provider = MockProvider(responses=["8"])
    result = await score_description_quality([GOOD_TOOL], provider)
    assert isinstance(result, DimensionScore)
    assert result.score == 80.0  # 8/10 * 100


async def test_description_quality_no_tools() -> None:
    provider = MockProvider()
    result = await score_description_quality([], provider)
    assert result.score == 0.0


async def test_score_all_returns_report() -> None:
    """Without a client, selection_accuracy and call_correctness must be stubs (score=0, not_implemented)."""
    provider = MockProvider(responses=["7"])
    report = await score_all([GOOD_TOOL, BAD_TOOL], provider)

    assert report.tool_count == 2
    assert 0 <= report.overall <= 100

    # All 8 expected dimensions must be present in the right order.
    dim_names = [d.name for d in report.dimensions]
    assert dim_names == list(DIMENSION_WEIGHTS.keys()), f"dimension order changed: {dim_names}"

    # Without a client, all three runner dims must be explicit stubs.
    dim_map = {d.name: d for d in report.dimensions}
    assert dim_map["selection_accuracy"].details.get("status") == "not_implemented", (
        "selection_accuracy should be a stub when no client is passed"
    )
    assert dim_map["call_correctness"].details.get("status") == "not_implemented", (
        "call_correctness should be a stub when no client is passed"
    )
    assert dim_map["error_legibility"].details.get("status") == "not_implemented", (
        "error_legibility should be a stub when no client is passed"
    )

    # schema_completeness and description_quality must be real (non-zero for GOOD_TOOL).
    assert dim_map["schema_completeness"].score > 0
    assert dim_map["description_quality"].score > 0


def _make_mock_client(tool: Tool) -> MCPClient:
    """Return a mock MCPClient that introspects to [tool] and returns success on call_tool."""
    session = MagicMock()
    tools_resp = MagicMock()
    tools_resp.tools = [tool]
    resources_resp = MagicMock()
    resources_resp.resources = []
    prompts_resp = MagicMock()
    prompts_resp.prompts = []
    session.list_tools = AsyncMock(return_value=tools_resp)
    session.list_resources = AsyncMock(return_value=resources_resp)
    session.list_prompts = AsyncMock(return_value=prompts_resp)
    call_resp = MagicMock()
    call_resp.content = [MagicMock(type="text", text="ok")]
    session.call_tool = AsyncMock(return_value=call_resp)
    return MCPClient(session)


async def test_score_all_with_client_activates_runner_dimensions() -> None:
    """With a client, selection_accuracy, call_correctness, and error_legibility are real.

    MockProvider responses consumed by score_all (trials=1, GOOD_TOOL has 1 required param):
      "7"    — description_quality judge for GOOD_TOOL
      "echo" — run_tasks: tool selection (correct → selection_accuracy = 100)
      "{}"   — run_tasks: arg construction (call_tool returns success → call_correctness = 100)
      "7"    — error_legibility judge: probe 1 (missing_required)
      "7"    — error_legibility judge: probe 2 (wrong_type_message)
    """
    client = _make_mock_client(GOOD_TOOL)
    provider = MockProvider(responses=["7", "echo", "{}", "7", "7"])

    report = await score_all([GOOD_TOOL], provider, client=client)

    dim_map = {d.name: d for d in report.dimensions}

    # All three client-activated dims must NOT be stubs.
    assert dim_map["selection_accuracy"].details.get("status") != "not_implemented", (
        "selection_accuracy is still a stub — client= kwarg not wired into score_all"
    )
    assert dim_map["call_correctness"].details.get("status") != "not_implemented", (
        "call_correctness is still a stub — client= kwarg not wired into score_all"
    )
    assert dim_map["error_legibility"].details.get("status") != "not_implemented", (
        "error_legibility is still a stub — client= kwarg not wired into score_all"
    )

    # With a correct-picking mock agent, scores should be 100.
    assert dim_map["selection_accuracy"].score == 100.0
    assert dim_map["call_correctness"].score == 100.0
    assert dim_map["error_legibility"].score > 0

    # All 8 dimensions present.
    assert [d.name for d in report.dimensions] == list(DIMENSION_WEIGHTS.keys())


def _make_task(tool_name: str = "echo") -> Task:
    return Task(tool_name=tool_name, description="Call echo", sample_args={})


def test_score_selection_accuracy_perfect() -> None:
    task = _make_task("echo")
    results = [RunResult(task=task, selected_tool="echo", constructed_args={}, success=True)]
    score = score_selection_accuracy(results)
    assert score.score == 100.0
    assert score.name == "selection_accuracy"


def test_score_selection_accuracy_zero() -> None:
    task = _make_task("echo")
    results = [RunResult(task=task, selected_tool="wrong", constructed_args={}, success=False)]
    score = score_selection_accuracy(results)
    assert score.score == 0.0
    assert len(score.fix_hints) > 0


def test_score_selection_accuracy_partial() -> None:
    task = _make_task("echo")
    results = [
        RunResult(task=task, selected_tool="echo", constructed_args={}, success=True),
        RunResult(task=task, selected_tool="wrong", constructed_args={}, success=False),
    ]
    score = score_selection_accuracy(results)
    assert score.score == 50.0


def test_score_selection_accuracy_empty() -> None:
    score = score_selection_accuracy([])
    assert score.score == 0.0


def test_score_call_correctness_perfect() -> None:
    task = _make_task("echo")
    results = [RunResult(task=task, selected_tool="echo", constructed_args={}, success=True)]
    score = score_call_correctness(results)
    assert score.score == 100.0
    assert score.name == "call_correctness"


def test_score_call_correctness_zero() -> None:
    task = _make_task("echo")
    results = [RunResult(task=task, selected_tool="echo", constructed_args={}, success=False)]
    score = score_call_correctness(results)
    assert score.score == 0.0
    assert len(score.fix_hints) > 0


def test_score_call_correctness_partial() -> None:
    task = _make_task("echo")
    results = [
        RunResult(task=task, selected_tool="echo", constructed_args={}, success=True),
        RunResult(task=task, selected_tool="echo", constructed_args={}, success=False),
    ]
    score = score_call_correctness(results)
    assert score.score == 50.0


def test_score_call_correctness_empty() -> None:
    score = score_call_correctness([])
    assert score.score == 0.0
