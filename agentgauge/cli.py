from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, TypeVar

import httpx
import typer
from rich.console import Console
from rich.markup import escape

from agentgauge import __version__
from agentgauge.audit import AuditReport, CoverageSummary, run_audit, summarize_constraint_coverage
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
from agentgauge.provider_config import create_provider, load_provider_config
from agentgauge.providers import MockProvider, OllamaProvider, Provider, ProviderUnreachableError
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


def _pin_utf8_pipes() -> None:
    """Write UTF-8 to redirected stdout/stderr whatever the host locale is.

    Why: Rich draws tables with box-drawing characters. A pipe otherwise inherits the process codec
    (cp1252 on Windows, or whatever PYTHONIOENCODING says), so a reader that decodes UTF-8 -- or a
    reader using a different codec than the child -- crashed or got mojibake. Interactive consoles
    are left alone: they render Unicode natively.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None and not stream.isatty():
            reconfigure(encoding="utf-8", errors="replace")


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    _pin_utf8_pipes()


# ─────────────────────────────────────────────────────────────────────────────
# Primary surface: diff, eval, lint, init.
#
# Per reports/v2_axis_triage.md, this repo retains no LLM-judged correlational
# scoring axis. `agentgauge diff` (the statistical regression harness) is the
# primary interface -- see reports/v2_2_optimal_allocation.md for its measured
# MDE and reports/v2_4_task1_blast_radius_audit.md for the causal-chain
# validation behind it. `agentgauge lint` (the deterministic defect linter) is
# a fast, zero-LLM-cost secondary utility: useful on its own, but it has at
# most one rule with a validated causal effect on task success (see the
# per-rule measured-effect table in README.md) -- the harness is what actually
# measures whether a change helped. `scan`/`fix`/`ci`/`try` below are v1,
# legacy, not the recommended surface (reports/predictive_validity_study.md
# found none of v1's 8 LLM-judged axes predict real task success).
# ─────────────────────────────────────────────────────────────────────────────


class CliError(Exception):
    """A user-facing failure: printed as one `Error: ...` line (plus optional hint), exit code 2."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


_T = TypeVar("_T")

# Shown whenever the live model backend is unavailable: each alternative needs no model at all.
_NO_MODEL_HINT = (
    "No model? Try `agentgauge demo` (bundled recorded run), `agentgauge diff --replay-before "
    "<before.json> --replay-after <after.json>`, or `agentgauge lint <server.py>` (no LLM). "
    "(`--mock` cannot produce a verdict.)"
)


def _fail(message: str, *, hint: str | None = None) -> typer.Exit:
    """Print `Error: <message>` (and an optional hint) to stderr and return Exit(2) to raise."""
    typer.echo(f"Error: {message}", err=True)
    if hint:
        typer.echo(hint, err=True)
    return typer.Exit(2)


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    """`asyncio.run` that turns expected user-facing failures into one-line errors (exit 2)
    instead of a traceback. Unexpected exceptions still propagate untouched."""
    try:
        return asyncio.run(coro)
    except CliError as exc:
        raise _fail(str(exc), hint=exc.hint) from None
    except ProviderUnreachableError as exc:
        raise _fail(str(exc), hint=_NO_MODEL_HINT) from None
    except httpx.ConnectError as exc:
        # Non-Ollama adapters (--provider-config) surface the raw transport error.
        raise _fail(f"Cannot reach the model endpoint: {exc}", hint=_NO_MODEL_HINT) from None


def _check_server_target(target: str) -> None:
    """Fail fast, before spawning a subprocess, if a file-path target cannot be a server script.

    Without this, a typo'd path spawns `python <path>`, which dies and surfaces as a ~100-line
    async traceback ending in `McpError: Connection closed`. HTTP/SSE URLs are not checked here.
    """
    path = Path(target)
    if not path.exists():
        raise CliError(f"server script not found: {target}")
    if not path.is_file():
        raise CliError(f"server path is not a file: {target}")
    if not os.access(path, os.R_OK):
        raise CliError(f"server script is not readable: {target}")


def _is_url(target: str) -> bool:
    return target.startswith(("http://", "https://"))


async def _connect(target: str) -> tuple[Any, Any, str | None]:
    if _is_url(target):
        client, ctx = await connect_http(target)
        return client, ctx, target
    _check_server_target(target)
    client, ctx = await connect_stdio(sys.executable, [target])
    return client, ctx, None


