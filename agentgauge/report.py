from __future__ import annotations

import dataclasses
import json

from rich.console import Console
from rich.table import Table
from rich.text import Text

from agentgauge.scorer import DIMENSION_WEIGHTS, ScoredReport


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


def render_json(report: ScoredReport) -> str:
    """Serialize a ScoredReport to indented JSON."""
    return json.dumps(dataclasses.asdict(report), indent=2, default=str)


def render_json_stable(report: ScoredReport) -> str:
    """Serialize a ScoredReport to the stable versioned JSON schema."""
    dimensions = [
        {"name": dim.name, "score": dim.score, "weight": DIMENSION_WEIGHTS.get(dim.name, 0.0)}
        for dim in report.dimensions
    ]
    doc: dict[str, object] = {
        "schema_version": "1.0",
        "overall_score": report.overall,
        "dimensions": dimensions,
    }
    return json.dumps(doc, indent=2)


def render_html(report: ScoredReport) -> str:
    """Produce a self-contained single-file HTML page for a ScoredReport."""
    score_color = (
        "#22c55e" if report.overall >= 75 else "#eab308" if report.overall >= 50 else "#ef4444"
    )

    rows = ""
    for dim in report.dimensions:
        if dim.details.get("status") == "not_implemented":
            status = "not yet"
            row_color = "#6b7280"
        elif dim.score >= 75:
            status = "good"
            row_color = "#22c55e"
        elif dim.score >= 50:
            status = "fair"
            row_color = "#eab308"
        else:
            status = "needs work"
            row_color = "#ef4444"
        rows += (
            f"<tr>"
            f"<td>{dim.name}</td>"
            f"<td style='text-align:right;color:{row_color};font-weight:bold'>{dim.score:.1f}</td>"
            f"<td style='color:{row_color}'>{status}</td>"
            f"</tr>\n"
        )

    all_hints = [
        (dim.name, hint)
        for dim in report.dimensions
        for hint in dim.fix_hints
        if dim.details.get("status") != "not_implemented"
    ]

    hints_html = ""
    if all_hints:
        items = "".join(
            f"<li><strong>[{name}]</strong> {hint}</li>" for name, hint in all_hints[:10]
        )
        hints_html = f"<h2>Prioritized Fixes</h2><ol>{items}</ol>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentGauge Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #0f172a; color: #e2e8f0; }}
  h1 {{ font-size: 1.5rem; color: #94a3b8; }}
  .score {{ font-size: 4rem; font-weight: 800; color: {score_color}; margin: 8px 0; }}
  .meta {{ color: #64748b; margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
  th {{ text-align: left; padding: 8px 12px; background: #1e293b; color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; }}
  tr:hover td {{ background: #1e293b; }}
  h2 {{ color: #94a3b8; font-size: 1.1rem; margin-top: 32px; }}
  ol {{ padding-left: 20px; line-height: 1.8; }}
  li {{ color: #cbd5e1; }}
  li strong {{ color: #93c5fd; }}
</style>
</head>
<body>
<h1>AgentGauge Report</h1>
<div class="score">{report.overall:.1f}<span style="font-size:1.5rem;color:#64748b">/100</span></div>
<div class="meta">Tools inspected: {report.tool_count}</div>
<table>
  <thead><tr><th>Dimension</th><th style="text-align:right">Score</th><th>Status</th></tr></thead>
  <tbody>
{rows}  </tbody>
</table>
{hints_html}
</body>
</html>"""
