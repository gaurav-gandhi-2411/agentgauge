# TASKS.md

Three-state board: TODO → IN-REVIEW → DONE.
Each item has explicit, testable acceptance criteria.
Autonomous runs: pick the single top TODO, implement it, move to IN-REVIEW.

---

## TODO

### T8 — Remove duplicate render_json

**Priority:** P3
**Category:** Mechanical / refactor — no judge calls, no real server, no real-model/network
behavior. Auto-merge eligible.

**Context:** `report.py` has two functions: `render_json_stable` (the pinned public `"1.0"` schema
the CLI writes to `--out` files) and the old `render_json` (emits `{overall, dimensions,
tool_count}`) which is no longer called by the CLI but is still exported and referenced by one
legacy test. Risk: a future caller that imports `render_json` instead of `render_json_stable` would
silently emit the wrong schema and break the public contract.

**Acceptance criteria:**

- Delete `render_json` from `report.py`.
- Migrate `test_render_json_parses` to test `render_json_stable` instead. The migrated test must
  assert the stable schema exactly: top-level keys are exactly `{schema_version, overall_score,
  dimensions}`, `schema_version == "1.0"`, each entry in `dimensions` has keys `{name, score,
  weight}`, and all 8 dimension names are present.
- Grep the codebase to confirm no other caller references the deleted `render_json`; if any exists,
  repoint it to `render_json_stable`.
- No change to `render_json_stable`'s output or signature.
- `verify.sh` exits 0: ruff, mypy, all tests pass.

---

## IN PROGRESS (manual)

*(empty)*

---

## IN-REVIEW

*(empty)*

---

## FUTURE / DEFERRED

### Re-calibrate judge bands against a ≥30B model

Re-calibrate `score_error_legibility` rubric bands against `llama3.3:70b` (or
equivalent ≥30B model) when a ≥64GB host is available. Model pinning makes this a
config + re-measure exercise, not a rebuild: update `CALIBRATED_JUDGE_MODEL` in
`cli.py`, re-run the three-tier calibration cases, and update `CLAUDE.md`. The
test suite guarantees ordering + actionability gap regardless of which model is used.

---

## DONE

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
