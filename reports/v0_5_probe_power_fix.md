# AgentGauge v0.5 Wave 1.6, Task 2 — fixing probe power, and what it costs

Follow-up to `reports/v0_5_mde_discrepancy.md` (measurement artifact #10) and
`reports/v0_5_shapley_scaling_audit.md` (Task 1: confirmed the Shapley scale-reversal is real and
benign). Binding constraint identified there: per-probe MDE ≥16.91pp at `n_tasks=24`, well above
both the harness's own server-level MDE (5.37pp at n=253) and the 8pp accuracy target this task
sets. This report fixes probe power (2a-2d) and then asks the decisive question the calling task
brief named explicitly: **does fixing accuracy also fix the economics, or does it break them?**

**Headline: accuracy is fixed. Economics is not — it gets categorically worse.** At the smallest
`n_tasks` that clears the requested ≤8pp MDE target (128), **every single tested attribution
configuration costs more than simply re-running the full 253-task evaluation from scratch** — the
cheapest case (`sampled_shapley` at 4 changed tools) is already 1.01x a full re-eval; every larger
or multi-culprit configuration is 2x-20x more expensive. There is no crossover point in the tested
range where attribution beats the thing it exists to make unnecessary. See section 5 before
reading any accuracy number below as good news on its own.

## 1. Task 2a — the premise is corrected, not the code

The calling task brief states probes "do not currently inherit" the server-level estimator's
paired + CRN + CUPED + clustered machinery. **Read directly against the code, this is factually
incorrect — probes already have it, and no fix was needed for this sub-task.**

`agentgauge.attribution_benchmark.make_probe_fn`'s `probe()` closure calls
`agentgauge.harness.diff_server_level` directly (`agentgauge/attribution_benchmark.py`, the
`result = diff_server_level(...)` line in both `make_probe_fn` and `make_multi_probe_fn`) — the
exact same function that produces the repo's server-level 5.37pp headline. `diff_server_level`:
- **Pairs** on task identity via `pair_tasks_common_random_numbers` (one row per task, matched
  before/after) — this codebase's implementation of common random numbers: within one probe, the
  before/after arms share correlated task-difficulty draws (`CALIBRATED_RHO=0.881` in the
  synthetic calibration), exactly what CRN is for.
- **CUPED-adjusts** via `cuped_adjust`, on by default (`use_cuped=True`, never overridden by
  `make_probe_fn`).
- Uses **task-clustered inference**, with the **t(G-1) few-clusters correction**
  (`t_adjusted_cluster_bootstrap_mean_ci`) automatically applied whenever `n_tasks < 30`
  (`_FEW_CLUSTERS_THRESHOLD`) — which is every `n_tasks` value tested in this report's ablation
  except 48/96/128.

**One correction to the task brief's own phrasing, not just the premise about probes**: the
"small-G wild cluster bootstrap correction" it names is implemented
(`wild_cluster_bootstrap_mean_ci`) but is **NOT** what `diff_server_level` uses —
`reports/v2_2_few_clusters_correction.md` measured it to make small-cluster coverage *worse*
(higher false-alarm rate, narrower not wider CIs, because a Rademacher sign-flip bootstrap is
bounded by 2^G distinct patterns, too coarse at G=4-8) and it was rejected in favor of the
t(G-1)-critical-value correction actually shipped. Implementing the wild bootstrap for probes, as
the brief's phrasing might suggest, would have been a regression against this repo's own prior
finding, not a fix — not done.

**Replay determinism**: unaffected, by construction, not merely "not measured to be affected."
This entire report touches only `agentgauge/harness.py` (new pure functions, no changes to
existing ones), `agentgauge/attribution_benchmark.py` (a default-parameter test only, see section
4), and new/changed scripts under `scripts/`. Zero lines in `agentgauge/cassette.py` or
`agentgauge/providers.py` — the two modules the 100%-replay-determinism claim is about — were
touched. The claim is orthogonal to this work by construction.

## 2. Task 2b — probe-level MDE ablation, n_tasks = 12/24/48/96

Since the full stack is already applied (section 1), this ablation quantifies each component's
contribution at probe-relevant task counts, extending `scripts/v2_1_mde_ablation.py`'s exact
methodology (same ablation-stage design: baseline → +task-level → +paired → +CUPED) with a fifth
stage this repo's original v2.1 ablation never needed to isolate: the few-clusters t-adjustment,
measured via `diff_server_level` **directly** (not an approximation of it — literally the function
real probes call), since `simulate_mde_task_level`'s own internal detector never applies this
correction (documented lower-bound caveat, `reports/v0_5_effect_size_sensitivity.md` §0).
`n_simulations=500`, power=80%, seed=42, `uv run python scripts/probe_mde_ablation.py`:

| n_tasks | baseline (trial-level) | +task-level (unpaired) | +paired | +paired+CUPED | +clustered (production) |
|---|---|---|---|---|---|
| 12 | 53.27pp | 40.41pp | 24.67pp | 23.16pp | **25.65pp** |
| 24 | 38.59pp | 28.59pp | 17.39pp | 16.48pp | **18.18pp** |
| 48 | 26.54pp | 20.60pp | 13.03pp | 12.43pp | **11.81pp** |
| 96 | 18.96pp | 14.34pp | 9.19pp | 8.59pp | **8.44pp** |

**Reading, matching the original v2.1 ablation's own honest framing**: pairing buys the largest
single reduction at every `n_tasks` (e.g. at n=24: 28.59→17.39pp, ~39% relative — expected given
`CALIBRATED_RHO=0.881`, same order as v2.1's own finding). **CUPED buys very little on top of
pairing** here too (17.39→16.48pp at n=24, ~5% relative) — the same "pairing already captures
nearly all the removable task-level variance" finding `reports/v2_1_estimator_rebuild.md` reported
for the server-level estimator, now confirmed to hold at probe scale as well, not just at n=253.
**The few-clusters correction's sign flips with `n_tasks`**: at n=12/24 (both `<30`, correction
active) it *widens* the effective MDE relative to the uncorrected `+paired+CUPED` figure (23.16→
25.65pp at n=12; 16.48→18.18pp at n=24) — this is the correction doing its job (a principled,
conservative widening at low degrees of freedom, exactly `reports/v2_2_few_clusters_correction.md`'s
intent); at n=48/96 (both `≥30`, correction inactive, `diff_server_level` uses the plain
`cluster_bootstrap_mean_ci`) the two columns track closely (12.43→11.81pp; 8.59→8.44pp — small
residual differences from `n_resamples`/implementation details, not the correction).

**This entire gap — the reason per-probe MDE (≥16.91-18.18pp at n=24) is so much worse than
server-level MDE (5.37pp at n=253) — is sample size, not a missing technique.** `18.18 × sqrt(24) ≈
89.1`; `8.44 × sqrt(96) ≈ 82.7`; `5.37 × sqrt(253) ≈ 85.4` (server-level headline) — all three land
within ~5% of each other, consistent with the classic `MDE ∝ 1/√n` scaling law for a fixed
estimator. Probes were never missing paired/CUPED/clustered machinery; they were always going to
need something close to a 253-task sample to approach the server-level number, because they
**are** the same estimator run at a smaller n.

## 3. Task 2c — target achievement

Bisection search using `mde_production` (the same `diff_server_level`-direct detector as
section 2's fifth column), power=80%, n_simulations=500:

| n_tasks | Production MDE | vs. 8.0pp target |
|---|---|---|
| 12 | 25.65pp | NOT MET (gap 17.65pp) |
| 24 | 18.18pp | NOT MET (gap 10.18pp) |
| 48 | 11.81pp | NOT MET (gap 3.81pp) |
| 96 | 8.44pp | NOT MET (gap 0.44pp) |
| 112 | 8.12pp | NOT MET (gap 0.12pp) |
| **128** | **7.34pp** | **MET** |

**Target achieved at `n_tasks=128`, per this task's own instruction not to round a near-miss up to
"met."** n=96 and n=112 both come within half a point of the target (a plausible margin of
simulation noise at `n_simulations=500`) but are reported as NOT MET, not rounded; n=128 is the
smallest tested value that clears it with headroom (7.34pp, 0.66pp under target). All Task 2d/2e
work below uses `n_tasks=128`.

## 4. Task 2d — accuracy/budget/scale/multi-culprit tables at n_tasks=128

`uv run python scripts/attribution_improved_probes_report.py` (new script; reuses
`scripts/scale_curve_report.py`'s scoring functions unmodified, imported not duplicated, for a
controlled single-variable comparison against that report's n_tasks=24 numbers). n_cases=30/bucket
(same as `scripts/scale_curve_report.py`), `check_probe_variance_calibration` and
`check_benchmark_construction_diffsize_bias` both run and pass clean on every bucket (artifact
#10/#9 do not reappear at n_tasks=128 — confirmed, not assumed).

### Single-culprit

| n_changed | greedy_bisection top1/top3 | mean probes | Ship bar | sampled_shapley top1/top3 | mean probes | Ship bar |
|---|---|---|---|---|---|---|
| 4 | 93.33%/100.00% | 5.77 | does not clear (not sub-exh) | 46.67%/93.33% | 2.00 | does not clear (top-1) |
| 10 | 96.67%/100.00% | 9.07 | **CLEARS** | 90.00%/100.00% | 5.00 | **CLEARS** |
| 20 | 100.00%/100.00% | 11.50 | **CLEARS** | 100.00%/100.00% | 10.00 | **CLEARS** |
| 40 | 93.33%/96.67% | 12.80 | **CLEARS** | 100.00%/100.00% | 20.00 | **CLEARS** |

**A genuine, substantial accuracy improvement over n_tasks=24** (`reports/v0_5_mde_discrepancy.md`
§4c): both strategies now clear the full ship bar at every single-culprit size ≥10, including the
n=40 size where `greedy_bisection` previously collapsed to 47% top-1 and `sampled_shapley` needed
n_tasks=24's inflated effective-sample-size trick to reach 100%. At n_tasks=128, `sampled_shapley`
hits 100%/100% at n=40 using genuinely well-powered individual probes, not many averaged
marginally-powered ones.

### Multi-culprit

| Config | greedy_bisection recall@m/top3 | mean probes | Ship bar | sampled_shapley recall@m/top3 | mean probes | Ship bar |
|---|---|---|---|---|---|---|
| 2 culprits, 20 tools | 98.33%/100.00% | 16.30 | **CLEARS** | 58.33%/53.33% | 10.00 | does not clear |
| 3 culprits, 20 tools | 98.89%/96.67% | 21.30 | does not clear (not sub-exh: 21.3 > 20) | 53.33%/6.67% | 10.00 | does not clear |
| 3 culprits, 40 tools | 94.44%/83.33% | 23.87 | does not clear | 80.00%/43.33% | 20.00 | does not clear |

**Partial rescue, not a full one.** `greedy_bisection` now clears the 2-culprit/20-tool
configuration for the first time in this project's history (previously: 46.67% top3 at n_tasks=24)
— genuine progress. It narrowly misses the 3-culprit/20-tool config purely on the budget leg
(21.30 probes vs. exhaustive's 20 — the same "wasted confirm-no-additional-culprit pass" mechanism
`reports/v0_5_effect_size_sensitivity.md` §11e diagnosed, still unfixed, still binding). Neither
strategy clears 3-culprit/40-tool. `sampled_shapley` does not clear any multi-culprit
configuration at n_tasks=128, same as at n_tasks=24 — its accuracy on `top3_strict` specifically
degrades sharply with `n_culprits` (53%→7%→43%) even as `recall@m` looks respectable, a distinct
failure mode from `greedy_bisection`'s (budget, not accuracy) that this report does not further
diagnose.

## 5. Task 2e — cost economics: the decisive result

**Full-corpus re-evaluation baseline**: 253 tasks × 2 arms × 1 trial = **506 trial-equivalents**
(matches `simulate_mde_task_level`'s default `trials_per_task=1` assumption, the same assumption
behind the repo's own "MDE 0.0537 at n=253" headline). Wall-clock: no fresh live-inference
measurement was run for this report (see MEASURED/NOT MEASURED); using the one real-agent
wall-clock data point on record (`reports/v0_5_real_agent_validation.md`: 28.61s / 4 tasks =
7.15s/task, with a 5.42-9.20s/task range across two prior pilot measurements) as a point estimate,
a full re-eval costs **~3618s (~60 minutes)**.

### Trial-equivalent cost at n_tasks=128 (Task 2d's configuration), vs. the 506-trial-equivalent full re-eval

| Bucket | exhaustive_ablation | sampled_shapley | greedy_bisection |
|---|---|---|---|
| single_n4 | 1024 (2.02x) | 512 (1.01x) | 1476 (2.92x) |
| single_n10 | 2560 (5.06x) | 1280 (2.53x) | 2321 (4.59x) |
| single_n20 | 5120 (10.12x) | 2560 (5.06x) | 2944 (5.82x) |
| single_n40 | 10240 (20.24x) | 5120 (10.12x) | 3277 (6.48x) |
| multi_c2_n20 | 5120 (10.12x) | 2560 (5.06x) | 4173 (8.25x) |
| multi_c3_n20 | 5120 (10.12x) | 2560 (5.06x) | 5453 (10.78x) |
| multi_c3_n40 | 10240 (20.24x) | 5120 (10.12x) | 6110 (12.07x) |

**Every single cell is more expensive than a full re-eval. The cheapest configuration in this
entire study — `sampled_shapley` localizing a single culprit among 4 changed tools — is already
1.01x the cost of re-running the whole 253-task corpus.** In wall-clock terms at the 7.15s/task
point estimate, that "cheapest" case is ~3661s (~61 min, matching the full re-eval almost exactly
by construction), and the worst tested case (`exhaustive_ablation`, 40 changed tools) is ~20.3
hours — for one localization, on one regressed PR.

### Was this inevitable, or specific to n_tasks=128? Crossover analysis at every tested `n_tasks`

Per-probe cost is `n_tasks × 2` trial-equivalents; a strategy using `P` probes beats the 506-
trial-equivalent full re-eval exactly when `P < 506 / (n_tasks × 2)`:

| n_tasks | Cost/probe | Exhaustive crosses over above n_changed ≈ | `sampled_shapley` (≈n/2 probes) crosses over above n_changed ≈ |
|---|---|---|---|
| 24 (original, pre-Wave-1.6) | 48 | **10.5** | **21.1** |
| 48 (would clear neither 8pp nor accuracy target) | 96 | 5.3 | 10.5 |
| 128 (clears the 8pp/accuracy target) | 256 | 2.0 | 4.0 |

**The economics problem is not new to this fix — it was already present, and already binding at
exactly the scale that matters, before this task started.** At the ORIGINAL `n_tasks=24`,
`exhaustive_ablation` was already more expensive than a full re-eval past ~10 changed tools, and
even `sampled_shapley` (the cheaper strategy) crossed over past ~21 — both comfortably inside the
target buyer's own stated scenario (spec §2: "a 40-tool server"). Fixing probe power for accuracy
(section 3) moved that crossover from "already tight at realistic scale" to **"crosses over at
n_changed≈2-4, before any interesting multi-file PR is even in scope."** There is no `n_tasks` in
the tested range where BOTH the accuracy target (section 3) and a real cost advantage over
re-measuring everything (this section) hold at once — `greedy_bisection`'s real probe counts (not
the `~n/2` formula) do slightly better than `sampled_shapley`'s worst case at n_tasks=128
(6.48x-12.07x rather than 20x+), but "6-12x more expensive than the alternative" is not a
cost-economics win by any reasonable product bar.

## 6. Task 3 — ship / kill recommendation

**Recommend: hold failure attribution as unreleased research. Ship v0.5.0 with model adapters
only.**

Both halves of the ship bar this task set were tested honestly, and only one clears:

- **Accuracy: largely fixed.** At `n_tasks=128`, both strategies clear the full ship bar at every
  single-culprit size ≥10 tools, and `greedy_bisection` clears one real multi-culprit
  configuration for the first time this project has measured. This is genuine, substantive
  progress, not a rounding exercise — section 4's numbers should be read as a real result, not
  discounted by section 5.
- **Cost economics: fails decisively, not marginally.** At the `n_tasks` accuracy requires, every
  tested configuration — down to the single cheapest case in the whole study — costs more than
  simply re-running the full evaluation the localizer exists to make unnecessary. This is not a
  close call resolved against the feature by a small margin; the closest case is 1.01x (a coin
  flip either way, noise-dominated) and the realistic-scale cases (the target buyer's actual
  10-40-tool, multi-file scenario) are 5x-20x. Per this task's own framing: *"a localizer that
  costs more than the thing it is meant to save has no product economics regardless of its
  accuracy"* — that condition is met, plainly, at every tested point.
- The tension is structural, not a tuning miss: lower `n_tasks` is cheap but statistically
  underpowered (section 2/3); higher `n_tasks` is powered but each probe individually costs a
  meaningful fraction of a full corpus re-eval, and any strategy needing more than 1-2 probes
  (i.e. any realistic localization problem) loses to just re-measuring everything. No `n_tasks`
  value tested, and no value implied by the `1/√n` scaling law established in section 2, resolves
  both simultaneously — closing this gap would need either a fundamentally different signal source
  (not more samples of the same one) or accepting a materially weaker accuracy bar than this task
  set.

**What ships**: model adapters (Component 1.1) — six adapters, 100% replay determinism (unaffected
by this report, see section 1), cost/timing accounting, already independently verified in
`reports/v0_5_wave1_report.md` and unaffected by anything in Wave 1.5/1.6. Recommend proceeding
with `v0.5.0` scoped to adapters only.

**What does not ship**: failure attribution (Component 1.2) as a product surface. The underlying
research remains valuable and should be preserved for the methods paper
(`spec-agentgauge-v0.5.md` §3a) — ten (now eleven, counting this investigation's confirmed-benign
audit as a non-event, so still ten) measurement artifacts, a fully diagnosed accuracy/cost
trade-off curve, and an honest negative economics result are exactly the kind of finding that
paper's contribution list already values. This is a recommendation, not a decision — GG's call per
this repo's standing autonomy policy on product/roadmap sequencing.

## 7. MEASURED vs. NOT MEASURED

**MEASURED:** the full paired+CUPED+clustered call chain in `make_probe_fn`/`make_multi_probe_fn`,
confirmed by direct code reading, not assumed (§1). The five-stage MDE ablation at n_tasks=
12/24/48/96, `n_simulations=500`, reproducible via `scripts/probe_mde_ablation.py` (§2). The exact
crossover between NOT-MET and MET at n_tasks=96/112/128 (§3). Full accuracy/budget/recall tables
at n_tasks=128 across 4 single-culprit and 3 multi-culprit configurations, n=30 cases/bucket,
reproducible via `scripts/attribution_improved_probes_report.py`, with `check_probe_variance_calibration`
and `check_benchmark_construction_diffsize_bias` both run and passing on every bucket (§4). Every
trial-equivalent cost figure and crossover threshold in §5 (pure arithmetic on measured probe
counts, not estimated).

**NOT MEASURED:** live wall-clock cost — every wall-clock figure in §5 is derived from a single
n=1 real-agent data point (`reports/v0_5_real_agent_validation.md`) with a disclosed ~1.7x
measurement spread, not independently re-measured this pass (per the standing constraint: no live
inference without an approved bounded estimate). Whether a smaller, targeted redesign (e.g.
caching shared task evaluations across probes, or a fundamentally different low-variance signal)
could close the accuracy/cost gap this report found structural — not attempted, flagged as the
natural next research question if attribution is revisited. `sampled_shapley`'s multi-culprit
`top3_strict` failure mode (§4) — not root-caused here, same open item `reports/
v0_5_shapley_scaling_audit.md` §2 already flagged. Any candidate-set size beyond 40 tools or
culprit count beyond 3 — outside this report's tested range.
