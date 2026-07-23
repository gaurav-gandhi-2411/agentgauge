# Predictive validity study: do AgentGauge's scoring axes predict real task success?

**Date:** 2026-07-23, revised across three same-day sessions (statistical correction + mechanism
test → schema-consistency lead + length-controlled test)
**Branch:** `chore/predictive-validity-study` (not merged to `main`)
**Raw data:** `evals/fixtures/predictive_validity/results_raw.json` (45 manifest entries, 44 valid
records, 1 permanent error — see Repo State below)
**Agent model (ground truth):** `gemma2:9b` · **Judge model (AgentGauge scoring):** `llama3.1:8b`
**Zero-cost:** all inference via Ollama (local + a temporary Cloud Run GPU proxy for Stage B/
Phase 3 collection), no `ANTHROPIC_API_KEY`, no paid third-party API calls.

## FINAL CONCLUSION: FALSIFIED

**The predictive-validity thesis — "AgentGauge's 8-axis quality score predicts real agent task
success" — is FALSIFIED under this study's own pre-registered decision rule.** This is the final
verdict, stated plainly and not walked back in any later section of this report:

1. **Neither axis survives the full test.** `overall_score` — the number a product CI-gate would
   actually threshold on — never reaches significance once corrected for the 8 comparisons this
   study actually tested (Bonferroni/BH, both reject it: p=0.0132 vs. a 0.00625 cutoff).
   `description_quality` survives that correction alone, but controlling for description length
   (a free, zero-LLM-call heuristic) drops its correlation from ρ=0.417 to a **partial ρ=0.308**
   that would **not** survive the same correction bar (p=0.044 vs. 0.00625) — and its own
   pre-registered "beats the best naive baseline by a meaningful margin" requirement was never
   demonstrated in the first place (CI overlaps `baseline_desc_length` almost entirely).
   `overall_score`'s partial correlation, controlling for length, falls to ρ=0.262 and crosses into
   **non-significance even uncorrected** (p=0.089).
2. **There is no axis in this study, at any stage of correction, that has been shown to beat a
   free character-count heuristic by a margin that survives both (a) multiple-comparison correction
   and (b) controlling for description length.** The honest reading of the data: longer descriptions
   score higher on these axes and correlate weakly with better real outcomes — that is not evidence
   the LLM-judged "quality" assessment captures anything beyond what `len()` already gives away.
3. Task 4 (re-architecture and further ground-truth collection to push past this result) is
   **cancelled** — no further GCP provisioning or inference is planned for this study's
   correlation/CONFIRM question. See "Repo state" for exact resource status (fully torn down).

Everything below this point is supporting detail for how this conclusion was reached, plus a
separate, still-live finding (the schema-consistency lead) that does not rescue the falsified
thesis but is a genuine, if small-sample, empirical result in its own right — see "Schema-
consistency checker: full results."

## History of this conclusion (for provenance, not to soften the verdict above)

**Session 1** (n=18 → n=44 expansion): reported a CONFIRM based on uncorrected significance.
**Session 2** (same day): applied multiple-comparison correction, downgraded CONFIRM to NOT
CONFIRMED, and falsified the leading mechanism (homogenization) for the Phase-3 blind spot — see
"Phase 3 mechanism test" below, which remains accurate and is not superseded by session 3.
**Session 3** (same day): controlled for description length, which is the test that moves the
verdict from NOT CONFIRMED to the stronger, final **FALSIFIED** stated above — `overall_score`'s
residual correlation is no longer even nominally significant once length is accounted for.

