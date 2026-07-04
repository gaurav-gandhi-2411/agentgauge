# Paper framing — two options to choose between (all-negative results)

Your evidence base (final): descriptions help ONLY in confusable-at-scale/under-documented regimes
(T18 +34.5pp; Frontier-T18 Llama-70B +40.8pp; Guard-B recovers documented source safely) — and that
regime is RARE in real servers (EXP-1: 0 of 9 servers with testable confusable families in-regime,
N=10 Python-only pilot; RW1/RW2 anchors
confirm); descriptions can HARM already-resolved families (P2-A account_query); the retrieval-index
thesis is dead (F2 negative across BM25/TFIDF/embedding); and localizing where descriptions would
help FAILS (EXP-3: single-score localizes nothing, pairwise localizes everything, both framings).

---

## FRAMING A — Boundary-establishment ("here's where the field's assumption breaks")

**Thesis:** The field treats tool-description quality as a broadly-important, improvable lever. We map
the BOUNDARY of that assumption: a precise regime where it holds (confusable-at-scale, under-
documented) and a large region where it doesn't (real servers, where capable agents resolve from
names + task context). We quantify how rare the "it-matters" regime is in practice.

**Emphasizes:** the regime MAP as the primary artifact; the prevalence number as the headline
("X% of real servers"); mechanism (why context-rich agents don't need descriptions).
**Positions against:** papers claiming description improvements yield accuracy gains (you show: only
in a rare regime).
**Reviewer reception:** reads as a *contribution* (a map, a boundary, a prevalence measurement) — the
strongest frame for a workshop. Risk: reviewers want the boundary crisply operationalized (your
behavioral regime-classifier delivers this — lean on it).
**Best if:** you want this to read as "we discovered the shape of the phenomenon," positive-in-spirit.

---

## FRAMING B — Cautionary / replication ("popular fixes don't generalize")

**Thesis:** Description-quality interventions (rewriting, source-grounding, retrieval-readiness,
confusability-localization) are widely assumed to help. We stress-test them and show they largely
DON'T generalize to real servers — and some HARM. A caution to practitioners over-investing in
description tooling.

**Emphasizes:** the sequence of interventions TESTED and found wanting; the harm cases; the
practitioner takeaway ("stop polishing descriptions, the agent uses context").
**Positions against:** the tooling/practice trend (description linters, source-grounded generators).
**Reviewer reception:** reads as *replication/cautionary* — respected but lower-prestige; "negative
results" papers in this frame risk "so you tried things and they didn't work."
**Best if:** you want maximum honesty-signal and a practitioner audience, less academic-prestige.

---

## RECOMMENDATION
**Framing A, with B's harm/caution findings as a section within it.** A is the stronger contribution
(a map + a prevalence number is a positive-shaped artifact even though the findings are negative); B's
material (interventions fail, some harm) becomes A's "what happens outside the regime" evidence. A
reviewer champions a boundary paper; they merely tolerate a cautionary one. The prevalence null and
the localizer null both fit A cleanly: "the regime is rare (prevalence), AND you can't even cheaply
find it when it occurs (localizer fails) — so blanket description-tooling is doubly unjustified."

## The honesty spine (both framings — non-negotiable in the writeup)
- N=10, Python-only, public GitHub = a PILOT; the strength is CONVERGENCE (EXP-1 + RW1/RW2 + P2-A +
  doc-density-rarity), not N=10 alone. Never claim "the regime doesn't occur" — claim "rare in
  sampled public servers; the under-documented internal segment is unmeasurable from public data."
- Report the 2 seed-bug false-positives caught/reversed (a credibility asset) + the false-negative
  asymmetry as a threat to validity.
- Tercile labels are RELATIVE (least-documented third of a documented pool), not absolute.
- Frontier claim = ONE open model (Llama-70B), NOT apples-to-apples with gemma; capability ladder
  explicitly DROPPED with justification.
- EXP-3 negative = robust (two framings, two degeneracy modes, identical numbers) — frame as
  "LLM-judge confusability assessment doesn't predict agent behavior," not "our method failed."
