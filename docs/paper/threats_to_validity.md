# Threats to Validity / Limitations — Compiled List

**Status:** PREP — compiled from the honesty spine (`paper_framing_options.md`), the frozen
protocol's governance section (`docs/research/frozen_protocol.md`), and gaps found while
sourcing the evidence table (`docs/paper/evidence_table.md`). Applies under either framing.
Every item traces to a specific finding already in the repo — nothing here is speculative.

---

## 0. THE FALSE-NEGATIVE ASYMMETRY (read this one first — elevated per adversarial self-audit)

**This is the single most important threat to this paper's null results, and it must be the
most visible item in this document, not bullet 2 of 6 under "measurement/judge validity."**

Section 5.4/8.3.1 of `paper.md` reports two false positives from a seed-configuration bug,
caught and reversed *because* they were surprising enough to trigger a recheck. A bug that
instead silently **suppressed** a real in-regime signal — turning a true positive into a false
null — would produce a result indistinguishable from a correctly-measured null. Nothing about a
null prompts the same "that's surprising, recheck it" response that caught the two false
positives. **This means EXP-1's 0-of-9 headline and EXP-3's localizer-fails headline both carry
a category of risk this paper's own demonstrated error-detection does not bound**: the pipeline
has shown it catches false positives; it has not shown, and structurally cannot easily show, that
it catches false negatives. State this before any other limitation, in the paper's Abstract or
Limitations summary, not only in a body-section subordinate clause.

---

## 1. Sampling / generalizability

- **N=10, Python-only, public-GitHub pilot (EXP-1).** The strength is *convergence* across
  four independent signals — EXP-1's own null, the RW1/RW2 anchors, P2-A's account_query harm,
  and the doc-density-rarity pattern across tiers — not N=10 in isolation. Never write "the
  regime doesn't occur"; write "rare in sampled public servers; the under-documented internal
  segment is unmeasurable from public data." (`STATUS.md` EXP-1 section, commit `0da8199`.)
- **Non-Python extraction was dropped, not merely deferred.** 11 non-Python servers were
  excluded after a systematic audit found the generic regex fallback pulls in template
  literals, parameter names, and unrelated example data — a capability limit of blind
  text-proximity matching, not a fixable bug. State this as a scope boundary of the *method*,
  not a data-availability inconvenience.
- **Tercile labels (well_documented / thin / near_empty) are RELATIVE ranks within the sampled
  pool, not absolute doc-quality bands.** Do not present a tier label as if it generalizes
  outside this specific N=10/N=23 frame.
- **Public-servers-skew-documented lower-bound caveat.** The prevalence number is explicitly a
  lower bound on how common the regime is among under-documented internal/custom servers,
  which cannot be sampled from public data. State this once, prominently, near the EXP-1
  headline — not buried in a footnote.

## 2. Agent / model scope

- **One default agent (gemma2:9b) for the whole regime map, T18, Q-series, RW1/RW2, and P2-A.**
  EXP-2 (the controlled capability ladder that would test this directly) is DROPPED — ratified
  (`spec.md` EXP-2 section, `0c78f49`) — because the underlying regime this paper's preparation
  could verify is already rare; a ladder over an uncommon regime has limited external relevance.
  State the drop and its justification explicitly; do not silently omit EXP-2 from the paper's
  scope statement.
- **FRONTIER-T18 (Llama-3.3-70B) is ONE model, ONE data point, and NOT apples-to-apples with
  the gemma2:9b harness** (different classifier host, different harness — see
  `docs/research/frozen_protocol.md` §Cross-Experiment Comparisons). It shows the effect
  *survives* at a stronger open-weight tier; it does not show a *trend*, and it is not a
  Claude/GPT-class frontier result. The frontier (proprietary-model) question remains open.
