from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import Tool
from rich.console import Console
from typer.testing import CliRunner

from agentgauge.cli import _bak_path, _render_fix_inline, app
from agentgauge.client import MCPClient, ServerInfo, ToolCallResult
from agentgauge.fixer import FixCandidate, FixReport, ValidationMode
from agentgauge.scorer import ScoredReport

# ── helpers ───────────────────────────────────────────────────────────────────

MYSTERY_TOOL = Tool(
    name="mystery",
    description="",
    inputSchema={
        "type": "object",
        "properties": {
            "x": {},
            "y": {},
        },
    },
)

GREET_TOOL = Tool(
    name="greet",
    description="",
    inputSchema={
        "type": "object",
        "properties": {"name": {"type": "string"}},
    },
)


def _make_mock_client(tools: list[Tool] | None = None) -> MCPClient:
    if tools is None:
        tools = [MYSTERY_TOOL, GREET_TOOL]
    session = MagicMock()
    client = MCPClient(session)
    client.introspect = AsyncMock(return_value=ServerInfo(tools=tools, resources=[], prompts=[]))
    client.call_tool = AsyncMock(return_value=ToolCallResult(success=True, content=[], error=None))
    return client


def _accepted_desc_candidate(
    tool_name: str = "mystery",
    old_desc: str = "old description",
    new_desc: str = "new description",
    delta: float = 20.0,
) -> FixCandidate:
    return FixCandidate(
        tool_name=tool_name,
        dim="description_quality",
        mode=ValidationMode.JUDGE_BASED,
        baseline_score=50.0,
        baseline_sigma=0.0,
        candidate_score=70.0,
        candidate_sigma=0.0,
        delta=delta,
        threshold=10.0,
        accepted=True,
        old_description=old_desc,
        new_description=new_desc,
    )


def _accepted_schema_candidate(
    tool_name: str = "mystery",
    old_props: dict | None = None,
    new_props: dict | None = None,
    delta: float = 40.0,
) -> FixCandidate:
    return FixCandidate(
        tool_name=tool_name,
        dim="schema_completeness",
        mode=ValidationMode.DETERMINISTIC,
        baseline_score=30.0,
        baseline_sigma=0.0,
        candidate_score=70.0,
        candidate_sigma=0.0,
        delta=delta,
        threshold=10.0,
        accepted=True,
        old_schema_props=old_props or {"x": {}, "y": {}},
        new_schema_props=new_props
        or {
            "x": {"type": "number", "description": "First input"},
            "y": {"type": "number", "description": "Second input"},
        },
    )


def _mock_fix_report_with_accepted(candidate: FixCandidate) -> FixReport:
    return FixReport(
        accepted=[candidate],
        rejected=[],
        skipped=[],
        patched_source="# patched",
        diff_text="--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n",
    )


# ── _bak_path: non-destructive backup path selection ─────────────────────────


def test_bak_path_no_existing(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text("content")
    bak = _bak_path(src)
    assert bak == Path(str(src) + ".bak")
    assert not bak.exists()


def test_bak_path_increments_when_bak_exists(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text("content")
    bak0 = Path(str(src) + ".bak")
    bak0.write_text("backup0")

    bak = _bak_path(src)
    assert bak == Path(str(src) + ".bak.1")
    assert not bak.exists()


def test_bak_path_increments_past_bak1(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text("content")
    Path(str(src) + ".bak").write_text("b0")
    Path(str(src) + ".bak.1").write_text("b1")

    bak = _bak_path(src)
    assert bak == Path(str(src) + ".bak.2")


# ── _render_fix_inline: TTY (color) and no-TTY (+/- markers) paths ───────────


def _capture_render(candidate: FixCandidate, *, force_terminal: bool) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=force_terminal, highlight=False)
    _render_fix_inline(candidate, console)
    return buf.getvalue()


def test_render_desc_tty_contains_old_and_new() -> None:
    c = _accepted_desc_candidate(old_desc="old description here", new_desc="new description here")
    out = _capture_render(c, force_terminal=True)
    assert "old description here" in out
    assert "new description here" in out


def test_render_desc_no_tty_uses_plus_minus_markers() -> None:
    c = _accepted_desc_candidate(old_desc="OLD TEXT", new_desc="NEW TEXT")
    out = _capture_render(c, force_terminal=False)
    assert "- OLD TEXT" in out
    assert "+ NEW TEXT" in out


def test_render_schema_tty_contains_param_names() -> None:
    c = _accepted_schema_candidate(new_props={"x": {"type": "number", "description": "X value"}})
    out = _capture_render(c, force_terminal=True)
    assert "x" in out
    assert "X value" in out


def test_render_schema_no_tty_uses_plus_minus_markers() -> None:
    c = _accepted_schema_candidate(
        old_props={"x": {}},
        new_props={"x": {"type": "number", "description": "X value"}},
    )
    out = _capture_render(c, force_terminal=False)
    assert "+ " in out
    assert "- " in out


# ── fix --mock (no --apply): writes nothing ───────────────────────────────────


def test_fix_mock_no_apply_writes_nothing(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    original_content = "# original"
    src.write_text(original_content)

    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())

    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
    ):
        result = runner.invoke(app, ["fix", str(src), "--mock"])

    assert result.exit_code == 0, result.output
    assert src.read_text() == original_content
    assert not Path(str(src) + ".bak").exists()


# ── fix --mock --apply: creates .bak, second run creates .bak.1 ──────────────


def test_fix_apply_creates_bak(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    original_content = "# original server"
    src.write_text(original_content)

    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    candidate = _accepted_desc_candidate()
    fix_report = _mock_fix_report_with_accepted(candidate)

    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=fix_report)),
    ):
        result = runner.invoke(app, ["fix", str(src), "--mock", "--apply"])

    assert result.exit_code == 0, result.output
    bak = Path(str(src) + ".bak")
    assert bak.exists(), "backup file must be created"
    assert bak.read_text() == original_content


