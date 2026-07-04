# Paper Evidence Table — Sourced Numbers

**Status:** PREP — framing-independent. Compiled while awaiting GG's Framing A vs B decision
(`paper_framing_options.md`). Every number below is traced to a specific committed file and,
where meaningful, a commit hash. **Ancestry column** states whether that commit is reachable
from this branch's HEAD (`claude/exp3-localizer`, currently `8fadbe0`) — i.e. whether a fresh
clone of this branch alone can reproduce the citation. This matters because the research
program is a stack of unmerged DRAFT branches, not a single merged history (see gap flagged
in §FRONTIER-T18 below).

Do not draft prose against any number in this table without re-checking it here first — this
table is the single point of truth for "did we source this."

---

## 1. EXP-4 Regime Map — consolidation, no new runs

### 1.1 Regime 1 — Confusable-at-scale (T18)

| Metric | Value | Source | Commit | Ancestor of HEAD? |
|---|---|---|---|---|
| Arm A (empty desc.) parse-success accuracy, contested | 62.9% (110/175) | `docs/research/exp4_regime_map.md` §Regime 1; `STATUS.md` T18 section | `fa766c9` (PR #41) | ✓ |
| Arm B (oracle) parse-success accuracy, contested | 97.4% (190/195) | same | same | ✓ |
| Discrimination effect | **+34.5pp** | same | same | ✓ |
| Sign test | n+=16, n−=0, ties=24, p<0.0001 | same | same | ✓ |
| Parse-failed A → B (separate mechanism) | 25/200 (12.5%) → 5/200 (2.5%) | same | same | ✓ |
| Conditions required | ≥60 tools / ≥10 families; real within-family axis; targeted descriptions | same | same | ✓ |
| Fixture | `evals/fixtures/t18_catalog.py` | — | `fa766c9` | ✓ |

### 1.2 Regime 2 — Under-documented source with docstrings (Q3/Q5/Q6 Guard-B)

| Condition | Recovery (n=6 structural) | p | No-fabrication | Source commit | Ancestor? |
|---|---|---|---|---|---|
| Q3 F-DOC (whole-file, docstrings) | 83.3% (5/6) | 0.0625 (marginal) | PASS | `03e72b1` (PR #44) | ✓ |
| Q3 F-BODY (whole-file, no docstrings) | 83.3% (invalidated by fabrication) | — | **FAIL** (`_db` cross-tool misattribution) | `03e72b1` | ✓ |
| Q4-DOC-scoped | 100% (6/6) | 0.0313 | **FAIL** (docstring-body gap) | `81ebee9` (PR #45) | ✓ |
| Q4-BODY-scoped | 100% (6/6) | 0.0313 | PASS | `81ebee9` | ✓ |
| Q5-guarded | 100% (6/6) | 0.0313 | PASS | `40857c7` (PR #46) | ✓ |
| Q6-guarded (23-tool blanket) | 100% (6/6) | 0.0312 | PASS, **0/11 regressions** (do-no-harm) | `32a099c` (PR #47) | ✓ |
| Interface-only ceiling (no source) | 12.5% recovery, both per-tool (Q2a) and catalog-aware (Q2b) generation | p=0.50 (n.s.) both | — | `8e26dd7` (Q2a, PR #42), `f01fe94` (Q2b, PR #43) | ✓ |

Source docs: `docs/research/exp4_regime_map.md` §Regime 2, §Non-Regime 5; `STATUS.md` Q2a/Q2b/Q3/Q4/Q5/Q6 sections.

### 1.3 Regime 3 — Strong-agent survival (FRONTIER-T18, Llama-3.3-70B) — ⚠️ SOURCING GAP, see below

| Metric | Value | Source |
|---|---|---|
| Arm A accuracy | 59.2% (71/120) | `docs/research/exp4_regime_map.md` §Regime 3 |
| Arm B (oracle) accuracy | 100.0% (120/120) | same |
| Effect | **+40.8pp** | same |
| Sign test | n+=19, n−=0, ties=21, p<0.0001; stable-set (excl. 5 Arm-A flippers) n+=14, n−=0, p<0.001 | same |
| Parse-failed | 0/200 both arms | same |

**⚠️ FLAG — not independently reproducible from this branch.** `docs/research/exp4_regime_map.md`
(committed on this branch's ancestry, commit `1493791`) cites this result as an already-banked
source experiment, but:

- The commit that actually recorded these numbers (`5269645`, `fix(frontier-t18): ... record
  STEP 2 durability result`, which edited `STATUS.md` with the full Arm A/B breakdown) lives
  on branch `claude/frontier-t18` — **verified NOT an ancestor of `HEAD`** (`git merge-base
  --is-ancestor 5269645 HEAD` → false), and **NOT an ancestor of `main`** either. This branch's
  stack (`claude/p2a-internal-proxy` → `claude/frozen-protocol-exp4` → `claude/exp1-prevalence`
  → `claude/exp3-localizer`) forked from `main` at `8cb679b` (RW2, PR #49), **before**
  `claude/frontier-t18` existed. The two branch lines never merged.
- The fuller writeup with caveats (`reports/frontier_t18_pr_body.md`) is **not git-tracked on
  any branch, including `claude/frontier-t18` itself** — `reports/` was added to `.gitignore`
  in the same commit (`5269645`) that produced this report. It exists only as a local file.
- No raw per-trial result JSON is committed anywhere for this experiment. The ad-hoc analysis
  script `scripts/analyze_frontier_t18.py` (currently untracked in this session's working tree
  — see git status) writes to `reports/frontier_t18_step2_groq.json` / `frontier_t18_ckpt.json`,
  both gitignored.

**Net effect:** the paper's third "helps" regime and its second-most novel claim (effect
survives at 70B) rests entirely on prose in a `STATUS.md` revision that a clone of the current
paper-writing branch cannot check out. **Before this number is cited in the paper, either (a)
merge or cherry-pick `claude/frontier-t18`'s commits (`9cd97ca`..`0a370de`) into this branch's
lineage so `git log` on the paper branch actually contains the result, or (b) commit a
fixture-hashed result JSON for it now.** Recommend escalating this as a pre-submission task,
not silently drafting around it. Not a reason to doubt the number (the underlying run is real
and its narrative is internally consistent with the T18 result it replicates) — purely a repo-
hygiene / reproducibility-artifact gap.

---

## 2. EXP-1 — Server-population prevalence (headline)

| Metric | Value | Source | Commit | Ancestor? |
|---|---|---|---|---|
| Servers IN-REGIME | **0/9 scored** (7 fresh + 2 anchors) | `STATUS.md` EXP-1 section | `0da8199` | ✓ |
| Frame | N=10, Python-only (non-Python regex extraction dropped as unreliable, v5) | `STATUS.md`, `spec.md` EXP-1/EXP-2 | `538affe` (frame ratify), `0da8199` | ✓ |
| Per-tier (fresh only) | well_documented 0/1 testable; thin 0/3; near_empty 0/3 | `STATUS.md` EXP-1 section | `0da8199` | ✓ |
| No testable family | 3/10 servers (Dataojitori-nocturne_memory, blazickjp-arxiv-mcp-server, LycheeMem-LycheeMem) | same | same | ✓ |
| Seed-bug false positives caught + reversed | 2 (`mrexodia-ida-pro-mcp` +50pp→90% no-headroom; `datalayer-jupyter-mcp-server` +25pp→−15pp HARM) | `STATUS.md` EXP-1 "Methodological note" | `0da8199` | ✓ |
| Fixtures | `evals/fixtures/exp1_*.json` (server frame, doc-density scores, trial batches, anchor validation) | — | `0da8199` and frame-history commits | ✓ |

**Precision note for drafting:** `paper_framing_options.md` (GG's own framing doc, uncommitted)
paraphrases this as "0/10 Python public servers in-regime" — the precise figure is **0/9
scored** (10 servers total, 3 had no testable confusable family and were never scored either
way). Use "0/9 scored servers, 0/10 total including 3 with no testable family" in the paper,
not the shorthand "0/10."

**RW1/RW2 anchors cited within EXP-1's N=10+2:**

| Server | Result | Source | Commit | Ancestor? |
|---|---|---|---|---|
| github-mcp (RW1) | 100% (21/21), 0 headroom, OUT-OF-REGIME | `STATUS.md` RW1 section | `4207615` (PR #48) | ✓ |
| aws-iam-mcp (RW2) | 100% (29/29 incl. 12 contested), 0 headroom, OUT-OF-REGIME | `STATUS.md` RW2 section | `8cb679b` (PR #49) | ✓ (this is the branch fork point) |

---

## 3. EXP-3 — Confusability localizer (positive-method attempt, closed as robust negative)

| Metric | Binary framing | Graded framing | Source | Commit | Ancestor? |
|---|---|---|---|---|---|
| Confusion matrix | TP=4, FP=20, FN=0, TN=0 | TP=4, FP=20, FN=0, TN=0 (identical) | `STATUS.md` EXP-3; `docs/research/exp4_regime_map.md` §Non-Regime 4 | `a4d7f1b` (binary), `8fadbe0` (graded) | ✓ ✓ |
| Precision | 0.167 (4/24) | 0.167 (4/24) | same | same | ✓ |
| Recall | 1.00 (4/4) | 1.00 (4/4) | same | same | ✓ |
| Verdict rate | 24/24 pairs CONFUSABLE | 24/24 pairs CONFUSABLE, mean scores banded 5.00–5.67 | same | same | ✓ |
| Pre-committed bar | precision ≥0.50 AND recall ≥0.50 → both framings **FAIL** the bar | | `docs/research/exp3_pre_registration.md` §5, §7 | `603bfb2`, `4bcaa37` | ✓ |
| Ground truth | 24 pairs (4 CONFUSED / 20 NOT_CONFUSED), drawn from EXP-1 raw trials + RW1/RW2 anchors | | `evals/fixtures/exp3_ground_truth.json` | `603bfb2` | ✓ |
| Result fixtures | — | — | `evals/fixtures/exp3_localizer_result.json` (binary, verified directly — TP/FP/FN/TN and per-pair mean scores match STATUS.md prose), `evals/fixtures/exp3_localizer_graded_result.json` (graded, verified directly — spot-checked pairs 1–4 against STATUS.md text) | `a4d7f1b`, `8fadbe0` | ✓ ✓ |
| Baseline (single-score discoverability) | 0/24 localized by construction (one number per catalog) | | `docs/research/exp3_pre_registration.md` §1 | `603bfb2` | ✓ |

---

## 4. Non-regime evidence (harm, retrieval, structural limits)

### 4.1 P2-A account_query HARM

| Arm | Accuracy | Source | Commit | Ancestor? |
|---|---|---|---|---|
| A (thin) | 100% (5/5) | `STATUS.md` P2-A section | `925b3cb` | ✓ |
| Guard-B | 80% (4/5), **−20pp** | same | same | ✓ |
| Oracle | 80% (4/5), **−20pp** | same | same | ✓ |

Aggregate P2-A (31 contested tasks, all families): A=77.4%, Guard-B=96.8%, Oracle=93.5%; sign
tests GuardB-vs-A p=0.07, Oracle-vs-A p=0.125 (both n.s. at N=31). Do-no-harm thorough set:
0/17 regressions. Source: same commit `925b3cb`.

### 4.2 F2 retrieval-readiness — CLOSED negative, all three retrievers

| Arm | BM25 MRR | TFIDF MRR | Embedding MRR (nomic-embed-text) |
|---|---|---|---|
| Thin | 0.304 | 0.317 | 0.510 |
| Guard-B | 0.225 (−0.079) | 0.204 (−0.113) | 0.286 (−0.224) |
| Oracle | 0.234 | 0.228 | 0.362 |

Source: `STATUS.md` F2 subsection; commits `146540f` (BM25/TFIDF, "NOT SUPPORTED") and `994e1cf`
(embedding, "F2 CLOSED"), both ancestors of HEAD ✓. Fixture: `evals/fixtures/p2a_f2_retrieval_spec.json`;
script `scripts/p2a_f2_retrieval.py`. Embedding R@1/MeanRank: thin 0.269/3.0, Guard-B 0.129/6.3,
Oracle 0.161/5.2 (`STATUS.md` same section).

### 4.3 Single-score discoverability score-validity gap (motivates EXP-3)

| Server | DISTINGUISH score | Overlap with real confusable families |
|---|---|---|
| github-mcp (RW1) | ~70/100 flat | 0/2 |
| aws-iam-mcp (RW2) | ~68.7/100 flat | 0/3 |

Source: `docs/research/exp4_regime_map.md` §Non-Regime 4; `STATUS.md` RW1/RW2 sections
(`4207615`, `8cb679b`). Ancestor of HEAD ✓.

---

## 5. Frozen protocol constants (methods section)

| Constant | Value | Source |
|---|---|---|
| Judge model / seed | `llama3.1:8b` / `42` | `docs/research/frozen_protocol.md` (commit `1493791`, ancestor ✓) |
| Generator model | `qwen3:8b` | same |
| Default agent | `gemma2:9b` | same |
| Trials per arm | 5 (T18/Q-series); 3 (FRONTIER-T18, EXP-3 judge) — **note the deviation for FRONTIER-T18/EXP-3 explicitly in Methods**, both pre-registered separately | same + respective pre-registrations |
| Sign test α | 0.05, two-sided unless pre-registered one-sided | same |
| Headroom ceiling | 0.85 (proceed to A/B only if Arm A < 85%) | same |
| Min contested tasks | 6 | same |
| Classifier | SELECTED-CORRECT / SELECTED-WRONG / ABSTAINED-OR-HEDGED + separate PARSE-FAILED | same |

---

## 6. Numbers flagged as NOT independently sourceable from this branch

1. **FRONTIER-T18 (+40.8pp) — see §1.3.** The only genuine gap found. Everything else in this
   table checks out against a commit reachable from `HEAD`.

No other unsourceable numbers were found. All EXP-1, EXP-3, EXP-4/T18/Q-series, RW1/RW2, P2-A,
and F2 figures trace to commits on this branch's direct ancestry path, cross-checked against
either `STATUS.md` prose or the underlying fixture JSON (spot-checked for EXP-3's binary and
graded result files).
