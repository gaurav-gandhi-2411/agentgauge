from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from agentgauge import __version__
from agentgauge.client import cleanup_connection, connect_http, connect_stdio
from agentgauge.constraints import BlindTask, constraint_satisfaction
from agentgauge.fixer import (
    DEFAULT_MIN_DELTA,
    DEFAULT_SKIP_ABOVE_BAND,
    DEFAULT_TRIALS,
    JUDGE_MODEL_DEFAULT,
    FixCandidate,
    assert_generator_ne_judge,
    run_fixer,
)
from agentgauge.harness import DecomposedRate, DiffResult, TrialOutcome, Verdict, diff_from_trials
from agentgauge.linter import LintReport, lint_tool_set
from agentgauge.providers import MockProvider, OllamaProvider
from agentgauge.report import render_html, render_json_stable, render_text
from agentgauge.runner import RunResult, run_tasks
from agentgauge.scorer import score_all
from agentgauge.tasks import Task

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


def _bak_path(source: Path) -> Path:
    """Return a backup path that does not already exist.

    Tries <file>.bak first; if that exists, tries .bak.1, .bak.2, etc.
    """
    candidate = Path(str(source) + ".bak")
    if not candidate.exists():
        return candidate
    n = 1
    while True:
        candidate = Path(str(source) + f".bak.{n}")
        if not candidate.exists():
            return candidate
        n += 1


def _render_fix_inline(candidate: FixCandidate, console: Console) -> None:
    """Print a compact before→after block for one accepted fix."""
    is_tty = console.is_terminal
    label = f"{candidate.tool_name}:{candidate.dim} (+{candidate.delta:.1f})"

    if candidate.dim == "description_quality":
        old_text = candidate.old_description or "(none)"
        new_text = candidate.new_description or "(none)"
        if is_tty:
            console.print(f"  [bold]{label}[/bold]")
            console.print(f"  [red]- {old_text}[/red]")
            console.print(f"  [green]+ {new_text}[/green]")
        else:
            console.print(f"  {label}")
            console.print(f"  - {old_text}")
            console.print(f"  + {new_text}")
    elif candidate.dim == "schema_completeness" and candidate.new_schema_props:
        if is_tty:
            console.print(f"  [bold]{label}[/bold]")
            for param, meta in candidate.new_schema_props.items():
                old_meta = candidate.old_schema_props.get(param, {})
                old_str = str(old_meta) if old_meta else "(no metadata)"
                new_str = str(meta)
                console.print(f"  [dim]{param}:[/dim]")
                console.print(f"    [red]- {old_str}[/red]")
                console.print(f"    [green]+ {new_str}[/green]")
        else:
            console.print(f"  {label}")
            for param, meta in candidate.new_schema_props.items():
                old_meta = candidate.old_schema_props.get(param, {})
                old_str = str(old_meta) if old_meta else "(no metadata)"
                new_str = str(meta)
                console.print(f"  {param}:")
                console.print(f"    - {old_str}")
                console.print(f"    + {new_str}")


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
    _console: Console | None = None,
) -> None:
    """Async implementation of the fix subcommand."""
    console = _console or Console()

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

        # Print accepted fixes with inline before/after
        for c in report.accepted:
            console.print(
                f"[green]ACCEPTED[/green] {c.tool_name}:{c.dim} — "
                f"delta={c.delta:+.1f} (threshold={c.threshold:.1f})"
            )
            _render_fix_inline(c, console)

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
            bak = _bak_path(source_path)
            bak.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
            console.print(f"[dim]Backup written to {bak}[/dim]")
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


