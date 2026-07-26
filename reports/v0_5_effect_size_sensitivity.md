# AgentGauge v0.5 Wave 1 — effect-size sensitivity study for failure attribution (Component 1.2 follow-up)

Follow-up to `reports/v0_5_attribution_benchmark.md` (Component 1.2's original localization
benchmark, and its section 7 diff-size-bias correction — **read section 7 of that report before
this one**, since this study is built on the CORRECTED, post-artifact-#9-fix
`agentgauge/attribution_benchmark.py`). That report measured attribution accuracy at exactly one
effect size: the true culprit's injected effect drawn from a fixed, favorable 13.3-28.9pp range,
explicitly flagged as "the favorable end of the harness's own measured detection power, not a
marginal one." This report answers the follow-up question directly: **how does localization
accuracy degrade as the true effect shrinks toward — and below — the harness's own detection
threshold**, so the shippable claim can be a real bound, not a single favorable-case number.

**Headline finding, in one line:** `greedy_bisection` shows a genuine CLIFF at ~8pp — it clears
the doctrine's ship bar (top-1 ≥ 0.70 AND top-3 ≥ 0.90) at every band ≥ 8.0pp and fails it at every
band < 8.0pp, with the collapse at low bands driven almost entirely by a newly-discovered
**implementation bug** (not a statistical inevitability — see "Implementation finding" below).
`sampled_shapley` shows NO clean cliff at all: it hovers in a noisy 54-71% top-1 band across the
**entire** 3.0-33.0pp range tested and only narrowly clears the ship bar in one of five bands.

All numbers below are reproducible: `uv run python scripts/effect_size_sensitivity_report.py`,
seed=42 (base) with a distinct, disclosed per-band seed (see §2), commit TBD (this report's own
commit). Zero live LLM calls anywhere — same deterministic synthetic ground-truth model as
`reports/v0_5_attribution_benchmark.md`.

## 0. Unit conversion (confirmed before writing any code)

The task's "true effect sizes spanning roughly 0.03 to 0.30... harness MDE (0.0537)" is stated as a
**FRACTION** on `[0,1]` — the same convention `agentgauge.harness.simulate_mde_task_level`'s return
value and `spec-agentgauge-v0.5.md`'s own headline ("MDE 0.0537 at n=253") use. This repo's existing
`agentgauge.attribution_benchmark` module expresses the identical quantity on a signed
**percentage-point** (`_pp`) scale (`CAUSAL_EFFECT_MIN_PP=-28.9`, `CAUSAL_EFFECT_MAX_PP=-13.3`,
`agentgauge.attribution.ProbeResult`'s docstring: "delta/ci_lo/ci_hi are fractions (0.05 == 5
percentage points)"). Confirmed directly against the code (not assumed): `ProbeResult.delta * 100.0`
is how every `_pp`-scale value in `attribution.py` is produced from a raw fraction. **0.0537
fraction = 5.37 on this repo's `_pp` scale; the requested "0.03 to 0.30" fraction sweep is this
module's "3.0 to 30.0" `_pp` range.** Used throughout, no second differently-scaled constant set
introduced (see `agentgauge/attribution_benchmark.py::generate_benchmark`'s new
`effect_min_pp`/`effect_max_pp` parameters, which reuse the existing signed convention exactly).

**Sanity-check finding, not a correction to the above:** the doctrine's own headline MDE (5.37pp)
is measured at `n_tasks=253` (`scripts/mde_grid_v2_5.py`). This benchmark's `make_probe_fn` probes
at `n_tasks=24` by default — a **>10x smaller** trial count per probe. `simulate_mde_task_level`
(the same paired+CUPED+cluster-bootstrap machinery `make_probe_fn`/`diff_server_level` use,
minus the few-clusters t-adjusted-CI correction `diff_server_level` applies below
`n_tasks_matched=30`) gives `n_tasks=24, power=0.8` → **MDE = 0.1691 fraction = 16.91pp**, a LOWER
BOUND on the true per-probe MDE this benchmark actually operates under (the omitted few-clusters
correction only widens CIs further, pushing the real number higher still). **The doctrine's 5.37pp
headline is NOT the number governing this benchmark's own probes** — it describes a different,
much larger trial-count regime. This does not change the band-construction instruction (bands were
explicitly anchored on 5.37pp per the task), but it is essential context for interpreting where the
measured cliff (§4) actually sits relative to both anchor numbers.

## 1. Method

