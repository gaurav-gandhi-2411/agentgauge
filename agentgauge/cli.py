from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agentgauge import __version__
from agentgauge.client import cleanup_connection, connect_http, connect_stdio
from agentgauge.providers import MockProvider, OllamaProvider
from agentgauge.report import render_text
from agentgauge.scorer import score_all

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
    model: Annotated[str, typer.Option("--model", "-m", help="Ollama model name")] = "llama3.2",
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
        # Treat as Python script path
        client, ctx = await connect_stdio("python", [target])

    try:
        info = await client.introspect()
        console.print(
            f"[dim]Found {len(info.tools)} tools, "
            f"{len(info.resources)} resources, "
            f"{len(info.prompts)} prompts[/dim]"
        )

        report = await score_all(info.tools, provider, trials=trials)
        render_text(report, console)

        if out is not None:
            import dataclasses
            import json

            out.write_text(
                json.dumps(dataclasses.asdict(report), indent=2, default=str), encoding="utf-8"
            )
            console.print(f"[dim]JSON report written to {out}[/dim]")

    finally:
        await cleanup_connection(ctx)
