"""CLI-level tests for `agentgauge lint --provider-compat` (stubbed server, no network/model)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import Tool
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.client import MCPClient, ServerInfo

LONG_NAME = "a" * 65  # one over the documented 64-character Vertex limit

LONG_NAME_TOOL = Tool(
    name=LONG_NAME,
    description="Look up a record.",
    inputSchema={
        "type": "object",
        "properties": {"record": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
        "required": ["record"],
    },
)


def _invoke(args: list[str]):  # type: ignore[no-untyped-def]
    client = MCPClient(MagicMock())
    client.introspect = AsyncMock(
        return_value=ServerInfo(tools=[LONG_NAME_TOOL], resources=[], prompts=[])
    )
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
    ):
        return CliRunner().invoke(app, ["lint", "stub_server.py", *args])


def test_text_output_with_flag_shows_findings_and_exits_zero() -> None:
    result = _invoke(["--provider-compat", "--show-info"])
    assert result.exit_code == 0, result.output  # advisory/info never fail CI
    # The existing text printer renders "[check]" as Rich markup, which swallows the check id,
    # so assert on tier headers and message text; check ids are asserted on the --json path.
    assert "1 ADVISORY violation(s)" in result.output
    assert LONG_NAME in result.output
    assert "INFO-severity hint(s)" in result.output


def test_json_output_with_flag_has_severities_and_not_flagged() -> None:
    result = _invoke(["--provider-compat", "--show-info", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    advisory = {v["check"] for v in payload["advisory"]}
    info = {v["check"] for v in payload["info"]}
    assert "provider_compat_tool_name" in advisory
    assert "provider_compat_schema_size" in info
    assert payload["flagged"] is False
    assert payload["n_blocking"] == 0


def test_default_run_shows_no_provider_compat_finding() -> None:
    text = _invoke(["--show-info"])
    assert "Gemini/Vertex" not in text.output
    assert "ADVISORY violation(s)" not in text.output
    payload = json.loads(_invoke(["--show-info", "--json"]).output)
    checks = {v["check"] for key in ("blocking", "advisory", "info") for v in payload[key]}
    assert not any(c.startswith("provider_compat") for c in checks)