@app.command(name="try")
def try_cmd(
    target: Annotated[str, typer.Argument(help="Path to MCP server script, or HTTP/SSE URL")],
    model: Annotated[
        str,
        typer.Option(
            "--model",
            "-m",
            help=f"Ollama judge model (default: '{CALIBRATED_JUDGE_MODEL}')",
        ),
    ] = CALIBRATED_JUDGE_MODEL,
    generator_model: Annotated[
        str,
        typer.Option("--generator-model", help="Model for generating fix previews"),
    ] = "qwen3:8b",
    judge_model: Annotated[
        str,
        typer.Option("--judge-model", help="Pinned judge model for fix validation"),
    ] = JUDGE_MODEL_DEFAULT,
    trials: Annotated[int, typer.Option("--trials", "-t", help="LLM trials per dimension")] = 1,
    mock: Annotated[
        bool, typer.Option("--mock", help="Use mock LLM provider (no network needed)")
    ] = False,
) -> None:
    """Scan + preview fixes in one read-only command. Writes nothing."""
    asyncio.run(
        _try_async(
            target,
            model=model,
            generator_model=generator_model,
            judge_model=judge_model,
            trials=trials,
            mock=mock,
        )
    )


async def _try_async(
    target: str,
    *,
    model: str,
    generator_model: str,
    judge_model: str,
    trials: int,
    mock: bool,
) -> None:
    console = Console()

    # Step (a): scan
    await _scan_async(target, model=model, trials=trials, out=None, mock=mock)

    # Step (b): fix preview — read-only, no --apply
    await _fix_async(
        target,
        dims="description_quality,schema_completeness",
        generator_model=generator_model,
        judge_model=judge_model,
        trials=DEFAULT_TRIALS,
        min_delta=DEFAULT_MIN_DELTA,
        skip_above_band=DEFAULT_SKIP_ABOVE_BAND,
        out_diff=None,
        apply=False,
        mock=mock,
        _console=console,
    )

    # Step (c): apply hint
    console.print(f"\nRun `agentgauge fix {target} --apply` to apply these fixes.")


# ─────────────────────────────────────────────────────────────────────────────
# v2 commands: lint, eval, diff, init
#
# Per reports/v2_axis_triage.md, v2 retains no LLM-judged correlational scoring
# axis — `scan`/`fix`/`ci`/`try` above are v1 and unchanged; these four commands
# are the new product surface: a deterministic defect linter and a statistical
# regression harness, evaluated by precision/recall/false-alarm rate/MDE (see
# reports/v2_linter_evaluation.md, reports/v2_harness_evaluation.md), not
# correlation.
# ─────────────────────────────────────────────────────────────────────────────


async def _connect(target: str) -> tuple[Any, Any, str | None]:
    if target.startswith("http://") or target.startswith("https://"):
        client, ctx = await connect_http(target)
        return client, ctx, target
    client, ctx = await connect_stdio(sys.executable, [target])
    return client, ctx, None


def _print_lint_report(report: LintReport, console: Console, *, show_info: bool) -> None:
    if not report.blocking and not report.advisory and not (show_info and report.info):
        console.print("[green]No violations found.[/green]")
        return
    if report.blocking:
        console.print(
            f"[bold red]{len(report.blocking)} BLOCKING violation(s) (fails CI):[/bold red]"
        )
        for v in report.blocking:
            console.print(f"  [red]x[/red] [{v.check}] {v.tool_name}: {v.detail}")
    if report.advisory:
        console.print(
            f"[bold yellow]{len(report.advisory)} ADVISORY violation(s) (does not fail CI):[/bold yellow]"
        )
        for v in report.advisory:
            console.print(f"  [yellow]![/yellow] [{v.check}] {v.tool_name}: {v.detail}")
    if show_info and report.info:
        console.print(
            f"\n[bold yellow]{len(report.info)} INFO-severity hint(s) (off by default):[/bold yellow]"
        )
        for v in report.info:
            console.print(f"  [yellow]-[/yellow] [{v.check}] {v.tool_name}: {v.detail}")


