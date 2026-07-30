#!/usr/bin/env python3
"""Attribution accuracy/budget/cost re-run at improved probe power (v0.5 Wave 1.6, Task 2d/2e).

Per `reports/v0_5_probe_power_fix.md` (Task 2b/2c): the current per-probe n_tasks=24 gives a
production per-probe MDE of ~18.18pp; n_tasks=128 is the smallest value tested that clears the
<=8pp target (7.34pp). This script re-runs the SAME candidate-set-size sweep (single-culprit
4/10/20/40; multi-culprit 2/3 culprits at n_changed=20/40) `scripts/scale_curve_report.py` already
measured at n_tasks=24, at n_tasks=128 instead -- same case-generation logic, same strategies, same
scoring conventions (imported directly from `scripts.scale_curve_report`, not reimplemented, so
this is a controlled, single-variable comparison against that report's numbers) -- plus a cost-
economics section (Task 2e) neither prior report computed: trial-equivalents and wall-clock cost
per strategy, compared against a full 253-task corpus re-evaluation.

Zero live LLM calls -- same deterministic synthetic ground-truth model every other v0.5
attribution report uses.

Usage:
    uv run python scripts/attribution_improved_probes_report.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.attribution import (
    AttributionResult,
    attribute_exhaustive,
    attribute_greedy_bisection,
    attribute_sampled_shapley,
    baseline_largest_textual_diff,
    baseline_most_lint_violations,
    baseline_uniform_random,
)
from agentgauge.attribution_benchmark import (
    MultiCulpritBenchmarkCase,
    confound_guard_report,
    generate_benchmark,
    generate_multi_culprit_benchmark,
    make_multi_probe_fn,
    make_probe_fn,
    multi_confound_guard_report,
)
from agentgauge.audit import (
    check_benchmark_construction_diffsize_bias,
    check_probe_variance_calibration,
)
from scripts.scale_curve_report import (  # noqa: E402
    STRATEGY_NAMES,
    expected_recall_at_k_uniform,
    expected_strict_topk_uniform,
    recall_at_k,
    strict_topk_hit,
)

N_TASKS = 128  # Task 2c's answer -- the smallest tested n_tasks clearing the <=8pp MDE target
STRATEGY_SEED = 42
N_CASES_PER_BUCKET = 30  # same as scripts/scale_curve_report.py -- controlled comparison
SHIP_BAR_RECALL = 0.70
SHIP_BAR_STRICT_TOP3 = 0.90

SINGLE_BUCKET_SEEDS: dict[int, int] = {4: 42, 10: 1_010, 20: 1_020, 40: 1_040}
MULTI_BUCKETS: list[tuple[int, int, int]] = [(2, 20, 1_102), (3, 20, 1_103), (3, 40, 1_140)]

# Full-corpus re-evaluation baseline (Task 2e): 253 tasks, 1 trial/task, 2 arms -- matches
# simulate_mde_task_level's default trials_per_task=1 assumption, the same assumption behind the
# repo's own "MDE 0.0537 at n=253" headline (spec-agentgauge-v0.5.md).
FULL_CORPUS_N_TASKS = 253
FULL_REEVAL_TRIAL_EQUIVALENTS = FULL_CORPUS_N_TASKS * 2

# Real-agent wall-clock per task-trial, from reports/v0_5_real_agent_validation.md's single real
# case (28.61s / 4 tasks = 7.15s/task before-arm; separately, the pilot's two prior measurements
# were 5.42 and 9.20 s/task -- a ~1.7x spread). Point estimate + range, both disclosed as NOT
# separately re-measured here (no live inference run for this report; see MEASURED/NOT MEASURED).
REAL_S_PER_TASK_POINT = 7.15
REAL_S_PER_TASK_RANGE = (5.42, 9.20)


def _run_probes(changed_tools: list[str], probe_fn) -> dict[str, AttributionResult]:
    return {
        "exhaustive_ablation": attribute_exhaustive(changed_tools, probe_fn),
        "sampled_shapley": attribute_sampled_shapley(changed_tools, probe_fn, seed=STRATEGY_SEED),
        "greedy_bisection": attribute_greedy_bisection(changed_tools, probe_fn),
    }


def _run_baselines(case) -> dict[str, AttributionResult]:
    before_desc = {t: case.before_description(t) for t in case.changed_tools}
    after_desc = {t: case.after_description(t) for t in case.changed_tools}
    return {
        "largest_textual_diff": baseline_largest_textual_diff(
            case.changed_tools, before_desc, after_desc
        ),
        "most_lint_violations": baseline_most_lint_violations(
            case.changed_tools, case.tools_before_like(), case.tools_after_like()
        ),
        "uniform_random": baseline_uniform_random(case.changed_tools, seed=STRATEGY_SEED),
    }


def _score_bucket(label: str, n_changed: int, n_culprits: int, cases: list) -> dict:
    top1_hits = dict.fromkeys(STRATEGY_NAMES, 0)
    top3_hits = dict.fromkeys(STRATEGY_NAMES, 0)
    recall_sums = dict.fromkeys(STRATEGY_NAMES, 0.0)
    probe_sums = dict.fromkeys(STRATEGY_NAMES, 0)
    probe_ci_widths: list[float] = []

    for case in cases:
        if isinstance(case, MultiCulpritBenchmarkCase):
            true_culprits = set(case.true_culprits)
            probe_fn = make_multi_probe_fn(case, n_tasks=N_TASKS, seed=STRATEGY_SEED)
            r = probe_fn(frozenset(case.true_culprits))
        else:
            true_culprits = {case.true_culprit}
            probe_fn = make_probe_fn(case, n_tasks=N_TASKS, seed=STRATEGY_SEED)
            r = probe_fn(frozenset({case.true_culprit}))
        probe_ci_widths.append(r.ci_hi - r.ci_lo)

        results = {**_run_probes(case.changed_tools, probe_fn), **_run_baselines(case)}
        m = len(true_culprits)
        for name, result in results.items():
            probe_sums[name] += result.probes_consumed
            if strict_topk_hit(result, true_culprits, 1):
                top1_hits[name] += 1
            if strict_topk_hit(result, true_culprits, 3):
                top3_hits[name] += 1
            recall_sums[name] += recall_at_k(result, true_culprits, m)

    n = len(cases)
    return {
        "label": label,
        "n_changed": n_changed,
        "n_culprits": n_culprits,
        "n_cases": n,
        "top1_strict": {k: v / n for k, v in top1_hits.items()},
        "top3_strict": {k: v / n for k, v in top3_hits.items()},
        "recall_at_m": {k: v / n for k, v in recall_sums.items()},
        "mean_probes": {k: v / n for k, v in probe_sums.items()},
        "probe_ci_widths": probe_ci_widths,
    }


def _print_bucket(result: dict) -> None:
    print(f"\n--- {result['label']} (n_changed={result['n_changed']}, n_culprits={result['n_culprits']}, n_tasks={N_TASKS}) ---")
    exhaustive_probes = result["mean_probes"]["exhaustive_ablation"]
    header = (
        f"{'method':22s} {'top1_strict':>12s} {'top3_strict':>12s} {'recall@m':>10s} "
        f"{'mean_probes':>12s} {'trial_equiv':>12s} {'wall_clock_pt':>14s} {'vs_full_reeval':>15s}"
    )
    print(header)
    for name in STRATEGY_NAMES:
        mp = result["mean_probes"][name]
        trial_equiv = mp * N_TASKS * 2
        wall_clock = trial_equiv * REAL_S_PER_TASK_POINT
        vs_full = "cheaper" if trial_equiv < FULL_REEVAL_TRIAL_EQUIVALENTS else "MORE EXPENSIVE"
        if name in ("largest_textual_diff", "most_lint_violations", "uniform_random"):
            vs_full = "0-probe"
        print(
            f"{name:22s} {result['top1_strict'][name]:12.2%} {result['top3_strict'][name]:12.2%} "
            f"{result['recall_at_m'][name]:10.2%} {mp:12.2f} {trial_equiv:12.0f} "
            f"{wall_clock:12.1f}s {vs_full:>15s}"
        )
    m = result["n_culprits"]
    n = result["n_changed"]
    print(
        f"uniform_random ANALYTIC: top1_strict={expected_strict_topk_uniform(n, m, 1):.2%} "
        f"top3_strict={expected_strict_topk_uniform(n, m, 3):.2%} "
        f"recall@m={expected_recall_at_k_uniform(n, m):.2%}"
    )
    for name in ("sampled_shapley", "greedy_bisection"):
        recall = result["recall_at_m"][name]
        top3 = result["top3_strict"][name]
        probes = result["mean_probes"][name]
        sub_exhaustive = probes < exhaustive_probes
        clears = recall >= SHIP_BAR_RECALL and top3 >= SHIP_BAR_STRICT_TOP3 and sub_exhaustive
        print(
            f"SHIP BAR {name}: recall@m={recall:.2%} top3_strict={top3:.2%} sub_exhaustive={sub_exhaustive} "
            f"-> {'CLEARS' if clears else 'does not clear'}"
        )


def main() -> None:
    print(f"N_TASKS={N_TASKS}, N_CASES_PER_BUCKET={N_CASES_PER_BUCKET}, seed_family per bucket")
    print(
        f"Full-corpus re-eval baseline: {FULL_CORPUS_N_TASKS} tasks x 2 arms x 1 trial = "
        f"{FULL_REEVAL_TRIAL_EQUIVALENTS} trial-equivalents, "
        f"~{FULL_REEVAL_TRIAL_EQUIVALENTS * REAL_S_PER_TASK_POINT:.0f}s "
        f"({FULL_REEVAL_TRIAL_EQUIVALENTS * REAL_S_PER_TASK_POINT / 60:.1f} min) at "
        f"{REAL_S_PER_TASK_POINT}s/task point estimate "
        f"(range {REAL_S_PER_TASK_RANGE[0]}-{REAL_S_PER_TASK_RANGE[1]}s/task, "
        f"n=1 real-agent-derived, NOT independently re-measured this pass)"
    )

    all_results = []
    t_start = time.time()

    print("\n=== Single-culprit buckets ===")
    for n_changed, seed in SINGLE_BUCKET_SEEDS.items():
        t0 = time.time()
        cases = generate_benchmark(n_cases=N_CASES_PER_BUCKET, seed=seed, n_changed=n_changed)
        guard = confound_guard_report(cases)
        diffsize_findings = check_benchmark_construction_diffsize_bias(cases)
        result = _score_bucket(f"single_n{n_changed}", n_changed, 1, cases)
        probe_findings = check_probe_variance_calibration(result["probe_ci_widths"], n_tasks=N_TASKS)
        print(
            f"\n[guard: single_n{n_changed}] positions={guard.n_positions_observed} "
            f"frac_max_diff={guard.frac_cases_culprit_is_max_diff:.3f} "
            f"fractional_rank={guard.mean_culprit_fractional_rank:.4f} "
            f"diffsize_BLOCK={bool(diffsize_findings)} "
            f"probe_variance_BLOCK={bool(probe_findings)}"
        )
        _print_bucket(result)
        all_results.append(result)
        print(f"[{n_changed} done in {time.time() - t0:.1f}s]")

    print("\n=== Multi-culprit buckets ===")
    for n_culprits, n_changed, seed in MULTI_BUCKETS:
        t0 = time.time()
        multi_cases = generate_multi_culprit_benchmark(
            n_cases=N_CASES_PER_BUCKET, n_culprits=n_culprits, n_changed=n_changed, seed=seed
        )
        multi_guard = multi_confound_guard_report(multi_cases)
        label = f"multi_c{n_culprits}_n{n_changed}"
        result = _score_bucket(label, n_changed, n_culprits, multi_cases)
        probe_findings = check_probe_variance_calibration(result["probe_ci_widths"], n_tasks=N_TASKS)
        print(
            f"\n[guard: {label}] positions={multi_guard.n_positions_observed} "
            f"frac_a_max_diff={multi_guard.frac_cases_a_culprit_is_max_diff:.3f} "
            f"fractional_rank={multi_guard.mean_culprit_fractional_rank:.4f} "
            f"probe_variance_BLOCK={bool(probe_findings)}"
        )
        _print_bucket(result)
        all_results.append(result)
        print(f"[{label} done in {time.time() - t0:.1f}s]")

    print(f"\nTotal runtime: {time.time() - t_start:.1f}s")

    print("\n=== Cost-economics crossover summary (Task 2e) ===")
    print(
        f"{'bucket':16s} {'method':22s} {'mean_probes':>12s} {'trial_equiv':>12s} "
        f"{'vs_full_reeval(506)':>20s}"
    )
    for result in all_results:
        for name in ("exhaustive_ablation", "sampled_shapley", "greedy_bisection"):
            mp = result["mean_probes"][name]
            te = mp * N_TASKS * 2
            ratio = te / FULL_REEVAL_TRIAL_EQUIVALENTS
            print(
                f"{result['label']:16s} {name:22s} {mp:12.2f} {te:12.0f} "
                f"{ratio:19.2f}x"
            )


if __name__ == "__main__":
    main()
