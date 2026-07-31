# Provenance ledger — AgentGauge methods paper

Every number cited in `docs/paper2/main.tex` must resolve to a row in this table. No number
enters the paper without a provenance pointer to a committed report and commit SHA (spec §5,
non-negotiable). MEASURED vs. NOT MEASURED is kept explicit. Superseded numbers are never cited
without their correction chain shown.

Commit SHA convention: `git log -1 --format=%H -- reports/<file>` — the commit that last touched
the file's current content. Several reports were introduced in the same squash-merged PR, so
groups of files legitimately share one SHA; that is expected, not an error.

---

## 0. Supersession ledger — CRITICAL, read first

These are the numbers explicitly flagged by the spec as having been corrected mid-project. Each
row states the ORIGINAL (do-not-cite) value, the FINAL (cite-this) value, and the full correction
chain. All three were resolved directly by the orchestrator, not delegated, given this project's
prior history of fabricated metrics.

### 0.1 ADVISORY (`param_renamed`) effect

| | Value | Source | SHA |
|---|---|---|---|
| Original (DO NOT CITE) | gemma2:9b -76.7pp, llama3.1:8b -80.0pp, qwen2.5:7b -76.7pp | `reports/v2_2_task_b_causal_chain_multimodel.md` §B4 | `78fff2f` |
| **Final (cite this)** | gemma2:9b **+0.0pp** [-20.5,+20.5] clean null; llama3.1:8b **-13.3pp** [-40.8,+14.1] CI incl. 0; qwen2.5:7b **+6.7pp** [-7.1,+20.4] CI incl. 0 | `reports/v2_3_task1_advisory_audit.md` | `78fff2f` |

Root cause: `constraint_satisfaction`'s gold-constraint lookup (`c.param`) was authored against the
pre-mutation schema, but `param_renamed` is the only injector that changes a property KEY —
runtime resolution against the post-mutation `constructed_args` dict silently failed. This is the
**same root-cause bug** as taxonomy class #7 (scoring-reference mismatch); confirmed as scoped
*only* to the ADVISORY/`param_renamed` measurement by an independent blast-radius audit
(`reports/v2_4_task1_blast_radius_audit.md`, `78fff2f`) that re-read all five injector functions
line-by-line and confirmed no other class touches a schema key. BLOCKING-tier effects (§0.2) are
unaffected and stand as reported.

### 0.2 `type_enum_contradiction` effect range

