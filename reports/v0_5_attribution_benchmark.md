# AgentGauge v0.5 Wave 1 — failure attribution / regression localization benchmark (Component 1.2)

> **SECTIONS 2, 3, AND 5 BELOW ARE SUPERSEDED (2026-07-26).** A benchmark-construction bug
> (measurement artifact #9: the injected culprit's textual diff size was systematically correlated
> with its role, not randomized independently of it) was found in the generator these sections
> describe, and fixed. **Section 7, "CORRECTION," at the end of this report is the current,
> trustworthy version of this benchmark's numbers and ship-bar verdict — read it, not sections 2/3/5,
> for anything cited going forward.** The original text below is kept verbatim, not deleted or
> silently edited, per this repo's honest-reporting convention (falsified/superseded results are
> marked, not erased). **Headline of the correction: the ship-bar conclusion CHANGES** —
> `sampled_shapley` no longer clears the doctrine's bar on the corrected benchmark (68.0% top-1,
> below the 70% bar); only `greedy_bisection` still clears it. See section 7.

Per `reports/v0_5_eval_doctrine.md` (Component 1.2) / `spec-agentgauge-v0.5.md` sec 4.2: localization
accuracy is measured against **known injected culprits**, at a **paired (accuracy, probe-budget)**
curve per strategy, against three zero-probe baselines, with a mandatory benchmark-construction
confound guard checked *before* any accuracy number is reported.

