# AgentGauge v0.5 Wave 1 — scale-curve + multi-culprit study for failure attribution
## (Component 1.2, Task 2; follow-up to `reports/v0_5_attribution_benchmark.md` section 7j)

> **THIS ENTIRE REPORT'S ACCURACY/BUDGET NUMBERS ARE SUPERSEDED (2026-07-30, measurement artifact
> #10).** `agentgauge.attribution_benchmark.make_probe_fn`/`make_multi_probe_fn`'s synthetic
> ground-truth model understated real variance -- see `reports/v0_5_mde_discrepancy.md` section 4c
> for the recomputed single-culprit and multi-culprit tables. **Headline of the correction: this
> report's central claim ("greedy_bisection clears the full ship bar at every single-culprit
> candidate-set size >= 10 tools") is FALSE under corrected noise.** Budget still improves with
> scale as this report found, but ACCURACY now COLLAPSES with scale instead (93%->80%->73%->47%
> top-1 as n_changed goes 4->10->20->40) -- `greedy_bisection` fails the ship bar at n=20 and n=40,
> the sizes closest to the target buyer's real use case. `sampled_shapley` shows the OPPOSITE
> scaling and now clears the full ship bar at every size >= 10 (including n=40, 100%/100%) --
> exactly reversing this report's implicit "greedy_bisection over sampled_shapley at scale"
> framing. The multi-culprit conclusion (neither strategy clears any tested configuration) is
> unchanged in direction. Do not cite this report's numbers without reading the corrected ones.

Direct follow-up to the open question `reports/v0_5_attribution_benchmark.md` section 7j leaves
unresolved: with honest probe-cost accounting, `greedy_bisection`'s always-attempted "confirm
there's no second culprit" pass costs MORE than exhaustive ablation (5.32 vs 3.96 mean probes) on
the original 50-case benchmark — but that benchmark, and `reports/v0_5_effect_size_sensitivity.md`,
both inject exactly ONE true culprit into a small (2-6-tool) candidate set. Is the wasted pass
*necessarily* wasteful, or only wasteful in that specific narrow regime? This report measures two
axes the prior studies never varied: **candidate-set size** (Task 2a: n_changed pinned to
4/10/20/40, still single-culprit) and **true culprit count** (Task 2b: 2 and 3 simultaneous real
culprits in one changed set).

**Headline: the original benchmark's negative verdict was a small-n, single-culprit-only artifact,
not a property of the feature itself.** At every single-culprit candidate-set size ≥ 10,
`greedy_bisection` clears the doctrine's full ship bar (100%/100% accuracy, genuinely
sub-exhaustive) — the crossover from "more expensive than exhaustive" to "cheaper" happens between
n_changed=4 and n_changed=10, exactly the range the original 50-case benchmark (n_changed drawn
from 2-6) never escaped. With multiple real culprits, the picture is genuinely mixed and
scale-dependent, not simply "fixed": `greedy_bisection` clears the ship bar with 2 simultaneous
culprits at n_changed=20 (-16.8% vs exhaustive) and with 3 simultaneous culprits at n_changed=40
(-33.4%), but **fails to clear it with 3 simultaneous culprits at n_changed=20** (+8.7% vs
exhaustive, i.e. genuinely more expensive) — even though its accuracy there is still excellent
(98.89% recall, 96.67% strict top-3). `sampled_shapley` is sub-exhaustive at every tested bucket by
construction (its budget is a fixed ~50% of n_changed), but its accuracy collapses below the ship
bar the instant more than one true culprit is present, at every size tested.

All numbers below are reproducible: `uv run python scripts/scale_curve_report.py`, seed family
documented in §2, commit `fca0aaa` (`feat(scripts): scale-curve + multi-culprit measurement run`)
or later. Zero live LLM calls — same deterministic synthetic ground-truth model as
`reports/v0_5_attribution_benchmark.md` and `reports/v0_5_effect_size_sensitivity.md`.

## 1. Scoring convention — read this before any table below

**Multi-culprit ground truth does not unambiguously generalize "top-k accuracy."** Two conventions
are reported side by side, defined here BEFORE any result was measured (not fitted after seeing
numbers):

