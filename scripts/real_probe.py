"""Real, live-LLM `ProbeFn` backend for `agentgauge.attribution` (v0.5 Wave 1, real-agent
validation pilot -- see `reports/v0_5_real_agent_validation.md`).

Every prior attribution report in this wave (`reports/v0_5_attribution_benchmark.md`,
`reports/v0_5_effect_size_sensitivity.md`, `reports/v0_5_scale_curve.md`) fed
`agentgauge.attribution`'s three localization strategies with
`agentgauge.attribution_benchmark.make_probe_fn`, a DECLARED, deterministic synthetic
ground-truth model -- zero live LLM calls anywhere. This module builds a REAL `ProbeFn`
(the identical interface `agentgauge.attribution`'s strategies already consume, per its
`ProbeFn = Callable[[frozenset[str]], ProbeResult]` type alias) that, given a subset of
changed tools to "revert" to their pre-defect description, actually:

1. Constructs a real in-memory MCP server variant (via `mcp.shared.memory
   .create_connected_server_and_client_session` -- an in-process client/server pair with no
   subprocess/stdio overhead, exactly the same protocol surface `agentgauge.client.MCPClient`
   talks to in production) with only the requested tools' descriptions reverted -- mixing
   before/after per-tool, not a monolithic before/after swap.
2. Runs real tasks against it via `agentgauge.runner.run_tasks`, using a real
   `agentgauge.providers.OllamaProvider` (`gemma2:9b` in this pilot) as the agent.
3. Scores real `agentgauge.harness.TrialOutcome`s: `selection_correct` is deterministic from
   which tool the agent actually called (`selected_tool == task_tool_name`) -- no LLM judge is
   used or needed for this metric. `constraint_satisfaction` is fixed at `1.0` whenever
   selection was correct (and therefore `0.0` when it was not, via
   `TrialOutcome.joint_success`), so the harness's `joint_success` metric collapses to exactly
   selection accuracy -- this ProbeFn measures selection-accuracy deltas only, not argument
   correctness (no judge model is wired up, per this task's explicit scope).
4. Feeds those real trial pairs through the SAME real `agentgauge.harness.diff_server_level`
   paired + CUPED + cluster-bootstrap estimator every synthetic probe in this wave already
   uses, returning a real `agentgauge.attribution.ProbeResult`.

Cost-of-inference design decision (stated explicitly, not left implicit): the "before" arm
(the current regressed state, i.e. reverting nothing) is measured ONCE per case, up front, and
cached for the lifetime of the returned `ProbeFn` -- it is genuinely constant across every
probe call (same server, same task set), so re-running it per call would waste real inference
budget for zero benefit. `agentgauge.attribution_benchmark.make_probe_fn`'s synthetic
counterpart re-draws its before-arm noise per call because synthetic draws are free; live LLM
calls are not. Each DISTINCT `reverted` subset's "after" arm is measured at most once per case
(cached across repeated calls with the identical subset -- e.g. across different strategies
probing the same revert), which is a legitimate real-cost optimization: `diff_server_level` is
re-run fresh against the cached trials on every call, so no strategy's measured delta/CI is
stale or reused incorrectly.

Per this repo's standing rule, the LLM is never called in this repo's `tests/` suite -- see
`tests/test_real_probe.py`, which exercises this exact module end-to-end with a deterministic
`agentgauge.providers.MockProvider` and a tiny synthetic in-memory catalog, no network, no
real inference. Only a manually-invoked script (`scripts/real_agent_validation.py`) calls this
module against a real Ollama endpoint.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.shared.memory import create_connected_server_and_client_session

from agentgauge.attribution import ProbeFn, ProbeResult
from agentgauge.attribution_benchmark import ToolLike
from agentgauge.client import MCPClient
from agentgauge.constraints import BlindTask
from agentgauge.harness import TrialOutcome, diff_server_level
from agentgauge.providers import Provider
from agentgauge.runner import run_tasks
from agentgauge.tasks import Task

# Sentinel used in place of the real gold tool name when the agent picked the wrong tool.
# `TrialOutcome.selection_correct` compares `selected_tool == task_tool_name`; since
# `task_tool_name` here is a globally-unique clustering key (see `_run_catalog_trials`), not the
# bare gold tool name, real correctness must be recorded explicitly via this sentinel rather than
# relying on `selected_tool` happening to equal the clustering key. Mirrors the same pattern
# `scripts/v2_5_argument_degradation_live.py` uses for the identical reason (disclosed there as a
# fix for a real bug in the shipped CLI's own bare-tool-name clustering key).
_WRONG_TOOL_SENTINEL = "__WRONG_TOOL__"


@dataclass
class RealAttributionCase:
    """One real, live-agent injected-culprit scenario -- the real-world analogue of
    `agentgauge.attribution_benchmark.BenchmarkCase`, with an identical public surface
    (`before_description`/`after_description`/`tools_before_like`/`tools_after_like`) so the
    existing zero-probe baselines (`agentgauge.attribution.baseline_largest_textual_diff`,
    `baseline_most_lint_violations`) work against it unmodified. Unlike `BenchmarkCase`, this is
    NOT randomly generated -- `scripts/real_case_construction.py` builds these deterministically
    from a real example MCP server file plus a real, hand-authored anti-tautology task fixture."""

    case_id: str
    server_name: str
    all_tools_before: list[dict[str, Any]]  # clean/original catalog (pre-defect-injection)
    all_tools_after: list[dict[str, Any]]  # regressed catalog (defect + decoys applied)
    changed_tools: list[str]
    true_culprit: str
    blind_tasks: list[BlindTask]
    diff_chars: dict[str, int] = field(default_factory=dict)

    def before_description(self, tool_name: str) -> str:
        return next(t["description"] or "" for t in self.all_tools_before if t["name"] == tool_name)

    def after_description(self, tool_name: str) -> str:
        return next(t["description"] or "" for t in self.all_tools_after if t["name"] == tool_name)

    def tools_before_like(self) -> list[ToolLike]:
        return [ToolLike(t) for t in self.all_tools_before]

    def tools_after_like(self) -> list[ToolLike]:
        return [ToolLike(t) for t in self.all_tools_after]


@dataclass
class RealProbeStats:
    """Wall-clock + call-count bookkeeping for one case's real (live-LLM) probe run -- the
    "cost" no synthetic benchmark in this wave could measure. `n_probe_calls` is the number of
    genuinely NEW (cache-miss) live probe invocations; `n_cache_hits` counts calls that reused an
    already-measured `reverted` subset's trials instead of re-running live inference."""

    n_probe_calls: int = 0
    n_cache_hits: int = 0
    before_arm_wallclock_s: float = 0.0
    before_arm_n_tasks: int = 0
    per_probe_wallclock_s: list[float] = field(default_factory=list)

    @property
    def total_after_arm_wallclock_s(self) -> float:
        return sum(self.per_probe_wallclock_s)

    @property
    def total_wallclock_s(self) -> float:
        return self.before_arm_wallclock_s + self.total_after_arm_wallclock_s


