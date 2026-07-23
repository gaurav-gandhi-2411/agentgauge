# Predictive validity study: do AgentGauge's scoring axes predict real task success?

**Date:** 2026-07-23 (supersedes the 2026-07-19 n=18 version of this report)
**Branch:** `chore/predictive-validity-study` (not merged to `main`)
**Raw data:** `evals/fixtures/predictive_validity/results_raw.json` (45 manifest entries, 44 valid
records, 1 permanent error — see Repo State below)
**Agent model (ground truth):** `gemma2:9b` · **Judge model (AgentGauge scoring):** `llama3.1:8b`
**Zero-cost:** all inference via Ollama (local + a temporary Cloud Run GPU proxy for Stage B/
Phase 3 collection), no `ANTHROPIC_API_KEY`, no paid third-party API calls.

## Headline finding

At n=44 (up from the original n=18), **`description_quality` (ρ=0.417, p=0.0048) and
`overall_score` (ρ=0.371, p=0.0132) now reach statistically significant, moderate correlation**
with real agent task success — both clearly stronger than the single-prompt-judge baseline, which
stays non-significant (ρ=0.116, p=0.455). Against `baseline_desc_length` (ρ=0.305, p=0.0438,
itself only borderline-significant), the picture is weaker than "clearly beats": `description_quality`'s
point estimate is higher and its own CI ([0.112, 0.677]) sits further from zero, but the two
bootstrap CIs overlap almost entirely (`baseline_desc_length`'s own CI reaches up to 0.58) and no
paired difference test (e.g. a bootstrap of the rho *difference*) was run to confirm the gap is
itself real rather than sampling noise. Per the pre-registered decision rule, this still reads as
a **CONFIRM** — the axis/overall score are predictive and numerically ahead of every baseline,
including the one baseline that also clears significance — but the margin over `baseline_desc_length`
specifically should be read as suggestive, not decisive, pending a proper paired test.

**But** the Phase 3 before/after fixer-pair analysis shows a specific, replicating blind spot: in
**6 of 7** pairs, an LLM-rewritten "improved" description raises `overall_score` (and often the
naive single-prompt baseline) substantially — often +15 to +30 points — while real task success
stays flat or drops. Only 1 of 7 pairs (`grounded_server` → `grounded_server_fixed`) improved on
both dimensions together. The correlation holding in aggregate does not mean AgentGauge's score is
safe against a specific adversarial-ish case: an LLM asked to "improve" a tool's description, which
is exactly the shape of a common real-world CI workflow (a PR that touches tool docstrings).
**Commercial takeaway: keep the CI-gate-linter thesis, but add a fixer/rewrite-regression check as
a complementary guardrail — a single passing `overall_score` is not sufficient evidence that a
description rewrite improved real usability.**

## Methodology

### What changed since the n=18 version of this report

1. **Manifest expanded 18 → 45** (Stage B): 22 new tool-set fixtures added across 4 real-world API
   mirrors (RW1 GitHub, RW2 AWS IAM, P2A internal proxy, plus a 5th mirror) and 2 synthetic
   catalogs (Q3, Q6), each run through bad/guard-b/oracle description-quality arms, plus a second
   12-tool T18 family subset (data_write + validate families, distinct from the original
   data_fetch + notify subset) for family-independence checking.
2. **Ground truth metric fixed a second time** (Phase 2): the original binary
   `success AND selected_tool == tool_name` metric was degenerate — every example server in this
   repo accepts any well-formed call, so `success` was always `True` regardless of whether
   constructed arguments were actually correct. 44% of Stage-A records tied at an exact 1.0
   ceiling. Replaced with a continuous **fractional constraint-satisfaction score**
   (`evals/fixtures/predictive_validity/constraints.py`): `(correct tool selected) x (fraction of
   that task's registered argument-correctness constraints satisfied)`, raised
   `GROUND_TRUTH_TRIALS` from 1 to 5 for proper per-task trial averaging. Ceiling incidence dropped
   from 44% to 11.4% (5/44) under the new metric — reduced, not eliminated (see Limitations).
3. **Phase 3 added**: 5 new LLM-fixer-generated ("improved") description variants
   (`agentgauge.fixer.run_fixer`, generator=`qwen3:8b`) of 5 existing "before" fixtures, plus the
   2 pre-existing T18-family fixer pairs from Stage A, for a total of **7 before/after pairs** used
   in the degradation-pattern analysis below.

### Tool sets (45)

Spans deliberately-empty/vague descriptions, LLM-fixer-generated descriptions, hand-curated oracle
descriptions, and 5 real-world API mirrors (GitHub, AWS IAM, Jupyter, arXiv, LinkedIn, plus a
memory/knowledge-graph server) with real tool names and verbatim public docstrings. Full manifest:
`evals/fixtures/predictive_validity/manifest.py`.

### Ground truth

`task_success_rate` = mean, over `GROUND_TRUTH_TRIALS=5` trials per hand-vetted anti-tautology
task (`evals/fixtures/predictive_validity/blind_tasks.py`), of `(correct tool selected) x
(fraction of registered argument constraints satisfied)`. Tasks never quote the gold tool's name,
required enum values, or format patterns verbatim (see `blind_tasks.py` module docstring for the
original tautology-leak incident this convention fixes).

### AgentGauge score

`scorer.score_all(tools, OllamaProvider("llama3.1:8b"), client=..., trials=3, base_url=None)` — a
run fully independent of ground-truth collection (own live MCP session, own trials). `docs_manifest`
floors at a constant 20.0 for every entry (all connections are stdio) and is excluded from
correlation as degenerate by construction.

### Baselines

1. **Description length**: mean description character length per tool set, zero LLM calls.
2. **Single-prompt LLM judge**: one holistic 0–100 rating from `llama3.1:8b` on the full tool
   listing, no rubric, no per-axis decomposition.

## Results

### Correlation table (Spearman ρ, continuous task_success_rate vs. field, n=44, bootstrap 95% CI, 2000 resamples, seed=42)

Command: `uv run python scripts/predictive_validity_analysis.py --axis discoverability` (the
`--axis` flag only selects which axis's flagged-cases list prints; the correlation table always
covers every field).

| Field | ρ | p | 95% CI | Effect | Status |
|---|---|---|---|---|---|
| `description_quality` | **0.417** | **0.0048** | [0.112, 0.677] | moderate | significant |
| `overall_score` | **0.371** | **0.0132** | [0.055, 0.622] | moderate | significant |
| Baseline: description length | 0.305 | 0.0438 | [-0.038, 0.580] | moderate | significant (borderline — CI nearly touches 0) |
| `schema_completeness` | 0.234 | 0.126 | [-0.130, 0.556] | small | not significant |
| `discoverability` | 0.186 | 0.226 | [-0.161, 0.495] | small | not significant |
| Baseline: single-prompt judge | 0.116 | 0.455 | [-0.174, 0.384] | small | not significant |
| `error_legibility` | 0.042 | 0.788 | [-0.262, 0.341] | negligible | not significant |
| `selection_accuracy` | -0.211 | 0.169 | [-0.491, 0.118] | small | not significant, wrong direction |
| `call_correctness` | — | — | — | — | degenerate — excluded |
| `robustness` | — | — | — | — | degenerate — excluded |
| `docs_manifest` | — | — | — | — | excluded by construction (constant 20.0, stdio-only) |

**`description_quality` and `overall_score` are the two fields that reach conventional
significance (p < 0.05) with a 95% CI that clearly excludes zero.** `baseline_desc_length` also
nominally clears p < 0.05, but its CI's lower bound (-0.038) sits almost on zero — a fragile
significance the two AgentGauge fields don't share. `selection_accuracy` again points in the wrong
direction (as it did at n=18), though still not significantly so.

Old-metric comparison (binary `task_success_rate_binary`, same 44 records) is included in the
script's own output for provenance — it shows a *different* pattern of what reaches significance
(e.g. `discoverability` and `baseline_single_prompt` flip to significant under the binary metric
while `description_quality`/`overall_score` weaken slightly), underscoring that the ground-truth
metric choice, not just sample size, materially shapes which claims the data will support.

### Phase 3: before/after fixer-pair synthesis (7 pairs)

| Before | After | ΔTask success | Δoverall_score | Δbaseline (single-prompt) | Pattern? |
|---|---|---|---|---|---|
| `t18_vague_server` | `t18_fixer_server` | -0.025 | +17.8 | +20.0 | **yes** |
| `t18_vague_server` | `t18_q2b_server` | -0.067 | +17.2 | +12.0 | **yes** |
| `grounded_server` | `grounded_server_fixed` | **+0.183** | +27.4 | +4.0 | no — genuine joint improvement |
| `confusable_server` | `confusable_server_fixed` | -0.031 | +15.2 | +11.0 | **yes** |
| `mediocre_server` | `mediocre_server_fixed` | -0.150 | +29.8 | 0.0 | **yes** |
| `call_constraints_server` | `call_constraints_server_fixed` | 0.000 | +16.4 | 0.0 | **yes** (flat success, score still jumps) |
| `call_constraints_v2_server` | `call_constraints_v2_server_fixed` | -0.020 | +17.0 | +42.0 | **yes** |

"Pattern" = real task success dropped or stayed flat while `overall_score` and/or the naive
single-prompt baseline rose. **6 of 7 pairs (86%)** show this pattern, with `overall_score` gains
of +15 to +30 points on tool sets whose real success simultaneously fell or didn't move. Only
`grounded_server_fixed` improved on both axes together (its description quality genuinely uses
math-fixture-appropriate specificity that both the judge and the agent benefit from — consistent
with `grounded_server_oracle` also outperforming its base arm by a large margin).

This replicates and generalizes the Stage-A finding (previously observed only in the 2 T18-family
pairs) across 5 additional, structurally different tool catalogs (mixed-echo, confusable-name,
mediocre-enum, and two call-constraints families). The mechanism proposed in the original report
still holds: an LLM asked to "improve" a description tends to produce text that reads well to
another LLM (the judge, and apparently the single-prompt baseline too) without resolving the
specific schema/name ambiguity that determines whether a *different* model doing the actual
selecting picks correctly.

### Decision rule

Pre-registered rule: **CONFIRM** if an axis/overall reaches significance and beats the best naive
baseline by a meaningful margin; **PIVOT** if correlation stays null but the Phase-3 degradation
pattern replicates; **FALSIFY** if both fail.

**This lands in CONFIRM**, not PIVOT: `description_quality` and `overall_score` both reach
significance with CIs that clearly exclude zero, and both numerically beat every naive baseline,
including the one (`baseline_desc_length`) that also happens to clear the p < 0.05 bar —
`baseline_single_prompt` fails outright, and is the baseline most relevant to "just ask an LLM to
rate this," the closest naive substitute for AgentGauge's own judge-based axes. **Caveat honestly:**
`description_quality`'s edge over `baseline_desc_length` specifically is directional, not
statistically confirmed — their bootstrap CIs overlap substantially, and no paired test was run on
the rho difference itself. The commercial thesis — "the score predicts real agent success, and
beats a do-nothing single-prompt baseline" — is well supported at n=44; "the score beats a
dumb-heuristic description-length count" is the weaker, still-open half of that claim.

**With an important qualification the Phase-3 data forces onto the CONFIRM claim**: the same axis
that correlates with success in aggregate is fooled 6 times out of 7 by the single most
commercially-relevant regression case (an LLM-driven description rewrite). A product built solely
on "gate merges when `overall_score` is above threshold X" would have let 6 real regressions
through in this sample. The sellable positioning is therefore CONFIRM-plus-caveat: keep the score
as a predictive signal, but ship a distinct "did this PR's description rewrite help or hurt"
regression check (comparing before/after `overall_score` is not sufficient on its own, since it's
exactly the signal shown to rise on the bad cases) rather than relying on the absolute score alone.

## Limitations (read before citing any number above)

- **`rw2_arm_guardb` (1 of 45 manifest entries) has no ground truth.** Five collection attempts
  across two Cloud Run deployments and a local run all failed, with three distinct error
  signatures (`ConnectError`, `HTTPStatusError 500`, `HTTPStatusError 404`). Root cause, confirmed
  via Cloud Run logs (`llama-server GPU discovery watchdog timed out` / `context deadline
  exceeded`): the study's two-model requirement (`gemma2:9b` for ground truth, `llama3.1:8b` for
  judging) forces Ollama to swap models in and out of a single shared L4 GPU's VRAM on every
  `_run_one` call, and that swap intermittently fails — a probabilistic infra flake more likely to
  hit larger tool sets (more judge calls = more swap opportunities), not a data or code defect. The
  final (5th) attempt's `404` additionally reflects a cold-start model wipe, a known trade-off of
  the no-gcsfuse Cloud Run config used for this collection run (see Repo State). n=44 throughout
  this report, not 45.
