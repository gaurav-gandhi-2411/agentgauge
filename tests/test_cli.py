from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import Tool
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.client import MCPClient, ServerInfo, ToolCallResult
from agentgauge.scorer import ScoredReport

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


def test_ci_exits_zero_when_above_threshold() -> None:
    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    mock_report = ScoredReport(overall=80.0, tool_count=1, dimensions=[])

    with (
        patch(
            "agentgauge.cli.connect_stdio",
            new=AsyncMock(return_value=(mock_client, fake_ctx)),
        ),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.score_all", new=AsyncMock(return_value=mock_report)),
    ):
        result = runner.invoke(
            app, ["ci", "examples/echo_server.py", "--mock", "--min-score", "70"]
        )

    assert result.exit_code == 0, result.output


def test_ci_exits_one_when_below_threshold() -> None:
    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    mock_report = ScoredReport(overall=40.0, tool_count=1, dimensions=[])

    with (
        patch(
            "agentgauge.cli.connect_stdio",
            new=AsyncMock(return_value=(mock_client, fake_ctx)),
        ),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.score_all", new=AsyncMock(return_value=mock_report)),
    ):
        result = runner.invoke(
            app, ["ci", "examples/echo_server.py", "--mock", "--min-score", "70"]
        )

    assert result.exit_code == 1, result.output


def test_scan_echo_server_subprocess() -> None:
    """End-to-end: spawn the real CLI against the echo server using sys.executable.

    This catches the regression where connect_stdio("python", ...) used the system
    Python instead of the venv interpreter, causing ModuleNotFoundError on mcp.
    """
    repo_root = Path(__file__).parent.parent
    echo_server = repo_root / "examples" / "echo_server.py"
    result = subprocess.run(
        [sys.executable, "-m", "agentgauge", "scan", str(echo_server), "--mock"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"scan exited {result.returncode}:\n{result.stderr}"
    assert "AgentGauge Score" in result.stdout