**Separately**, the Phase 3 before/after fixer-pair analysis still shows the same **6 of 7 pairs**
where an LLM-rewritten description raises `overall_score` substantially while real task success
stays flat or drops — that empirical pattern is unaffected by any of the statistical corrections
above and remains real. A dedicated mechanism test (session 2) of the leading explanation for
*why* — "the rewrite homogenizes descriptions across tools, reducing discriminability, causing
wrong-tool selection" — **falsifies that specific mechanism**. Properly measured (using the actual
selection-prompt text the agent sees, not bare tool descriptions), similarity between tools
*decreased* (became more differentiated) in 6 of the 7 pairs, not increased, and the
similarity-delta/outcome-delta correlations point the wrong sign for the hypothesis in both
directions tested. Two of the seven pairs (`call_constraints_server`/`_v2`) show 0% wrong-tool
selection in both arms — their outcome is 100% an argument-construction effect, with zero possible
contribution from tool discriminability. See "Phase 3 mechanism test" for the full analysis, and
"Schema-consistency checker: full results" (session 3) for the follow-up lead this produced.
**The blind-spot pattern (score rises, success doesn't) is real and replicates; the homogenization
explanation for it does not; a schema-consistency explanation is a small-sample, suggestive
follow-up lead, not a rescued thesis.**

## Methodology

### What changed since the n=18 version of this report

1. **Manifest expanded 18 → 45** (Stage B): 22 new tool-set fixtures added across 4 real-world API
   mirrors (RW1 GitHub, RW2 AWS IAM, P2A internal proxy, plus a 5th mirror) and 2 synthetic
   catalogs (Q3, Q6), each run through bad/guard-b/oracle description-quality arms, plus a second
   12-tool T18 family subset (data_write + validate families, distinct from the original
   data_fetch + notify subset) for family-independence checking.
2. **Ground truth metric fixed a second time** (Phase 2): the original binary
   `success AND selected_tool == tool_name` metric was degenerate — every example server in this
   repo accepts any well-formed call, so `success` was always `True` regardless of whether
   constructed arguments were actually correct. 44% of Stage-A records tied at an exact 1.0
   ceiling. Replaced with a continuous **fractional constraint-satisfaction score**
   (`evals/fixtures/predictive_validity/constraints.py`): `(correct tool selected) x (fraction of
   that task's registered argument-correctness constraints satisfied)`, raised
   `GROUND_TRUTH_TRIALS` from 1 to 5 for proper per-task trial averaging. Ceiling incidence dropped
   from 44% to 11.4% (5/44) under the new metric — reduced, not eliminated (see Limitations).
3. **Phase 3 added**: 5 new LLM-fixer-generated ("improved") description variants
   (`agentgauge.fixer.run_fixer`, generator=`qwen3:8b`) of 5 existing "before" fixtures, plus the
   2 pre-existing T18-family fixer pairs from Stage A, for a total of **7 before/after pairs** used
   in the degradation-pattern analysis below.

### Tool sets (45)

Spans deliberately-empty/vague descriptions, LLM-fixer-generated descriptions, hand-curated oracle
descriptions, and 5 real-world API mirrors (GitHub, AWS IAM, Jupyter, arXiv, LinkedIn, plus a
memory/knowledge-graph server) with real tool names and verbatim public docstrings. Full manifest:
`evals/fixtures/predictive_validity/manifest.py`.

### Ground truth

`task_success_rate` = mean, over `GROUND_TRUTH_TRIALS=5` trials per hand-vetted anti-tautology
task (`evals/fixtures/predictive_validity/blind_tasks.py`), of `(correct tool selected) x
(fraction of registered argument constraints satisfied)`. Tasks never quote the gold tool's name,
required enum values, or format patterns verbatim (see `blind_tasks.py` module docstring for the
original tautology-leak incident this convention fixes).

### AgentGauge score

`scorer.score_all(tools, OllamaProvider("llama3.1:8b"), client=..., trials=3, base_url=None)` — a
run fully independent of ground-truth collection (own live MCP session, own trials). `docs_manifest`
floors at a constant 20.0 for every entry (all connections are stdio) and is excluded from
correlation as degenerate by construction.

### Baselines

1. **Description length**: mean description character length per tool set, zero LLM calls.
2. **Single-prompt LLM judge**: one holistic 0–100 rating from `llama3.1:8b` on the full tool
   listing, no rubric, no per-axis decomposition.

## Results

### Correlation table (Spearman ρ, continuous task_success_rate vs. field, n=44, bootstrap 95% CI, 2000 resamples, seed=42)

Command: `uv run python scripts/predictive_validity_analysis.py --axis discoverability` (the
`--axis` flag only selects which axis's flagged-cases list prints; the correlation table always
covers every field).

| Field | ρ | p | 95% CI | Effect | Status |
|---|---|---|---|---|---|
| `description_quality` | **0.417** | **0.0048** | [0.112, 0.677] | moderate | significant |
| `overall_score` | **0.371** | **0.0132** | [0.055, 0.622] | moderate | significant |
| Baseline: description length | 0.305 | 0.0438 | [-0.038, 0.580] | moderate | significant (borderline — CI nearly touches 0) |
| `schema_completeness` | 0.234 | 0.126 | [-0.130, 0.556] | small | not significant |
| `discoverability` | 0.186 | 0.226 | [-0.161, 0.495] | small | not significant |
| Baseline: single-prompt judge | 0.116 | 0.455 | [-0.174, 0.384] | small | not significant |
| `error_legibility` | 0.042 | 0.788 | [-0.262, 0.341] | negligible | not significant |
| `selection_accuracy` | -0.211 | 0.169 | [-0.491, 0.118] | small | not significant, wrong direction |
| `call_correctness` | — | — | — | — | degenerate — excluded |
| `robustness` | — | — | — | — | degenerate — excluded |
| `docs_manifest` | — | — | — | — | excluded by construction (constant 20.0, stdio-only) |

**`description_quality` and `overall_score` are the two fields that reach conventional,
uncorrected significance (p < 0.05) with a 95% CI that clearly excludes zero.** `baseline_desc_length`
also nominally clears p < 0.05, but its CI's lower bound (-0.038) sits almost on zero — a fragile
significance the two AgentGauge fields don't share. `selection_accuracy` again points in the wrong
direction (as it did at n=18), though still not significantly so. **This paragraph describes
uncorrected p-values only — see the multiple-comparison correction immediately below, which
changes the picture substantially.**

Old-metric comparison (binary `task_success_rate_binary`, same 44 records) is included in the
script's own output for provenance — it shows a *different* pattern of what reaches significance
(e.g. `discoverability` and `baseline_single_prompt` flip to significant under the binary metric
while `description_quality`/`overall_score` weaken slightly), underscoring that the ground-truth
metric choice, not just sample size, materially shapes which claims the data will support.

### Multiple-comparison correction (added 2026-07-23, second session)

The correlation table above tests **8 fields** for significance (`description_quality`,
`discoverability`, `schema_completeness`, `selection_accuracy`, `error_legibility`,
`overall_score`, `baseline_desc_length`, `baseline_single_prompt` — `call_correctness`,
`robustness`, and `docs_manifest` are excluded/degenerate and were never actually tested, so they
don't count toward the correction). Testing 8 hypotheses at α=0.05 uncorrected inflates the
false-positive rate; applying Bonferroni and Benjamini-Hochberg (both at family-wise/FDR α=0.05,
m=8):

| Field | p (uncorrected) | Bonferroni (α/m=0.00625) | Benjamini-Hochberg |
|---|---|---|---|
| `description_quality` | 0.0048 | **survives** | **survives** |
| `overall_score` | 0.0132 | fails | fails |
| `baseline_desc_length` | 0.0438 | fails | fails |
| `schema_completeness` | 0.126 | fails | fails |
| `selection_accuracy` | 0.169 | fails | fails |
| `discoverability` | 0.226 | fails | fails |
| `baseline_single_prompt` | 0.455 | fails | fails |
| `error_legibility` | 0.788 | fails | fails |

**Only `description_quality` survives correction — under either method.** `overall_score` — the
single number a product CI-gate would actually threshold on — does **not** survive either
correction (p=0.0132 vs. the Bonferroni cutoff of 0.00625, and vs. its own BH-adjusted rank-2
cutoff of 0.0125). This is a materially different picture from the uncorrected table above and
must be read as the controlling result, not the uncorrected p-values.

### Corrected decision-rule label

**This is NOT a clean CONFIRM under the pre-registered rule, and the original label is withdrawn.**
The pre-registered rule required an axis/overall_score to (a) reach significance AND (b) beat the
best naive baseline by a **meaningful margin**. Neither condition survives scrutiny for the
product-relevant metric:
- `overall_score` fails condition (a) outright once corrected for the 8 comparisons actually
  tested (Bonferroni and BH both reject it).
- `description_quality` survives (a), but condition (b) was never actually met even in the
  original write-up: its bootstrap CI ([0.112, 0.677]) overlaps `baseline_desc_length`'s CI
  ([-0.038, 0.58]) almost entirely, and no paired difference-of-rho test was run. "Beats the best
  naive baseline by a meaningful margin" is not demonstrated for the one field that does survive
  correction, either.

Neither pre-registered branch is a clean fit: correlation is not fully null (`description_quality`
survives correction), so this isn't a clean PIVOT either (PIVOT was defined as "correlation stays
null"). The honest label is **NOT CONFIRMED** — a single axis (`description_quality`) shows a
real, correction-surviving association with real task success, but the product-relevant metric
(`overall_score`) does not, and even the surviving axis fails the baseline-beating bar the
pre-registered rule required. Selling "AgentGauge's score predicts real agent success" on this
data, as originally drafted, overstates what n=44 actually supports.

### Phase 3: before/after fixer-pair synthesis (7 pairs)

| Before | After | ΔTask success | Δoverall_score | Δbaseline (single-prompt) | Pattern? |
|---|---|---|---|---|---|
| `t18_vague_server` | `t18_fixer_server` | -0.025 | +17.8 | +20.0 | **yes** |
| `t18_vague_server` | `t18_q2b_server` | -0.067 | +17.2 | +12.0 | **yes** |
| `grounded_server` | `grounded_server_fixed` | **+0.183** | +27.4 | +4.0 | no — genuine joint improvement |
| `confusable_server` | `confusable_server_fixed` | -0.031 | +15.2 | +11.0 | **yes** |
| `mediocre_server` | `mediocre_server_fixed` | -0.150 | +29.8 | 0.0 | **yes** |
| `call_constraints_server` | `call_constraints_server_fixed` | 0.000 | +16.4 | 0.0 | **yes** (flat success, score still jumps) |
| `call_constraints_v2_server` | `call_constraints_v2_server_fixed` | -0.020 | +17.0 | +42.0 | **yes** |

"Pattern" = real task success dropped or stayed flat while `overall_score` and/or the naive
single-prompt baseline rose. **6 of 7 pairs (86%)** show this pattern, with `overall_score` gains
of +15 to +30 points on tool sets whose real success simultaneously fell or didn't move. Only
`grounded_server_fixed` improved on both axes together (its description quality genuinely uses
math-fixture-appropriate specificity that both the judge and the agent benefit from — consistent
with `grounded_server_oracle` also outperforming its base arm by a large margin).

This replicates and generalizes the Stage-A finding (previously observed only in the 2 T18-family
pairs) across 5 additional, structurally different tool catalogs (mixed-echo, confusable-name,
mediocre-enum, and two call-constraints families). The mechanism proposed in the original report
still holds: an LLM asked to "improve" a description tends to produce text that reads well to
another LLM (the judge, and apparently the single-prompt baseline too) without resolving the
specific schema/name ambiguity that determines whether a *different* model doing the actual
selecting picks correctly.

### Decision rule (superseded — see "Corrected decision-rule label" above)

The paragraphs that previously stood here argued this study "lands in CONFIRM." That argument is
**withdrawn** as of the second session (2026-07-23): it never applied the multiple-comparison
correction, which knocks `overall_score` out of significance entirely, and it did not resolve
whether `description_quality`'s edge over `baseline_desc_length` was real (the CIs overlap almost
completely). See "Corrected decision-rule label" above for the current position: **NOT CONFIRMED**.
This section is kept (not deleted) so the correction is visible in-place — see rule 53 (honest
documentation includes what didn't hold up, not just what shipped).

The Phase-3 qualification ("the same axis that correlates with success in aggregate is fooled 6
times out of 7...") is **not** withdrawn — the empirical pattern is unaffected by the statistical
correction above. What changed this session is the proposed *explanation* for it — see "Phase 3
mechanism test" immediately below.

### Phase 3 mechanism test: does homogenization explain the blind spot? (added second session, 2026-07-23)

**Pre-registered hypothesis:** an LLM asked to rewrite a tool's description homogenizes it toward
other tools' descriptions in the same set (raises inter-tool text similarity), reducing
discriminability, which drives the wrong-tool-selection component of the observed success drop.

**Pre-registered falsifiers (recorded before running):** (1) mean pairwise similarity does not rise
in a majority of the 6 degraded pairs; (2) similarity-delta and success-delta show no consistent
negative relationship across all 7 pairs; (3) the success drop is dominated by wrong-argument
construction on the correctly-selected tool, not wrong-tool-selection; (4) `grounded_server_fixed`
(the one improved pair) shows a similarity increase comparable to the degraded pairs.

**Method, and a mid-run correction.** For each of the 7 pairs, both servers were connected live
(stdio), every tool's description embedded (`nomic-embed-text`, local Ollama), and within-set
pairwise cosine similarity computed (mean + the single most-similar "nearest confusable pair").
The first pass embedded bare `tool.description` only and found similarity apparently *rising*
sharply (+0.59 to +0.72) in the empty-description "before" arms. This was an artifact, caught
before drawing any conclusion: embedding an empty string returns a zero-length vector (confirmed
directly: `curl .../api/embeddings -d '{"prompt":""}'` → `{"embedding":[]}`), and 5 of the 6
"before" fixtures have **100% empty tool-level descriptions by design** (that's what makes them the
"bad" tier) — the apparent "rise" was mostly "text went from absent to present," not
"homogenization." The test was redone using the actual **selection-prompt text**
(`agentgauge/runner.py`'s `_build_tool_listing` format: description + `param:type` pairs, matching
exactly what the agent sees when choosing a tool) — a construct-valid fix, not a re-run for a
better-looking number.

**Results (n=7, selection-text basis):**

| Before → After | Δ mean similarity | Δ wrong-tool rate | Δ task success | arg-score\|correct-tool (before→after) |
|---|---|---|---|---|
| `t18_vague_server` → `t18_fixer_server` | -0.246 | +0.025 | -0.025 | 0.886 → 0.882 |
| `t18_vague_server` → `t18_q2b_server` | -0.247 | +0.108 | -0.067 | 0.886 → 0.933 |
| `grounded_server` → `grounded_server_fixed` | -0.099 | **-0.100** | **+0.183** | 0.708 → 0.833 |
| `confusable_server` → `confusable_server_fixed` | -0.184 | +0.063 | -0.031 | 0.788 → 0.813 |
| `mediocre_server` → `mediocre_server_fixed` | **+0.004** | **+0.233** | -0.150 | 0.727 → 0.767 |
| `call_constraints_server` → `..._fixed` | -0.163 | **0.000 → 0.000** | 0.000 | 0.500 → 0.500 |
| `call_constraints_v2_server` → `..._fixed` | -0.123 | **0.000 → 0.000** | -0.020 | 0.360 → 0.340 |

Spearman(Δsimilarity, Δwrong-tool-rate) = **-0.198** (p=0.67, n=7). Spearman(Δsimilarity,
Δtask-success) = **+0.179** (p=0.70, n=7). Both weak and non-significant at this n — but both point
the **opposite sign** from what the hypothesis predicts (it predicts positive
Δsim↔Δwrong-tool-rate and negative Δsim↔Δtask-success).

**Falsification-criteria verdict:**
1. **Triggered.** Similarity *decreased* (tools became more differentiated, not less) in 6 of 7
   pairs. Only `mediocre_server` rose, by a negligible +0.004.
2. **Triggered, and in the wrong direction.** Both correlations above are weak/non-significant and
   have the sign opposite to the hypothesis's prediction.
3. **Triggered for 2 of 7 pairs, directly.** `call_constraints_server` and `..._v2` show **0%
   wrong-tool selection in both arms** — their outcomes are entirely an argument-construction
   effect (`arg_score|correct_tool` moving while wrong-tool-rate sits at exactly 0.0 → 0.0), with
   zero possible contribution from a selection/discriminability mechanism.
4. **Partially triggered.** `grounded_server_fixed`'s similarity change shares the same direction
   (decrease) as 5 of 6 degraded pairs, but its magnitude (-0.099) is the *smallest* of the six —
   not really "comparable," which weakens (but doesn't reverse) this specific criterion's read.

**Verdict: the homogenization hypothesis is falsified as stated.** It is not the mechanism behind
the Phase-3 blind spot. A finding outside the original hypothesis, found while investigating why:
`mediocre_server`'s selection-relevant text is essentially **unchanged** before/after (the fixer
only added uniform `param:type` suffixes to two tools — `get_a`/`get_b` — that already shared
identical names and identical bare param lists, so they were already indistinguishable by this text
before the "fix" and remain exactly as indistinguishable after), yet this pair shows the **largest**
wrong-tool-rate increase of all 7 (+0.233). That strongly suggests sampling noise around an
already-near-chance-level, structurally-unfixable-via-description confusable pair — consistent with
this repo's own prior banked finding (cited already in this report's Phase-3 discussion) that
"T18-decisive distinctions live in tool *behavior*, absent from names and schemas — no generator can
recover what the interface does not contain." Separately, reading the actual fixer diff for
`mediocre_server_fixed` surfaced a concrete, likely-more-relevant mechanism for the
`call_constraints_*` pairs specifically: the fixer's newly-added parameter-level descriptions can be
factually **wrong** (e.g. it describes the `key` parameter — actually a record-key/aggregation-mode
selector — as an "authentication key or API token" for `get_a`/`get_b`/`del_a`/`del_b`). Parameter
descriptions are shown to the agent only at the argument-construction step
(`agentgauge/runner.py`'s raw-schema prompt), never at selection — which lines up exactly with
`call_constraints_server`/`_v2` showing zero selection error but real argument-score movement. A
**hallucinated/incorrect schema metadata** mechanism is a more parsimonious explanation for at least
part of the Phase-3 blind spot than inter-tool homogenization, though this report does not yet
formally test it across more than this one observed instance — flagged as a candidate follow-up,
not asserted as confirmed.

**Consequence for the originally-planned Task 3** (prototyping an `inter_tool_discriminability`
axis): that step was explicitly conditioned on this mechanism test supporting the hypothesis. It
does not. Building a discriminability-based 9th axis on a falsified mechanism would not address the
actual blind spot and is not undertaken in this report — see Recommended next step.

### Is `description_quality` just a length proxy? (third session, 2026-07-23)

Computed a partial Spearman correlation of `description_quality` (and separately `overall_score`)
with real task success, controlling for `baseline_desc_length` (mean description character count),
across all n=44 records. Method: rank-transform all three variables, compute pairwise Pearson
correlations on the ranks, then the standard partial-correlation formula
`(r_xy - r_xz·r_yz) / sqrt((1-r_xz²)(1-r_yz²))`, significance via a t-test with `df = n - 3`. Reused
this repo's own dependency-free `_rank`/`_pearsonr`/`_t_two_tailed_p` helpers
(`scripts/predictive_validity_analysis.py`) rather than introducing scipy.

`description_quality` correlates strongly with description length in its own right:
**Spearman(description_quality, length) = 0.590, p<0.0001.** `overall_score` similarly:
**Spearman(overall_score, length) = 0.511, p=0.0004.**

| Field | Raw ρ (vs. success) | Partial ρ (vs. success, controlling length) | Partial p |
|---|---|---|---|
| `description_quality` | 0.417 | **0.308** | 0.0444 |
| `overall_score` | 0.371 | **0.262** | 0.0894 |

**Neither collapses fully to zero — this is not "the axis is purely a length counter."** But both
attenuate substantially once length is controlled for, and the practical consequence is blunt:
`description_quality`'s partial p (0.0444) would **not** survive the same Bonferroni bar
(0.00625) that its raw, unpartialed p (0.0048) cleared earlier in this report — a large chunk of
what looked like a correction-surviving finding is attributable to description length, a metric
`baseline_desc_length` already gets for zero LLM calls. `overall_score`'s partial correlation
crosses from nominally significant to **not significant even uncorrected** (p=0.089). **Commercial
read: paying for an LLM judge to compute `description_quality` buys some signal beyond what a free
character count already gives you, but a substantial share of its apparent predictive power is
just rewarding longer descriptions, not something specifically about their quality.** This further
weakens the case for `overall_score` as a standalone product signal, on top of the
multiple-comparison correction above.

### Schema-consistency checker (third session, 2026-07-23)

Prompted by the mediocre_server hallucination found in the mechanism test above, and a second,
independently-discovered concrete instance: reading `call_constraints_server_fixed`'s live schema
directly showed the fixer had **introduced** `"required": ["host"]` (and similarly for two other
tools) referencing a property that doesn't exist in `properties` at all (`{}`, unchanged) — while
the tool's rewritten top-level description explicitly and now-falsely states "with no required
parameters." Confirmed via the "before" arm's live schema (`call_constraints_server`, not fixed):
`required: []` for all 4 affected tools, consistent with the description at that point — this
defect was introduced by the rewrite, not pre-existing.

Built a deterministic checker (`scripts/schema_consistency_checker.py`, `run_schema_consistency.py`)
with four checks, no LLM calls, run across all 45 manifest entries' live-introspected tools:
- **(a) `described_not_in_schema`**: identifier-like tokens in the description absent from the
  schema's own properties. Heuristic and noisy by construction (natural-language synonyms
  false-positive) — flagged as approximate in its own docstring, not claimed precise.
- **(b) `required_not_mentioned`**: a schema-required property name that never appears (substring)
  in the description text.
- **(c) `type_enum_contradiction`**: boolean-ish description language for a non-boolean-typed
  property, or a quoted description value absent from that property's own schema `enum`.
- **(e) `required_references_missing_property`**: schema-internal — a name in `required` that isn't
  a key in `properties` at all (the exact defect found above). Fully deterministic, no NLP
  judgment involved.
- (A separate, LLM-judged check "(d)" — does a *parameter-level* description's stated meaning match
  what its name/schema constraints imply — is implemented (`check_d_semantic_llm`) but **not run
  in this session**: local GPU is contended (confirmed via `nvidia-smi`, <500 MB free) and this
  check requires live inference. Deferred, not silently skipped.)

**Cross-referencing violations-per-tool delta against task-success delta across the same 7 Phase-3
pairs used in the mechanism test above:**

| Before → After | Δ violations/tool (all checks) | Δ violations/tool (checks b+e only) | Δ task success |
|---|---|---|---|
| `t18_vague_server` → `t18_fixer_server` | -1.00 | -1.00 | -0.025 |
| `t18_vague_server` → `t18_q2b_server` | -0.08 | -1.00 | -0.067 |
| `grounded_server` → `grounded_server_fixed` | **-2.00** | -2.00 | **+0.183** |
| `confusable_server` → `confusable_server_fixed` | -1.44 | -1.44 | -0.031 |
| `mediocre_server` → `mediocre_server_fixed` | **+2.40** | +2.40 | **-0.150** |
| `call_constraints_server` → `..._fixed` | **+0.62** | +0.62 | 0.000 |
| `call_constraints_v2_server` → `..._fixed` | -1.83 | -1.83 | -0.020 |

Spearman(Δviolations, Δtask-success) = **-0.607** (p=0.148, n=7) using all checks; **-0.577**
(p=0.175, n=7) using only the two hand-validated deterministic checks (b)+(e), confirming the
correlation isn't an artifact of the noisier check (a). **Not statistically significant at n=7**
(expected — this is a 7-point sample), but a substantially larger effect size, in the
theoretically-expected direction (more violations, less success), than the near-zero,
wrong-signed correlations the homogenization mechanism test produced. The two pairs where
violations *increased* (`mediocre_server_fixed`, `call_constraints_server_fixed`) are exactly the
two with the worst/flat real-success outcomes among the 7; the pair with the largest violation
*decrease* (`grounded_server_fixed`, -2.00/tool) is the one pair that genuinely improved. This is
suggestive, not confirmed — see Task 3 pre-registration and scope discussion for what a properly
powered follow-up requires.

### Schema-consistency checker: full results (fourth session, 2026-07-23 — no inference, no GCP)

Task 4's ground-truth expansion was cancelled (see FINAL CONCLUSION above) after 5 consecutive
local-process/Cloud-Run-proxy failures burned real spend without completing. This section reports
the schema-consistency checker's results, which were computed and committed in session 3 but never
written up in this report until now.

**(a) Violation prevalence across all 45 manifest entries.** `evals/fixtures/predictive_validity/
schema_consistency_results.json`, computed over 749 total tools:

| Check | Raw violation count |
|---|---|
| (b) `required_not_mentioned` | **872** |
| (a) `described_not_in_schema` | 143 |
| (c) `type_enum_contradiction` | 42 |
| (e) `required_references_missing_property` | 6 |
| **Total** | **1,063** |

**40 of 45 entries (89%) have at least 1 violation.** Only 5 have zero: `mediocre_server`,
`t18_fixer_server`, `t18_fixer_server_set2`, `grounded_server_fixed`, `confusable_server_fixed`.
`required_not_mentioned` (check b) dominates by volume — most tool descriptions in this study's
fixtures, across every tier, simply don't name their required parameters in prose. This is not
unique to fixer-rewritten arms; it's pervasive, including in real-world mirrors with verbatim public
docstrings (e.g. `rw2_aws_iam_mirror`: 59 violations across 29 tools, all check (b) — a real AWS IAM
API's own terse one-line docstrings don't enumerate required params either).

**(b) Do violations increase after LLM rewrite, across all 9 valid Phase-3 pairs** (the original 7
plus 2 previously-unreported free pairs found this session, `t18_vague_server_set2` →
`t18_fixer_server_set2` / `t18_q2b_server_set2`, both already fully collected at zero extra cost):

| Before | After | Violations before | Violations after | Δ | Δ task success | Δ overall_score |
|---|---|---|---|---|---|---|
| `t18_vague_server` | `t18_fixer_server` | 12 | 0 | -12 | -0.025 | +17.8 |
| `t18_vague_server` | `t18_q2b_server` | 12 | 11 | -1 | -0.067 | +17.2 |
| `grounded_server` | `grounded_server_fixed` | 10 | 0 | -10 | **+0.183** | +27.4 |
| `confusable_server` | `confusable_server_fixed` | 23 | 0 | -23 | -0.031 | +15.2 |
| `mediocre_server` | `mediocre_server_fixed` | 0 | 12 | **+12** | -0.150 | +29.8 |
| `call_constraints_server` | `..._fixed` | 8 | 13 | **+5** | 0.000 | +16.4 |
| `call_constraints_v2_server` | `..._fixed` | 13 | 2 | -11 | -0.020 | +17.0 |
| `t18_vague_server_set2` | `t18_fixer_server_set2` | 12 | 0 | -12 | -0.042 | +16.2 |
| `t18_vague_server_set2` | `t18_q2b_server_set2` | 12 | 5 | -7 | **+0.075** | +15.9 |

**Violations increased in 2/9 pairs, decreased in 7/9, flat in 0/9.** This replicates the n=7
finding's direction at n=9 (the 2 new pairs are both decreases, one paired with the study's second
genuine joint-improvement case: `t18_q2b_server_set2` improved real success too). The two pairs
where violations rose are exactly the two flat/worst outcomes among the original 7 — unchanged from
the earlier report.

**(c) Confusion matrix against the blind-spot pattern** (pattern = real success flat-or-down while
`overall_score` rose — true for 7 of these 9 pairs; the 2 exceptions are `grounded_server_fixed` and
`t18_q2b_server_set2`, both genuine joint improvements). Two candidate flagging rules, reported
separately since they represent different practical linter designs:

| Flagging rule | TP | FP | FN | TN | Precision | Recall |
|---|---|---|---|---|---|---|
| A: violations *increased* (Δ>0) | 2 | 0 | 5 | 2 | **100%** | 29% |
| B: violations *present* in after-arm (>0) | 4 | 1 | 3 | 1 | 80% | 57% |

**Rule A (delta-based — "did this rewrite make it worse") never cries wolf in this sample: 0 false
positives.** Its one cost is recall — it misses 5 of 7 real degraded pairs, because most of them
still have *fewer* absolute violations after the rewrite even though the rewrite didn't help (or
hurt) real success; a delta-only rule can't see that. **Rule B (absolute — "is this currently
non-compliant") catches more (4/7) at the cost of one false positive** (`t18_q2b_server_set2`,
which improved real success despite having 5 residual violations). n=9 is small — these are point
estimates with wide confidence intervals, not final numbers — but the qualitative shape (rule A:
zero false positives, weak recall; rule B: better recall, one false positive) is the honest
takeaway a linter design should account for.

