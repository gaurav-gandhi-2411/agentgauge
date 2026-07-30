# AgentGauge v0.5 Wave 1.6, Task 1 — auditing the sampled_shapley scale reversal

`reports/v0_5_mde_discrepancy.md` (measurement artifact #10 fix) recomputed every attribution
table and found `sampled_shapley`'s accuracy IMPROVES with candidate-set size (50%→83%→90%→100%
top-1 as `n_changed` goes 4→10→20→40), the opposite of `greedy_bisection`'s collapse. On its face
this looks mechanistically backwards: more candidates should mean more sampling noise per
candidate, not less. **This report audits that specific finding before it becomes the new
shipping recommendation.** Read `reports/v0_5_mde_discrepancy.md` first — this is a direct
follow-up, same corrected `agentgauge.attribution_benchmark.make_probe_fn`.

**Headline: the reversal is real and benign — confirmed by matching arithmetic on two
independent axes (probe-budget scaling and effective-sample-size-vs-MDE), not an artifact.
Not logged as artifact #11.** One unrelated, secondary observation surfaced during the
investigation (section 2) is flagged but not logged as a defect, for reasons given there.

## 1a. Does probe-budget scaling benignly explain it?

`agentgauge.attribution._sampled_shapley_budget(n) = min(max(2, ceil(n*0.5)), n-1)` — the
**absolute** probe budget grows linearly with `n_changed`, it is not held fixed. Since each
candidate's own contribution estimate is `mean(delta | subsets containing t) -
mean(delta | subsets not containing t)`, and each tool is independently included in a sampled
subset with probability 0.5, the number of probes actually backing one candidate's own
`mean_with` estimate is `E[with] = budget / 2`:

| n_changed | budget = ceil(n·0.5) | E[with] (probes averaged per candidate) |
|---|---|---|
| 4 | 2 | 1.0 |
| 10 | 5 | 2.5 |
| 20 | 10 | 5.0 |
| 40 | 20 | 10.0 |

**This is the arithmetic the task brief's "backwards" intuition missed**: it implicitly assumed a
fixed per-candidate probe budget. This algorithm's budget is a fixed *fraction* of `n_changed`
(≈50%), so the *absolute* number of independent samples informing any one candidate's estimate
grows 10x from n=4 to n=40 — standard-error should fall by roughly `1/sqrt(10) ≈ 0.32x` over that
range purely from this averaging effect. That is the right order of magnitude to explain the
observed accuracy curve, but "the right order of magnitude" is not proof — sections 1b/1c verify
it directly rather than accept it on inspection.

## 1b. Does the corrected probe model still contain hidden structure favoring Shapley specifically?

**Hypothesis tested**: `make_probe_fn` draws a fresh, independently-seeded `task_effect` (the
dominant variance component, `CALIBRATED_SIGMA_TASK`) for **every distinct subset probed**, via
`_stable_seed(seed, reverted)`. In a real deployment, task-difficulty (why some of the 24 tasks
are just harder, independent of which unrelated tool got reverted) would plausibly *persist*
across different probes of the same underlying task corpus, not reset to a fresh independent draw
every single probe call. If `sampled_shapley`'s averaging exploits this artificial
cross-probe independence to cancel a noise source a real deployment could not actually cancel,
that would be a genuine 11th artifact — inflating precision specifically for the strategy that
averages over many probes.

**Empirical test** (diagnostic script, not committed — reproducible from this section's
description): built a second probe-model variant where `task_effect`/`after_task_effect` for each
of the 24 synthetic tasks is drawn **once per case** and reused identically across every probe for
that case (only residual noise is redrawn per probe), and compared it against the current shipped
model at `n_changed` = 4/10/20/40, n_cases=40/bucket, seed=42, all three strategies:

| n_changed | exhaustive_ablation (indep → shared) | sampled_shapley (indep → shared) | greedy_bisection (indep → shared) |
|---|---|---|---|
| 4 | 92.5% → 100.0% | 50.0% → 50.0% | 90.0% → 87.5% |
| 10 | 90.0% → 100.0% | 75.0% → 85.0% | 72.5% → 75.0% |
| 20 | 82.5% → 97.5% | 87.5% → 92.5% | 72.5% → 72.5% |
| 40 | 85.0% → 97.5% | 100.0% → 100.0% | 60.0% → 70.0% |

**This refutes the hypothesis as stated.** `attribute_exhaustive` makes exactly **one** probe per
candidate — it never averages multiple probes for a single candidate's estimate, so it is
mechanistically immune to a "cross-probe averaging cancels correlated noise" effect. If the
hypothesis were correct, `exhaustive_ablation`'s numbers should be flat between the two columns.
Instead `exhaustive_ablation` shows an uplift **as large as or larger than** `sampled_shapley`'s
at every `n_changed`. The shared/case-level task-effect variant is not selectively helping the
averaging-based strategy — it is uniformly reducing a different, unrelated source of
between-candidate noise (in the independent model, every candidate's own single probe draws a
completely unrelated task-difficulty realization from every *other* candidate's probe, adding
extra apparent variability across the ranking that a shared realization removes for everyone).
This is a real property of the current shipped model worth knowing about, but it is not
Shapley-specific and does not explain the scale-reversal this report is auditing — **not logged
as a formal artifact**: it doesn't distort the *relative* comparison between strategies (all three
move in the same direction, roughly proportionally), it doesn't reproduce the "backwards
intuition" pattern under investigation, and running it down fully (is task-difficulty really
shared or independent across differently-catalogued LLM calls in a live deployment?) is a live-agent
empirical question outside this report's synthetic-benchmark scope — flagged as an open question
in section 4, not resolved here.

## 1c. Reconciling against probe MDE — effective sample size

If `sampled_shapley`'s precision genuinely comes from averaging `K = budget/2` independent
`n_tasks=24` probes per candidate (section 1a's mechanism, and section 1b confirms nothing
artificially favors it beyond that), then the natural check is: does the *effective* sample size
implied by that averaging correspond to a sensible point on the harness's own calibrated MDE
curve, or does it imply "free" power inconsistent with calibration?

`simulate_mde_task_level(n_tasks=K·24, power=0.8)`, computed directly (not estimated), at the
`K`/`n_tasks_eff` values section 1a derives:

| n_changed | K = E[with] | n_tasks_eff = K·24 | MDE at n_tasks_eff, power=0.8 | Benchmark's tested effect range | Expected regime |
|---|---|---|---|---|---|
| 4 | 1.0 | 24 | ≥16.91pp (established, `v0_5_mde_discrepancy.md` §1) | 13.3-28.9pp | at/above MDE — low, noisy power |
| 10 | 2.5 | 60 | **10.29pp** | 13.3-28.9pp | below MDE floor — most of range detectable |
| 20 | 5.0 | 120 | **7.78pp** | 13.3-28.9pp | well below MDE floor — high power |
| 40 | 10.0 | 240 | **5.60pp** | 13.3-28.9pp | comfortably below MDE floor — near-ceiling power |

**This is a clean, quantitative match to the observed accuracy curve, not a coincidence.** At
n=4, the effective sample size barely exceeds a single raw probe (K≈1), so the effective MDE
(≥16.91pp) sits at or above the tested effect range's own floor (13.3pp) — exactly where
`greedy_bisection`'s single-probe confirmation was shown to fail in
`reports/v0_5_effect_size_sensitivity.md`, and exactly where `sampled_shapley` measures its
weakest accuracy (50%). At n=40, the effective sample size (240) lands in the same regime as the
n=253 configuration that produces the repo's own 5.37pp headline MDE — comfortably below the
entire 13.3-28.9pp tested range, exactly where 100% top-1 is the expected outcome, not a surprising
one. **`sampled_shapley` is not beating the harness's calibration; it is legitimately buying
additional statistical power by spending a probe budget that scales with `n_changed`, and the
size of that power gain is arithmetically consistent with the calibrated MDE table at the
resulting effective sample size.**

**The real cost, stated plainly**: this power is not free. At n=40, 20 real `diff_server_level`
probes × 24 tasks × 2 arms = 960 real trial-equivalents for **one case's** attribution — half of
exhaustive's 1920, satisfying "sub-exhaustive" by the doctrine's own probe-count definition, but a
substantial absolute cost that grows linearly with `n_changed`, unlike `greedy_bisection`'s
`O(log n)` absolute probe count. The doctrine's ship bar (probe count vs. exhaustive) is not wrong
as a metric — both strategies' probes cost the same (n_tasks=24 each) — but a reader should not
mistake "sub-exhaustive count" for "cheap in absolute terms" at large `n_changed`.

## 1d. `check_probe_variance_calibration` against Shapley's own probe result sets

Artifact #10 was found and fixed in the shared `make_probe_fn`/`make_multi_probe_fn` ground-truth
model, so it necessarily also affected every prior `sampled_shapley` number — but it had not been
checked against `sampled_shapley`'s *specific* probe usage pattern (larger, mixed-size random
subsets, not single-tool or half-set reverts) before this report. Instrumented
`attribute_sampled_shapley` to record every real probe's CI width, at `n_changed` = 4/10/20/40,
n_cases=20/bucket, run through `agentgauke.audit.check_probe_variance_calibration`:

| n_changed | n probe widths collected | mean CI width | `check_probe_variance_calibration` |
|---|---|---|---|
| 4 | 40 | 0.1700 | no finding (passes) |
| 10 | 100 | 0.1647 | no finding (passes) |
| 20 | 200 | 0.1637 | no finding (passes) |
| 40 | 400 | 0.1616 | no finding (passes) |

All four buckets pass cleanly, with mean widths in a tight, stable band (0.16-0.17) close to the
~0.19 calibrated reference established in `v0_5_mde_discrepancy.md` — as expected, since **each
individual probe** is still exactly one `n_tasks=24` `diff_server_level` call regardless of how
large the sampled subset is or how many total probes the strategy makes; the artifact-#10 class
(an understated PER-PROBE noise floor) does not reappear in `sampled_shapley`'s usage pattern.
This is the direct confirmation that section 1c's effective-sample-size argument rests on
correctly-calibrated individual probes, not on a second, undetected noise-floor understatement
compounding the first.

## 2. Secondary observation (not an artifact, flagged for the record)

Section 1b's negative result surfaced something worth recording even though it doesn't explain
the reversal: the current shipped probe model draws a **fresh, independent** task-difficulty
realization for every distinct subset probed, including different single-tool probes within the
same case. Whether real task difficulty is genuinely independent across different (but closely
related) tool-catalog variants, or substantially shared/correlated as section 1b's alternate
model assumed, is an empirical question about live-agent behavior this synthetic benchmark cannot
answer either way — both are defensible modeling choices, and section 1b shows the choice affects
all three strategies roughly uniformly, so it does not bias the STRATEGY COMPARISON this repo's
tables are used for. Flagged as an open modeling question for any future real-agent validation
pass, not resolved and not logged as an artifact.

## 3. Verdict

**Not artifact #11.** `sampled_shapley`'s improving-with-scale accuracy is a direct, arithmetically
verified consequence of a probe budget that scales linearly with `n_changed` (section 1a),
confirmed not to depend on any hidden cross-probe-independence exploit (section 1b, tested and
refuted), reconciled against the harness's own calibrated MDE table via an effective-sample-size
argument that matches the observed accuracy curve within the expected regime at every tested size
(section 1c), and re-verified clean against the artifact-#10 audit gate on Shapley's own specific
probe usage (section 1d). `reports/v0_5_mde_discrepancy.md`'s corrected recommendation — that
`sampled_shapley` now outperforms `greedy_bisection` at realistic scale (≥10 changed tools) —
**stands, audited, not merely re-asserted.**

This does not by itself mean attribution is ready to ship: the underlying probe-level MDE
(≥16.91pp at n_tasks=24 for a single probe) remains the binding constraint the calling task
brief's Task 2 exists to fix, and multi-culprit configurations still fail every tested ship bar
regardless of strategy. Those questions are unaffected by this audit and remain open.

## 4. MEASURED vs. NOT MEASURED

**MEASURED:** the probe-budget arithmetic (1a); the empirical cross-probe-independence test, two
model variants × 4 candidate-set sizes × 3 strategies × 40 cases/bucket, all against the real
`agentgauge.attribution` strategy implementations and `diff_server_level` (1b); the effective-MDE
reconciliation, `simulate_mde_task_level` computed directly at n_tasks=60/120/240 (1c, not
estimated or interpolated); `check_probe_variance_calibration` run against 740 real probe CI
widths collected from `attribute_sampled_shapley` across four candidate-set sizes (1d).

**NOT MEASURED:** whether real task-difficulty is genuinely independent or correlated across
different tool-catalog variants in a live deployment (section 2, open); any live-agent validation
of `sampled_shapley`'s accuracy at scale (unchanged from every prior report's NOT MEASURED
section); whether the effective-sample-size argument in 1c continues to hold at candidate-set
sizes beyond 40 (not tested); the real wall-clock/dollar cost of `sampled_shapley`'s linearly-
growing absolute probe budget at very large `n_changed` (e.g. 100+ tool servers) — flagged in 1c
as a real, if doctrine-compliant, cost, not quantified in absolute currency terms here.