**Headline: yes, a strategy clears the doctrine's ship bar** (top-1 ≥ 0.70 AND top-3 ≥ 0.90 AND
probe budget strictly below exhaustive ablation) — **greedy bisection** clears it decisively (100%
top-1, 100% top-3, at 2.98 mean probes vs. exhaustive's 4.22), and **sampled Shapley** clears it too
(74% top-1, 96% top-3, at 2.22 mean probes). This is reported plainly per the doctrine's honesty
requirement, with the same rigor as this repo's negative/falsified results: the finding is real,
but measured on a **synthetic benchmark with an unusually clean ground-truth signal** (see the
"MEASURED vs NOT MEASURED" section below) — this is not yet validated against a real agent.

All numbers below are reproducible: `uv run python scripts/attribution_benchmark_report.py`,
seed=42, commit `2976893` (`feat(attribution): failure attribution / regression localization
(v0.5 Wave 1, 1.2)`) — see the "Provenance note" at the end of this report for a git-workflow
collision this commit's history records and how it was resolved.

## 1. What was measured, and how

`agentgauge/attribution.py` implements three probe-based localization strategies —
`attribute_exhaustive` (a), `attribute_sampled_shapley` (b), `attribute_greedy_bisection` (c) — and
three zero-probe baselines: `baseline_largest_textual_diff` (i), `baseline_most_lint_violations`
(ii), `baseline_uniform_random` (iii). All six share one interface: given the set of changed tools
and a `ProbeFn` callback, return a ranked list of suspects (`AttributionCandidate`s) plus
`probes_consumed`.

`agentgauge/attribution_benchmark.py` generates injected-culprit benchmark cases from
`evals/fixtures/v2_tool_definitions.json` (the same real multi-tool corpus
`scripts/v2_defect_injector.py` already uses): one randomly-selected tool per case gets the REAL,
causally-validated `type_enum_contradiction` defect (a string property's type flipped + a
boolean-phrase sentence appended — the exact mutation `scripts/v2_defect_injector.py`'s
`inject_type_flipped` performs, reimplemented locally since `agentgauge/` package code may not
import from `scripts/`); every other changed tool in the case gets a benign, zero-effect textual
decoy mutation at one of three diff-size tiers (small/medium/large).

Every probe call is routed through `agentgauge.harness.diff_server_level` — the real paired +
CUPED + cluster-bootstrap estimator — fed with synthetic `TrialOutcome` pairs built from a
declared, deterministic ground-truth model (see §4). This literally reuses the harness's own
estimator per probe, per the doctrine's instruction, rather than a hand-computed shortcut.

- **n_cases = 50**, seed = 42.
- **n_changed per case**: 2–6 tools (drawn per case; corpus catalogs have 4–60 tools each).
- **True culprit's injected effect**: drawn uniformly in [-28.9pp, -13.3pp] per case — the measured
  `type_enum_contradiction` causal range across 3 model families (`scripts/v2_defect_injector.py`,
  `reports/v2_2_task_b_causal_chain_multimodel.md`).

## 2. Accuracy / budget table

| Method | top-1 | top-3 | mean probes | vs. exhaustive |
|---|---|---|---|---|
| **exhaustive_ablation** (a) | 100.0% | 100.0% | 4.22 | reference |
| **sampled_shapley** (b) | 74.0% | 96.0% | 2.22 | sub-exhaustive |
| **greedy_bisection** (c) | 100.0% | 100.0% | 2.98 | sub-exhaustive |
| largest_textual_diff (i) | 4.0% | 66.0% | 0 (zero-probe) | — |
| most_lint_violations (ii) | 64.0% | 80.0% | 0 (zero-probe) | — |
| uniform_random (iii), one draw | 30.0% | 70.0% | 0 (zero-probe) | — |
| uniform_random (iii), **analytic expectation** | 26.7% | 75.1% | 0 (zero-probe) | — |

The uniform-random row reports both a single deterministic draw (30.0%/70.0%) and the analytic
expectation averaged per-case as `min(k, n_changed) / n_changed` (26.7%/75.1%) — per the doctrine's
explicit instruction not to report a single draw's incidental variance as the baseline's real
accuracy. A Monte Carlo cross-check (`tests/test_attribution.py::TestExpectedTopkAccuracy::
test_matches_repeated_draw_average`, 2000 repeated draws) confirms the analytic formula matches
empirical draw frequency to within 5 percentage points.

## 3. Ship bar verdict (doctrine Component 1.2: top-1 ≥ 0.70 AND top-3 ≥ 0.90 AND sub-exhaustive budget)

| Strategy | top-1 | top-3 | mean probes | sub-exhaustive? | Verdict |
|---|---|---|---|---|---|
| exhaustive_ablation | 100.0% | 100.0% | 4.22 | **No** (it is the reference) | does not clear (not sub-exhaustive by definition) |
| sampled_shapley | 74.0% | 96.0% | 2.22 | Yes | **CLEARS** |
| greedy_bisection | 100.0% | 100.0% | 2.98 | Yes | **CLEARS** |

**Two of the three probe-based strategies clear the ship bar on this benchmark.** Exhaustive
ablation trivially reaches 100%/100% but is excluded by construction (it *is* the exhaustive
reference the doctrine requires beating on budget, not a candidate for "sub-exhaustive"). Both
zero-probe baselines and the random floor fall well short of the bar (largest-textual-diff is
*worse than random* on top-1 in this benchmark — see §5), confirming the doctrine's baselines are
genuinely being beaten, not tied.

## 4. MEASURED vs. NOT MEASURED — read this before citing the numbers above

**MEASURED:** every number in §2/§3 comes from running the code in this repo against a
deterministic synthetic ground-truth model, on 50 generated benchmark cases, seed=42, fully
reproducible via `scripts/attribution_benchmark_report.py`. Zero live LLM calls anywhere in this
benchmark, per this repo's standing test-determinism rule.

**NOT MEASURED — and the most important caveat in this report:** this benchmark's ground-truth
model is an unusually clean measurement regime relative to a real agent run:
- Decoys have **exactly zero** causal effect by construction — a real benign textual edit to a
  real agent's tool description might have a small nonzero effect the harness's CI can't
  distinguish from the true culprit's effect at typical trial counts, which would degrade every
  probe-based strategy's accuracy below what is reported here.
- The true culprit's effect (13.3–28.9pp) is a *large*, well-separated signal by real-agent-eval
  standards — `reports/v2_harness_evaluation.md`'s own MDE table shows the harness needs a
  25–75-point true effect to reliably detect anything at realistic trial counts (5–50/arm); this
  benchmark's injected effect sits at the favorable end of the harness's own measured detection
  power, not a marginal one.
- **This benchmark has never been run against a real agent + real LLM judge.** The 100%/74%
  top-1 figures above are a measured property of this synthetic benchmark and the estimator's
  behavior on it — not a claim about real-world localization accuracy on an arbitrary regression.
  Validating against a live-model run (with real, noisier decoy variance and a harder-to-separate
  true effect) is explicitly future work, not yet attempted, per spec §7's cost constraint (no
  paid provider without an approved bounded estimate) and this repo's standing no-live-inference
  rule for this task's scope.

