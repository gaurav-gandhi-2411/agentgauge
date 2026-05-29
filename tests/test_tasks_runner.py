from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import Tool

from agentgauge.client import MCPClient, ToolCallResult
from agentgauge.providers import MockProvider
from agentgauge.runner import RunResult, _parse_selection_response, run_tasks
from agentgauge.scorer import score_call_correctness, score_selection_accuracy
from agentgauge.tasks import Task, _sample_value, generate_tasks

# ── fixtures ───────────────────────────────────────────────────────────────

ECHO_TOOL = Tool(
    name="echo",
    description="Echo a message back",
    inputSchema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Text to echo"},
            "count": {"type": "integer", "description": "Repeat count"},
        },
        "required": ["message"],
    },
)

NOOP_TOOL = Tool(
    name="noop",
    description=None,
    inputSchema={"type": "object", "properties": {}},
)


def _make_mock_client(success: bool = True, error: str | None = None) -> MCPClient:
    session = MagicMock()
    client = MCPClient(session)
    client.call_tool = AsyncMock(
        return_value=ToolCallResult(success=success, content=[], error=error)
    )
    return client


# ── generate_tasks ─────────────────────────────────────────────────────────


def test_generate_tasks_one_per_tool() -> None:
    tasks = generate_tasks([ECHO_TOOL, NOOP_TOOL])
    assert len(tasks) == 2
    assert tasks[0].tool_name == "echo"
    assert tasks[1].tool_name == "noop"


def test_generate_tasks_sample_args_from_schema() -> None:
    tasks = generate_tasks([ECHO_TOOL])
    args = tasks[0].sample_args
    assert "message" in args
    assert isinstance(args["message"], str)
    assert "count" in args
    assert isinstance(args["count"], int)


def test_generate_tasks_no_description_tool() -> None:
    tasks = generate_tasks([NOOP_TOOL])
    assert tasks[0].sample_args == {}
    assert "noop" in tasks[0].description.lower()


def test_generate_tasks_uses_tool_description() -> None:
    tasks = generate_tasks([ECHO_TOOL])
    assert "Echo" in tasks[0].description


def test_generate_tasks_empty_list() -> None:
    assert generate_tasks([]) == []


# ── _sample_value ──────────────────────────────────────────────────────────


def test_sample_value_string() -> None:
    assert isinstance(_sample_value({"type": "string"}), str)


def test_sample_value_integer() -> None:
    assert isinstance(_sample_value({"type": "integer"}), int)


def test_sample_value_number() -> None:
    assert isinstance(_sample_value({"type": "number"}), float)


def test_sample_value_boolean() -> None:
    assert isinstance(_sample_value({"type": "boolean"}), bool)


def test_sample_value_array() -> None:
    assert isinstance(_sample_value({"type": "array"}), list)


def test_sample_value_object() -> None:
    assert isinstance(_sample_value({"type": "object"}), dict)


def test_sample_value_unknown_type() -> None:
    assert _sample_value({}) is None


# ── _parse_selection_response ──────────────────────────────────────────────


def test_parse_valid_json_response() -> None:
    resp = '{"tool_name": "echo", "arguments": {"message": "hi"}}'
    tool, args = _parse_selection_response(resp)
    assert tool == "echo"
    assert args == {"message": "hi"}


def test_parse_json_embedded_in_text() -> None:
    resp = 'Sure! {"tool_name": "echo", "arguments": {}} done.'
    tool, args = _parse_selection_response(resp)
    assert tool == "echo"
    assert args == {}


def test_parse_invalid_response_returns_none() -> None:
    tool, args = _parse_selection_response("not json at all")
    assert tool is None
    assert args is None


def test_parse_empty_response() -> None:
    tool, args = _parse_selection_response("")
    assert tool is None


# ── run_tasks ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_tasks_correct_selection() -> None:
    provider = MockProvider(responses=['{"tool_name": "echo", "arguments": {"message": "hi"}}'])
    client = _make_mock_client(success=True)
    tasks = generate_tasks([ECHO_TOOL])

    results = await run_tasks(tasks, client, provider, [ECHO_TOOL])

    assert len(results) == 1
    r = results[0]
    assert r.selected_tool == "echo"
    assert r.constructed_args == {"message": "hi"}
    assert r.success is True
    assert r.error is None