- **`top1_strict` / `top3_strict`**: does the top-k ranked list contain **ALL** true culprits (a
  strict, all-or-nothing set-containment check)? At `k=1` this is only satisfiable when there is
  exactly one true culprit (`m=1`) — for `m≥2` buckets, `top1_strict` is included in every table
  for transparency/continuity but is **expected to be near-zero by construction**, not a
  meaningful signal (you cannot fit 2-3 items into 1 ranked slot). `top3_strict` is the doctrine's
  original top-3 metric, unchanged in definition, generalized to require ALL true culprits (not
  just one) within the top 3.
- **`recall@m`** (partial credit, `m = len(true_culprits)`): the fraction of true culprits present
  in the top-`m` ranked list. This is `recall@|true_culprits|` — the tightest k that could
  plausibly contain every true culprit, scored proportionally rather than all-or-nothing.

**Both conventions reduce EXACTLY to the original single-culprit metrics when `m=1`**:
`recall@1 == top1_strict == agentgauge.attribution.top_k_hit(result, culprit, 1)`'s 0/1 value, and
`top3_strict == top_k_hit(..., 3)`. This is not a coincidence — it is why the single-culprit
bucket rows below are numerically comparable to `reports/v0_5_attribution_benchmark.md`'s and
`reports/v0_5_effect_size_sensitivity.md`'s existing tables, not merely analogous to them.

**Generalized ship bar** (used throughout this report in place of the doctrine's literal top-1/
top-3 wording, since top-1 alone is not meaningful for `m≥2`): **`recall@m ≥ 0.70` AND
`top3_strict ≥ 0.90` AND mean probes strictly below `exhaustive_ablation`'s (`= n_changed`,
always, by definition).** At `m=1` this is byte-for-byte the doctrine's original bar.

`largest_textual_diff` / `most_lint_violations` (zero-probe baselines, unchanged implementations)
and `uniform_random`'s single realized draw are scored against multi-culprit truth using the exact
same `top1_strict`/`top3_strict`/`recall@m` functions — no separate multi-culprit-aware version of
either baseline was written (none was needed; both already produce a ranking over `changed_tools`).

**`uniform_random`'s analytic expectation was rederived, not reused unchanged**, per the task's
explicit instruction:
- `E[recall@k] = k / n_changed`, **independent of `m`** — by linearity of expectation, each
  individual true culprit independently has probability `k/n_changed` of landing in a random
  k-subset of a uniform permutation, and recall@k is the mean of `m` such indicators, each with
  that same expectation regardless of `m` or which other items are marked. This is numerically
  identical to `agentgauge.attribution.expected_topk_accuracy(n, k)` (reused directly, not
  reimplemented, in `scripts/scale_curve_report.py::expected_recall_at_k_uniform`).
- `P(all m true culprits in the top k) = C(n_changed - m, k - m) / C(n_changed, k)` for `k ≥ m`,
  else exactly `0` — the standard hypergeometric containment probability, since the SET of items
  occupying the first k positions of a uniformly random permutation is itself a uniformly random
  k-subset of the n items (`scripts/scale_curve_report.py::expected_strict_topk_uniform`).

## 2. What was measured, and how

`agentgauge.attribution_benchmark.generate_benchmark`'s new `n_changed: int | None` parameter
(Task 2a) pins every generated case's candidate-set size instead of drawing it from the original
2-6 range; the default (`n_changed=None`) is unchanged and remains byte-identical to every
existing caller. Corpus catalogs top out at 60 tools (confirmed directly against
`evals/fixtures/v2_tool_definitions.json`, not assumed), so n_changed=40 is achievable without
silently capping — 8 of the corpus's 39 deduplicated catalogs have ≥40 tools.

