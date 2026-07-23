# AgentGauge v2.1 — product readiness report (Task 7)

Consolidates every number produced across the v2 rebuild (Tasks 0–7, `reports/v2_*.md`) and the
v2.1 statistical-power rebuild (Tasks 0–7, `reports/v2_1_*.md`), separates MEASURED from NOT
MEASURED, and states the headline claim in numbers, not adjectives, per this task's explicit
instruction. Provenance: branch `feat/agentgauge-v2`, pushed to origin.

**Headline claim:** the v2.1 estimator (paired + task-clustered + CUPED) reduces the minimum
detectable effect at n=20 tasks/arm, 80% power from **0.433** (v2 trial-level baseline) to
**0.188** — a 2.3× improvement. **The ship target (detect a 10-point regression at 80% power with
≤20 tasks/arm) is NOT MET** — the gap is 0.088, requiring roughly 47% further variance reduction
beyond what pairing + CUPED already deliver.

---

## 1. MEASURED

### 1.1 Task 1 (v2) — Axis triage (`reports/v2_axis_triage.md`)

Zero of v1's 8 LLM-judged axes survive as a scored quality dimension. `call_correctness` and
`robustness` are degenerate (zero variance, n=44). The other six — including composite
`overall_score` — fail length-controlled partial correlation against the pre-committed Bonferroni
bar (m=6, α/m=0.00833). `discoverability`'s deterministic name-collision sub-heuristic is salvaged
into the linter as `name_collision`; the rest is deleted.

### 1.2 Task 1 (v2.1) — Variance structure (`reports/v2_variance_structure.md`)

Independently verified (separate fresh re-derivation, not a re-run). Computed from 5,535 real
historical trial records, zero inference:

| Finding | Value |
|---|---|
| ICC(1) of trial outcomes within (tool_set, task) | **0.793** |
| Effective sample size (of nominal 5,535 trials) | **878** (15.9% efficiency) |
| (tool_set, task) groups with exactly zero within-group variance | **90.3%** (650/720) |
| Variance share: between tool set / between task within set / between trial within task | **25.9% / 56.1% / 18.0%** |
| Pooled before/after task-mean correlation, 40 matched Phase-3 tasks | **Pearson r=0.881** |

These three numbers directly set the v2.1 redesign priority: pair on task first (removes the
56.1% task-level share), cluster-robust at the task level second, CUPED third, sequential testing
fourth (justified by ICC — repeat trials add almost no information).

### 1.3 Task 2 (v2.1) — Linter recall fix (`reports/v2_1_linter_recall_fix.md`)

New check `param_possibly_renamed` (inverse of `described_not_in_schema`), with two precision
guards found necessary empirically (a naive version produced 147 false positives; guards below cut
it to 4):

| Metric | Before | After |
|---|---|---|
| `param_renamed` recall, overall (n=48) | 22.9% | **83.3%** |
| `param_renamed` recall, single-word properties (n=35) — the specific gap named in the task brief | 2.9% | **82.9%** |
| Clean-corpus false-alarm rate, per tool (n=521) | 3.45% | 4.22% (still < 5% target) |

Guards: (1) exclude common id/unit-suffix abbreviations (`customer_id` → "customer" is shorthand,
not a rename — fixed ~79% of an initial false-positive blowup); (2) require the near-miss token and
property name to share a common prefix (fixed the residual coincidental collisions, e.g.
`page`/`name`). A length-scaled edit-distance approach was tried and **rejected** — it improved
precision further but dropped recall to 41.7%, worse than the target; reported as a real, disclosed
negative result, not silently discarded.

### 1.4 Task 5 (v2.1) — Severity gate restructuring (`reports/v2_1_severity_gate.md`)

Severity restructured from a single HIGH tier into BLOCKING (`type_enum_contradiction`,
`required_references_missing_property` — both measured 0% false alarms) and ADVISORY
(`described_not_in_schema`, `name_collision`, `param_possibly_renamed` — each carries documented,
only-partially-fixable noise). `LintReport.flagged` (CI exit code) now keys off BLOCKING only.

| Granularity | BLOCKING-only false-alarm rate | Target |
|---|---|---|
| Per tool set (n=21) | **0.00%** (0/21) | <10% — passes decisively |
| Per tool (n=521) | **0.00%** (0/521) | — |

The old single-tier rate (66.67% per tool set) does not disappear — it moves to the non-blocking
ADVISORY tier, still surfaced to the user, just not gating CI.

### 1.5 Task 2/3 (v2.1) — Estimator rebuild and re-derived MDE table (`reports/v2_1_estimator_rebuild.md`)

