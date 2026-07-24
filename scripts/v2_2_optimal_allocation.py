"""Task 1 (v2.2): optimal trial/task allocation.

ICC=0.793 (reports/v2_variance_structure.md 1a) means repeat trials on the same
task carry almost no independent information. The design-effect formula
DEFF = 1 + (m-1)*ICC gives n_eff = n_tasks*trials_per_task / DEFF -- at fixed
total trial budget (n_tasks*trials_per_task), n_eff is maximized at
trials_per_task=1. This script simulates whether that theoretical prediction
translates into a materially better MDE in agentgauge's actual bootstrap-CI
estimator (not just the n_eff formula), across a realistic allocation grid.

Zero live inference -- pure simulation via agentgauge.harness, calibrated to
Task 1 (v2.1)'s measured variance structure.

Checkpointed after every grid cell (this repo's sessions have had background
processes killed/duplicated by the launch environment more than once) -- a
re-run picks up where the checkpoint left off rather than restarting.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentgauge.harness import (
    PairedTaskDelta,
    _lcg_random,
    cuped_adjust,
    simulate_mde_task_level,
    simulate_task_level_pairs,
)

OUT_PATH = Path("evals/fixtures/v2_2_optimal_allocation.json")

TRIALS_PER_TASK_GRID = [1, 2, 3, 5]
N_TASKS_GRID = [20, 50, 100, 150]
POWER_LEVELS = [0.80, 0.95]
SHIP_TARGET_MDE = 0.10
GRID_N_SIMULATIONS = 500  # exploratory grid -- faster, coarser
PRECISE_N_SIMULATIONS = 2000  # winning cell(s) -- slower, precise, for the headline number


def _design_effect(icc: float, m: int) -> float:
    return 1 + (m - 1) * icc


def measure_cuped_effectiveness(n_tasks: int, trials_per_task: int, n_sim: int = 2000) -> float:
    """1d: measure CUPED's actual variance-reduction percentage (not just
    "does it crash") at a given trials_per_task, using a single large
    simulated null-delta sample (mechanically identical to a real
    diff_server_level call's cuped_adjust step)."""
    rng = _lcg_random(123)
    pairs_raw = simulate_task_level_pairs(0.75, 0.0, n_sim, rng, trials_per_task=trials_per_task)
    pairs = [
        PairedTaskDelta(f"t{i}", b, a, a - b, trials_per_task, trials_per_task)
        for i, (b, a) in enumerate(pairs_raw)
    ]
    _, _, reduction_pct = cuped_adjust(pairs)
    return reduction_pct


def _load_state() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {"grid": [], "precise": {}, "cuped_effectiveness_by_trials_per_task": {}}


def _save_state(state: dict) -> None:
    OUT_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> None:
    print("=== 1a. MDE across the allocation grid ===")
    print(
        f"ICC=0.793 design-effect check: DEFF(m=5)={_design_effect(0.793, 5):.3f} "
        f"(n_eff for 20x5 = {20 * 5 / _design_effect(0.793, 5):.1f})"
    )

    state = _load_state()
    done_cells = {(r["trials_per_task"], r["n_tasks"], r["power"]) for r in state["grid"]}

    for power in POWER_LEVELS:
        print(f"\n--- power={power:.0%} ---")
        for trials in TRIALS_PER_TASK_GRID:
            for n_tasks in N_TASKS_GRID:
                key = (trials, n_tasks, power)
                if key in done_cells:
                    print(f"  [skip, checkpointed] trials={trials} tasks={n_tasks} power={power}")
                    continue
                mde = simulate_mde_task_level(
                    n_tasks=n_tasks,
                    power=power,
                    n_simulations=GRID_N_SIMULATIONS,
                    seed=42,
                    trials_per_task=trials,
                )
                total_trials = trials * n_tasks
                row = {
                    "trials_per_task": trials,
                    "n_tasks": n_tasks,
                    "power": power,
                    "total_trials_per_arm": total_trials,
                    "mde": mde,
                }
                state["grid"].append(row)
                _save_state(state)
                print(
                    f"  trials={trials:>3} tasks={n_tasks:>4} total={total_trials:>4} MDE={mde:.4f}"
                )

    grid_rows = state["grid"]

    print("\n=== 1b. Compute-optimal allocation (MDE<=0.10, 80% power) ===")
    candidates_80 = [r for r in grid_rows if r["power"] == 0.80 and r["mde"] <= SHIP_TARGET_MDE]
    if candidates_80:
        best = min(candidates_80, key=lambda r: r["total_trials_per_arm"])
        print(f"Cheapest grid cell meeting target: {best}")
    else:
        print("NO grid cell meets MDE<=0.10 at 80% power.")
        best = min((r for r in grid_rows if r["power"] == 0.80), key=lambda r: r["mde"])
        print(f"Closest cell: {best}")
    state["best_cell_meeting_target"] = best
    state["ship_target_mde"] = SHIP_TARGET_MDE
    _save_state(state)

    print("\n=== 1c. Precise re-measurement: 100 tasks x 1 trial vs 20 tasks x 5 trials ===")
    if "100x1" not in state["precise"]:
        mde_100x1 = simulate_mde_task_level(
            n_tasks=100, power=0.80, n_simulations=PRECISE_N_SIMULATIONS, seed=42, trials_per_task=1
        )
        state["precise"]["100x1"] = mde_100x1
        _save_state(state)
    print(
        f"MDE(100 tasks x 1 trial, 80% power) = {state['precise']['100x1']:.4f} (predicted ~0.092)"
    )

    if "20x5" not in state["precise"]:
        mde_20x5 = simulate_mde_task_level(
            n_tasks=20, power=0.80, n_simulations=PRECISE_N_SIMULATIONS, seed=42, trials_per_task=5
        )
        state["precise"]["20x5"] = mde_20x5
        _save_state(state)
    print(
        f"MDE(20 tasks x 5 trials, 80% power) = {state['precise']['20x5']:.4f} (same total budget: 100)"
    )

    ratio = (
        state["precise"]["20x5"] / state["precise"]["100x1"]
        if state["precise"]["100x1"] > 0
        else None
    )
    state["improvement_ratio"] = ratio
    _save_state(state)
    print(f"Improvement ratio: {ratio:.3f}x (predicted ~2.04x)")

    print("\n=== 1d. CUPED effectiveness vs trials_per_task ===")
    for trials in TRIALS_PER_TASK_GRID:
        key = str(trials)
        if key in state["cuped_effectiveness_by_trials_per_task"]:
            print(f"  [skip, checkpointed] trials_per_task={trials}")
            continue
        reduction = measure_cuped_effectiveness(50, trials)
        state["cuped_effectiveness_by_trials_per_task"][key] = reduction
        _save_state(state)
        print(f"  trials_per_task={trials}: CUPED variance reduction = {reduction:.2f}%")

    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
