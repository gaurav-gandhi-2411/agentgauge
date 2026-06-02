# spec.md — T12: Generator emits `required` arrays

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` (after PR #26 merge) ·
**Branch:** `claude/t12-required-arrays`
**Routing:** DRAFT PR. Generation-only — does NOT touch scorer.py, so NOT draft-forcing #1.
Real-generator-dependent, so committed tests mock the generator; the required-array correctness
check is the human-reviewed gate. NOT in `AUTO_MERGE_TASKS`.

---

## Problem

Increment 1 left `mystery.schema_completeness` at 66.7/100: the generator adds type + description
but never emits a `required` array, so the heuristic's third point (required params / params with
defaults) is never earned. Every tool with mandatory params caps at 2/3. T12 closes this.

---

## The real hazard (read before implementing)

Score-green ≠ correct, again. The schema_completeness heuristic only checks that `required` is
populated — it does NOT check that the right params are in it. So an LLM that marks an **optional**
param required would *raise the score while making the schema wrong*. Over-marking is a correctness
regression the heuristic rewards. T12 must be conservative and the gate must verify semantic
correctness, not just the delta.

**Ground truth = the tool signature.** For Python MCP fixtures (echo_server.py), a param with no
default is required; a param with a default is optional. When source is reachable, derive required-ness
from the signature. When only the introspected schema is available (generic remote servers), infer
conservatively from signature-absent signal and mark required ONLY on strong evidence.

---

## Scope

**IN:** `fixer.py` generation step emits a `required` array as part of the schema fix for
`schema_completeness`. Conservative required-ness inference. Target fixture = echo_server.py.

**OUT:** new dimensions; the "skip tools already above band" cost pre-filter (queue as T13);
anything touching scorer.py.

---

## Acceptance criteria

1. When fixing `schema_completeness`, the candidate schema includes a `required` array.
2. **Deterministic re-score:** `mystery.schema_completeness` 66.7 → 100.0 (exact, no trials),
   *provided* mystery's x/y are intended required (confirm from signature — step 1 of kickoff).
3. **Correctness gate (human-reviewed, the point of T12):** generated `required` for mystery matches
   signature-derived required exactly — x and y both present, nothing extra.
4. **No over-marking:** a tool with an optional (defaulted) param must NOT have that param in
   `required`. If echo_server has no such tool, the executor adds a fixture tool with a defaulted
   param and asserts it stays out of `required`.
5. **No regression:** `add` / `echo` (already 100) unchanged; good-tool descriptions not churned.
6. scorer.py untouched; `generator_model != judge_model` still asserted; verify.sh green,
   coverage ≥ 60%; committed tests mock the generator (seed 42, no network).

---

## Validation

- CI: MockProvider returns a candidate with a known `required` array; assert the schema-merge and
  re-score plumbing are correct, and that the over-marking guard rejects/strips a defaulted param.
- Real-generator (manual, in PR description): run the fix on echo_server with qwen3:8b; record the
  emitted `required` arrays per tool and the schema_completeness before/after. Reviewer confirms
  required-ness is semantically correct against signatures, not just that the score rose.

---

## If x/y are NOT meant to be required

Then 66.7 is the correct ceiling for mystery and T12 narrows to: emit `required` only where the
signature/semantics warrant, and the acceptance number for mystery is its true arity, not 100.
Confirm before generating.
