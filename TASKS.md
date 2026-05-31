# TASKS.md

Three-state board: TODO → IN-REVIEW → DONE.
Each item has explicit, testable acceptance criteria.
Autonomous runs: pick the single top TODO, implement it, move to IN-REVIEW.

---

## IN PROGRESS (manual)

### T5 — Docs/manifest dimension

**Priority:** P3
**Acceptance criteria:**
- `scorer.py`: `score_docs_manifest(target_url, provider)` fetches `<base_url>/llms.txt` and
  any tool-level docs linked from it; asks the provider to rate completeness 0-10 per tool.
  Falls back gracefully (score=0, no crash) if no `llms.txt` exists. Integrated into `score_all`.
- Tests: mock `httpx` (no network); mock provider.
- `./scripts/verify.sh` exits 0.

---

## TODO

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
