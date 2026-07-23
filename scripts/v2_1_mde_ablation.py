"""Task 3 (v2.1): re-derive the MDE table under the new estimator, at the
SERVER (task-clustered) level, with an ablation breakdown showing each of
Task 2's components' individual contribution.

Zero live inference -- pure simulation via agentgauge.harness, calibrated to
Task 1's measured variance structure (reports/v2_variance_structure.md).

Ablation stages (each isolates one additional component):
  1. baseline        -- v2's original trial-level, unpaired estimator
                         (already measured in reports/v2_harness_evaluation.md;
                         cited here, not recomputed, for direct comparison)
  2. +task-level      -- move to task-level unit of analysis (Task 2b), still
                         treating before/after as independent samples
  3. +paired          -- add pairing on task / common random numbers (Task 2a)
  4. +CUPED           -- add covariate adjustment on top of pairing (Task 2c)

Sequential testing (Task 2d) is reported separately as expected sample size
under the null and under a 10-point regression, not as an MDE-at-fixed-n row
(a sequential design's headline output is "how many tasks until a decision",
not "MDE at n").
"""

from __future__ import annotations

import json
from pathlib import Path

from agentgauge.harness import simulate_mde_task_level, simulate_sequential_expected_n

OUT_PATH = Path("evals/fixtures/v2_1_mde_ablation.json")

# Cited from reports/v2_harness_evaluation.md Table 3b (baseline=0.75, the
# original v2 trial-level estimator) -- not recomputed here, since that
# estimator's code and its measured numbers are unchanged in this rebuild.
V2_BASELINE_MDE = {
    (5, 0.80): 0.711,
    (5, 0.95): 0.750,
    (10, 0.80): 0.598,
    (10, 0.95): 0.692,
    (20, 0.80): 0.433,
    (20, 0.95): 0.537,
    (50, 0.80): 0.273,
    (50, 0.95): 0.355,
}

N_TASKS_CELLS = [5, 10, 20, 50]
POWER_CELLS = [0.80, 0.95]
SHIP_TARGET_N = 20
SHIP_TARGET_MDE = 0.10
SHIP_TARGET_POWER = 0.80


def main() -> None:
    rows = []
    print(
        f"{'n_tasks':>8} {'power':>6} {'baseline(v2)':>13} {'+task-level':>12} {'+paired':>9} {'+CUPED':>8}"
    )
    for n_tasks in N_TASKS_CELLS:
        for power in POWER_CELLS:
            baseline = V2_BASELINE_MDE[(n_tasks, power)]

            mde_task_level_unpaired = simulate_mde_task_level(
                n_tasks=n_tasks,
                power=power,
                n_simulations=1000,
                seed=42,
                use_paired=False,
                use_cuped=False,
            )
            mde_paired = simulate_mde_task_level(
                n_tasks=n_tasks,
                power=power,
                n_simulations=1000,
                seed=42,
                use_paired=True,
                use_cuped=False,
            )
            mde_paired_cuped = simulate_mde_task_level(
                n_tasks=n_tasks,
                power=power,
                n_simulations=1000,
                seed=42,
                use_paired=True,
                use_cuped=True,
            )

            row = {
                "n_tasks": n_tasks,
                "power": power,
                "mde_v2_baseline_trial_level": baseline,
                "mde_task_level_unpaired": mde_task_level_unpaired,
                "mde_paired": mde_paired,
                "mde_paired_cuped": mde_paired_cuped,
            }
            rows.append(row)
            print(
                f"{n_tasks:>8} {power:>6.0%} {baseline:>13.3f} {mde_task_level_unpaired:>12.3f} "
                f"{mde_paired:>9.3f} {mde_paired_cuped:>8.3f}"
            )

    ship_row = next(
        r for r in rows if r["n_tasks"] == SHIP_TARGET_N and r["power"] == SHIP_TARGET_POWER
    )
    ship_mde = ship_row["mde_paired_cuped"]
    ship_met = ship_mde <= SHIP_TARGET_MDE
    print(
        f"\nSHIP TARGET (detect a {SHIP_TARGET_MDE:.0%} regression at {SHIP_TARGET_POWER:.0%} power, "
        f"<= {SHIP_TARGET_N} tasks/arm): measured MDE = {ship_mde:.3f} -> "
        f"{'MET' if ship_met else 'NOT MET'}"
    )
    if not ship_met:
        gap = ship_mde - SHIP_TARGET_MDE
        print(f"Gap: {gap:.3f} (need {gap / ship_mde * 100:.0f}% further variance reduction)")

    print("\n=== Sequential testing (Task 2d): expected sample size ===")
    seq_null = simulate_sequential_expected_n(
        true_delta=0.0,
        look_schedule=(5, 10, 15, 20, 25, 30, 35, 40, 45, 50),
        n_simulations=1000,
        seed=42,
    )
    seq_10pt_regression = simulate_sequential_expected_n(
        true_delta=-0.10,
        look_schedule=(5, 10, 15, 20, 25, 30, 35, 40, 45, 50),
        n_simulations=1000,
        seed=42,
    )
    print(
        f"Under the null (true_delta=0): expected_n={seq_null['expected_n']:.1f}, "
        f"median_n={seq_null['median_n']}, "
        f"pct_unresolved_at_n_max={seq_null['pct_unresolved_at_n_max']:.1f}%, "
        f"verdicts={seq_null['verdict_counts']}"
    )
    print(
        f"Under a 10-point regression (true_delta=-0.10): expected_n={seq_10pt_regression['expected_n']:.1f}, "
        f"median_n={seq_10pt_regression['median_n']}, "
        f"pct_unresolved_at_n_max={seq_10pt_regression['pct_unresolved_at_n_max']:.1f}%, "
        f"verdicts={seq_10pt_regression['verdict_counts']}"
    )

    out = {
        "mde_ablation_table": rows,
        "ship_target": {
            "n_tasks": SHIP_TARGET_N,
            "power": SHIP_TARGET_POWER,
            "target_mde": SHIP_TARGET_MDE,
            "measured_mde": ship_mde,
            "met": ship_met,
        },
        "sequential": {
            "under_null": seq_null,
            "under_10pt_regression": seq_10pt_regression,
        },
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
