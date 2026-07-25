# AgentGauge v0.4.0 — reconciling the type_enum_contradiction effect-size discrepancy

## 1a. Tracing both figures to source

**-25.2pp / -28.9pp / -13.3pp** (gemma2:9b / llama3.1:8b / qwen2.5:7b) — the
**pooled BLOCKING-tier per-model effect**, `reports/v2_2_task_b_causal_chain_multimodel.md`
§B1-B3: 6 tool sets, `trials_per_task=1`, **18 BLOCKING instances (45 tasks)
per model, pooling 3 defect types** (`type_flipped`, `enum_dropped` — both
map to `type_enum_contradiction` — and `contradictory_required_claim`,
which mapped to `required_references_missing_property`, still BLOCKING tier
at that time, since demoted in v2.3). **Independently re-measured in v2.4**
(`reports/v2_4_task1_blast_radius_audit.md` §1b, live on a freshly rebuilt
Cloud Run instance, "restricted to the 3 BLOCKING defect types" — the same
scope, not a subset): **-25.19pp / -28.89pp / -13.33pp**, matching to 2
decimal places. This is the only version of this claim that has been
independently re-measured and reproduced.

**-40.0pp** — `reports/v2_2_task_b_causal_chain_multimodel.md` line 47, the
**per-defect-type breakdown table**: gemma2:9b's `enum_dropped` sub-defect
specifically, **n=15** (not the pooled n=45), CI **[-66.9, -13.1]**. This is
real, measured data — not fabricated — but it answers a narrower, different
question: one defect subtype, one model, at a sample size the source
document itself flags as insufficient ("`type_enum_contradiction`'s effect
is NOT uniformly significant across models when split by individual defect
type at n=15" — qwen2.5:7b's per-defect-type CIs include zero at this
granularity, even though its *pooled* n=45 figure doesn't). **Never
independently re-measured** — v2.4's re-measurement re-verified the pooled
n=45 figures, not the per-defect-type n=15 breakdown.

## What changed: a category error, not a re-run or a different subset

The claim-audit pass (`reports/v0_4_0_pre_publication_claim_audit.md`) took
the range's floor from one measurement (pooled, n=45, twice-verified) and
its ceiling from a *different* measurement (one defect subtype, one model,
n=15, never re-verified, and — per its own source document — not uniformly
significant at that granularity). Constructing a range by min/max-ing across
two different levels of pooling produces a number that looks like "the
type_enum_contradiction pooled 3-model range" but isn't a real statistic of
anything — no single measurement produced "-13.3 to -40.0pp." This was an
error introduced during that audit pass, not a re-run, a schema change, or a
different defect subset being intentionally selected.

**Secondary note, disclosed for completeness, not actioned**: the -25.2/
-28.9/-13.3pp figures pool `type_enum_contradiction`'s two defect subtypes
with `required_references_missing_property`'s one (now-separately-tracked,
null-effect) subtype. Since that third subtype shows ~0pp effect in all 3
models, pooling it in dilutes the average toward zero rather than inflating
it — meaning these figures are, if anything, a slight *understatement* of
`type_enum_contradiction`'s fully-isolated effect, not an overstatement. No
independently-verified `type_enum_contradiction`-only (2-defect-type, n=30)
pooled remeasurement exists to cite instead of the current figures — this
is the best verified number available, not a compromise.

## 1b. The single correct figure — per-model, with 95% CIs

| Model | Δ (task success) | 95% CI | n |
|---|---|---|---|
| gemma2:9b | **-25.2pp** | [-39.0, -11.3] | 45 |
| llama3.1:8b | **-28.9pp** | [-43.6, -14.2] | 45 |
| qwen2.5:7b | **-13.3pp** | [-25.2, -1.5] | 45 |

Range: **-13.3pp to -28.9pp**. Independently re-measured in v2.4 to 2
decimal places (-25.19/-28.89/-13.33) on a separately rebuilt instance —
the most-verified number in this project's causal-chain findings, checked
twice, holds both times.

**Corrected to this figure, replacing "-13.3 to -40.0pp," in:**

- `README.md:36` (per-rule measured-effect table)
- `reports/capability_statement.md:16` (headline numbers table)
- PR #64 description, headline-numbers table (via `gh pr edit`)
- `reports/v2_product_readiness.md:179` (§0-B.2 re-tiering table)
- `reports/v0_4_0_pre_publication_claim_audit.md:89,95` (this session's own
  claim audit — corrected with a note rather than silently rewritten, since
  it documented what was believed true at the time)

`agentgauge/cli.py` needed no change: its docstrings state "at most one
lint rule has a validated causal effect" without citing a specific
percentage-point figure, so it was never inconsistent.

## 1c. -40.0pp does not survive as a headline figure

Per this task's explicit fallback: it cannot be traced to a verified source
*for the claim it was being used to support* ("type_enum_contradiction,
pooled, all 3 models"). **Reverted to the verified per-model figures above.**
The n=15 per-defect-type breakdown itself remains accurately reported where
it already lived (`reports/v2_3_task2_retiering.md`'s dense per-defect-type
cell, with its own caveats intact) — not deleted, just not promoted into
the one-number-everywhere headline claim.

## Independent verification

A separate verifier agent independently re-derived the pooled per-model
figures from source, confirmed the -40.0pp figure's actual scope (defect
subtype, model, n, CI) by reading the source table directly, and confirmed
every corrected location now states the same number.

**Result: all 4 items CONFIRMED, no discrepancies.**

1. `reports/v2_2_task_b_causal_chain_multimodel.md` independently re-read:
   confirmed the §B1-B3 pooled table (-25.2/-28.9/-13.3pp, n=45/model,
   pooling 3 defect types) and the separate per-defect-type breakdown table
   (gemma2:9b `enum_dropped` -40.0% [-66.9,-13.1], n=15) are genuinely two
   different tables measuring two different things.
2. `reports/v2_4_task1_blast_radius_audit.md` §1b independently re-read:
   confirmed it re-measured the pooled figures specifically ("restricted to
   the 3 BLOCKING defect types"), reproducing -25.19/-28.89/-13.33 — not
   the per-defect-type breakdown.
3. All 4 corrected locations (`README.md:36`, `reports/capability_statement.md:16`,
   `reports/v2_product_readiness.md:179`, and PR #64's live body via
   `gh pr view 64`) independently re-fetched and confirmed to state
   "-13.3 to -28.9pp" with the per-model breakdown, not "-13.3 to -40.0pp."
4. Independently searched `reports/`, `evals/`, and `scripts/` for any
   isolated 2-defect-type (`type_flipped`+`enum_dropped` only, excluding
   `contradictory_required_claim`) pooled remeasurement across all 3
   models — none found, confirming no better-scoped verified figure was
   missed or overlooked in favor of the coarser pooled one.

One note from the verifier, not a discrepancy: `reports/v0_4_0_pre_publication_claim_audit.md`
still contains the literal string "-13.3 to -40.0pp" (in the preserved
historical section, per design — a correction blockquote precedes it,
confirmed present by the verifier). Flagged here for clarity, not as an
outstanding issue.
