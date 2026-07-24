# AgentGauge v2.5 — Task 3: complete the MDE grid at the full corpus

v2.4 Task 4 left n=200 and n=252 unmeasured to exact precision ("still
computing when this report was finalized" — `reports/v2_4_task4_corpus_expansion.md`).
This task finishes the grid at the full, Task-2-validated corpus (253 tasks,
not 252 — the GitHub Issues fix added one task; no fixture was removed, so
none of the corpus shrinks).

## Result

`agentgauge.harness.simulate_mde_task_level`, calibrated constants
(`CALIBRATED_BASELINE_RATE`/`CALIBRATED_SIGMA_TASK`/`CALIBRATED_RESID_SD`/
`CALIBRATED_RHO`, unchanged from v2.2), `trials_per_task=1` (the Task 1
optimal allocation), 80% power, `n_simulations=2000` — identical settings to
the already-reported 62/100/150 cells, only `n_tasks` varies:

| n_tasks | MDE (80% power) | Status |
|---|---|---|
| 62 (pre-expansion ceiling) | 0.1061 | Above the 0.10 ship target |
| 100 | 0.0848 | Clears the ship target |
| 150 | 0.0689 | — |
| 200 | **0.0605** (measured this task, 613.1s) | — |
| 253 (full corpus) | **0.0537** (measured this task, 722.9s) | — |

`scripts/mde_grid_v2_5.py` — deterministic (`seed=42`, no LLM calls, no
network I/O), reproducible by re-running the same script; the 62/100/150
cells are not recomputed here since re-running a fully deterministic
simulation on unchanged inputs would reproduce the identical float, not new
information (see the script's own docstring for this reasoning).

## Headline claim

**The 10-point ship target is met, and by a wide margin at the full corpus
size.** MDE=0.0537 at n=253 is roughly half the 0.10 threshold — the harness
can now reliably detect a 5.4-point regression at 80% power using the full
task pool, not just a 10-point one. This was already true at n=100
(MDE=0.0848, established in v2.4); this task's contribution is completing
the precision picture across the full achievable range and confirming the
monotonic-decrease property holds all the way to the corpus ceiling, not
just at the previously-measured points.

## What this does and does not establish (MEASURED vs NOT MEASURED)

**MEASURED**: the achievable MDE at every grid point from 62 to 253 tasks,
using the real (Task-2-validated, no known factual defects) 253-task corpus.
The ship target is cleared at n=100 and every larger n on the grid.

**NOT MEASURED (unchanged from v2.4's own scope note, still open)**: what
the argument-degradation cross-model effect size actually IS at this
allocation. This task establishes achievable *statistical power*, not a new
*live measurement* — no new LLM inference was run. The natural next step
(re-running the argument-degradation cross-model comparison at the 100- or
253-task allocation) remains outside this task's scope, exactly as it was
left in v2.4's own "what this does and does not establish" section.

## Independent verification

A separate verifier agent independently re-ran `scripts/mde_grid_v2_5.py`
from scratch (fully deterministic on `seed=42`, so exact reproduction is
the correct verification method here, not a second methodology). Took two
attempts: the first two runs stalled without producing a final report — a
subagent-tooling issue (it kept re-checking its own long-running background
job rather than reading the completed result), not evidence against the
computation itself, so a third resume was sent with an explicit instruction
to check the completed output. That attempt completed cleanly.

**Result: CONFIRMED on all 5 checked items, no discrepancies:**

1. **Determinism, verified by code inspection**: `harness.py` imports no
   `random`/`numpy`; every stochastic draw flows through the single
   `_lcg_random(seed)` closure (hand-rolled LCG,
   `state = (1103515245*state + 12345) & 0x7FFFFFFF`), reseeded only from
   values deterministically derived from that same LCG stream — never from
   `time.time()` or OS entropy. Aggregation is over fixed-order `list`s, not
   `set`/`dict` iteration, so floating-point summation order is stable.
2. **Reproduced values, exact match**: `n_tasks=200 → MDE=0.0605` (547.9s),
   `n_tasks=253 → MDE=0.0537` (701.2s) — identical to the claimed values to
   the printed 4-decimal precision.
3. **Calibration constants, unchanged**: `git log -p -- agentgauge/harness.py`
   shows `CALIBRATED_BASELINE_RATE`/`CALIBRATED_SIGMA_TASK`/
   `CALIBRATED_RESID_SD`/`CALIBRATED_RHO` were all set once, in commit
   `fc149ba` (v2.1's estimator rebuild), and never touched by any commit
   since — independently cross-checked against `0.7749`/`0.881` as quoted in
   `reports/v2_product_readiness.md` and `reports/v2_1_estimator_rebuild.md`.
   No silent recalibration to produce a more favorable number.
4. **Monotonicity holds**: 0.0537 (n=253) < 0.0605 (n=200) < 0.0689 (n=150)
   < 0.0848 (n=100) < 0.1061 (n=62) — strictly decreasing, as expected of a
   correctly functioning estimator.
