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

### T17 — Selection-limited fixture (Q1: does description-help exist?)

**Branch:** claude/t17-selection-limited — DRAFT PR.

8 confusable clusters (2 tools each, 32 pre-registered tasks). Arm A: empty
descriptions. Arm B: ORACLE (pre-registered, hand-written) descriptions.

**Q1 oracle A/B result (gemma2:9b, 2026-06-03): ABORTED — fixture-quality, NOT a null.**
Pre-check aborted: Arm A baseline 81.2% (stability run 1, all 32 tasks surviving,
3 trials each). Above the 70% headroom ceiling. Task-clustered oracle table not run
per pre-registration; no A-vs-B comparison was made.

**Cross-run through-line:** T17 completes a three-fixture pattern. Every fixture tested
has landed in a dead zone — either names are self-describing (saturated Arm A), verbose-
domain names the model resolves from priors (T17, 81.2%), or opaque names where
descriptions carry no recoverable signal either (ObsStore). No fixture has produced
the middle regime: names ambiguous enough to need descriptions, descriptions informative
enough to help.

**⚠ Do NOT attempt a "shorter/opaque names" redesign.** Shortening names or making
them more abbreviated slides toward the ObsStore regime — where names are signal-less
AND descriptions are not description-recoverable (fixer-generated descriptions were
hallucinated; real-agent arm B ≤ arm A). That regime does not test description-recovery;
it tests hallucination tolerance. It is not a valid probe of description_quality or
discoverability.

**Design decision required before any T17 rebuild.** The question is whether a confusable-
name regime exists at all for this agent class, or whether `selection_accuracy` is
structurally description-insensitive for gemma2:9b. See STATUS.md for the cross-run
framing. Rebuild only with a pre-registered fixture design that has a principled argument
for why the target names are ambiguous-but-recoverable (not just shorter/opaque).

---

### Tx — Generator abstains on opaque tool names (fixer description quality)

**Branch:** claude/tx-abstain-no-harm — DRAFT PR, A/B complete, per-task analysis pending.

Grounding detection added to `fixer.py`: when all tokens in a tool name are either
single-character or in the `_GENERIC_TOKENS` vocabulary (get, set, put, del, etc.),
`is_low_grounding` returns True and `run_fixer` records `ABSTAINED` instead of calling
the generator. Degenerate-guard CI test asserts `transform_scale` does NOT abstain.
A/B results: harm gate PASS (ObsStore all abstain, delta=0%); upside step 1 POSITIVE
(oracle +20pp, p<0.05); upside step 2 DIRECTIONAL (+10pp, b+c=5<10, significance pending
powered re-run — see Tx-val below).

---

## FUTURE / DEFERRED

### Tx-val — Powered upside re-run (grounded-fixture significance)

Tx step 2 showed a directional +10pp improvement (Arm B 90% vs Arm A 80%) but is
underpowered: only ~2 tasks had headroom (Arm A at 80%, just at the ceiling), and the
McNemar b+c=5 <10 makes chi-square unreliable. The "fixer improves selection" claim requires
a properly powered, task-clustered analysis.

**Acceptance criteria:**
- New grounded fixture with >= 30 tasks, designed so Arm A baseline is ~50-60% (not 80%).
  Tool names must be meaningful enough to avoid abstain AND tasks must be ambiguous enough
  to create real headroom under Arm A.
- **Task stability pre-screen:** before running the full A/B, run Arm A alone twice; drop
  any task where Arm A accuracy varies by more than 1 trial across runs (run-to-run-flaky
  tasks corrupt the task-level analysis). Tx's normalize tasks were flaky (0/5 in both
  full runs but arm B varied) and must be excluded or replaced.
- Analysis clustered by task (task is the unit; trials are repeated measures). Use a sign
  test on tasks (B>A vs B<A) or a mixed-effects model, not trial-level McNemar.
- **Detector generalization check:** before the A/B, verify the grounding detector handles
  opaque names beyond get/put/del -- e.g. single-letter names (`a`, `b`), numeric suffixes
  (`tool_1`, `op_2`), non-CRUD generic verbs (`process_x`, `handle_z`), and CamelCase
  variants (`GetA`, `SetB`). Confirm each correctly returns `is_low_grounding=True`.
  Document any names where the detector fails and add CI coverage for the new cases.
- Only THEN claim "fixer improves selection" in STATUS.md or PR descriptions.

**Pre-condition:** own spec; do NOT inherit Tx's fixtures or tasks unchanged.

---

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
