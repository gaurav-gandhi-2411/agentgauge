# spec.md — Tx: Generator abstains (do-no-harm) on low-grounding tool names

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 0917779 ·
**Branch:** `claude/tx-abstain-no-harm`
**Routing:** DRAFT PR. Changes generator behavior in `fixer.py` — draft-forcing #2/#3 (validation
needs a real-agent A/B), but **NOT condition #1** (does not touch the judge, scorer, rubrics,
calibration, or blending weights). NOT in `AUTO_MERGE_TASKS`.

**This spec, committed at branch start, IS the pre-registration.** Do not edit hypotheses,
thresholds, or fixture definitions after seeing results.

---

## Why

The T16 ground-truth run (#4, valid) found the fixer's description generation ACTIVELY HARMS
selection on opaque-named tools: qwen3:8b fabricated a confident wrong description (`get_a`'s
record-id param described as an "authentication key"), and the wrong description misled the agent
worse than the original vague `"Get."`. Replicated across runs #3 and #4 (Arm B <= Arm A, delta
-10%). Tx makes the generator do no harm: when it lacks evidence to describe a tool correctly, it
must NOT fabricate.

## The degenerate solution — and the guard against it (read this first)

"Abstain on low-grounding tools" is trivially satisfiable by abstaining on EVERYTHING: then Arm B =
Arm A, the harm gate passes, and the description_quality feature is silently gutted while the report
says "fixed." The harm gate alone is gameable. Therefore Tx is accepted ONLY if it passes BOTH:
- **Harm gate (ObsStore, opaque names):** abstain fires → Arm B selection_accuracy >= Arm A (the
  -10% regression is removed).
- **Upside gate (grounded fixture):** abstain does NOT fire → the fixer's grounded description still
  helps → Arm B > Arm A.

Passing harm but failing upside = the degenerate solution. Reject it.

## A prerequisite we have not established

No valid run has EVER shown a good description improving selection for gemma2:9b (run #2, the only
candidate, had the names-only manipulation bug). So before claiming the fixer "preserves upside," Tx
must first prove the upside EXISTS: on the grounded fixture, a hand-written ORACLE good description
must make Arm B > Arm A. Pre-registered branch:
- If the oracle achieves B > A → the upside is real; require the fixer's generation to also achieve
  it (abstain must not fire there).
- If even the oracle cannot beat A → description-based selection help does not exist for this agent.
  Then the correct product behavior is to ABSTAIN GLOBALLY on selection-facing descriptions, and the
  finding is: description_quality generation has no selection upside for capable agents, only
  downside. Report that straight — do not engineer an upside.

---

## Scope

**IN:** safety of selection-facing description generation in `fixer.py` — detection of low grounding,
an abstain behavior, the do-no-harm contract, validation on selection_accuracy.

**OUT:** `call_correctness` (saturated/untestable — that's Ty's headroom fixture); the
`schema_completeness` path (deterministic type/description/required + non-destructive merge — proven,
unaffected, leave it); other dimensions.

## Design

- **Do-no-harm contract:** for any tool, the description the fixer emits must be no worse for agent
  selection than the original. Default-safe action on abstain = leave the ORIGINAL description
  unchanged (do not emit a generated one). New report status `ABSTAINED`, distinct from
  ACCEPTED / REJECTED / SKIPPED.
- **Detection (CC chooses mechanism, justify it) — must be conservative:** false-abstain is
  acceptable; false-confident-generate is the harm. Candidates:
  (a) deterministic grounding signal from evidence in the tool definition (meaningful tokens in the
      tool/param names, presence of a non-trivial existing description, type info), or
  (b) generate-then-verify: reject a generated description that introduces concepts absent from the
      tool definition (the `get_a`->"authentication" failure mode), abstain instead.
  Whatever the mechanism, it must satisfy the CI cases below and the two real-agent gates.
- **Do NOT use the scoring judge (`llama3.1:8b`) for any grounding/verification step** — keep the
  scoring judge out of the generator path so the two never entangle. Use the generator model or a
  separate verifier.

## Required fixtures

1. **Harm fixture = ObsStore (opaque names), already built.** Reuse the run-#4 fixture unchanged.
2. **Upside fixture = grounded-but-vague (new):** tools with MEANINGFUL names and params but
   poor/empty descriptions, where the original (Arm A) causes some wrong selections (headroom) and a
   correct grounded description should disambiguate. Include the ORACLE description (hand-written,
   correct) to establish the upside ceiling. Document each tool and the pre-registered expected
   direction.

---

## Acceptance criteria

1. **CI (deterministic, MockProvider, seed 42, no network):**
   - Detection: on opaque inputs → ABSTAINED, original description preserved, no generated text
     emitted. On grounded inputs → generation fires.
   - ABSTAINED reported distinctly from ACCEPTED/REJECTED/SKIPPED.
   - **Degenerate-guard test:** assert the generator does NOT abstain on a clearly-grounded tool
     (prevents abstain-always). At least one grounded fixture tool must produce a generated
     description in CI.
   - schema_completeness path unaffected (mystery/greet still reach 100 in existing tests).
2. **Real-agent A/B (manual, in PR description — the deliverable), gemma2:9b (!= judge != generator):**
   Reuse the T15 harness. For EACH run, before interpreting, confirm via the harness: per-metric
   Arm-A headroom (<=80% on selection) AND the manipulation check (A vs B prompts differ).
   - **Harm gate:** ObsStore — Arm B selection_accuracy >= Arm A (regression removed). Report table.
   - **Upside, step 1:** grounded fixture with ORACLE description — confirm Arm B > Arm A (upside
     exists). If not, switch to the global-abstain branch above and report that finding.
   - **Upside, step 2 (only if step 1 positive):** grounded fixture with the FIXER's generated
     description — confirm Arm B > Arm A (abstain did not fire; value preserved).
   - State outcomes honestly. Do not tune fixtures or detection after seeing results.
3. scorer.py / judge / rubrics / calibration untouched; generator != judge asserted; verify.sh
   green; coverage >= 60%; committed tests use mocks.

## Housekeeping

- TASKS.md: Tx -> IN-REVIEW on completion. STATUS.md: record the measured gates (harm removed;
  upside preserved OR global-abstain finding). Do not claim the fixer "improves selection" unless
  the upside gate passed with the fixer's own output.
