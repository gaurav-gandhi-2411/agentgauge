from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool

from agentgauge.client import MCPClient
from agentgauge.providers import MockProvider
from agentgauge.runner import _parse_tool_selection, run_tasks
from agentgauge.tasks import Task

ECHO_TOOL = Tool(
    name="echo",
    description="Echo a message",
    inputSchema={
        "type": "object",
        "properties": {"message": {"type": "string", "description": "Text"}},
        "required": ["message"],
    },
)


def _make_mock_client(success: bool = True, error: str | None = None) -> MCPClient:
    session = MagicMock()
    if success:
        session.call_tool = AsyncMock(
            return_value=MagicMock(content=[MagicMock(type="text", text="result")])
        )
    else:
        session.call_tool = AsyncMock(side_effect=RuntimeError(error or "tool failed"))
    return MCPClient(session)


def _task(tool_name: str = "echo") -> Task:
    return Task(tool_name=tool_name, description="Echo a message", sample_args={"message": "test"})


# --- _parse_tool_selection unit tests ---


def test_parse_direct_json() -> None:
    result = _parse_tool_selection('{"tool": "echo", "args": {"message": "hi"}}')
    assert result == ("echo", {"message": "hi"})


def test_parse_json_embedded_in_text() -> None:
    text = 'Sure! Here: {"tool": "echo", "args": {}} — that is the answer.'
    tool, args = _parse_tool_selection(text)
    assert tool == "echo"
    assert args == {}


def test_parse_invalid_json_returns_none() -> None:
    assert _parse_tool_selection("not json at all") == (None, None)


def test_parse_json_without_tool_key_returns_none() -> None:
    assert _parse_tool_selection('{"foo": "bar"}') == (None, None)


def test_parse_missing_args_defaults_to_empty_dict() -> None:
    tool, args = _parse_tool_selection('{"tool": "echo"}')
    assert tool == "echo"
    assert args == {}


# --- run_tasks integration tests ---


async def test_run_tasks_selects_correct_tool() -> None:
    provider = MockProvider(responses=[json.dumps({"tool": "echo", "args": {"message": "hi"}})])
    client = _make_mock_client()
    results = await run_tasks([_task()], client, provider)
    assert len(results) == 1
    assert results[0].selected_tool == "echo"
    assert results[0].success is True


async def test_run_tasks_records_constructed_args() -> None:
    provider = MockProvider(responses=[json.dumps({"tool": "echo", "args": {"message": "hello"}})])
    client = _make_mock_client()
    results = await run_tasks([_task()], client, provider)
    assert results[0].constructed_args == {"message": "hello"}


async def test_run_tasks_unparseable_response() -> None:
    provider = MockProvider(responses=["not json"])
    client = _make_mock_client()
    results = await run_tasks([_task()], client, provider)
    assert len(results) == 1
    assert results[0].selected_tool is None
    assert results[0].success is False
    assert results[0].error is not None


async def test_run_tasks_tool_call_failure() -> None:
    provider = MockProvider(responses=[json.dumps({"tool": "echo", "args": {"message": "hi"}})])
    client = _make_mock_client(success=False, error="tool not found")
    results = await run_tasks([_task()], client, provider)
    assert results[0].success is False
    assert "tool not found" in (results[0].error or "")


async def test_run_tasks_multiple_trials() -> None:
    resp = json.dumps({"tool": "echo", "args": {"message": "hi"}})
    provider = MockProvider(responses=[resp] * 3)
    client = _make_mock_client()
    results = await run_tasks([_task()], client, provider, trials=3)
    assert len(results) == 3
    assert all(r.success for r in results)


async def test_run_tasks_multiple_tasks() -> None:
    t1 = Task(tool_name="echo", description="Echo a message", sample_args={"message": "test"})
    t2 = Task(tool_name="add", description="Add numbers", sample_args={"a": 1, "b": 2})
    provider = MockProvider(
        responses=[
            json.dumps({"tool": "echo", "args": {"message": "hi"}}),
            json.dumps({"tool": "add", "args": {"a": 1, "b": 2}}),
        ]
    )
    client = _make_mock_client()
    results = await run_tasks([t1, t2], client, provider)
    assert len(results) == 2
    assert results[0].selected_tool == "echo"
    assert results[1].selected_tool == "add"


async def test_run_tasks_empty_tasks() -> None:
    provider = MockProvider()
    client = _make_mock_client()
    results = await run_tasks([], client, provider)
    assert results == []
