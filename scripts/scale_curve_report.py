#!/usr/bin/env python3
"""Candidate-set scale-curve + multi-culprit study for failure attribution (v0.5 Wave 1,
Component 1.2, Task 2 -- see `reports/v0_5_scale_curve.md`).

Follow-up to `reports/v0_5_attribution_benchmark.md` section 7j: with honest probe-cost
accounting, `greedy_bisection`'s always-attempted "confirm there's no second culprit" pass costs
MORE than exhaustive ablation on every benchmark measured so far -- but every one of those
benchmarks injects exactly ONE real culprit, making that pass guaranteed-failing overhead by
construction. This script answers the follow-up question directly: does that pass stop being
wasted once a genuine second (or third) culprit is present, and/or at larger candidate-set sizes?

Produces every number in `reports/v0_5_scale_curve.md`. No live LLM calls -- same deterministic
synthetic ground-truth model the rest of this repo's attribution benchmark uses, run through the
real `agentgauge.harness.diff_server_level` estimator per probe.

Usage:
    uv run python scripts/scale_curve_report.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from math import comb
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.attribution import (  # noqa: E402
    AttributionResult,
    ProbeFn,
    attribute_exhaustive,
    attribute_greedy_bisection,
    attribute_sampled_shapley,
    baseline_largest_textual_diff,
    baseline_most_lint_violations,
    baseline_uniform_random,
    expected_topk_accuracy,
)
from agentgauge.attribution_benchmark import (  # noqa: E402
    BenchmarkCase,
    MultiCulpritBenchmarkCase,
    before_arm_floor_clip_rate,
    confound_guard_report,
    generate_benchmark,
    generate_multi_culprit_benchmark,
    make_multi_probe_fn,
    make_probe_fn,
    multi_confound_guard_report,
)
from agentgauge.audit import (  # noqa: E402
    check_benchmark_construction_diffsize_bias,
    check_probe_variance_calibration,
)

STRATEGY_SEED = 42  # internal RNG seed for sampled_shapley/uniform_random, uniform across buckets
N_CASES_PER_BUCKET = 30

SHIP_BAR_RECALL = 0.70  # generalizes the doctrine's top-1 >= 0.70 bar -- see report sec 1
SHIP_BAR_STRICT_TOP3 = 0.90  # unchanged from the doctrine's top-3 >= 0.90 bar

# This study's own seed family -- deliberately distinct from
# reports/v0_5_effect_size_sensitivity.md's per-band seeds (42/1042/2042/3042/4042), which vary a
# DIFFERENT parameter (effect magnitude) at a fixed candidate-set-size range (2-6). Reusing those
# exact seed values here, for a generator call that varies candidate-set SIZE instead, would risk
# a reader assuming the two studies share cases; they do not, and giving this study its own seed
# family makes that unambiguous without relying on prose alone.
SINGLE_BUCKET_SEEDS: dict[int, int] = {4: 42, 10: 1_010, 20: 1_020, 40: 1_040}

# (n_culprits, n_changed, seed). The first two entries are the task's required minimum (2/3
# culprits at one "realistic PR scale" size, n_changed=20). The third entry (3 culprits at
# n_changed=40) was added AFTER the first two ran and showed 3-culprit @ n_changed=20 crossing
# back OVER exhaustive's cost -- not to chase a favorable number (the outcome was unknown when
# this was added), but because Task 2c explicitly asks "at what size does cost cross below
# n_changed" and a single n_changed=20 data point cannot show whether a larger candidate set
# rescues the 3-culprit case the way it rescues the single-culprit case between n_changed=4 and
# n_changed=40. This is disclosed here, not silently folded into "the plan all along."
MULTI_BUCKETS: list[tuple[int, int, int]] = [
    (2, 20, 1_102),
    (3, 20, 1_103),
    (3, 40, 1_140),
]

STRATEGY_NAMES = [
    "exhaustive_ablation",
    "sampled_shapley",
    "greedy_bisection",
    "largest_textual_diff",
    "most_lint_violations",
    "uniform_random",
]


# =============================================================================
# Multi-culprit-aware scoring. NOT added to agentgauge.attribution (out of this task's edit scope
# -- that module's top_k_hit is intentionally single-culprit-string-shaped); these are thin,
# self-contained generalizations local to this script.
# =============================================================================


def strict_topk_hit(result: AttributionResult, true_culprits: set[str], k: int) -> bool:
    """STRICT convention: does the top-k ranked list contain ALL true culprits? Reduces exactly
    to `agentgauge.attribution.top_k_hit` when `len(true_culprits) == 1`."""
    top_k_names = {c.tool_name for c in result.ranked[:k]}
    return true_culprits.issubset(top_k_names)


def recall_at_k(result: AttributionResult, true_culprits: set[str], k: int) -> float:
    """PARTIAL-CREDIT convention: fraction of true culprits present in the top-k ranked list.
    Reduces exactly to a 0/1 top-k hit when `len(true_culprits) == 1`."""
    if not true_culprits:
        return 0.0
    top_k_names = {c.tool_name for c in result.ranked[:k]}
    hits = len(true_culprits & top_k_names)
    return hits / len(true_culprits)


def expected_strict_topk_uniform(n: int, m: int, k: int) -> float:
    """Analytic probability that a uniformly random ranking of `n` candidates (containing `m`
    true culprits) places ALL `m` of them within the first `k` positions.

    Derivation: for a uniformly random permutation of n items, the SET occupying the first k
    positions is itself a uniformly random k-subset of the n items (a standard fact about random
    permutations). So P(all m marked items land in a random k-subset) is the hypergeometric
    containment probability C(n-m, k-m) / C(n, k) for k >= m, and exactly 0 for k < m (you cannot
    fit m items into fewer than m slots). At m=1 this reduces to k/n, matching
    `agentgauge.attribution.expected_topk_accuracy`'s existing single-culprit formula exactly."""
    if k < m or n <= 0:
        return 0.0
    k = min(k, n)
    return comb(n - m, k - m) / comb(n, k)