Reuses `agentgauge.attribution_benchmark.generate_benchmark`'s confound-guarded, diff-size-
decorrelated case generator unchanged (post measurement-artifact-#9 fix), with one new capability:
`effect_min_pp`/`effect_max_pp` parameters that let the true culprit's injected effect magnitude be
drawn from a caller-specified band instead of only the original fixed range. This parameter only
remaps which interval the single per-case effect `rng()` draw lands in — it consumes exactly one
PRNG state transition regardless of interval, so for a fixed seed every other drawn field (catalog,
culprit, decoy tiers, positions, diff sizes) is bit-identical across bands (proven directly, not
argued: `tests/test_effect_size_sensitivity.py::TestEffectBandParameterization::
test_effect_band_does_not_change_non_effect_draws_at_same_seed`).

## 2. Effect bands

5 bands, 24 cases each (120 new cases total), each with its own seed (independently drawn cases per
band, not a reuse of the original 50-case set — see §3 for why):

| Band | True effect range | Seed | Relative to anchors |
|---|---|---|---|
| `below_mde` | 3.0-5.0pp | 42 | below both the doctrine's n=253 MDE (5.37pp) and the n=24 probe-regime MDE (16.91pp) |
| `straddle_mde` | 5.0-8.0pp | 1042 | straddles the doctrine's n=253 MDE; still well below the n=24 probe-regime MDE |
| `moderate` | 8.0-13.3pp | 2042 | below the n=24 probe-regime MDE, approaching the original benchmark's floor |
| `original` | 13.3-28.9pp | 3042 | the original benchmark's exact range (`CAUSAL_EFFECT_MIN_PP`/`MAX_PP`) |
| `beyond` | 28.9-33.0pp | 4042 | extends past the original benchmark's ceiling |

## 3. Confound guard — re-verified independently at every band

The guard is NOT assumed to generalize from the original 50-case set. Both mandatory checks
(`confound_guard_report`'s fractional-rank statistic and the standalone
`agentgauge.audit.check_benchmark_construction_diffsize_bias`) were re-run on each band's own
freshly-drawn 24 cases:

| Band | Mean culprit diff-size fractional rank | In [0.35, 0.65]? | Audit BLOCK fired? |
|---|---|---|---|
| below_mde | 0.5729 | Yes | No |
| straddle_mde | 0.5639 | Yes | No |
| moderate | 0.6236 | Yes | No |
| original | 0.5861 | Yes | No |
| beyond | 0.4868 | Yes | No |

**All 5 bands pass both checks.** No interaction between effect band and tier/diff-size draws was
found — consistent with the structural argument in §1 (the effect draw cannot alter the sequence of
subsequent draws for a fixed seed) and now also confirmed empirically across 5 **independent**
seeds, so this isn't merely a restatement of that structural argument.
`tests/test_effect_size_sensitivity.py::TestConfoundGuardPerBand` locks this in.

## 4. Per-band accuracy / budget table (n=24 cases/band)

| Band | Method | top-1 | top-3 | mean probes |
|---|---|---|---|---|
| **below_mde** (3.0-5.0pp) | exhaustive_ablation | 66.67% | 100.00% | 4.04 |
| | sampled_shapley | 54.17% | 95.83% | 2.12 |
| | greedy_bisection | 54.17% | 83.33% | **0.00 (undercounted — see §5)** |
| | largest_textual_diff | 25.00% | 70.83% | 0 |
| | most_lint_violations | 66.67% | 83.33% | 0 |
| | uniform_random | 16.67% | 75.00% | 0 |
| **straddle_mde** (5.0-8.0pp) | exhaustive_ablation | 95.83% | 100.00% | 3.92 |
| | sampled_shapley | 62.50% | 95.83% | 2.04 |
| | greedy_bisection | 41.67% | 91.67% | **0.58 (undercounted)** |
| | largest_textual_diff | 20.83% | 87.50% | 0 |
| | most_lint_violations | 54.17% | 83.33% | 0 |
| | uniform_random | 29.17% | 83.33% | 0 |
| **moderate** (8.0-13.3pp) | exhaustive_ablation | 100.00% | 100.00% | 3.92 |
| | sampled_shapley | 58.33% | 100.00% | 1.92 |
| | greedy_bisection | 95.83% | 100.00% | 2.83 |
| | largest_textual_diff | 25.00% | 66.67% | 0 |
| | most_lint_violations | 41.67% | 79.17% | 0 |
| | uniform_random | 33.33% | 79.17% | 0 |
| **original** (13.3-28.9pp) | exhaustive_ablation | 100.00% | 100.00% | 4.29 |
| | sampled_shapley | 70.83% | 95.83% | 2.42 |
| | greedy_bisection | 100.00% | 100.00% | 2.96 |
| | largest_textual_diff | 12.50% | 62.50% | 0 |
| | most_lint_violations | 54.17% | 87.50% | 0 |
| | uniform_random | 16.67% | 70.83% | 0 |
| **beyond** (28.9-33.0pp) | exhaustive_ablation | 100.00% | 100.00% | 3.62 |
| | sampled_shapley | 58.33% | 100.00% | 1.83 |
| | greedy_bisection | 100.00% | 100.00% | 2.71 |
| | largest_textual_diff | 37.50% | 70.83% | 0 |
| | most_lint_violations | 58.33% | 95.83% | 0 |
| | uniform_random | 20.83% | 83.33% | 0 |

**Even `exhaustive_ablation` (the reference strategy) degrades near the floor**: 66.67% top-1 at
`below_mde`, vs. 100.00% at `moderate`/`original`/`beyond` — the task instruction explicitly asked
not to assume the reference stays immune, and it measurably does not. Its top-3 stays at 100% in
every band, so the degradation is confined to distinguishing the single best candidate from a
close second, not losing the culprit from consideration entirely.

Baselines behave as expected: zero-probe, effect-size-independent by construction, and their
numbers bounce around within ordinary sampling noise across bands (`largest_textual_diff` 12.5-
37.5%, `most_lint_violations` 41.7-66.7%, `uniform_random` 16.7-33.3%) with no monotonic trend tied
to effect size — confirming nothing spurious changes for these three, as expected.

## 5. Implementation finding (NEW, first surfaced by this study) — `probes_consumed` undercounting and a degenerate positional fallback in `attribute_greedy_bisection`

**Not a statistical inevitability — a real accounting/ranking bug in `agentgauge/attribution.py`,
reported here per this task's explicit instruction not to fix it.** Investigated directly against
the code, not guessed:

`_bisect_within` accumulates real `probe()` calls in a local `probes_used` counter and real
per-tool signal in a local `elim_scores` dict throughout its binary search. **If the search's FINAL
confirmation probe fails to clear the significance threshold, the function `return None`** —
discarding `probes_used` and `elim_scores` in their entirety, even though real (paid-for) probe
calls happened and real (if statistically insignificant) signal was gathered along the way. The
caller (`attribute_greedy_bisection`) then does `elim_scores.setdefault(t, 0.0)` for **every** tool
still in `remaining`, so on a total search failure every candidate ties at exactly `0.0`. Python's
stable sort preserves insertion order under a tie, and `rest` is built as
`[t for t in changed_tools if t not in found_names]` — so **the reported top-1 becomes exactly
`changed_tools[0]`, regardless of any signal actually observed**, and `probes_consumed` reports
`0` even though real probe calls were made.

Directly measured (not inferred) per band:

| Band | Cases with `probes_consumed==0` | Of those, predicted `changed_tools[0]` | Of those, "hit" top-1 by pure positional luck |
|---|---|---|---|
| below_mde | 24/24 (100%) | 24/24 | 13/24 |
| straddle_mde | 20/24 (83%) | 20/20 | 6/20 |
| moderate | 1/24 (4%) | 1/1 | 0/1 |
| original | 0/24 | — | — |
| beyond | 0/24 | — | — |

**`below_mde`'s reported 54.17% top-1 for `greedy_bisection` is *entirely* explained by this
degenerate fallback**: every single one of its 24 cases had a total search failure, every single
one predicted `changed_tools[0]`, and the reported top-1 hit count (13) is EXACTLY the count of
cases where `changed_tools[0]` happened to be the true culprit — there is zero real localization
signal behind that 54.17% number. This also means `mean_probes` for `greedy_bisection` at
`below_mde`/`straddle_mde` (0.00/0.58) is a genuine **undercount** of real cost, not a genuine
budget saving — actual probe calls were made and paid for; they just weren't counted. This is the
opposite of the failure mode a "budget" column should misrepresent — it makes a collapsing strategy
look artificially *cheap* exactly where it is failing.

This bug was invisible in `reports/v0_5_attribution_benchmark.md`'s original 50-case benchmark
because that benchmark's 13.3-28.9pp effect range never triggered a total search failure (100%
top-1 throughout) — this effect-size sensitivity study is the first measurement to exercise this
code path at all. **Reported, not fixed, per this task's explicit scope boundary** — a reasonable
fix (e.g., `_bisect_within` returning its partial `probes_used`/`elim_scores` even on failure
instead of discarding them via `None`) is a judgment call left to the orchestrator.

