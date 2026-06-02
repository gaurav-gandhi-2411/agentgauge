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

*(empty)*

---

## FUTURE / DEFERRED

### T13 — skip tools already above band X before generating (cost pre-filter)

Skip calling the generator for tools whose baseline score already exceeds a configurable
threshold (e.g. `--skip-above 80`). Avoids burning generator tokens on tools that are
already well-scored. Implementation: add a `skip_above` param to `run_fixer`; tools
scoring above threshold go into `report.skipped` with a "already_above_threshold" reason.

---

### Re-calibrate judge bands against a ≥30B model

Re-calibrate `score_error_legibility` rubric bands against `llama3.3:70b` (or
equivalent ≥30B model) when a ≥64GB host is available. Model pinning makes this a
config + re-measure exercise, not a rebuild: update `CALIBRATED_JUDGE_MODEL` in
`cli.py`, re-run the three-tier calibration cases, and update `CLAUDE.md`. The
test suite guarantees ordering + actionability gap regardless of which model is used.

---

## DONE

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
