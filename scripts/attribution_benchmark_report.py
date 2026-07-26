#!/usr/bin/env python3
"""Run the injected-culprit attribution benchmark (v0.5, Wave 1, Component 1.2) and print the
accuracy/budget table + confound-guard check that `reports/v0_5_attribution_benchmark.md` is
built from.

No live LLM calls -- every measurement in this script comes from
`agentgauge.attribution_benchmark`'s deterministic, synthetic ground-truth model (calibrated to
`type_enum_contradiction`'s real measured effect range) run through the real
`agentgauge.harness.diff_server_level` estimator. See `agentgauge/attribution_benchmark.py`'s
module docstring for the MEASURED-synthetic vs. NOT-MEASURED-live-agent distinction.

Usage:
    uv run python scripts/attribution_benchmark_report.py
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
    expected_topk_accuracy,
    top_k_hit,
)
from agentgauge.attribution_benchmark import (
    BenchmarkCase,
    confound_guard_report,
    generate_benchmark,
    make_probe_fn,
)
from agentgauge.audit import run_audit

N_CASES = 50
SEED = 42

SHIP_BAR_TOP1 = 0.70
SHIP_BAR_TOP3 = 0.90


def _run_baselines(case: BenchmarkCase) -> dict[str, AttributionResult]:
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


def main() -> None:
    t0 = time.time()
    cases = generate_benchmark(n_cases=N_CASES, seed=SEED)
    print(f"Generated {len(cases)} benchmark cases in {time.time() - t0:.1f}s")

    audit_report = run_audit(tasks=[], benchmark_cases=cases)
    print("\n--- Measurement-validity audit (agentgauge.audit.run_audit) ---")
    for f in audit_report.blocking:
        print(f"AUDIT BLOCK ({f.check}): {f.detail}")
    for f in audit_report.warnings:
        print(f"AUDIT WARN ({f.check}): {f.detail}")
    if not audit_report.passed:
        print("\nAudit failed -- refusing to report accuracy. Fix the flagged issue(s) and re-run.")
        sys.exit(2)
    print("Audit passed -- no blocking findings.")

    guard = confound_guard_report(cases)
    print("\n--- Confound-guard check ---")
    print(f"n_cases: {guard.n_cases}")
    print(f"position_counts (index of true culprit within changed_tools): {guard.position_counts}")
    print(f"n_distinct_positions_observed: {guard.n_positions_observed}")
    print(
        f"cases where culprit IS the max-diff tool: {guard.n_cases_culprit_is_max_diff}"
        f" ({guard.frac_cases_culprit_is_max_diff:.1%})"
    )
    print(
        f"cases where >=1 decoy diff EXCEEDS culprit diff: "
        f"{guard.n_cases_a_decoy_exceeds_culprit_diff} ({guard.frac_cases_a_decoy_exceeds_culprit_diff:.1%})"
    )
    print(
        f"mean culprit diff_chars: {guard.mean_culprit_diff_chars:.2f}  "
        f"mean decoy diff_chars: {guard.mean_decoy_diff_chars:.2f}  "
        f"mean culprit fractional rank (0=biggest,1=smallest, null=0.5): "
        f"{guard.mean_culprit_fractional_rank:.4f}"
    )

    strategy_names = [
        "exhaustive_ablation",
        "sampled_shapley",
        "greedy_bisection",
        "largest_textual_diff",
        "most_lint_violations",
        "uniform_random",
    ]
    top1_hits: dict[str, int] = dict.fromkeys(strategy_names, 0)
    top3_hits: dict[str, int] = dict.fromkeys(strategy_names, 0)
    probes: dict[str, list[int]] = {n: [] for n in strategy_names}
    n_changed_list: list[int] = []

    t0 = time.time()
    for case in cases:
        n_changed_list.append(len(case.changed_tools))
        probe_fn = make_probe_fn(case, seed=SEED)
        results: dict[str, AttributionResult] = {
            "exhaustive_ablation": attribute_exhaustive(case.changed_tools, probe_fn),
            "sampled_shapley": attribute_sampled_shapley(case.changed_tools, probe_fn, seed=SEED),
            "greedy_bisection": attribute_greedy_bisection(case.changed_tools, probe_fn),
            **_run_baselines(case),
        }
        for name, result in results.items():
            probes[name].append(result.probes_consumed)
            if top_k_hit(result, case.true_culprit, 1):
                top1_hits[name] += 1
            if top_k_hit(result, case.true_culprit, 3):
                top3_hits[name] += 1
    print(f"\nScored {len(cases)} cases across 6 methods in {time.time() - t0:.1f}s")

    n = len(cases)
    exhaustive_mean_probes = sum(probes["exhaustive_ablation"]) / n

    print("\n--- Accuracy / budget table ---")
    header = f"{'method':24s} {'top1':>7s} {'top3':>7s} {'mean_probes':>12s} {'vs_exhaustive':>14s}"
    print(header)
    for name in strategy_names:
        top1 = top1_hits[name] / n
        top3 = top3_hits[name] / n
        mean_probes = sum(probes[name]) / n
        sub_exhaustive = "sub-exh" if mean_probes < exhaustive_mean_probes else "n/a (0-probe)"
        if name == "exhaustive_ablation":
            sub_exhaustive = "reference"
        print(f"{name:24s} {top1:7.2%} {top3:7.2%} {mean_probes:12.2f} {sub_exhaustive:>14s}")

    print(
        "\n--- Uniform-random ANALYTIC expected accuracy (not the single-draw realized value) ---"
    )
    mean_top1_analytic = sum(expected_topk_accuracy(nc, 1) for nc in n_changed_list) / len(
        n_changed_list
    )
    mean_top3_analytic = sum(expected_topk_accuracy(nc, 3) for nc in n_changed_list) / len(
        n_changed_list
    )
    print(
        f"analytic mean top1: {mean_top1_analytic:.2%}, analytic mean top3: {mean_top3_analytic:.2%}"
    )

    print("\n--- Ship bar check (doctrine Component 1.2) ---")
    print(
        f"Ship bar: top1 >= {SHIP_BAR_TOP1:.0%} AND top3 >= {SHIP_BAR_TOP3:.0%}, sub-exhaustive budget."
    )
    any_ships = False
    for name in ("exhaustive_ablation", "sampled_shapley", "greedy_bisection"):
        top1 = top1_hits[name] / n
        top3 = top3_hits[name] / n
        mean_probes = sum(probes[name]) / n
        sub_exhaustive = mean_probes < exhaustive_mean_probes
        clears = top1 >= SHIP_BAR_TOP1 and top3 >= SHIP_BAR_TOP3 and sub_exhaustive
        any_ships = any_ships or clears
        print(
            f"{name}: top1={top1:.2%} top3={top3:.2%} mean_probes={mean_probes:.2f} "
            f"sub_exhaustive={sub_exhaustive} -> {'CLEARS' if clears else 'does not clear'} ship bar"
        )
    print(f"\nAny strategy clears the ship bar: {any_ships}")


if __name__ == "__main__":
    main()
