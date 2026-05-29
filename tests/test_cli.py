from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import Tool
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.client import MCPClient, ServerInfo, ToolCallResult

ECHO_TOOL = Tool(
    name="echo",
    description="Echo a message back",
    inputSchema={
        "type": "object",
        "properties": {"message": {"type": "string", "description": "Text"}},
        "required": ["message"],
    },
)


def _make_mock_client() -> MCPClient:
    session = MagicMock()
    client = MCPClient(session)
    client.introspect = AsyncMock(
        return_value=ServerInfo(tools=[ECHO_TOOL], resources=[], prompts=[])
    )
    client.call_tool = AsyncMock(return_value=ToolCallResult(success=True, content=[], error=None))
    return client


def test_scan_mock_provider(tmp_path) -> None:
    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())

    with (
        patch(
            "agentgauge.cli.connect_stdio",
            new=AsyncMock(return_value=(mock_client, fake_ctx)),
        ),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
    ):
        result = runner.invoke(app, ["scan", "examples/echo_server.py", "--mock"])

    assert result.exit_code == 0, result.output
    assert "AgentGauge Score" in result.output


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
