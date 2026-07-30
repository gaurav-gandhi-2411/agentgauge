from __future__ import annotations

import json
import re
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
    from agentgauge import __version__

    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


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


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    """Strip ANSI escape codes and the soft-wrap linebreaks Typer/Rich's `--help` renderer can
    inject mid-token (e.g. splitting "--experimental" across a color-code boundary) -- CI's Linux
    runner renders `--help` with color even though this repo's other CLI tests never hit this
    because they don't assert on hyphen-prefixed option tokens inside help/rich-rendered text."""
    return _ANSI_RE.sub("", output)


class TestAttributeExperimentalGate:
    """v0.5.0: `agentgauge attribute` is gated experimental, off by default
    (reports/v0_5_probe_power_fix.md's measured cost finding -- attribution costs
    1.01x-20.24x a full re-evaluation; not shipped for production use)."""

    def test_refuses_without_experimental_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["attribute"])
        assert result.exit_code == 1
        assert "--experimental" in _plain(result.output)

    def test_refusal_message_states_measured_cost_numbers(self) -> None:
        """Per Task 1b: help/refusal text must state the measured reason in numbers, no
        adjectives."""
        runner = CliRunner()
        result = runner.invoke(app, ["attribute"])
        output = _plain(result.output)
        assert "1.01x" in output
        assert "20.24x" in output
        assert "2-4 changed tools" in output
        assert "v0_5_probe_power_fix.md" in output

    def test_proceeds_with_experimental_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["attribute", "--experimental"])
        assert result.exit_code == 0
        assert "Experimental mode acknowledged" in _plain(result.output)

    def test_help_text_mentions_experimental_gate(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["attribute", "--help"])
        output = _plain(result.output)
        assert result.exit_code == 0
        assert "EXPERIMENTAL" in output
        assert "--experimental" in output


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


class TestScoringReferenceConsistencyGate:
    """Integration-level regression tests for the artifact #7 class in shipped
    product code (v2.5, Task 1): `agentgauge diff`/`eval`'s live task-file
    constraints must be checked against the ACTUAL connected schema before
    any live inference runs, not just before a result is reported. Seeded
    with the real historical case (`evals/fixtures/v2_3_advisory_audit.json`
    / `reports/v2_3_task1_advisory_audit.md`): a schema property renamed
    'field' -> 'field_v2', with the task file's gold constraint still
    referencing the stale 'field' name.
    """

    RENAMED_TOOL = Tool(
        name="query_records",
        description="Get all orders matching a field/value pair.",
        inputSchema={
            "type": "object",
            "properties": {
                "field_v2": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["field_v2", "value"],
        },
    )

    @staticmethod
    def _make_client_never_called() -> MCPClient:
        """A client whose `call_tool` raises if invoked -- proves the audit
        gate blocked BEFORE any live inference, not just before reporting."""
        session = MagicMock()
        client = MCPClient(session)
        client.introspect = AsyncMock(
            return_value=ServerInfo(
                tools=[TestScoringReferenceConsistencyGate.RENAMED_TOOL], resources=[], prompts=[]
            )
        )

        async def _fail_if_called(*_args: object, **_kwargs: object) -> None:
            raise AssertionError(
                "call_tool was invoked -- the schema-only audit pre-check did not "
                "block before live inference, defeating its fail-fast purpose"
            )

        client.call_tool = AsyncMock(side_effect=_fail_if_called)
        return client

    @staticmethod
    def _write_stale_tasks_file(tmp_path: Path) -> Path:
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(
            json.dumps(
                [
                    {
                        "tool_name": "query_records",
                        "description": "Get all orders where the status field is set to 'pending'",
                        "constraints": [
                            # stale: references the PRE-rename name 'field', not
                            # the actual schema's 'field_v2'
                            {"param": "field", "kind": "contains", "gold_value": "status"}
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        return tasks_file

    def test_diff_blocks_before_any_live_trial_on_renamed_param(self, tmp_path: Path) -> None:
        runner = CliRunner()
        mock_client = self._make_client_never_called()
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        tasks_file = self._write_stale_tasks_file(tmp_path)

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
                    "examples/confusable_server.py",
                    "examples/confusable_server_fixed.py",
                    "--tasks",
                    str(tasks_file),
                    "--mock",
                ],
            )

        assert result.exit_code == 2, result.output
        assert "scoring_reference_consistency" in result.output
        assert "field_v2" in result.output
        # No measurement was ever printed -- the gate blocked before diff_from_trials ran.
        assert "REGRESSION" not in result.output
        assert "NO_CHANGE" not in result.output
        assert "INSUFFICIENT_SENSITIVITY" not in result.output

    def test_eval_blocks_before_any_live_trial_on_renamed_param(self, tmp_path: Path) -> None:
        runner = CliRunner()
        mock_client = self._make_client_never_called()
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        tasks_file = self._write_stale_tasks_file(tmp_path)

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
                    "examples/confusable_server.py",
                    "--tasks",
                    str(tasks_file),
                    "--mock",
                ],
            )

        assert result.exit_code == 2, result.output
        assert "scoring_reference_consistency" in result.output
        assert "joint success rate" not in result.output

    def test_diff_proceeds_normally_when_schema_matches(self, tmp_path: Path) -> None:
        """Control case: the same constraint against the CORRECT (pre-rename)
        schema must not be blocked -- confirms the gate doesn't over-fire."""
        matching_tool = Tool(
            name="query_records",
            description="Get all orders matching a field/value pair.",
            inputSchema={
                "type": "object",
                "properties": {"field": {"type": "string"}, "value": {"type": "string"}},
                "required": ["field", "value"],
            },
        )
        session = MagicMock()
        mock_client = MCPClient(session)
        mock_client.introspect = AsyncMock(
            return_value=ServerInfo(tools=[matching_tool], resources=[], prompts=[])
        )
        mock_client.call_tool = AsyncMock(
            return_value=ToolCallResult(success=True, content=[], error=None)
        )
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        tasks_file = self._write_stale_tasks_file(tmp_path)
        runner = CliRunner()

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
                    "examples/confusable_server.py",
                    "examples/confusable_server_fixed.py",
                    "--tasks",
                    str(tasks_file),
                    "--mock",
                ],
            )

        assert "scoring_reference_consistency" not in result.output
        assert result.exit_code in (0, 1)  # a real verdict was reached, not an audit block