**(d) Hand spot-check of 5 flagged violations, one per check type where possible, judged as
"genuine defect a developer would fix" vs. "false positive":**

1. **`ping_server` (check e, `call_constraints_server_fixed`).** Description: *"...with no required
   parameters..."* Schema: `required: ['host']`, `properties: {}` (host doesn't even exist as a
   property). **GENUINE** — confirmed fixer-introduced (the "before" arm has `required: []`,
   consistent with its description at the time). Unambiguous, severe, exactly the finding that
   motivated building this checker.
2. **`put_x` (check b, `mediocre_server_fixed`).** Description: *"Put."* (one word, unchanged by the
   fixer). Schema requires `sid`, `key`, `val`, `ts` — none named in the description.
   **GENUINE** — a real, actionable gap, though pre-existing (not introduced by this particular
   rewrite; the fixer left the tool-level description untouched here and only added parameter-level
   metadata, per the mechanism-test finding above).
3. **`get_company_profile` (check a, `exp1_stickerdaniel_linkedin_mcp_server_mirror`).** Flagged
   `described_not_in_schema: ['unknown_sections', 'company_urn']`. Reading the full docstring: both
   terms are documented **return-value fields** ("Includes `unknown_sections` list when...",
   "...may include a `{kind: "company_urn"...}` entry"), not input parameters at all.
   **FALSE POSITIVE** — check (a) doesn't distinguish input-parameter mentions from output/return
   documentation, a real precision gap beyond the "natural-language synonym" caveat already
   documented in the checker's own docstring. (The same tool's `required_not_mentioned: ['extractor']`
   finding is separately genuine — `extractor` is a required schema field never mentioned anywhere
   in the docstring.)
