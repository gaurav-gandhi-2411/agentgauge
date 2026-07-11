# spec.md — PAPER REWRITE (Option B): maximize reach WITHOUT inflating any claim

**File:** docs/paper/paper.md (branch claude/paper-evidence-prep, current HEAD 341419c).
**Nature:** REFRAME + REPACKAGE + RESTRUCTURE only. NO new claims, NO new experiments, NO un-scoping.
Every number and every caveat in the current draft STAYS. This is a readability/reach edit, not a
scope edit.

## The razor (read before every edit)
Option B increases readership by surfacing the TRUEST, most INTERESTING finding the paper already
contains — the counterintuitive multi-objective inversion — and by giving readers an ADOPTABLE tool.
It does NOT increase reach by making any claim broader than its evidence. If a reframed sentence reads
as more general/sweeping than the current draft's version of the same claim, it is WRONG — revert it.
The honesty (N=10, one density point, one non-frontier model, one-fixture retrieval result,
lower-bound, false-negative asymmetry) is the paper's credibility and its ceiling; do not trade it for
reach.

## MOVE 1 — Elevate the multi-objective inversion to the CENTRAL thesis
Currently buried in §4.4 (mechanism throughline) and §4.3.3 (retrieval). It is the paper's most
interesting, most portable, most counterintuitive TRUE finding, and it is under-billed.

The finding, stated at its HONEST maximum: **tool-description quality is not a single "better/worse"
axis. The precision that helps an agent disambiguate WITHIN a confusable family is a DIFFERENT
property than what a context-rich agent needs (which it often gets from the task, not the
description) or what a retrieval index rewards — and on the catalogs we tested, optimizing for one can
NEUTRALIZE or HARM the others.** "Better descriptions are uniformly better" is the assumption; "description
quality is multi-objective and the objectives can conflict" is the finding.

SCOPE GUARD (mandatory — this is the least-evidenced, most-interesting half): the retrieval-harm
result is ONE synthetic catalog, three retrievers (§4.3.3). The selection-help result is ONE density
point (§4.2.1). So the inversion is presented as an OBSERVATION with a legible mechanism, tested on
specific fixtures — NOT a proven general law. Frame: "we observe, on the fixtures tested, that these
pull in opposite directions; the mechanism is legible [precision matches implementation-level detail,
which helps within-family selection and hurts coarse-query retrieval]; we do not claim this
generalizes beyond the fixtures (§8.1)." The interestingness comes from the counterintuitive
DIRECTION + the legible mechanism, NOT from an over-broad claim.

- Pull the inversion into the ABSTRACT's opening (it currently opens on "the assumption is widely
  held"; open instead on the surprising multi-objective finding, THEN the boundary map).
- Give it a named home in the body (promote §4.4 from "mechanism throughline" to a titled synthesis,
  e.g. "§4.4 Description quality is multi-objective") — keep all its existing scope hedges.

## MOVE 2 — Name + box the behavioral regime test as an ADOPTABLE diagnostic
The paper's reusable artifact (its "thing you can build on," scoped honestly) is the behavioral
regime definition (§5.1): before investing in description tooling, check (a) does the agent actually
FAIL a contested task on current descriptions, AND (b) does an oracle/near-perfect description RECOVER
it. Neither -> no headroom / unfixable -> description tooling won't help.

- Give it a NAME (propose 2-3 for GG; memorable, not cute; descriptive — e.g. "the headroom check,"
  "the two-condition regime test"). 
- Present it ONCE as a small boxed/numbered PROCEDURE a practitioner can run, in the Discussion (§7)
  or a short dedicated subsection — the "what to do Monday morning" artifact.
- SCOPE GUARD: present it as a decision procedure whose VALIDATION is this paper's own experiments —
  NOT as a validated general tool. It is "here is the check we used and recommend," not "here is a
  proven instrument." Do not let naming it imply more validation than N=10 supports.

## MOVE 3 — Restructure the Introduction to lead with the hook
Current intro leads with §1.1 "the assumption under test." Re-order so the FIRST thing a reader meets
is the counterintuitive claim: you'd assume better descriptions uniformly help selection AND
retrieval; we find description quality is multi-objective (the properties conflict), the regime where
it helps selection at all is narrow, and you can't cheaply tell if you're in it. THEN the assumption,
THEN the roadmap. Hook -> gap -> contributions. Keep §1.1's citations and the GitHub tension intact,
just after the hook.

## TITLE — propose 2-3 for GG (honest AND catchy)
Current: "When Does Tool-Description Quality Improve Agent Behavior? A Regime Analysis."
Candidates to draft (must be honest — helps/harms/doesn't-matter is the real triad):
- "Better Tool Descriptions Aren't Uniformly Better: When Description Quality Helps, Harms, or Doesn't
  Matter"
- "Tool-Description Quality Is Multi-Objective: A Regime Analysis of Selection, Retrieval, and Harm"
- keep current as the safe option.
GG picks. The title may headline the inversion ONLY if the body's scope guards are intact.

## HARD CONSTRAINTS — DO NOT CHANGE (diff-verify byte-identical after edit)
The six credibility passages stay verbatim: abstract's caveats, §4.2.3 survival-not-growth-not-
frontier, §5.4 seed-bug episode, §8.3.1 false-negative asymmetry, §1.1 GitHub/RW1 tension, §5.5
lower-bound scope. Every number stays (grep-verify). EXP-1 stays 0/9. Retrieval stays one-fixture.
No caveat becomes less prominent than it currently is. The appendices (A.6, A.7) stay.

## Acceptance
- The inversion is the abstract's opening hook and a titled body synthesis, WITH its one-fixture/
  one-point scope stated in the same breath.
- The regime test is named and boxed as an adoptable procedure, scoped as "the check we used," not a
  validated instrument.
- Intro leads with the hook.
- 2-3 title options proposed.
- ANTI-INFLATION AUDIT (required): after the rewrite, re-run the adversarial overclaim sweep
  specifically checking that NO reframed sentence is broader than the current draft's equivalent.
  Report any sentence where the reach-reframe outran the evidence, with the conservative revert.
- Diff-verify the six protected passages byte-identical; grep-verify every number still present.

Then GG reads the reframed abstract + intro + §4.4 + the boxed regime test + the anti-inflation audit.