| | Value | Source | SHA |
|---|---|---|---|
| Erroneous (DO NOT CITE) | "-13.3 to -40.0pp" | constructed by min/max-ing across two different pooling levels in `reports/v2_2_task_b_causal_chain_multimodel.md` (pooled n=45 table vs. a single model's n=15 per-defect-subtype table) — never a real statistic of anything | `78fff2f` |
| **Final (cite this)** | **-13.3pp to -28.9pp** — gemma2:9b -25.2pp [-39.0,-11.3], llama3.1:8b -28.9pp [-43.6,-14.2], qwen2.5:7b -13.3pp [-25.2,-1.5], n=45/model | `reports/v0_4_0_effect_size_reconciliation.md` | `78fff2f` |

Independently re-measured in v2.4 to 2 decimal places (-25.19/-28.89/-13.33) on a separately
rebuilt instance — the most-verified number in this project's causal-chain findings.
`reports/v0_4_0_pre_publication_claim_audit.md` still contains the literal string "-13.3 to
-40.0pp" — by design, preserved as historical record, always preceded by a correction blockquote
(lines 88-97). Confirmed present as expected during extraction; not a live discrepancy.

### 0.3 `greedy_bisection` accuracy at low effect size

| | Value | Source | SHA |
|---|---|---|---|
| Original (DO NOT CITE) | 100% top-1 / 100% top-3 at every effect size 3.0-33.0pp and every candidate-set size 4-40 tools | `reports/v0_5_wave1_report.md` §8.2 | `3d79172` |
| Intermediate (DO NOT CITE — superseded within its own file) | 100%→96%/100% top-1/top-3 (probe-cost accounting fix); ship-bar verdict flipped 3 times in-file (2-of-3 clear → 1-of-3 → 0-of-3) | `reports/v0_5_attribution_benchmark.md` §§2,7d,7e,7j | `3d79172` |
| Intermediate (DO NOT CITE — later inverted) | "clears full ship bar at every single-culprit size ≥10 tools" | `reports/v0_5_scale_curve.md` (pre-correction) | `3d79172` |
| **Final (cite this)** | **58.33% top-1**, 95.83% top-3, 3.25 mean probes, at the 3.0-5.0pp ("below_mde") band — does not clear the 70% ship bar | `reports/v0_5_mde_discrepancy.md` §4b | `3d79172` |

Root cause: measurement artifact #10 (probe variance mis-calibration) — the synthetic probe-noise
model omitted the between-task variance component, inflating detection power 3-7x. Fixed in
`agentgauge/attribution_benchmark.py`'s `make_probe_fn`/`make_multi_probe_fn`. The fix also
**inverts** the scale-curve headline: corrected accuracy *degrades* with candidate-set size
(93%→80%→73%→47% top-1 as n_changed goes 4→10→20→40), the opposite of the original claim that it
improved with scale.

`reports/v0_5_mde_discrepancy.md` §4 states explicitly: *"Nothing from
`reports/v0_5_attribution_benchmark.md`, `reports/v0_5_effect_size_sensitivity.md`, or
`reports/v0_5_scale_curve.md`'s accuracy/budget numbers may be cited going forward without reading
the corrected tables"* in that report. **`v0_5_mde_discrepancy.md` is the terminal authority for
every attribution accuracy/budget number in this paper** (§4a: 50-case benchmark; §4b:
effect-size sensitivity; §4c: scale curve). `reports/v0_5_shapley_scaling_audit.md` and
`reports/v0_5_probe_power_fix.md` (Wave 1.6) are later, separate follow-on measurements at a
different, larger `n_tasks=128` configuration built on top of the corrected model — they do not
further correct the 58.33% figure, they extend it to a different regime.

---

## 1. §3 Experimental setup

| Claim | Value | Report:Line | SHA | Latest authority? |
|---|---|---|---|---|
| Corpus size | 253 tasks (62 pre-existing + 191 from 10 real-API fixtures) | `v2_4_task4_corpus_expansion.md:36` (252, pre-fix) + `v2_5_task2_fixture_validation.md:69-71,158-165` (+1 task, GitHub `state_reason='duplicate'`) | `78fff2f` | Yes |
| 10 real-API gold-constraint fixtures | GitHub, Stripe, Google Calendar, Jira, Slack, Docker, Kubernetes, Twilio, AWS S3, Spotify | `v2_4_task4_corpus_expansion.md` lines 18-30 (domain table) | `78fff2f` | Yes |
| 3 of 10 fixtures had factual defects, found against live docs | GitHub Issues (`state_reason` missing `'duplicate'`), Stripe Payments (`customer_id`→`customer`, required→optional), Kubernetes Workloads (DNS-1123 regex wrongly allowed leading digit) — hallucination rate 3/10 (30%) | `v2_5_task2_fixture_validation.md:34-46` (table), `:47-55` (rate), `:62-101` (fix detail) | `78fff2f` | Yes |
| Models | gemma2:9b, llama3.1:8b, qwen2.5:7b | `v2_2_task_b_causal_chain_multimodel.md` per-model tables (§B1-B4) | `78fff2f` | Yes |
| Byte-exact / cassette replay determinism | **100% cassette-replay determinism, all 6 model adapters**, against mocked wire responses, seed=42, zero live network calls | `v0_5_wave1_report.md:136` (§ "MEASURED, this wave, reproducibly") | `3d79172` | Yes |
| Outcome scoring decomposition | Joint task-success rate decomposed into selection accuracy + argument-construction accuracy | `v2_harness_evaluation.md:11-16` §3a | `78fff2f` | Yes |
| "Continuous partial credit" scoring | Fractional constraint-satisfaction score = (correct tool selected) x (fraction of registered argument constraints satisfied) | `predictive_validity_study.md` lines 78-86 (`evals/fixtures/predictive_validity/constraints.py`) | `78fff2f` | See gaps.md — the exact phrase "continuous partial credit" is the spec's own paraphrase, not a literal quote in any report; the underlying fractional-scoring mechanism is measured and cited here. |

## 2. §4 Variance structure of agent task outcomes

| Claim | Value | Report:Line | SHA | Latest authority? |
|---|---|---|---|---|
| ICC (one-way random-effects, within tool-set/task) | **0.793**, N=5,535 trials, k=720 groups, 90.3% of groups zero within-group variance | `v2_variance_structure.md:19,25-26` | `78fff2f` | Yes — independently re-derived by a separate verifier (fresh script), CONFIRMED |
| Variance decomposition | Between tool-set 25.9%; **between task, within tool-set 56.1%**; between trial, within task 18.0% | `v2_variance_structure.md:38-51` | `78fff2f` | Yes |
| Before/after task correlation | **Pearson r = 0.881** (n=40, pooled); Spearman rho = 0.869 for the same pooled set — downstream reports label 0.881 "rho," which is a citation-label imprecision; use "r=0.881" per the source table | `v2_variance_structure.md:58-66` | `78fff2f` | Yes |
| n_eff formula + consequence | `n_eff = n / (1 + (m̄-1)*ICC)` → n_eff=878 from n=5,535 (15.9% efficiency ratio); "repeated trials on the same task carry almost no independent information" | `v2_variance_structure.md:20-26` | `78fff2f` | Yes |
| Allocation grid: MDE across {1,2,3,5} trials/task x {20,50,100,150} tasks/arm | Full 32-cell grid at 80%/95% power; **compute-optimal cell: 100 tasks/arm x 1 trial/task, MDE=0.085** (refined to 0.0848 at n_simulations=2000); no cheaper cell clears the 0.10 ship target | `v2_2_optimal_allocation.md:17-46` | `78fff2f` | Yes |
| Headline: task diversity dominates trial repetition | Verbatim: "The lever that matters is task-set size, not trials-per-task repetition." Measured 1.55x MDE improvement (100x1 vs. 20x5 at identical 100-trial budget) — the naive 2.04x prediction is explicitly refuted in the same report as "not a value to report as measured." | `v2_2_optimal_allocation.md:63-75,104` | `78fff2f` | Yes — use 1.55x, not 2.04x |

**Not measured (§4):** whether the argument-degradation effect is model-specific or universal at
adequate power (`v2_1_cross_model_validation.md`, n=16 only); full 521-tool linter corpus false-
alarm rate (only a 174-tool stratified sample was run).

## 3. §5 An estimator for agent regression detection

| Claim | Value | Report:Line | SHA | Latest authority? |
|---|---|---|---|---|
| Estimator stack | Paired design + CRN (`pair_tasks_common_random_numbers`) + task-clustered bootstrap (`cluster_bootstrap_mean_ci`) + small-G t(G-1) correction (`t_adjusted_cluster_bootstrap_mean_ci`) + CUPED (`cuped_adjust`) + O'Brien-Fleming sequential testing (`simulate_sequential_expected_n`) | `v2_1_estimator_rebuild.md:8-22`; t(G-1) in `v2_2_few_clusters_correction.md:25-30` | `78fff2f` | Yes |
| Wild cluster bootstrap tried, measured WORSE on small-G coverage | <10-task stratum: wild bootstrap CI width 0.0588 (narrower) but false-alarm 2.00% vs. resample-with-replacement's 0.0647 width / 1.71% false-alarm — narrower-but-wrong. Shipped t(G-1) instead improved this stratum to 1.57%. Root cause: Rademacher sign-flip bounded to 2^G patterns, too coarse at G=4-8. | `v2_2_few_clusters_correction.md:9-30` | `78fff2f` | Yes — useful negative result, report as specified |
| Component ablation table (MDE, n=20/80% power) | v2 trial-level baseline 0.433 -> +task-level unpaired 0.313 -> +paired 0.191 -> **+paired+CUPED 0.188**. CUPED's marginal contribution on top of pairing is small (~2% relative) — explicitly not a large independent contributor, though never worse. | `v2_1_estimator_rebuild.md:26-45` | `78fff2f` | Yes |
| Abstention rate (INSUFFICIENT_SENSITIVITY) | v2 (trial-level) 71.5% -> **v2.1 (paired+CUPED) 21.6%**, on 2200 null comparisons / 44 real tool sets | `v2_1_estimator_rebuild.md:61-65` | `78fff2f` | Yes |
| MDE table | n=20/80%: 0.433 -> **0.188**. Full-corpus grid (trials_per_task=1): n=62 0.1061, n=100 0.0848, n=150 0.0689, n=200 0.0605, **n=253 0.0537** | `v2_1_estimator_rebuild.md:32`; `v2_5_task3_mde_completion.md:17-23` | `78fff2f` | Yes — n=253/0.0537 independently re-verified by a separate agent to 4 decimals |
| False-alarm rate under the null | v2.1 aggregate **0.59%** (13/2200); stratified <10 tasks 1.71% (later 1.57% after t(G-1) fix), >=10 tasks 0.07% | `v2_1_estimator_rebuild.md:61-75`; `v2_2_few_clusters_correction.md:32-43` | `78fff2f` | Yes |
| Replay determinism | **100%** — code-inspection-confirmed (hand-rolled LCG `_lcg_random`, no `random`/`numpy` imports, fixed-order aggregation) + exact-value reproduction to 4 decimals on independent rerun. Note: NOT independently re-measured via a fresh 50-run empirical count for the v2.1 paired+CUPED estimator specifically — that count is inherited/ASSUMED from an earlier measurement, flagged explicitly in-source. Separately, cassette-replay determinism (100%, 6 adapters, §1 above) is a different claim (LLM-call replay, not bootstrap determinism) and IS freshly measured. | `v2_1_estimator_rebuild.md:77-83` (ASSUMED flag); `v2_5_task3_mde_completion.md:69-78` (code-inspection confirmation) | `78fff2f` | Partial — see caveat; cite the code-inspection confirmation, not an empirical "100%/50 runs" figure for the bootstrap RNG specifically |

**Not measured (§5):** live cross-model argument-degradation effect size at the n=253/MDE=0.0537
allocation (statistical power established, no new LLM inference run); O'Brien-Fleming sequential
testing not wired into the live CLI, simulation only.

## 4. §6 Taxonomy of measurement artifacts (the paper's core contribution)

| # | Class | Mechanism | Discovery | Spurious result | Detector / regression test | Report:Line | SHA |
|---|---|---|---|---|---|---|---|
| 1 | Task/answer leakage | Task text quoted the gold tool's own name verbatim (`f"Call '{tool.name}': ..."`), making selection trivial | Inspecting task text directly during the predictive-validity study | Zero-variance, near-ceiling ground truth on first 9 tool sets | Anti-tautology task-authoring convention (`evals/fixtures/predictive_validity/blind_tasks.py`) — tasks never quote gold name/enum/format verbatim | `predictive_validity_study.md:621-626,103-105` | `78fff2f` |
| 2 | Tool-name ceiling | (A) Binary ground truth = `success AND selected_tool==tool_name`, but example servers accept any well-formed call so `success` was always True. (B) `TrialOutcome.selection_correct` compared a composite clustering key against a bare tool name — always False, collapsing `joint_success` to 0.0 for all trials. | (A) Phase-2 ceiling-incidence re-examination. (B) Implausible before=after=0.0 result caught immediately post-run. | (A) 44% of Stage-A records tied at ceiling 1.0. (B) before=after=0.0 for all 3 models, 1518 trials. | (A) Continuous fractional constraint-satisfaction score, `GROUND_TRUTH_TRIALS` 1->5; residual ceiling 11.4% (5/44), reduced not eliminated. (B) Derived real `selected_tool==tool_name` before constructing `TrialOutcome`; independently re-verified via `git show 117225a` diff, bit-identical reproduction. | (A) `predictive_validity_study.md:78-86,627-635,592-595`. (B) `v0_4_0_task1_argument_degradation.md:62-81,162-166` | `78fff2f` |
| 3 | Zero-vector empty-string embedding | `nomic-embed-text` returns a zero-LENGTH vector (not zero-valued or error) for an empty string; 5/6 Phase-3 "before" fixtures have empty descriptions by design, so bare-description embedding made similarity appear to jump after a fixer rewrite | Caught during Phase-3 mechanism test, before drawing any conclusion | Apparent similarity rise of +0.59 to +0.72 in empty-description "before" arms — would have falsely supported the homogenization hypothesis | Re-measured using the actual agent-visible selection-prompt text (description + `param:type` pairs) instead of bare `tool.description` | `predictive_validity_study.md:259-272,636-642` | `78fff2f` |
| 4 | Self-descriptive-name confound | Real, self-explanatory tool names (e.g. `get_pull_request_diff`) let the agent select correctly regardless of description quality, unlike deliberately-synonymous names where real spread appears | Direct inspection of live tool names via `introspect()` during a correlation-table audit | RW1 family clustered at 0.95-1.00 task-success across all 4 description-quality arms — near-zero variance; biases the pooled correlation toward the null (understatement, not a false positive) | `diff_from_trials` now emits explicit `INSUFFICIENT_SENSITIVITY`/`NO_CHANGE` verdict instead of an ambiguous flat correlation; `tests/test_harness.py::test_insufficient_sensitivity_with_few_trials` | `predictive_validity_study.md:572-586,643-650`; fix in `v2_harness_evaluation.md:91-102` | `78fff2f` |
| 5 | Subset-vs-catalog mismatch | Linter's clean-corpus false-alarm measurement ran against a cost-bounded 12-tool subset, not the full 60-tool catalog; legitimate sibling-tool references outside the subset looked like unknown identifiers | Empirical during v2 linter clean-corpus evaluation, traced by comparing to the full catalog | `t18_q2b_server`: 11 HIGH violations -> 0 once corrected — purely a fixture/catalog artifact, never a real linter defect | Full unfiltered catalog extraction (`scripts/v2_extract_tool_definitions.py`) used as linting input going forward | `v2_linter_evaluation.md:36-43` | `78fff2f` |
| 6 | LCG index saturation | Hand-rolled LCG can return exactly `1.0` (state saturates at `0x7FFFFFFF`), so `int(rng()*n)==n` — one index past the resample list's end | Found while carrying a prior Task 7 pass forward into the estimator rebuild | Crash (IndexError) at the resample-list boundary, not a silent wrong number | Clamped `min(int(rng()*n), n-1)`; verified the fix only changes the previously-crashing boundary case | `v2_product_readiness.md:566-570`; carried in `v2_1_estimator_rebuild.md:93` | `78fff2f` |
| 7 | Scoring-reference mismatch | `constraint_satisfaction`'s gold-constraint parameter lookup (`c.param`) was authored against the PRE-mutation schema; only `inject_param_renamed` changes a property KEY, so post-mutation `constructed_args` no longer has that key | Line-by-line re-read of all 5 injector functions during a blast-radius audit, after the ADVISORY effect (§0.1) was found anomalous | The -76.7 to -80.0pp ADVISORY effect (§0.1) — a real scoring bug masquerading as a large causal effect | `constraint_satisfaction_renamed` (landed v2.3); blast-radius audit confirmed no other injection class shares the bug | `v2_3_task1_advisory_audit.md` (full file); `v2_4_task1_blast_radius_audit.md:14-33` | `78fff2f` |
| 8 | Fixture-schema hallucination | Agent-authored real-API fixtures were written from model memory, not fetched schemas; type-only `inputSchema`s (no `enum` declared, by design) meant nothing could catch a wrong required/optional flag, enum set, or format rule | 10 parallel read-only agents each checked one fixture against live official docs; findings re-verified by the report author against primary sources | 3/10 fixtures (30%) factually wrong: GitHub `state_reason` enum, Stripe `customer_id`/required, Kubernetes DNS-1123 regex (see §1 above) — "would have silently mis-scored every correct agent response for that parameter" | `agentgauge.audit.check_enum_schema_fidelity` (WARN severity, offline-only) wired into `run_audit`; 4 new tests in `tests/test_audit.py::TestEnumSchemaFidelity`, seeded with the real GitHub pre-fix case | `v2_5_task2_fixture_validation.md:34-55,62-101` | `78fff2f` |
| 9 | Benchmark-construction bias | Injected true culprit's textual diff was bounded to 32-47 chars while 2/3 decoy tiers unconditionally exceeded that range — diff size correlated with culprit-vs-decoy role, not sampling noise | Task 3a re-measurement: mean culprit fractional rank 0.7333 (n=50)/0.6600 (n=300) — culprit's diff almost always near the smallest end, despite passing the doctrine's binary edge-checks | `baseline_largest_textual_diff` scored 4.0% top-1 — *below* the 26.7% random floor; drove an inflated original headline that 2/3 attribution strategies cleared the ship bar | `agentgauge.audit.check_benchmark_construction_diffsize_bias` (BLOCK), fractional-rank band [0.35,0.65]; culprit now draws an independent camouflage tier + fixed-length decoy floor filler; post-fix rank 0.6113/0.5536, baseline moved to ~24-26% (chance) | `v0_5_attribution_benchmark.md` §7 (lines 201-313) | `3d79172` |
| 10 | Probe variance mis-calibration | Synthetic probe-noise model omitted the between-task variance component, inflating detection power 3-7x relative to the calibrated reference | `check_probe_variance_calibration` audit: reconstructed pre-fix probe widths measured at 34% of the calibrated reference width (should BLOCK); real fixed widths measure in-band | See §0.3 above — 100% top-1 (3pp effect) -> **58.33% top-1**, does not clear ship bar; also inverts the scale-curve headline (accuracy degrades, not improves, with candidate-set size) | `agentgauge.audit.check_probe_variance_calibration` (BLOCK), wired into `run_audit` via `probe_ci_widths`/`probe_n_tasks`; 9 new tests in `tests/test_audit.py` | `v0_5_mde_discrepancy.md` (full file, esp. §3-4) | `3d79172` |

**Candidate 11th artifact (flagged, not adopted as a numbered class — see gaps.md):**
real-world-baseline contamination — a defect-detection signal calibrated against synthetic "bad"
fixtures fires almost as often on genuine, unremarkable real-world documentation, undermining its
use as a quality discriminator even though each individual flag is factually correct. Two
occurrences: `required_not_mentioned` firing at 1.42/tool on real-world-mirror docs vs. 1.37/tool
on deliberately-bad fixtures (`predictive_validity_study.md:530-557`); `name_collision`/
`described_not_in_schema` clean-corpus noise on verb-differentiated pairs
(`v2_linter_evaluation.md` §§2c/2e, lines 75-93). This substantiates the paper's own threats-to-
validity claim ("ten artifacts found suggests an eleventh exists") with a concrete, if informal,
candidate.

## 5. §7.1 / §7.2 Applications and negative results

| Claim | Value | Report:Line | SHA | Latest authority? |
|---|---|---|---|---|
| Per-rule causal effect table | Only `type_enum_contradiction` has a CI-excluding-zero effect, all 3 models (-13.3 to -28.9pp, §0.2). `required_references_missing_property`: clean null, 0.0pp. `described_not_in_schema`/`param_renamed`: null after correction (§0.1). `param_possibly_renamed`, `name_collision`: never causally measured. | `v0_4_0_pre_publication_claim_audit.md:104-111` (preceded by correction blockquote lines 88-97); `v2_product_readiness.md:179-182` | `78fff2f` | Yes |
| LLM-judge baseline degenerate | **97.1% false-alarm** (169/174 clean tools) at **100% recall** (138/138 defect cases). Measured on a 174/521-tool stratified sample, not the full corpus. | `v2_product_readiness.md:502-516` | `78fff2f` | Yes — caveat sample size in the paper |
| §7.2 rewriting-descriptions null | 253 tasks x 3 models, MDE=0.0537 (80% power), threshold=0.05: gemma2:9b +0.0217 [-0.0042,+0.0505] no_change; llama3.1:8b +0.0553 [+0.0232,+0.0885] no_change (CI excludes 0 but below the practical threshold); qwen2.5:7b +0.0040 [-0.0211,+0.0292] no_change | `v0_4_0_task1_argument_degradation.md:83-114` | `78fff2f` | Yes |
| §7.2 "initially appeared to show a large effect" predecessor | **Needs a framing decision, not a fabrication risk — see gaps.md.** The underpowered n=62 predecessor (`v2_2_task_a_reallocation.md`, MDE=0.106) found FLAT near-zero deltas, explicitly labeled inconclusive-underpowered, not "a large effect." The ADVISORY -76.7/-80.0pp story (§0.1) IS a real "initially large, later corrected" narrative, but belongs to a different rule/experiment (causal-chain `param_renamed`, not the rewriting-descriptions argument-construction question). Do not conflate the two in the same sentence. | `v2_2_task_a_reallocation.md`; `v2_2_task_b_causal_chain_multimodel.md:71-89` | `78fff2f` | Flagged, see gaps.md |

## 6. §7.3 The attribution impossibility result

All accuracy/budget numbers below are per §0.3's terminal authority, `v0_5_mde_discrepancy.md`.

| Claim | Value | Report:Line | SHA | Latest authority? |
|---|---|---|---|---|
| Final strategy comparison (50-case benchmark, corrected) | See `v0_5_mde_discrepancy.md` §4a full table (exhaustive_ablation/sampled_shapley/greedy_bisection, top-1/top-3/mean-probes/ship-bar) | `v0_5_mde_discrepancy.md` §4a | `3d79172` | Yes |
| Effect-size sensitivity (corrected, n=24/band) | 5 bands 3.0-33.0pp; below_mde band greedy_bisection **58.33%** top-1 (§0.3); accuracy clears ship bar only at "original" (13.3-28.9pp) and "beyond" (28.9-33.0pp) bands | `v0_5_mde_discrepancy.md` §4b | `3d79172` | Yes |
| Scale curve (corrected) | Single-culprit accuracy DEGRADES with n_changed: 93%(4)->80%(10)->73%(20)->47%(40) top-1 — inverts the pre-correction claim that accuracy improved with scale | `v0_5_mde_discrepancy.md` §4c | `3d79172` | Yes |
| Cost-crossover vs. full re-eval | Crossover at n_changed ~= **2-4** changed tools (n_tasks=128 regime, where the accuracy target is met); realistic buyer scenarios (10-40 tools) cost **5x-20x** a full re-eval; every tested configuration at the accuracy-adequate n_tasks is MORE expensive than re-running the whole 253-task corpus | `v0_5_probe_power_fix.md` §5 (Task 2e), lines 170-211 | `3d79172` | Yes — later than mde_discrepancy (Wave 1.6), a distinct larger-n_tasks=128 follow-on, not a further correction of the 58.33%/3pp figure |
| Ship/kill recommendation | Hold failure attribution as unreleased research; ship v0.5.0 with model adapters only; preserve the research for this methods paper | `v0_5_probe_power_fix.md:213-253` | `3d79172` | Yes |

**Not measured (§7.3):** attribution accuracy against a real agent + real LLM judge (all numbers
above are synthetic-benchmark, `make_probe_fn`/`make_multi_probe_fn`); `sampled_shapley` has zero
real (live-LLM) data points; whether `sampled_shapley`'s multi-culprit failure mode is
mechanistically distinct from `greedy_bisection`'s.

---

## Ambiguous / needs-a-framing-decision (flagged, not guessed)

1. **§7.2's "underpowered predecessor" framing.** Two genuinely different "later corrected"
   narratives exist in the source reports (see §5 table above) — the rewriting-descriptions null
   (which was never a large effect, just underpowered-inconclusive at n=62) vs. the ADVISORY
   causal-chain effect (which WAS a large, later-corrected-to-null effect, but for a different
   experiment). The spec's §7.2 text risks conflating these. Recommend the paper's §7.2 state the
   rewriting-descriptions result on its own terms (flat at both n=62 and n=253, not "initially
   large") and let §6's artifact #7 carry the ADVISORY story where it belongs.
2. **rho=0.881 label.** Downstream reports cite "rho=0.881" for the before/after correlation, but
   the source table (`v2_variance_structure.md`) labels 0.881 as Pearson r (Spearman rho=0.869 is
   a separate value in the same table). Use "r=0.881" in the paper, per the source table's own
   labels.
3. **n=20 MDE discrepancy (0.188 vs. 0.182).** `v2_1_estimator_rebuild.md` (paired+CUPED, n=20,
   80% power) reports MDE=0.188; `v2_2_optimal_allocation.md` (trials_per_task=1, tasks=20, 80%
   power) reports MDE=0.182. Very likely different default trials/task configs (v2.1 predates the
   `trials_per_task` parameter added in v2.2) rather than a genuine conflict, but neither source
   file states the other's exact config — insufficient information to fully reconcile from the
   text alone. Use 0.188 (the estimator-ablation table's own number) for the §5 ablation table,
   and 0.085/0.0848 (the allocation-grid's own number) for the §4 grid table — do not mix them.
4. **"Continuous partial credit"** — the literal phrase does not appear in any committed report
   (confirmed by repo-wide grep); it is the spec's own paraphrase of the measured fractional
   constraint-satisfaction scoring mechanism (§1 table, row 7). The underlying mechanism and its
   formula are measured and cited; the phrase itself is expository, not a quoted metric name.

## Not-measured index (consolidated)

- Whether the argument-degradation effect is model-specific or universal (only n=16 measured,
  underpowered) — `v2_1_cross_model_validation.md`.
- Full 521-tool linter-corpus clean false-alarm rate (only a 174-tool stratified sample run) —
  `v2_product_readiness.md`.
- True cross-model argument-degradation effect size at the n=253/MDE=0.0537 allocation (power
  established, no new inference run) — `v2_5_task3_mde_completion.md`.
- O'Brien-Fleming sequential testing wired into the live CLI (simulation only) —
  `v2_product_readiness.md`.
- Fresh 50-run empirical determinism count for the v2.1 paired+CUPED bootstrap specifically
  (inherited/ASSUMED from an earlier estimator's measurement) — `v2_1_estimator_rebuild.md`.
- Attribution accuracy against a real agent + real LLM judge (all attribution numbers are
  synthetic-benchmark) — `v0_5_mde_discrepancy.md`, `v0_5_probe_power_fix.md`.
- `sampled_shapley` real (live-LLM) data points — zero exist.
- Isolated 2-defect-type (excluding the null `required_references_missing_property` subtype),
  n=30 pooled re-measurement of `type_enum_contradiction` — does not exist.

## Coverage summary

- Claims mapped: 34 (contributions + section-outline claims across §3-§7.3), all with report path
  + SHA.
- Supersession chains fully resolved: 3/3 flagged in the spec, plus the attribution cascade's full
  chain (4 reports deep) documented in §0.3.
- Ambiguous/framing items flagged for author decision: 4 (none required guessing a number).
- Not-measured items consolidated: 8 (feeds `docs/paper2/gaps.md`).
