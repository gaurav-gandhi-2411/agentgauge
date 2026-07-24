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

A separate verifier agent is re-running `scripts/mde_grid_v2_5.py`
independently to confirm 0.0605/0.0537 are reproducible (this script is
fully deterministic on `seed=42`, so an independent re-run reproducing the
exact same floats is the correct verification method here — not a second,
different methodology). Results appended once it returns.
