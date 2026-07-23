#!/usr/bin/env python3
"""Predictive-validity study: does AgentGauge's 8-axis score predict real task success?

For each tool-set fixture in ``evals.fixtures.predictive_validity.manifest.MANIFEST``,
collects in one run:
  1. Ground truth: agent (gemma2:9b) task-success rate over hand-vetted, anti-tautology
     tasks (``evals/fixtures/predictive_validity/blind_tasks.py``) -- NOT
     ``generate_tasks``, which quotes the gold tool name verbatim in the task text and
     makes selection trivial regardless of description quality.
  2. AgentGauge score: all 8 axis scores + overall, via ``scorer.score_all`` judged by
     llama3.1:8b (the pinned judge model, see agentgauge/CLAUDE.md).
  3. Baseline 1 (description length): mean description char length, zero LLM calls.
  4. Baseline 2 (single-prompt judge): one holistic 0-100 rating from the judge model
     on the full tool listing.

DO NOT RUN THIS SCRIPT as part of routine CI or test verification -- it makes many
real Ollama calls against two local models and is expected to take on the order of
2-3.5 hours for the full 18-entry manifest at trials=3. It is a deliberately separate,
gated, human-run data-collection step. See scripts/predictive_validity_analysis.py for
the (test-covered, network-free) analysis of its output.

Usage:
    python scripts/predictive_validity_study.py

Crash safety: this is a long unattended run. Each completed tool-set's record is
appended immediately to evals/fixtures/predictive_validity/results_raw.ndjson (one
JSON object per line, flush-on-write), and results_raw.json (the full list consumed by
the analysis script) is re-synced from the ndjson log after every tool-set. A crash
after N tool-sets complete loses at most the in-flight (N+1)th record -- never
previously-completed ones.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.types import Tool

from agentgauge.client import (
    MCPClient,
    ServerInfo,
    ToolCallResult,
    cleanup_connection,
    connect_stdio,
)
from agentgauge.providers import Message, OllamaProvider, Provider
from agentgauge.runner import RunResult, _build_tool_listing, run_tasks
from agentgauge.scorer import score_all
from evals.fixtures.predictive_validity.blind_tasks import BLIND_TASKS
from evals.fixtures.predictive_validity.constraints import TASK_CONSTRAINTS, constraint_satisfaction
from evals.fixtures.predictive_validity.manifest import (
    AGENT_MODEL,
    JUDGE_MODEL,
    MANIFEST,
    ToolSetEntry,
    resolve_server_path,
)

# Pre-registered trial count for AgentGauge's own scoring (score_all's internal
# generate_tasks-driven run, plus its judge-only dimensions).
TRIALS = 3

# Ground-truth trials use BLIND_TASKS (2+ hand-vetted, anti-tautology tasks per tool --
# see blind_tasks.py) instead of generate_tasks' 1-task-per-tool default, so even a
# single trial already samples multiple tasks per tool. GROUND_TRUTH_TRIALS was
# originally pinned at 1 on that basis. It no longer is: Phase 2 replaced the binary
# `success AND selected_tool == tool_name` ground truth with a continuous
# constraint-satisfaction fraction (see TASK_CONSTRAINTS / constraint_satisfaction
# below), and that continuous metric needs repeated trials per task for statistical
# averaging and per-trial variance (confidence intervals) -- a role BLIND_TASKS' task
# diversity does not substitute for, since it's the SAME task's repeated sampling
# variance under stochastic agent decoding that trials measure, not task diversity.
# Raised to 5 per the explicit Phase 2 requirement ("re-run ground truth with >=5
# trials per tool set").
GROUND_TRUTH_TRIALS = 5

# Local Ollama can intermittently contend with other GPU workloads on this machine
# (observed: an unrelated process repeatedly loading a third model forced partial CPU
# fallback and starved requests past the 180s default). 300s gives real-but-slow calls
# room to complete instead of hard-failing the whole tool-set on transient contention.
PROVIDER_TIMEOUT = 300.0

RESULTS_DIR = Path(__file__).parent.parent / "evals" / "fixtures" / "predictive_validity"
NDJSON_PATH = RESULTS_DIR / "results_raw.ndjson"
JSON_PATH = RESULTS_DIR / "results_raw.json"

_NUMBER_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")


class _FilteredClient:
    """Wraps an ``MCPClient`` so ``introspect()`` only returns the filtered tool subset.

    ``run_tasks`` and several of ``scorer.score_all``'s client-based dimensions call
    ``client.introspect()`` internally to (re)build the full tool listing shown to the
    agent. For a manifest entry with a ``tool_name_filter`` (the 4 t18-family entries,
    sliced from a 60-tool server down to a 12-tool subset), passing the raw client
    through unfiltered would silently show the agent the server's FULL 60-tool catalog
    during task selection while every other AgentGauge dimension (schema_completeness,
    description_quality, discoverability, error_legibility, robustness) was scored
    against only the 12-tool subset. That mismatch would mean the ground-truth
    task_success_rate and the AgentGauge score are not measuring the same tool set --
    a construct-validity break for a predictive-validity study. This wrapper keeps
    every downstream consumer (ground truth + all 8 axes) looking at the identical
    filtered tool set. ``call_tool``/``call_tool_with_bad_input`` delegate unchanged --
    filtering only affects what tools are considered "available", not tool execution.
    """

    def __init__(self, client: MCPClient, tool_name_filter: list[str]) -> None:
        self._client = client
        self._filter = set(tool_name_filter)

    async def introspect(self) -> ServerInfo:
        info = await self._client.introspect()
        return ServerInfo(
            tools=[t for t in info.tools if t.name in self._filter],
            resources=info.resources,
            prompts=info.prompts,
        )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        return await self._client.call_tool(name, arguments)

    async def call_tool_with_bad_input(self, name: str, bad_args: dict[str, Any]) -> ToolCallResult:
        return await self._client.call_tool_with_bad_input(name, bad_args)


def _extract_score(resp: str, *, max_score: float = 100.0) -> float | None:
    """Pull the first bare number out of a judge response, capped at ``max_score``.

    Mirrors the number-extraction regex used throughout agentgauge/scorer.py (e.g.
    ``score_description_quality``, ``score_docs_manifest``) -- there is no shared
    exported helper for this in the codebase, so this duplicates the same pattern
    rather than introducing a new one.
    """
    m = _NUMBER_RE.search(resp)
    if not m:
        return None
    return min(float(m.group(1)), max_score)


def _description_length_baseline(tools: list[Tool]) -> float:
    """Baseline 1: mean description character length across tools. Zero LLM calls."""
    if not tools:
        return 0.0
    return sum(len(t.description or "") for t in tools) / len(tools)


async def _single_prompt_baseline(tools: list[Tool], provider: Provider) -> float | None:
    """Baseline 2: one holistic LLM-judge call over the full tool listing, 0-100."""
    listing = _build_tool_listing(tools)
    prompt = (
        "Below is the full tool catalog of an MCP server, with each tool's name, "
        "description, and parameters.\n\n"
        f"{listing}\n\n"
        "Rate this tool documentation 0-100 for how well an AI agent could use it "
        "to correctly select and call the right tool to complete tasks. "
        "Reply with ONLY the number."
    )
    resp = await provider.chat([Message(role="user", content=prompt)], seed=42)
    return _extract_score(resp, max_score=100.0)


def _run_result_to_dict(result: RunResult, constraint_score: float) -> dict[str, Any]:
    """Serialize the fields of a RunResult needed for provenance.

    ``constraint_score`` is the per-trial continuous ground-truth value (0.0 for a
    wrong tool selection, else the fraction of registered argument-correctness
    constraints satisfied) -- stored alongside the existing binary-metric fields so
    the raw NDJSON/JSON output supports re-deriving ``task_success_rate`` (and its
    variance, for confidence intervals) independently of the aggregated mean computed
    in ``_run_one``.
    """
    return {
        "task_tool_name": result.task.tool_name,
        "selected_tool": result.selected_tool,
        "success": result.success,
        "error": result.error,
        "parse_failed": result.parse_failed,
        "constraint_satisfaction": constraint_score,
    }


async def _run_one(entry: ToolSetEntry) -> dict[str, Any]:
    """Collect ground truth, AgentGauge score, and both baselines for one tool set."""
    server_path = resolve_server_path(entry)
    python = sys.executable
    client, ctx = await connect_stdio(python, [str(server_path)])
    try:
        info = await client.introspect()
        if entry.tool_name_filter is not None:
            keep = set(entry.tool_name_filter)
            tools = [t for t in info.tools if t.name in keep]
            effective_client: MCPClient | _FilteredClient = _FilteredClient(
                client, entry.tool_name_filter
            )
        else:
            tools = info.tools
            effective_client = client

        # Ground truth: agent task-success rate, using hand-vetted anti-tautology
        # tasks (BLIND_TASKS) rather than generate_tasks -- generate_tasks builds each
        # task as f"Call '{tool.name}': {tool.description}", which quotes the gold tool
        # name verbatim in the text shown to the agent, making selection trivial
        # regardless of description quality (see blind_tasks.py module docstring for
        # the full incident writeup). Every manifest entry must have a BLIND_TASKS
        # entry -- a missing one is a hard error, not a silent fallback to the leaking
        # generator.
        tasks = BLIND_TASKS[entry.name]
        available_names = {t.name for t in tools}
        stray = [t.tool_name for t in tasks if t.tool_name not in available_names]
        if stray:
            raise ValueError(
                f"BLIND_TASKS['{entry.name}'] references tool(s) not in the "
                f"(possibly filtered) tool list: {stray}"
            )
        agent_provider = OllamaProvider(AGENT_MODEL, timeout=PROVIDER_TIMEOUT)
        run_results = await run_tasks(
            tasks,
            effective_client,  # type: ignore[arg-type]  # duck-typed wrapper, see _FilteredClient
            agent_provider,
            trials=GROUND_TRUTH_TRIALS,
        )
        # Ground truth is now a CONTINUOUS metric, not a binary AND. The prior binary
        # metric (`r.success and r.selected_tool == r.task.tool_name`) is degenerate --
        # this repo's example MCP servers never raise from `call_tool`, so `success` is
        # always True regardless of whether the constructed arguments were actually
        # correct, and the metric collapsed to pure tool-name matching (44% of tool
        # sets tied at exact 1.0). The fix: score = (correct tool selected) x (fraction
        # of that task's registered argument constraints satisfied), a value in [0, 1].
        # A task with no registered constraint defaults to 1.0 via
        # `constraint_satisfaction`'s own empty/None handling (correct tool, no
        # argument-correctness signal to check -- not penalized).
        per_trial_scores: list[float] = []
        for r in run_results:
            if r.selected_tool != r.task.tool_name:
                per_trial_scores.append(0.0)  # wrong tool entirely -- constraints on args are moot
            else:
                constraints = TASK_CONSTRAINTS.get(entry.name, {}).get(
                    (r.task.tool_name, r.task.description)
                )
                per_trial_scores.append(constraint_satisfaction(r.constructed_args, constraints))
        task_success_rate = (
            sum(per_trial_scores) / len(per_trial_scores) if per_trial_scores else 0.0
        )

        # Old binary metric retained (not discarded) so a later analysis can directly
        # compare old-vs-new on the same collected data.
        n_success_binary = sum(
            1 for r in run_results if r.success and r.selected_tool == r.task.tool_name
        )
        task_success_rate_binary = n_success_binary / len(run_results) if run_results else 0.0

        # AgentGauge score (all 8 axes + overall). base_url=None -> stdio, docs_manifest
        # floors at 20.0 for every entry here (see CLAUDE.md docs_manifest notes) --
        # expected and handled downstream by excluding it from correlation analysis.
        judge_provider = OllamaProvider(JUDGE_MODEL, timeout=PROVIDER_TIMEOUT)
        report = await score_all(
            tools,
            judge_provider,
            client=effective_client,  # type: ignore[arg-type]
            trials=TRIALS,
            base_url=None,
        )
        dimension_scores = {d.name: d.score for d in report.dimensions}

        # Baselines.
        baseline_desc_length = _description_length_baseline(tools)
        baseline_single_prompt = await _single_prompt_baseline(tools, judge_provider)

        return {
            "name": entry.name,
            "tier": entry.tier,
            "server_path": entry.server_path,
            "tool_name_filter": entry.tool_name_filter,
            "tool_count": len(tools),
            "agent_model": AGENT_MODEL,
            "judge_model": JUDGE_MODEL,
            "trials": TRIALS,
            "ground_truth_trials": GROUND_TRUTH_TRIALS,
            "task_success_rate": round(task_success_rate, 4),
            "task_success_rate_binary": round(task_success_rate_binary, 4),
            "dimension_scores": dimension_scores,
            "overall_score": report.overall,
            "baseline_desc_length": round(baseline_desc_length, 2),
            "baseline_single_prompt": baseline_single_prompt,
            "run_results": [
                _run_result_to_dict(r, s)
                for r, s in zip(run_results, per_trial_scores, strict=True)
            ],
            "timestamp": datetime.now(UTC).isoformat(),
            "error": None,
        }
    finally:
        await cleanup_connection(ctx)


def _load_completed_names() -> set[str]:
    """Names of tool sets that already have a *successful* record in the NDJSON log.

    Only successes are skipped on resume -- a previously FAILED entry (e.g. from a
    transient GPU-contention timeout) is retried, since its record has no usable data.
    Reading the log directly (not results_raw.json) means resume is correct even if a
    prior run was killed mid-sync.
    """
    if not NDJSON_PATH.exists():
        return set()
    completed: set[str] = set()
    with NDJSON_PATH.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if record.get("error") is None:
                completed.add(record["name"])
    return completed


def _sync_json_from_ndjson() -> None:
    """Rebuild results_raw.json (the full list) from the append-only NDJSON log.

    Called after every tool-set completes so a crash mid-run never loses more than the
    single in-flight record -- results_raw.json always reflects the last successful
    tool-set that finished. Deduplicated by name, keeping the LAST record per name --
    a resumed run that retries a previously-failed entry appends a second line for the
    same name, and the retry's outcome (success or repeat failure) must supersede the
    original failure rather than appearing twice in the analysis input.
    """
    if not NDJSON_PATH.exists():
        return
    by_name: dict[str, dict[str, Any]] = {}
    with NDJSON_PATH.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                record = json.loads(stripped)
                by_name[record["name"]] = record
    JSON_PATH.write_text(json.dumps(list(by_name.values()), indent=2), encoding="utf-8")


# Approximate tool count per manifest entry, used ONLY to order execution (cheapest
# first) so that on an environment prone to killing long-running background processes
# mid-flight (observed on this machine -- see run log), the run banks as many entries
# as possible before hitting the most expensive ones. Not used for scoring -- every
# entry's actual tool list still comes from live introspection in `_run_one`. Counts
# match the tool_name_filter length (T18 entries) or the documented count in
# manifest.py's module docstring (everything else).
_APPROX_TOOL_COUNT: dict[str, int] = {
    "echo_server": 4,
    "grounded_server": 5,
    "grounded_server_oracle": 5,
    "mediocre_server": 5,
    "call_constraints_v2_server": 6,
    "call_constraints_v2_server_oracle": 6,
    "call_constraints_server": 8,
    "call_constraints_server_oracle": 8,
    "exp1_blazickjp_arxiv_mcp_server_mirror": 8,
    "t18_vague_server": 12,
    "t18_fixer_server": 12,
    "t18_q2b_server": 12,
    "t18_oracle_server": 12,
    "confusable_server": 16,
    "confusable_server_oracle": 16,
    "exp1_datalayer_jupyter_mcp_server_mirror": 17,
    "exp1_datalayer_jupyter_mcp_server_mirror_oracle": 17,
    "exp1_stickerdaniel_linkedin_mcp_server_mirror": 17,
}


async def main() -> None:
    """Run the full manifest, cheapest-first, logging progress and syncing output.

    Resumable: entries with an already-successful record in the NDJSON log are skipped,
    so a killed/crashed run can be relaunched with the same command and picks up where
    it left off rather than re-paying inference for tool sets already banked. Processed
    in ascending approximate tool count (see ``_APPROX_TOOL_COUNT``) rather than
    manifest-declaration order, so an interrupted run has already banked the cheap
    entries before reaching the few expensive ones most likely to still be mid-flight
    when interrupted. This does not change what gets measured -- only the order.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    completed = _load_completed_names()
    ordered = sorted(MANIFEST, key=lambda e: _APPROX_TOOL_COUNT.get(e.name, 999))
    print(f"Predictive-validity study: {len(ordered)} tool sets, trials={TRIALS}")
    print(f"Agent model: {AGENT_MODEL}  |  Judge model: {JUDGE_MODEL}")
    print(f"Crash-safe log:   {NDJSON_PATH}")
    print(f"Analysis input:   {JSON_PATH}")
    print(f"Execution order (cheapest first): {[e.name for e in ordered]}")
    if completed:
        print(
            f"Resuming: {len(completed)} tool set(s) already completed, skipping: {sorted(completed)}"
        )

    start = time.monotonic()
    for i, entry in enumerate(ordered, start=1):
        if entry.name in completed:
            print(f"\n[{i}/{len(ordered)}] Skipping '{entry.name}' (already completed).")
            continue
        entry_start = time.monotonic()
        print(f"\n[{i}/{len(ordered)}] Running '{entry.name}' (tier={entry.tier})...")
        try:
            record = await _run_one(entry)
        except Exception as exc:  # noqa: BLE001 -- one bad fixture must not kill the whole run
            elapsed = time.monotonic() - entry_start
            print(f"  FAILED after {elapsed:.1f}s: {exc!r}")
            record = {
                "name": entry.name,
                "tier": entry.tier,
                "server_path": entry.server_path,
                "tool_name_filter": entry.tool_name_filter,
                "error": repr(exc),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        else:
            elapsed = time.monotonic() - entry_start
            print(
                f"  done in {elapsed:.1f}s -- "
                f"task_success_rate={record['task_success_rate']:.2f}  "
                f"overall={record['overall_score']:.1f}"
            )
        with NDJSON_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        _sync_json_from_ndjson()

    total_elapsed = time.monotonic() - start
    print(f"\nDone. {len(ordered)} tool sets in {total_elapsed / 60:.1f} min.")
    print(f"Results: {JSON_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
