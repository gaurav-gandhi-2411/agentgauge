# AgentGauge v2 — product readiness report (Task 7)

Consolidates every number produced in Tasks 1–6 of the v2 rebuild, separates what is measured in
this repo from what is assumed, records one adversarial-pass finding (a real bug, fixed) and one
adversarial-pass cross-check (a modeling assumption, verified not to matter), and states plainly
what would falsify this product's value claim. Provenance: branch `feat/agentgauge-v2`, commit
`32c46cc` plus the two follow-up commits from this report's own adversarial pass (harness bugfix +
regression test, this report). Per the task brief: **STOP after this report — no publish or merge
action follows without further explicit authorization.**

---

## 1. MEASURED

### 1.1 Task 1 — Axis triage (`reports/v2_axis_triage.md`)

- **Zero of v1's 8 axes survive** as a scored quality dimension. `call_correctness` and
  `robustness` are degenerate (zero variance, n=44). The other six — including the composite
  `overall_score` — all fail length-controlled partial correlation against the pre-committed
  Bonferroni bar (m=6, α/m=0.00833); none reaches even the uncorrected p<0.05 threshold except
  `description_quality` (partial ρ=+0.308, p=0.044), which still fails Bonferroni.
  `discoverability`'s raw correlation (ρ=+0.186, already non-significant) **sign-flips** to
  ρ=-0.132 once description length is controlled for — the cleanest demonstration in this dataset
  that a judged axis can look like signal while re-deriving `len()`.
- **One structural component salvaged:** `discoverability`'s deterministic Levenshtein
  near-duplicate-name collision heuristic (never itself a correlational score) is extracted into
  the Task 2 linter as `name_collision`. The LLM-judged half of `discoverability` is deleted
  entirely.

### 1.2 Task 2 — Deterministic linter (`reports/v2_linter_evaluation.md`, `agentgauge/linter.py`)

| Metric | Value | Against doctrine target |
|---|---|---|
| False-alarm rate, per tool (21 tool sets, 521 tools, clean corpus) | **3.45%** (18/521) | Target <5% — **passes** |
| False-alarm rate, per tool set (≥1 flag anywhere) | 66.67% (14/21) | No target set; reported because a naive "any flag blocks the PR" CI wiring would fail its own target even though the per-tool rate passes |
| Recall, `contradictory_required_claim` / `type_flipped` / `enum_dropped` (177 injected defects) | **100.0% / 100.0% / 100.0%** | — |
| Recall, `required_unmentioned_prose` (INFO-severity only, 51 injected) | 94.1% | Not surfaced by default (demoted per the PV study's own finding this check fires on clean professional docs) |
| Recall, `param_renamed` (48 injected) | **22.9%** overall — 76.9% multi-word, **2.9%** single-word | Genuine, quantified weak spot — not fixed, fixing would explode false alarms |
| Recall, raw JSON-Schema structural validation baseline | 0.0% (all 5 defect types) | Linter beats it on every defect type — none of the injected defects are structurally invalid JSON-Schema |
| Recall, single-prompt LLM baseline | **not measured** | See §2.2 |

### 1.3 Task 3 — Regression harness (`reports/v2_harness_evaluation.md`, `agentgauge/harness.py`)

| Metric | Value | Against doctrine target |
|---|---|---|
| False-alarm rate under the null (2200 resampled comparisons, 44 real tool sets) | **0.0%** (0/2200) | Target <5% — **passes**, with the caveat that 71.5% of the 2200 are `INSUFFICIENT_SENSITIVITY` (correct abstention), only 28.5% confident correct `NO_CHANGE` |
| Replay determinism (50 identical repeated runs) | **100%** byte-identical | — |
| MDE @ n=50/arm, 80% power (baseline=0.75) | **0.273** | Reported as a measured fact, not a target — a regression must cut task success by ~27 points before this harness reliably (80%) catches it at 50 trials/arm |
| MDE @ n=5/arm, 80% power (baseline=0.75) | 0.711 | Only a near-total collapse in success is reliably caught at CI-realistic trial counts |
| Full 16-row table (n∈{5,10,20,50} × power∈{80%,95%} × baseline∈{0.75,0.50}) | `evals/fixtures/v2_mde_table.json` | — |

### 1.4 Task 4 — Argument-vs-selection decomposition

Not a separate metric class per the doctrine (`reports/v2_eval_doctrine.md`, Component 3) — it is
folded into Task 2's defect-injection table (`described_not_in_schema`, `type_enum_contradiction`,
etc. all operate on the schema/description level, independent of tool selection) and into
`agentgauge.harness.TrialOutcome`, which reports `selection_correct` and `argument_score`
separately by construction (`argument_score` is `None`, not `0.0`, when selection is wrong). CLI
`agentgauge diff` and `agentgauge eval` print both rates. Verified against the exact real historical
`call_constraints_server` pattern this decomposition was built to fix
(`tests/test_harness.py::TestDecomposedRate::test_call_constraints_style_pattern`, and confirmed on
real data via `agentgauge diff --replay-before/--replay-after` against
`mediocre_server`/`mediocre_server_fixed` during manual CLI verification).