@pytest.mark.asyncio
async def test_run_tasks_invalid_provider_response() -> None:
    provider = MockProvider(responses=["not json"])
    client = _make_mock_client()
    tasks = generate_tasks([ECHO_TOOL])

    results = await run_tasks(tasks, client, provider, [ECHO_TOOL])

    assert len(results) == 1
    r = results[0]
    assert r.selected_tool is None
    assert r.success is False
    assert r.error is not None


@pytest.mark.asyncio
async def test_run_tasks_tool_call_failure() -> None:
    provider = MockProvider(responses=['{"tool_name": "echo", "arguments": {"message": "hi"}}'])
    client = _make_mock_client(success=False, error="Tool execution error")
    tasks = generate_tasks([ECHO_TOOL])

    results = await run_tasks(tasks, client, provider, [ECHO_TOOL])

    assert results[0].success is False
    assert results[0].error == "Tool execution error"


@pytest.mark.asyncio
async def test_run_tasks_empty_task_list() -> None:
    provider = MockProvider()
    client = _make_mock_client()
    results = await run_tasks([], client, provider, [ECHO_TOOL])
    assert results == []


@pytest.mark.asyncio
async def test_run_tasks_multiple_tools() -> None:
    responses = [
        '{"tool_name": "echo", "arguments": {"message": "hello"}}',
        '{"tool_name": "noop", "arguments": {}}',
    ]
    provider = MockProvider(responses=responses)
    client = _make_mock_client(success=True)
    tasks = generate_tasks([ECHO_TOOL, NOOP_TOOL])

    results = await run_tasks(tasks, client, provider, [ECHO_TOOL, NOOP_TOOL])

    assert len(results) == 2
    assert results[0].selected_tool == "echo"
    assert results[1].selected_tool == "noop"


# ── score_selection_accuracy ───────────────────────────────────────────────


def _make_run_result(
    tool_name: str, selected: str | None, success: bool = True, error: str | None = None
) -> RunResult:
    return RunResult(
        task=Task(tool_name=tool_name, description="test", sample_args={}),
        success=success,
        selected_tool=selected,
        error=error,
    )


def test_score_selection_accuracy_all_correct() -> None:
    results = [
        _make_run_result("echo", "echo"),
        _make_run_result("noop", "noop"),
    ]
    score = score_selection_accuracy(results)
    assert score.score == 100.0
    assert score.details["correct"] == 2


def test_score_selection_accuracy_none_correct() -> None:
    results = [
        _make_run_result("echo", "noop"),
        _make_run_result("noop", "echo"),
    ]
    score = score_selection_accuracy(results)
    assert score.score == 0.0
    assert len(score.fix_hints) > 0


def test_score_selection_accuracy_partial() -> None:
    results = [
        _make_run_result("echo", "echo"),
        _make_run_result("noop", "echo"),
    ]
    score = score_selection_accuracy(results)
    assert score.score == 50.0


def test_score_selection_accuracy_empty() -> None:
    score = score_selection_accuracy([])
    assert score.score == 0.0


def test_score_selection_accuracy_none_selected() -> None:
    results = [_make_run_result("echo", None, success=False)]
    score = score_selection_accuracy(results)
    assert score.score == 0.0


# ── score_call_correctness ─────────────────────────────────────────────────


def test_score_call_correctness_all_success() -> None:
    results = [
        _make_run_result("echo", "echo", success=True),
        _make_run_result("noop", "noop", success=True),
    ]
    score = score_call_correctness(results)
    assert score.score == 100.0
    assert score.details["successful"] == 2


def test_score_call_correctness_all_failed() -> None:
    results = [
        _make_run_result("echo", "echo", success=False, error="oops"),
        _make_run_result("noop", "noop", success=False, error="bad args"),
    ]
    score = score_call_correctness(results)
    assert score.score == 0.0
    assert len(score.fix_hints) > 0


def test_score_call_correctness_partial() -> None:
    results = [
        _make_run_result("echo", "echo", success=True),
        _make_run_result("noop", "noop", success=False, error="err"),
    ]
    score = score_call_correctness(results)
    assert score.score == 50.0


def test_score_call_correctness_empty() -> None:
    score = score_call_correctness([])
    assert score.score == 0.0
