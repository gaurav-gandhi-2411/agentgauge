#!/usr/bin/env python3
"""Real, live-LLM attribution validation pilot (v0.5 Wave 1, Component 1.2 -- see
`reports/v0_5_real_agent_validation.md`).

Every other attribution report in this wave (`reports/v0_5_attribution_benchmark.md`,
`reports/v0_5_effect_size_sensitivity.md`, `reports/v0_5_scale_curve.md`) measured against a
DECLARED, deterministic synthetic ground-truth model -- zero live LLM calls. This script runs
the SAME real strategy implementations (`agentgauge.attribution.attribute_exhaustive`
/`attribute_sampled_shapley`/`attribute_greedy_bisection`, unmodified, plus the three zero-probe
baselines) against a REAL `scripts.real_probe.ProbeFn` backed by a real local Ollama model
(`gemma2:9b`, localhost-only, no cloud/paid fallback under any circumstance per this task's hard
constraint) and real, hand-authored anti-tautology tasks from `evals/fixtures/v2_4_corpus/`.

**Pilot-first, budget-bounded design** (per this task's explicit instruction: never scale up a
live-LLM run before measuring its actual pace). A single pilot probe was measured BEFORE this
script's scope was fixed: one full probe cycle (before-arm once, 4 tasks + one after-arm revert,
4 tasks) against the `real_github_issues` case took 58.48s wall-clock (36.81s before-arm +
21.68s one after-arm probe), i.e. roughly 5.4-9.2s per task-run (each task-run = 2 LLM calls:
tool selection + argument construction -- argument construction is called by
`agentgauge.runner.run_tasks` unconditionally even though this pilot does not score it, since
this script reuses the real, unmodified `run_tasks` function rather than special-casing it).
Extrapolating that pace across all three probe-based strategies at n_changed=3-4 (up to ~12
probes per case, per `reports/v0_5_scale_curve.md`'s own measured single_n4 mean-probe figures)
originally suggested roughly 5 minutes/case for the 4-tool cases -- a 3-case run
(github_issues/jira_issues/stripe_payments) was attempted first (see below) and reduced to 1.

**Two stall incidents, and why this script's shipped scope is smaller than originally planned**
(disclosed here, not hidden -- see `reports/v0_5_real_agent_validation.md` for the full evidence
trail): the first live-run attempt used `run_in_background` (a backgrounded, non-blocking shell
invocation) across all 3 cases x 3 strategies. It completed the pilot's before-arm run
successfully, then produced zero further output for 15 minutes; the model unloaded from VRAM
(`ollama ps` went empty) and the process itself was confirmed gone from the process list, with no
traceback ever written. Root cause was not conclusively isolated, but the leading hypothesis is
that a long-running FOREGROUND monitoring command (a 10-minute poll loop checking the background
job's output) and the BACKGROUNDED live script shared/recycled shell state, killing the
background process. The second attempt (this shipped configuration) removes both suspect
mechanisms at once: **no `run_in_background`, no separate polling loop** -- this script is run as
a single, direct, blocking shell call the caller waits on directly, reading real output only after
it returns. Scope was cut to fit comfortably inside that one blocking call's time budget:
**1 case only** (`real_github_issues`, chosen because its before-arm was already proven to work),
**2 of 3 strategies** (`exhaustive_ablation` + `greedy_bisection`; `sampled_shapley` skipped this
run -- an explicit, disclosed budget cut, not a silently-dropped corner). Estimated cost at this
scope, from the pilot's own measured pace (36.81s before-arm + up to ~10 probes x ~21.68s each):
roughly 4-5 minutes, comfortably inside the tool's single-call ceiling even with the pilot's
already-observed ~1.7x per-call latency variance.

**Cost design**: both strategies for the one case share a SINGLE `ProbeFn` instance (and its
cache) -- run in the fixed order exhaustive -> greedy_bisection, so a `reverted` subset the first
strategy already probed live is never re-probed live for the second. This is disclosed explicitly
because it means each strategy's reported wall-clock/probe-call figures below are
MARGINAL/incremental costs given this run order, not standalone per-strategy costs measured in
isolation -- a real production deployment running only one strategy at a time would pay each
strategy's full (non-shared) cost. Each strategy's own `probes_consumed` (a LOGICAL count the
strategy itself reports, independent of caching) is also recorded, matching every other report in
this wave.

Usage (run as a single direct blocking call -- do NOT background this script and do NOT run a
separate polling loop against it; see the stall-incident disclosure above for why):
    uv run python scripts/real_agent_validation.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.attribution import (  # noqa: E402
    AttributionResult,
    attribute_exhaustive,
    attribute_greedy_bisection,
    attribute_sampled_shapley,
    baseline_largest_textual_diff,
    baseline_most_lint_violations,
    baseline_uniform_random,
    expected_topk_accuracy,
    top_k_hit,
)
from agentgauge.providers import OllamaProvider  # noqa: E402
from scripts.real_case_construction import REAL_CASE_SPECS, build_case_from_spec  # noqa: E402
from scripts.real_probe import RealAttributionCase, RealProbeStats, make_real_probe_fn  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
CHECKPOINT_PATH = REPO_ROOT / "evals" / "fixtures" / "v0_5_real_agent_validation.jsonl"
SUMMARY_PATH = REPO_ROOT / "evals" / "fixtures" / "v0_5_real_agent_validation_summary.json"

MODEL = "gemma2:9b"
SEED = 42

# Disclosed scope decision -- see module docstring's "Pilot-first" section for the pilot
# measurement that drove this, and the "Two stall incidents" section for why this was reduced
# from the originally-planned 3-case run to a single case. Order matters only for readability;
# each case is independent.
SELECTED_CASE_IDS: list[str] = ["real_github_issues"]

# Disclosed scope cut (second attempt, orchestrator-directed): sampled_shapley is skipped this
# run -- two strategies (exhaustive_ablation, greedy_bisection) is enough for a genuine single
# real data point within the remaining live-inference budget after two stalled attempts. Not a
# silently-cut corner: recorded here and in the report as an explicit, disclosed reduction.
STRATEGIES_TO_RUN: list[str] = ["exhaustive_ablation", "greedy_bisection"]


def _print_environment_check() -> None:
    """Re-confirm GPU/Ollama state immediately before the live phase, per this task's explicit
    instruction not to trust a stale summary. Prints raw command output; does not parse or gate
    on it (a human/agent reviewing this script's output is the actual gate, per the task's "if
    GPU contention appears, stop and report" instruction -- this script does not auto-abort)."""
    print("=== Environment check (immediately before live phase) ===", flush=True)
    try:
        nvidia = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        print("nvidia-smi:", nvidia.stdout.strip() or nvidia.stderr.strip(), flush=True)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"nvidia-smi check failed: {exc}", flush=True)
    try:
        ollama = subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=15, check=False
        )
        print("ollama ps:", ollama.stdout.strip() or "(no resident models)", flush=True)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"ollama ps check failed: {exc}", flush=True)
    print("=" * 60, flush=True)


