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

### Ty2 — guessable-constraints oracle A/B (call_correctness, last gemma attempt)

**Branch:** `claude/ty2-guessable-constraints`

Oracle A/B on `call_correctness` using guessable-but-error-prone constraints. CI: 25 fixture
tests (integrity, stability screen, manipulation check, inferability, gold-validity,
`_is_correct_call` unit tests); 293 total tests, 89.61% coverage.

30 contested tasks (5 per tool), 4 constraint types:
- near-miss enums: `update_order_status` (settled/voided/disputed/processing/pending),
  `create_support_ticket` (P1/P2/P3/P4), `set_asset_visibility` (public/unlisted/internal/archived)
- format-precision: `schedule_callback` (RFC3339+offset vs naive datetime)
- unit-magnitude: `set_request_timeout` (ms vs seconds, per-task range check)
- commonly-omitted required field: `charge_customer` (idempotency_key presence)

Real-agent results: pending (gemma2:9b, 5 trials, 3 stability).

---

### Ty — H2 headroom fixture (call_correctness oracle A/B)

**Branch:** `claude/ty-call-correctness`

Two-run oracle A/B experiment on call_correctness. CI: fixture integrity, stability screen,
manipulation check, inferability tests (268 tests, 89.61% coverage). Real-agent runs:
gemma2:9b, 5 trials main / 3 stability.

**Run 1 (PRELIMINARY — floor-effect design):**
- 32 tasks: 16 easy (no constrained params) + 16 hard (arbitrary enum codes)
- Hard-task Arm A: 0% by construction (ACQ_BURST/CODEC_R8 etc. are unguessable)
- Aggregate Arm A: 50% (padded by easy tasks); headroom gate "passed" artificially
- Sign test (contested tasks only): n_plus=16, n_minus=0, ties=0, p=0.0000
- Verdict: technically POSITIVE but near-tautological (agent read the enum token from
  schema and echoed it — not evidence of reliability improvement in a partial-ability regime)

**Run 2 (FIXTURE FAILURE — Arm A below headroom gate):**
- 30 tasks, all hard, mixed constraints: format patterns / semi-conventional enums / non-standard units
- Stability screen: 0 tasks dropped
- Arm A baseline (stability run 1): 33.3% → STOP (gate: 40–70%)
- Format patterns (ERR[0-9]{3}, [A-Z]{2}[0-9]{2}) and non-standard units (centiseconds, deciseconds)
  proved harder for gemma2:9b than expected; Arm A never reached partial-headroom regime
- No A/B comparison made (pre-registered gate honored)

**Combined verdict:** ABORTED on the non-tautological hypothesis. Cannot establish a
partial-headroom regime with these constraint types for gemma2:9b. Run 1's tautological
POSITIVE stands (oracle supplies an unguessable token → agent emits it) but this is not
the product-relevant claim. Schema quality in the call-construction stage remains untested
in a genuine partial-ability regime.

**Acceptance criteria met?** Manipulation check: PASS. Inferability: PASS. Headroom gate:
FAIL (Run 1 trivially, Run 2 genuinely). Honest verdict: recorded (ABORTED).

**PR:** #36 (draft)

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

### T17 — Selection-limited fixture (Q1: does description-help exist?)

**Merged:** PR #33 (abe54f9) — feat(t17): selection-limited fixture + Q1 oracle A/B (fixture-quality failure, ABORTED)

ABORTED — fixture-quality failure, not a null. Arm A baseline 81.2% > 70% headroom ceiling; oracle arm never run per pre-registration. Cross-run through-line: no confusable-name regime found where (a) names are ambiguous to the agent AND (b) descriptions carry recoverable signal. `selection_accuracy` may be behaviorally description-insensitive for gemma2:9b on standard API vocabulary. Design decision required before any rebuild — see FUTURE/DEFERRED notes in STATUS.md.

---

### Tx — Generator abstains on opaque tool names (fixer description quality)

**Merged:** PR #32 (a4652b5) — feat(fixer): Tx — abstain on low-grounding tool names (do-no-harm guard)

Grounding detection in `fixer.py`; `ABSTAINED` status in `FixReport`. Harm gate PASS; upside step 1 POSITIVE (oracle +20pp, p<0.05); upside step 2 NO REPRODUCIBLE TASK-LEVEL EFFECT. Powered re-run required — tracked as Tx-val in FUTURE/DEFERRED.

---

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
