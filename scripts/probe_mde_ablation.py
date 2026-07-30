#!/usr/bin/env python3
"""Probe-level MDE ablation (v0.5 Wave 1.6, Task 2b).

Per `reports/v0_5_shapley_scaling_audit.md` / `reports/v0_5_mde_discrepancy.md`: the binding
constraint on failure attribution is per-probe MDE (>=16.91pp at n_tasks=24), not server-level MDE
(5.37pp at n_tasks=253). Wave 1.6 Task 2a found -- by reading the code, not assuming -- that
`agentgauge.attribution_benchmark.make_probe_fn`'s `probe()` ALREADY calls
`agentgauge.harness.diff_server_level` directly: the exact same paired + CUPED + task-clustered
(with the t(G-1) few-clusters correction, `diff_server_level`'s ACTUAL production behavior for
`n_tasks < 30` -- NOT the Rademacher wild-cluster-bootstrap correction, which
`reports/v2_2_few_clusters_correction.md` measured to make small-cluster coverage WORSE and is
implemented but never called by `diff_server_level`) estimator that produces the server-level
5.37pp headline. There is no missing variance-reduction component to "apply" to probes -- the
entire per-probe-vs-server-level MDE gap is explained by the sample-size difference (n_tasks=24 vs
253), consistent with the classic ~1/sqrt(n) MDE scaling law.

This script quantifies each component's contribution AT PROBE-RELEVANT TASK COUNTS
(n_tasks=12/24/48/96, matching `scripts/v2_1_mde_ablation.py`'s exact ablation-stage design, one
new stage added for the few-clusters correction which that script's original n_tasks cells (20/50)
never needed to isolate at n_tasks=20 since v2.2 postdated v2.1's rebuild):

  1. baseline (v1/v2 trial-level) -- `simulate_minimum_detectable_effect`: pure binomial trials,
     no task-clustering, no pairing, no CUPED. The historical starting point.
  2. +task-level, unpaired -- `simulate_mde_task_level(use_paired=False, use_cuped=False)`: moves
     the unit of analysis to one row per task (Task 1b's finding: repeat trials on the same task
     carry almost no information), still treating before/after as independent samples.
  3. +paired -- `simulate_mde_task_level(use_paired=True, use_cuped=False)`: adds common-random-
     numbers pairing on task identity (`pair_tasks_common_random_numbers`'s mechanism). This is
     where common random numbers (CRN) enters -- pairing IS this codebase's implementation of CRN,
     not a separate independent toggle (see report discussion).
  4. +CUPED -- `simulate_mde_task_level(use_paired=True, use_cuped=True)`: adds the before-arm
     covariate adjustment on top of pairing.
  5. +clustered (production) -- NOT available via `simulate_mde_task_level` (its own `_detects`
     never applies the few-clusters t-adjustment -- documented as a LOWER-BOUND caveat in
     `reports/v0_5_effect_size_sensitivity.md` section 0). This script adds a fifth stage that
     calls `agentgauge.harness.diff_server_level` DIRECTLY -- the exact function real probes call
     -- via a bisection-based MDE search, so this row is the true, current, shippable per-probe MDE,
     not an approximation of it.

Zero live LLM calls -- pure simulation via `agentgauge.harness`, calibrated to the same measured
constants (`CALIBRATED_BASELINE_RATE`/`CALIBRATED_SIGMA_TASK`/`CALIBRATED_RESID_SD`/
`CALIBRATED_RHO`) every other v0.5 attribution report uses.

Usage:
    uv run python scripts/probe_mde_ablation.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.harness import (
    CALIBRATED_BASELINE_RATE,
    TrialOutcome,
    _lcg_random,
    diff_server_level,
    simulate_mde_task_level,
    simulate_minimum_detectable_effect,
    simulate_task_level_pairs,
)

N_TASKS_CELLS = [12, 24, 48, 96]
POWER = 0.80
N_SIMULATIONS = 500  # reduced from the v2.1 ablation's 1000 for this wider n_tasks sweep's runtime
TARGET_MDE_PP = 8.0


def _detects_production(true_delta: float, n_tasks: int, rng, base_seed: int) -> bool:
    """The stage-5 detector: builds calibrated task pairs via the SAME
    `simulate_task_level_pairs` generator every other stage uses, then runs them through
    `agentgauge.harness.diff_server_level` -- the REAL function `make_probe_fn`'s probes call in
    production, few-clusters t-adjustment included automatically via its own `n_tasks < 30`
    branch. This is not a re-approximation of `diff_server_level`; it IS `diff_server_level`."""
    pairs = simulate_task_level_pairs(CALIBRATED_BASELINE_RATE, true_delta, n_tasks, rng)
    before = [TrialOutcome(f"t{i}", f"t{i}", b) for i, (b, _a) in enumerate(pairs)]
    after = [TrialOutcome(f"t{i}", f"t{i}", a) for i, (_b, a) in enumerate(pairs)]
    result = diff_server_level(before, after, n_resamples=300, seed=base_seed)
    return result.ci_hi < 0 if true_delta < 0 else result.ci_lo > 0


def mde_production(n_tasks: int, power: float, n_simulations: int, seed: int = 42) -> float:
    """Bisection-search MDE using `_detects_production` -- mirrors
    `agentgauge.harness.simulate_mde_task_level`'s own bisection loop exactly, just swapping in
    the production `diff_server_level` detector instead of that function's internal (non-few-
    -clusters-adjusted) one."""
    rng = _lcg_random(seed)
    lo, hi = 0.0, CALIBRATED_BASELINE_RATE
    for _ in range(12):
        mid = (lo + hi) / 2
        n_detected = sum(
            1 for i in range(n_simulations) if _detects_production(-mid, n_tasks, rng, seed + i)
        )
        detected_rate = n_detected / n_simulations
        if detected_rate >= power:
            hi = mid
        else:
            lo = mid
    return hi


def main() -> None:
    print(f"n_simulations={N_SIMULATIONS}, power={POWER:.0%}, seed=42\n")
    header = (
        f"{'n_tasks':>8} {'baseline(trial)':>16} {'+task-level':>12} {'+paired':>9} "
        f"{'+CUPED':>8} {'+clustered(prod)':>17}"
    )
    print(header)
    rows = []
    for n_tasks in N_TASKS_CELLS:
        t0 = time.time()
        baseline = simulate_minimum_detectable_effect(
            CALIBRATED_BASELINE_RATE, n_trials=n_tasks, power=POWER, n_simulations=N_SIMULATIONS
        )
        task_level_unpaired = simulate_mde_task_level(
            n_tasks=n_tasks,
            power=POWER,
            n_simulations=N_SIMULATIONS,
            use_paired=False,
            use_cuped=False,
        )
        paired = simulate_mde_task_level(
            n_tasks=n_tasks, power=POWER, n_simulations=N_SIMULATIONS, use_paired=True, use_cuped=False
        )
        paired_cuped = simulate_mde_task_level(
            n_tasks=n_tasks, power=POWER, n_simulations=N_SIMULATIONS, use_paired=True, use_cuped=True
        )
        clustered_prod = mde_production(n_tasks, POWER, N_SIMULATIONS)

        rows.append(
            {
                "n_tasks": n_tasks,
                "baseline_trial_level": baseline,
                "task_level_unpaired": task_level_unpaired,
                "paired": paired,
                "paired_cuped": paired_cuped,
                "clustered_production": clustered_prod,
            }
        )
        print(
            f"{n_tasks:>8} {baseline:>16.4f} {task_level_unpaired:>12.4f} {paired:>9.4f} "
            f"{paired_cuped:>8.4f} {clustered_prod:>17.4f}   ({time.time() - t0:.1f}s)"
        )

    print(f"\n=== Target: per-probe MDE <= {TARGET_MDE_PP}pp at power={POWER:.0%} (production estimator) ===")
    for row in rows:
        mde_pp = row["clustered_production"] * 100.0
        met = mde_pp <= TARGET_MDE_PP
        print(
            f"n_tasks={row['n_tasks']:>3}: production MDE = {mde_pp:.2f}pp -> "
            f"{'MET' if met else 'NOT MET'}"
            + (f" (gap: {mde_pp - TARGET_MDE_PP:.2f}pp)" if not met else "")
        )


if __name__ == "__main__":
    main()