async def _preflight_provider(provider: Provider) -> None:
    """Cheap reachability probe before any trial, for providers that offer one (Ollama).

    A dead backend then fails in ~3 s with one line, not after ~25 s of connect timeouts.
    Providers without `ensure_reachable` (mock, hosted adapters) are skipped.
    """
    check = getattr(provider, "ensure_reachable", None)
    if check is not None:
        await check()


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
def diff(
    before: Annotated[
        str | None,
        typer.Argument(
            help="Path to the 'before' MCP server script (not needed with --replay-before/after)"
        ),
    ] = None,
    after: Annotated[
        str | None,
        typer.Argument(
            help="Path to the 'after' MCP server script (not needed with --replay-before/after)"
        ),
    ] = None,
    tasks_file: Annotated[
        Path | None,
        typer.Option("--tasks", help="JSON file of anti-tautology tasks (see `agentgauge init`)"),
    ] = None,
    replay_before: Annotated[Path | None, typer.Option("--replay-before")] = None,
    replay_after: Annotated[Path | None, typer.Option("--replay-after")] = None,
    model: Annotated[str, typer.Option("--model", "-m", help="Ollama agent model")] = "gemma2:9b",
    provider_config: Annotated[
        Path | None,
        typer.Option(
            "--provider-config",
            help=(
                "YAML provider config (see configs/provider.*.yaml) -- alternative to "
                "--model for non-Ollama adapters (Anthropic, OpenAI-compatible, Bedrock, "
                "Vertex, custom endpoint). Ignored when --mock is set; overrides --model "
                "otherwise. Existing --model/Ollama-default behavior is unchanged when "
                "this is not given."
            ),
        ),
    ] = None,
    trials: Annotated[
        int,
        typer.Option(
            "--trials",
            "-t",
            help=(
                "Trials per task. Default 1: measured ICC=0.793 means repeat trials on the "
                "SAME task carry almost no independent information -- more distinct TASKS is "
                "what buys detection power. At 100 tasks/arm x 1 trial, MDE=0.085 at 80% power "
                "(reports/v2_2_optimal_allocation.md) -- write ~100 tasks in your --tasks file "
                "for a reliable regression gate, not more trials per task."
            ),
        ),
    ] = 1,
    threshold: Annotated[
        float,
        typer.Option(
            "--threshold",
            help="Regression threshold on joint success rate (see reports/v2_2_optimal_allocation.md for the real MDE at your trial count)",
        ),
    ] = 0.05,
    seed: Annotated[
        int,
        typer.Option(
            "--seed",
            help=(
                "Base seed. Each (task, trial) gets its own seed derived from this, so repeat "
                "trials differ but a rerun with the same --seed is identical (Ollama only; "
                "hosted APIs ignore seeds)."
            ),
        ),
    ] = 42,
    mock: Annotated[bool, typer.Option("--mock", help="Use mock LLM provider")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """PRIMARY interface: statistical regression harness. Bootstrap-CI
    comparison of real task success between two tool-set variants, decomposed
    into selection vs. argument accuracy -- measures whether a change actually
    helped, which `agentgauge lint`'s static rules mostly do not validate on
    their own (see README.md's per-rule measured-effect table).

    Exit codes: 0 = IMPROVEMENT, NO_CHANGE, INSUFFICIENT_SENSITIVITY, or CEILING / FLOOR (every
    trial in both arms scored 1.0 / 0.0: no delta is reported, the task set has no headroom or no
    signal -- a valid finding, not a failure); 1 = REGRESSION; 2 = usage error, failed audit, or
    backend unreachable.

    See reports/v2_2_optimal_allocation.md for
    the measured minimum detectable effect at your --trials count before
    trusting a NO_CHANGE verdict as conclusive, and reports/
    v2_4_task1_blast_radius_audit.md for the causal-chain validation behind
    this harness's flagship claim.
    """
    _run(
        _diff_async(
            before,
            after,
            tasks_file=tasks_file,
            replay_before=replay_before,
            replay_after=replay_after,
            model=model,
            provider_config=provider_config,
            trials=trials,
            threshold=threshold,
            seed=seed,
            mock=mock,
            json_output=json_output,
        )
    )


async def _diff_async(
    before: str | None,
    after: str | None,
    *,
    tasks_file: Path | None,
    replay_before: Path | None,
    replay_after: Path | None,
    model: str,
    provider_config: Path | None = None,
    trials: int,
    threshold: float,
    seed: int = 42,
    mock: bool,
    json_output: bool,
) -> None:
    console = Console()
    before_tools: list[Any] | None = None
    after_tools: list[Any] | None = None
    before_stats: TrialCollectionStats | None = None
    after_stats: TrialCollectionStats | None = None
    coverage: CoverageSummary | None = None  # needs the tasks file, so live runs only
    if replay_before is not None and replay_after is not None:
        before_trials = _load_replay_trials(replay_before)
        after_trials = _load_replay_trials(replay_after)
        # Same trial-level audit as a live run (a replay file carries no tasks or schemas, so
        # only the checks that need trial outcomes apply).
        _trial_audit_or_exit(
            run_audit([], before_trials=before_trials, after_trials=after_trials),
            console=console,
            json_output=json_output,
        )
    elif tasks_file is not None:
        if before is None or after is None:
            raise CliError("a live diff needs both <before> and <after> server paths.")
        tasks = _load_tasks_file(tasks_file)
        # Cheapest checks first: local paths, then (live only) the model backend, all BEFORE
        # any server subprocess is spawned or any trial is attempted.
        for server_path in (before, after):
            if not _is_url(server_path):
                _check_server_target(server_path)
        provider, _label = _resolve_provider(
            model=model, mock=mock, provider_config=provider_config
        )
        await _preflight_provider(provider)
        before_tools = await _introspect_tools(before)
        after_tools = await _introspect_tools(after)
        # Schema-only pass FIRST -- catches a scoring-reference mismatch (a
        # task's constraint naming a parameter that isn't in the ACTUAL
        # schema this run just connected to, e.g. a renamed property) before
        # any live inference runs, not just before the result is reported.
        _schema_audit_or_exit(
            tasks,
            before_tools=before_tools,
            after_tools=after_tools,
            console=console,
            json_output=json_output,
            fail_message="Audit failed -- refusing to run live trials. Fix the flagged issue(s) and re-run.",
        )
        if mock:
            raise _refuse_mock(len(tasks), trials, console=console, json_output=json_output)
        coverage = summarize_constraint_coverage(tasks, before_tools)
        before_trials, before_stats = await _collect_trials(
            before,
            tasks,
            model=model,
            trials=trials,
            mock=mock,
            provider_config=provider_config,
            seed=seed,
        )
        after_trials, after_stats = await _collect_trials(
            after,
            tasks,
            model=model,
            trials=trials,
            mock=mock,
            provider_config=provider_config,
            seed=seed,
        )
        _trial_audit_or_exit(
            run_audit(
                tasks,
                before_tools=before_tools,
                after_tools=after_tools,
                before_trials=before_trials,
                after_trials=after_trials,
            ),
            console=console,
            json_output=json_output,
        )
    else:
        console.print(
            "[red]Error: provide either --tasks, or both --replay-before and --replay-after.[/red]"
        )
        raise typer.Exit(2)

    result: DiffResult = diff_from_trials(before_trials, after_trials, threshold=threshold)

    if json_output:
        no_delta = result.verdict in (Verdict.CEILING, Verdict.FLOOR)  # nothing to estimate
        payload = {
            "verdict": result.verdict.value,
            "delta": None if no_delta else result.delta,
            "ci_lo": None if no_delta else result.ci_lo,
            "ci_hi": None if no_delta else result.ci_hi,
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
            "before_cost": _cost_payload(before_stats),
            "after_cost": _cost_payload(after_stats),
            "constraint_coverage": coverage.as_dict() if coverage else None,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_diff_text(result, before_stats, after_stats, console, coverage=coverage)

    raise typer.Exit(result.exit_code)


def _print_diff_text(
    result: DiffResult,
    before_stats: TrialCollectionStats | None,
    after_stats: TrialCollectionStats | None,
    console: Console,
    *,
    coverage: CoverageSummary | None = None,
) -> None:
    """Human-readable diff report (shared by `diff` and `demo`)."""
    _print_decomposed("before", result.before_decomposed, console)
    console.print()
    _print_decomposed("after", result.after_decomposed, console)
    console.print()
    _print_cost_summary("before", before_stats, console)
    _print_cost_summary("after", after_stats, console)
    console.print()
    verdict_color = {
        Verdict.REGRESSION: "red",
        Verdict.IMPROVEMENT: "green",
        Verdict.NO_CHANGE: "cyan",
        Verdict.INSUFFICIENT_SENSITIVITY: "yellow",
        Verdict.CEILING: "yellow",
        Verdict.FLOOR: "yellow",
    }[result.verdict]
    label = ""
    if coverage is not None:
        console.print(escape(coverage.line()))
        if coverage.verdict_is_selection_only:
            label = " (selection-only)"
    console.print(
        f"[bold {verdict_color}]{result.verdict.value.upper()}{label}[/bold {verdict_color}]: "
        f"{result.message}"
    )
    if label:
        console.print(
            "[yellow]Selection-only: more than half the tasks register no argument constraint, "
            "so this verdict says nothing about whether the agent built correct arguments.[/yellow]"
        )


def _refuse_mock(n_tasks: int, trials: int, *, console: Console, json_output: bool) -> typer.Exit:
    """Refuse to report a verdict/measurement from `--mock`; return Exit(2) to raise.

    `MockProvider` answers every prompt with the same canned reply, so every trial scores
    identically. There is no n-task floor to quote: `audit.check_degenerate_metrics` blocks any
    run with >= 2 trials (zero variance), and a single trial has no variance to measure at all
    (`diff_from_trials` would print NO_CHANGE with a zero-width CI). So no mock run can ever
    yield a meaningful verdict, at any task count. Before this refusal, a 1-task placeholder
    scaffold + `--mock` printed a confident-looking NO_CHANGE.
    """
    message = (
        f"--mock cannot produce a verdict: MockProvider gives the same canned reply to every "
        f"prompt, so all {n_tasks * trials} trial(s) ({n_tasks} task(s) x {trials} trial(s)) "
        "score identically -- no task count changes that (a run of >= 2 trials is blocked by the audit's "
        "degenerate_metrics gate, and a single trial has no variance). Use a real model, "
        "`agentgauge demo`, or --replay-before/--replay-after."
    )
    if json_output:
        typer.echo(json.dumps({"mock_refused": True, "message": message}, indent=2))
    else:
        console.print(f"[bold red]Error:[/bold red] {message}")
    return typer.Exit(2)


def _load_tasks_file(path: Path) -> list[BlindTask]:
    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise CliError(f"tasks file not found: {path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"cannot read tasks file {path}: {exc}") from None
    return [BlindTask.from_dict(d) for d in raw]


async def _introspect_tools(target: str) -> list[Any]:
    """Connect, introspect, disconnect -- no live trials. Used to run the
    schema-only `agentgauge.audit` checks (task leakage, scoring-reference
    consistency) BEFORE spending any inference budget, not just before
    reporting a result (v2.5, Task 1: the v2.4 audit gate correctly blocked a
    bad measurement from being REPORTED, but `_collect_trials` still ran a
    full, wasted set of live trials first every time -- fixing the artifact
    #7 class in shipped code means failing fast and cheap on a schema
    mismatch, not just failing safe after paying for it)."""
    client, ctx, _ = await _connect(target)
    try:
        info = await client.introspect()
        return list(info.tools)
    finally:
        await cleanup_connection(ctx)


@dataclass
class TrialCollectionStats:
    """Cost/timing metadata for one live `_collect_trials` call (spec-agentgauge-
    v0.5.md S4.1: "cost accounting per run ... surfaced in the diff output").
    `tokens_in`/`tokens_out`/`cost_usd` are `None` when the wrapped provider does not
    expose them (e.g. `OllamaProvider` has no cost tracking today -- matches
    `cassette.CassetteEntry`'s existing `tokens_in`/`tokens_out` optionality)."""

    provider_label: str
    duration_s: float
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None


def _resolve_provider(
    *, model: str, mock: bool, provider_config: Path | None
) -> tuple[Provider, str]:
    """Pick the live-run provider + a human-readable label for it. Precedence:
    `--mock` > `--provider-config` > `--model`/Ollama-default -- this is additive to
    the pre-existing `--model` contract, never a breaking change to it."""
    if mock:
        return MockProvider(), "mock"
    if provider_config is not None:
        config = load_provider_config(provider_config)
        return create_provider(config), f"{config.provider}:{config.model}"
    return OllamaProvider(model), f"ollama:{model}"


async def _collect_trials(
    target: str,
    tasks: list[BlindTask],
    *,
    model: str,
    trials: int,
    mock: bool,
    provider_config: Path | None = None,
    seed: int = 42,
) -> tuple[list[TrialOutcome], TrialCollectionStats]:
    """Live trial collection: connects, runs each task `trials` times, scores
    argument correctness against any user-supplied constraints (1.0 default for
    unconstrained tasks — see agentgauge.constraints' documented limitation).
    Callers must run `_introspect_tools` + a schema-only `agentgauge.audit.run_audit`
    pass BEFORE calling this (see `_diff_async`/`_eval_async`) so a
    scoring-reference mismatch (the artifact #7 class -- a task's constraints
    authored against a different schema than the one connected here) is
    caught before live inference runs, not just before its result is
    reported.

    Returns `(outcomes, stats)` -- `stats` carries wall-clock duration + token/cost
    accounting for the run, surfaced by `_diff_async`/`_eval_async` in the CLI output.
    """
    provider, provider_label = _resolve_provider(
        model=model, mock=mock, provider_config=provider_config
    )
    start = time.perf_counter()
    client, ctx, _ = await _connect(target)
    try:
        task_objs = [Task(tool_name=t.tool_name, description=t.description) for t in tasks]
        run_results: list[RunResult] = await run_tasks(
            task_objs, client, provider, trials=trials, base_seed=seed
        )
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
    finally:
        await cleanup_connection(ctx)

    stats = TrialCollectionStats(
        provider_label=provider_label,
        duration_s=time.perf_counter() - start,
        tokens_in=getattr(provider, "tokens_in", None),
        tokens_out=getattr(provider, "tokens_out", None),
        cost_usd=getattr(provider, "total_cost_usd", None),
    )
    return outcomes, stats


def _cost_payload(stats: TrialCollectionStats | None) -> dict[str, Any]:
    """JSON-mode cost/timing block. `stats is None` means replay mode was used --
    explicit `"live": false` + a note, never zeros that would look like a real
    zero-cost run (spec-agentgauge-v0.5.md S4.1)."""
    if stats is None:
        return {"live": False, "note": "replay mode -- no live cost to report"}
    return {
        "live": True,
        "provider": stats.provider_label,
        "duration_s": round(stats.duration_s, 3),
        "tokens_in": stats.tokens_in,
        "tokens_out": stats.tokens_out,
        "cost_usd": stats.cost_usd,
    }


def _print_cost_summary(label: str, stats: TrialCollectionStats | None, console: Console) -> None:
    """Text-mode cost/timing line. Replay mode says so explicitly rather than
    printing a real-looking zero (spec-agentgauge-v0.5.md S4.1)."""
    if stats is None:
        console.print(f"[dim]{label} cost: replay mode -- no live cost to report.[/dim]")
        return
    if stats.tokens_in is not None and stats.tokens_out is not None:
        tokens_str = f"{stats.tokens_in} in / {stats.tokens_out} out"
    else:
        tokens_str = "n/a (provider has no token accounting)"
    cost_str = f"${stats.cost_usd:.6f}" if stats.cost_usd is not None else "n/a"
    console.print(
        f"[dim]{label} cost: provider={stats.provider_label} "
        f"duration={stats.duration_s:.2f}s tokens={tokens_str} est_spend={cost_str}[/dim]"
    )


def _schema_audit_or_exit(
    tasks: list[BlindTask],
    *,
    before_tools: list[Any] | None = None,
    after_tools: list[Any] | None = None,
    console: Console,
    json_output: bool,
    fail_message: str,
) -> None:
    """Schema-only audit pass (no trial data yet) -- run before any live
    inference. Raises typer.Exit(2) on a BLOCKING finding so a scoring-
    reference mismatch or task-leakage defect is caught for free, before
    paying for a single LLM call."""
    report = run_audit(tasks, before_tools=before_tools, after_tools=after_tools)
    if report.blocking:
        if not json_output:
            _print_audit_report(report, console)
            console.print(f"[bold red]{fail_message}[/bold red]")
        else:
            typer.echo(
                json.dumps(
                    {"audit_failed": True, "blocking": [f.detail for f in report.blocking]},
                    indent=2,
                )
            )
        raise typer.Exit(2)


def _trial_audit_or_exit(report: AuditReport, *, console: Console, json_output: bool) -> None:
    """Print the audit findings and raise Exit(2) on a BLOCKING one (live and replay paths)."""
    if not json_output:
        _print_audit_report(report, console)
        if report.findings:
            console.print()
    if report.passed:
        return
    if json_output:
        typer.echo(
            json.dumps(
                {"audit_failed": True, "blocking": [f.detail for f in report.blocking]}, indent=2
            )
        )
    else:
        console.print(
            "[bold red]Audit failed -- refusing to report a diff. "
            "Fix the flagged issue(s) and re-run.[/bold red]"
        )
    raise typer.Exit(2)


def _print_audit_report(report: AuditReport, console: Console) -> None:
    for f in report.blocking:
        # escape(): details carry labels like "[after]" that Rich would otherwise swallow as markup
        console.print(f"[bold red]AUDIT BLOCK[/bold red] ({f.check}): {escape(f.detail)}")
    for f in report.warnings:
        console.print(f"[yellow]AUDIT WARN[/yellow] ({f.check}): {escape(f.detail)}")


def _load_replay_trials(path: Path) -> list[TrialOutcome]:
    """Load pre-collected trial outcomes from a JSON file shaped like
    evals/fixtures/predictive_validity/results_raw.json's `run_results` field
    -- lets `diff`/`eval` be tested and used with zero live inference."""
    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise CliError(f"replay file not found: {path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"cannot read replay file {path}: {exc}") from None
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
    provider_config: Annotated[
        Path | None,
        typer.Option(
            "--provider-config",
            help=(
                "YAML provider config (see configs/provider.*.yaml) -- alternative to "
                "--model for non-Ollama adapters. Ignored when --mock is set; overrides "
                "--model otherwise. Existing --model/Ollama-default behavior is unchanged "
                "when this is not given."
            ),
        ),
    ] = None,
    trials: Annotated[
        int,
        typer.Option(
            "--trials",
            "-t",
            help=(
                "Trials per task. Default 1: measured ICC=0.793 means repeat trials on the "
                "SAME task carry almost no independent information (reports/"
                "v2_variance_structure.md) -- more distinct TASKS, not more trials per task, "
                "is what buys detection power (reports/v2_2_optimal_allocation.md)."
            ),
        ),
    ] = 1,
    seed: Annotated[
        int,
        typer.Option(
            "--seed",
            help=(
                "Base seed. Each (task, trial) gets its own seed derived from this, so repeat "
                "trials differ but a rerun with the same --seed is identical (Ollama only; "
                "hosted APIs ignore seeds)."
            ),
        ),
    ] = 42,
    mock: Annotated[bool, typer.Option("--mock", help="Use mock LLM provider")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lint + single-point task-success measurement (selection vs. argument
    accuracy reported separately — Task 4's decomposition). Not a regression
    diff; use `agentgauge diff` to compare two variants."""
    _run(
        _eval_async(
            target,
            tasks_file=tasks_file,
            replay=replay,
            model=model,
            provider_config=provider_config,
            trials=trials,
            seed=seed,
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
    provider_config: Path | None = None,
    trials: int,
    seed: int = 42,
    mock: bool,
    json_output: bool,
) -> None:
    console = Console()
    if not _is_url(target):
        _check_server_target(target)
    if tasks_file is not None and replay is None:
        # Live path: confirm the model backend is up before any work (mock/hosted: no-op).
        provider, _label = _resolve_provider(
            model=model, mock=mock, provider_config=provider_config
        )
        await _preflight_provider(provider)
    client, ctx, _ = await _connect(target)
    try:
        info = await client.introspect()
        lint_report = lint_tool_set(info.tools)
    finally:
        await cleanup_connection(ctx)

    if not json_output:
        _print_lint_report(lint_report, console, show_info=False)

    tools: list[Any] | None = None
    stats: TrialCollectionStats | None = None
    coverage: CoverageSummary | None = None  # needs the tasks file, so live runs only
    if replay is not None:
        outcomes = _load_replay_trials(replay)
    elif tasks_file is not None:
        tasks = _load_tasks_file(tasks_file)
        tools = list(info.tools)
        coverage = summarize_constraint_coverage(tasks, tools)
        # Schema-only pass FIRST (reusing the introspection already done for
        # linting above) -- catches a scoring-reference mismatch before any
        # live inference runs, not just before the result is reported.
        _schema_audit_or_exit(
            tasks,
            before_tools=tools,
            console=console,
            json_output=json_output,
            fail_message="Audit failed -- refusing to run live trials. Fix the flagged issue(s) and re-run.",
        )
        if mock:
            raise _refuse_mock(len(tasks), trials, console=console, json_output=json_output)
        outcomes, stats = await _collect_trials(
            target,
            tasks,
            model=model,
            trials=trials,
            mock=mock,
            provider_config=provider_config,
            seed=seed,
        )
        audit_report = run_audit(tasks, before_tools=tools, before_trials=outcomes)
        if not json_output:
            _print_audit_report(audit_report, console)
        if not audit_report.passed:
            if json_output:
                typer.echo(
                    json.dumps(
                        {
                            "audit_failed": True,
                            "blocking": [f.detail for f in audit_report.blocking],
                        },
                        indent=2,
                    )
                )
            else:
                console.print(
                    "[bold red]Audit failed -- refusing to report a task-success measurement. "
                    "Fix the flagged issue(s) and re-run.[/bold red]"
                )
            raise typer.Exit(2)
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
            "cost": _cost_payload(stats),
            "constraint_coverage": coverage.as_dict() if coverage else None,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_decomposed(target, rate, console)
        _print_cost_summary(target, stats, console)
        if coverage is not None:
            console.print(escape(coverage.line()))
            if coverage.verdict_is_selection_only:
                console.print(
                    "[yellow]Selection-only: more than half the tasks register no argument "
                    "constraint, so these rates say nothing about argument correctness.[/yellow]"
                )
    if lint_report.flagged:
        raise typer.Exit(1)


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

    A fast, zero-cost SECONDARY utility -- `agentgauge diff` is the primary
    interface (see README.md). At most one lint rule (`type_enum_contradiction`)
    has a validated causal effect on real task success; the rest are either
    unvalidated or measured to have zero effect (README.md's per-rule table).
    Exits 1 if any BLOCKING violation is found (CI-friendly); ADVISORY
    violations are printed but do not fail the exit code (v2.1, Task 5 --
    a naive "any flag blocks" gate rejected 66.67% of clean tool sets). See
    reports/v2_1_severity_gate.md for measured precision/recall/false-alarm rate
    and reports/v2_3_task2_retiering.md for the causal-impact-based re-tiering.
    """
    _run(_lint_async(target, show_info=show_info, json_output=json_output))


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


_STARTER_TASKS_TEMPLATE = """[
  {
    "tool_name": "REPLACE_WITH_YOUR_TOOL_NAME",
    "description": "Open a high-priority ticket in the billing project titled 'Refund not received for order 4417'.",
    "note": "WORKED EXAMPLE of FULL argument coverage -- replace it. Describe the user's INTENT; never quote the tool name. Give every required parameter of the tool a constraint, and constrain every value the task text states (here: the project, the title, the order number and the priority are all checked). A task with no constraints only checks that the right tool was picked (`agentgauge diff` reports it as selection-only). Kinds: enum, contains, format, range, numeric_equals.",
    "constraints": [
      {"param": "project", "kind": "enum", "gold_value": "billing"},
      {"param": "title", "kind": "contains", "gold_value": "4417"},
      {"param": "priority", "kind": "enum", "gold_value": "high"}
    ]
  }
]
"""

_GITHUB_ACTION_TEMPLATE = """\
# agentgauge -- GitHub Actions workflow scaffolded by `agentgauge init`.
#
# MODE: LINT-ONLY BY DEFAULT. Out of the box this runs the `lint` job only: a deterministic,
# zero-LLM check (no Ollama, no model download, no API keys, no cost) that fails the PR on a
# BLOCKING finding. The `live-diff` job below is OFF until you opt in.
#
# TO SWITCH ON THE LIVE before/after DIFF (statistical task-success regression gate):
#   1. Repo Settings > Secrets and variables > Actions > Variables > New repository variable:
#      AGENTGAUGE_LIVE_DIFF = true
#   2. Write real tasks in agentgauge_tasks.json (see `agentgauge init` output).
#   Cost/time: the job installs Ollama on the runner and pulls gemma2:9b (~5.4 GB). GitHub-hosted
#   runners have no GPU, so every model call runs on CPU -- expect it to be slow for ~100
#   tasks (the job is capped at 90 minutes). To skip a runner-hosted model entirely,
#   run `agentgauge diff` locally or on your own GPU runner and commit the recorded trials, then
#   call `agentgauge diff --replay-before before.json --replay-after after.json` in CI.
#
# Edit the two `path/to/your_server.py` placeholders below to your real MCP server path.
name: agentgauge
on:
  pull_request:
    paths:
      - "path/to/your_server.py"   # <-- edit to your actual MCP server path(s)
permissions:
  contents: read
jobs:
  lint:
    # ACTIVE by default. No model needed.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install agentgauge
        run: pip install agentgauge-harness
      - name: Lint (deterministic, zero LLM cost; fails on BLOCKING findings only)
        shell: bash   # bash with pipefail, so the lint exit code survives the tee below
        run: agentgauge lint ./path/to/your_server.py | tee -a "$GITHUB_STEP_SUMMARY"

  live-diff:
    # OPT-IN. Skipped unless the repository variable AGENTGAUGE_LIVE_DIFF is 'true'.
    if: ${{ vars.AGENTGAUGE_LIVE_DIFF == 'true' }}
    runs-on: ubuntu-latest
    timeout-minutes: 90
    env:
      AGENTGAUGE_MODEL: gemma2:9b
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # need the base-branch file too, for the diff step
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install agentgauge
        run: pip install agentgauge-harness
      - name: Install Ollama and pull the model
        shell: bash
        run: |
          curl -fsSL https://ollama.com/install.sh | sh
          (ollama serve > ollama.log 2>&1 &)
          for _ in $(seq 1 30); do
            curl -fsS http://localhost:11434/api/version && break
            sleep 2
          done
          ollama pull "$AGENTGAUGE_MODEL"
      - name: Diff against base branch (fails on REGRESSION or a failed audit)
        shell: bash
        run: |
          git show "origin/${{ github.base_ref }}:path/to/your_server.py" > /tmp/before_server.py
          agentgauge diff /tmp/before_server.py ./path/to/your_server.py \\
            --tasks ./agentgauge_tasks.json --model "$AGENTGAUGE_MODEL" \\
            | tee -a "$GITHUB_STEP_SUMMARY"
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

    try:
        workflow_dir.mkdir(parents=True, exist_ok=True)  # also creates out_dir (and parents)
    except OSError as exc:
        raise _fail(f"cannot create output directory {out_dir}: {exc.strerror or exc}") from None

    try:
        if tasks_path.exists():
            console.print(f"[yellow]{tasks_path} already exists -- not overwriting.[/yellow]")
        else:
            tasks_path.write_text(_STARTER_TASKS_TEMPLATE, encoding="utf-8")
            console.print(f"[green]Wrote {tasks_path}[/green]")

        if workflow_path.exists():
            console.print(f"[yellow]{workflow_path} already exists -- not overwriting.[/yellow]")
        else:
            workflow_path.write_text(_GITHUB_ACTION_TEMPLATE, encoding="utf-8")
            console.print(f"[green]Wrote {workflow_path}[/green]")
    except OSError as exc:
        raise _fail(f"cannot write scaffold files under {out_dir}: {exc.strerror or exc}") from None

    console.print(
        "\nNext steps:\n"
        "  1. Edit agentgauge_tasks.json with real anti-tautology tasks for your tools.\n"
        "  2. Run `agentgauge lint <your_server.py>` (zero LLM cost).\n"
        "  3. Run `agentgauge diff <before.py> <after.py> --tasks agentgauge_tasks.json` "
        "before merging a description/schema change.\n"
        "  New here? `agentgauge demo` replays a bundled before/after run -- no model needed.\n"
    )


_DEMO_FILES = (
    "before_server.py",
    "after_server.py",
    "tasks.json",
    "replay_before.json",
    "replay_after.json",
    "PROVENANCE.md",
)


@app.command()
def demo(
    extract: Annotated[
        Path | None,
        typer.Option(
            "--extract",
            help=(
                "Copy the bundled demo servers, tasks file and recorded replays into this "
                "directory (created if missing) so you can run a live `agentgauge diff` on them."
            ),
        ),
    ] = None,
) -> None:
    """Replay a bundled, pre-recorded before/after diff -- no GPU, keys or network needed.

    The recording is a real gemma2:9b run over a tiny illustrative server pair (see
    agentgauge/demo/PROVENANCE.md). With --extract DIR, copy the pair out instead of replaying.
    """
    console = Console()
    assets = resources.files("agentgauge.demo")

    if extract is not None:
        _extract_demo(assets, extract, console)
        return

    with (
        resources.as_file(assets / "replay_before.json") as before_path,
        resources.as_file(assets / "replay_after.json") as after_path,
    ):
        before_trials = _load_demo_replay(before_path)
        after_trials = _load_demo_replay(after_path)
    with resources.as_file(assets / "tasks.json") as tasks_path:
        demo_tasks = _load_tasks_file(tasks_path)
    from agentgauge.demo import before_server  # tool schemas, so required params are known

    demo_tools = [
        SimpleNamespace(name=t["name"], inputSchema=t["inputSchema"]) for t in before_server.TOOLS
    ]
    coverage = summarize_constraint_coverage(demo_tasks, demo_tools)
    result = diff_from_trials(before_trials, after_trials)
    n = len(before_trials)
    console.print(
        f"[bold]agentgauge demo[/bold]: replaying {n} recorded gemma2:9b trials per arm "
        "(no model, GPU, keys or network used)\n"
    )
    _trial_audit_or_exit(
        run_audit([], before_trials=before_trials, after_trials=after_trials),
        console=console,
        json_output=False,
    )
    _print_diff_text(result, None, None, console, coverage=coverage)
    console.print()
    for line in _demo_explanation(result, n):
        console.print(line)
    console.print(
        "\nRun it live on the same pair: `agentgauge demo --extract demo_files`, then "
        "`agentgauge diff demo_files/before_server.py demo_files/after_server.py "
        "--tasks demo_files/tasks.json` (needs Ollama + gemma2:9b). A live run is a "
        "fresh sample and may differ from this recording."
    )


def _load_demo_replay(path: Path) -> list[TrialOutcome]:
    try:
        return _load_replay_trials(path)
    except CliError as exc:
        raise _fail(str(exc)) from None


def _demo_explanation(result: DiffResult, n_tasks: int) -> list[str]:
    """Two plain-language lines explaining a demo verdict (derived from the actual result)."""
    b, a = result.before_decomposed, result.after_decomposed
    line1 = (
        f"What happened: with identical tool names, only the descriptions changed -- joint success "
        f"went {b.joint_success_rate:.2f} -> {a.joint_success_rate:.2f} "
        f"(delta {result.delta:+.2f}, 95% CI [{result.ci_lo:+.2f}, {result.ci_hi:+.2f}], "
        f"{n_tasks} tasks)."
    )
    why = {
        Verdict.INSUFFICIENT_SENSITIVITY: (
            f"Why this verdict: {n_tasks} tasks is too few for the CI to be narrower than 2x the "
            f"{result.threshold:.2f} threshold, so the harness declines to call it either way; "
            "a real gate needs ~100 tasks per arm."
        ),
        Verdict.IMPROVEMENT: (
            "Why this verdict: the whole 95% CI sits above the regression threshold, so the "
            "description rewrite is a measured improvement, not noise."
        ),
        Verdict.NO_CHANGE: (
            "Why this verdict: the 95% CI does not clear the threshold in either direction at "
            "this task count."
        ),
        Verdict.REGRESSION: (
            "Why this verdict: the whole 95% CI sits below minus the threshold, so the change "
            "made the agent worse."
        ),
        Verdict.CEILING: "Why this verdict: every trial in both arms succeeded; no headroom.",
        Verdict.FLOOR: "Why this verdict: every trial in both arms failed; no signal.",
    }[result.verdict]
    return [line1, why]


def _extract_demo(assets: Any, dest: Path, console: Console) -> None:
    """Copy the bundled demo files into `dest`; never overwrite anything already there."""
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _fail(f"cannot create directory {dest}: {exc.strerror or exc}") from None
    clashes = [name for name in _DEMO_FILES if (dest / name).exists()]
    if clashes:
        raise _fail(f"refusing to overwrite existing file(s) in {dest}: {', '.join(clashes)}")
    try:
        for name in _DEMO_FILES:
            with resources.as_file(assets / name) as src:
                shutil.copyfile(src, dest / name)
    except OSError as exc:
        raise _fail(f"cannot write demo files to {dest}: {exc.strerror or exc}") from None
    console.print(f"[green]Extracted {len(_DEMO_FILES)} demo files to {dest}[/green]")
    console.print(
        "\nTry it:\n"
        f"  agentgauge lint {dest / 'before_server.py'}\n"
        f"  agentgauge diff --replay-before {dest / 'replay_before.json'} "
        f"--replay-after {dest / 'replay_after.json'}\n"
        f"  agentgauge diff {dest / 'before_server.py'} {dest / 'after_server.py'} "
        f"--tasks {dest / 'tasks.json'}   # live: needs Ollama + gemma2:9b\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Legacy v1 surface: scan, fix, ci, try.
#
# An 8-axis LLM-judged correlational score. reports/predictive_validity_study.md
# found none of the 8 axes predict real task success by a margin surviving
# both multiple-comparison correction and length-control. Kept for users who
# already depend on these commands -- not the recommended product surface.
# Use `agentgauge diff`/`eval`/`lint`/`init` instead (see above).
# ─────────────────────────────────────────────────────────────────────────────


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
    """(legacy) Scan an MCP server and print an agent-readiness score."""
    _run(_scan_async(target, model=model, trials=trials, out=out, mock=mock))


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
    if not _is_url(target):
        _check_server_target(target)
    await _preflight_provider(provider)

    console.print(f"[dim]Connecting to [bold]{target}[/bold]...[/dim]")

    if _is_url(target):
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
    """(legacy) Auto-generate improved descriptions and schema metadata for low-scoring tools."""
    _run(
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
    await _preflight_provider(generator)

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
    """(legacy) Scan an MCP server and exit 1 if the overall score is below --min-score."""
    overall = _run(_scan_async(target, model=model, trials=trials, out=None, mock=mock))
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
    """(legacy) Scan + preview fixes in one read-only command. Writes nothing."""
    _run(
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


# Measured cost finding, v0.5.0 (reports/v0_5_probe_power_fix.md section 5): at the n_tasks
# probe-power fix requires (128, to clear an 8pp per-probe MDE target -- reports/
# v0_5_probe_power_fix.md section 3), every tested attribution configuration costs MORE than a
# full 253-task re-evaluation of the whole server: 1.01x at the cheapest measured case (sampled
# Shapley, 4 changed tools) up to 20.24x at the most expensive (exhaustive ablation, 40 changed
# tools). The crossover to "cheaper than re-measuring everything" sits at ~2-4 changed tools --
# below the scale at which localization has any practical purpose (spec-agentgauge-v0.5.md
# section 2: the target buyer's own scenario is "a 40-tool server with a 12-file PR"). Numbers
# only, no adjectives, per this repo's standing convention.
_ATTRIBUTION_COST_FINDING = (
    "agentgauge attribute is EXPERIMENTAL and requires --experimental.\n\n"
    "Measured cost (reports/v0_5_probe_power_fix.md, n_tasks=128, the value required to reach an "
    "8pp per-probe minimum detectable effect):\n"
    "  - 1.01x-20.24x the cost of a full 253-task server re-evaluation, depending on "
    "candidate-set size.\n"
    "  - Crossover to cheaper-than-re-evaluating-everything: ~2-4 changed tools.\n"
    "  - Multi-culprit (2-3 simultaneous regressions) does not clear the accuracy ship bar at "
    "any tested configuration.\n\n"
    "This is not shipped for production use. Full findings: reports/v0_5_probe_power_fix.md, "
    "reports/v0_5_mde_discrepancy.md, reports/v0_5_shapley_scaling_audit.md."
)


@app.command(hidden=True)
def attribute(
    experimental: Annotated[
        bool,
        typer.Option(
            "--experimental",
            help="Required opt-in. Attribution is measured uneconomical -- see the cost finding "
            "printed without this flag.",
        ),
    ] = False,
) -> None:
    """Failure attribution / regression localization (Component 1.2) -- EXPERIMENTAL, NOT
    RECOMMENDED FOR PRODUCTION. Off by default; requires --experimental. See
    reports/v0_5_probe_power_fix.md for the measured cost finding this gate enforces."""
    if not experimental:
        typer.echo(_ATTRIBUTION_COST_FINDING, err=True)
        raise typer.Exit(1)
    typer.echo(
        "Experimental mode acknowledged. There is no production attribution runner in this "
        "CLI -- the feature exists as library code (agentgauge.attribution, "
        "agentgauge.attribution_benchmark) and research scripts (scripts/attribution_*.py, "
        "scripts/probe_mde_ablation.py, scripts/scale_curve_report.py) for research use only. "
        "Import those modules directly; see reports/v0_5_probe_power_fix.md for what is and "
        "is not measured before relying on any number."
    )
