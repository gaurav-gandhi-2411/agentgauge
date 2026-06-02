# TASKS.md

Three-state board: TODO → IN-REVIEW → DONE.
Each item has explicit, testable acceptance criteria.
Autonomous runs: pick the single top TODO, implement it, move to IN-REVIEW.

---

## TODO

*(empty)*

---

## IN PROGRESS (manual)

*(empty)*

---

## IN-REVIEW

### Tx — Generator abstains on opaque tool names (fixer description quality)

**Branch:** claude/tx-abstain-no-harm — DRAFT PR pending real-agent A/B results.

Grounding detection added to `fixer.py`: when all tokens in a tool name are either
single-character or in the `_GENERIC_TOKENS` vocabulary (get, set, put, del, etc.),
`is_low_grounding` returns True and `run_fixer` records `ABSTAINED` instead of calling
the generator. Harm gate: opaque ObsStore tools (get_a/del_b/put_x) all abstain → arm B
= arm A → delta ≥ 0 trivially satisfied. Upside gate: grounded fixture (`transform_*`
tools, empty descriptions) — grounding check passes so fixer generates; real-agent A/B
pending. Degenerate-guard CI test asserts that `transform_scale` (clearly grounded) does
NOT abstain.

---

## FUTURE / DEFERRED

### Ty — H2 headroom fixture (call_correctness testable)

In all four T16 runs, gemma2:9b saturated at 100% call_correctness from training priors.
Create a fixture where a correct tool call genuinely requires schema metadata the agent cannot
infer: e.g. an arbitrary enum (`unit: "p1"/"p2"/"p3"`) or a non-standard format constraint
with no natural-language equivalent. Alternatively, use a weaker/constrained agent.

**Scope:** new fixture in `examples/`; no scorer.py changes; requires real-agent A/B run.
**Pre-condition:** own spec, pre-registered H2 hypothesis with validity gate ≤ 80% arm A.

---

### Tz — Scan-path prompt_version in JSON report schema

The runner.py fix (descriptions now shown in selection prompt) breaks score comparability:
pre-fix `selection_accuracy` scores (names-only prompt) and post-fix scores (descriptions +
param types) are not comparable. The JSON report should record the prompt format version so
consumers can identify which regime a score was computed under.

**Scope:** `report.py` / JSON schema only — no scorer or runner logic changes.
**Note:** this is adjacent to scorer output (report schema); flag as possible condition #1 and
require its own spec before implementing.

---

### Re-calibrate judge bands against a ≥30B model

Re-calibrate `score_error_legibility` rubric bands against `llama3.3:70b` (or
equivalent ≥30B model) when a ≥64GB host is available. Model pinning makes this a
config + re-measure exercise, not a rebuild: update `CALIBRATED_JUDGE_MODEL` in
`cli.py`, re-run the three-tier calibration cases, and update `CLAUDE.md`. The
test suite guarantees ordering + actionability gap regardless of which model is used.

---

## DONE

### T16 — Held-out fixture + real A/B run

**Priority:** P1
**Merged:** PR #31 — feat(ab): T15+T16 — paired A/B harness + held-out fixture + real-agent result

Four A/B runs (gemma2:9b agent, 10 tasks × 5 trials). Two valid runs both showed arm B ≤ arm A
on selection_accuracy. Finding scoped to opaque tool names — see STATUS.md and spec.md for full
run log and diagnosis. H2 (call_correctness) UNTESTABLE on this fixture/model (saturation).

---

### T15 — Paired A/B harness

**Priority:** P1
**Merged:** PR #31 — feat(ab): T15+T16 — paired A/B harness + held-out fixture + real-agent result

`agentgauge/ab_harness.py` with `run_paired_ab`, `compute_mcnemar`, `assert_agent_ne_judge_ne_generator`.
Runner selection prompt updated to show descriptions + param types; CI manipulation-check asserted.

---

### T14 — Non-destructive schema merge (fixer data-loss bug)

**Priority:** P1
**Merged:** PR #29 (3579309) — feat(fixer): T14 — non-destructive schema merge (fixes default/enum/min erasure)

---

### T13 — cost pre-filter (skip generation on already-good tools)

**Priority:** P2
**Merged:** PR #30 (2d2d616) — feat(fixer): T13 — cost pre-filter skip generation on already-good tools

---

### T12 — generator emits `required` arrays in schema fixes

**Priority:** P2
**Merged:** PR #28 (03cefd4) — feat(fixer): T12 — emit required arrays in schema fixes with over-marking guard

---

### T11 — real-judge validation harness + before/after protocol

**Priority:** P2
**Merged:** PR #26 (69e5fdd) — feat(fixer): T9/T10/T11 — auto-fix loop Increment 1

---

### T10 — generation step (Provider-pluggable, generator ≠ judge)

**Priority:** P2
**Merged:** PR #26 (69e5fdd) — feat(fixer): T9/T10/T11 — auto-fix loop Increment 1

---

### T9 — fixer.py skeleton + accept/reject gate + diff emit

**Priority:** P2
**Merged:** PR #26 (69e5fdd) — feat(fixer): T9/T10/T11 — auto-fix loop Increment 1

---

### T8 — Remove duplicate render_json

**Priority:** P3
**Merged:** `claude/eloquent-johnson-e0J9d` — refactor(report): T8 — remove duplicate render_json, migrate test to stable schema (#23)

---

### T7 — JSON report schema stabilization + `agentgauge ci` exit code

**Priority:** P2
**Merged:** `claude/eloquent-johnson-i7MQv` — feat(report,cli): T7 — stable JSON schema and ci subcommand

---

### T6 — Discoverability dimension

**Priority:** P3
**Merged:** PR #18 — fix(scorer): discoverability judge extracts DISTINGUISH score reliably

---

### T5 — Docs/manifest dimension

**Priority:** P3
**Merged:** PR #17 — feat(scorer): T5 — docs/manifest dimension

---

### T4 — JSON + HTML report output

**Priority:** P2
**Merged:** `claude/eloquent-feynman-8lVs8` — feat: add JSON and HTML report output formats

---

### T3 — Robustness dimension

**Priority:** P2
**Merged:** `claude/eloquent-feynman-AMWOk` — feat: implement T3 robustness scoring dimension

---

### T2 — Error-legibility dimension

**Priority:** P2
**Merged:** PR #10 — feat(scorer): T2 — error-legibility dimension

---

### T1 — Task generator + agent runner (selection-accuracy & call-correctness)

**Priority:** P2
**Merged:** PR #6 — feat(runner): T1 — task generator, agent runner, selection & call scoring