def _run_baselines(case: RealAttributionCase) -> dict[str, AttributionResult]:
    before_desc = {t: case.before_description(t) for t in case.changed_tools}
    after_desc = {t: case.after_description(t) for t in case.changed_tools}
    return {
        "largest_textual_diff": baseline_largest_textual_diff(
            case.changed_tools, before_desc, after_desc
        ),
        "most_lint_violations": baseline_most_lint_violations(
            case.changed_tools, case.tools_before_like(), case.tools_after_like()
        ),
        "uniform_random": baseline_uniform_random(case.changed_tools, seed=SEED),
    }


def _stats_snapshot(stats: RealProbeStats) -> tuple[int, float]:
    return stats.n_probe_calls, stats.total_wallclock_s


def _append_checkpoint(record: dict[str, Any]) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CHECKPOINT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()


def _run_one_case(case_id: str) -> dict[str, Any]:
    """Synchronous by design: `scripts.real_probe.make_real_probe_fn`'s returned `ProbeFn`
    internally drives its own live inference via a fresh `asyncio.run()` call per probe (the
    `ProbeFn` interface `agentgauge.attribution`'s strategies consume is synchronous). Calling
    `asyncio.run()` from within an already-running event loop raises `RuntimeError` -- so this
    function, and `main()` below, are deliberately plain `def`, not `async def`; the one
    genuinely async step (`build_case_from_spec`) gets its own dedicated, immediately-completed
    `asyncio.run()` call instead of being awaited inside a larger event loop."""
    spec = next(s for s in REAL_CASE_SPECS if s.case_id == case_id)
    print(f"\n--- Case: {case_id} (server={spec.server_name}, culprit={spec.culprit}) ---", flush=True)

    case = asyncio.run(build_case_from_spec(spec))
    print(
        f"changed_tools={case.changed_tools} n_tasks={len(case.blind_tasks)} "
        f"diff_chars={case.diff_chars}",
        flush=True,
    )

    provider = OllamaProvider(MODEL)
    probe, stats = make_real_probe_fn(case, provider, trials=1, n_resamples=500, seed=SEED)
    print(
        f"before-arm: {stats.before_arm_wallclock_s:.2f}s "
        f"for {stats.before_arm_n_tasks} tasks",
        flush=True,
    )

    all_strategies: dict[str, Any] = {
        "exhaustive_ablation": lambda: attribute_exhaustive(case.changed_tools, probe),
        "sampled_shapley": lambda: attribute_sampled_shapley(case.changed_tools, probe, seed=SEED),
        "greedy_bisection": lambda: attribute_greedy_bisection(case.changed_tools, probe),
    }
    strategy_records: dict[str, dict[str, Any]] = {}
    for name in STRATEGIES_TO_RUN:
        fn = all_strategies[name]
        calls_before, wallclock_before = _stats_snapshot(stats)
        t0 = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - t0
        calls_after, wallclock_after = _stats_snapshot(stats)
        top1 = top_k_hit(result, case.true_culprit, 1)
        top3 = top_k_hit(result, case.true_culprit, 3)
        strategy_records[name] = {
            "probes_consumed": result.probes_consumed,
            "top1_hit": top1,
            "top3_hit": top3,
            "ranked_top3": [c.tool_name for c in result.ranked[:3]],
            "marginal_live_probe_calls": calls_after - calls_before,
            "marginal_wallclock_s": wallclock_after - wallclock_before,
            "elapsed_s": elapsed,
        }
        print(
            f"  {name}: top1={top1} top3={top3} probes_consumed={result.probes_consumed} "
            f"marginal_live_calls={calls_after - calls_before} "
            f"marginal_wallclock_s={wallclock_after - wallclock_before:.2f}",
            flush=True,
        )

    baselines = _run_baselines(case)
    baseline_records: dict[str, Any] = {}
    for name, result in baselines.items():
        baseline_records[name] = {
            "top1_hit": top_k_hit(result, case.true_culprit, 1),
            "top3_hit": top_k_hit(result, case.true_culprit, 3),
            "ranked_top3": [c.tool_name for c in result.ranked[:3]],
        }
    n_changed = len(case.changed_tools)
    baseline_records["uniform_random_analytic"] = {
        "expected_top1": expected_topk_accuracy(n_changed, 1),
        "expected_top3": expected_topk_accuracy(n_changed, 3),
    }

    record = {
        "case_id": case_id,
        "server_name": case.server_name,
        "true_culprit": case.true_culprit,
        "changed_tools": case.changed_tools,
        "n_tasks": len(case.blind_tasks),
        "diff_chars": case.diff_chars,
        "before_arm_wallclock_s": stats.before_arm_wallclock_s,
        "total_live_probe_calls": stats.n_probe_calls,
        "total_cache_hits": stats.n_cache_hits,
        "total_wallclock_s": stats.total_wallclock_s,
        "strategies": strategy_records,
        "baselines": baseline_records,
    }
    _append_checkpoint(record)
    print(
        f"Case {case_id} total: {stats.total_wallclock_s:.2f}s wallclock, "
        f"{stats.n_probe_calls} distinct live probes ({stats.n_cache_hits} cache hits)",
        flush=True,
    )
    return record


def main() -> None:
    _print_environment_check()

    run_t0 = time.perf_counter()
    records: list[dict[str, Any]] = []
    for case_id in SELECTED_CASE_IDS:
        record = _run_one_case(case_id)
        records.append(record)
    total_elapsed = time.perf_counter() - run_t0

    print(f"\n=== Live-LLM phase complete: {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min) ===")

    summary = {
        "model": MODEL,
        "seed": SEED,
        "selected_case_ids": SELECTED_CASE_IDS,
        "total_wallclock_s": total_elapsed,
        "cases": records,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary written to {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
