# AgentGauge v2.2 — optimal trial/task allocation (Task 1)

Zero live inference. `agentgauge/harness.py` (`trials_per_task` parameter added to
`simulate_task_level_pairs`/`simulate_mde_task_level`), `scripts/v2_2_optimal_allocation.py`.

## The hypothesis

ICC=0.793 (`reports/v2_variance_structure.md` 1a) means repeat trials on the same task carry
almost no independent information. The design-effect formula `DEFF = 1 + (m-1)·ICC` gives
`n_eff = n_tasks·m / DEFF` — at a fixed total trial budget, n_eff is maximized at m=1 (trials per
task). The v2.1 ship-target gap (MDE=0.188 at n=20 tasks/arm vs. a 0.10 target) was hypothesized to
be a budget-allocation problem, not a fundamental limit: the same 100 trials spent as 20 tasks × 5
trials (n_eff≈24) vs. 100 tasks × 1 trial (n_eff=100) should give a ~2.04× MDE improvement
(`√(100/24) ≈ 2.04`, since MDE scales roughly as `1/√n_eff` under the naive normal-theory
approximation).

## 1a. MDE across the allocation grid

Full 32-cell grid (`{1,2,3,5} trials/task × {20,50,100,150} tasks/arm`, 80%/95% power):
`evals/fixtures/v2_2_optimal_allocation.json`. 80%-power slice:

| trials/task | tasks/arm | total trials/arm | MDE |
|---|---|---|---|
| 1 | 20 | 20 | 0.182 |
| 1 | 50 | 50 | 0.121 |
| **1** | **100** | **100** | **0.085** |
| 1 | 150 | 150 | 0.070 |
| 2 | 20 | 40 | 0.153 |
| 2 | 50 | 100 | 0.097 |
| 2 | 100 | 200 | 0.072 |
| 3 | 20 | 60 | 0.141 |
| 3 | 50 | 150 | 0.089 |
| 5 | 20 | 100 | 0.132 |
| 5 | 50 | 250 | 0.084 |
| 5 | 100 | 500 | 0.061 |

At every fixed total-trial budget, `trials_per_task=1` gives the best (lowest) MDE — the
prediction holds directionally across the entire grid, not just at one cell.

## 1b. Compute-optimal allocation meeting MDE≤0.10 at 80% power

**100 tasks/arm × 1 trial/task = 100 total trials/arm. Measured MDE = 0.085.** This is the
cheapest grid cell clearing the target — no cell with a smaller total-trial budget clears 0.10 at
80% power (the next cheapest passing cells are 50 tasks × 5 trials = 250 total, MDE=0.084, and
100 tasks × 2 trials = 200 total, MDE=0.072 — both cost more total trials for a similar or worse
MDE than 100×1).

**This closes the v2.1 ship-target gap.** The harness CAN detect a 10-point regression at 80%
power — the earlier "NOT MET" verdict (`reports/v2_1_estimator_rebuild.md`) was measured at n=20
tasks/arm, an allocation this task shows was never going to work regardless of trials/task,
because 20 tasks alone (n_eff≤20) is short of what ~100 independent task-level observations buys.

## 1c. Precise re-measurement: prediction confirmed directionally, refuted on magnitude

At `n_simulations=2000` (4× the grid's 500, for a stable headline number):

| Allocation | Total trials/arm | MDE (80% power) |
|---|---|---|
| 100 tasks × 1 trial | 100 | **0.0848** |
| 20 tasks × 5 trials | 100 (same budget) | 0.1313 |

**Improvement ratio: 1.55×** (0.1313/0.0848), not the predicted ~2.04×.

**Confirmed:** the direction and rough magnitude of the prediction — 100×1 is substantially better
than 20×5 at identical total cost, and its absolute MDE (0.085) is close to the naive prediction of
~0.092 computed from the n_eff ratio alone.

**Refuted:** the exact 2.04× multiplier. The naive prediction assumes MDE scales as `1/√n_eff`
under a clean normal-theory model with no other moving parts. The actual simulated estimator has
two additional effects the simple formula doesn't capture: (1) CUPED's own variance reduction is
folded into every cell (both 100×1 and 20×5 use it, per the actual `diff_server_level` pipeline),
and (2) the MDE is found via a bootstrap-CI binary search, not a closed-form calculation — it
inherits whatever finite-sample behavior the bootstrap has, not a clean asymptotic. The measured
1.55× is the number to use going forward; the 2.04× was a useful first approximation for
prioritizing the search, not a value to report as measured.

## 1d. CUPED and pairing still work at 1 trial/task — confirmed, not just assumed

The concern: CUPED's covariate is the before-arm task mean; at trials_per_task=1, that mean is a
single noisy observation, not an average — does the covariate still carry useful signal?

**Measured CUPED variance-reduction percentage vs. trials_per_task** (n_tasks=50, fixed, only
trials_per_task varied):

| trials_per_task | CUPED variance reduction |
|---|---|
| **1** | **13.1%** |
| 2 | 9.4% |
| 3 | 8.0% |
| 5 | 6.9% |

**CUPED does not break at trials_per_task=1 — it is measurably the MOST effective there**, not the
least. Mechanism: CUPED's reduction comes from the before-arm value predicting the task's stable
difficulty effect (Task 1's own 1c/rho=0.881 finding); a single noisy trial still carries that
signal, and averaging more trials per task doesn't add proportionally more of it once the
task-level effect itself is already well-represented in the covariate. No re-optimization under a
"CUPED needs ≥N trials" constraint was needed — the constraint doesn't exist at the trials_per_task
values tested.

## Default configuration updated

`agentgauge/cli.py`'s `eval` and `diff` commands: `--trials` default changed from 5 to **1**, with
updated help text pointing at this report and recommending ~100 tasks in the user's `--tasks` file
for a reliable regression gate. The lever that matters is task-set size, not trials-per-task
repetition.