### 1.5 Task 6 — Packaging

- CLI: `lint` / `eval` / `diff` / `init` implemented, manually verified end-to-end (text and
  `--json` modes, correct exit codes, `--mock` and `--replay` zero-inference paths, one live
  real-historical-data replay reproducing a previously-found selection-accuracy-drop pattern).
- GitHub Action template (`init`-scaffolded) posts a PR comment and fails the check on
  `REGRESSION` verdict; `permissions: pull-requests: write` set; explicit note that the runner
  needs a reachable Ollama instance for live (non-replay) diffs.
- `pyproject.toml`: version `0.2.0`, Apache-2.0. Verified by building a wheel (`uv build`),
  installing into a clean venv, and confirming `agentgauge --version` prints `0.2.0`. **Not
  published to PyPI**, per the task brief's explicit instruction.
- README rewritten around the measured numbers above (this session, commit `32c46cc`); a
  under-5-minute quickstart using `lint`/`init`/`diff` is the primary path, v1's `scan`/`fix`/`ci`/
  `try` are marked legacy but left functional.
- Test suite: **803 tests pass**, 89.4% coverage (`uv run pytest`), `ruff check`/`ruff format
  --check`/`mypy` all clean on every v2 module (`linter.py`, `harness.py`, `constraints.py`,
  `cli.py`) as of this report.

---

## 2. NOT MEASURED (blocked, not silently skipped)

### 2.1 Task 5 — Cross-model generalization

**Blocked on GPU contention for the entire duration of this rebuild.** Checked repeatedly via
`nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv` and `ollama ps`; most
recent check (this report): **490 MiB free of 8192 MiB**, consistent with every prior check this
session (24–490 MiB free range). Per this study's standing constraint, no inference is run without
confirming GPU availability first.

- **The linter half of Task 5 needs no live trials and is trivially satisfied by construction:**
  `agentgauge/linter.py` makes zero LLM calls — its output is identical regardless of which model
  (if any) is later used as the acting agent. There is no cross-model question to answer for the
  linter; this is a fact about the code, not a measurement that was skipped.
- **The harness's cross-model replication genuinely requires live inference** (running the same
  task set against gemma2:9b, llama3.1:8b, and qwen2.5:7b as acting agents, qwen3:8b reserved as
  generator) and has not been attempted. This is the single largest open item in this rebuild.

### 2.2 Task 2e — Single-prompt LLM baseline for the linter

Same GPU blocker. Not measured. The other two baselines in the doctrine's Component 1 (no linter;
raw JSON-Schema validation) are measured (§1.2).

---

## 3. Adversarial pass — hunting for a fifth measurement artifact