New estimator: `pair_tasks_common_random_numbers` (2a) + `cluster_bootstrap_mean_ci`/
`diff_server_level` (2b) + `cuped_adjust` (2c) + `simulate_sequential_expected_n` with
O'Brien-Fleming alpha-spending (2d), in `agentgauge/harness.py`, alongside the unchanged v2
trial-level functions.

**MDE ablation, server level** (baseline_rate=0.7749, measured from real data):

| n_tasks/arm | power | v2 baseline (trial-level) | +task-level unpaired | +paired | +paired+CUPED |
|---|---|---|---|---|---|
| 5 | 80% | 0.711 | 0.608 | 0.366 | 0.336 |
| 10 | 80% | 0.598 | 0.441 | 0.263 | 0.254 |
| **20** | **80%** | **0.433** | **0.313** | **0.191** | **0.188** |
| 50 | 80% | 0.273 | 0.198 | 0.121 | 0.119 |

(95%-power rows and the full 8-row table: `evals/fixtures/v2_1_mde_ablation.json`.)

**Ablation reading:** moving to a task-level unit of analysis alone buys ~28% MDE reduction (a
direct consequence of Task 1's ICC finding). Pairing buys the largest further reduction (~39%
relative, expected given rho=0.881). **CUPED buys very little on top of pairing** (~2% relative at
n=20) — pairing already captures nearly all the removable task-level variance CUPED's covariate
could otherwise explain.

**SHIP TARGET (detect a 10-point regression at 80% power, ≤20 tasks/arm): measured MDE = 0.188 →
NOT MET.** Gap = 0.088 (≈47% further variance reduction needed). This is the honest, unsoftened
number — the 2.3× improvement over the v2 baseline is real but does not reach the stated target.

**False-alarm re-verification** (`diff_server_level`, same 44 real historical tool sets, 2200 null
comparisons):

| Metric | v2 (trial-level) | v2.1 (paired+CUPED) |
|---|---|---|
| False-alarm rate under the null | 0.00% | **0.59%** (13/2200, still <5% target) |
| Abstention (`INSUFFICIENT_SENSITIVITY`) rate | 71.5% | **21.6%** |
| Confident `NO_CHANGE` rate | 28.5% | **77.8%** |

The v2.1 estimator trades a small (still-passing) false-alarm increase for a much more decisive
harness. **The false-alarm rate is not uniform**: 1.71% on tool sets with <10 tasks vs. 0.07% on
tool sets with ≥10 tasks (12/700 vs. 1/1500) — the well-documented "few clusters" problem in
cluster-robust bootstrap inference, found and quantified during this rebuild's own adversarial pass
(§3 below), not previously visible in the v2 estimator (which never clustered by task).