## 5. Confound-guard verification (mandatory, per doctrine Component 1.2)

**Guard 1 — true culprit's position is not fixed.** Across 50 cases, the culprit's index within
`changed_tools` (itself independently Fisher-Yates-shuffled per case) took **6 distinct values**:
`{0: 19, 1: 11, 2: 5, 3: 7, 4: 2, 5: 6}`. Position 0 is the single most common value (38%), but this
is an artifact of position 0 being a valid slot for every `n_changed` (2–6), not a fixed-position
confound — conditioning on `n_changed` separately (verified with a larger n=300 sample in
development, not part of the committed 50-case set) shows an approximately uniform distribution
within each stratum. `tests/test_attribution_benchmark.py::TestConfoundGuard::
test_culprit_position_is_not_fixed` asserts `n_positions_observed > 1` and passes.

**Guard 2 — decoy diffs are not systematically smaller than the culprit's diff.** Only **2/50
cases (4.0%)** have the true culprit as the single largest-diff tool in its case; in **48/50 cases
(96.0%)** at least one decoy has a strictly larger character-edit-distance diff than the true
culprit. This decisively satisfies the doctrine's requirement ("some decoys must have larger
textual diffs than the real culprit, or baseline (i) would win by construction") —
`baseline_largest_textual_diff`'s own measured 4.0% top-1 accuracy in §2 is the direct, honest
consequence: this benchmark does NOT let the largest-diff heuristic win by construction, and
indeed the heuristic performs *worse than the uniform-random floor* here.

**Disclosed asymmetry, reported rather than hidden:** the true culprit's diff-size RANK is skewed
toward the small end (mean fractional rank ≈0.66 on a 0=biggest/1=smallest scale, measured in
development on a larger sample) — the real defect injection (`_inject_type_enum_contradiction`) is
a short, surgical mutation (~40–50 characters), while decoy tiers include "large" cosmetic
rewordings (~230 characters) with probability 1/3 each. This is a real, disclosed distributional
property of this generator, not a violation of the mandatory guard (the guard requires "not always
biggest," not "uniformly ranked") — but it does mean baseline (i)'s 4.0% here should be read as
"this generator's specific decoy-size mix makes max-diff perform badly," not as a universal claim
that textual diff size is never informative. Both tests
(`test_culprit_is_not_always_the_max_diff_tool`, `test_at_least_some_decoys_exceed_culprit_diff`)
pass.

## 6. Summary against the doctrine's pre-declared bar

- **Ship bar (top-1 ≥ 0.70, top-3 ≥ 0.90, sub-exhaustive budget): CLEARED** by 2 of 3 probe-based
  strategies (`greedy_bisection`, `sampled_shapley`) — reported as a genuine positive finding, not
  softened or inflated beyond what was measured.
- **Confound guard: run and passed**, both required checks (position not fixed, decoys not
  systematically smaller) — verified in `tests/test_attribution_benchmark.py::TestConfoundGuard`
  and reproduced in `scripts/attribution_benchmark_report.py`'s own printed output.
- **The honest limitation, stated per the doctrine's own framing:** this is a favorable-regime
  synthetic benchmark (zero-effect decoys, a large well-separated true effect), not yet validated
  against a real agent. Per spec §8 risk 2 ("attribution may need an infeasible probe budget... if
  localizing a culprit costs more compute than a full re-eval, the feature has no value"): on THIS
  benchmark the probe budget is genuinely sub-exhaustive AND accurate, so risk 2 does not
  materialize here — but that conclusion is scoped to this synthetic regime until a real-agent
  validation is run.

## Provenance note

This report's code (`agentgauge/attribution.py`, `agentgauge/attribution_benchmark.py`,
`scripts/attribution_benchmark_report.py`, `tests/test_attribution.py`,
`tests/test_attribution_benchmark.py`, this report) is committed as its own change in commit
`2976893`. A git-workflow collision occurred first and is worth recording honestly: a
concurrently-running session on the same `feat/v0-5-wave1` branch committed its own (unrelated,
Component 1.1 provider-config) work at effectively the same moment as this task's first commit
attempt, and that session's `git commit` swept this task's already-staged files into commit
`460b2de` alongside its own. That session then itself detected the collision and issued a
follow-up commit (`7cfce82`, `git rm --cached` only, on-disk content untouched) restoring this
task's files to an untracked state so they could be committed independently — which they then were,
cleanly, as `2976893`. The content of every file above is exactly as authored for this task —
nothing from Component 1.1's work was written or edited by this task, and nothing here touches
`agentgauge/cli.py`, `agentgauge/providers.py`, `agentgauge/cassette.py`,
`agentgauge/provider_config.py`, `configs/`, `tests/test_cassette.py`,
`tests/test_cli_provider_cost.py`, or `tests/test_provider_config.py`.

---

## 7. CORRECTION (2026-07-26) — measurement artifact #9: benchmark-construction diff-size bias

**This section supersedes sections 2, 3, and 5 above.** Everything below was independently
re-measured after fixing the bug described here; nothing above this line was edited to match it.

### 7a. What was wrong (Task 3a measurement)

Section 5's "disclosed asymmetry" paragraph reported the culprit's mean diff-size fractional rank
as "≈0.66, measured in development on a larger sample" and argued this was a disclosed, acceptable
property, not a guard violation, because the guard only requires "not always biggest" and "some
decoy sometimes bigger" — both of which passed. That framing was too weak: **both edge-condition
checks pass even when there is a real, systematic DISTRIBUTIONAL correlation between diff size and
culprit-vs-decoy role**, and there was one here.

Re-measured directly against the code as it existed before this fix (`generate_benchmark`,
seed=42):

| Sample | culprit diff_chars (mean / median / min / max) | decoy diff_chars (mean / median / min / max) | mean culprit fractional rank (0=biggest, 1=smallest) |
|---|---|---|---|
| n=50 | 37.22 / 37.00 / 32 / 47 | 98.33 / 61.00 / 6 / 276 | **0.7333** |
| n=300 | 37.21 / 37.00 / 32 / 47 | 109.97 / 61.00 / 6 / 276 | **0.6600** |

The culprit's diff was **tightly bounded to 32-47 characters in every single case** (the fixed-
length defect sentence `f" Set {pname} to true/false as needed."`), while 2 of the 3 decoy tiers
("medium" ~65 chars, "large" ~230 chars) unconditionally exceed that range by construction. This is
not sampling noise — it is a deterministic consequence of the tier-size choices, and it is the
direct, mechanistic explanation for `baseline_largest_textual_diff`'s previously reported 4.0%
top-1 (below the 26.7% random floor): the benchmark was systematically pointing that heuristic at
the wrong tool.