4. **`enumerate_all` (check c, `confusable_server_oracle`).** Flagged: *"description uses boolean
   language near 'collection' but its schema type is 'string'."* The description is: *"Returns the
   complete set of all items in a collection with no pagination."* **FALSE POSITIVE, and a clean
   bug**: the trigger is the word **"no"** in "no pagination" — an ordinary English word with zero
   relation to the `collection` parameter's type. Check (c)'s boolean-word detector has no proximity
   or grammatical-relevance filtering; it fires on any boolean-ish word appearing anywhere in a
   description that also mentions the parameter's name, however unrelated.
5. **`attach_user_policy` (check b, `rw2_aws_iam_mirror`, a real-world mirror).** Description:
   *"Attach a managed policy to an IAM user."* Schema requires `user_name`, `policy_arn`,
   `confirmed` — none named. **GENUINE** — an accurate reflection of how terse real AWS-IAM-style
   API one-liners actually are; not a rewrite artifact, but a real, actionable documentation gap.

**Precision by check, from this spot-check (small sample, not exhaustive):** checks **(b)** and
**(e)** were genuine in all 3 instances examined. Checks **(a)** and **(c)** each produced one
concrete false positive out of one instance examined — **(a)**'s input/output-field confusion and
**(c)**'s naive "no" trigger are both real, fixable precision problems, not edge cases. **Saying
this plainly, as instructed: (a) and (c) are not demonstrated to be precise enough for a linter a
developer wouldn't turn off. (b) and (e) — the two checks driving the large majority of this
section's positive signal (872 + 6 of 1,063 total violations, 83%) — held up in every instance
checked (per-instance accuracy).** No fix to (a)/(c) was made in this session (out of scope —
report, not repair — see Task 1's explicit ask). This finding does not change the confusion-matrix
numbers above, which were computed against the checker's current, as-shipped behavior, including
the noisier checks.

**A second, different angle on check (b) specifically — per-tier discriminative value, not
per-instance accuracy (fourth session, 2026-07-23):** grouping `required_not_mentioned` rate by
manifest tier tells a more complicated story than "genuine, therefore useful":

| Tier | Tools | (a)/tool | **(b)/tool** | (c)/tool | (e)/tool |
|---|---|---|---|---|---|
| real-world-mirror-improved | 17 | 0.35 | **1.76** | 0.35 | 0.00 |
| real-world-mirror | 147 | 0.58 | **1.42** | 0.21 | 0.00 |
| bad | 227 | 0.00 | **1.37** | 0.00 | 0.00 |
| mediocre-good | 145 | 0.18 | **1.16** | 0.00 | 0.00 |
| good | 140 | 0.19 | **0.94** | 0.04 | 0.00 |
| fixer-improved | 40 | 0.00 | **0.53** | 0.00 | 0.15 |
| mixed | 4 | 0.00 | 0.25 | 0.00 | 0.00 |
| mediocre | 29 | 0.00 | 0.00 | 0.00 | 0.00 |

**`real-world-mirror` (verbatim public docstrings from real, unremarkable-quality GitHub/AWS-style
API servers — not the "bad" tier by design) fires check (b) at 1.42/tool, nearly as high as the
deliberately-authored "bad" tier's 1.37/tool.** Each individual firing is accurate (the required
param genuinely isn't named in prose — confirmed by hand above), but a check that fires at nearly
equal rates on real professional documentation and deliberately-bad synthetic fixtures has **low
discriminative value as a quality signal**, independent of whether each instance is individually
true. This is a distinct criticism from the per-instance-accuracy spot-check above, and both are
valid at once: **(b) is accurate but not very discriminating; (a) and (c) are both inaccurate in a
demonstrated instance and lower-volume.** Neither framing alone is the full picture. `good` and
`fixer-improved` do show the lowest rates in this table, so (b) is not *purely* noise — there is a
real, if weak, gradient — but "required param not mentioned in prose" is common enough across even
professionally-written real-world API docs that failing this specific check should not, on its
own, be read as "this description is defective."

## Limitations (read before citing any number above)

- **`rw2_arm_guardb` (1 of 45 manifest entries) has no ground truth.** Five collection attempts
  across two Cloud Run deployments and a local run all failed, with three distinct error
  signatures (`ConnectError`, `HTTPStatusError 500`, `HTTPStatusError 404`). Root cause, confirmed
  via Cloud Run logs (`llama-server GPU discovery watchdog timed out` / `context deadline
  exceeded`): the study's two-model requirement (`gemma2:9b` for ground truth, `llama3.1:8b` for
  judging) forces Ollama to swap models in and out of a single shared L4 GPU's VRAM on every
  `_run_one` call, and that swap intermittently fails — a probabilistic infra flake more likely to
  hit larger tool sets (more judge calls = more swap opportunities), not a data or code defect. The
  final (5th) attempt's `404` additionally reflects a cold-start model wipe, a known trade-off of
  the no-gcsfuse Cloud Run config used for this collection run (see Repo State). n=44 throughout
  this report, not 45.
