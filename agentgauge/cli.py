from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agentgauge import __version__
from agentgauge.client import cleanup_connection, connect_http, connect_stdio
from agentgauge.fixer import (
    DEFAULT_MIN_DELTA,
    DEFAULT_SKIP_ABOVE_BAND,
    DEFAULT_TRIALS,
    JUDGE_MODEL_DEFAULT,
    assert_generator_ne_judge,
    run_fixer,
)
from agentgauge.providers import MockProvider, OllamaProvider
from agentgauge.report import render_html, render_json_stable, render_text
from agentgauge.scorer import score_all

# Model the judge rubric was calibrated against. Scores are model-specific:
# changing --model shifts absolute band values and makes results non-comparable
# to prior runs. See README.md and CLAUDE.md for calibration notes.
CALIBRATED_JUDGE_MODEL = "llama3.1:8b"

app = typer.Typer(
    name="agentgauge",
    help="Score how well an AI agent can use an MCP server.",
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"agentgauge {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    pass


@app.command()
def scan(
    target: Annotated[str, typer.Argument(help="Path to MCP server script, or HTTP/SSE URL")],
    model: Annotated[
        str,
        typer.Option(
            "--model",
            "-m",
            help=(
                f"Ollama model name (default: calibrated judge model '{CALIBRATED_JUDGE_MODEL}'). "
                "Changing this shifts absolute score bands — results are not comparable "
                "across judge models."
            ),
        ),
    ] = CALIBRATED_JUDGE_MODEL,
    trials: Annotated[int, typer.Option("--trials", "-t", help="LLM trials per dimension")] = 1,
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="Write JSON report to file")
    ] = None,
    mock: Annotated[
        bool, typer.Option("--mock", help="Use mock LLM provider (no network needed)")
    ] = False,
) -> None:
    """Scan an MCP server and print an agent-readiness score."""
    asyncio.run(_scan_async(target, model=model, trials=trials, out=out, mock=mock))


async def _scan_async(
    target: str,
    *,
    model: str,
    trials: int,
    out: Path | None,
    mock: bool,
) -> float:
    console = Console()
    provider = MockProvider() if mock else OllamaProvider(model)

    console.print(f"[dim]Connecting to [bold]{target}[/bold]...[/dim]")

    if target.startswith("http://") or target.startswith("https://"):
        client, ctx = await connect_http(target)
        base_url: str | None = target
    else:
        # Use sys.executable so the subprocess inherits the active venv, not system Python.
        client, ctx = await connect_stdio(sys.executable, [target])
        base_url = None  # stdio servers have no HTTP base URL; no llms.txt to fetch

    try:
        info = await client.introspect()
        console.print(
            f"[dim]Found {len(info.tools)} tools, "
            f"{len(info.resources)} resources, "
            f"{len(info.prompts)} prompts[/dim]"
        )

        report = await score_all(
            info.tools, provider, client=client, trials=trials, base_url=base_url
        )
        render_text(report, console)

        if out is not None:
            suffix = out.suffix.lower()
            if suffix == ".json":
                out.write_text(render_json_stable(report), encoding="utf-8")
                console.print(f"[dim]JSON report written to {out}[/dim]")
            elif suffix == ".html":
                out.write_text(render_html(report), encoding="utf-8")
                console.print(f"[dim]HTML report written to {out}[/dim]")
            else:
                console.print(
                    f"[yellow]Warning: unsupported output format '{suffix}' — skipping write[/yellow]"
                )

        return report.overall

    finally:
        await cleanup_connection(ctx)


@app.command()
def fix(
    target: Annotated[str, typer.Argument(help="Path to MCP server script")],
    dims: Annotated[
        str,
        typer.Option("--dims", help="Comma-separated dimensions to fix"),
    ] = "description_quality,schema_completeness",
    generator_model: Annotated[
        str,
        typer.Option(
            "--generator-model", help="Model for generating fixes (must differ from judge)"
        ),
    ] = "qwen3:8b",
    judge_model: Annotated[
        str,
        typer.Option("--judge-model", help="Pinned judge model for validation"),
    ] = JUDGE_MODEL_DEFAULT,
    trials: Annotated[
        int, typer.Option("--trials", help="Judge trials for JUDGE_BASED dims")
    ] = DEFAULT_TRIALS,
    min_delta: Annotated[
        float, typer.Option("--min-delta", help="Minimum score delta to accept a fix")
    ] = DEFAULT_MIN_DELTA,
    skip_above_band: Annotated[
        float,
        typer.Option(
            "--skip-above-band",
            help="Skip generation for tools already at or above this score",
        ),
    ] = DEFAULT_SKIP_ABOVE_BAND,
    out_diff: Annotated[
        Path | None, typer.Option("--out-diff", help="Write unified diff to file")
    ] = None,
    apply: Annotated[
        bool, typer.Option("--apply", help="Apply accepted fixes to the target file")
    ] = False,
    mock: Annotated[
        bool, typer.Option("--mock", help="Use mock LLM provider (no network needed)")
    ] = False,
) -> None:
    """Auto-generate improved descriptions and schema metadata for low-scoring tools."""
    asyncio.run(
        _fix_async(
            target,
            dims=dims,
            generator_model=generator_model,
            judge_model=judge_model,
            trials=trials,
            min_delta=min_delta,
            skip_above_band=skip_above_band,
            out_diff=out_diff,
            apply=apply,
            mock=mock,
        )
    )


