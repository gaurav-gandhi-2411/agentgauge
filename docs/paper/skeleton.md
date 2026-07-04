# Paper Skeleton — "When Does Tool-Description Quality Actually Improve Agent Behavior? A Regime Analysis"

**Status:** Section headers + one-line intent only — NO PROSE. Framing-agnostic: works under
either Framing A (boundary-establishment) or Framing B (cautionary/replication) from
`paper_framing_options.md`. Where a section's *emphasis* would shift with framing, a bracketed
note says how; the section itself does not change.

Scope: EXP-4 (regime map, consolidation) + EXP-1 (prevalence) + EXP-3 (localizer). EXP-2
(capability ladder) is DROPPED — ratified by GG, see `spec.md`.

---

### Abstract
One paragraph. States the question, the method (frozen protocol + regime map + prevalence +
localizer), and the headline: description quality helps only in a narrow, characterizable
regime (confusable-at-scale + documented source), that regime is rare in a sampled pilot of
public servers, and even locating the regime cheaply (pairwise localization) fails.
[Framing A: lead with "we map the boundary." Framing B: lead with "popular fixes don't
generalize." Same facts, different opening clause.]

### 1. Introduction
1.1 The assumption under test: tool-description quality is treated as a broadly-applicable,
    improvable lever for agent tool-use.
1.2 What this paper does instead: a falsifiable, regime-bounded map, a prevalence measurement,
    and a test of whether the regime can be cheaply localized.
1.3 Contributions list (3 bullets, one per EXP: regime map, prevalence null, localizer null).
1.4 Roadmap paragraph.

### 2. Related Work
2.1 Tool/function-calling agent benchmarks and description-quality interventions (the practices
    this paper stress-tests).
2.2 MCP ecosystem and server-documentation practices.
2.3 Retrieval-augmented tool selection (contextualizes the F2 retrieval-readiness finding).
2.4 Positioning: [A] against papers claiming blanket description gains; [B] against the
    description-tooling/linting practice trend — same related-work section serves both.

### 3. Methods — The Frozen Evaluation Protocol
3.1 Governance: pre-registration, condition-#1 (judge-touching) escalation, null-first-class.
3.2 Frozen configuration table (judge/generator/agent models+seeds, trial counts, sign-test α,
    headroom ceiling, min contested tasks) — reproduced from `docs/research/frozen_protocol.md`.
3.3 The 3-outcome + PARSE-FAILED classifier, and why parse-failure is reported separately.
3.4 Effect measurement: task as unit of analysis, stability screen, sign test.
3.5 Cross-experiment comparability rules — what is and is not apples-to-apples (flags
    FRONTIER-T18 and EXP-2's dropped ladder explicitly as NOT part of the controlled comparison).

### 4. EXP-4 — Regime Map (Results I)
4.1 Method: consolidation of already-banked findings, no new runs.
4.2 Where it helps:
    - 4.2.1 Confusable-at-scale (T18): density-gated discrimination effect, +34.5pp.
    - 4.2.2 Under-documented source with docstrings (Q3→Q6 Guard-B progression): the
      safety/recovery inversion story (whole-file vs scoped, docstrings vs body-only).
    - 4.2.3 Strong-agent survival (FRONTIER-T18): effect does not collapse at 70B open-weight
      scale. (Sourcing gap resolved — see `evidence_table.md` §1.3; cites the committed,
      hash-verified fixture, not the original unmerged-branch prose.)
4.3 Where it doesn't / harms:
    - 4.3.1 No-headroom real servers (RW1 GitHub, RW2 AWS IAM).
    - 4.3.2 Harm on already-resolved families (P2-A account_query, −20pp).
    - 4.3.3 Retrieval-readiness closed negative (F2: BM25/TFIDF/embedding, all harmed).
    - 4.3.4 Single-score discoverability cannot localize (motivates EXP-3).
4.4 Mechanism throughline: description precision helps within-family discrimination, is
    orthogonal/anti-correlated to context-rich-agent needs and to retrieval.
[Framing A: this section IS the paper's primary artifact — lead the results with it, longest
section. Framing B: reframe 4.3 as the lead ("here's what we tried and where it failed"),
4.2 becomes "the narrow exception."]

### 5. EXP-1 — Server-Population Prevalence (Results II)
5.1 Question and behavioral (non-circular) regime definition — the two-condition test.
5.2 Sampling frame: history of the frame's 5 revisions (v1→v5), final N=10 Python-only scope,
    and why non-Python mechanical extraction was dropped (reliability, not choice).
5.3 Headline result: 0/9 scored servers IN-REGIME; per-tier null; RW1/RW2 anchors as
    independent confirmation.
5.4 The seed-bug episode: 2 false positives caught and reversed before reporting — presented as
    a credibility asset (per `paper_framing_options.md`'s honesty spine), not hidden.
5.5 Scope caveat: public-servers-skew-documented lower bound; do not generalize to the
    unsampleable under-documented internal segment.

### 6. EXP-3 — Confusability Localization (Results III)
6.1 Motivation: the structural limit of single-score discoverability (RW1/RW2 score-validity
    gap) — a positive method is attempted on top of the negative.
6.2 Method: pairwise confusability judge, binary framing, pre-registered ground truth (24 pairs
    from already-collected behavioral data).
6.3 Binary result: precision 0.167 / recall 1.00 — fails the pre-committed bar; 24/24 pairs
    flagged (near-constant-YES failure mode).
6.4 GG-ratified graded-confidence retry: identical confusion matrix under a materially
    different question format — rules out a framing artifact.
6.5 Conclusion: pairwise judging (binary or graded) with this frozen judge is not a usable
    per-pair confusability signal. Robust negative, hard stop per pre-registration.

### 7. Discussion
7.1 Synthesis across EXP-4/EXP-1/EXP-3: the regime is narrow (4), rare (5), and not cheaply
    locatable when present (6) — description-tooling investment is at minimum over-claimed.
7.2 Practical implications for MCP server authors / tool-catalog builders.
7.3 What would change the picture: a larger or non-Python-verified EXP-1 sample; a true
    frontier-model FRONTIER-T18 run; a non-judge-based localizer signal.

### 8. Threats to Validity / Limitations
Pointer section — full content lives in `docs/paper/threats_to_validity.md`; this section in
the paper is the prose rendering of that list. Subsections mirror that file's structure
(sampling/generalizability, agent/model scope, measurement/judge validity, asymmetry and
stability, reproducibility gaps).

### 9. Reproducibility Artifact
9.1 One-command reproduction claim: exact server set + hashes, model strings/versions, seeds,
    frozen protocol.
9.2 Governance: condition-#1 gating, DRAFT-PR-only merge policy.
9.3 FRONTIER-T18 data/code split: the result data is committed and hash-verified on this branch
    (`evals/fixtures/frontier_t18_step2_*.json`); the harness code that produced it still lives
    only in unmerged PR #50 — state this distinction plainly (see `evidence_table.md` §1.3).

### 10. Conclusion
One paragraph restating the three results and the field-level takeaway, framing-dependent in
tone only (A: "here is the boundary we found"; B: "here is what didn't hold up").

### Appendix
A.1 Full cross-experiment regime table (from `docs/research/exp4_regime_map.md`).
A.2 Frozen judge/generator prompts (Guard-B, pairwise/graded confusability).
A.3 Fixture hash manifest.
A.4 Per-server EXP-1 table (the 10-server frame with tier, family, arm results).