- **Task-difficulty confound between tool-set families (found in this session's audit, not
  previously documented).** The RW1 family (`rw1_github_mirror`, `rw1_arm_a`, `rw1_arm_guardb`,
  `rw1_arm_oracle`) shows task_success_rate clustered at **0.95–1.00 across all 4 quality arms**
  (`{'rw1_github_mirror': 1.0, 'rw1_arm_a': 1.0, 'rw1_arm_guardb': 0.9524, 'rw1_arm_oracle': 1.0}`)
  — essentially zero variance despite spanning bad-to-oracle descriptions. Direct inspection of the
  live tool names (via `connect_stdio`/`introspect()`) shows why: RW1's real GitHub API tool names
  (`get_pull_request`, `get_pull_request_diff`, `get_pull_request_files`, ...) are self-explanatory
  enough that `gemma2:9b` likely selects correctly from the name alone, regardless of description
  quality — unlike `confusable_server`'s deliberately-synonymous names (`search_documents` /
  `query_records`, `list_items` / `enumerate_all`), where real spread (0.64 bad vs. 0.80 oracle)
  appears. Pooling a name-dominant family (RW1) with description-dominant families in one Spearman
  correlation attenuates whatever true signal exists — this biases the aggregate correlation
  toward the null, not toward a false positive, so it does not manufacture the correction-surviving
  `description_quality` finding above, but it does mean the true effect size for
  description-sensitive tool sets specifically is likely understated by the pooled n=44 statistic.