async def _fix_async(
    target: str,
    *,
    dims: str,
    generator_model: str,
    judge_model: str,
    trials: int,
    min_delta: float,
    skip_above_band: float,
    out_diff: Path | None,
    apply: bool,
    mock: bool,
) -> None:
    """Async implementation of the fix subcommand."""
    console = Console()

    # Startup assertion: generator != judge (skip for mock — both models are "mock")
    if not mock:
        assert_generator_ne_judge(generator_model, judge_model)

    dim_list = [d.strip() for d in dims.split(",") if d.strip()]
    source_path = Path(target)
    if not source_path.exists():
        console.print(f"[red]Error: {target} not found[/red]")
        raise typer.Exit(1)

    if mock:
        generator: MockProvider | OllamaProvider = MockProvider()
        judge: MockProvider | OllamaProvider = MockProvider()
    else:
        generator = OllamaProvider(generator_model)
        judge = OllamaProvider(judge_model)

    # Introspect tools by connecting to the server
    client, ctx = await connect_stdio(sys.executable, [target])
    try:
        info = await client.introspect()
        console.print(f"[dim]Found {len(info.tools)} tools[/dim]")

        report = await run_fixer(
            info.tools,
            generator,
            judge,
            source_path,
            dim_list,
            trials=trials,
            min_delta=min_delta,
            skip_above_band=skip_above_band,
        )

        # Print results
        for c in report.accepted:
            console.print(
                f"[green]ACCEPTED[/green] {c.tool_name}:{c.dim} — "
                f"delta={c.delta:+.1f} (threshold={c.threshold:.1f})"
            )
            if c.dim == "description_quality":
                console.print(f"  New description: {c.new_description[:80]!r}")

        for c in report.rejected:
            console.print(f"[yellow]REJECTED[/yellow] {c.tool_name}:{c.dim} — {c.rejection_reason}")

        for s in report.skipped:
            console.print(f"[dim]SKIPPED {s}[/dim]")

        generated = len(report.accepted) + len(report.rejected)
        console.print(
            f"\n{generated} generated, "
            f"{len(report.accepted)} accepted, "
            f"{len(report.rejected)} rejected, "
            f"{len(report.skipped)} skipped"
        )

        if out_diff and report.diff_text:
            out_diff.write_text(report.diff_text, encoding="utf-8")
            console.print(f"[dim]Diff written to {out_diff}[/dim]")

        if apply and report.accepted and report.patched_source:
            source_path.write_text(report.patched_source, encoding="utf-8")
            console.print(f"[green]Applied {len(report.accepted)} fix(es) to {source_path}[/green]")
        elif apply and not report.accepted:
            console.print("[dim]Nothing to apply — no accepted fixes[/dim]")

    finally:
        await cleanup_connection(ctx)


@app.command()
def ci(
    target: Annotated[str, typer.Argument(help="Path to MCP server script, or HTTP/SSE URL")],
    model: Annotated[
        str,
        typer.Option(
            "--model",
            "-m",
            help=(
                f"Ollama model name (default: calibrated judge model '{CALIBRATED_JUDGE_MODEL}'). "
                "Changing this shifts absolute score bands — results are not comparable "
                "across judge models."
            ),
        ),
    ] = CALIBRATED_JUDGE_MODEL,
    trials: Annotated[int, typer.Option("--trials", "-t", help="LLM trials per dimension")] = 1,
    mock: Annotated[
        bool, typer.Option("--mock", help="Use mock LLM provider (no network needed)")
    ] = False,
    min_score: Annotated[
        int,
        typer.Option(
            "--min-score",
            help="Minimum required overall score (0–100). Exits 1 if overall_score < this value.",
        ),
    ] = 0,
) -> None:
    """Scan an MCP server and exit 1 if the overall score is below --min-score."""
    overall = asyncio.run(_scan_async(target, model=model, trials=trials, out=None, mock=mock))
    if overall < min_score:
        raise typer.Exit(1)
