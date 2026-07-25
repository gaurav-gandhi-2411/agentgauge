"""Tests for the cost/timing accounting surfaced in `agentgauge diff`/`eval` output
(spec-agentgauge-v0.5.md S4.1: "Cost accounting per run ... surfaced in the diff
output"). Live-mode runs use `--mock` (MockProvider has no token/cost tracking, which
exercises the "n/a" path); replay-mode runs prove the explicit "no live cost to
report" message never degrades to printed zeros.
"""

from __future__ import annotations

import json
from pathlib import Path
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


def _write_tasks_file(tmp_path: Path) -> Path:
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(
        json.dumps(
            [{"tool_name": "echo", "description": "Send a message back", "constraints": []}]
        ),
        encoding="utf-8",
    )
    return tasks_file


def _write_replay_file(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps(
            [
                {"task_tool_name": "echo", "selected_tool": "echo", "constraint_satisfaction": 1.0},
                {"task_tool_name": "echo", "selected_tool": "echo", "constraint_satisfaction": 1.0},
            ]
        ),
        encoding="utf-8",
    )
    return path


class TestDiffCostAccounting:
    def test_live_mock_run_prints_cost_summary_line(self, tmp_path: Path) -> None:
        runner = CliRunner()
        mock_client = _make_mock_client()
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        tasks_file = _write_tasks_file(tmp_path)

        with (
            patch(
                "agentgauge.cli.connect_stdio",
                new=AsyncMock(return_value=(mock_client, fake_ctx)),
            ),
            patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        ):
            result = runner.invoke(
                app,
                [
                    "diff",
                    "examples/echo_server.py",
                    "examples/echo_server_fixed.py",
                    "--tasks",
                    str(tasks_file),
                    "--mock",
                ],
            )

        assert result.exit_code in (0, 1), result.output
        assert "before cost: provider=mock" in result.output
        assert "after cost: provider=mock" in result.output
        # MockProvider has no token/cost tracking -- must say "n/a", never a fake $0.000000.
        assert "est_spend=n/a" in result.output

    def test_live_mock_run_json_mode_includes_cost_keys(self, tmp_path: Path) -> None:
        runner = CliRunner()
        mock_client = _make_mock_client()
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        tasks_file = _write_tasks_file(tmp_path)

        with (
            patch(
                "agentgauge.cli.connect_stdio",
                new=AsyncMock(return_value=(mock_client, fake_ctx)),
            ),
            patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        ):
            result = runner.invoke(
                app,
                [
                    "diff",
                    "examples/echo_server.py",
                    "examples/echo_server_fixed.py",
                    "--tasks",
                    str(tasks_file),
                    "--mock",
                    "--json",
                ],
            )

        payload = json.loads(result.output)
        assert payload["before_cost"]["live"] is True
        assert payload["before_cost"]["provider"] == "mock"
        assert payload["before_cost"]["cost_usd"] is None
        assert payload["after_cost"]["live"] is True

    def test_replay_mode_reports_no_live_cost_explicitly(self, tmp_path: Path) -> None:
        runner = CliRunner()
        replay_before = _write_replay_file(tmp_path, "before.json")
        replay_after = _write_replay_file(tmp_path, "after.json")

        result = runner.invoke(
            app,
            [
                "diff",
                "unused_before.py",
                "unused_after.py",
                "--replay-before",
                str(replay_before),
                "--replay-after",
                str(replay_after),
            ],
        )

        assert result.exit_code in (0, 1), result.output
        assert "before cost: replay mode -- no live cost to report." in result.output
        assert "after cost: replay mode -- no live cost to report." in result.output
        # Never a printed-zero that looks like a real free run.
        assert "est_spend=$0.000000" not in result.output

    def test_replay_mode_json_marks_live_false(self, tmp_path: Path) -> None:
        runner = CliRunner()
        replay_before = _write_replay_file(tmp_path, "before.json")
        replay_after = _write_replay_file(tmp_path, "after.json")

        result = runner.invoke(
            app,
            [
                "diff",
                "unused_before.py",
                "unused_after.py",
                "--replay-before",
                str(replay_before),
                "--replay-after",
                str(replay_after),
                "--json",
            ],
        )

        payload = json.loads(result.output)
        assert payload["before_cost"] == {
            "live": False,
            "note": "replay mode -- no live cost to report",
        }
        assert payload["after_cost"] == {
            "live": False,
            "note": "replay mode -- no live cost to report",
        }


class TestEvalCostAccounting:
    def test_live_mock_run_prints_cost_summary_line(self, tmp_path: Path) -> None:
        runner = CliRunner()
        mock_client = _make_mock_client()
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        tasks_file = _write_tasks_file(tmp_path)

        with (
            patch(
                "agentgauge.cli.connect_stdio",
                new=AsyncMock(return_value=(mock_client, fake_ctx)),
            ),
            patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        ):
            result = runner.invoke(
                app,
                ["eval", "examples/echo_server.py", "--tasks", str(tasks_file), "--mock"],
            )

        assert "cost: provider=mock" in result.output

    def test_json_mode_includes_cost_key(self, tmp_path: Path) -> None:
        runner = CliRunner()
        mock_client = _make_mock_client()
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        tasks_file = _write_tasks_file(tmp_path)

        with (
            patch(
                "agentgauge.cli.connect_stdio",
                new=AsyncMock(return_value=(mock_client, fake_ctx)),
            ),
            patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        ):
            result = runner.invoke(
                app,
                [
                    "eval",
                    "examples/echo_server.py",
                    "--tasks",
                    str(tasks_file),
                    "--mock",
                    "--json",
                ],
            )

        payload = json.loads(result.output)
        assert payload["cost"]["live"] is True
        assert payload["cost"]["provider"] == "mock"