### 7b. The fix (Task 3b)

`agentgauge/attribution_benchmark.py`, commit `6c4571d`: the true culprit now ALSO draws an
independent camouflage tier from the same `_DECOY_TIERS` distribution decoys use, appended after
the mandatory (unchanged, verbatim) defect sentence. A first attempt at exactly this — append-only,
no other change — was measured and rejected before shipping: it moved the bias to the *other*
direction (mean fractional rank 0.34-0.36 at n=50/n=300) because the defect sentence's own ~32-47
char floor has no decoy-side counterpart, making the culprit's total diff systematically bigger
instead of smaller. The shipped fix additionally gives every decoy a matching fixed-length,
zero-causal-effect floor sentence (`_DECOY_FLOOR_FILLER`, 38 chars, sized inside the defect
sentence's measured 32-47 char range) before its own tier suffix, so both culprit and decoy start
from a comparable floor before the same independently-drawn tier is layered on top. This
camouflage/floor mechanism is disclosed in the module docstring as exactly what it is: synthetic
benchmark-construction plumbing bolted onto the real, causally-validated `type_enum_contradiction`
defect for decorrelation purposes, not part of the real defect itself — the defect-triggering
sentence (type flip + boolean phrase) is present verbatim in every case, unchanged by this fix.

Re-measured post-fix (`fractional_rank_from_diffs`, same methodology as 7a):

| Sample | culprit diff_chars (mean / median / min / max) | decoy diff_chars (mean / median / min / max) | mean culprit fractional rank |
|---|---|---|---|
| n=50 | 144.42 / 96.00 / 38 / 316 | 154.20 / 99.00 / 44 / 314 | **0.6113** |
| n=300 | 144.35 / 96.00 / 38 / 317 | 152.41 / 99.00 / 44 / 314 | **0.5536** |

Both mean and median diffs are now close between culprit and decoy pool (vs. a ~2.6-3x mean gap
pre-fix), and the mean fractional rank sits much closer to the 0.5 null than the pre-fix
0.66-0.73 — not exactly 0.5 (the residual gap is sampling noise in the tier draw counts at these
sample sizes, not a remaining structural bias; see the commit `6c4571d` message for the exact
tier-count diagnostic). `TestConfoundGuard::test_culprit_diff_size_distribution_not_correlated_with_role`
(band [0.35, 0.65]) and `agentgauge.audit.check_benchmark_construction_diffsize_bias` (same band,
BLOCK severity, commit `6ae80d8`) both pass on the corrected generator and both fail on the
pre-fix numbers above — verified directly, not asserted.

### 7c. Corrected confound-guard report (n=50, seed=42, post-fix)

| Check | Pre-fix (original report, section 5) | Post-fix (corrected) |
|---|---|---|
| Distinct culprit positions observed | 6 | 6 |
| Cases where culprit IS max-diff tool | 2/50 (4.0%) | 12/50 (24.0%) |
| Cases where >=1 decoy diff EXCEEDS culprit | 48/50 (96.0%) | 38/50 (76.0%) |
| Mean culprit fractional rank | ~0.66-0.73 (dev-time estimate; 7a gives the real number) | **0.6113** |

The "culprit is max-diff tool" rate moving from an artificially low 4.0% to a more plausible 24.0%
(roughly what a role-independent 1-of-~4-changed-tools process would produce) is itself evidence
the fix worked as intended, not just the fractional-rank statistic in isolation.

### 7d. Corrected 6-method accuracy/budget table (n=50, seed=42, post-fix; `scripts/attribution_benchmark_report.py`)

| Method | top-1 | top-3 | mean probes | vs. exhaustive | Pre-fix top-1 (section 2) |
|---|---|---|---|---|---|
| exhaustive_ablation (a) | 100.0% | 100.0% | 3.96 | reference | 100.0% |
| **sampled_shapley (b)** | **68.0%** | 98.0% | 1.92 | sub-exhaustive | 74.0% |
| greedy_bisection (c) | 100.0% | 100.0% | 2.78 | sub-exhaustive | 100.0% |
| largest_textual_diff (i) | 24.0% | 72.0% | 0 | — | 4.0% |
| most_lint_violations (ii) | 62.0% | 82.0% | 0 | — | 64.0% |
| uniform_random (iii), one draw | 26.0% | 76.0% | 0 | — | 30.0% |
| uniform_random (iii), analytic expectation | 30.1% | 78.2% | 0 | — | 26.7% |

`largest_textual_diff` moving from 4.0% (below-random, the direct symptom of the bug) to 24.0%
(close to the ~26-30% random floor, as a role-independent diff-size heuristic should measure on
this corpus) is the single clearest confirmation that the confound is gone — a heuristic that
previously performed *worse than chance by construction* now performs *approximately at chance*,
which is what "diff size carries no real localization signal in this specific injected-defect
class" should actually look like.

### 7e. Ship-bar verdict — CHANGED (headline)

**`sampled_shapley` no longer clears the doctrine's ship bar** (top-1 ≥ 0.70 AND top-3 ≥ 0.90 AND
sub-exhaustive budget): 68.0% top-1 is below the 70% bar. Only **`greedy_bisection`** still clears
it (100.0%/100.0%/2.78 mean probes, sub-exhaustive).