## 6. Mechanism investigation — why does CI-based bisection fail near the threshold?

For every case where the REAL `attribute_greedy_bisection` call missed top-1, a diagnostic-only
reimplementation of its exact decision logic (`scripts/effect_size_sensitivity_report.py::
trace_greedy_bisection_decisions` — duplicated, not imported; `agentgauge/attribution.py` was not
modified) re-derives each binary-search split decision using the SAME deterministic probe callback
the real run used, and classifies each decision against ground truth (available only to the
benchmark, never to the real strategy):

- **Mode A — detection-power failure**: the true culprit genuinely WAS in the probed half (a real
  recovery effect was present) but the CI failed to exclude the threshold
  (`marginal_ci_lo <= threshold`) — the estimator could not detect a real effect at this trial
  count.
- **Mode B — false-positive noise**: the true culprit was NOT in the probed half (no real recovery
  effect) but the CI crossed the threshold anyway (`marginal_ci_lo > threshold`) — sampling noise
  producing a false-positive significant result, sending the search the wrong way.

**Measured result: Mode A dominates completely. Mode B was never observed, in any band.**

| Band | Miss cases | Decisions classified Mode A | Decisions classified Mode B | Miss cases with ≥1 Mode A | Miss cases with ≥1 Mode B |
|---|---|---|---|---|---|
| below_mde | 11/24 | 11 | **0** | 11/11 | 0/11 |
| straddle_mde | 14/24 | 14 | **0** | 14/14 | 0/14 |
| moderate | 1/24 | 1 | **0** | 1/1 | 0/1 |
| original | 0/24 | — | — | — | — |
| beyond | 0/24 | — | — | — | — |
| **Total** | **26** | **26** | **0** | **26/26** | **0/26** |