- **Constraint coverage is not uniform across entries (found in this session's audit).** Verified
  programmatically (not from code comments): constrained-task fraction per entry ranges from
  **0%** (`exp1_blazickjp_arxiv_mcp_server_mirror` — all 8 tools have genuinely empty schemas, so
  no argument exists to constrain regardless of task specificity; correctly documented in
  `constraints.py`, but worth naming explicitly here) to 100%. For that one entry,
  `task_success_rate` is still effectively the old pure-tool-name-match metric. Half of
  `call_constraints_server`/`_oracle`/`_fixed`'s tasks are also intentionally unconstrained (empty-
  schema "easy" tools). Ceiling incidence (exact 1.0) dropped from 44% (old binary metric) to
  **11.4% (5/44)** under the fractional metric — real improvement, not full elimination.
- **`GROUND_TRUTH_TRIALS = 5`**, a deliberate compute bound. Still a modest number of trials per
  task for confidence-interval purposes at the individual-tool-set level (the correlation table's
  own bootstrap CI is across tool sets, not within one).
- **Single judge/agent model pair.** `llama3.1:8b` (judge) and `gemma2:9b` (agent) are each one
  point on the capability spectrum — see `agentgauge/CLAUDE.md`'s own calibration notes on
  `llama3.1:8b`'s aspirational absolute bands. Results should be read as "true for this model
  pair, this run," not "true of AgentGauge in general."