**Sequential testing** (O'Brien-Fleming, look schedule 5–50 tasks in steps of 5): under the null,
expected stopping n=43.8 (55.8% unresolved at n_max=50); under a true 10-point regression, expected
n=40.0 (56.4% unresolved). **Sequential testing does not fix insufficient power** — since even
fixed n=50 struggles to detect exactly a 10-point regression at 80% power (MDE=0.119 > 0.10 at
n=50), most sequential runs correctly report `INSUFFICIENT_SENSITIVITY` rather than resolving
early; the modest expected-n savings (≈6–10 tasks under null) is real but not the headline result.

**Determinism:** not re-measured for the new estimator in this pass — the underlying `_lcg_random`
mechanism is unchanged and inherits the v2 100%/50-run determinism result, not independently
re-verified from scratch. Flagged as ASSUMED, not MEASURED (§2 below).

### 1.6 Task 6 (v2.1) — Cross-model validation (`reports/v2_1_cross_model_validation.md`)

Live inference across gemma2:9b, llama3.1:8b, qwen2.5:7b (qwen3:8b reserved as generator), against
`call_constraints_server`'s flagship real-world pattern. Required rebuilding the `agentgauge-agent`
Cloud Run service from scratch (bucket had been deleted; gcsfuse volume mount failed outright;
`gcloud run services proxy` died silently mid-run twice — fixed by calling Cloud Run directly over
HTTPS with an IAM identity-token bearer header instead).

| Model | Selection (before→after) | Argument accuracy (before→after) |
|---|---|---|
| gemma2:9b | 1.000 → 1.000 | 0.500 → 0.500 |
| llama3.1:8b | 0.938 → 1.000 | 0.533 → 0.500 |
| qwen2.5:7b | 1.000 → 0.938 | 0.500 → 0.467 |

n=16 trials/cell (trials=1, reduced from the historical 32-task/3-trial design to fit inside a
single uninterruptible Cloud Run session).

- **Established:** the selection-accuracy-flat half of the flagship pattern replicates across all
  3 model families (0.938–1.000 in every cell) — not a gemma2:9b artifact.
- **Not established either way:** the argument-accuracy-degrades half. Observed differences (0 to
  −0.067) are small and diluted by construction — 4 of 8 tools in this task set have no
  constrained parameters and always score 1.0, compressing roughly half of every aggregate figure
  toward a guaranteed ceiling value. This is reported as **inconclusive at this sample size**, not
  as "model-specific" or "doesn't replicate" — neither stronger claim is supported.

### 1.7 Task 2e (v2.1) — Single-prompt LLM linter baseline (`reports/v2_1_cross_model_validation.md` §Task 2e)

Bounded stratified sample (174/521 clean-corpus tools, 138/276 defect-injection cases), llama3.1:8b:

| Metric | Value |
|---|---|
| Clean-corpus false-alarm rate | **97.1%** (169/174) |
| Recall, all 5 defect types | **100.0%** (138/138) |

**The baseline is degenerate** — it answers "INCONSISTENT" on 97.1% of genuinely clean tools, so
its 100% recall is not a meaningful signal. Spot-checked directly (not assumed): the model
hallucinated a fabricated claim ("parameter 'b' is missing from the schema") about a schema that
plainly contained `b` — confirmed this is a real LLM confabulation, not a regex-parsing artifact on
the measurement side. The deterministic linter's 4.22% false-alarm / 83.3% recall is a materially
more useful signal than this baseline's 97.1% false-alarm / 100% recall.

### 1.8 Packaging

- CLI: `lint` / `eval` / `diff` / `init` implemented and manually verified end-to-end. GitHub Action
  template updated for BLOCKING-only gating.
- `pyproject.toml`: v0.2.0, Apache-2.0. Verified via clean-venv wheel install. **Not published to
  PyPI**, per instruction.
- Test suite: **834 tests pass**, 90.0% coverage. `ruff check` / `ruff format --check` / `mypy`
  clean on every touched module.

---

## 2. NOT MEASURED (or only partially measured — stated plainly, not silently rounded up)

- **Task 3d determinism for the new estimator**: not independently re-measured; inherits the v2
  result via unchanged shared PRNG code, not re-verified from scratch.
- **Task 6 argument-accuracy replication**: inconclusive at n=16/trials=1 (§1.6) — the full 32-task
  set at trials≥3 across all 3 models would be needed to resolve this, and was not run (would
  require the Cloud Run infrastructure to sustain a substantially longer continuous session than
  this rebuild's demonstrated reliability window).
- **Task 2e full-corpus LLM baseline**: only a stratified sample (174/521, 138/276) was measured,
  for the same infrastructure-duration reason. The qualitative conclusion (baseline is degenerate)
  is very unlikely to flip on the remaining cases, but exact percentages could shift slightly.
- **Sequential testing (2d) is not wired into the live CLI** — only the statistical machinery and
  its simulation-based expected-sample-size measurement exist; `agentgauge diff` still runs a
  fixed-n comparison. Incremental live-trial collection with early stopping is a follow-on
  engineering task.
- **The CUPED covariate reduction (§1.5) was checked at one baseline rate only** (~0.75–0.77,
  derived from this study's own historical mean) — not re-checked at the 0.50 baseline row or at
  baseline rates outside what real MCP servers in this corpus produced.

---

## 3. Adversarial pass — hunting for further measurement artifacts

Per the study's standing constraint. Four artifacts were found in the predictive-validity study
(task leakage, tool-name ceiling, zero-vector embedding, RW1 confound); a fifth (bootstrap index
bug) and a checked-and-cleared concern (binary vs. continuous outcome shape) were found during the
v2 rebuild's Task 7 pass (`reports/v2_product_readiness.md`'s original §3, preserved below). This
v2.1 pass found two more, both substantive:

### 3.1 (Carried from v2) Bootstrap index bug in `bootstrap_delta_ci` — fixed

The deterministic LCG can return exactly `1.0` (state saturates at `0x7FFFFFFF`), causing
`int(rng() * n) == n` — one index past the resample list's end. Fixed by clamping
(`min(int(rng() * n), n - 1)`); the fix only changes the previously-crashing boundary case, so no
previously-reported numbers needed recomputation. Regression test: `tests/test_harness.py::
TestBootstrapDeltaCI::test_no_index_error_across_many_seeds_and_sizes` (200 seeds × 50 resamples).

### 3.2 (Carried from v2) Binary vs. continuous outcome-shape assumption — checked, cleared

The v2 MDE simulation assumes binary (0/1) outcomes; real data is continuous partial credit
(`{0.0, 0.5, 0.667, 1.0}`). Cross-checked empirically: every MDE cell differed by ≤0.025 from the
binomial-model table — the assumption does not materially change the result at this baseline rate.

### 3.3 (New, v2.1) "Few clusters" false-alarm inflation in the paired/cluster estimator

Found while re-verifying false-alarm rate under the null (§1.5): the new estimator's 0.59%
aggregate false-alarm rate is not uniform — it concentrates in tool sets with few tasks (<10 tasks:
1.71%, 12/700; ≥10 tasks: 0.07%, 1/1500 — a 24× difference). This is the well-documented
finite-sample anti-conservative-coverage problem in cluster-robust bootstrap inference (fewer
clusters → less reliable CI coverage), not previously visible in the v2 trial-level estimator
(which never clustered by task at all, so had no analogous failure mode to exhibit). Both rates
still clear the <5% doctrine target, but this is a genuine, previously-undocumented caveat: **the
v2.1 estimator's false-alarm guarantee is strongest for servers with ≥10 distinct tasks; smaller
catalogs should expect a higher (though still passing) false-alarm rate.**

### 3.4 (New, v2.1) Single-prompt LLM baseline hallucinates on unambiguous input

Found while measuring Task 2e (§1.7): spot-checked a false alarm directly rather than assuming the
97.1% false-alarm rate reflected a genuine (if unhelpful) LLM judgment — it does. The model's own
stated reason for flagging a clean tool was a checkable-false claim about its own context window
(claiming a schema property was "missing" when the same prompt's JSON schema plainly contained it).
Ruled out a measurement-side bug (e.g. the extraction regex matching "not inconsistent") before
accepting this as a real finding, not an artifact of this study's own scoring code.

### 3.5 Length-scaled edit-distance rejected during Task 2 iteration

Not a "found artifact" in the sense of the four above, but the same spirit of self-skepticism: a
plausible-looking precision fix for `param_possibly_renamed` (require tighter edit distance on
short identifiers) was implemented, measured, and **rejected** because it dropped recall from 87.5%
to 41.7% — reported as a negative result in `reports/v2_1_linter_recall_fix.md` rather than quietly
discarded without a trace.

No further measurement artifact was found in this pass.

---

## 4. What would falsify this product's value claim

- **Linter:** a clean-corpus false-alarm rate >5% on a materially different, independent corpus, or
  `param_renamed` single-word recall failing to hold above 80% on such a corpus.
- **Harness MDE:** a real (not simulated) n=50 comparison with a known ~15–20 point true regression
  failing to be detected anywhere near the reported power would indicate the calibration constants
  (sigma_task, resid_sd, rho — all measured from this study's own historical data) don't generalize.
- **Harness false-alarm, few-clusters caveat:** if a materially larger sample of small-task-count
  (<10 task) servers showed a false-alarm rate approaching or exceeding 5% (not just the 1.71%
  measured here on 700 comparisons), the "still passes" framing in §1.5/§3.3 would need revision.
- **Cross-model:** if the full 32-task, trials≥3 replication (not run — §2) showed the
  argument-accuracy pattern genuinely diverges by model family (one model degrades sharply, another
  doesn't), every harness number in this report would need a "model-specific, not general" caveat
  retroactively added. This remains the single largest open risk in the v2.1 rebuild, now partially
  but not fully addressed.
- **Axis triage (v2):** a larger, independently collected dataset showing any of the six
  non-degenerate axes clearing length-controlled Bonferroni significance.

---

## 5. Recommendation

Every doctrine-declared target that could be measured this session was measured. Three pass
decisively (linter false-alarm 4.22%<5%, harness false-alarm-under-null 0.59%<5%, BLOCKING-only
per-tool-set false-alarm 0%<10%). **One explicit ship target is NOT MET**: the harness cannot yet
detect a 10-point regression at 80% power within 20 tasks/arm (measured: 0.188, a 2.3× improvement
over the v2 baseline but short of the target by 0.088). Two adversarial-pass findings this session
(few-clusters false-alarm concentration, LLM-baseline hallucination) are new, substantive, and
disclosed rather than smoothed over. Cross-model validation partially succeeded (selection-flat
pattern confirmed across 3 models) and partially remains open (argument-degrades pattern
inconclusive at the sample size this session's infrastructure could sustain).

**Per the task brief: stopping here.** No publish, merge, or push beyond what's already pushed to
`feat/agentgauge-v2` follows without further explicit authorization. Outstanding before further
work would make sense: a decision on whether the 0.188 MDE (vs. 0.10 target) is an acceptable
shipped state or requires further variance-reduction work, and whether to invest in a
longer-duration Cloud Run session to complete the full-scope cross-model and LLM-baseline
measurements this report flags as sample-limited.