**This directly confirms the task's leading hypothesis and rules out the alternative.** Every
single traced decision behind every single top-1 miss across all 5 bands is a genuine effect that
the CI simply couldn't detect at `n_tasks=24` — never a case of noise inventing a false signal in a
truly-null half. Concrete example (`below_mde`, `case_002`, true culprit `create_repository`):
probing the half containing the true culprit measured `marginal_delta=+0.0703`,
`marginal_ci_lo=+0.0365` — a real, substantial, POSITIVE recovery signal — but
`+0.0365 <= threshold (0.05)`, so the CI did not clear the bar and the search recursed the wrong
way. The effect was there; the estimator, at this trial count, could not certify it.

## 7. Ship-bar verdict per band (top-1 ≥ 0.70 AND top-3 ≥ 0.90)

| Band | greedy_bisection | sampled_shapley |
|---|---|---|
| below_mde (3.0-5.0pp) | does not clear (54.17%/83.33%) | does not clear (54.17%/95.83%) |
| straddle_mde (5.0-8.0pp) | does not clear (41.67%/91.67%) | does not clear (62.50%/95.83%) |
| moderate (8.0-13.3pp) | **CLEARS** (95.83%/100.00%) | does not clear (58.33%/100.00%) |
| original (13.3-28.9pp) | **CLEARS** (100.00%/100.00%) | **CLEARS** (70.83%/95.83%) |
| beyond (28.9-33.0pp) | **CLEARS** (100.00%/100.00%) | does not clear (58.33%/100.00%) |

## 8. Shippable claim

### `greedy_bisection`: a genuine CLIFF, with a caveat about its cause

**"Localizes the culprit at top-1 ≥ 0.70 when the true effect is ≥ 8.0pp"** (the exact boundary
between `straddle_mde` and `moderate`, the only two adjacent bands measured on either side of the
transition). Every band ≥ 8.0pp clears the FULL ship bar (top-1 ≥ 0.70 AND top-3 ≥ 0.90); every
band < 8.0pp fails it. This is a real cliff, not a gradual decay you could draw a single clean
threshold through at a different point — `below_mde` (54.17%) and `straddle_mde` (41.67%) are
non-monotonic with each other (straddle is LOWER despite a larger true effect), which is itself
evidence that **both** sub-8.0pp bands have collapsed into the same "no real signal, just
positional-luck" regime described in §5, not that accuracy is meaningfully varying within that
regime.

