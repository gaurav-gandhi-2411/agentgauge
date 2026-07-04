# EXP-4 — Regime Map: Where Tool-Description Quality Changes Agent Behavior

**Status:** COMPLETE (consolidation only; no new runs)
**Date compiled:** 2026-06-22
**Source experiments:** T18, FRONTIER-T18, Q2a, Q2b, Q3, Q4, Q5, Q6, RW1, RW2, P2-A, F2

This document synthesizes all banked findings into the paper's core contribution:
a falsifiable, regime-bounded map of WHERE tool-description quality changes agent
behavior and where it does not.

---

## WHERE Description Quality HELPS

### Regime 1 — Confusable-at-scale (T18)

**Source:** T18 oracle A/B, 60-tool / 10-family confusable synthetic catalog, gemma2:9b.

| Arm | Parse-success accuracy (contested) | parse_failed |
|-----|-----------------------------------|-------------|
| A (empty descriptions) | 62.9% (110/175) | 25/200 (12.5%) |
| B (oracle, discriminating) | 97.4% (190/195) | 5/200 (2.5%) |

Effect: **+34.5pp** (sign test n+=16, n−=0, ties=24, p<0.0001).
Parse stabilization bonus: A 12.5% → B 2.5% parse_failed (separate mechanism;
contributes ~5–6pp of the aggregate +40pp delta, not part of the discrimination effect).

**Conditions required:**
- Catalog density ≥ 60 tools / ≥ 10 families — T17 (16 tools) showed no headroom;
  density is the gating variable, not description quality per se
- Real within-family semantic distinctions that CAN be encoded in descriptions
  (source medium, operation scope, permanence flag, notification channel, computation type)
- Descriptions that TARGET the within-family distinguishing dimension (not generic)

**Mechanism:** At high catalog density, tool names alone cannot disambiguate within-family
variants. Descriptions targeting the critical axis (e.g., "stores in-memory with TTL" vs
"persists to SQL row") break the tie. The effect is entirely on the 16 confusable-but-
discriminable tasks; 22/40 tasks were at ceiling in both arms (names sufficient); 2/40
were at floor in both arms (ambiguous gold label, not agent failure).

---

### Regime 2 — Under-documented source with docstrings (Q3 / Q5 / Q6 Guard-B)

**Source:** Q3–Q6 source-aware generation series, 12–23-tool fixtures, gemma2:9b.

| Condition | Recovery (6 structural contested tasks) | p | No-fabrication |
|-----------|----------------------------------------|---|----------------|
| Q3 F-DOC (whole-file, docstrings) | 83.3% (5/6) | 0.0625 (marginal) | PASS |
| Q5-guarded (scoped, Guard-B, docstrings) | 100% (6/6) | 0.0313 | PASS |
| Q6-guarded (23-tool blanket) | 100% (6/6) | 0.0312 | PASS |

Do-no-harm (Q6): 0/11 regressions on already-passing tools including 3 collision-prone pairs.

**Conditions required:**
- Server has source code **with docstrings** (body-only opens fabrication; F-BODY unsafe in Q3)
- Thin descriptions fail ≥ 1 contested task in Arm A (headroom gate passes)
- Generator uses Guard-B prompt (target-grounded; no comparative neighbor claims)

**Mechanism:** Source docstrings supply behavioral facts (return shapes, permanence flags,
storage backends) absent from the tool interface. Guard-B descriptions encode these within-
family distinctions safely. Without source (interface-only: Q2a, Q2b), recovery = 12.5%
regardless of generation strategy — an information-theoretic ceiling.

**Deployment boundary (from Q3/Q4):**
- Whole-file + docstrings: safe (vocabulary anchors prevent cross-tool misattribution)
- Scoped + docstrings only: UNSAFE (docstring-body gap opens fabrication vector in Q4)
- Scoped + Guard-B + docstrings: safe AND 100% recovering (Q5 = Q6 deployed config)
- Body-only (no docstrings): unsafe in whole-file (Q3 _db misattribution); safe but
  discards docstring signal in scoped (Q4)

---

### Regime 3 — Strong-agent survival (FRONTIER-T18, Llama-3.3-70B)

**Source:** FRONTIER-T18, T18 fixture replicated, Llama-3.3-70B via OpenRouter (3 trials × 40 tasks).