@app.command()
def lint(
    target: Annotated[str, typer.Argument(help="Path to MCP server script, or HTTP/SSE URL")],
    show_info: Annotated[
        bool, typer.Option("--show-info", help="Also show INFO-severity hints (off by default)")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Machine-readable JSON output")
    ] = False,
) -> None:
    """Deterministic schema-consistency + name-collision linter. No LLM calls.

    Exits 1 if any BLOCKING violation is found (CI-friendly); ADVISORY
    violations are printed but do not fail the exit code (v2.1, Task 5 --
    a naive "any flag blocks" gate rejected 66.67% of clean tool sets). See
    reports/v2_1_severity_gate.md for measured precision/recall/false-alarm rate.
    """
    asyncio.run(_lint_async(target, show_info=show_info, json_output=json_output))


async def _lint_async(target: str, *, show_info: bool, json_output: bool) -> None:
    console = Console()
    client, ctx, _ = await _connect(target)
    try:
        info = await client.introspect()
        report = lint_tool_set(info.tools)
        if json_output:
            payload = {
                "blocking": [
                    {
                        "check": v.check,
                        "severity": v.severity.value,
                        "tool_name": v.tool_name,
                        "detail": v.detail,
                    }
                    for v in report.blocking
                ],
                "advisory": [
                    {
                        "check": v.check,
                        "severity": v.severity.value,
                        "tool_name": v.tool_name,
                        "detail": v.detail,
                    }
                    for v in report.advisory
                ],
                "info": [
                    {
                        "check": v.check,
                        "severity": v.severity.value,
                        "tool_name": v.tool_name,
                        "detail": v.detail,
                    }
                    for v in (report.info if show_info else [])
                ],
                "n_blocking": report.n_blocking,
                "n_advisory": report.n_advisory,
                "n_info": report.n_info,
                "flagged": report.flagged,
            }
            typer.echo(json.dumps(payload, indent=2))
        else:
            _print_lint_report(report, console, show_info=show_info)
    finally:
        await cleanup_connection(ctx)
    if report.flagged:
        raise typer.Exit(1)


def _load_tasks_file(path: Path) -> list[BlindTask]:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    return [BlindTask.from_dict(d) for d in raw]


async def _collect_trials(
    target: str, tasks: list[BlindTask], *, model: str, trials: int, mock: bool
) -> list[TrialOutcome]:
    """Live trial collection: connects, runs each task `trials` times, scores
    argument correctness against any user-supplied constraints (1.0 default for
    unconstrained tasks — see agentgauge.constraints' documented limitation)."""
    provider = MockProvider() if mock else OllamaProvider(model)
    client, ctx, _ = await _connect(target)
    try:
        task_objs = [Task(tool_name=t.tool_name, description=t.description) for t in tasks]
        run_results: list[RunResult] = await run_tasks(task_objs, client, provider, trials=trials)
        outcomes = []
        constraints_by_key = {(t.tool_name, t.description): t.constraints for t in tasks}
        for r in run_results:
            key = (r.task.tool_name, r.task.description)
            constraints = constraints_by_key.get(key)
            score = (
                constraint_satisfaction(r.constructed_args, constraints)
                if r.selected_tool == r.task.tool_name
                else 0.0
            )
            outcomes.append(
                TrialOutcome(
                    task_tool_name=r.task.tool_name,
                    selected_tool=r.selected_tool,
                    constraint_satisfaction=score,
                )
            )
        return outcomes
    finally:
        await cleanup_connection(ctx)


def _load_replay_trials(path: Path) -> list[TrialOutcome]:
    """Load pre-collected trial outcomes from a JSON file shaped like
    evals/fixtures/predictive_validity/results_raw.json's `run_results` field
    -- lets `diff`/`eval` be tested and used with zero live inference."""
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    return [TrialOutcome.from_dict(r) for r in raw]


def _print_decomposed(label: str, rate: DecomposedRate, console: Console) -> None:
    arg_str = (
        f"{rate.argument_accuracy_given_correct_selection:.3f}"
        if rate.argument_accuracy_given_correct_selection is not None
        else "n/a (0 correct-selection trials)"
    )
    console.print(f"[bold]{label}[/bold] (n={rate.n_trials} trials)")
    console.print(f"  selection accuracy:          {rate.selection_accuracy:.3f}")
    console.print(f"  argument accuracy | correct: {arg_str}")
    console.print(f"  joint success rate:          {rate.joint_success_rate:.3f}")