def expected_recall_at_k_uniform(n: int, k: int) -> float:
    """Analytic expected recall@k of a uniformly random ranking over n candidates: E[recall@k] =
    k/n, INDEPENDENT of m (the true-culprit count) -- by linearity of expectation, each individual
    true culprit independently has probability k/n of landing in a random k-subset, and recall@k
    is just the mean of m such 0/1 indicators, whose individual expectations are each k/n
    regardless of how many there are or which items the others are. This is numerically identical
    to `agentgauge.attribution.expected_topk_accuracy(n, k)` -- reused directly below rather than
    reimplemented, since the two formulas ARE the same formula once recall@k=|true_culprits| is
    recognized as the multi-culprit generalization of "top-k accuracy" from a single true item."""
    return expected_topk_accuracy(n, k)


@dataclass
class BucketResult:
    label: str
    n_changed: int
    n_culprits: int
    n_cases: int
    top1_strict: dict[str, float]
    top3_strict: dict[str, float]
    recall_at_m: dict[str, float]
    mean_probes: dict[str, float]


def _run_probe_strategies(
    changed_tools: list[str], probe_fn: ProbeFn
) -> dict[str, AttributionResult]:
    return {
        "exhaustive_ablation": attribute_exhaustive(changed_tools, probe_fn),
        "sampled_shapley": attribute_sampled_shapley(changed_tools, probe_fn, seed=STRATEGY_SEED),
        "greedy_bisection": attribute_greedy_bisection(changed_tools, probe_fn),
    }


def _run_baselines(
    changed_tools: list[str],
    before_desc: dict[str, str],
    after_desc: dict[str, str],
    tools_before_like: list[Any],
    tools_after_like: list[Any],
) -> dict[str, AttributionResult]:
    return {
        "largest_textual_diff": baseline_largest_textual_diff(
            changed_tools, before_desc, after_desc
        ),
        "most_lint_violations": baseline_most_lint_violations(
            changed_tools, tools_before_like, tools_after_like
        ),
        "uniform_random": baseline_uniform_random(changed_tools, seed=STRATEGY_SEED),
    }


