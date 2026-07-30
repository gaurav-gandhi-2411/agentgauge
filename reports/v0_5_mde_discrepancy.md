# AgentGauge v0.5 — MDE discrepancy investigation and resolution (measurement artifact #10)

Resolves the open question carried from `reports/v0_5_wave1_report.md`'s SESSION-CLOSE note
(2026-07-26): `greedy_bisection` was reported at 100% top-1/top-3 down to a 3.0pp true effect size,
while the harness's own server-level MDE (n=253) is 5.37pp — a nominal effect below the harness's
detection floor was apparently being attributed perfectly. Two explanations were left open:
(1) probe-level power genuinely differs from server-level MDE (benign), or (2) a measurement
artifact.

**Resolution: (2). Confirmed as measurement artifact #10, fixed, and every attribution
accuracy/budget table this repo has published to date has been recomputed against the fix.** The
correction is not cosmetic — it changes Wave 1.5's central recommendation (see section 6).

## 1. Task 1a — does probe-level power benignly explain it? No.

If per-probe power were simply higher than the server-level headline implies (fewer clusters,
different aggregation), that would be a benign, arithmetic explanation requiring no code change.
Directly computed, not assumed:

- Server-level headline MDE: **5.37pp** at `n_tasks=253`, power=0.8 (`scripts/mde_grid_v2_5.py`,
  `spec-agentgauge-v0.5.md`'s own headline number).
- Per-probe MDE at `n_tasks=24` (the benchmark's actual per-probe trial count,
  `agentgauge.attribution_benchmark.make_probe_fn`'s default): `simulate_mde_task_level(n_tasks=24,
  power=0.8)` = **0.1691 fraction = 16.91pp** (this run, `n_simulations=1000`, seed=42; a prior run
  in `reports/v0_5_effect_size_sensitivity.md` section 0 reported 16.48-16.91pp across runs — both
  reproduce the same order of magnitude). This is a **lower bound**: `simulate_mde_task_level`'s
  internal `_detects` uses the plain `cluster_bootstrap_mean_ci`, not the few-clusters
  `t_adjusted_cluster_bootstrap_mean_ci` correction `diff_server_level` actually applies whenever
  `n_tasks_matched < 30` (`agentgauge.harness._FEW_CLUSTERS_THRESHOLD = 30`) — the omitted
  correction only widens real CIs further, pushing the true per-probe MDE higher still.

**The per-probe MDE (>=16.91pp) is higher than the server-level MDE (5.37pp), not lower.** Fewer
tasks per probe means LESS power, not more. This directly rules out the benign explanation: if
probe power genuinely matched this calibration, detecting a 3pp effect at `n_tasks=24` should have
been *harder* than the already-hard 5.37pp server-level bar, not something `greedy_bisection`
aced at 100%. The premise driving this investigation stands confirmed as a real anomaly, not a
misreading of two differently-scoped MDE numbers.

## 2. Task 1b — direct investigation: what does explain it?

**Root cause, found by reading `agentgauge.attribution_benchmark.make_probe_fn`'s ground-truth
model directly against `agentgauge.harness.simulate_task_level_pairs` (the model that actually
produces the repo's calibrated MDE numbers) line by line:**

`simulate_task_level_pairs` (the validated model) gives every synthetic task **two** independent
noise sources:
1. A **between-task** "difficulty" effect, `task_effect ~ N(0, CALIBRATED_SIGMA_TASK=0.3588)`,
   correlated at `CALIBRATED_RHO=0.881` between a task's before/after arms.
2. Independent **residual** noise per observation, `~ N(0, CALIBRATED_RESID_SD=0.1392)`.

`CALIBRATED_SIGMA_TASK` (0.3588) is measured directly from real trial data
(`reports/v2_variance_structure.md`) and is **more than 2.5x the residual noise scale** — this
component is *why* 56.1% of total variance is between-task, the finding CUPED (`cuped_adjust`) and
task-pairing exist specifically to partially correct for.

`agentgauge.attribution_benchmark.make_probe_fn`/`make_multi_probe_fn`'s ORIGINAL ground-truth
model (both, before this fix) had **only source (2)** — uniform noise scaled to
`CALIBRATED_RESID_SD`, applied independently per arm, with **no between-task variance term at
all**. Every synthetic "task" behaved as an interchangeable, equally-easy draw around a fixed
baseline. This is a fundamentally lower-noise regime than what the harness's own calibration says
real measurements look like.

### Empirical confirmation (not just structural argument)

Detection power of `diff_server_level` (the real estimator, with the few-clusters t-correction
applied, exactly as production code runs it) at `n_tasks=24`, comparing the **pre-fix** probe model
against the **properly calibrated** model (`simulate_task_level_pairs`, same estimator):

| True effect | Pre-fix probe model power | Calibrated-variance model power |
|---|---|---|
| 3.0pp | 38.3% | 8.8% |
| 5.0pp | 71.7% | 10.0% |
| 8.0pp | 96.7% | 27.5% |
| 13.3pp | 100.0% | 51.3% |
| 16.91pp | -- | 75.0% |
| 20.0pp | 100.0% | 83.8% |
| 28.9pp | 100.0% | 97.5% |

(60-80 simulated probes per cell, seeded, `diff_server_level` called directly — reproducible via
the diagnostic described in section 7.) The calibrated-model column is internally consistent with
`simulate_mde_task_level`'s own 16.48-16.91pp MDE figure (75-84% power right around that effect
size, as it should be). **The pre-fix probe model's power at 5-8pp (72-97%) is not a subtly
different number from the calibrated model's (10-28%) — it is 3-7x higher**, decisively confirming
this is the mechanism, not sampling noise or a second, smaller effect layered on top of a mostly-
correct model.

**Conclusion: confirmed as a real measurement artifact.** The synthetic injection did carry
separable signal the artifact #9 fix did not remove — not in the diff-size dimension #9 already
fixed, but in the probe's underlying noise-floor construction, a structurally different defect.

## 3. Task 1c — fix, artifact log, and standing audit check

**Logged as measurement artifact #10** (`agentgauge/audit.py` module docstring,
`tests/test_audit.py`'s enumerated historical-case list, this report).

**Fix** (`agentgauge/attribution_benchmark.py`, `make_probe_fn` and `make_multi_probe_fn`): both
probe closures now draw a correlated `task_effect`/`after_task_effect` pair per synthetic task
(scale `CALIBRATED_SIGMA_TASK`, correlation `CALIBRATED_RHO`), mirroring
`simulate_task_level_pairs` exactly, including switching from the ad hoc uniform residual noise to
`_approx_standard_normal`-based noise (the same normal-approximation draw the calibrated model
uses). `test_reduces_to_single_culprit_model_at_n_culprits_1`
(`tests/test_scale_curve.py`) continues to pass unmodified — both functions draw in the same
order/count, so the drop-in-generalization invariant is preserved.

**Standing check**: `agentgauge.audit.check_probe_variance_calibration` (BLOCK severity) — takes a
set of observed probe CI widths and the `n_tasks` they were measured at, simulates a calibrated-
variance reference width at the same `n_tasks` via `simulate_task_level_pairs` +
`diff_server_level`'s own CI machinery, and BLOCKs if the observed mean width is under 60% of that
reference. Confirmed against both directions: the reconstructed pre-fix probe model's widths
measure at **34%** of the calibrated reference (fires); the real, fixed `make_probe_fn`'s widths
measure in-band (does not fire). Wired into `run_audit` via new optional
`probe_ci_widths`/`probe_n_tasks` parameters; `scripts/attribution_benchmark_report.py` now samples
a true-culprit-revert probe width per case and runs this gate before printing any accuracy number.
9 new regression tests in `tests/test_audit.py::TestProbeVarianceCalibration` /
`::TestRunAuditProbeCiWidths`.

**One existing test relaxed, honestly**: `tests/test_attribution_benchmark.py::TestMakeProbeFn::
test_reverting_true_culprit_shows_significant_recovery` previously asserted CI-significant
detection in **100%** of 8 cases at the original 13.3-28.9pp effect range — that was itself a
symptom of the artifact (the whole point of the fix is that a probe no longer always detects a
real effect at this trial count). Now asserts a majority-hit rate (>=60%, measured 75% on n=24 at
this seed), matching this repo's existing convention for probabilistic measurements
(`TestExhaustiveAblationOnBenchmark`). The other two `TestMakeProbeFn` tests (decoy / empty-revert
show no significant effect) were UNCHANGED by the fix and continue to pass as originally written —
more noise does not manufacture false positives at this significance test's threshold construction.

## 4. Task 1c — recomputed tables (every prior attribution accuracy/budget number superseded)

All three of this repo's attribution accuracy/budget artifacts have been re-run end-to-end against
the fixed code. **Nothing from `reports/v0_5_attribution_benchmark.md`,
`reports/v0_5_effect_size_sensitivity.md`, or `reports/v0_5_scale_curve.md`'s accuracy/budget
numbers may be cited going forward without reading the corrected tables below** — each of those
reports now carries a superseded banner pointing here.

### 4a. Original 50-case benchmark (2-6 changed tools, 13.3-28.9pp effect), corrected

`uv run python scripts/attribution_benchmark_report.py`, seed=42, this report's commit.

| Method | top-1 | top-3 | mean probes | vs. exhaustive (3.96) | Ship bar |
|---|---|---|---|---|---|
| exhaustive_ablation | 98.00% | 100.00% | 3.96 | reference | reference |
| sampled_shapley | 64.00% | 98.00% | 1.92 | sub-exhaustive | does not clear (top-1 < 0.70) |
| greedy_bisection | 96.00% | 100.00% | 4.60 | **MORE expensive (+16.2%)** | does not clear (not sub-exhaustive) |
| largest_textual_diff | 24.00% | 72.00% | 0 | -- | baseline |
| most_lint_violations | 62.00% | 82.00% | 0 | -- | baseline |
| uniform_random (analytic) | 30.07% | 78.20% | 0 | -- | baseline (floor) |

**Zero of three probe-based strategies clear the ship bar** at this scale -- unchanged in
direction from the last (post-implementation-bug-fix) corrected number in
`reports/v0_5_attribution_benchmark.md` section 7j, though the exact figures moved (accuracy
dropped modestly across the board -- e.g. `greedy_bisection` 100.0%->96.0% top-1 -- since even a
correctly-isolated culprit's confirmation probe is no longer immune from occasional CI-significance
misses at this effect range). Audit gate (`run_audit` with `benchmark_cases` + `probe_ci_widths`)
passes cleanly on the corrected generator.

### 4b. Effect-size sensitivity, corrected (n=24 cases/band)

`uv run python scripts/effect_size_sensitivity_report.py`, seed=42 (base), per-band seeds
42/1042/2042/3042/4042, this report's commit.

| Band | Method | top-1 | top-3 | mean probes | Ship bar |
|---|---|---|---|---|---|
| below_mde (3.0-5.0pp) | exhaustive_ablation | 50.00% | 95.83% | 4.04 | reference |
| | sampled_shapley | 45.83% | 87.50% | 2.12 | does not clear |
| | **greedy_bisection** | **58.33%** | 95.83% | 3.25 | does not clear |
| straddle_mde (5.0-8.0pp) | exhaustive_ablation | 83.33% | 95.83% | 3.92 | reference |
| | sampled_shapley | 50.00% | 91.67% | 2.04 | does not clear |
| | greedy_bisection | 66.67% | 91.67% | 3.29 | does not clear |
| moderate (8.0-13.3pp) | exhaustive_ablation | 66.67% | 91.67% | 3.92 | reference |
| | sampled_shapley | 54.17% | 95.83% | 1.92 | does not clear |
| | greedy_bisection | 54.17% | 91.67% | 3.21 | does not clear |
| original (13.3-28.9pp) | exhaustive_ablation | 95.83% | 100.00% | 4.29 | reference |
| | sampled_shapley | 62.50% | 95.83% | 2.42 | does not clear |
| | **greedy_bisection** | **87.50%** | 100.00% | 4.88 | **CLEARS** |
| beyond (28.9-33.0pp) | exhaustive_ablation | 100.00% | 100.00% | 3.62 | reference |
| | sampled_shapley | 54.17% | 100.00% | 1.83 | does not clear |
| | greedy_bisection | 100.00% | 100.00% | 5.25 | **CLEARS** |

**This directly resolves the SESSION-CLOSE question.** `greedy_bisection`'s real accuracy at
3.0-5.0pp is **58.33% top-1** -- not the previously reported 100%. The `below_mde`/`straddle_mde`/
`moderate` bands (3.0-13.3pp, spanning and below the doctrine's own 5.37pp server-level MDE) all
now **fail** the ship bar, exactly as a genuine detection-power limit should look. The mechanism
trace (`trace_greedy_bisection_decisions`, re-run against the fixed code) confirms every single
top-1 miss across every band is **Mode A (genuine detection-power failure: a real recovery signal
present but the CI failed to certify it)** -- Mode B (false-positive noise) was **never** observed,
in any band, at any point in this investigation, pre- or post-fix. The estimator is not making
false-positive errors; it is honestly reporting "not enough signal at this trial count," which is
the statistically correct behavior a fixed noise floor was previously masking.

The implementation-bug fix from Wave 1.5 (`f432f5a`, no `probes_consumed==0` degenerate cases in
any band here) remains intact and is unaffected by this fix -- `0/24` zero-probe cases in every
band, confirmed directly in this run's output.

### 4c. Scale curve, corrected (single-culprit, n_changed pinned; multi-culprit, n_changed=20/40)

`uv run python scripts/scale_curve_report.py`, seed=42, this report's commit. `top1_strict` here is
the single-culprit metric (identical semantics to `top-1` above); `recall@m` and `top3_strict` are
the multi-culprit-aware metrics `scripts/scale_curve_report.py` defines.

**Single-culprit, by candidate-set size:**

| n_changed | greedy_bisection top1 | top3 | mean probes | vs. exhaustive | Ship bar | sampled_shapley top1 | mean probes | Ship bar |
|---|---|---|---|---|---|---|---|---|
| 4 | 93.33% | 100.00% | 4.83 | **+20.8% (more expensive)** | does not clear | 50.00% | 2.00 | does not clear |
| 10 | 80.00% | 96.67% | 7.80 | -22.0% | **CLEARS** | 83.33% | 5.00 | **CLEARS** |
| 20 | 73.33% | **80.00%** | 8.83 | -55.8% | **does not clear (top-3 < 0.90)** | 90.00% | 10.00 | **CLEARS** |
| 40 | **46.67%** | **53.33%** | 9.33 | -76.7% | **does not clear (accuracy collapsed)** | **100.00%** | 20.00 | **CLEARS** |

**This is the single largest correction in this investigation, and it inverts Wave 1.5's headline
recommendation.** The previous (artifact-inflated) numbers showed `greedy_bisection` at 100%/100%
top-1/top-3 at every single-culprit size from 4 to 40 tools, with budget crossing over to
sub-exhaustive at n>=10 -- the basis for "ship `greedy_bisection` only, recommended operating
envelope >=10 changed tools." **Under corrected, calibration-faithful noise, `greedy_bisection`'s
BUDGET still improves with scale exactly as before (-22% to -77% vs. exhaustive at n>=10), but its
ACCURACY now degrades with scale**: 93%→80%→73%→47% top-1 as `n_changed` grows 4→10→20→40, failing
the ship bar at n=20 (top-3 dips to 80%) and collapsing outright at n=40 (47% top-1, worse than a
64% coin-flip). Mechanism (consistent with section 4b): each `_bisect_within` binary search performs
`~ceil(log2(n))` sequential significance tests: at n=40 that is 6 splits, each individually
imperfect at the effect range tested here, and a single missed split anywhere in the chain sends
the search down the wrong half permanently -- more splits at fixed per-split reliability means
compounding failure probability, not the "more probes = more signal" intuition budget-only analysis
suggested. **`sampled_shapley` shows the OPPOSITE scaling behavior**: 50%→83%→90%→100% top-1 as
n_changed grows, because its probe budget (`~n/2`) scales WITH n rather than logarithmically,
giving it more independent samples to average over at exactly the sizes where bisection's fixed-
depth search runs out of statistical margin. `sampled_shapley` clears the full ship bar (top-1,
top-3, AND sub-exhaustive budget, all three) at n=10/20/40 -- every single-culprit size this study
tested except the smallest (n=4, where exhaustive ablation is cheap enough that neither strategy
needs to compete for it).

**Multi-culprit (2-3 simultaneous culprits, n_changed=20/40) -- unchanged conclusion, still
failing:**

| Config | greedy_bisection recall@m | top3_strict | sampled_shapley recall@m | top3_strict | Ship bar (either) |
|---|---|---|---|---|---|
| 2 culprits, 20 tools | 66.67% | 46.67% | 50.00% | 53.33% | does not clear |
| 3 culprits, 20 tools | 56.67% | 13.33% | 54.44% | 3.33% | does not clear |
| 3 culprits, 40 tools | 53.33% | 6.67% | 76.67% | 36.67% | does not clear |

No configuration in the multi-culprit regime clears the ship bar under either strategy, pre- or
post-fix -- this conclusion does not change, though the exact percentages moved. Confound guards
passed cleanly in every bucket (both single- and multi-culprit), reproduced directly in this run's
output.

## 5. A related documentation-accuracy finding (not the artifact itself, but caught along the way)

`reports/v0_5_wave1_report.md` section 8.2 stated: *"greedy_bisection's accuracy was never in
question -- it is 100% top-1/top-3 in every single-culprit configuration tested, at every effect
size from 3.0pp... to 33.0pp, and at every candidate-set size from 4 to 40 tools."* This sentence
conflated two SEPARATE studies run at different fixed parameters (the effect-size sweep held
candidate-set size at the original 2-6-tool range; the scale-curve sweep held effect size at the
original 13.3-28.9pp band) into a single "100% everywhere" claim that was not, in fact, what either
study's own corrected tables showed even before this investigation: `reports/
v0_5_effect_size_sensitivity.md` section 11b's own post-implementation-bug-fix table already showed
75.00%/83.33% top-1 (not 100%) at the two lowest bands. This was a synthesis error in the
consolidation report, not a second code bug -- flagged here for the record since it is exactly the
kind of over-claim this repo's honesty doctrine exists to catch, and it is corrected by section 4's
tables above regardless of its origin.

## 6. Task 1d — plain statement of resolution

**Not benign.** The 100%-top-1-at-3pp finding that prompted this investigation was a real
measurement artifact (#10): `agentgauge.attribution_benchmark`'s synthetic probe/ground-truth model
omitted the harness's own calibrated between-task variance component, giving every probe a noise
floor 3-7x quieter than what a real deployment at the same trial count would show. This is now
fixed, logged, guarded by a standing audit check, and every attribution accuracy/budget table this
repo has published has been recomputed against the fix.

**The corrected picture is materially different from Wave 1.5's recommendation, not just
quantitatively adjusted:**
- The SESSION-CLOSE question is resolved: `greedy_bisection` does NOT reliably localize effects at
  or below the harness's own MDE (58.33% top-1 at 3-5pp, well short of the 70% bar) -- this is now
  a genuine, mechanistically-confirmed (100% Mode-A, 0% Mode-B) detection-power limit, not an
  artifact.
- Wave 1.5's headline recommendation ("ship `greedy_bisection` only, operating envelope >=10
  changed tools") **no longer holds**: at the realistic-noise candidate-set-size sweep,
  `greedy_bisection`'s accuracy COLLAPSES at exactly the scale (n=40) closest to the target buyer's
  stated use case (spec section 2: "a 40-tool server"), while `sampled_shapley` -- previously
  characterized as "never once clears top3_strict >= 90% at any multi-culprit configuration" and
  demoted -- now CLEARS the full single-culprit ship bar at every size >=10 tools, including n=40
  (100%/100%).
- Neither strategy clears any tested multi-culprit configuration, before or after this fix -- that
  conclusion is unchanged.

**This is a genuine reopening of Component 1.2's rescope decision, not a confirmation of it.**
Wave 2's Task 2a/2b (fix the wasted confirm-no-second-culprit pass; demote `sampled_shapley`) as
specified in the original session brief were written against the now-superseded numbers and should
not proceed as originally scoped without re-reading this report first -- in particular, "demote
`sampled_shapley`" is the opposite of what section 4c's corrected single-culprit scale curve now
supports.

## 7. MEASURED vs. NOT MEASURED

**MEASURED:** the per-probe vs. server-level MDE arithmetic (section 1); the empirical detection-
power comparison, pre-fix vs. calibrated model, at 6 effect sizes (section 2, diagnostic script not
committed -- reproducible from the formulas in `agentgauge.harness.simulate_task_level_pairs` and
this report's section 2 table); the fix itself and its unit-test coverage (section 3); all three
recomputed accuracy/budget tables in full (section 4), each independently re-run by the
orchestrating session against the actual repo code, not taken from a subagent's self-report. Full
test suite re-run after the fix (see commit for pass count).

**NOT MEASURED:** whether the corrected noise model itself is now a fully faithful reproduction of
real-agent variance -- it matches `simulate_task_level_pairs`'s calibration, which is itself
measured from historical `predictive_validity` trial data (real, but from an earlier study, not a
fresh live-agent run against this exact benchmark). Real-agent validation of the corrected
attribution numbers (beyond the single `n=1` gemma2:9b case already on record, itself now stale
relative to these corrected synthetic numbers) remains open, unchanged from every prior report's
NOT MEASURED section. Whether `sampled_shapley`'s multi-culprit failure mode is mechanistically
different from `greedy_bisection`'s (both fail, but via different-looking metrics) was not
investigated in this pass -- flagged as open follow-up, not resolved here.