- **Reproducibility gap on FRONTIER-T18 itself — RESOLVED.** The commit that recorded the
  +40.8pp result in prose (`5269645`) was not reachable from this paper-writing branch's history
  (nor from `main`) — it lived only on the unmerged sibling branch `claude/frontier-t18`
  (open DRAFT PR #50), and the writeup was gitignored everywhere. The raw per-task and
  per-call result files survived on local disk; both were independently re-derived (counting
  `SELECTED-CORRECT` directly from the 240 raw per-call records reproduces 71/120 and 120/120
  exactly) and committed as hashed fixtures: `evals/fixtures/frontier_t18_step2_result.json`
  (sha256[:12] `3ca4a25dbd25`) and `evals/fixtures/frontier_t18_step2_raw_calls.json`
  (sha256[:12] `93fb0d77262d`), plus `docs/research/frontier_t18_result.md` for the caveats
  writeup. **Residual scope note:** the harness code itself (`agentgauge/frontier.py`,
  `scripts/run_frontier_t18.py`) still lives only in unmerged PR #50 — a from-scratch re-run
  requires merging that PR first, even though the reported number is now independently
  verifiable from committed data. State this distinction in §9 (Reproducibility Artifact).
  Full detail: `docs/paper/evidence_table.md` §1.3.

## 3. Measurement / judge validity

- **Two seed-bug false positives caught and reversed before reporting**
  (`mrexodia-ida-pro-mcp`, `datalayer-jupyter-mcp-server` — see `STATUS.md` EXP-1
  "Methodological note"). Report this as a credibility asset per the honesty spine: it shows
  the pipeline catches its own artifacts, not that the pipeline is unreliable. **The
  false-negative asymmetry this implies is covered in §0 above, standalone — do not re-bury it
  here as a subordinate clause.**
- **The single-score `discoverability` judge structurally cannot localize** (Non-Regime 4) —
  this is a known, reported limitation of the *product*, and it is the motivating fact for
  EXP-3, not a threat to EXP-3's own validity.
- **EXP-3's negative is robust, not a single-framing artifact.** Binary yes/no and graded 0–10
  confidence framings produced the *same* confusion matrix (precision 0.167, recall 1.00) via
  two different degeneracy modes (uniform-YES vs anchoring at the scale midpoint). Frame this
  as "LLM-judge confusability assessment doesn't predict agent behavior [with this frozen
  judge, on this fixture]," not "our method failed" — and do not imply a third variant was
  tried or would change the conclusion; the pre-registration commits to a hard stop.
- **EXP-3 validates the judging step only, not candidate-pair generation.** 2 of the 4 real
  confusions in the ground truth cross mechanical prefix-family boundaries; a family-scoped
  candidate generator would not have proposed them as candidates at all, independent of the
  judging result. State this as a pre-declared scope limit, not a discovered-after-the-fact
  caveat.
- **Trial-count deviation across experiments.** The frozen protocol specifies 5 trials/arm as
  default; FRONTIER-T18 and EXP-3's judge calls use 3 trials/pair — each independently
  pre-registered with its own justification (cost/rate-limit for FRONTIER-T18's API calls;
  matching the existing `_judge_discoverability` convention for EXP-3). State both deviations
  explicitly in Methods rather than presenting "5 trials" as a blanket constant.

## 4. Harm / asymmetric risk

- **Blanket description-fixing is not universally safe.** P2-A's account_query family shows
  −20pp harm under BOTH Guard-B and Oracle descriptions, reproducing at the same magnitude —
  not noise. This is a genuine risk finding, not a hedge: any practitioner-facing claim from
  this paper must carry the harm case alongside the recovery cases, not just the positive
  regime.
- **Do-no-harm testing (Q6) covers only cases where honest descriptions remain semantically
  distinct.** Total description-collapse to identical phrasing for sibling tools is explicitly
  untested (`STATUS.md` Q6 "MECHANISM" note) — the safe-to-blanket claim is conditioned on this,
  not unconditional.

## 5. Scope / framing discipline (apply regardless of A vs B)

- Never write "the regime doesn't occur" — always "rare in sampled public servers; the
  under-documented internal segment is unmeasurable from public data."
- Never present the FRONTIER-T18 +40.8pp and T18 gemma +34.5pp figures as directly comparable
  or as evidence of a capability trend — different harness, explicitly flagged in
  `docs/research/frozen_protocol.md`.
- Every number drafted into paper prose must trace to a row in `docs/paper/evidence_table.md`;
  if a claim doesn't have a row, it doesn't go in the paper without first adding and sourcing
  that row.
