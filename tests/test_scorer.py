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


def _run_result(
    tool_name: str, selected: str | None, success: bool, error: str | None = None
) -> RunResult:
    task = Task(tool_name=tool_name, description="test task", sample_args={})
    return RunResult(
        task=task, selected_tool=selected, constructed_args={}, success=success, error=error
    )


def test_score_selection_accuracy_perfect() -> None:
    results = [_run_result("echo", "echo", True)]
    dim = score_selection_accuracy(results)
    assert dim.score == 100.0


def test_score_selection_accuracy_zero() -> None:
    results = [_run_result("echo", "other_tool", False)]
    dim = score_selection_accuracy(results)
    assert dim.score == 0.0


def test_score_selection_accuracy_partial() -> None:
    results = [
        _run_result("echo", "echo", True),
        _run_result("echo", "wrong", False),
    ]
    dim = score_selection_accuracy(results)
    assert dim.score == 50.0


def test_score_selection_accuracy_no_results() -> None:
    dim = score_selection_accuracy([])
    assert dim.score == 0.0


def test_score_call_correctness_all_success() -> None:
    results = [_run_result("echo", "echo", True)]
    dim = score_call_correctness(results)
    assert dim.score == 100.0


def test_score_call_correctness_all_fail() -> None:
    results = [_run_result("echo", "echo", False, error="oops")]
    dim = score_call_correctness(results)
    assert dim.score == 0.0


def test_score_call_correctness_partial() -> None:
    results = [
        _run_result("echo", "echo", True),
        _run_result("echo", "echo", False),
    ]
    dim = score_call_correctness(results)
    assert dim.score == 50.0


def test_score_call_correctness_no_results() -> None:
    dim = score_call_correctness([])
    assert dim.score == 0.0


async def test_score_all_with_client() -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock

    from agentgauge.client import MCPClient

    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=MagicMock(content=[MagicMock(type="text", text="result")])
    )
    client = MCPClient(session)

    provider = MockProvider(
        responses=[
            "8",
            json.dumps({"tool": "echo", "args": {"message": "hello"}}),
        ]
    )
    report = await score_all([GOOD_TOOL], provider, client=client)
    assert report.tool_count == 1
    assert 0 <= report.overall <= 100
    dim_map = {d.name: d for d in report.dimensions}
    assert dim_map["selection_accuracy"].score == 100.0
    assert dim_map["call_correctness"].score == 100.0


async def test_score_all_without_client_stubs_runner_dims() -> None:
    provider = MockProvider(responses=["7"])
    report = await score_all([GOOD_TOOL], provider)
    dim_map = {d.name: d for d in report.dimensions}
    assert dim_map["selection_accuracy"].score == 0.0
    assert dim_map["call_correctness"].score == 0.0