| Strategy | top-1 | top-3 | mean probes | sub-exhaustive? | Verdict (corrected) | Verdict (original, section 3) |
|---|---|---|---|---|---|---|
| exhaustive_ablation | 100.0% | 100.0% | 3.96 | No (reference) | does not clear (reference) | does not clear (reference) |
| sampled_shapley | 68.0% | 98.0% | 1.92 | Yes | **does NOT clear** (top-1 < 0.70) | CLEARS |
| greedy_bisection | 100.0% | 100.0% | 2.78 | Yes | **CLEARS** | CLEARS |

This is reported plainly as the headline of this correction, per the task's explicit instruction:
**the corrected benchmark still shows one strategy (`greedy_bisection`) clearing the doctrine's
ship bar, but the number of clearing strategies dropped from two to one.** `sampled_shapley`'s
68.0% top-1 is close to the 70% bar (a 2-percentage-point miss, i.e. 1 case out of 50) — this
should be read as "does not currently clear," not "structurally cannot," and is a candidate for a
larger-n re-measurement or a budget increase (`_sampled_shapley_budget` is deliberately capped at
~half of `n_changed`) before being written off, but that follow-up is out of this task's scope and
is not performed here. The doctrine's own bar is binary; softening it after seeing this specific
number would be exactly the "fitting the metric after seeing the results" this repo's doctrine
forbids, so it is reported as a miss, not rounded up.