`agentgauge.attribution_benchmark.generate_multi_culprit_benchmark` + `MultiCulpritBenchmarkCase`
+ `make_multi_probe_fn` (Task 2b) inject 2 or 3 independently-drawn real `type_enum_contradiction`
defects into one changed set, each with its own independently-drawn effect magnitude from the same
13.3-28.9pp measured causal range the single-culprit benchmark uses. **Effect combination is
additive**: each active (not-yet-reverted) culprit contributes its own penalty independently;
reverting a subset removes exactly the summed penalty of the reverted culprits, leaving every
other active culprit's penalty untouched. This is a direct, drop-in generalization of the
single-culprit ground-truth model — with `m=1` it reduces to numerically identical arithmetic
(locked by `tests/test_scale_curve.py::TestMakeMultiProbeFn::
test_reduces_to_single_culprit_model_at_n_culprits_1`).

**Buckets measured** (`N_CASES_PER_BUCKET = 30` per bucket, this study's own seed family — see
`scripts/scale_curve_report.py` for exact values, deliberately distinct from
`reports/v0_5_effect_size_sensitivity.md`'s per-band seeds so no reader mistakes the two studies
for sharing cases):

| Bucket | n_changed | n_culprits (m) | n_cases |
|---|---|---|---|
| single_n4 | 4 | 1 | 30 |
| single_n10 | 10 | 1 | 30 |
| single_n20 | 20 | 1 | 30 |
| single_n40 | 40 | 1 | 30 |
| multi_c2_n20 | 20 | 2 | 30 |
| multi_c3_n20 | 20 | 3 | 30 |
| multi_c3_n40 | 40 | 3 | 30 |

The last row (`multi_c3_n40`) was **added after** `multi_c2_n20`/`multi_c3_n20` ran and showed
`greedy_bisection` crossing back over exhaustive's cost at 3 culprits/n_changed=20 — not to chase
a favorable number (the outcome of adding it was unknown at the time), but because Task 2c
explicitly asks "at what size does cost cross below n_changed," and a single n_changed=20 data
point cannot show whether a larger candidate set rescues the 3-culprit case the way it rescues the
single-culprit case between n_changed=4 and n_changed=40. This addition, and the reasoning for it,
is disclosed here rather than silently folded into "the plan all along" — see
`scripts/scale_curve_report.py`'s `MULTI_BUCKETS` comment for the same disclosure in code.

**Runtime**: full run (7 buckets × 30 cases × 6 methods, all real probes through the real
`agentgauge.harness.diff_server_level` estimator) completes in ~161s on this machine — well within
the "tens of minutes, not hours" budget; no case-count reduction was needed at any bucket size,
including n_changed=40.

## 3. Confound guard — re-verified at every bucket, not assumed to generalize

**Single-culprit buckets** (`confound_guard_report` + `agentgauge.audit.
check_benchmark_construction_diffsize_bias`, the exact two checks
`reports/v0_5_attribution_benchmark.md` section 7 established):

| Bucket | n_positions_observed | frac culprit is max-diff | frac decoy exceeds culprit diff | mean fractional rank | audit BLOCK fired | PASSED |
|---|---|---|---|---|---|---|
| single_n4 | 4 | 0.3333 | 0.6667 | 0.4944 | No | Yes |
| single_n10 | 10 | 0.1000 | 0.9000 | 0.5389 | No | Yes |
| single_n20 | 15 | 0.0667 | 0.9333 | 0.6360 | No | Yes |
| single_n40 | 20 | 0.2000 | 0.8000 | 0.5154 | No | Yes |

All four pass the same `[0.35, 0.65]` fractional-rank band the original 50-case benchmark used —
**no bias reappeared or worsened at the extreme n_changed=40 size**, directly answering the task's
explicit concern that a construction bias "could plausibly reappear or worsen at extreme sizes."

**Multi-culprit buckets** (`multi_confound_guard_report` — a SEPARATE, explicitly-generalized set
of checks; the single-culprit guard's `.true_culprit`-singular semantics do not apply to a case
with 2-3 true culprits, so `agentgauge.audit.check_benchmark_construction_diffsize_bias` is **not**
called on these cases at all — see `MultiConfoundGuardReport`'s field docstrings in
`agentgauge/attribution_benchmark.py` for exactly how each single-culprit definition below was
generalized, not silently reused unchanged):

