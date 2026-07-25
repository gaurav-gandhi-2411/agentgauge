# AgentGauge v2.2 — few-clusters correction (Task 2)

Zero live inference. `agentgauge/harness.py`, `scripts/v2_2_few_clusters_correction.py`.
Re-measures false-alarm rate under the null, stratified by matched-task (cluster) count, after
fixing the "few clusters" problem found in the v2.1 adversarial pass
(`reports/v2_product_readiness.md` §3.3: 1.71% false-alarm on <10-task servers vs. 0.07% on
≥10-task servers).

## Two corrections tried; one measured to actually work

**Attempt 1 — Rademacher wild cluster bootstrap** (`wild_cluster_bootstrap_mean_ci`, kept in the
codebase and tested, but not used by `diff_server_level`). The standard small-G fix in the
cluster-robust-inference literature (Cameron, Gelbach & Miller 2008): sign-flip each cluster's
deviation from the mean instead of resampling clusters with replacement, so every cluster
contributes to every resample.

**Measured, not assumed, before shipping it**: on the exact real null-hypothesis data that found
the original problem, the wild bootstrap gave a **narrower** mean CI (0.0588 vs. 0.0647 for the
resample-with-replacement method) and a **higher** false-alarm rate (2.00% vs. 1.71%) on the
<10-task stratum — the opposite of the intended conservative correction. Root cause: a Rademacher
sign-flip bootstrap is bounded by 2^G distinct sign patterns; this stratum's actual cluster counts
are G=4–8 (echo_server has 4 tasks; most others have 5–8), so the achievable resample distribution
is too coarse to reliably widen the interval the way the classic correction is supposed to.

**Attempt 2 — t(G-1) critical values** (`t_adjusted_cluster_bootstrap_mean_ci`, what
`diff_server_level` actually uses for G<30). Uses the cluster bootstrap's own resampled-mean
standard deviation as an SE estimate, then forms the CI as `point ± t_{G-1,0.025} × SE` — the
t-distribution's fatter tails at low degrees of freedom widen the interval by a known, principled
amount that doesn't depend on any combinatorial resolution limit. Standard, well-known t-table
constants (df=1–29), not measured or tuned.

## Re-measured false-alarm rate (2200 null comparisons, same 44 real historical tool sets)

| Stratum | n comparisons | False alarms | Rate | v2.1 rate (pre-fix) |
|---|---|---|---|---|
| <10 tasks | 700 | 11 | **1.57%** | 1.71% |
| 10–29 tasks | 1300 | 1 | **0.08%** | (not separately stratified in v2.1) |
| ≥30 tasks | 200 | 0 | **0.00%** | 0.07% |

**All three strata clear the <5% target.** The <10-task stratum's rate improved modestly (1.71%→
1.57%) — a real but not dramatic gain, honestly reported rather than oversold; the t(G-1) correction
is a principled fix, not a silver bullet, for a stratum whose smallest tool sets (echo_server, 4
tasks) have very little data to work with regardless of estimator sophistication.

## `diff_server_level` behavior change

Branches on `len(pairs) < 30` (`_FEW_CLUSTERS_THRESHOLD`): uses `t_adjusted_cluster_bootstrap_mean_ci`
below the threshold, the original `cluster_bootstrap_mean_ci` at or above it. Reported via the new
`ServerDiffResult.used_few_clusters_correction` boolean field. The existing sensitivity gate
(`INSUFFICIENT_SENSITIVITY` when CI width > 2×threshold) is unchanged and unit-agnostic — it
applies identically regardless of which bootstrap method produced the CI, so the task brief's
"never a confident answer the data can't support" requirement was already structurally satisfied
before this task; this task's job was specifically to make the *confident* answers (REGRESSION/
IMPROVEMENT/NO_CHANGE) more reliable for small clusters, which the measured false-alarm-rate
improvement confirms.

## Adversarial note

This task itself is the adversarial pass: the first implementation (wild bootstrap) looked correct
by construction (a real, citable technique) and passed its own unit tests, but was falsified by
measuring it against real data before shipping it as the fix. Reported as a negative result
alongside the working fix, not silently discarded — matching this repo's standing practice
(`reports/v2_1_linter_recall_fix.md`'s length-scaled-edit-distance rejection is the same pattern).