| Arm | Accuracy | parse_failed |
|-----|----------|-------------|
| A (empty descriptions) | 59.2% | 0/200 |
| B (oracle) | 100.0% | 0/200 |

Effect: **+40.8pp** (sign test n+=19, n−=0, ties=21, p<0.0001).
Stable-set (excl. 5 Arm-A flippers): n+=14, n−=0, p<0.001.

**Scope caveat:** Llama-3.3-70B is a strong open model, **not** a true frontier (Claude/GPT-class).
The effect survives at 70B scale but the frontier question is not closed. One model = one
data point. This run is **NOT** part of EXP-2's controlled ladder — different harness,
different host, not apples-to-apples with a same-family size comparison.

**Implication:** The description effect is not weak-agent-bound at 70B open scale.

---

## WHERE Description Quality DOESN'T HELP / HARMS

### Non-Regime 1 — Well-documented real servers (RW1 GitHub, RW2 AWS IAM)

**Source:** RW1 (GitHub MCP, 21-tool mirror, 5 families) and RW2 (AWS IAM, 29-tool mirror, 3 families).

| Server | Arm A accuracy | Guard-B recovers |
|--------|---------------|-----------------|
| GitHub MCP (RW1) | 100% (21/21) | nothing (headroom = 0) |
| AWS IAM (RW2) | 100% (29/29, incl. 12 contested) | nothing (headroom = 0) |

**Mechanism:** Real terse docstrings (GitHub: 1-sentence; AWS IAM: 1-sentence) are sufficient
for gemma2:9b. The agent resolves tool selection from task context alone — tool descriptions add
no incremental information. These are well-documented servers with naming that is self-disambiguating
at gemma2:9b capability.

**Implication:** The "no-headroom" non-regime defines the buyer exclusion: GitHub-class and
AWS IAM-class servers self-serve. The target buyer segment is under-documented internal/custom
servers where Arm A accuracy shows real headroom.

---

### Non-Regime 2 — Already-resolved families via name-task heuristic (P2-A account_query)

**Source:** P2-A synthetic internal-proxy, account_query_family (5 tools).

| Arm | Accuracy |
|-----|----------|
| A (thin descriptions) | 100% (5/5) |
| Guard-B | 80% (4/5) **−20pp** |
| Oracle | 80% (4/5) **−20pp** |

**Mechanism:** Thin descriptions + name-task heuristic alignment produce correct selection.
The task text uses SQL-like WHERE-clause syntax that maps heuristically to `query_accounts`
by name. Oracle descriptions ("Executes a parameterized SQL-like WHERE clause") create
disambiguation noise among the five account tools. The harm reproduces at −20pp under
BOTH Guard-B and Oracle — not noise; not arm-specific.

**Implication:** Blanket description improvement is not safe. Per-family targeting is required.
Families where thin descriptions already work via name → task heuristic alignment should be
excluded from fixing, or tested before applying the fix.

Note: This harm fires on the contested set only. The do-no-harm gate in `agentgauge fix`
guards the thorough set (already-passing) but does NOT guard against harm on a contested
family that Arm A happens to resolve correctly via heuristic. A pre-fix headroom check per
family is the needed guard.

---

### Non-Regime 3 — Retrieval-readiness / F2 (BM25, TFIDF, semantic embedding — all CLOSED)

**Source:** F2 retrieval-readiness, 93 queries across 31 contested tools × 3 queries each,
P2-A fixture, nomic-embed-text for embedding.

| Arm | BM25 MRR | TFIDF MRR | Embedding MRR |
|-----|----------|-----------|---------------|
| Thin | **0.304** | **0.317** | **0.510** |
| Guard-B | 0.225 (−0.079) | 0.204 (−0.113) | 0.286 (−0.224) |
| Oracle | 0.234 | 0.228 | 0.362 |

Guard-B harms **all 7 families** under embedding retrieval. Harm is larger in semantic
retrieval than lexical retrieval. No family improves under Guard-B in any retriever.

