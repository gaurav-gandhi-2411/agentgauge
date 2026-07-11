# EXP-3 — Pairwise Confusability Localizer: Pre-Registration

**Branch:** `claude/exp3-localizer` · **Committed:** 2026-07-04 · **Status:** PRE-REGISTERED, before any judge run.

This document is committed before any localizer judge call is made. Per the frozen
protocol (`docs/research/frozen_protocol.md`), the ground-truth pair list, labels,
judge prompt, trial/seed scheme, and the interpretation thresholds below are fixed
at commit time and must not be edited after results are collected.

**Condition #1 notice:** this experiment builds a new judge-touching mechanism (the
pairwise confusability judge). Per `spec.md` / `frozen_protocol.md` governance, this
is a DRAFT PR, escalated to the author before merge, with a held-out re-validation split
called out explicitly below.

---

## 1. Motivation (already-banked negative this experiment answers)

Non-Regime 4 (`docs/research/exp4_regime_map.md`) established that the existing
single-score `discoverability` judge cannot localize which tool pairs in a catalog
are behaviorally confusable — it returns one DISTINGUISH number for the whole
catalog. On RW1 (GitHub) and RW2 (AWS IAM), this produced a flat ~70/100 and
~68.7/100 score respectively, and the *heuristic* sub-score flagged the wrong pairs
(verb-antonym name collisions, not the cross-principal-type / scope-variant pairs
that actually matter structurally). Neither the judge nor the heuristic identifies
*which* pair is the problem — that is the structural limit EXP-3 is built to fix.

**Baseline for comparison (already banked, not re-run):** single-score discoverability
localizes 0/24 pairs below (it cannot address individual pairs by construction) —
recall = 0/4 = 0%, precision undefined (no positive predictions). This is the number
the pairwise localizer must beat to be a positive methodological contribution.

---

## 2. Method

**Pairwise confusability judge.** For each candidate tool pair (A, B), one judge call:

```
You are evaluating whether two MCP tool descriptions could cause an AI agent to
select the wrong tool for a task.

Tool A: {name_a}
Description: {desc_a}

Tool B: {name_b}
Description: {desc_b}

Question: Given a task that should call Tool A, could an agent plausibly select
Tool B instead based on these two descriptions? Also consider the reverse: given a
task for Tool B, could an agent plausibly select Tool A? Consider both name
similarity AND described functionality/behavior overlap.

Answer with exactly one line:
CONFUSABLE: YES
or
CONFUSABLE: NO
```

- **Judge model:** `llama3.1:8b` (frozen, per `frozen_protocol.py`).
- **Trials per pair:** 3, seed = `JUDGE_SEED + trial_idx` (42, 43, 44) — the
  established per-trial seed convention (`scorer.py`, `fixer.py`); a single fixed
  seed across nominal "trials" was the exact bug caught and fixed in EXP-1
  (STATUS.md, "Methodological note"). Not repeating that mistake here.
- **Aggregation:** majority vote (≥2/3 `YES`) → predicted `CONFUSABLE`; else
  predicted `NOT-CONFUSABLE`.
- **Parse handling:** response parsed via `CONFUSABLE\s*:?\s*(YES|NO)`
  (case-insensitive), falling back to the first bare `YES`/`NO` token. A trial that
  matches neither is `PARSE-FAILED` and reported separately (not silently dropped,
  not counted toward the majority-vote denominator as a NO).
- **Output:** a confusability matrix (one row per candidate pair) with the raw
  per-trial votes, the aggregated verdict, and parse-failed counts — the localized
  output the single score cannot produce.

**Scope of what this experiment validates:** the judging step only — *given* a
candidate pair, does the judge correctly classify it as confusable/not? This
experiment does **not** validate an automatic candidate-pair *generation*
mechanism (e.g., which pairs to even consider from a full catalog). The 24 pairs
below are curated directly from already-collected behavioral data, including pairs
that cross mechanical-family boundaries (see Section 3) that a same-prefix-family
generator would not have proposed in the first place. This is a real, pre-declared
scope limit on the claim, not a result to be discovered later.

---

## 3. Ground truth (behavioral, all already-collected, no new agent runs)

