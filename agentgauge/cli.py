from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agentgauge import __version__
from agentgauge.client import cleanup_connection, connect_http, connect_stdio
from agentgauge.providers import MockProvider, OllamaProvider
from agentgauge.report import render_html, render_json, render_text
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
) -> None:
    console = Console()
    provider = MockProvider() if mock else OllamaProvider(model)

    console.print(f"[dim]Connecting to [bold]{target}[/bold]...[/dim]")

    if target.startswith("http://") or target.startswith("https://"):
        client, ctx = await connect_http(target)
    else:
        # Use sys.executable so the subprocess inherits the active venv, not system Python.
        client, ctx = await connect_stdio(sys.executable, [target])

    try:
        info = await client.introspect()
        console.print(
            f"[dim]Found {len(info.tools)} tools, "
            f"{len(info.resources)} resources, "
            f"{len(info.prompts)} prompts[/dim]"
        )

        report = await score_all(info.tools, provider, client=client, trials=trials)
        render_text(report, console)

        if out is not None:
            suffix = out.suffix.lower()
            if suffix == ".json":
                out.write_text(render_json(report), encoding="utf-8")
                console.print(f"[dim]JSON report written to {out}[/dim]")
            elif suffix == ".html":
                out.write_text(render_html(report), encoding="utf-8")
                console.print(f"[dim]HTML report written to {out}[/dim]")
            else:
                console.print(
                    f"[yellow]Warning: unsupported output format '{suffix}' — skipping write[/yellow]"
                )

    finally:
        await cleanup_connection(ctx)
