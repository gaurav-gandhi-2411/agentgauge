from __future__ import annotations

from mcp.types import Tool

from agentgauge.providers import MockProvider
from agentgauge.runner import RunResult
from agentgauge.scorer import (
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
    provider = MockProvider(responses=["7"])
    report = await score_all([GOOD_TOOL, BAD_TOOL], provider)
    assert report.tool_count == 2
    assert 0 <= report.overall <= 100
    assert len(report.dimensions) == 8


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