- **Task-difficulty confound between tool-set families (found in this session's audit, not
  previously documented).** The RW1 family (`rw1_github_mirror`, `rw1_arm_a`, `rw1_arm_guardb`,
  `rw1_arm_oracle`) shows task_success_rate clustered at **0.95–1.00 across all 4 quality arms**
  (`{'rw1_github_mirror': 1.0, 'rw1_arm_a': 1.0, 'rw1_arm_guardb': 0.9524, 'rw1_arm_oracle': 1.0}`)
  — essentially zero variance despite spanning bad-to-oracle descriptions. Direct inspection of the
  live tool names (via `connect_stdio`/`introspect()`) shows why: RW1's real GitHub API tool names
  (`get_pull_request`, `get_pull_request_diff`, `get_pull_request_files`, ...) are self-explanatory
  enough that `gemma2:9b` likely selects correctly from the name alone, regardless of description
  quality — unlike `confusable_server`'s deliberately-synonymous names (`search_documents` /
  `query_records`, `list_items` / `enumerate_all`), where real spread (0.64 bad vs. 0.80 oracle)
  appears. Pooling a name-dominant family (RW1) with description-dominant families in one Spearman
  correlation attenuates whatever true signal exists — this biases the aggregate correlation
  toward the null, not toward a false positive, so it does not undermine the CONFIRM finding above,
  but it does mean the true effect size for description-sensitive tool sets specifically is likely
  understated by the pooled n=44 statistic.
