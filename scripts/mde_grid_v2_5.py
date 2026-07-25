from __future__ import annotations

"""v2.5 Task 3: complete the MDE grid at the full 253-task corpus, filling in
the n=200 and n=253 cells that v2.4 Task 4 left unmeasured. Same estimator,
same calibrated constants, same trials_per_task=1 allocation, same
n_simulations=2000 as the already-reported 62/100/150 cells
(reports/v2_4_task4_corpus_expansion.md) -- only n_tasks changes, so results
are directly comparable to those three.

62/100/150 are NOT recomputed here: `simulate_mde_task_level` is fully
deterministic (seed=42, no LLM calls, no external I/O) -- re-running it on an
unchanged n_tasks/power/n_simulations/trials_per_task tuple reproduces the
exact same float, so doing so would only burn ~15 minutes of CPU to confirm
what determinism already guarantees. New corpus size is 253 (was 252): the
v2.5 Task 2 GitHub Issues fix added one task (state_reason='duplicate'
coverage), so 200 stays on the grid unchanged but the top cell moves from
252 -> 253.

Run: uv run python scripts/mde_grid_v2_5.py
"""

import time

from agentgauge.harness import simulate_mde_task_level

GRID = [200, 253]
POWER = 0.80
N_SIMULATIONS = 2000

if __name__ == "__main__":
    print(f"MDE grid, power={POWER}, n_simulations={N_SIMULATIONS}, trials_per_task=1")
    for n_tasks in GRID:
        t0 = time.time()
        mde = simulate_mde_task_level(
            n_tasks=n_tasks, power=POWER, n_simulations=N_SIMULATIONS, trials_per_task=1
        )
        elapsed = time.time() - t0
        print(f"n_tasks={n_tasks:4d}  MDE={mde:.4f}  ({elapsed:.1f}s)", flush=True)