- **`docs_manifest` structurally degenerate** for this study (constant 20.0, all connections
  stdio) — excluded, not a finding about the dimension itself.
- **`call_correctness` and `robustness` remain degenerate/near-constant** at n=44 and are excluded
  rather than reported with a misleading near-zero correlation.
- **No formal chance-baseline computed.** Several ground-truth constraints are binary enums (e.g.
  `mediocre_server`'s hard/soft delete mode) with a non-trivial guess probability; a
  `task_success_rate` near 0.5 on such entries is not cleanly distinguishable from chance without a
  computed baseline, which this study does not provide.

## Methodology contribution: four measurement artifacts found during this study

Independent of the FALSIFIED product-thesis conclusion above, this study's own process is a
citable finding in its own right: **four distinct measurement artifacts were found and fixed or
documented across three sessions, each of which would have produced a spuriously positive or
spuriously confident result if left uncaught.** Listed here as a standalone methodology
contribution, since it's a concrete demonstration of how easily an agent-evaluation study can
manufacture false signal even when built carefully:

1. **Task-name leakage (Stage A, session 1 predecessor).** `agentgauge.tasks.generate_tasks()`
   quotes the gold tool's name verbatim in the task text shown to the agent
   (`f"Call '{tool.name}': {tool.description}"`), making tool selection trivial regardless of
   description quality. Produced a zero-variance, near-ceiling ground truth on the first 9 tool sets
   collected this way. Fixed by hand-authoring anti-tautology tasks (`blind_tasks.py`) that never
   quote the gold tool's name or required literal values.
2. **Binary-metric tool-name-match ceiling collapse (Stage A→B transition).** The original ground
   truth (`success AND selected_tool == tool_name`) was degenerate because every example server in
   this repo accepts any well-formed call — `success` was always `True` regardless of argument
   correctness, so the metric collapsed to pure tool-name matching. 44% of the original Stage-A
   records tied at an exact 1.0 ceiling under the old binary metric (this figure is about the
   now-discarded metric on the original smaller sample, not the current n=44 dataset — see
   Methodology above; ceiling incidence under the current fractional metric is 11.4%, 5/44).
   Fixed with a continuous fractional constraint-satisfaction score
   (`constraints.py`); ceiling incidence dropped to 11.4%.
3. **Zero-vector empty-string embedding artifact (session 2, mechanism test).** Embedding an empty
   string via `nomic-embed-text` returns a zero-length vector, not a zero vector or an error. Since
   5 of 6 "before" fixer-pair fixtures have literally empty tool descriptions by design, a
   bare-`tool.description` similarity measurement showed similarity apparently *rising* sharply
   after the fixer rewrite — an artifact of "text went from absent to present," not of
   homogenization. Caught before drawing any conclusion; fixed by re-measuring on the actual
   selection-prompt text format instead.
4. **RW1 self-descriptive-tool-name confound (session 2, correlation-table audit).** The RW1 family
   (real GitHub API tool names like `get_pull_request`, `get_pull_request_diff`) shows near-zero
   task-success variance (0.95–1.00) across all 4 description-quality arms, because the tool names
   alone are informative enough for `gemma2:9b` to select correctly regardless of description
   content — unlike `confusable_server`'s deliberately-synonymous names, where real spread appears.
   Pooling a name-dominant family with description-dominant families in one correlation dilutes
   whatever true signal exists — found by directly comparing live tool names across families, not
   assumed.

All four biased toward manufacturing or inflating a *positive* result (or, in artifact 4's case,
toward attenuating the true correlation, which would have made the eventual FALSIFY conclusion
easier to reach sooner, not harder) — none were caught by a single check; each required directly
reading raw data (task text, embeddings, live schemas, live tool names) rather than trusting an
aggregate statistic. **The practical lesson for any future agent-eval study: budget explicit time to
audit for exactly this class of artifact before trusting a correlation, especially a positive one.**

## Recommended next step

The predictive-validity thesis is FALSIFIED (see top of report) and Task 4 (further ground-truth
collection to test past this result) is cancelled — no further GCP spend or inference is planned
against the core correlation question. What remains open and small-sample-suggestive, not
rescued, is the schema-consistency lead: Spearman(Δviolations, Δtask-success) = -0.607 (n=7) /
consistent direction at n=9, with a confusion matrix showing zero false positives (delta-based
rule) at the cost of weak recall. If this thesis is ever revisited, the schema-consistency checker
itself needs the two precision problems from the spot-check fixed first (check (a)'s input/output
confusion, check (c)'s naive boolean-word trigger) before it could be trusted as a linter, not
just a research instrument — and any further ground-truth collection would need the infra
reliability problems from this session's Task 4 attempt (5 consecutive local-process/Cloud-Run
failures) solved first, independent of whether the underlying question is worth re-testing at all.

## Repo state note

All Stage A/B/Phase-3 study code, fixtures, and this report were committed to
`chore/predictive-validity-study` (not `main`) on 2026-07-23, following an audit pass (see below)
and 759 passing tests. The one pre-existing unauthorized commit (`b309e14`, `blind_tasks.py` base
version, committed by a prior session's executor without authorization) was left as-is per
instruction — not reverted or amended.

**GCP resources used for Stage B/Phase 3 collection (temporary, provisioned mid-session with
explicit user confirmation):** a `agentgauge-agent` Cloud Run service (region `us-central1`,
project `expense-tracker-498014`) was deployed to run `gemma2:9b` + `llama3.1:8b` + `qwen3:8b`
concurrently, after local collection was blocked by GPU contention from an unrelated `aetherart`
process. The service's original config (`scripts/agentgauge-agent-service.yaml`) mounts model
storage via a gcsfuse-backed GCS bucket for cross-cold-start persistence — this was found, via
direct Cloud Run log inspection, to be **fundamentally incompatible with Ollama's parallel-part
download writer**: all 3 model pulls stalled indefinitely (`gcsfuse` "legacy staged writes"
warnings, Ollama "part N stalled; retrying" on all 16 concurrent download parts, zero completed
blobs after 10+ minutes across 3 attempts). A time-boxed test confirmed the diagnosis: the same
pull succeeded in under 5 minutes against the container's own ephemeral disk (no gcsfuse mount).
The service currently runs on this ephemeral-storage config — model weights are **not** persisted
across a cold start / scale-to-zero cycle, unlike the pre-existing `agentgauge-judge` service
(left untouched throughout, per standing instruction). This trade-off directly caused the final
(5th) `rw2_arm_guardb` collection attempt's `404` error (models had been wiped by an intervening
cold start). Both the `agentgauge-agent` Cloud Run service and its bucket were torn down (user
confirmed) once data collection finished — no ongoing billing from this study's GCP usage.

**Second GCP episode (session 3, Phase-3 expansion attempt, also fully torn down):** `agentgauge-agent`
was redeployed (ephemeral-storage config only, no gcsfuse bucket — the lesson from the first episode
applied directly) to build ≥20 fixer pairs for the schema-hallucination follow-up. Local
proxy/build-process reliability failed 5 consecutive times across 3 distinct launch mechanisms
(console-window `cmd start`, Windows Task Scheduler, and a repeat `cmd start`), with 2 different
failure signatures (a ~30min-mark silent death, and a <3min-mark death ending in a bare `Ctrl+C` in
the proxy's log) that were never conclusively root-caused. 5 of the planned 11 new fixer fixtures
were generated and preserved (tool/parameter-name parity verified against each "before" counterpart)
before the attempt was abandoned; **zero ground truth was collected for any of them** — the crashes
happened during fixture generation, before the collection phase started. `agentgauge-agent` and all
associated local processes were torn down/killed; verified via `gcloud run services list` (service
absent, 0 revisions), `gcloud storage buckets list` (no `agentgauge-agent` bucket — none was ever
created this episode), and local process checks (proxy port closed, no build-script process
running) — zero billable resources remain from this study as of this report.

### Audit performed before trusting this data (this session)

Before relying on the expanded dataset, an adversarial pass checked for a third artifact of the
same class as the two already-fixed bugs (task-name leakage in Stage A's first pass;
partial-credit ceiling collapse in the original binary metric). Checked and ruled out as
*systematic* biases: (a) task-text/gold-tool lexical or semantic leakage — every quality-tiered
family shares the literal same task-list object across all description-quality arms, confirmed by
reading `BLIND_TASKS`, not just its comments; (b) partial-credit gaming — `constraint_satisfaction`
is a strict per-constraint check with no cross-task leakage possible. Found and documented above,
not previously written down anywhere: the RW1 tool-name-self-descriptiveness confound and the
arxiv-mirror 0%-constrained residual ceiling case. Neither manufactures a false-positive
correlation; both bias toward the null, meaning the `description_quality` correlation that does
survive correction is, if anything, conservative — though this audit predates, and is unaffected
by, the second session's withdrawal of the CONFIRM verdict and falsification of the homogenization
mechanism (see corrections at the top of this report).

### Second-session addendum: statistical correction + mechanism test (2026-07-23)

A follow-up session applied multiple-comparison correction to the correlation table (see
"Multiple-comparison correction" and "Corrected decision-rule label" above) and ran a pre-registered
mechanism test of the Phase-3 blind spot's proposed cause (see "Phase 3 mechanism test" above). Net
effect: the CONFIRM verdict is withdrawn (NOT CONFIRMED is the corrected label), and the
homogenization hypothesis is falsified as an explanation for the blind spot. The blind-spot pattern
itself (6/7 pairs, score up while success flat-or-down) is unaffected and remains the report's most
robust finding. No commits were made without explicit authorization, consistent with this study's
standing rule; this addendum and the corrections above were written pending that authorization.