def _build_in_memory_server(name: str, tools: list[dict[str, Any]]) -> Server[Any]:
    """Build a real `mcp.server.Server` from a plain tool-catalog (dicts with
    name/description/inputSchema, matching `agentgauge.attribution_benchmark.BenchmarkCase`'s
    catalog convention) -- served entirely in-process via
    `mcp.shared.memory.create_connected_server_and_client_session`, no subprocess/stdio needed.
    `call_tool` always echoes success (matches `examples/github_issues_server_fixed.py` and
    every other real-domain example fixture's convention in this repo): this ProbeFn measures
    tool SELECTION accuracy only, so what the tool "does" when called is irrelevant."""
    server: Server[Any] = Server(name)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=t["name"],
                description=t.get("description") or "",
                inputSchema=t.get("inputSchema") or {"type": "object", "properties": {}},
            )
            for t in tools
        ]

    @server.call_tool()
    async def _call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        return [types.TextContent(type="text", text=json.dumps({"tool": name, "args": arguments}))]

    return server


async def _run_catalog_trials(
    catalog: list[dict[str, Any]],
    server_name: str,
    blind_tasks: list[BlindTask],
    provider: Provider,
    *,
    trials: int = 1,
) -> list[TrialOutcome]:
    """Run every `blind_tasks` entry once (or `trials` times) against an in-memory MCP server
    built from `catalog`, and score each trial's real `TrialOutcome` -- selection accuracy only
    (see module docstring point 3). `task_tool_name` is a globally-unique clustering key
    (`f"{tool_name}::{description}"`), not the bare tool name -- required so
    `agentgauge.harness.pair_tasks_common_random_numbers`/`aggregate_to_tasks` cluster by
    distinct TASK, not by tool (a real fixture has multiple tasks per tool; collapsing them
    would understate the true number of independent task clusters -- the exact bug
    `scripts/v2_5_argument_degradation_live.py` already found and worked around in this repo)."""
    server = _build_in_memory_server(server_name, catalog)
    task_objs = [Task(tool_name=t.tool_name, description=t.description) for t in blind_tasks]
    async with create_connected_server_and_client_session(server) as session:
        client = MCPClient(session)
        run_results = await run_tasks(task_objs, client, provider, trials=trials)

    outcomes: list[TrialOutcome] = []
    for r in run_results:
        unique_key = f"{r.task.tool_name}::{r.task.description}"
        really_correct = r.selected_tool == r.task.tool_name
        outcomes.append(
            TrialOutcome(
                task_tool_name=unique_key,
                selected_tool=unique_key if really_correct else _WRONG_TOOL_SENTINEL,
                constraint_satisfaction=1.0,
            )
        )
    return outcomes