def _score_bucket(
    label: str,
    n_changed: int,
    n_culprits: int,
    cases: list[BenchmarkCase] | list[MultiCulpritBenchmarkCase],
) -> BucketResult:
    top1_hits: dict[str, int] = dict.fromkeys(STRATEGY_NAMES, 0)
    top3_hits: dict[str, int] = dict.fromkeys(STRATEGY_NAMES, 0)
    recall_sums: dict[str, float] = dict.fromkeys(STRATEGY_NAMES, 0.0)
    probe_sums: dict[str, int] = dict.fromkeys(STRATEGY_NAMES, 0)

    for case in cases:
        if isinstance(case, MultiCulpritBenchmarkCase):
            true_culprits = set(case.true_culprits)
            probe_fn = make_multi_probe_fn(case, seed=STRATEGY_SEED)
        else:
            true_culprits = {case.true_culprit}
            probe_fn = make_probe_fn(case, seed=STRATEGY_SEED)

        before_desc = {t: case.before_description(t) for t in case.changed_tools}
        after_desc = {t: case.after_description(t) for t in case.changed_tools}
        results: dict[str, AttributionResult] = {
            **_run_probe_strategies(case.changed_tools, probe_fn),
            **_run_baselines(
                case.changed_tools,
                before_desc,
                after_desc,
                case.tools_before_like(),
                case.tools_after_like(),
            ),
        }
        m = len(true_culprits)
        for name, result in results.items():
            probe_sums[name] += result.probes_consumed
            if strict_topk_hit(result, true_culprits, 1):
                top1_hits[name] += 1
            if strict_topk_hit(result, true_culprits, 3):
                top3_hits[name] += 1
            recall_sums[name] += recall_at_k(result, true_culprits, m)

    n = len(cases)
    return BucketResult(
        label=label,
        n_changed=n_changed,
        n_culprits=n_culprits,
        n_cases=n,
        top1_strict={k: v / n for k, v in top1_hits.items()},
        top3_strict={k: v / n for k, v in top3_hits.items()},
        recall_at_m={k: v / n for k, v in recall_sums.items()},
        mean_probes={k: v / n for k, v in probe_sums.items()},
    )


def _print_confound_guard_single(label: str, cases: list[BenchmarkCase]) -> bool:
    guard = confound_guard_report(cases)
    audit_findings = check_benchmark_construction_diffsize_bias(cases)
    # Artifact #10 guard (v0.5 Wave 1.6): sample a raw probe CI width (true-culprit revert) per
    # case, so this bucket's own probe/ground-truth noise floor is checked too -- see
    # reports/v0_5_mde_discrepancy.md and reports/v0_5_shapley_scaling_audit.md.
    probe_ci_widths = []
    for case in cases:
        pfn = make_probe_fn(case, seed=STRATEGY_SEED)
        r = pfn(frozenset({case.true_culprit}))
        probe_ci_widths.append(r.ci_hi - r.ci_lo)
    probe_findings = check_probe_variance_calibration(probe_ci_widths, n_tasks=24)
    print(f"\n--- Confound guard: {label} (n={len(cases)}) ---")
    print(f"n_positions_observed: {guard.n_positions_observed}")
    print(
        f"frac culprit is max-diff tool: {guard.frac_cases_culprit_is_max_diff:.4f}  "
        f"frac a decoy exceeds culprit diff: {guard.frac_cases_a_decoy_exceeds_culprit_diff:.4f}"
    )
    print(f"mean culprit fractional rank: {guard.mean_culprit_fractional_rank:.4f}")
    print(f"audit.check_benchmark_construction_diffsize_bias BLOCK fired: {bool(audit_findings)}")
    print(f"audit.check_probe_variance_calibration BLOCK fired: {bool(probe_findings)}")
    passed = (
        guard.n_positions_observed > 1
        and guard.frac_cases_culprit_is_max_diff < 1.0
        and 0.35 <= guard.mean_culprit_fractional_rank <= 0.65
        and not audit_findings
        and not probe_findings
    )
    print(f"GUARD PASSED: {passed}")
    return passed