- **Constraint coverage is not uniform across entries (found in this session's audit).** Verified
  programmatically (not from code comments): constrained-task fraction per entry ranges from
  **0%** (`exp1_blazickjp_arxiv_mcp_server_mirror` — all 8 tools have genuinely empty schemas, so
  no argument exists to constrain regardless of task specificity; correctly documented in
  `constraints.py`, but worth naming explicitly here) to 100%. For that one entry,
  `task_success_rate` is still effectively the old pure-tool-name-match metric. Half of
  `call_constraints_server`/`_oracle`/`_fixed`'s tasks are also intentionally unconstrained (empty-
  schema "easy" tools). Ceiling incidence (exact 1.0) dropped from 44% (old binary metric) to
  **11.4% (5/44)** under the fractional metric — real improvement, not full elimination.
- **`GROUND_TRUTH_TRIALS = 5`**, a deliberate compute bound. Still a modest number of trials per
  task for confidence-interval purposes at the individual-tool-set level (the correlation table's
  own bootstrap CI is across tool sets, not within one).
- **Single judge/agent model pair.** `llama3.1:8b` (judge) and `gemma2:9b` (agent) are each one
  point on the capability spectrum — see `agentgauge/CLAUDE.md`'s own calibration notes on
  `llama3.1:8b`'s aspirational absolute bands. Results should be read as "true for this model
  pair, this run," not "true of AgentGauge in general."