def test_fix_apply_second_run_creates_bak1_not_stomping_bak(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    original_content = "# original server"
    src.write_text(original_content)

    runner = CliRunner()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    candidate = _accepted_desc_candidate()

    def _make_run(content: str):
        report = FixReport(
            accepted=[candidate],
            rejected=[],
            skipped=[],
            patched_source=content,
            diff_text="--- a\n+++ b\n",
        )
        mock_client = _make_mock_client()
        return mock_client, report

    # First apply
    mock_client1, fix_report1 = _make_run("# patched v1")
    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client1, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=fix_report1)),
    ):
        runner.invoke(app, ["fix", str(src), "--mock", "--apply"])

    bak0 = Path(str(src) + ".bak")
    assert bak0.exists()
    content_after_first = src.read_text()

    # Second apply — .bak already exists, must produce .bak.1
    mock_client2, fix_report2 = _make_run("# patched v2")
    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client2, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=fix_report2)),
    ):
        runner.invoke(app, ["fix", str(src), "--mock", "--apply"])

    bak1 = Path(str(src) + ".bak.1")
    assert bak1.exists(), ".bak.1 must be created on second apply"
    assert bak0.read_text() == original_content, ".bak must not be stomped"
    assert bak1.read_text() == content_after_first


# ── fix --mock (preview): inline before/after in stdout ──────────────────────


def test_fix_preview_shows_old_and_new_in_stdout(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text("# server content")

    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    candidate = _accepted_desc_candidate(old_desc="OLD DESCRIPTION", new_desc="NEW DESCRIPTION")
    fix_report = FixReport(
        accepted=[candidate],
        rejected=[],
        skipped=[],
        patched_source="# patched",
        diff_text="",
    )

    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=fix_report)),
    ):
        result = runner.invoke(app, ["fix", str(src), "--mock"])

    assert result.exit_code == 0, result.output
    assert "OLD DESCRIPTION" in result.output
    assert "NEW DESCRIPTION" in result.output


def test_fix_preview_no_tty_uses_plus_minus_markers(tmp_path: Path) -> None:
    """CliRunner output is not a TTY — markers must appear."""
    src = tmp_path / "server.py"
    src.write_text("# server content")

    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    candidate = _accepted_desc_candidate(old_desc="OLD DESCRIPTION", new_desc="NEW DESCRIPTION")
    fix_report = FixReport(
        accepted=[candidate],
        rejected=[],
        skipped=[],
        patched_source="# patched",
        diff_text="",
    )

    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=fix_report)),
    ):
        result = runner.invoke(app, ["fix", str(src), "--mock"])

    # CliRunner doesn't attach a real TTY, so Rich's is_terminal is False
    # → +/- markers path is used
    assert "- OLD DESCRIPTION" in result.output
    assert "+ NEW DESCRIPTION" in result.output


# ── try --mock: exits 0, prints score + inline, writes nothing ────────────────


def test_try_mock_exits_zero(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text("# server")

    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    mock_report = ScoredReport(overall=60.0, tool_count=2, dimensions=[])

    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.score_all", new=AsyncMock(return_value=mock_report)),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=FixReport())),
    ):
        result = runner.invoke(app, ["try", str(src), "--mock"])

    assert result.exit_code == 0, result.output


def test_try_mock_prints_apply_hint(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text("# server")

    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    mock_report = ScoredReport(overall=60.0, tool_count=2, dimensions=[])

    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.score_all", new=AsyncMock(return_value=mock_report)),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=FixReport())),
    ):
        result = runner.invoke(app, ["try", str(src), "--mock"])

    assert "--apply" in result.output


def test_try_mock_writes_nothing(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    original = "# original server content"
    src.write_text(original)

    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    mock_report = ScoredReport(overall=60.0, tool_count=2, dimensions=[])
    candidate = _accepted_desc_candidate()
    fix_report = _mock_fix_report_with_accepted(candidate)

    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.score_all", new=AsyncMock(return_value=mock_report)),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=fix_report)),
    ):
        result = runner.invoke(app, ["try", str(src), "--mock"])

    assert result.exit_code == 0, result.output
    assert src.read_text() == original, "try must not modify the target file"
    assert not Path(str(src) + ".bak").exists(), "try must not create a backup"


def test_try_mock_prints_inline_before_after(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text("# server content")

    runner = CliRunner()
    mock_client = _make_mock_client()
    fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
    mock_report = ScoredReport(overall=60.0, tool_count=2, dimensions=[])
    candidate = _accepted_desc_candidate(old_desc="OLD DESC", new_desc="NEW DESC")
    fix_report = FixReport(
        accepted=[candidate],
        rejected=[],
        skipped=[],
        patched_source="# patched",
        diff_text="",
    )

    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(mock_client, fake_ctx))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.score_all", new=AsyncMock(return_value=mock_report)),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=fix_report)),
    ):
        result = runner.invoke(app, ["try", str(src), "--mock"])

    assert result.exit_code == 0, result.output
    assert "OLD DESC" in result.output
    assert "NEW DESC" in result.output