def _print_confound_guard_multi(label: str, cases: list[MultiCulpritBenchmarkCase]) -> bool:
    guard = multi_confound_guard_report(cases)
    # Artifact #10 guard: same idea as the single-culprit guard above, reverting ALL true
    # culprits per case (the analogue of a "full recovery" probe for a multi-culprit case).
    probe_ci_widths = []
    for case in cases:
        pfn = make_multi_probe_fn(case, seed=STRATEGY_SEED)
        r = pfn(frozenset(case.true_culprits))
        probe_ci_widths.append(r.ci_hi - r.ci_lo)
    probe_findings = check_probe_variance_calibration(probe_ci_widths, n_tasks=24)
    print(f"\n--- Multi-culprit confound guard: {label} (n={len(cases)}) ---")
    print(f"n_positions_observed: {guard.n_positions_observed}")
    print(
        f"frac a culprit is max-diff tool: {guard.frac_cases_a_culprit_is_max_diff:.4f}  "
        f"frac a decoy exceeds MIN culprit diff: "
        f"{guard.frac_cases_a_decoy_exceeds_min_culprit_diff:.4f}"
    )
    print(f"mean per-culprit-instance fractional rank: {guard.mean_culprit_fractional_rank:.4f}")
    clip_rate = before_arm_floor_clip_rate(cases)
    print(f"before-arm floor-clip rate (0.0 clipping in the ground-truth model): {clip_rate:.4f}")
    print(f"audit.check_probe_variance_calibration BLOCK fired: {bool(probe_findings)}")
    passed = (
        guard.n_positions_observed > 1
        and guard.frac_cases_a_culprit_is_max_diff < 1.0
        and 0.35 <= guard.mean_culprit_fractional_rank <= 0.65
        and not probe_findings
    )
    print(f"GUARD PASSED: {passed}")
    return passed


def _print_bucket_table(result: BucketResult) -> None:
    exhaustive_probes = result.mean_probes["exhaustive_ablation"]
    print(f"\n--- Accuracy / budget table: {result.label} ---")
    header = (
        f"{'method':24s} {'top1_strict':>12s} {'top3_strict':>12s} {'recall@m':>10s} "
        f"{'mean_probes':>12s} {'vs_exhaustive':>14s}"
    )
    print(header)
    for name in STRATEGY_NAMES:
        mean_probes = result.mean_probes[name]
        if name == "exhaustive_ablation":
            tag = "reference"
        elif name in ("largest_textual_diff", "most_lint_violations", "uniform_random"):
            tag = "0-probe"
        else:
            tag = "sub-exh" if mean_probes < exhaustive_probes else "MORE EXPENSIVE"
        print(
            f"{name:24s} {result.top1_strict[name]:12.2%} {result.top3_strict[name]:12.2%} "
            f"{result.recall_at_m[name]:10.2%} {mean_probes:12.2f} {tag:>14s}"
        )
    m = result.n_culprits
    n = result.n_changed
    print(
        f"uniform_random ANALYTIC: top1_strict={expected_strict_topk_uniform(n, m, 1):.2%} "
        f"top3_strict={expected_strict_topk_uniform(n, m, 3):.2%} "
        f"recall@m={expected_recall_at_k_uniform(n, m):.2%}"
    )