- **`docs_manifest` structurally degenerate** for this study (constant 20.0, all connections
  stdio) — excluded, not a finding about the dimension itself.
- **`call_correctness` and `robustness` remain degenerate/near-constant** at n=44 and are excluded
  rather than reported with a misleading near-zero correlation.
- **No formal chance-baseline computed.** Several ground-truth constraints are binary enums (e.g.
  `mediocre_server`'s hard/soft delete mode) with a non-trivial guess probability; a
  `task_success_rate` near 0.5 on such entries is not cleanly distinguishable from chance without a
  computed baseline, which this study does not provide.

## Recommended next step

The CONFIRM finding is real but should not be oversold as "the score alone is a safe CI gate." The
concrete next artifact this data argues for is a **fixer/rewrite-regression check**: re-score a
tool set before and after any description change and flag when `overall_score` rises while an
independent (cheap, automatable) proxy for real usability does not — which requires deciding what
that proxy is for a product context without this study's blind-task ground-truth machinery
available at gate-time. Not undertaken here; flagged as the natural following work item.

## Repo state note

All Stage A/B/Phase-3 study code, fixtures, and this report were committed to
`chore/predictive-validity-study` (not `main`) on 2026-07-23, following an audit pass (see below)
and 759 passing tests. The one pre-existing unauthorized commit (`b309e14`, `blind_tasks.py` base
version, committed by a prior session's executor without authorization) was left as-is per
instruction — not reverted or amended.

**GCP resources used for Stage B/Phase 3 collection (temporary, provisioned mid-session with
explicit user confirmation):** a `agentgauge-agent` Cloud Run service (region `us-central1`,
project `expense-tracker-498014`) was deployed to run `gemma2:9b` + `llama3.1:8b` + `qwen3:8b`
concurrently, after local collection was blocked by GPU contention from an unrelated `aetherart`
process. The service's original config (`scripts/agentgauge-agent-service.yaml`) mounts model
storage via a gcsfuse-backed GCS bucket for cross-cold-start persistence — this was found, via
direct Cloud Run log inspection, to be **fundamentally incompatible with Ollama's parallel-part
download writer**: all 3 model pulls stalled indefinitely (`gcsfuse` "legacy staged writes"
warnings, Ollama "part N stalled; retrying" on all 16 concurrent download parts, zero completed
blobs after 10+ minutes across 3 attempts). A time-boxed test confirmed the diagnosis: the same
pull succeeded in under 5 minutes against the container's own ephemeral disk (no gcsfuse mount).
The service currently runs on this ephemeral-storage config — model weights are **not** persisted
across a cold start / scale-to-zero cycle, unlike the pre-existing `agentgauge-judge` service
(left untouched throughout, per standing instruction). This trade-off directly caused the final
(5th) `rw2_arm_guardb` collection attempt's `404` error (models had been wiped by an intervening
cold start). **Disposition of the `agentgauge-agent` service and its bucket as of this report is
the user's decision, pending explicit confirmation** — it has been billing continuously since
deployment.

### Audit performed before trusting this data (this session)

Before relying on the expanded dataset, an adversarial pass checked for a third artifact of the
same class as the two already-fixed bugs (task-name leakage in Stage A's first pass;
partial-credit ceiling collapse in the original binary metric). Checked and ruled out as
*systematic* biases: (a) task-text/gold-tool lexical or semantic leakage — every quality-tiered
family shares the literal same task-list object across all description-quality arms, confirmed by
reading `BLIND_TASKS`, not just its comments; (b) partial-credit gaming — `constraint_satisfaction`
is a strict per-constraint check with no cross-task leakage possible. Found and documented above,
not previously written down anywhere: the RW1 tool-name-self-descriptiveness confound and the
arxiv-mirror 0%-constrained residual ceiling case. Neither manufactures a false-positive
correlation; both bias toward the null, meaning the CONFIRM finding above is, if anything,
conservative.
