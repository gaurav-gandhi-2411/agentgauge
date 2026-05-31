# TASKS.md

Three-state board: TODO → IN-REVIEW → DONE.
Each item has explicit, testable acceptance criteria.
Autonomous runs: pick the single top TODO, implement it, move to IN-REVIEW.

---

## TODO

### T7 — JSON report schema stabilization + `agentgauge ci` exit code

**Priority:** P2
**Category:** Mechanical / schema / CLI — no judge calls, fully mock-testable

#### Part A — versioned JSON schema

`agentgauge scan --out report.json` must emit a JSON document that contains:

- `schema_version` field (string, e.g. `"1"`)
- `overall` score
- One entry for each of the 8 scoring dimensions:
  `schema_completeness`, `description_quality`, `discoverability`,
  `selection_accuracy`, `call_correctness`, `error_legibility`,
  `robustness`, `docs_manifest`

**Acceptance criteria:**
- A new test asserts the emitted JSON contains all 8 dimension keys, an `overall`
  key, and a `schema_version` key.
- `schema_version` is documented in `README.md` (a brief "JSON output schema" section
  listing the top-level fields and their types).
- All existing tests continue to pass.

#### Part B — `agentgauge ci` subcommand

Add `agentgauge ci <target> --min-score N` (integer, 0–100):
- Runs the same scan as `agentgauge scan` (accepts same flags: `--model`, `--trials`,
  `--mock`).
- Exits `0` if `overall_score >= N`.
- Exits `1` if `overall_score < N`.

**Acceptance criteria:**
- Test using `MockProvider`: assert exit code `0` when mock overall ≥ threshold.
- Test using `MockProvider`: assert exit code `1` when mock overall < threshold.
- `--mock` flag wires through so no network/Ollama dependency in tests.
- `agentgauge ci --help` lists `--min-score` with a description.

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