Per the study's standing constraint ("before reporting ANY positive result, run an adversarial
pass specifically hunting for a fifth [artifact beyond the four already found in the
predictive-validity study]. Assume it exists."), this pass targeted Task 3's MDE simulation
specifically, because it is the one component whose "positive result" (the MDE table) rests on a
modeling assumption rather than a direct empirical measurement.

### 3.1 Found and fixed: an indexing crash in `bootstrap_delta_ci`

`agentgauge.harness.bootstrap_delta_ci`'s deterministic LCG PRNG (`_lcg_random`) can return
exactly `1.0` (its internal state saturates at `0x7FFFFFFF`, and `next_float()` divides by that
same value). `int(rng() * n)` then equals `n` — one index past the end of the resample list,
raising `IndexError`. This was found empirically: a cross-check script
(`scripts/v2_mde_continuous_crosscheck.py`, written for §3.2 below) hit it after ~4.5 minutes of
simulation, on real code already shipped in `agentgauge/harness.py`.

**This is a real, previously-undiscovered bug in the harness's core statistics engine**, not a bug
in the cross-check script — both call the same `bootstrap_delta_ci` function. It did not surface
during Task 3's original measurement runs (`v2_mde_table.py`, `v2_false_alarm_and_determinism.py`)
because those specific seed sequences did not happen to hit the saturated LCG state — a matter of
luck, not correctness. Left unfixed, `agentgauge diff` could crash in production on an
unpredictable, seed-dependent fraction of runs.

**Fix:** clamp the resample index (`min(int(rng() * n), n - 1)`) rather than trusting the draw is
always `< 1.0`. This changes behavior only in the previously-crashing boundary case — every other
draw resamples identically to before, so **none of the already-reported §1.3 numbers need
recomputation** (they were computed on seed sequences that never reached the boundary state).
Regression test added: `tests/test_harness.py::TestBootstrapDeltaCI::
test_no_index_error_across_many_seeds_and_sizes` (200 seeds × 50 resamples, would have raised
`IndexError` pre-fix). Full suite re-run after the fix: 803/803 pass.

### 3.2 Checked and found not to matter: binary vs. continuous outcome-shape assumption

`simulate_minimum_detectable_effect`'s docstring already discloses that it "uses a binomial outcome
model... a simplification of the real continuous constraint-satisfaction outcome" — but this was
never empirically checked against real data before this report. Inspecting
`evals/fixtures/predictive_validity/results_raw.json` directly: real trial outcomes take **4
distinct values, `{0.0, 0.5, 0.6667, 1.0}`** (n=5535 trials) — genuine partial credit from
multi-constraint tasks, not a binary 0/1 outcome. A pure-binomial MDE simulation cannot represent
that intermediate-value variance by construction, so the reported §1.3 MDE table rests on a
variance model that provably does not match this study's own data.

**Cross-check performed** (`scripts/v2_mde_continuous_crosscheck.py`,
`evals/fixtures/v2_mde_continuous_crosscheck.json`): re-ran the identical binary-search MDE
procedure, but drew "success" outcomes from the real observed non-zero value pool (n=4317 values,
still `{0.5, 0.6667, 1.0}`) instead of a fixed `1.0`, at the real empirical mean rate (0.7749 vs.
the original table's 0.75 — both derived the same way, from the same fixture, at slightly
different points in this session).

| n_trials/arm | power | MDE — binomial model (§1.3, baseline=0.75) | MDE — empirical outcome shape (baseline=0.7749) | Δ |
|---|---|---|---|---|
| 5 | 80% | 0.711 | 0.723 | +0.012 |
| 5 | 95% | 0.750 | 0.775 | +0.025 |
| 10 | 80% | 0.598 | 0.581 | -0.017 |
| 10 | 95% | 0.692 | 0.699 | +0.007 |
| 20 | 80% | 0.433 | 0.422 | -0.011 |
| 20 | 95% | 0.537 | 0.539 | +0.002 |
| 50 | 80% | 0.273 | 0.264 | -0.009 |
| 50 | 95% | 0.355 | 0.348 | -0.007 |

