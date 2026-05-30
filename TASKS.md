# TASKS.md

Three-state board: TODO → IN-REVIEW → DONE.
Each item has explicit, testable acceptance criteria.
Autonomous runs: pick the single top TODO, implement it, move to IN-REVIEW.

---

## TODO

### T3 — Robustness dimension

**Priority:** P2
**Acceptance criteria:**
- `scorer.py`: `score_robustness(tools, client)` fuzzes each tool with at least three
  malformed-input cases (null values, extra fields, wrong types); verifies no crash / no
  unhandled exception (i.e., errors are returned, not raised). Score is % of probes that
  return a structured error rather than crash.
- Tests: mock `client.call_tool` to simulate crash vs. structured-error responses; deterministic.
- `./scripts/verify.sh` exits 0.

---

### T4 — JSON + HTML report output

**Priority:** P2
**Acceptance criteria:**
- `report.py`: `render_json(report) -> str` serializes `ScoredReport` to indented JSON with
  all fields. `render_html(report) -> str` produces a self-contained single-file HTML page
  (inline CSS, no external dependencies) with the score prominently displayed.
- `cli.py`: `--out <file>` writes JSON when file ends in `.json`; HTML when `.html`.
- Tests: `render_json` output parses with `json.loads`; HTML contains the overall score string.
- `./scripts/verify.sh` exits 0.

---

### T5 — Docs/manifest dimension

**Priority:** P3
**Acceptance criteria:**
- `scorer.py`: `score_docs_manifest(target_url, provider)` fetches `<base_url>/llms.txt` and
  any tool-level docs linked from it; asks the provider to rate completeness 0-10 per tool.
  Falls back gracefully (score=0, no crash) if no `llms.txt` exists. Integrated into `score_all`.
- Tests: mock `httpx` (no network); mock provider.
- `./scripts/verify.sh` exits 0.

---

### T6 — Discoverability dimension

**Priority:** P3
**Acceptance criteria:**
- `scorer.py`: `score_discoverability(tools)` is a heuristic + LLM-judge hybrid:
  (a) static: are tool names distinct, non-generic (`do_thing`, `run_it` score low)?
  (b) LLM judge: given the list of tool names only (no descriptions), can an agent guess
  what each does? Score 0-10 per tool, averaged to 0-100. Integrated into `score_all`.
- Tests: deterministic with MockProvider; cover static heuristic path too.
- `./scripts/verify.sh` exits 0.

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

### T2 — Error-legibility dimension

**Priority:** P2
**Merged:** PR #10 — feat(scorer): T2 — error-legibility dimension

---

### T1 — Task generator + agent runner (selection-accuracy & call-correctness)

**Priority:** P2
**Merged:** PR #6 — feat(runner): T1 — task generator, agent runner, selection & call scoring
