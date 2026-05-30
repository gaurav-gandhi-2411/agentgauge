# TASKS.md

Three-state board: TODO → IN-REVIEW → DONE.
Each item has explicit, testable acceptance criteria.
Autonomous runs: pick the single top TODO, implement it, move to IN-REVIEW.

---

## IN PROGRESS (manual)

### T2 — Error-legibility dimension

**Priority:** P2
**Claimed:** manual session (feat/t2-error-legibility branch)
**Acceptance criteria:**
- `client.py`: `call_tool_with_bad_input(tool_name, bad_args)` injects malformed arguments
  (missing required, wrong type) and returns the raw error response.
- `scorer.py`: `score_error_legibility(tools, client, provider)` asks the provider whether the
  error messages are actionable for an AI agent (0-10 per tool, averaged to 0-100). Integrated
  into `score_all`.
- Tests: mock both client (returns crafted error strings) and provider; deterministic.
- `./scripts/verify.sh` exits 0.

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

## DONE

### T1 — Task generator + agent runner (selection-accuracy & call-correctness)

**Priority:** P2
**Merged:** PR #6 — feat(runner): T1 — task generator, agent runner, selection & call scoring
