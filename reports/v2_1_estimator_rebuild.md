# AgentGauge v2.1 — estimator rebuild (Tasks 2–3)

Consolidates the harness redesign driven by `reports/v2_variance_structure.md`'s Task 1 findings
(ICC=0.793 within task, 56.1% of variance between tasks, rho=0.881 before/after task correlation).
Implementation: `agentgauge/harness.py` (new functions alongside the unmodified v2 trial-level
ones). Scripts: `scripts/v2_1_mde_ablation.py`, `scripts/v2_1_false_alarm_new_estimator.py`.

## Task 2 — what was built

- **2a. Paired design, common random numbers** (`pair_tasks_common_random_numbers`): matches
  before/after arms on `task_tool_name` — one row per task, not per trial. Unmatched tasks
  (present in only one arm) are returned explicitly, never silently dropped.
- **2b. Correct unit of analysis** (`cluster_bootstrap_mean_ci`, `diff_server_level`): resamples at
  the TASK level (the cluster Task 1b showed carries 56.1% of variance), reporting one verdict per
  server, not per tool set fragment.
- **2c. CUPED** (`cuped_adjust`): covariate-adjusts each task's delta using its own before-arm mean
  as the covariate (`theta = Cov(before, delta) / Var(before)`), preserving the point estimate by
  construction while reducing variance.
- **2d. Sequential testing** (`simulate_sequential_expected_n`): O'Brien-Fleming alpha-spending
  efficacy boundary (cumulative alpha calibrated via the standard Lan-DeMets formula, hardcoded for
  alpha=0.05) plus a non-binding futility stop (disclosed simplification: reuses the efficacy CI's
  width rather than a separate beta-spending schedule).

## Task 3 — re-derived MDE table (server level, paired + CUPED)

| n_tasks/arm | power | v2 baseline (trial-level) | +task-level unpaired | +paired | +paired+CUPED |
|---|---|---|---|---|---|
| 5 | 80% | 0.711 | 0.608 | 0.366 | 0.336 |
| 5 | 95% | 0.750 | 0.775 | 0.530 | 0.485 |
| 10 | 80% | 0.598 | 0.441 | 0.263 | 0.254 |
| 10 | 95% | 0.692 | 0.556 | 0.353 | 0.335 |
| 20 | 80% | 0.433 | 0.313 | 0.191 | **0.188** |
| 20 | 95% | 0.537 | 0.382 | 0.253 | 0.240 |
| 50 | 80% | 0.273 | 0.198 | 0.121 | 0.119 |
| 50 | 95% | 0.355 | 0.239 | 0.161 | 0.155 |

**Ablation reading:** moving to a task-level unit of analysis (ignoring pairing) already buys a
~28% MDE reduction at n=20/80% power (0.433→0.313) — this alone is "free", a direct consequence of
Task 1a's finding that trial-level repeats add almost no information, so counting the real unit
(tasks) rather than the inflated one (trials) tightens the estimate. Pairing buys the largest
further reduction (0.313→0.191, ~39% relative) — expected given rho=0.881. **CUPED buys very
little on top of pairing** (0.191→0.188 at n=20, ~2% relative) — pairing already captures nearly
all the removable task-level variance that CUPED's before-arm covariate could otherwise explain;
CUPED is not "earning its keep" as a large independent contributor here, though it is never worse
than pairing alone.

**Ship target: detect a 10-point (0.10) regression at 80% power with <=20 tasks/arm — NOT MET.**
Measured MDE at n=20/80% power is 0.188, a gap of 0.088 (47% further variance reduction still
needed). This is reported as a real, measured gap — the 2.3x improvement over the v2 baseline
(0.433→0.188) is real and substantial, but does not reach the stated target. What would close the
gap: more tasks per server (the table shows continued but diminishing returns — n=50/80% power
reaches 0.119, still short); a covariate stronger than the before-arm mean for CUPED; or accepting
a lower power target (95%→80% already assumed) or a larger detectable-regression threshold.

## Task 3c — false-alarm re-verification (new estimator, real historical data)

Same methodology as the original v2 false-alarm test (bootstrap-resample each of 44 real tool
sets' own trial pools into two independent samples, 50 repeats each = 2200 null comparisons), now
using `diff_server_level` (paired + task-clustered + CUPED) instead of `diff_from_trials`.

| Metric | v2 (trial-level) | v2.1 (paired + CUPED) |
|---|---|---|
| False-alarm rate under the null | 0.00% (0/2200) | **0.59%** (13/2200) |
| INSUFFICIENT_SENSITIVITY (abstention) rate | 71.5% | **21.6%** |
| Confident NO_CHANGE rate | 28.5% | **77.8%** |

Both estimators clear the <5% false-alarm target. The new estimator trades a small, still-passing
increase in false alarms for a much more decisive harness (abstains 3.3x less often). **The
false-alarm rate is not uniform across tool-set sizes** — stratifying the 13 false alarms by task
count: tool sets with <10 tasks show 1.71% (12/700), tool sets with >=10 tasks show 0.07% (1/1500).
This is the well-documented "few clusters" problem in cluster-robust bootstrap inference (fewer
clusters → less reliable CI coverage) — not a uniform defect, and not previously visible in the v2
estimator's trial-level design (which never clustered by task at all). Practical implication: this
harness's false-alarm guarantee is strongest for servers with >=10 distinct tasks; smaller catalogs
should expect a higher (though still <2%, still passing) false-alarm rate.

## Task 3d — determinism

Not independently re-measured for the new estimator in this pass (the underlying `_lcg_random`
mechanism is unchanged and already verified deterministic at 100%/50 runs in the v2 measurement,
`reports/v2_harness_evaluation.md` §3d) — the new estimator's bootstrap resampling uses the same
deterministic PRNG, so this is inherited, not re-verified from scratch. Flagged here as ASSUMED,
not separately MEASURED, per the doctrine's honesty requirement.

## Task 3e — sensitivity reporting

Unchanged mechanism from v2 (`reports/v2_harness_evaluation.md` §3e): `diff_server_level` emits
`INSUFFICIENT_SENSITIVITY` with an explicit message when the CI is wider than 2x the threshold,
never a bare point estimate. The RW1-confound fix this exists for is preserved.

## Adversarial pass — a real bug found and fixed, and a modeling check that held

While building the Task 3 cross-check tooling, `bootstrap_delta_ci`'s LCG-saturation indexing bug
was found and fixed (see `reports/v2_product_readiness.md` §3.1, carried over from the prior Task
7 pass — the fix is in the same `agentgauge/harness.py` this rebuild extends, so it is inherited by
every v2.1 function that calls `bootstrap_delta_ci`/`cluster_bootstrap_mean_ci`'s shared resampling
pattern). The new `cluster_bootstrap_mean_ci` function was written with the same `min(idx, n-1)`
clamp from the start, so it never had this bug independently.