Source: EXP-1's real per-trial `raw_log_a` records (`evals/fixtures/exp1_trial_*.json`)
for 6 of the 7 fresh-scored EXP-1 servers (`AminForou-mcp-gsc`,
`datalayer-jupyter-mcp-server`, `mrexodia-ida-pro-mcp`,
`stefanoamorelli-sec-edgar-mcp`, `stickerdaniel-linkedin-mcp-server`,
`lucasastorian-llmwiki`) plus the RW1/RW2 validation anchors
(`scripts/exp1_validate_anchors.py` `_RW1_TESTED_FAMILIES` /
`_RW2_TESTED_FAMILIES`, both 100%-accuracy, already-published in
`docs/research/exp4_regime_map.md`). `taylorwilsdon-google_workspace_mcp` is
excluded from ground truth: its 0% Arm-A result is catalog-overwhelm
(malformed/hedged output under a 116-tool listing), not confident wrong-tool
selection — using it would mislabel noise as a confusability signal (STATUS.md,
EXP-1 section).

A pair is `CONFUSED` iff at least one real trial shows the agent selecting one
tool of the pair when the other was gold (`SELECTED-WRONG`, not
`ABSTAINED-OR-HEDGED`). A pair is `NOT_CONFUSED` iff both tools were tested with
gold-labeled contested tasks and zero cross-selection was observed across all
trials.

**Class balance note:** 4 CONFUSED / 20 NOT-CONFUSED. This mirrors EXP-1's own
headline (0/9 servers in-regime under the strict two-condition regime test) —
real behavioral confusion is rare in this sample. Precision/recall, not raw
accuracy, is the pre-registered metric for exactly this reason (a trivial
always-predict-NO baseline would score 83% accuracy but 0% recall).

**Cross-family note:** pairs #1, #3, #6 below cross mechanical prefix-family
boundaries (the confused tool was not in the same name-prefix cluster as the
gold tool per `exp1_family_candidates.json`). They are included because the
ground truth demands it — a family-scoped candidate generator would structurally
miss these, which is exactly the kind of limitation this experiment is designed
to surface honestly, not hide.

**Regime-classification note:** #5/#6 (`mrexodia-ida-pro-mcp`) come from a
server whose family was `aborted` under EXP-1's regime test (Arm A = 90% ≥ the
85% headroom ceiling) — i.e., `xrefs_family` is OUT-OF-REGIME at the family
level. The underlying trial-level fact (the agent selected the wrong tool on
2/40 trials) is still a real, observed behavioral event, and is used here as
pair-level ground truth for the localizer — a different question from EXP-1's
family-level regime verdict. Not a contradiction of EXP-1's finding.

