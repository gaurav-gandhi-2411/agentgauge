from __future__ import annotations

from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from agentgauge import cli
from agentgauge.audit import AuditFinding, AuditReport
from agentgauge.client import MCPClient, ServerInfo
from agentgauge.fixer import FixCandidate, FixReport
from agentgauge.report import render_text
from agentgauge.scorer import DimensionScore, ScoredReport

# Server-controlled text that Rich would parse as markup (a stray closing tag raises
# MarkupError; a valid tag is silently swallowed). Short so Rich does not wrap mid-token.
NOPE = "[/nope]"
BOLD = "[bold]x[/bold]"
HOSTILE = f"{NOPE}{BOLD}"


def _console(*, tty: bool = False) -> tuple[Console, StringIO]:
    buf = StringIO()
    return Console(file=buf, width=300, force_terminal=tty, color_system=None), buf


def _candidate(**kw: object) -> FixCandidate:
    base: dict[str, object] = {
        "tool_name": f"t{HOSTILE}",
        "dim": "description_quality",
        "mode": "mock",
        "baseline_score": 1.0,
        "baseline_sigma": 0.0,
        "candidate_score": 2.0,
        "candidate_sigma": 0.0,
        "delta": 1.0,
        "threshold": 0.5,
        "accepted": True,
        "old_description": f"old {HOSTILE}",
        "new_description": f"new {HOSTILE}",
    }
    base.update(kw)
    return FixCandidate(**base)  # type: ignore[arg-type]


def test_audit_report_renders_hostile_text_literally() -> None:
    console, buf = _console()
    report = AuditReport(
        findings=[
            AuditFinding(check=f"c{HOSTILE}", severity="block", detail=f"d{HOSTILE}"),
            AuditFinding(check=f"w{HOSTILE}", severity="warn", detail=f"e{HOSTILE}"),
        ]
    )
    cli._print_audit_report(report, console)
    out = buf.getvalue()
    for s in (f"c{HOSTILE}", f"d{HOSTILE}", f"w{HOSTILE}", f"e{HOSTILE}"):
        assert s in out


@pytest.mark.parametrize("tty", [False, True])
def test_render_fix_inline_description_renders_literally(tty: bool) -> None:
    console, buf = _console(tty=tty)
    cli._render_fix_inline(_candidate(), console)
    out = buf.getvalue()
    assert f"t{HOSTILE}:description_quality" in out
    assert f"old {HOSTILE}" in out
    assert f"new {HOSTILE}" in out


@pytest.mark.parametrize("tty", [False, True])
def test_render_fix_inline_schema_renders_literally(tty: bool) -> None:
    console, buf = _console(tty=tty)
    cand = _candidate(
        dim="schema_completeness",
        new_schema_props={f"p{HOSTILE}": {"description": f"new {HOSTILE}"}},
        old_schema_props={f"p{HOSTILE}": {"description": f"old {HOSTILE}"}},
    )
    cli._render_fix_inline(cand, console)
    out = buf.getvalue()
    assert f"p{HOSTILE}:" in out
    assert f"new {HOSTILE}" in out
    assert f"old {HOSTILE}" in out


def test_render_text_prioritized_fixes_renders_literally() -> None:
    console, buf = _console()
    dim = DimensionScore(name="description_quality", score=40.0, fix_hints=[f"fix {HOSTILE}"])
    render_text(ScoredReport(overall=40.0, dimensions=[dim], tool_count=1), console)
    out = buf.getvalue()
    # The dimension tag in brackets used to be swallowed as markup.
    assert f"[description_quality] fix {HOSTILE}" in out


def test_fix_async_accepted_rejected_skipped_render_literally(tmp_path) -> None:
    src = tmp_path / "server.py"
    src.write_text("# stub\n", encoding="utf-8")
    report = FixReport(
        accepted=[_candidate()],
        rejected=[_candidate(accepted=False, rejection_reason=f"why {HOSTILE}")],
        skipped=[f"s{HOSTILE}"],
    )
    client = MCPClient(MagicMock())
    client.introspect = AsyncMock(return_value=ServerInfo(tools=[], resources=[], prompts=[]))
    console, buf = _console()
    with (
        patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(client, None))),
        patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        patch("agentgauge.cli.run_fixer", new=AsyncMock(return_value=report)),
    ):
        import asyncio

        asyncio.run(
            cli._fix_async(
                str(src),
                dims="description_quality",
                generator_model="mock",
                judge_model="mock",
                trials=1,
                min_delta=0.5,
                skip_above_band=100.0,
                out_diff=None,
                apply=False,
                mock=True,
                _console=console,
            )
        )
    out = buf.getvalue()
    assert f"ACCEPTED t{HOSTILE}:description_quality" in out
    assert f"REJECTED t{HOSTILE}:description_quality" in out
    assert f"why {HOSTILE}" in out
    assert f"SKIPPED s{HOSTILE}" in out


def test_fix_async_missing_target_path_with_markup_does_not_crash(tmp_path) -> None:
    import asyncio

    import typer

    console, buf = _console()
    target = str(tmp_path / "no[x]")
    with pytest.raises(typer.Exit):
        asyncio.run(
            cli._fix_async(
                target,
                dims="description_quality",
                generator_model="mock",
                judge_model="mock",
                trials=1,
                min_delta=0.5,
                skip_above_band=100.0,
                out_diff=None,
                apply=False,
                mock=True,
                _console=console,
            )
        )
    assert "no[x] not found" in buf.getvalue()