**Mechanism:** Compact verb-noun descriptions ("Get the order.", "Notify the customer.")
match coarse intent-level queries directly via term overlap (lexical) or semantic proximity
(embedding). Guard-B prose ("Returns order summary fields including status, total, item
count...") matches at the implementation level — the right level for within-family
discrimination but the wrong level for coarse retrieval queries.

**Key finding:** The description property that helps direct-selection disambiguation
(behavioral-axis precision) is **anti-correlated** with what retrieval rewards (compact,
intent-level vocabulary). This is non-obvious and mechanistically interesting: the fix
helps one task (selection from a full catalog) and harms another (retrieval to build
the candidate set).

**F2 CLOSED** across all three retriever types. No further retriever testing warranted
on this fixture.

---

### Non-Regime 4 — Single-score discoverability can't localize (RW1 + RW2 score-validity gap)

**Source:** RW1 (GitHub, real prefix-sharing naming), RW2 (AWS IAM, confusable policy families).

| Server | DISTINGUISH score (all families) | Overlap with known-confusable families |
|--------|----------------------------------|---------------------------------------|
| GitHub MCP (RW1) | ~70/100 flat | 0/2 (pr_read_variants, search_variants not flagged) |
| AWS IAM (RW2) | ~68.7/100 flat | 0/3 (all 3 contested families not flagged) |

The heuristic flagged wrong pairs in both cases (verb-antonym pairs, not principal-type-variant
pairs that cause actual agent confusion).

**Mechanism:** The DISTINGUISH rubric asks the judge for ONE catalog-level number. It cannot
identify WHICH tool pairs within a catalog are confusable. This is a structural limit of
single-score aggregation, not a calibration problem — no amount of rubric tuning can make
a single-number judge output identify pair-level confusability.

**Implication:** EXP-3's pairwise confusability localizer is motivated by this structural limit.
The positive method (asking "could a task for A plausibly select B?" for each pair) directly
addresses what the single-score approach cannot do.

**EXP-3 result (2026-07-04, branch `claude/exp3-localizer`, DRAFT — condition #1, escalated to
GG):** built and validated against a 24-pair pre-registered behavioral ground truth (4 CONFUSED /
20 NOT_CONFUSED, drawn from EXP-1 + RW1/RW2 raw trial data). Result: precision 0.167 / recall
1.00 — below the pre-committed real-positive-method bar. The judge verdicted **24/24 pairs
CONFUSABLE**, including all 9 sampled RW1/RW2 pairs from servers that resolved 100% behaviorally.
**This is a different failure mode from the single-score judge, not a fix for it**: single-score
localizes nothing (structural, one number per catalog); naive pairwise localizes everything (a
direct yes/no confusability question elicits yes near-uniformly). Neither, as built, is a usable
per-pair ranking signal. Full result: `evals/fixtures/exp3_localizer_result.json`,
`docs/research/exp3_pre_registration.md`, `STATUS.md` EXP-3 section.

**GG-ratified graded-confidence retry (one time-boxed attempt, pre-registered before running):**
same 24-pair ground truth, 0–10 CONFUSABILITY score per pair instead of binary yes/no, threshold
>=5.0. Result: identical confusion matrix (TP=4, FP=20, FN=0, TN=0; precision 0.167, recall
1.00) — every pair's mean score landed in a narrow 5.00–5.67 band regardless of whether it was a
real behavioral confusion or a 100%-resolved anchor pair. **Final EXP-3 result (hard stop, no
third variant):** pairwise judging fails to localize behavioral confusability under both a
binary and a graded framing with the frozen `llama3.1:8b` judge — a robust negative, not a
framing artifact. Full detail: `evals/fixtures/exp3_localizer_graded_result.json`.

---

### Non-Regime 5 — Interface-only generation (Q2a / Q2b)

**Source:** Q2a (per-tool, interface-only) and Q2b (catalog-aware, interface-only), T18 fixture.

| Generation strategy | Recovery fraction | F-vs-A sign test |
|--------------------|------------------|-----------------|
| Q2a: per-tool, interface-only | 12.5% (11.1pp / 88.9pp oracle) | p=0.5 (not significant) |
| Q2b: catalog-aware, interface-only | 12.5% (11.1pp / 88.9pp oracle) | p=0.5 (not significant) |

**Mechanism (information-theoretic):** The T18-decisive distinctions (storage backend, operation
scope, delete permanence, notification channel) live in tool **behavior** — they are absent
from tool names and identical `{query: string}` schemas. No generation strategy can recover
information that does not exist in the interface. The oracle had it only because a human who
knew the implementations supplied it directly. This result was confirmed across two independent
experiments — ruling out per-tool context gap as the explanation.

**Liability finding (Q2a):** On ≥ 2 tools, the per-tool generator produced confidently wrong
descriptions (`store_item` described as "designed for persistent storage"; `forward_record`
described as "straightforward record retrieval"). These are worse than empty descriptions
for an agent reading them.

---

## Mechanism Throughline

```
Tool description precision HELPS within-family discrimination when:
 ├── Catalog density is high enough (≥60 tools / ≥10 families)
 │     for tool names alone to be ambiguous
 ├── Source has docstrings (for safe generation; body-only is unsafe)
 └── Arm A shows real headroom (agent is not already resolving from task context)

Tool description precision is ORTHOGONAL or ANTI-CORRELATED to:
 ├── What context-rich agents need → agents resolve from task wording,
 │     not tool descriptions (RW1 100%, RW2 100%, P2-A high-stakes families 100%)
 ├── What retrieval rewards → coarse intent queries match compact verb-noun;
 │     precision prose is a semantic mismatch (F2 CLOSED, all retrievers)
 └── What single-score judges can report → localization requires pairwise comparison
       (RW1 + RW2 score-validity gap)
```

The same property — behavioral-axis precision, within-family discrimination — that helps
direct-selection also harms retrieval and can harm families where thin descriptions are
already sufficient. This is the central non-obvious finding: description improvement is
not universally beneficial; it is regime-specific.

---

## Cross-Experiment Regime Table

| Finding | Experiment | Regime | Effect | N | p |
|---------|-----------|--------|--------|---|---|
| +34.5pp discrimination (oracle, parse-success) | T18 (60-tool, gemma2:9b) | **IN-REGIME** | +34.5pp | 16 contested tasks | p<0.0001 |
| +40.8pp survival at 70B | FRONTIER-T18 (Llama-3.3-70B, diff harness) | **IN-REGIME** | +40.8pp | 19 contested tasks | p<0.0001 |
| 83–100% recovery, documented source | Q3 F-DOC / Q5 / Q6 Guard-B | **IN-REGIME** | 83–100% recovery | 6 contested tasks | p=0.0313 |
| No headroom — GitHub MCP | RW1 | **OUT-OF-REGIME** | +0pp | 21 tasks | n/a (aborted) |
| No headroom — AWS IAM MCP | RW2 | **OUT-OF-REGIME** | +0pp | 29 tasks | n/a (aborted) |
| HARM on already-resolved family | P2-A account_query | **HARM** | −20pp | 5 tasks | n/a |
| Retrieval harm, all retrievers | F2 | **ANTI-REGIME** | −0.079 to −0.224 MRR | 93 queries | n/a |
| Interface-only generation fails | Q2a + Q2b | **OUT-OF-REGIME** | 12.5% recovery | 18 contested tasks | p=0.5 |
| Single score can't localize | RW1 + RW2 score-validity gap | **STRUCTURAL LIMIT** | n/a | n/a | n/a |

---

## Paper Claim Inventory (for GG ratification — factual syntheses, not framed claims)

The following are factual descriptions of what the data shows. GG ratifies all
external framing (e.g., "market is durable", "blanket fixing is unsafe").

1. **Regime-bounded effect:** The description improvement effect is real but regime-bounded.
   It requires catalog density ≥ 60 tools AND source docstrings for safe generation.
   Outside this regime, the effect is zero (no headroom) or negative (harm).

2. **Scale-gated:** The effect was absent at 16-tool scale (T17) and present at 60-tool scale
   (T18) with the same agent. Density is the gating variable.

3. **Strong-agent survival (open model):** The effect survives a substantially stronger open
   model (Llama-3.3-70B vs gemma2:9b). Effect size does not collapse. Frontier question
   (Claude/GPT-class) remains open.

4. **Retrieval is anti-correlated:** Better descriptions harm retrieval across all three
   retriever types tested. The property that helps selection hurts retrieval.

5. **Harm is real:** −20pp harm on the account_query family from both Guard-B and Oracle.
   Blanket fixing is not safe; per-family targeting is needed.

6. **Single-score localization gap:** The current discoverability dimension cannot identify
   which tool pairs are confusable. Pairwise comparison is structurally required (EXP-3).

7. **Source is the information bottleneck:** Interface-only generation (Q2a/Q2b) cannot close
   the T18 gap regardless of generation strategy. Source docstrings are the required input.