**Verdict: the outcome-shape mismatch does not materially change the MDE table.** Every cell
differs by ≤0.025, well within the noise floor of a 1000-simulation Monte Carlo estimate at either
model. The theoretically-valid concern (binomial variance ≠ real partial-credit variance) turns out
not to move the substantive conclusion — the bootstrap CI's width is evidently driven by sample
size and mean-estimator variance in a way that is not very sensitive to the exact shape of the
non-zero outcome distribution at this baseline rate. **This is reported as a checked-and-cleared
concern, not a proven-safe one** — it was verified at one baseline rate (~0.75-0.77) derived from
this study's own historical data; it has not been re-checked at the 0.50 baseline row of the
original table, nor at baseline rates far from what real MCP servers in this corpus produced.

No further measurement artifact was found in this pass. The search focused on Task 3's harness
(the component most rooted in a synthetic model rather than direct counting); a symmetrical pass
over Task 2's linter was not repeated here since `reports/v2_linter_evaluation.md` §2c/2d already
documents five separately-found false-positive mechanisms and one measurement-harness artifact
found during that task's own development, each with its own regression test — the linter has
already been through more rounds of adversarial hunting than the harness had until this pass.

---

## 4. What would falsify this product's value claim

- **Linter:** if a clean-corpus false-alarm rate measured on a materially different, larger corpus
  (not derived from this study's own 21 base tool sets) exceeded 5%, or if `param_renamed` recall
  on single-word properties could not be improved without a proportional false-alarm increase on an
  independent corpus, the "precision-first" framing would need revision.
- **Harness:** if Task 5's (currently blocked) cross-model replication showed the same tool-set
  change produces a `REGRESSION` verdict under one model family and `NO_CHANGE` under another at
  matched trial counts, the harness's central claim — that it measures something about the tool set,
  not an artifact of one specific judge/agent model — would be falsified, and every MDE/false-alarm
  number in this report would need a "model-specific, not general" caveat added retroactively.
  This is the single biggest open risk in this rebuild.
- **Harness MDE, more narrowly:** if a real (not simulated) two-arm comparison at n=50 with a known,
  independently-verified ~15-20 point true regression failed to be detected at anywhere near the
  reported 80% rate, the MDE table's already-checked-once (§3.2) modeling assumptions would need a
  second, harder look — specifically, whether real trial-to-trial correlation (e.g., outcomes for
  the same task template correlated across trials, not i.i.d.) inflates true variance beyond what
  either the binomial or empirical-outcome-shape model captures. Neither cross-check in this report
  tested for within-tool-set trial correlation — only outcome value shape.
- **Overall:** the axis-triage result (Task 1) would be falsified by a larger, independently
  collected dataset showing any of the six non-degenerate axes clearing length-controlled
  significance with Bonferroni correction — this report treats that as settled for this dataset,
  not for all possible future data.

---

## 5. Recommendation

Every doctrine-declared target that could be measured this session was measured and passes (linter
false-alarm <5%, harness false-alarm-under-null <5%, 100% determinism); the two that could not be
measured (Task 5 cross-model replication, Task 2e LLM baseline) are both blocked on the same,
already-repeatedly-confirmed GPU contention, not on anything about the product itself. One real bug
was found and fixed during this report's own adversarial pass (§3.1), with a regression test; one
modeling assumption was checked and found not to move the numbers (§3.2). Nothing in this rebuild
is currently unverified-and-reported-as-verified.

**Per the task brief: STOPPING HERE.** No publish, merge, or push action follows without explicit
authorization. Outstanding before that authorization would make sense: Task 5's cross-model run
(needs GPU availability), and a decision on whether to push `feat/agentgauge-v2` (6 commits ahead of
this report, not yet pushed to origin) for review.