| # | Server | Tool A | Tool B | Label | Evidence |
|---|--------|--------|--------|-------|----------|
| 1 | AminForou-mcp-gsc | delete_sitemap | manage_sitemaps | **CONFUSED** | gsc_2: 5/5 trials wrong (selected manage_sitemaps, gold delete_sitemap). Cross-family (manage_sitemaps not in delete_family). Real functional overlap: manage_sitemaps has a delete action. |
| 2 | AminForou-mcp-gsc | delete_site | delete_sitemap | NOT_CONFUSED | gsc_1+gsc_3 (delete_site, 10/10 correct), gsc_4 (delete_sitemap, 5/5 correct); 0/20 cross-selection. |
| 3 | datalayer-jupyter-mcp-server | read_notebook | list_notebooks | **CONFUSED** | jupyter_1 (1/5) + jupyter_3 (5/5) wrong: selected list_notebooks, gold read_notebook. Cross-family (list_notebooks in list_family, not read_family). |
| 4 | datalayer-jupyter-mcp-server | read_notebook | read_cell | NOT_CONFUSED | jupyter_2+jupyter_4 (read_cell, 10/10 correct); zero read_notebook/read_cell cross-selection observed. |
| 5 | mrexodia-ida-pro-mcp | xrefs_to | xrefs_to_field | **CONFUSED** | ida_3 trial 0: gold=xrefs_to, selected=xrefs_to_field (1/5 wrong). Low rate but a real observed trial. Family aborted at server level (90%≥85% ceiling) — see regime-classification note above. |
| 6 | mrexodia-ida-pro-mcp | xrefs_to_field | entity_query | **CONFUSED** | ida_4 trial 0: gold=xrefs_to_field, selected=entity_query (1/5 wrong). Cross-family (entity_query not clustered). |
| 7 | stefanoamorelli-sec-edgar-mcp | discover_xbrl_concepts | discover_company_metrics | NOT_CONFUSED | secedgar_1–4, 20/20 correct, 0 cross-selection. |
| 8 | stickerdaniel-linkedin-mcp-server | search_companies | search_jobs | NOT_CONFUSED | 100% both tasks, 0 cross-selection. |
| 9 | stickerdaniel-linkedin-mcp-server | search_companies | search_people | NOT_CONFUSED | as above. |
| 10 | stickerdaniel-linkedin-mcp-server | search_companies | search_conversations | NOT_CONFUSED | as above. |
| 11 | stickerdaniel-linkedin-mcp-server | search_jobs | search_people | NOT_CONFUSED | as above. |
| 12 | stickerdaniel-linkedin-mcp-server | search_jobs | search_conversations | NOT_CONFUSED | as above. |
| 13 | stickerdaniel-linkedin-mcp-server | search_people | search_conversations | NOT_CONFUSED | as above. |
| 14 | lucasastorian-llmwiki | create_knowledge_base | create | NOT_CONFUSED | 20/20 correct, 0 cross-selection, despite the generic name "create". |
| 15 | github-mcp (RW1 anchor) | get_pull_request_diff | get_pull_request_files | NOT_CONFUSED | RW1: 21/21 (100%). **Adversarial**: the old Levenshtein heuristic flagged this exact pair at 85.0 collision score — a false positive by the prior method. |
| 16 | github-mcp (RW1 anchor) | get_pull_request | get_pull_request_reviews | NOT_CONFUSED | RW1: 100%. |
| 17 | github-mcp (RW1 anchor) | search_repositories | search_code | NOT_CONFUSED | RW1: 100%. |
| 18 | github-mcp (RW1 anchor) | list_pull_requests | list_issues | NOT_CONFUSED | RW1: 100%. |
| 19 | github-mcp (RW1 anchor) | get_repository | list_repositories | NOT_CONFUSED | RW1: 100%. |
| 20 | aws-iam-mcp (RW2 anchor) | attach_user_policy | detach_user_policy | NOT_CONFUSED | RW2: 100%. **Adversarial**: old heuristic flagged this verb-antonym pair as a collision. |
| 21 | aws-iam-mcp (RW2 anchor) | attach_user_policy | attach_group_policy | NOT_CONFUSED | RW2: 100%. This is RW2's real "Family A" cross-principal-type contested pair — missed by the old heuristic entirely, resolved 100% behaviorally by gemma2:9b from task context. |
| 22 | aws-iam-mcp (RW2 anchor) | put_user_policy | get_user_policy | NOT_CONFUSED | RW2: 100%. **Adversarial**: 2nd old-heuristic-flagged verb-antonym pair. |
| 23 | aws-iam-mcp (RW2 anchor) | list_user_policies | list_role_policies | NOT_CONFUSED | RW2: 100%. RW2's real "Family C" scope-variant pair, missed by the heuristic. |
| 24 | aws-iam-mcp (RW2 anchor) | delete_user_policy | delete_role_policy | NOT_CONFUSED | RW2: 100%. RW2's destructive contested pair. |

Machine-readable form (labels, docstrings, evidence) committed at
`evals/fixtures/exp3_ground_truth.json`. Fixture hash to be recorded at run time
per the frozen protocol appendix.

---

## 4. Metrics (pre-registered formulas)

- TP = predicted `CONFUSABLE` ∩ labeled `CONFUSED`
- FP = predicted `CONFUSABLE` ∩ labeled `NOT_CONFUSED`
- FN = predicted `NOT-CONFUSABLE` ∩ labeled `CONFUSED`
- TN = predicted `NOT-CONFUSABLE` ∩ labeled `NOT_CONFUSED`
- Precision = TP / (TP + FP); Recall = TP / (TP + FN)
- Baseline (single-score discoverability, already banked): 0 pairs flagged →
  recall = 0/4 = 0%, precision undefined.

## 5. Pre-committed interpretation

- **Real positive method:** precision ≥ 0.50 AND recall ≥ 0.50 (localizer
  correctly identifies at least half the real confusions, and at least half its
  flags are real). Report as EXP-3's positive contribution.
- **Honest negative:** below that bar on either axis. Report as-is — "even
  pairwise judging does not reliably predict behavioral confusion" is a clean,
  reportable result per the frozen protocol's null-first-class rule. Not tuned
  after the fact; this threshold is fixed now, before any judge call.
- Separately and always reported regardless of the above: full confusion matrix
  (TP/FP/FN/TN pairs named explicitly, not just counts), parse-failed count,
  and per-pair vote breakdown (3/3, 2/3, 1/3, 0/3) — a pair sitting on a 2-1
  split is a materially weaker signal than 3-0, and that nuance must not be
  collapsed into the binary verdict alone.

