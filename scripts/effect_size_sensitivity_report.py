#!/usr/bin/env python3
"""Effect-size sensitivity study for failure attribution (v0.5 Wave 1, Component 1.2 follow-up).

Measures how `agentgauge.attribution`'s probe-based localization strategies degrade as the true
injected culprit's effect magnitude shrinks toward -- and below -- the harness's own measured
minimum detectable effect, instead of only at the original `attribution_benchmark`'s favorable,
well-separated 13.3-28.9pp range (see `reports/v0_5_attribution_benchmark.md`).

Produces every number in `reports/v0_5_effect_size_sensitivity.md`. No live LLM calls -- same
deterministic synthetic ground-truth model the rest of this repo's attribution benchmark uses,
run through the real `agentgauge.harness.diff_server_level` estimator per probe.

Usage:
    uv run python scripts/effect_size_sensitivity_report.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.attribution import (
    DEFAULT_THRESHOLD,
    AttributionResult,
    ProbeFn,
    attribute_exhaustive,
    attribute_greedy_bisection,
    attribute_sampled_shapley,
    baseline_largest_textual_diff,
    baseline_most_lint_violations,
    baseline_uniform_random,
    top_k_hit,
)
from agentgauge.attribution_benchmark import (
    CAUSAL_EFFECT_MAX_PP,
    CAUSAL_EFFECT_MIN_PP,
    BenchmarkCase,
    confound_guard_report,
    generate_benchmark,
    make_probe_fn,
)
from agentgauge.audit import check_benchmark_construction_diffsize_bias, run_audit
from agentgauge.harness import CALIBRATED_BASELINE_RATE, simulate_mde_task_level

SEED = 42
N_CASES_PER_BAND = 24
SHIP_BAR_TOP1 = 0.70
SHIP_BAR_TOP3 = 0.90

# Doctrine headline MDE (spec-agentgauge-v0.5.md sec 4.2 / reports/v2_5_task3_mde_grid.md-family):
# 0.0537 FRACTION at n_tasks=253, measured by agentgauge.harness.simulate_mde_task_level. On this
# module's signed _pp scale (see attribution_benchmark.generate_benchmark's docstring) that is
# 5.37pp -- the number the task instruction resolved as the sensitivity study's anchor.
DOCTRINE_MDE_PP_AT_N253 = 5.37

# label, effect_min_pp (more negative / larger magnitude), effect_max_pp (less negative /
# smaller magnitude), seed. Kept in sync manually with tests/test_effect_size_sensitivity.py's
# _EFFECT_BANDS (see that file's module docstring for why it's duplicated, not imported).
EFFECT_BANDS: tuple[tuple[str, float, float, int], ...] = (
    ("below_mde_3.0_5.0pp", -5.0, -3.0, 42),
    ("straddle_mde_5.0_8.0pp", -8.0, -5.0, 1042),
    ("moderate_8.0_13.3pp", -13.3, -8.0, 2042),
    ("original_13.3_28.9pp", CAUSAL_EFFECT_MIN_PP, CAUSAL_EFFECT_MAX_PP, 3042),
    ("beyond_28.9_33.0pp", -33.0, -28.9, 4042),
)

STRATEGY_NAMES = (
    "exhaustive_ablation",
    "sampled_shapley",
    "greedy_bisection",
    "largest_textual_diff",
    "most_lint_violations",
    "uniform_random",
)


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


@dataclass
class BandResult:
    label: str
    min_pp: float
    max_pp: float
    n_cases: int
    top1: dict[str, float]
    top3: dict[str, float]
    mean_probes: dict[str, float]
    confound_guard_findings: list[str]
    mean_culprit_fractional_rank: float


def _run_band(label: str, min_pp: float, max_pp: float, seed: int) -> BandResult:
    cases = generate_benchmark(
        n_cases=N_CASES_PER_BAND, seed=seed, effect_min_pp=min_pp, effect_max_pp=max_pp
    )

    # Artifact #10 guard (v0.5 Wave 1.6): sample a raw probe CI width (true-culprit revert) per
    # case at this band's own n_tasks, so run_audit can check the probe/ground-truth model's
    # noise floor at every effect band, not just the original benchmark -- see
    # reports/v0_5_mde_discrepancy.md and reports/v0_5_shapley_scaling_audit.md.
    probe_ci_widths = []
    for case in cases:
        pfn = make_probe_fn(case, seed=SEED)
        r = pfn(frozenset({case.true_culprit}))
        probe_ci_widths.append(r.ci_hi - r.ci_lo)

    audit_report = run_audit(
        tasks=[],
        benchmark_cases=cases,
        probe_ci_widths=probe_ci_widths,
        probe_n_tasks=24,
    )
    guard = confound_guard_report(cases)
    audit_findings = [f.detail for f in audit_report.blocking]
    audit_findings += [f.detail for f in check_benchmark_construction_diffsize_bias(cases)]

    top1_hits: dict[str, int] = dict.fromkeys(STRATEGY_NAMES, 0)
    top3_hits: dict[str, int] = dict.fromkeys(STRATEGY_NAMES, 0)
    probes: dict[str, list[int]] = {n: [] for n in STRATEGY_NAMES}

    for case in cases:
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

    n = len(cases)
    return BandResult(
        label=label,
        min_pp=min_pp,
        max_pp=max_pp,
        n_cases=n,
        top1={k: top1_hits[k] / n for k in STRATEGY_NAMES},
        top3={k: top3_hits[k] / n for k in STRATEGY_NAMES},
        mean_probes={k: sum(probes[k]) / n for k in STRATEGY_NAMES},
        confound_guard_findings=audit_findings,
        mean_culprit_fractional_rank=guard.mean_culprit_fractional_rank,
    )


# =============================================================================
# Mechanism investigation: diagnostic-only reimplementation of greedy bisection's
# decision logic, instrumented against ground truth. See module docstring below
# and reports/v0_5_effect_size_sensitivity.md section "mechanism investigation".
# =============================================================================


@dataclass
class BisectionDecision:
    case_id: str
    probed_half: tuple[str, ...]
    marginal_delta: float
    marginal_ci_lo: float
    decision_significant: bool  # marginal_ci_lo > threshold -> "recurse into probed_half"
    ground_truth_significant: bool  # true_culprit is genuinely still findable in probed_half
    classification: str  # "correct" | "mode_a_detection_power_failure" | "mode_b_false_positive_noise"


def trace_greedy_bisection_decisions(
    changed_tools: list[str],
    probe: ProbeFn,
    true_culprit: str,
    case_id: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[BisectionDecision]:
    """Diagnostic-only reimplementation mirroring `agentgauge.attribution._bisect_within` /
    `attribute_greedy_bisection`'s decision logic exactly (duplicated, not imported or modified --
    attribution.py's strategy logic is out of this task's scope to change), instrumented to
    classify each binary-search split decision (and the final single-candidate confirmation)
    against GROUND TRUTH, which only the benchmark (never the real strategy) has access to.

    Every probe call goes through the SAME `probe` callback (`make_probe_fn(case, seed=SEED)`,
    fully deterministic given `case`+`seed`) that the real `attribute_greedy_bisection` call for
    the same case used, so this reconstructs -- rather than approximates -- the real decision path.
    This trace is NEVER used to compute any reported accuracy number; `attribute_greedy_bisection`
    itself (called separately in `_run_band` above) is the sole source of every top1/top3/probes
    figure in this report.

    Ground truth for one split decision ("does reverting `probed_half` (plus whatever's already
    confirmed-reverted in `base`) recover a real, still-present regression?") is exactly:
    `true_culprit in probed_half` AND `true_culprit not in base` (once the true culprit has
    already been found and reverted in an earlier round, no further real effect remains to find,
    so every subsequent decision's ground truth is "not significant").

    Classification:
      - "correct": `decision_significant == ground_truth_significant`.
      - "mode_a_detection_power_failure": ground truth says a real recovery effect WAS present in
        `probed_half`, but the CI failed to exclude the threshold (`marginal_ci_lo <= threshold`)
        -- a genuine effect the estimator could not detect at this trial count.
      - "mode_b_false_positive_noise": ground truth says NO real recovery effect was present, but
        the CI crossed the threshold anyway (`marginal_ci_lo > threshold`) -- sampling noise
        producing a false-positive significant result.
    """
    decisions: list[BisectionDecision] = []
    remaining = list(changed_tools)
    base: frozenset[str] = frozenset()
    base_delta = 0.0

    while remaining:
        candidates = list(remaining)
        while len(candidates) > 1:
            mid = len(candidates) // 2
            half_a, half_b = candidates[:mid], candidates[mid:]
            r = probe(base | frozenset(half_a))
            marginal_delta = r.delta - base_delta
            marginal_ci_lo = r.ci_lo - base_delta
            decision_significant = marginal_ci_lo > threshold
            ground_truth_significant = true_culprit in half_a and true_culprit not in base
            if decision_significant == ground_truth_significant:
                classification = "correct"
            elif ground_truth_significant and not decision_significant:
                classification = "mode_a_detection_power_failure"
            else:
                classification = "mode_b_false_positive_noise"
            decisions.append(
                BisectionDecision(
                    case_id=case_id,
                    probed_half=tuple(half_a),
                    marginal_delta=marginal_delta,
                    marginal_ci_lo=marginal_ci_lo,
                    decision_significant=decision_significant,
                    ground_truth_significant=ground_truth_significant,
                    classification=classification,
                )
            )
            candidates = half_a if decision_significant else half_b

        culprit_candidate = candidates[0]
        final = probe(base | frozenset({culprit_candidate}))
        marginal_delta = final.delta - base_delta
        marginal_ci_lo = final.ci_lo - base_delta
        decision_significant = marginal_ci_lo > threshold
        ground_truth_significant = culprit_candidate == true_culprit and true_culprit not in base
        if decision_significant == ground_truth_significant:
            classification = "correct"
        elif ground_truth_significant and not decision_significant:
            classification = "mode_a_detection_power_failure"
        else:
            classification = "mode_b_false_positive_noise"
        decisions.append(
            BisectionDecision(
                case_id=case_id,
                probed_half=(culprit_candidate,),
                marginal_delta=marginal_delta,
                marginal_ci_lo=marginal_ci_lo,
                decision_significant=decision_significant,
                ground_truth_significant=ground_truth_significant,
                classification=classification,
            )
        )
        if not decision_significant:
            break  # mirrors _bisect_within returning None -> outer loop breaks
        remaining = [t for t in remaining if t != culprit_candidate]
        base = base | frozenset({culprit_candidate})
        base_delta = final.delta + base_delta

    return decisions


def _investigate_mechanism(label: str, min_pp: float, max_pp: float, seed: int) -> dict[str, Any]:
    """For every case in this band, first checks for the IMPLEMENTATION-LEVEL finding this study
    surfaced (`attribute_greedy_bisection`/`_bisect_within`'s total-search-failure fallback: see
    `reports/v0_5_effect_size_sensitivity.md`'s "implementation finding" section) -- then, for
    every case where the REAL `attribute_greedy_bisection` missed top-1, re-derives the decision
    trace and tallies which CI-detection failure mode dominates."""
    cases = generate_benchmark(
        n_cases=N_CASES_PER_BAND, seed=seed, effect_min_pp=min_pp, effect_max_pp=max_pp
    )
    mode_a = 0
    mode_b = 0
    n_miss_cases = 0
    n_miss_cases_with_any_mode_a = 0
    n_miss_cases_with_any_mode_b = 0
    examples: list[str] = []
    # Implementation finding: whenever `_bisect_within`'s first call on the full changed-tool set
    # returns None (fails to confirm ANY candidate), attribute_greedy_bisection (a) silently drops
    # every probe spent in that call from `probes_consumed` (real work, uncounted) and (b) discards
    # all elim_scores gathered during the failed search, defaulting every remaining tool to a flat
    # 0.0 -- Python's stable sort then returns candidates in their original `changed_tools` order,
    # so the "ranked" top-1 becomes `changed_tools[0]` regardless of any signal actually observed.
    n_zero_probe_cases = 0
    n_zero_probe_pred_is_position0 = 0
    n_zero_probe_hits = 0

    for case in cases:
        probe_fn = make_probe_fn(case, seed=SEED)
        real_result = attribute_greedy_bisection(case.changed_tools, probe_fn)
        if real_result.probes_consumed == 0:
            n_zero_probe_cases += 1
            if real_result.ranked and real_result.ranked[0].tool_name == case.changed_tools[0]:
                n_zero_probe_pred_is_position0 += 1
            if top_k_hit(real_result, case.true_culprit, 1):
                n_zero_probe_hits += 1
        if top_k_hit(real_result, case.true_culprit, 1):
            continue
        n_miss_cases += 1

        # Fresh, deterministic probe_fn -- identical draws to the one `real_result` used above,
        # since make_probe_fn's ground-truth model is a pure function of (case, seed, subset).
        trace_probe_fn = make_probe_fn(case, seed=SEED)
        trace = trace_greedy_bisection_decisions(
            case.changed_tools, trace_probe_fn, case.true_culprit, case.case_id
        )
        case_has_mode_a = any(d.classification == "mode_a_detection_power_failure" for d in trace)
        case_has_mode_b = any(d.classification == "mode_b_false_positive_noise" for d in trace)
        mode_a += sum(1 for d in trace if d.classification == "mode_a_detection_power_failure")
        mode_b += sum(1 for d in trace if d.classification == "mode_b_false_positive_noise")
        if case_has_mode_a:
            n_miss_cases_with_any_mode_a += 1
        if case_has_mode_b:
            n_miss_cases_with_any_mode_b += 1
        if len(examples) < 3:
            steps = "; ".join(
                f"probed={d.probed_half} marginal_delta={d.marginal_delta:+.4f} "
                f"marginal_ci_lo={d.marginal_ci_lo:+.4f} sig={d.decision_significant} "
                f"truth={d.ground_truth_significant} -> {d.classification}"
                for d in trace
            )
            examples.append(f"{case.case_id} (true_culprit={case.true_culprit}): {steps}")

    return {
        "label": label,
        "n_cases": len(cases),
        "n_miss_cases": n_miss_cases,
        "n_decisions_mode_a": mode_a,
        "n_decisions_mode_b": mode_b,
        "n_miss_cases_with_any_mode_a": n_miss_cases_with_any_mode_a,
        "n_miss_cases_with_any_mode_b": n_miss_cases_with_any_mode_b,
        "examples": examples,
        "n_zero_probe_cases": n_zero_probe_cases,
        "n_zero_probe_pred_is_position0": n_zero_probe_pred_is_position0,
        "n_zero_probe_hits": n_zero_probe_hits,
    }


def main() -> None:
    print("=== Unit conversion (confirmed) ===")
    print(
        f"spec-agentgauge-v0.5.md's headline 'MDE 0.0537 at n=253' is a FRACTION on [0,1] "
        f"(agentgauge.harness.simulate_mde_task_level's return convention) == "
        f"{DOCTRINE_MDE_PP_AT_N253} on this repo's signed _pp scale "
        f"(agentgauge.attribution_benchmark.CAUSAL_EFFECT_MIN_PP/MAX_PP, "
        f"agentgauge.attribution.ProbeResult.delta * 100.0). The requested '0.03 to 0.30' fraction "
        f"sweep is this module's '3.0 to 30.0' _pp range."
    )

    print("\n=== Probe-regime MDE sanity check (n_tasks=24, this benchmark's actual probe budget) ===")
    t0 = time.time()
    naive_mde_frac = simulate_mde_task_level(n_tasks=24, power=0.8, n_simulations=1000, seed=SEED)
    print(f"simulate_mde_task_level(n_tasks=24, power=0.8) = {naive_mde_frac:.4f} "
          f"({naive_mde_frac * 100:.2f}pp) in {time.time() - t0:.1f}s")
    print(
        "CAVEAT: this uses the SAME paired+CUPED+cluster-bootstrap machinery as "
        "make_probe_fn/diff_server_level, calibrated to the same constants, but WITHOUT the "
        "few-clusters t-adjusted-CI correction diff_server_level actually applies for "
        "n_tasks_matched < 30 (harness._FEW_CLUSTERS_THRESHOLD=30; this benchmark's n_tasks=24 "
        "is below it). It is therefore a LOWER BOUND on the true probe-regime MDE, not an exact "
        "figure -- the doctrine's own headline '5.37pp at n=253' is measured at a >10x larger "
        "trial count and is NOT the number directly governing this benchmark's probes."
    )
    print(f"CALIBRATED_BASELINE_RATE = {CALIBRATED_BASELINE_RATE}")

    print(f"\n=== Per-band accuracy / budget (n={N_CASES_PER_BAND} cases/band, seed per band) ===")
    band_results: list[BandResult] = []
    for label, min_pp, max_pp, seed in EFFECT_BANDS:
        t0 = time.time()
        result = _run_band(label, min_pp, max_pp, seed)
        band_results.append(result)
        print(f"\n--- {label} (true effect in [{min_pp}, {max_pp}]pp, seed={seed}) ---")
        if result.confound_guard_findings:
            print("AUDIT/GUARD FINDINGS (should be empty):")
            for f in result.confound_guard_findings:
                print(f"  BLOCK: {f}")
        else:
            print(
                "Confound guard + audit: PASS (no blocking findings), mean culprit fractional "
                f"rank = {result.mean_culprit_fractional_rank:.4f}"
            )
        header = f"{'method':24s} {'top1':>7s} {'top3':>7s} {'mean_probes':>12s}"
        print(header)
        for name in STRATEGY_NAMES:
            print(
                f"{name:24s} {result.top1[name]:7.2%} {result.top3[name]:7.2%} "
                f"{result.mean_probes[name]:12.2f}"
            )
        print(f"({time.time() - t0:.1f}s)")

    print("\n=== Ship-bar check per band (top1 >= 0.70 AND top3 >= 0.90), probe-based strategies ===")
    for result in band_results:
        for name in ("greedy_bisection", "sampled_shapley"):
            clears = result.top1[name] >= SHIP_BAR_TOP1 and result.top3[name] >= SHIP_BAR_TOP3
            print(
                f"{result.label:26s} {name:18s} top1={result.top1[name]:.2%} "
                f"top3={result.top3[name]:.2%} -> {'CLEARS' if clears else 'does not clear'}"
            )

    print("\n=== Mechanism investigation: greedy_bisection top-1 misses ===")
    for label, min_pp, max_pp, seed in EFFECT_BANDS:
        t0 = time.time()
        mech = _investigate_mechanism(label, min_pp, max_pp, seed)
        print(
            f"\n--- {label}: {mech['n_miss_cases']}/{mech['n_cases']} cases missed top-1 "
            f"({time.time() - t0:.1f}s) ---"
        )
        print(
            f"IMPLEMENTATION FINDING: {mech['n_zero_probe_cases']}/{mech['n_cases']} cases had "
            f"probes_consumed==0 (total search failure on the first _bisect_within call); of "
            f"those, {mech['n_zero_probe_pred_is_position0']}/{mech['n_zero_probe_cases']} "
            f"predicted exactly changed_tools[0], and {mech['n_zero_probe_hits']}/"
            f"{mech['n_zero_probe_cases']} happened to hit top-1 by pure positional luck"
        )
        if mech["n_miss_cases"] == 0:
            print("(no misses -- nothing to investigate)")
            continue
        print(
            f"decision-level tally across all miss cases: "
            f"mode_a (detection-power failure) = {mech['n_decisions_mode_a']}, "
            f"mode_b (false-positive noise) = {mech['n_decisions_mode_b']}"
        )
        print(
            f"case-level: {mech['n_miss_cases_with_any_mode_a']}/{mech['n_miss_cases']} miss "
            f"cases show >=1 mode_a decision; {mech['n_miss_cases_with_any_mode_b']}/"
            f"{mech['n_miss_cases']} show >=1 mode_b decision"
        )
        for ex in mech["examples"]:
            print(f"  EXAMPLE: {ex}")


if __name__ == "__main__":
    main()