def _ship_bar_verdict(result: BucketResult) -> None:
    print(
        f"\n--- Ship bar (recall@m >= {SHIP_BAR_RECALL:.0%} AND top3_strict >= "
        f"{SHIP_BAR_STRICT_TOP3:.0%} AND sub-exhaustive): {result.label} ---"
    )
    exhaustive_probes = result.mean_probes["exhaustive_ablation"]
    for name in ("sampled_shapley", "greedy_bisection"):
        recall = result.recall_at_m[name]
        top3 = result.top3_strict[name]
        probes = result.mean_probes[name]
        sub_exhaustive = probes < exhaustive_probes
        clears = recall >= SHIP_BAR_RECALL and top3 >= SHIP_BAR_STRICT_TOP3 and sub_exhaustive
        print(
            f"{name}: recall@m={recall:.2%} top3_strict={top3:.2%} mean_probes={probes:.2f} "
            f"(exhaustive={exhaustive_probes:.2f}) sub_exhaustive={sub_exhaustive} -> "
            f"{'CLEARS' if clears else 'does not clear'}"
        )


def main() -> None:
    t_start = time.time()
    all_results: list[BucketResult] = []

    print("=" * 78)
    print("SINGLE-CULPRIT BUCKETS (Task 2a): n_changed in {4, 10, 20, 40}")
    print("=" * 78)
    for n_changed, seed in SINGLE_BUCKET_SEEDS.items():
        label = f"single_n{n_changed}"
        t0 = time.time()
        cases = generate_benchmark(n_cases=N_CASES_PER_BUCKET, seed=seed, n_changed=n_changed)
        assert len(cases) == N_CASES_PER_BUCKET, (
            f"{label}: generated {len(cases)} cases, expected {N_CASES_PER_BUCKET}"
        )
        guard_ok = _print_confound_guard_single(label, cases)
        if not guard_ok:
            print(f"REFUSING to report accuracy for {label}: confound guard failed.")
            sys.exit(2)
        result = _score_bucket(label, n_changed, 1, cases)
        _print_bucket_table(result)
        _ship_bar_verdict(result)
        all_results.append(result)
        print(f"[{label} done in {time.time() - t0:.1f}s]")

    print("\n" + "=" * 78)
    print(f"MULTI-CULPRIT BUCKETS (Task 2b): (n_culprits, n_changed) in {MULTI_BUCKETS}")
    print("=" * 78)
    for n_culprits, n_changed, seed in MULTI_BUCKETS:
        label = f"multi_c{n_culprits}_n{n_changed}"
        t0 = time.time()
        multi_cases = generate_multi_culprit_benchmark(
            n_cases=N_CASES_PER_BUCKET,
            n_culprits=n_culprits,
            n_changed=n_changed,
            seed=seed,
        )
        assert len(multi_cases) == N_CASES_PER_BUCKET, (
            f"{label}: generated {len(multi_cases)} cases, expected {N_CASES_PER_BUCKET}"
        )
        guard_ok = _print_confound_guard_multi(label, multi_cases)
        if not guard_ok:
            print(f"REFUSING to report accuracy for {label}: multi-culprit confound guard failed.")
            sys.exit(2)
        result = _score_bucket(label, n_changed, n_culprits, multi_cases)
        _print_bucket_table(result)
        _ship_bar_verdict(result)
        all_results.append(result)
        print(f"[{label} done in {time.time() - t0:.1f}s]")

    print("\n" + "=" * 78)
    print("BUDGET-CROSSOVER ANALYSIS (Task 2c)")
    print("=" * 78)
    for name in ("sampled_shapley", "greedy_bisection"):
        print(f"\n{name}:")
        for r in all_results:
            probes = r.mean_probes[name]
            exhaustive = r.mean_probes["exhaustive_ablation"]
            sub = probes < exhaustive
            print(
                f"  {r.label:20s} n_changed={r.n_changed:3d} n_culprits={r.n_culprits} "
                f"mean_probes={probes:6.2f}  exhaustive={exhaustive:6.2f}  "
                f"sub_exhaustive={sub}  ({(probes / exhaustive - 1) * 100:+.1f}% vs exhaustive)"
            )

    print(f"\nTotal runtime: {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