## 7. Graded-confidence retry (pre-registered 2026-07-04, before any judge call)

**Ratified:** the binary result (Section 3's method, run 2026-07-04 — see `STATUS.md`
EXP-3 section and `evals/fixtures/exp3_localizer_result.json`: precision 0.167, recall 1.00,
24/24 pairs verdicted CONFUSABLE) is the degenerate yes-sayer failure — an unanchored binary
"could these be confused?" question has no incentive to
discriminate, so the judge defaults to a uniform `YES`. This is the same root cause as the
flat-70 single-score judge (Non-Regime 4): unanchored judgments default to a uniform answer.
This is **one pre-registered retry, time-boxed** — not tuning to a positive, since the method,
threshold, and ground truth are fixed here, before this result is known, and this is the
**last** variant tried regardless of outcome.

**Method chosen: graded confidence (not ranking).** A forced pairwise/listwise ranking was the
other option considered; graded confidence is chosen because it keeps each pair's judgment
independent (matching the ground truth's pair-independent structure — ranking would require
presenting multiple pairs to the judge in one call, a materially different and more complex
call structure), and it mirrors this codebase's existing `_judge_discoverability` /
`_parse_distinguish_score` pattern (`scorer.py`), which is already anchored with a 0–10 scale
and scoring-guide bands.

**Prompt (frozen before any call):**

```
You are evaluating whether two MCP tool descriptions could cause an AI agent to select the
wrong tool for a task.

Tool A: {name_a}
Description: {desc_a}

Tool B: {name_b}
Description: {desc_b}

On a scale of 0-10, how likely is an AI agent to confuse these two tools when selecting which
one to call for a task?

Scoring guide:
- 0-2: Completely distinct -- no reasonable task would create ambiguity between them
- 3-4: Minor surface similarity (e.g. shared verb or domain) but functionally clearly distinct
- 5-6: Real overlap -- a plausible task could go either way
- 7-8: Strong overlap -- significant chance of agent confusion
- 9-10: Near-identical in function -- an agent would struggle to tell them apart

Answer with exactly one line:
CONFUSABILITY: <number 0-10>
```

- **Judge model:** `llama3.1:8b` (unchanged, frozen).
- **Trials per pair:** 3, seed = `JUDGE_SEED + trial_idx` (42, 43, 44) — same convention as the
  binary run.
- **Parsing:** `CONFUSABILITY\s*:?\s*(\d+(?:\.\d+)?)` (case-insensitive) as the labeled strategy;
  fallback to the last bare number in the response (mirrors `_parse_distinguish_score`'s
  strategy order in `scorer.py`); a response with no digit at all is `PARSE-FAILED` for that
  trial, excluded from the mean (not coerced to 0), consistent with the binary run's
  parse-failed handling.
- **Aggregation:** mean of the non-parse-failed trial scores. If all 3 trials parse-failed, the
  pair's verdict is `UNDETERMINED` (same convention as the binary run).
- **Threshold (pre-registered, midpoint of the 0–10 scale, chosen for being the least arbitrary
  possible cut point — not chosen by looking at any score distribution):** mean score **>= 5.0**
  => predicted `CONFUSABLE`; else `NOT-CONFUSABLE`.
- **Ground truth, metric formulas, and interpretation bar: unchanged** — same 24-pair fixture
  (`evals/fixtures/exp3_ground_truth.json`), same precision/recall formulas (Section 4), same
  precision ≥ 0.50 AND recall ≥ 0.50 bar (Section 5).

**Pre-committed interpretation (fixed now, before this result is known):**
- Clears the bar → the graded localizer **is** EXP-3's positive method: it predicts behavioral
  confusion. Report as the paper's positive contribution, with the binary attempt reported
  alongside as the (failed) first framing tried.
- Fails the bar → **the robust negative**: pairwise judging fails under both a binary and a
  graded framing — a fundamental limit of asking this frozen judge to localize confusability
  this way, not an artifact of the binary phrasing. This is the final EXP-3 result either way.

**Hard stop:** this is the only retry. No third variant will be proposed regardless of outcome.

## 8. Governance

- Condition #1: this PR is DRAFT and escalated to the author before merge.
- `generator != judge != agent`: no generator or agent call is made in this
  experiment; only the judge is invoked. No conflict.
- No assistant-vendor credentials are set or used.
- No fixture edits after this commit. If the implementation script's counts
  don't match, that is reported as a discrepancy, not fixed by editing the
  ground truth after the fact.