### 7f. Task 3c — `most_lint_violations` recheck

Re-measured on the corrected 50-case benchmark: **62.0% top-1 / 82.0% top-3** — within noise of
the original 64.0%/80.0% (moved -2pp top-1, +2pp top-3; the diff-size fix does not touch this
baseline's own logic or its inputs' schema content, so this small movement is expected sampling
variance from the regenerated corpus, not a real effect of the fix).

The more important finding, from directly investigating the mechanism (not just re-running the
number): **68% of the 50 cases (34/50) have a TIE at the top of the raw violation-count ranking.**
The true culprit's mandatory defect sentence both (a) triggers the new BLOCKING
`type_enum_contradiction` violation and (b) newly MENTIONS the flipped parameter's name, which
simultaneously satisfies the pre-existing INFO-severity `required_not_mentioned` check for that
same property — netting the culprit's raw violation-COUNT delta to exactly **0** in 34/50 cases,
despite a real, guaranteed BLOCKING-severity gain in every case. Decoys never trigger
`type_enum_contradiction` (confirmed directly: only `required_references_missing_property` /
`required_not_mentioned` ever fire on decoys, and only as incidental *decreases*, never increases —
they never out-rank the culprit via a genuine competing blocking signal). With the raw count tied
at 0 in most cases, `baseline_most_lint_violations`'s ranking falls back to `changed_tools` list
order (Python's stable sort), so a large share of its "hits" are position luck, not a real
count-based signal.

**This is reported as a finding about the heuristic, not fixed by redefining the baseline**, per
the task's explicit instruction. A trivial severity-aware check (does the tool carry >=1 BLOCKING
violation at all, ignoring count) identifies the true culprit in **100% of the same 50 cases** —
confirming this is a genuine property of raw-count ranking's severity-blindness (a real limitation
of the heuristic as specified), not primarily a construction artifact of this specific benchmark
(decoys do not spuriously trip the blocking check; the offset is a real side effect of the defect
sentence needing to *name* the parameter it mutates, interacting with a real INFO-severity check).
`baseline_most_lint_violations`'s implementation is unchanged. Locked in by
`tests/test_attribution_benchmark.py::TestBaselineMostLintViolationsRawCountOffsetOnBenchmark`
(commit `10d977b`).

### 7g. Artifact log and standing check

Logged as **measurement artifact #9** in `agentgauge/audit.py`'s module docstring and
`tests/test_audit.py`'s enumerated historical-case list (both updated, commit `6ae80d8`), matching
this repo's established eight-artifact-class format. `agentgauge.audit.check_benchmark_construction_diffsize_bias`
is a new, standalone, duck-typed standing check (mean fractional rank vs. the 0.5 null, band
[0.35, 0.65], BLOCK severity) that any injected-culprit benchmark generator's case output can be
run through before its accuracy numbers are trusted — tested against a deliberately-biased fixture
(fires), an unbiased fixture (does not fire), and the real corrected `generate_benchmark()` output
(does not fire). **Not yet wired into `run_audit`'s top-level dispatcher** — that reshaping is
scoped separately (v0.5 Wave 1 Task 5a), since `run_audit`'s current signature is built around
`BlindTask`/tool-based `diff`/`eval` inputs, not benchmark-generator case objects.

### 7h. Reproduction

