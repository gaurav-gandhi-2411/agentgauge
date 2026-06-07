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

### Q2b — Catalog-aware fixer (cross-tool context injection)

**Branch:** `claude/q2b-catalog-aware` | **CI:** verify.sh green (339 tests, 90% coverage)

**Motivation:** Q2a showed the current per-tool generator recovers 12.5% of the T18 oracle gain
(F-vs-A p=0.50, not significant). All 14 misses were (i): cross-tool distinctions that cannot be
encoded from `{name, current, schema}` alone. Two tools received confidently wrong descriptions
(store_item cache→"persistent"; forward_record POST→"retrieval") — net-negative on confusable
catalogs. The fix is to inject sibling context into the generator prompt so it can encode the
within-family distinguishing dimension.

**What was implemented:**
- `_select_neighbors(target, catalog, k=6)` in `fixer.py`: Jaccard token-overlap similarity on
  lowercased name tokens (splits on underscores/camelCase). Deterministic; does NOT read family
  labels — works on `Tool.name` only, as an unlabeled 200-tool catalog would present it.
- `_DESC_GENERATOR_CATALOG_AWARE_PROMPT`: catalog-aware prompt showing target + K neighbors
  (names, schemas, current descs) with explicit NO-FABRICATION guard: "If NOT meaningfully
  different from a neighbor on the available evidence, say what it does plainly and DO NOT invent
  a distinction."
- `_generate_description(tool, generator, *, neighbors=None)`: when `neighbors` is non-empty,
  uses catalog-aware prompt; otherwise falls back to original per-tool prompt.
- `run_fixer(..., catalog_aware=False, neighbor_k=6)`: when `catalog_aware=True`, computes
  neighbors from `tools` list before generating.
- `scripts/generate_arm_f_descriptions_q2b.py`: Phase 1 script (catalog-aware generation).
- `examples/t18_q2b_server.py`: Arm F Q2b MCP server fixture.
- `scripts/run_q2b_three_arm.py`: Phase 2 three-arm experiment script (reuses Q2a harness).
- 11 new CI tests: neighbor selection determinism, no-family-label assertion, token similarity
  ranking, prompt content verification (no-fabrication guard present, neighbors in prompt),
  MockProvider real-diff and identical-neighbor cases, run_fixer catalog_aware integration.

**Pending real-agent run (Phase 1 + Phase 2):**
1. `python scripts/generate_arm_f_descriptions_q2b.py` (qwen3:8b, GPU-exclusive)
2. `ollama stop` → verify `ollama ps` empty
3. `python scripts/run_q2b_three_arm.py` (gemma2:9b watchdog)
4. Report Sections A–E + no-fabrication control + verdict.

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

### Q2a — Three-arm fixer recovery (does the current fixer recover the T18 gain?)

**Merged:** PR #42 — feat(q2a): three-arm fixer recovery — LOW recovery (12.5%), all misses (i), Q2b warranted

Three-arm A/B on `selection_accuracy` (60-tool confusable catalog, 18 contested tasks, gemma2:9b, 5 trials).
Arm A=0.0% / Arm F=11.1% / Arm O=88.9%. Recovery fraction (F−A)/(O−A)=0.125. F-vs-A p=0.50 (not significant).
All 14 misses classified (i): cross-tool distinction only. ≥2 tools received confidently wrong descriptions
(store_item→"persistent", forward_record→"retrieval"). Per-tool fixer is net-negative on confusable catalogs;
catalog-aware generation (Q2b) is the motivated next step.

---

### T18 — Discoverability at scale (confusable catalog oracle A/B)

**Merged:** PR #41 — feat(t18): discoverability at scale — oracle A/B POSITIVE (+34.5pp discrimination, 60-tool confusable catalog)

60-tool catalog (10 families × 6 near-neighbors), 40 pre-registered tasks, 5 trials per arm, gemma2:9b agent. GPU-exclusive run (watchdog-confirmed, 2026-06-07). **POSITIVE.** Within-family discrimination: +34.5 pp on parse-success calls (62.9% → 97.4%), 16/16 contested tasks improved, p=0.0000. Parse-stabilization separate finding: 12.5% → 2.5% malformed-call rate — catalog ambiguity destabilizes call formation at scale, not just selection. Effect is scale-gated (≥60-tool density required; T17 at 16 tools saturated Arm A at 81.2%). First located behavioral effect for a description-facing dimension.

---

### Ty — H2 headroom fixture (call_correctness oracle A/B)

**Merged:** PR #36 (d138369) — feat(ty): call-correctness oracle A/B — two-run experiment (ABORTED)

Two-run oracle A/B on call_correctness, gemma2:9b agent. Run 1: tautological POSITIVE (oracle supplies unguessable enum token → agent echoes it; not a genuine partial-ability result). Run 2: Arm A 33.3% < 40% headroom gate → STOP, no A/B comparison made. Combined verdict: ABORTED — cannot establish a partial-ability regime for this constraint class on this model. Guessable-constraints follow-up tracked as Ty2 (PR #37, open draft on separate branch).

---

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