@app.command(name="eval")
def eval_cmd(
    target: Annotated[str, typer.Argument(help="Path to MCP server script, or HTTP/SSE URL")],
    tasks_file: Annotated[
        Path | None,
        typer.Option("--tasks", help="JSON file of anti-tautology tasks (see `agentgauge init`)"),
    ] = None,
    replay: Annotated[
        Path | None,
        typer.Option(
            "--replay", help="Replay pre-collected trial outcomes instead of running live"
        ),
    ] = None,
    model: Annotated[str, typer.Option("--model", "-m", help="Ollama agent model")] = "gemma2:9b",
    trials: Annotated[int, typer.Option("--trials", "-t", help="Trials per task")] = 5,
    mock: Annotated[bool, typer.Option("--mock", help="Use mock LLM provider")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lint + single-point task-success measurement (selection vs. argument
    accuracy reported separately — Task 4's decomposition). Not a regression
    diff; use `agentgauge diff` to compare two variants."""
    asyncio.run(
        _eval_async(
            target,
            tasks_file=tasks_file,
            replay=replay,
            model=model,
            trials=trials,
            mock=mock,
            json_output=json_output,
        )
    )


async def _eval_async(
    target: str,
    *,
    tasks_file: Path | None,
    replay: Path | None,
    model: str,
    trials: int,
    mock: bool,
    json_output: bool,
) -> None:
    console = Console()
    client, ctx, _ = await _connect(target)
    try:
        info = await client.introspect()
        lint_report = lint_tool_set(info.tools)
    finally:
        await cleanup_connection(ctx)

    if not json_output:
        _print_lint_report(lint_report, console, show_info=False)

    if replay is not None:
        outcomes = _load_replay_trials(replay)
    elif tasks_file is not None:
        tasks = _load_tasks_file(tasks_file)
        outcomes = await _collect_trials(target, tasks, model=model, trials=trials, mock=mock)
    else:
        console.print(
            "[yellow]No --tasks or --replay given -- skipping task-success measurement "
            "(lint-only). Run `agentgauge init` to scaffold a starter tasks file.[/yellow]"
        )
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "n_blocking": lint_report.n_blocking,
                        "n_advisory": lint_report.n_advisory,
                        "flagged": lint_report.flagged,
                    },
                    indent=2,
                )
            )
        if lint_report.flagged:
            raise typer.Exit(1)
        return

    rate = DecomposedRate.from_trials(outcomes)
    if json_output:
        payload = {
            "n_blocking": lint_report.n_blocking,
            "n_advisory": lint_report.n_advisory,
            "flagged": lint_report.flagged,
            "selection_accuracy": rate.selection_accuracy,
            "argument_accuracy_given_correct_selection": rate.argument_accuracy_given_correct_selection,
            "joint_success_rate": rate.joint_success_rate,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_decomposed(target, rate, console)
    if lint_report.flagged:
        raise typer.Exit(1)


@app.command()
def diff(
    before: Annotated[str, typer.Argument(help="Path to the 'before' MCP server script")],
    after: Annotated[str, typer.Argument(help="Path to the 'after' MCP server script")],
    tasks_file: Annotated[
        Path | None,
        typer.Option("--tasks", help="JSON file of anti-tautology tasks (see `agentgauge init`)"),
    ] = None,
    replay_before: Annotated[Path | None, typer.Option("--replay-before")] = None,
    replay_after: Annotated[Path | None, typer.Option("--replay-after")] = None,
    model: Annotated[str, typer.Option("--model", "-m", help="Ollama agent model")] = "gemma2:9b",
    trials: Annotated[int, typer.Option("--trials", "-t", help="Trials per task")] = 5,
    threshold: Annotated[
        float,
        typer.Option(
            "--threshold",
            help="Regression threshold on joint success rate (see reports/v2_harness_evaluation.md for the real MDE at your trial count)",
        ),
    ] = 0.05,
    mock: Annotated[bool, typer.Option("--mock", help="Use mock LLM provider")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Regression harness: bootstrap-CI comparison of task success between two
    tool-set variants, decomposed into selection vs. argument accuracy.

    Exits 1 on a REGRESSION verdict. See reports/v2_harness_evaluation.md for
    the measured minimum detectable effect at your --trials count before
    trusting a NO_CHANGE verdict as conclusive.
    """
    asyncio.run(
        _diff_async(
            before,
            after,
            tasks_file=tasks_file,
            replay_before=replay_before,
            replay_after=replay_after,
            model=model,
            trials=trials,
            threshold=threshold,
            mock=mock,
            json_output=json_output,
        )
    )


async def _diff_async(
    before: str,
    after: str,
    *,
    tasks_file: Path | None,
    replay_before: Path | None,
    replay_after: Path | None,
    model: str,
    trials: int,
    threshold: float,
    mock: bool,
    json_output: bool,
) -> None:
    console = Console()
    if replay_before is not None and replay_after is not None:
        before_trials = _load_replay_trials(replay_before)
        after_trials = _load_replay_trials(replay_after)
    elif tasks_file is not None:
        tasks = _load_tasks_file(tasks_file)
        before_trials = await _collect_trials(before, tasks, model=model, trials=trials, mock=mock)
        after_trials = await _collect_trials(after, tasks, model=model, trials=trials, mock=mock)
    else:
        console.print(
            "[red]Error: provide either --tasks, or both --replay-before and --replay-after.[/red]"
        )
        raise typer.Exit(2)

    result: DiffResult = diff_from_trials(before_trials, after_trials, threshold=threshold)

    if json_output:
        payload = {
            "verdict": result.verdict.value,
            "delta": result.delta,
            "ci_lo": result.ci_lo,
            "ci_hi": result.ci_hi,
            "threshold": result.threshold,
            "message": result.message,
            "before": {
                "selection_accuracy": result.before_decomposed.selection_accuracy,
                "argument_accuracy_given_correct_selection": result.before_decomposed.argument_accuracy_given_correct_selection,
                "joint_success_rate": result.before_decomposed.joint_success_rate,
            },
            "after": {
                "selection_accuracy": result.after_decomposed.selection_accuracy,
                "argument_accuracy_given_correct_selection": result.after_decomposed.argument_accuracy_given_correct_selection,
                "joint_success_rate": result.after_decomposed.joint_success_rate,
            },
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_decomposed("before", result.before_decomposed, console)
        console.print()
        _print_decomposed("after", result.after_decomposed, console)
        console.print()
        verdict_color = {
            Verdict.REGRESSION: "red",
            Verdict.IMPROVEMENT: "green",
            Verdict.NO_CHANGE: "cyan",
            Verdict.INSUFFICIENT_SENSITIVITY: "yellow",
        }[result.verdict]
        console.print(
            f"[bold {verdict_color}]{result.verdict.value.upper()}[/bold {verdict_color}]: {result.message}"
        )

    raise typer.Exit(result.exit_code)


_STARTER_TASKS_TEMPLATE = """[
  {
    "tool_name": "REPLACE_WITH_YOUR_TOOL_NAME",
    "description": "Describe the user's INTENT in plain language. Never quote the tool name or any required enum/literal value verbatim -- that makes selection trivial regardless of description quality. See reports/predictive_validity_study.md's blind_tasks.py convention for worked examples.",
    "constraints": [
      {"param": "some_param", "kind": "enum", "gold_value": "expected_value"}
    ]
  }
]
"""

_GITHUB_ACTION_TEMPLATE = """name: agentgauge
on:
  pull_request:
    paths:
      - "path/to/your_server.py"   # <-- edit to your actual MCP server path(s)
jobs:
  agentgauge:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write   # required to comment the results table on the PR
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # need the base-branch file too, for the diff step

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install agentgauge
        run: pip install agentgauge

      - name: Lint (deterministic, zero LLM cost)
        id: lint
        run: agentgauge lint ./path/to/your_server.py --json > lint.json || true

      - name: Diff against base branch (requires Ollama reachable from the runner)
        id: diff
        run: |
          git show origin/${{ github.base_ref }}:path/to/your_server.py > /tmp/before_server.py
          agentgauge diff /tmp/before_server.py ./path/to/your_server.py \\
            --tasks ./agentgauge_tasks.json --json > diff.json || true

      - name: Comment results on the PR
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const lint = JSON.parse(fs.readFileSync('lint.json', 'utf8'));
            const diff = JSON.parse(fs.readFileSync('diff.json', 'utf8'));
            const blockingLines = lint.blocking.map(v => `- **${v.check}** (${v.tool_name}): ${v.detail}`).join('\\n') || '_none_';
            const advisoryLines = lint.advisory.map(v => `- **${v.check}** (${v.tool_name}): ${v.detail}`).join('\\n') || '_none_';
            const body = [
              '### agentgauge results',
              '',
              `**Linter:** ${lint.n_blocking} BLOCKING finding(s) (fails CI), ${lint.n_advisory} ADVISORY finding(s) (does not fail CI)`,
              blockingLines,
              advisoryLines,
              '',
              `**Regression harness:** verdict = \\`${diff.verdict}\\``,
              `delta=${diff.delta.toFixed(3)}, 95% CI [${diff.ci_lo.toFixed(3)}, ${diff.ci_hi.toFixed(3)}]`,
              '',
              `| | selection accuracy | argument accuracy | joint success |`,
              `|---|---|---|---|`,
              `| before | ${diff.before.selection_accuracy.toFixed(3)} | ${diff.before.argument_accuracy_given_correct_selection ?? 'n/a'} | ${diff.before.joint_success_rate.toFixed(3)} |`,
              `| after  | ${diff.after.selection_accuracy.toFixed(3)} | ${diff.after.argument_accuracy_given_correct_selection ?? 'n/a'} | ${diff.after.joint_success_rate.toFixed(3)} |`,
              '',
              diff.message,
            ].join('\\n');
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body,
            });

      - name: Fail on regression or BLOCKING lint finding (ADVISORY does not fail CI)
        run: |
          agentgauge lint ./path/to/your_server.py
          agentgauge diff /tmp/before_server.py ./path/to/your_server.py --tasks ./agentgauge_tasks.json
"""


@app.command()
def init(
    out_dir: Annotated[Path, typer.Option("--out", help="Directory to scaffold into")] = Path("."),
) -> None:
    """Scaffold a starter anti-tautology tasks file and a GitHub Action template."""
    console = Console()
    tasks_path = out_dir / "agentgauge_tasks.json"
    workflow_dir = out_dir / ".github" / "workflows"
    workflow_path = workflow_dir / "agentgauge.yml"

    if tasks_path.exists():
        console.print(f"[yellow]{tasks_path} already exists -- not overwriting.[/yellow]")
    else:
        tasks_path.write_text(_STARTER_TASKS_TEMPLATE, encoding="utf-8")
        console.print(f"[green]Wrote {tasks_path}[/green]")

    workflow_dir.mkdir(parents=True, exist_ok=True)
    if workflow_path.exists():
        console.print(f"[yellow]{workflow_path} already exists -- not overwriting.[/yellow]")
    else:
        workflow_path.write_text(_GITHUB_ACTION_TEMPLATE, encoding="utf-8")
        console.print(f"[green]Wrote {workflow_path}[/green]")

    console.print(
        "\nNext steps:\n"
        "  1. Edit agentgauge_tasks.json with real anti-tautology tasks for your tools.\n"
        "  2. Run `agentgauge lint <your_server.py>` (zero LLM cost).\n"
        "  3. Run `agentgauge diff <before.py> <after.py> --tasks agentgauge_tasks.json` "
        "before merging a description/schema change.\n"
    )
