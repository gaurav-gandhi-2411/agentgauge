# spec.md — Q5: the docstring-mismatch / asymmetric-evidence guard (DOC-scoped + guard)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 17c92b1 ·
**Branch:** `claude/q5-distinction-guard`
**Routing:** DRAFT PR. Generator prompt/logic change + real-agent A/B. Draft-forcing #2/#3.
**NOT condition #1.** Reuses the Q3/Q4 fixture unchanged.

**Pre-registration:** committed at branch start. The guard design, the dual-axis acceptance (safe
AND recovering), and the control/structural task split are fixed before the run.

---

## Why

Q4 found that in the scoped regime, providing neighbor DOCSTRINGS opens a fabrication vector:
the generator has the TARGET's body (verified behavior) but only NEIGHBORS' surfaces (claimed
behavior), so it contrasts target-body against neighbor-docstring and invents false distinctions
(find_entries "count vs entries" — both return counts). Q4-BODY-scoped was safe only by REMOVING
the docstrings — which discards useful signal real servers have. The current prompt already says
"no fabrication"; exhortation is insufficient. Q5 adds a STRUCTURAL guard so DOC-scoped becomes safe
WITHOUT discarding docstrings, because real servers are documented and "strip your docstrings" is not
shippable advice.

## Root cause (name it precisely)

ASYMMETRIC EVIDENCE. The generator can verify the TARGET's behavior from its body but only KNOWS the
NEIGHBORS' CLAIMS from their surfaces. Any comparative statement ("unlike X, which does Y") asserts a
fact about a neighbor the generator cannot verify. That is the fabrication mechanism.

## Guard design (Guard B — target-grounded, no comparative claims)

The fix is to forbid unverifiable comparative claims, not to remove evidence:
- The generator may state distinctions ONLY as POSITIVE facts about the TARGET, grounded in the
  target's own body ("This tool returns a count of matching entries and writes to a 5-minute TTL
  cache"). It must NOT make claims about what a neighbor does ("unlike lookup_data, which returns
  full entries").
- Neighbor surfaces are provided ONLY to tell the generator WHICH AXES may be discriminating (so it
  knows to mention the return type / storage / permanence the family varies on) — never as a basis
  to assert a neighbor's behavior.
- Prompt change: explicit instruction + 1-2 examples showing target-grounded phrasing (good) vs
  comparative neighbor-claims (forbidden). Keep the scoped-source structure and the shared extractor.

### Why not the alternatives (record the reasoning)
- "Symmetric surface-only" (compare target-surface vs neighbor-surface): safe but discards the body,
  which is the signal that closed the gap in Q3/Q4 — would regress recovery. Rejected.
- "Detect docstring-vs-body disagreement and suppress": narrower; only catches the find_entries
  case, not the general asymmetry. Guard B subsumes it.

## The risk this must be validated against

Forbidding comparative phrasing could REGRESS RECOVERY: a purely self-describing "returns a count"
may not help the agent RULE OUT a sibling the way a contrastive description does. So Q5 is a TWO-AXIS
test — it must be BOTH safe (no fabrication on equivalent controls) AND still recovering (on the
structural contested tasks). A guard that is safe but drops recovery toward Arm-A is a FAIL, not a
win.

---

## Design (arms; reuse Q3/Q4 fixture)

- Arm A = empty (floor). Arm O = oracle (ceiling).
- Arm Q4-DOC = Q4 DOC-scoped, no guard (reference: recovers ~100% on the 6-task subset, FABRICATES
  4/4 controls). 
- Arm Q5 = DOC-scoped + Guard B.
- Generator gets target scoped body + neighbor surfaces (docstrings INCLUDED — that's the point;
  the guard must make docstrings safe, not require their removal). qwen3:8b; agent gemma2:9b;
  phase-separated GPU.
- Metric: parse-success selection_accuracy on the SAME 6 structural contested tasks as Q4 (NOT
  control_search — excluded, ambiguous gold). Recovery (Q5-A)/(O-A); sign test n=6.

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** the guard prompt forbids comparative neighbor-claims
   and instructs target-grounded phrasing (assert the instruction + example present); neighbor
   surfaces still included (docstrings present in prompt); MockProvider: a target-grounded description
   passes through, and (if a lightweight post-check is added) a description containing a comparative
   "unlike <neighbor>" claim is flagged. No real model in committed tests.
2. **Real-agent A/B (manual, in PR description) — BOTH axes required:**
   - GPU exclusivity + parse_failed FIRST.
   - SAFETY: on the 4 equivalent-control tools, classify Q5 descriptions FAITHFUL-EQUIVALENT /
     INCIDENTAL-BUT-TRUE / FABRICATED. Q5 target: NO FABRICATED (vs Q4-DOC's 4/4 FABRICATED). This is
     the guard working.
   - RECOVERY: table A / Q4-DOC / Q5 / O on the 6 structural contested tasks + recovery + sign test.
     Q5 target: recovery must remain HIGH (not regress toward Arm-A). Report the exact number.
   - Per-task: for any structural task Q5 now MISSES that Q4-DOC passed, show the Q5 description —
     this is the "guard over-suppressed and killed a real distinction" failure, diagnose it.
   - Verdict matrix:
     - SAFE + RECOVERS (no fabrication AND recovery ~ Q4-DOC): the guard works — DOC-scoped is now
       safe without stripping docstrings. Best outcome; this is the shippable config.
     - SAFE + REGRESSES (no fabrication but recovery drops): the guard over-suppressed; target-only
       phrasing isn't discriminating enough. Boundary: safety costs recovery -> body-only (Q4) stays
       the safe-and-recovering config and docstrings can't be made safe this way.
     - STILL FABRICATES: Guard B insufficient; report what it fabricated and from what.
3. scorer.py / judge / rubrics / calibration / schema-gen path untouched; generator != judge
   asserted; verify.sh green; coverage >= 60%.

## Housekeeping

- TASKS.md: Q5 (TODO -> IN-REVIEW). STATUS.md: record SAFETY and RECOVERY for Q5 vs Q4-DOC, the
  verdict cell, and whether documented source can now be used safely (the deployment question Q4
  left open). Do not claim "docstrings are safe with the guard" unless Q5 was BOTH no-fabrication
  AND non-regressing.