**Caveat that must ship alongside this number**: §5's implementation finding means the low-band
failure is a *combination* of a genuine statistical detection-power limit (§6: Mode A dominates
100% of the time) AND an implementation bug that converts "the search found nothing conclusive"
into "silently guess position 0 and report 0 probes spent" instead of, e.g., abstaining or
reporting partial information. The true STATISTICAL cliff (where detection genuinely becomes
unreliable) is real and would still show up as degraded accuracy even with a fixed implementation
— but the EXACT 8.0pp number and the specific 54.17%/41.67% figures below it are entangled with
this bug's behavior, not a clean measurement of the underlying detection curve alone. This
entanglement could not be separated within this task's scope (fixing the bug is out of scope here).

### `sampled_shapley`: NO defensible cliff — flat, noisy, and near-bar across the entire tested range

**Does not fit the "top-1 ≥ 0.70 when effect ≥ X pp" form.** Across all 5 bands spanning 3.0-33.0pp,
`sampled_shapley`'s top-1 ranges narrowly between 54.17% and 70.83%, clearing the ship bar in
exactly ONE of five bands (`original`, 13.3-28.9pp, and only by a 0.83-point margin) — with NO
monotonic relationship to effect size: `beyond` (28.9-33.0pp, a LARGER true effect than `original`)
scores 58.33%, *tied* with `moderate` (8.0-13.3pp, also 58.33%) despite the two bands' true effect
ranges being on opposite sides of `original`, and both sit below `straddle_mde`'s 62.50% (5.0-8.0pp,
a *smaller* true effect than either). This is the honest characterization the task asked for when
a single-number claim doesn't fit the data: **`sampled_shapley`'s accuracy ceiling in this benchmark
appears to be governed primarily by its own fixed sub-exhaustive random-coalition sampling budget
(`_sampled_shapley_budget`, ~half of `n_changed`) rather than by true effect magnitude in the 3-33pp
range tested** — it never clearly separates from the ~54-71% band regardless of how large or small
the true effect is, consistent with `reports/v0_5_attribution_benchmark.md`'s own finding (68.0% on
the corrected 50-case set, a narrow 2-point miss of the same bar) that this strategy sits right at
the ship-bar boundary with sampling noise on both sides. **No X-pp threshold claim is defensible for
`sampled_shapley` from this data** — the honest statement for the README is that it does not
reliably clear the ship bar at any tested effect size except marginally at the original benchmark's
own favorable range, and is not effect-size-sensitive in the way `greedy_bisection` is.

## 9. MEASURED vs. NOT MEASURED

**MEASURED:** every number above comes from running the code in this repo against the same
deterministic synthetic ground-truth model `reports/v0_5_attribution_benchmark.md` uses, on 120
newly-generated cases (24 per band × 5 bands, each band its own seed), fully reproducible via
`uv run python scripts/effect_size_sensitivity_report.py`. Zero live LLM calls. The confound guard
was re-verified independently per band, not assumed to generalize. The §5 implementation finding
and §6 mechanism classifications are both derived directly from code inspection plus live
measurement (probe counts, prediction identities, decision-level traces), not inferred or guessed.

**NOT MEASURED:**
- Every caveat in `reports/v0_5_attribution_benchmark.md` §4 still applies unchanged (zero-effect
  decoys, no live-agent validation) — this study only varies the true effect's magnitude within the
  same favorable synthetic regime, it does not address the "never run against a real agent" gap.
- The exact statistical cliff location for `greedy_bisection` in the ABSENCE of the §5
  implementation bug is not isolated — see §8's caveat.
- `n=24` cases/band is small; per-band figures carry real sampling noise (visible directly in the
  non-monotonic dips discussed in §8) — a larger per-band `n` would tighten these figures but was
  not run in this task's scope (n=24 was chosen to match this repo's existing per-band test
  convention and keep the reproducibility script's runtime bounded).
- The probe-regime MDE reported in §0 (16.91pp) is a naive lower bound (omits the few-clusters
  t-adjusted-CI correction `diff_server_level` actually applies at `n_tasks=24 < 30`) — the true
  single-probe MDE at this trial count is not exactly measured, only bounded below.

## 10. Reproduction

`uv run python scripts/effect_size_sensitivity_report.py`, seed=42 (base) with per-band seeds
42/1042/2042/3042/4042 (see §2), this report's own commit. Building on
`reports/v0_5_attribution_benchmark.md`'s corrected `agentgauge/attribution_benchmark.py`
(post-`6ae80d8`, artifact #9 fix) — running this script against a pre-fix checkout would reintroduce
the diff-size confound this study's §3 explicitly re-verified is absent.
