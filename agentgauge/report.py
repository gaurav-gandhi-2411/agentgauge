from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from agentgauge.scorer import ScoredReport


def render_text(report: ScoredReport, console: Console | None = None) -> None:
    if console is None:
        console = Console()

    score_color = "green" if report.overall >= 75 else "yellow" if report.overall >= 50 else "red"
    console.print()
    console.print(
        Text(f"  AgentGauge Score: {report.overall:.1f}/100", style=f"bold {score_color}")
    )
    console.print(f"  Tools inspected: {report.tool_count}")
    console.print()

    table = Table(title="Dimension Breakdown", show_header=True, header_style="bold cyan")
    table.add_column("Dimension", style="dim", width=24)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Status", width=14)

    for dim in report.dimensions:
        if dim.details.get("status") == "not_implemented":
            status = Text("not yet", style="dim")
        elif dim.score >= 75:
            status = Text("good", style="green")
        elif dim.score >= 50:
            status = Text("fair", style="yellow")
        else:
            status = Text("needs work", style="red")
        table.add_row(dim.name, f"{dim.score:.1f}", status)

    console.print(table)

    all_hints = [
        (dim.name, hint)
        for dim in report.dimensions
        for hint in dim.fix_hints
        if dim.details.get("status") != "not_implemented"
    ]

    if all_hints:
        console.print()
        console.print("[bold]Prioritized Fixes[/bold]")
        for i, (dim_name, hint) in enumerate(all_hints[:10], 1):
            console.print(f"  {i}. [{dim_name}] {hint}")

    console.print()
