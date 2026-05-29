from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import Tool

from agentgauge.client import MCPClient


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()

    tools_resp = MagicMock()
    tools_resp.tools = [
        Tool(
            name="echo",
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

    return session


async def test_introspect_returns_server_info(mock_session: MagicMock) -> None:
    client = MCPClient(mock_session)
    info = await client.introspect()
    assert len(info.tools) == 1
    assert info.tools[0].name == "echo"
    assert info.resources == []
    assert info.prompts == []


async def test_call_tool_success(mock_session: MagicMock) -> None:
    client = MCPClient(mock_session)
    result = await client.call_tool("echo", {"message": "hi"})
    assert result.success is True
    assert result.error is None
    mock_session.call_tool.assert_called_once_with("echo", {"message": "hi"})


async def test_call_tool_failure(mock_session: MagicMock) -> None:
    mock_session.call_tool = AsyncMock(side_effect=RuntimeError("tool not found"))
    client = MCPClient(mock_session)
    result = await client.call_tool("missing", {})
    assert result.success is False
    assert "tool not found" in (result.error or "")