`uv run python scripts/attribution_benchmark_report.py`, seed=42, commit `6ae80d8` (this
correction's final commit) or later. Task 3a's pre-fix numbers in 7a are reproducible by checking
out commit `2976893` (or any commit before `6c4571d`) and running the same script / the analysis in
`6c4571d`'s commit message.

### 7i. Effect-size sensitivity follow-up (v0.5 Wave 1, 2026-07-26)

Everything above (sections 2/3/5's original numbers, and this section 7's correction) was measured
at ONE effect size: the true culprit's injected effect drawn from a fixed 13.3-28.9pp range — a
large, well-separated signal explicitly flagged in section 4's "NOT MEASURED" caveat as favorable
relative to the harness's own detection power. `reports/v0_5_effect_size_sensitivity.md` extends
this same corrected benchmark generator (`agentgauge.attribution_benchmark.generate_benchmark`'s
new `effect_min_pp`/`effect_max_pp` parameters) across five effect bands spanning 3.0-33.0pp,
including below and straddling the harness's own measured MDE, to determine the true effect size
below which top-1 accuracy stops clearing the doctrine's 0.70 bar for `greedy_bisection` and
`sampled_shapley` — see that report for the per-band accuracy/budget table, the confound guard
re-verified independently at every band, and a mechanism investigation into why accuracy degrades
near the detection threshold (including an implementation-level finding this study surfaced that
was invisible in the single-favorable-effect-size measurement above).

### 7j. CORRECTION (2026-07-26, same day) — the effect-size study's implementation finding also
### changes THIS section's headline ship-bar verdict, on the original 50-case benchmark

**Section 7's table above (and its "greedy_bisection clears the ship bar decisively" verdict) is
now itself superseded.** The bug 7i's follow-up study found in `agentgauge/attribution.py`'s
`_bisect_within`/`attribute_greedy_bisection` (probe cost silently dropped from `probes_consumed`
on every search-failure path, including the always-failing "check for a second culprit" pass every
single-culprit case triggers once the real culprit is found) was not specific to the low-effect
bands it was discovered in — it fires on ANY case where a bisection sub-search fails to find a
significant tool, which includes the guaranteed second search in every one of THIS section's
original 50 cases too. Fixed in commit `f432f5a`; re-running `scripts/attribution_benchmark_report.py`
against the fixed code, same seed=42, same 50 cases:

| Method | top-1 | top-3 | mean probes | vs. exhaustive (3.96) | Ship bar |
|---|---|---|---|---|---|
| exhaustive_ablation | 100.00% | 100.00% | 3.96 | reference | does not clear (reference) |
| sampled_shapley | 68.00% | 98.00% | 1.92 | sub-exhaustive | does not clear (top-1 < 0.70) |
| **greedy_bisection** | 100.00% | 100.00% | **5.32** (was 2.78) | **NOT sub-exhaustive** (was "clears") | **does NOT clear** |
| largest_textual_diff | 24.00% | 72.00% | 0 | — | baseline |
| most_lint_violations | 62.00% | 82.00% | 0 | — | baseline |
| uniform_random (analytic) | 30.07% | 78.20% | 0 | — | baseline (floor) |

**Headline: with honest probe accounting, ZERO of the three probe-based strategies clear the
doctrine's ship bar on this benchmark** (top-1≥0.70 AND top-3≥0.90 AND sub-exhaustive budget).
`greedy_bisection` still finds the true culprit with perfect accuracy (100%/100%, unchanged — the
accuracy numbers were never wrong, only the cost accounting was), but its REAL cost — including the
"confirm there's no second culprit" pass its multi-culprit-capable design always pays for, even when
(as in every case this benchmark generates) there is only ever one — now measures at 5.32 mean
probes, 34% MORE than exhaustive ablation's 3.96. A localizer that costs more than a full re-eval
has no value, per spec section 4's own framing; this is reported as exactly that finding, not
softened. The previously reported "2.78 mean probes, decisively sub-exhaustive" figure in section 7
above was real code, run correctly, measuring a real accuracy result — it was the *cost* half of the
measurement that silently undercounted, not a fabricated number, but the conclusion drawn from it
("clears the ship bar") does not survive the fix and is retracted here, not merely caveated.

This does NOT necessarily mean the feature is dead: the wasted "confirm no second culprit" pass is
overhead specifically because this benchmark only ever injects ONE true culprit — in a genuinely
multi-culprit scenario (2-3 simultaneous real regressions, the realistic multi-file-PR shape per
spec's own framing), that same pass is doing necessary work, not wasted work, and the cost
comparison against exhaustive ablation could look very different. **This is exactly what the
separately-scoped scale/multi-culprit study (Task 2 of this validation wave) is measuring next** —
this section's corrected verdict should be read as "does not clear on THIS single-culprit
benchmark," not yet as a final verdict on the feature. See `reports/v0_5_wave1_report.md`'s Wave 1.5
consolidation (once written) for the overall recommendation across all of Tasks 1-4.

Reproduction: `uv run python scripts/attribution_benchmark_report.py` at commit `f432f5a` or later.
