from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool

from agentgauge.client import MCPClient
from agentgauge.providers import MockProvider
from agentgauge.runner import RunResult, run_tasks
from agentgauge.tasks import Task


def _make_mock_client(tool_name: str = "echo") -> MCPClient:
    session = MagicMock()

    tools_resp = MagicMock()
    tools_resp.tools = [
        Tool(
            name=tool_name,
            description="Echo a message",
            inputSchema={
                "type": "object",
                "properties": {"message": {"type": "string", "description": "Text"}},
                "required": ["message"],
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

    call_resp = MagicMock()
    call_resp.content = [MagicMock(type="text", text="hello")]
    session.call_tool = AsyncMock(return_value=call_resp)

    return MCPClient(session)


async def test_run_tasks_returns_run_results() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", '{"message": "example"}'])
    tasks = [
        Task(
            tool_name="echo",
            description="Call echo: Echo a message",
            sample_args={"message": "example"},
        )
    ]

    results = await run_tasks(tasks, client, provider)

    assert len(results) == 1
    assert isinstance(results[0], RunResult)
    assert results[0].selected_tool == "echo"
    assert results[0].success is True


async def test_run_tasks_multiple_trials() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", "{}"])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider, trials=2)
    assert len(results) == 2


async def test_run_tasks_invalid_json_args_uses_empty_dict() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", "not valid json"])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].constructed_args == {}


async def test_run_tasks_tool_call_failure() -> None:
    client = _make_mock_client("echo")
    client._session.call_tool = AsyncMock(side_effect=RuntimeError("bad call"))
    provider = MockProvider(responses=["echo", "{}"])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].success is False
    assert results[0].error is not None


async def test_run_tasks_empty_tasks() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", "{}"])

    results = await run_tasks([], client, provider)
    assert results == []


async def test_run_tasks_selected_tool_recorded() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", '{"message": "hi"}'])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].selected_tool == "echo"
    assert results[0].constructed_args == {"message": "hi"}