def _apply_revert(case: RealAttributionCase, reverted: frozenset[str]) -> list[dict[str, Any]]:
    """Build the tool catalog for one probe call: tools named in `reverted` get their
    PRE-mutation (clean/original, `all_tools_before`) definition restored; every other tool
    keeps its current regressed (`all_tools_after`) definition. Tools outside
    `case.changed_tools` are identical in both catalogs already, so iterating
    `case.all_tools_after` unconditionally is safe."""
    before_by_name = {t["name"]: t for t in case.all_tools_before}
    catalog: list[dict[str, Any]] = []
    for t in case.all_tools_after:
        if t["name"] in reverted:
            catalog.append(json.loads(json.dumps(before_by_name[t["name"]])))
        else:
            catalog.append(json.loads(json.dumps(t)))
    return catalog


def make_real_probe_fn(
    case: RealAttributionCase,
    provider: Provider,
    *,
    trials: int = 1,
    n_resamples: int = 500,
    seed: int = 42,
) -> tuple[ProbeFn, RealProbeStats]:
    """Build a real, live-LLM `ProbeFn` for one `RealAttributionCase`, plus a `RealProbeStats`
    handle the caller can inspect after the strategies finish (probe/cache-hit counts, real
    wall-clock time) -- see module docstring for the before-arm caching and cross-call dedup
    design decisions. `n_resamples=500` matches
    `agentgauge.attribution_benchmark.make_probe_fn`'s own speed-reduction disclosure (vs.
    `diff_server_level`'s own 2000 default) -- purely a bootstrap-resample-count speed knob, not
    a change to the estimator itself.
    """
    stats = RealProbeStats()
    cache: dict[frozenset[str], list[TrialOutcome]] = {}

    t0 = time.perf_counter()
    before_trials = asyncio.run(
        _run_catalog_trials(
            case.all_tools_after, case.server_name, case.blind_tasks, provider, trials=trials
        )
    )
    stats.before_arm_wallclock_s = time.perf_counter() - t0
    stats.before_arm_n_tasks = len(case.blind_tasks)

    def probe(reverted: frozenset[str]) -> ProbeResult:
        if reverted in cache:
            stats.n_cache_hits += 1
            after_trials = cache[reverted]
        else:
            t_start = time.perf_counter()
            catalog = _apply_revert(case, reverted)
            after_trials = asyncio.run(
                _run_catalog_trials(
                    catalog, case.server_name, case.blind_tasks, provider, trials=trials
                )
            )
            stats.per_probe_wallclock_s.append(time.perf_counter() - t_start)
            stats.n_probe_calls += 1
            cache[reverted] = after_trials
        result = diff_server_level(before_trials, after_trials, n_resamples=n_resamples, seed=seed)
        return ProbeResult(result.delta, result.ci_lo, result.ci_hi)

    return probe, stats