| Bucket | n_positions_observed | frac *a* culprit is max-diff | frac decoy exceeds *min* culprit diff | mean per-culprit-instance fractional rank | before-arm floor-clip rate | PASSED |
|---|---|---|---|---|---|---|
| multi_c2_n20 | 19 | 0.1333 | 0.9667 | 0.6171 | 0.0000 | Yes |
| multi_c3_n20 | 20 | 0.4000 | 1.0000 | 0.5245 | 0.0000 | Yes |
| multi_c3_n40 | 36 | 0.3667 | 0.9667 | 0.4916 | 0.0333 | Yes |

All three pass. The **before-arm floor-clip rate** (a NEW diagnostic this study adds, not present
in either prior report: the fraction of synthetic "before"-arm task rates that hit
`CALIBRATED_BASELINE_RATE`'s 0.0 floor before noise, i.e. `CALIBRATED_BASELINE_RATE -
sum(all active culprits' magnitudes) ≤ 0`) is measured directly rather than assumed away: **0.00%
at m=2 and at m=3/n_changed=20, rising to 3.33% at m=3/n_changed=40** (larger n_changed draws more
distinct culprit-effect combinations across 30 cases, occasionally landing near the extreme end of
the 13.3-28.9pp×3 range). This is small but genuinely nonzero — flagged as a known limitation of
the additive ground-truth model at the high end of the causal-effect range, not hidden. See §7 for
the honest caveat this implies.

## 4. Consolidated accuracy / budget table — all 7 buckets

| Bucket | Method | top1_strict | top3_strict | recall@m | mean probes | vs. exhaustive |
|---|---|---|---|---|---|---|
| **single_n4** (n=4, m=1) | exhaustive_ablation | 100.00% | 100.00% | 100.00% | 4.00 | reference |
| | sampled_shapley | 60.00% | 93.33% | 60.00% | 2.00 | sub-exh (-50.0%) |
| | greedy_bisection | 100.00% | 100.00% | 100.00% | 6.00 | **MORE EXPENSIVE (+50.0%)** |
| | largest_textual_diff | 30.00% | 70.00% | 30.00% | 0 | — |
| | most_lint_violations | 60.00% | 86.67% | 60.00% | 0 | — |
| | uniform_random (draw) | 13.33% | 80.00% | 13.33% | 0 | — |
| | uniform_random (analytic) | 25.00% | 75.00% | 25.00% | 0 | — |
| **single_n10** (n=10, m=1) | exhaustive_ablation | 100.00% | 100.00% | 100.00% | 10.00 | reference |
| | sampled_shapley | 90.00% | 100.00% | 90.00% | 5.00 | sub-exh (-50.0%) |
| | greedy_bisection | 100.00% | 100.00% | 100.00% | 9.37 | sub-exh (-6.3%) |
| | largest_textual_diff | 6.67% | 26.67% | 6.67% | 0 | — |
| | most_lint_violations | 46.67% | 56.67% | 46.67% | 0 | — |
| | uniform_random (draw) | 13.33% | 23.33% | 13.33% | 0 | — |
| | uniform_random (analytic) | 10.00% | 30.00% | 10.00% | 0 | — |
| **single_n20** (n=20, m=1) | exhaustive_ablation | 100.00% | 100.00% | 100.00% | 20.00 | reference |
| | sampled_shapley | 100.00% | 100.00% | 100.00% | 10.00 | sub-exh (-50.0%) |
| | greedy_bisection | 100.00% | 100.00% | 100.00% | 11.50 | sub-exh (-42.5%) |
| | largest_textual_diff | 3.33% | 3.33% | 3.33% | 0 | — |
| | most_lint_violations | 30.00% | 43.33% | 30.00% | 0 | — |
| | uniform_random (draw) | 6.67% | 13.33% | 6.67% | 0 | — |
| | uniform_random (analytic) | 5.00% | 15.00% | 5.00% | 0 | — |
| **single_n40** (n=40, m=1) | exhaustive_ablation | 100.00% | 100.00% | 100.00% | 40.00 | reference |
| | sampled_shapley | 100.00% | 100.00% | 100.00% | 20.00 | sub-exh (-50.0%) |
| | greedy_bisection | 100.00% | 100.00% | 100.00% | 13.67 | sub-exh (-65.8%) |
| | largest_textual_diff | 16.67% | 16.67% | 16.67% | 0 | — |
| | most_lint_violations | 16.67% | 16.67% | 16.67% | 0 | — |
| | uniform_random (draw) | 3.33% | 3.33% | 3.33% | 0 | — |
| | uniform_random (analytic) | 2.50% | 7.50% | 2.50% | 0 | — |
| **multi_c2_n20** (n=20, m=2) | exhaustive_ablation | 0.00% | 100.00% | 100.00% | 20.00 | reference |
| | sampled_shapley | 0.00% | 50.00% | 53.33% | 10.00 | sub-exh (-50.0%) |
| | greedy_bisection | 0.00% | 100.00% | 100.00% | 16.63 | sub-exh (-16.8%) |
| | largest_textual_diff | 0.00% | 3.33% | 10.00% | 0 | — |
| | most_lint_violations | 0.00% | 13.33% | 28.33% | 0 | — |
| | uniform_random (draw) | 0.00% | 6.67% | 16.67% | 0 | — |
| | uniform_random (analytic) | 0.00% | 1.58% | 10.00% | 0 | — |
| **multi_c3_n20** (n=20, m=3) | exhaustive_ablation | 0.00% | 100.00% | 100.00% | 20.00 | reference |
| | sampled_shapley | 0.00% | 6.67% | 50.00% | 10.00 | sub-exh (-50.0%) |
| | greedy_bisection | 0.00% | 96.67% | 98.89% | 21.73 | **MORE EXPENSIVE (+8.7%)** |
| | largest_textual_diff | 0.00% | 0.00% | 18.89% | 0 | — |
| | most_lint_violations | 0.00% | 20.00% | 38.89% | 0 | — |
| | uniform_random (draw) | 0.00% | 0.00% | 13.33% | 0 | — |
| | uniform_random (analytic) | 0.00% | 0.09% | 15.00% | 0 | — |
| **multi_c3_n40** (n=40, m=3) | exhaustive_ablation | 0.00% | 100.00% | 100.00% | 40.00 | reference |
| | sampled_shapley | 0.00% | 40.00% | 77.78% | 20.00 | sub-exh (-50.0%) |
| | greedy_bisection | 0.00% | 100.00% | 100.00% | 26.63 | sub-exh (-33.4%) |
| | largest_textual_diff | 0.00% | 3.33% | 18.89% | 0 | — |
| | most_lint_violations | 0.00% | 20.00% | 26.67% | 0 | — |
| | uniform_random (draw) | 0.00% | 0.00% | 7.78% | 0 | — |
| | uniform_random (analytic) | 0.00% | 0.01% | 7.50% | 0 | — |

`top1_strict` is 0.00% in every `m≥2` row exactly as expected by the metric's own definition (§1)
— not a strategy failure, a structural consequence of asking "does 1 slot contain 2-3 items."

## 5. The central question: does `greedy_bisection`'s wasted pass stop being wasted with a real second culprit?

**Direct answer: NOT simply "yes" — the honest answer is scale-dependent, and the mechanism is
measurable, not hand-wavy.**

`greedy_bisection`'s outer loop always runs `(true culprit count) + 1` bisection search passes:
one successful `O(log n_changed)`-cost search per real culprit it isolates, plus exactly one final
FAILED search confirming there is no additional culprit beyond however many actually exist. **That
final confirmation pass is wasted overhead in EVERY case, single- or multi-culprit alike** — it
never finds anything, by construction, once every real culprit has already been found. What changes
with more real culprits is that the *other* `m` passes (which were entirely absent in the
single-culprit-only original benchmark's failure mode) are each genuinely productive, diluting the
one fixed wasted pass as a shrinking fraction of a larger, more useful total.

The measured mean-probe costs closely track the mechanistic estimate
`(m + 1) × (⌈log₂(n_changed)⌉ + 1)` (m successful searches + 1 wasted confirmation, each costing
roughly one bisection-depth's worth of probes plus a final isolation/confirmation probe):

| Bucket | m | n_changed | Formula estimate | Measured mean probes | Exhaustive (n_changed) |
|---|---|---|---|---|---|
| single_n4 | 1 | 4 | 2 × 3 = 6 | 6.00 | 4 |
| single_n10 | 1 | 10 | 2 × 5 = 10 | 9.37 | 10 |
| single_n20 | 1 | 20 | 2 × 6 = 12 | 11.50 | 20 |
| single_n40 | 1 | 40 | 2 × 7 = 14 | 13.67 | 40 |
| multi_c2_n20 | 2 | 20 | 3 × 6 = 18 | 16.63 | 20 |
| multi_c3_n20 | 3 | 20 | 4 × 6 = 24 | 21.73 | 20 |
| multi_c3_n40 | 3 | 40 | 4 × 7 = 28 | 26.63 | 40 |

(The formula is a slight overestimate throughout because later searches in the outer loop operate
over the shrinking remainder after earlier culprits are removed, which is cheaper than searching
the full `n_changed` set each time — a real, minor economy the formula does not capture.)

Because `greedy_bisection`'s cost grows **linearly in `m`** but only **logarithmically in
`n_changed`**, while `exhaustive_ablation`'s cost is always exactly `n_changed` (linear in
`n_changed`, independent of `m`), **whether the wasted pass is affordable is jointly determined by
BOTH axes, not by culprit count alone**:

- Holding `m=1` fixed and growing `n_changed` (Task 2a): the wasted pass's cost is fixed at
  `~⌈log₂(n)⌉+1`, shrinking relative to `n_changed` as `n_changed` grows — crossover from
  MORE-expensive to sub-exhaustive happens between n_changed=4 (+50.0%) and n_changed=10 (-6.3%),
  and by n_changed=40 the strategy is dramatically cheaper (-65.8%).
- Holding `n_changed=20` fixed and growing `m` (Task 2b): each additional real culprit adds its
  own full search pass, so total cost grows roughly linearly in `m` while exhaustive's cost stays
  flat at 20 — sub-exhaustive at m=1 (-42.5%) and m=2 (-16.8%), but **crosses back OVER
  exhaustive at m=3 (+8.7%)**, exactly where the linear-in-m growth catches up to the fixed
  n_changed=20 budget.
- Growing `n_changed` again at the SAME `m=3` (the `multi_c3_n40` bucket added specifically to
  test this): the crossover reopens — sub-exhaustive again at n_changed=40 (-33.4%), because
  `n_changed` doubling only grows the per-search log-cost by one extra bisection level, while
  exhaustive's cost doubles outright.

**So: the wasted confirmation pass does not stop being wasted just because a second or third
culprit exists — it is still real, unproductive overhead in every case. What changes is whether
the OTHER, genuinely productive passes' log-scaling advantage is large enough, at the tested
candidate-set size, to absorb that one fixed wasted pass and still beat exhaustive's linear cost.**
At realistic-to-large PR scale (n_changed ≥ 40 in this corpus) it comfortably is, even with 3 real
culprits. At smaller/moderate scale (n_changed=20) with 3 simultaneous culprits, it is not — the
original section 7j finding ("more expensive than exhaustive") genuinely still holds there, not as
an artifact of this study's earlier, narrower benchmark, but as a real, separately-confirmed
result in its own right.

## 6. Budget-crossover table per strategy (Task 2c)

**`sampled_shapley` is sub-exhaustive at EVERY tested bucket** (single and multi alike) — this is
not an emergent finding but a direct, guaranteed consequence of its fixed budget formula
(`_sampled_shapley_budget`, capped at `~⌈n_changed × 0.5⌉`, strictly below `n_changed` for every
`n_changed ≥ 2`): every measured mean-probe figure above is exactly 50.0% of the corresponding
`exhaustive_ablation` figure, at every bucket, by construction.

| Bucket | greedy_bisection mean probes | exhaustive | sub-exhaustive? | vs. exhaustive |
|---|---|---|---|---|
| single_n4 (n=4, m=1) | 6.00 | 4.00 | **No** | +50.0% |
| single_n10 (n=10, m=1) | 9.37 | 10.00 | Yes | -6.3% |
| single_n20 (n=20, m=1) | 11.50 | 20.00 | Yes | -42.5% |
| single_n40 (n=40, m=1) | 13.67 | 40.00 | Yes | -65.8% |
| multi_c2_n20 (n=20, m=2) | 16.63 | 20.00 | Yes | -16.8% |
| multi_c3_n20 (n=20, m=3) | 21.73 | 20.00 | **No** | +8.7% |
| multi_c3_n40 (n=40, m=3) | 26.63 | 40.00 | Yes | -33.4% |

**`greedy_bisection` is sub-exhaustive at every tested single-culprit size ≥ n_changed=10** (the
crossover from the original benchmark's unfavorable n_changed=2-6 regime sits between n_changed=4
and n_changed=10); **in the multi-culprit regime it is sub-exhaustive through 2 simultaneous
culprits at n_changed=20, crosses back to more-expensive at 3 simultaneous culprits at
n_changed=20, and returns to sub-exhaustive at 3 simultaneous culprits once n_changed grows to
40.** No single "X-pp" or "X-tool" threshold cleanly separates every sub-exhaustive bucket from
every more-expensive one — the crossover genuinely depends on both `n_changed` and `m` jointly, as
§5's mechanism analysis shows directly.

## 7. Ship-bar verdict — where does anything clear the doctrine's bar, in this larger space?

Generalized bar (§1): `recall@m ≥ 0.70` AND `top3_strict ≥ 0.90` AND sub-exhaustive mean probes.

| Bucket | sampled_shapley | greedy_bisection |
|---|---|---|
| single_n4 (n=4, m=1) | does not clear (recall 60.00% < 70%) | does not clear (not sub-exhaustive) |
| single_n10 (n=10, m=1) | **CLEARS** (90.00%/100.00%, -50.0%) | **CLEARS** (100.00%/100.00%, -6.3%) |
| single_n20 (n=20, m=1) | **CLEARS** (100.00%/100.00%, -50.0%) | **CLEARS** (100.00%/100.00%, -42.5%) |
| single_n40 (n=40, m=1) | **CLEARS** (100.00%/100.00%, -50.0%) | **CLEARS** (100.00%/100.00%, -65.8%) |
| multi_c2_n20 (n=20, m=2) | does not clear (top3 50.00% < 90%) | **CLEARS** (100.00%/100.00%, -16.8%) |
| multi_c3_n20 (n=20, m=3) | does not clear (top3 6.67% < 90%) | does not clear (98.89%/96.67% accuracy, but +8.7% — fails sub-exhaustive) |
| multi_c3_n40 (n=40, m=3) | does not clear (top3 40.00% < 90%, recall 77.78% ≥ 70%) | **CLEARS** (100.00%/100.00%, -33.4%) |

**Both strategies clear the ship bar somewhere in this expanded space** — this is a genuinely
different and more positive picture than section 7j's "ZERO of three strategies clear the ship bar"
verdict on the original single small-candidate-set benchmark, but the two strategies clear it in
very different regimes:

- **`sampled_shapley`** clears the bar at EVERY single-culprit size ≥ 10 (its sub-exhaustive budget
  is guaranteed by construction; its accuracy is what varies, and it is decisively high at
  moderate-to-large single-culprit sizes) — but **fails at every multi-culprit bucket tested**,
  never once reaching `top3_strict ≥ 90%` once more than one real culprit is present, regardless of
  `n_changed`. Its accuracy ceiling appears to be governed by its fixed sampling budget rather than
  by scale.
- **`greedy_bisection`** clears the bar at every single-culprit size ≥ 10 AND at 2 of the 3
  multi-culprit buckets tested (2-culprit@20, 3-culprit@40) — its accuracy is consistently
  excellent (≥96.67% in every bucket measured, single- or multi-culprit), and its failures against
  the ship bar in this study are ALWAYS a budget failure (not sub-exhaustive), never an accuracy
  failure. The one bucket where it does not clear (3-culprit@20) fails on cost alone, by a narrow
  8.7% margin, and is rescued by doubling `n_changed` alone with no change to the strategy itself.

**Neither strategy clears the ship bar at the smallest tested candidate-set size (n_changed=4,
single-culprit)** — `sampled_shapley` on accuracy, `greedy_bisection` on budget. This matches the
intuition that very small candidate sets (2-4 tools) don't leave enough log-scaling room for
bisection's overhead to pay for itself, and leave `sampled_shapley`'s already-small fixed budget
(2 probes at n=4) too thin to reliably separate signal from noise.

## 8. MEASURED vs. NOT MEASURED

**MEASURED:** every number in §3-§7 comes from running the code in this repo against the
deterministic synthetic ground-truth model (additive combination for multi-culprit, per §2),
routed through the real `agentgauge.harness.diff_server_level` estimator per probe, on 210 total
generated cases (30 per bucket × 7 buckets), seed family disclosed in §2, fully reproducible via
`uv run python scripts/scale_curve_report.py`. Zero live LLM calls. The confound guard (single- and
multi-culprit variants) was re-verified independently at every bucket, not assumed to generalize
from the original 50-case benchmark or from any other bucket.

**NOT MEASURED — read before citing this report's numbers elsewhere:**
- Every caveat in `reports/v0_5_attribution_benchmark.md` §4 and
  `reports/v0_5_effect_size_sensitivity.md` §9 still applies unchanged: this is a favorable-regime
  synthetic benchmark (zero-effect decoys, effect magnitudes at the well-separated end of the
  harness's measured detection power), never run against a real agent + real LLM judge.
- **The additive multi-culprit ground-truth model's floor-clipping caveat (§3)**: at n_changed=40
  with 3 simultaneous culprits, 3.33% of synthetic "before"-arm task rates hit
  `CALIBRATED_BASELINE_RATE`'s 0.0 floor before noise — a real (if small) departure from pure
  additivity at the extreme high end of the combined effect range, not eliminated by construction.
  This was measured directly (`agentgauge.attribution_benchmark.before_arm_floor_clip_rate`), not
  assumed away.
- **Real-world multi-culprit correlation structure is not modeled.** This study's 2-3 simultaneous
  culprits are drawn as fully independent defects with independent effect magnitudes and zero
  interaction — a real multi-file PR's regressions could plausibly interact (e.g. partially
  overlapping failure modes, non-additive combined effects) in ways this additive model, by
  explicit design choice (§2), does not capture. The additive choice was made because it is the
  simplest defensible model, not because interaction effects were measured and found negligible —
  they were not measured at all.
- `sampled_shapley`'s multi-culprit accuracy collapse (never clearing `top3_strict ≥ 90%` at any
  tested `m≥2` bucket) is measured, not diagnosed to a specific mechanism the way §5 diagnoses
  `greedy_bisection`'s cost crossover — a follow-up mechanism investigation (analogous to
  `reports/v0_5_effect_size_sensitivity.md` §6's Mode A/Mode B trace) was out of this task's scope.
- `n_cases=30`/bucket carries real sampling noise, especially visible in the multi-culprit buckets'
  `top1_strict`/small-percentage cells (e.g. `uniform_random`'s single-draw rows) — a larger
  per-bucket `n` would tighten these figures but was not run here (30 was chosen to match this
  study's own stated 20-30 minimum while keeping total runtime well under the stated budget).

## 9. Reproduction

`uv run python scripts/scale_curve_report.py`, seed family per §2, commit `fca0aaa` or later.
Building on `agentgauge/attribution_benchmark.py`'s corrected generator
(post-`6ae80d8`/artifact-#9-fix, per `reports/v0_5_attribution_benchmark.md` §7) and the fixed
`agentgauge/attribution.py` (post-`f432f5a`, per that report's §7j) — this study does not modify
either file, only measures against them.

---

See `reports/v0_5_attribution_benchmark.md` section 7j for the open question this report answers,
and `reports/v0_5_effect_size_sensitivity.md` for the companion axis (true effect magnitude) this
report does not vary (all buckets here use the original 13.3-28.9pp causal-effect range).
