# When Does Tool-Description Quality Actually Improve Agent Behavior? A Regime Analysis

**Status:** DRAFT — Framing A (boundary-establishment), locked by GG. Every number in this
draft traces to a row in `docs/paper/evidence_table.md`; do not add a number here without
adding and sourcing it there first. Scope: EXP-4 (regime map, consolidation) + EXP-1
(prevalence) + EXP-3 (confusability localizer). EXP-2 (capability ladder) is out of scope —
dropped and justified in `spec.md`.

---

## Abstract

Tool-description quality is widely treated as a broadly-applicable, improvable lever for
agent tool-use: better descriptions are assumed to help agents pick the right tool more
often, and tooling that rewrites, grounds, or scores descriptions is built on that
assumption. We test the assumption directly with a single frozen evaluation protocol —
one classifier, one judge, one generator family, pre-registered thresholds — applied across
a synthetic confusable-catalog experiment, two real production MCP-server mirrors, a
synthetic internal-proxy catalog, and a sampled pilot of ten public MCP servers. We find the
effect is real but **regime-bounded**: it appears only when a catalog is dense enough that
tool names stop disambiguating themselves (≥60 tools, ≥10 confusable families) and only when
description generation has access to documented source code, giving a +34.5 percentage-point
(pp) selection-accuracy gain on a synthetic catalog (gemma2:9b) that survives, undiminished,
on a substantially stronger open model (+40.8pp, Llama-3.3-70B). Outside that regime, the
effect vanishes or reverses: two well-documented production servers (GitHub, AWS IAM) show
zero headroom because agents already resolve tool selection from task context; a synthetic
internal-proxy catalog shows a family where better descriptions **harm** already-correctly-resolved
selections (−20pp); improved descriptions **harm** retrieval-based tool lookup across three
retriever types (lexical BM25/TF-IDF and semantic embedding); and a pilot sample of ten public
MCP servers shows the confusable-at-scale regime occurring in **0 of 9** servers with a testable
confusable family. We additionally test whether the regime can be cheaply *localized* — flagged
automatically before an agent ever encounters it — with a pairwise LLM-judge confusability
method, and find it cannot: under both a binary and a graded-confidence framing, the judge
flags roughly all pairs as confusable (precision 0.167, recall 1.00 in both), a robust failure
mode rather than an artifact of question phrasing. Together these results map where the
field's central assumption holds, and show it holds in a narrower and rarer place than current
practice assumes.

---

## 1. Introduction

### 1.1 The assumption under test

Agentic systems that call external tools — via MCP servers, OpenAI-style function schemas, or
similar interfaces — depend on an LLM agent correctly selecting which tool to invoke for a
given task. A large and growing body of practice treats the *quality of the tool description
text* as the primary lever for improving that selection: description linters, LLM-based
description rewriters, retrieval-readiness scoring, and "documentation quality" rubrics all
assume that clearer, more precise descriptions make agents more reliable, broadly and by
default. This assumption is rarely tested against real agent behavior at the regime level —
most evaluations either show a positive result on a hand-built adversarial fixture, or assume
the result generalizes without checking where it stops holding.

### 1.2 What this paper does instead

We hold three properties fixed across every experiment reported here: one frozen evaluation
protocol (Section 3), one classifier, and null-first-class reporting — an aborted or negative
result is reported as a finding, not omitted. Against that fixed protocol we ask three
questions in sequence:

1. **Where does description quality change agent behavior, and where doesn't it?** (Section 4,
   EXP-4 — a regime map assembled from every experiment run under the frozen protocol.)
2. **How common is the "it matters" regime in real, sampled MCP servers?** (Section 5, EXP-1 —
   a behavioral prevalence measurement on a pre-registered sample.)
3. **Can the regime be found cheaply, before deploying an agent against a real server?**
   (Section 6, EXP-3 — a pairwise confusability localizer, tested against behavioral ground
   truth.)

### 1.3 Contributions

- **A falsifiable, regime-bounded map** of where tool-description quality changes agent
  selection behavior: it requires catalog density (≥60 tools / ≥10 confusable families) *and*
  documented source access for safe generation; outside that intersection the effect is null or
  negative (Section 4).
- **A prevalence measurement**: on a pre-registered pilot sample of 10 Python-only public MCP
  servers, 0 of 9 servers with a testable confusable family showed in-regime behavior — a lower
  bound, not a closed claim, on how rare the regime is among public, documented servers
  (Section 5).
- **A localizer negative result**: a pairwise LLM-judge confusability method — the natural
  cheap alternative to running the full behavioral protocol against every server — fails under
  two independently pre-registered framings, in the same way both times (Section 6).

### 1.4 Roadmap

Section 2 positions this work against tool-use benchmarks, MCP documentation practice, and
retrieval-augmented tool selection. Section 3 fixes the evaluation protocol every experiment
reuses. Section 4 presents the regime map: where the effect helps, and — as part of the same
map, not a separate cautionary appendix — where it does nothing or actively harms. Section 5
presents the prevalence result. Section 6 presents the localizer result. Section 7 discusses
the synthesis. Sections 8–9 cover threats to validity and the reproducibility artifact.

---

## 2. Related Work

### 2.1 Tool-use and function-calling benchmarks

Benchmarks for LLM tool/function-calling typically measure whether an agent calls the *correct*
tool and constructs a *valid* call, usually against a fixed, hand-built catalog. Our starting
point is that these benchmarks say little about description *quality* specifically unless the
catalog is built to isolate it — which is why the regime map in Section 4 spans purpose-built
synthetic catalogs at controlled scale (T18) alongside real production-server mirrors (RW1,
RW2) rather than a single fixture.

### 2.2 MCP ecosystem and documentation practice

The Model Context Protocol ecosystem has produced a growing set of public servers with
widely varying documentation quality, and a parallel set of tools (linters, description
scorers, `llms.txt` conventions) that assume documentation quality is both measurable and
improvable in a way that changes agent behavior. Section 4.3.4 and Section 6 directly test
the measurability half of that assumption (can a scorer identify which tool pairs are
confusable) and find it fails at both the single-score and pairwise level as currently
constructed.

### 2.3 Retrieval-augmented tool selection

Where a catalog is too large to place in-context, tool retrieval (lexical or embedding-based)
is used to narrow the candidate set before selection. Retrieval and direct-selection
description quality are often assumed to move together — a better description should help
both. Section 4.3.3 shows they are anti-correlated: the same precision that helps
direct-selection disambiguation matches poorly against the coarse, intent-level queries a
retrieval index is queried with.

### 2.4 Positioning

This paper positions against the implicit claim, common across the practices above, that
tool-description-quality improvement is a broadly-applicable, low-risk intervention. We do not
dispute that it helps in *some* regime — Section 4.2 establishes exactly where — but we show
the regime is narrower, and the intervention riskier outside it, than that implicit claim
assumes.

---

## 3. Methods — The Frozen Evaluation Protocol

All results in this paper are produced under a single protocol, committed once
(`docs/research/frozen_protocol.md`) and never edited after any experiment's results were
collected. This section states it in full; individual experiment sections do not repeat it.

### 3.1 Governance

Every experiment's spec — task set, gold labels, stability-screen procedure, and sidedness of
the sign test — is pre-registered to its branch **before** any run starts. Any change to the
judge, scorer, rubric, or calibration constants ("condition #1") is escalated as a draft PR for
human review before merge. Null and aborted results are reported as-is; results are never
tuned after being observed. `ANTHROPIC_API_KEY` is never used in any experiment reported here,
to keep judge/generator/agent model families structurally independent of the assistant used to
run the research program.

### 3.2 Frozen configuration

| Component | Value |
|---|---|
| Judge model / seed | `llama3.1:8b` / `42` |
| Generator model | `qwen3:8b` (always distinct from the judge) |
| Default agent | `gemma2:9b` |
| Trials per arm | 5 (default); **3** for FRONTIER-T18 and EXP-3's judge calls — each independently pre-registered and justified (API rate/cost limits for FRONTIER-T18; matching the codebase's existing graded-judge convention for EXP-3) |
| Sign-test α | 0.05, two-sided unless pre-registered one-sided |
| Headroom ceiling | 0.85 — if Arm A (unmodified descriptions) already scores ≥85% parse-success accuracy on the contested set, the experiment aborts as a null (no headroom), rather than proceeding to an A/B comparison |
| Minimum contested tasks | 6 |

### 3.3 Classifier

Every trial is classified into exactly one of three outcomes, plus a separate flag:

- `SELECTED-CORRECT` — the agent selected the pre-registered gold tool.
- `SELECTED-WRONG` — the agent selected a different tool.
- `ABSTAINED-OR-HEDGED` — the agent produced output but hedged or explicitly abstained.
- `PARSE-FAILED` — the output could not be parsed into a structured selection at all.

`PARSE-FAILED` is always reported and never folded into the three-outcome denominator; a model
or condition that appears to show "no effect" is checked against its parse-failure rate before
that conclusion is accepted (Section 8.3).

### 3.4 Effect measurement

The unit of analysis is the **task**, not the trial. Arm A is run twice with independent seeds
as a stability screen; a task whose per-run accuracy differs by more than one trial is dropped
from the primary analysis and reported separately. Effect is Arm B accuracy minus Arm A
accuracy on parse-success, stable, contested tasks; the sign test is computed per-task
(B-beats-A vs. A-beats-B vs. tie), not per-trial.

### 3.5 Cross-experiment comparability

Cross-experiment effect-size comparisons (e.g., "does the T18 effect hold at a different
capability tier?") are valid only when the fixture, judge, classifier, and sign-test procedure
are identical and the *only* varying factor is the one under test. The T18 gemma2:9b (+34.5pp)
and FRONTIER-T18 Llama-3.3-70B (+40.8pp) figures reported in Section 4.2.3 are explicitly
**not** part of a single controlled ladder — they come from different harnesses and hosts — and
are never combined into a claim that the effect "grows with capability," only that it
"survives" at a higher capability tier tested independently. EXP-2, the controlled same-family
capability ladder that would test this properly, was dropped from this paper's scope (see
Section 8.2).

---

## 4. EXP-4 — Regime Map

EXP-4 makes no new runs; it consolidates every experiment already run under the frozen protocol
into a single map of where tool-description quality changes agent behavior and where it does
not. Framing A treats this map, together with the prevalence finding in Section 5, as the
paper's primary artifact — the field's assumption is not "false," it is **regime-bounded**, and
this section states the boundary precisely enough to be checked against a new server.

### 4.1 Where it helps

#### 4.2.1 Confusable-at-scale (T18)

On a synthetic 60-tool catalog (10 families of 6 near-neighbor tools each, gemma2:9b agent),
empty descriptions leave the agent to resolve tool selection from names alone: parse-success
accuracy on the contested subset is **62.9%** (110/175). Oracle descriptions that target each
family's within-family distinguishing dimension (storage medium, operation scope, permanence,
notification channel, computation type) raise this to **97.4%** (190/195) — a **+34.5pp**
discrimination effect (task-clustered sign test: n+=16, n−=0, ties=24, p<0.0001). A second,
mechanistically distinct effect appears alongside it: at this catalog density, empty
descriptions also destabilize call *formation* itself — parse-failure rate falls from 12.5%
(25/200) to 2.5% (5/200) under oracle descriptions, contributing roughly 5–6pp of the
aggregate delta separately from the discrimination effect.

Critically, this effect is **density-gated**, not a general property of description quality:
an earlier fixture at 16 tools / 8 clusters (T17) placed Arm A at 81.2% accuracy from names
alone — above the headroom ceiling, aborted before any description effect could even be
tested. The same description-quality manipulation that produces +34.5pp at 60-tool density
produces nothing measurable at 16-tool density, because names alone already disambiguate at
that scale. Density is the gating variable.

#### 4.2.2 Under-documented source with docstrings (Q3 → Q6, Guard-B)

The T18 result establishes that oracle (hand-written, ground-truth) descriptions help; it does
not establish that a *generator* can produce them safely. A four-stage progression on a
12–23-tool fixture (Q3, Q4, Q5, Q6) establishes both the recovery and safety conditions:

| Condition | Recovery (6 structural contested tasks) | p | No-fabrication |
|---|---|---|---|
| Q3 F-DOC (whole-file source + docstrings) | 83.3% (5/6) | 0.0625 (marginal) | PASS |
| Q3 F-BODY (whole-file, docstrings stripped) | 83.3% (invalidated) | — | **FAIL** — cross-tool source misattribution |
| Q4-DOC-scoped (per-tool source + docstrings) | 100% (6/6) | 0.0313 | **FAIL** — docstring-body vocabulary gap |
| Q4-BODY-scoped | 100% (6/6) | 0.0313 | PASS |
| Q5-guarded (per-tool source + docstrings + target-grounded prompt) | 100% (6/6) | 0.0313 | PASS |
| Q6-guarded (23-tool blanket application) | 100% (6/6) | 0.0312 | PASS, **0/11 regressions** on already-passing tools |

Two findings compose into the deployment answer. First, **generation from the interface alone
cannot recover the T18 gap**: two independent interface-only generation strategies (per-tool,
Q2a; catalog-aware, Q2b) both recover only 12.5% of the oracle gain (11.1pp of 88.9pp
available), not significant (p=0.50). The T18-decisive distinctions live in tool *behavior* —
absent from both tool names and identical parameter schemas — and no amount of interface-level
prompting recovers information that is not present in the interface. Second, **source access
alone is not automatically safe**: whole-file source with docstrings stripped, and per-tool
scoped source with docstrings present, each open a distinct fabrication failure mode (cross-tool
symbol misattribution; docstring-body vocabulary gaps, respectively). The safe *and* fully
recovering configuration — scoped source, docstrings retained, target-grounded prompting that
forbids comparative neighbor claims (Guard-B) — was reached only at the fourth iteration (Q5),
and confirmed to cause zero regressions when applied blanket across a 23-tool catalog including
three collision-prone pairs (Q6).

#### 4.2.3 Strong-agent survival (FRONTIER-T18)

A natural objection to Section 4.2.1 is that the effect might be an artifact of gemma2:9b's
specific capability level — a stronger agent might resolve the same catalog from names alone.
We re-ran the identical T18 fixture and oracle descriptions against Llama-3.3-70B (OpenRouter),
a substantially stronger open-weight agent, using a 3-outcome classifier and 3 trials per task.
Arm A accuracy was **59.2%** (71/120) — comparable headroom to the gemma2:9b run — and Arm B
(oracle) reached **100.0%** (120/120): an effect of **+40.8pp** (sign test n+=19, n−=0, ties=21,
p<0.0001; on the stable set excluding 5 Arm-A trial-flippers, n+=14, n−=0, p<0.001). All 19
Arm-A miss tasks were fully recovered by the oracle, with no oracle-resistant floor in this
fixture. The effect does not collapse, and does not shrink, moving from a 9B to a 70B agent.

This is a survival claim, not a growth claim, and not a frontier claim: Llama-3.3-70B is a
strong open model, not a Claude/GPT-class proprietary frontier model, and the +40.8pp figure is
**not directly comparable** to T18's +34.5pp — different harness, different classifier host
(Section 3.5). The result rules out "the T18 effect is a weak-agent artifact" as an
explanation; it does not close the question of whether a true frontier model would behave
differently.

### 4.2 Where it doesn't help, or actively harms

This is not a separate cautionary appendix — under Framing A it is the other half of the same
map, and the boundary in Section 4.2 is only precise because these non-regimes were tested
under the identical protocol.

#### 4.3.1 No-headroom real servers (RW1, RW2)

Two production MCP-server mirrors — GitHub (`github/github-mcp-server`, 21 tools, 5 confusable
families, real docstrings) and AWS IAM (`awslabs/mcp`, 29 tools, 3 confusable families,
including four-way attach/detach/user/group confusability) — were tested with real, unmodified
docstrings. Both resolved **100%** of tasks correctly, including every pre-registered contested
task (21/21 for GitHub; 29/29 including 12 contested for AWS IAM). There is no headroom for a
description fixer to recover on either server: gemma2:9b resolves these tools from task-context
wording alone, and the terse, one-sentence docstrings both servers already ship are sufficient.
The regime identified in Section 4.2.1–4.2.2 requires headroom that these two real,
well-documented servers simply do not have.

#### 4.3.2 Harm on an already-resolved family (P2-A account_query)

On a 48-tool synthetic internal-proxy catalog built to test whether description improvement is
uniformly safe across many confusable families, one family (`account_query`, 5 tools) shows the
opposite of the T18/Q-series pattern. Under thin descriptions, the task's SQL-like WHERE-clause
phrasing heuristically matches `query_accounts` by name: **100%** (5/5) correct. Under both
Guard-B-generated and hand-written oracle descriptions, more precise phrasing ("Executes a
parameterized SQL-like WHERE clause") introduces disambiguation noise among five semantically
related tools, and accuracy **drops to 80%** (4/5) under both — a **−20pp harm**, reproducing
at the same magnitude under two independent generation strategies, ruling out noise as the
explanation. Two other families on the same catalog (`ticket_lifecycle`: delete/purge/archive/
expire; `invoice_write`: update/upsert/patch/replace/amend) stay at 100% across all three arms —
task-context phrasing already signals the dangerous distinction ("this cannot be undone"), and
better descriptions add no incremental safety there either way. The one family that is *fully*
recovered from a genuine failure (`order_read`, 0%→100% under both Guard-B and oracle) is a
low-stakes return-shape disambiguation, not a high-stakes one. Aggregate across all 31 contested
tasks (A=77.4%, Guard-B=96.8%, Oracle=93.5%) is directional but underpowered (sign test
p=0.07/0.125); the account_query harm is the reproducible, per-family finding, and the aggregate
number should not be read as a headline recovery rate.

#### 4.3.3 Retrieval-readiness is anti-correlated, not neutral (F2)

If a catalog is too large to place in-context, tool selection is often mediated by a retrieval
step (lexical or embedding-based lookup against description text) before the agent ever sees a
candidate set. Testing the same P2-A catalog's descriptions as retrieval documents against 93
underspecified natural-language queries, across three retriever types:

| Arm | BM25 MRR | TF-IDF MRR | Embedding MRR (nomic-embed-text) |
|---|---|---|---|
| Thin | **0.304** | **0.317** | **0.510** |
| Guard-B | 0.225 (−0.079) | 0.204 (−0.113) | 0.286 (−0.224) |
| Oracle | 0.234 | 0.228 | 0.362 |

Thin descriptions **outperform** Guard-B and oracle descriptions on every retriever tested,
with the harm larger under semantic embedding retrieval than lexical retrieval. The mechanism
is legible: compact verb-noun descriptions ("Get the order.") keyword- and semantically-match
coarse, intent-level queries ("get an order") directly; precision-optimized descriptions
("Returns order summary fields including status, total, item count...") match at the
implementation level — exactly the level that helps within-family selection disambiguation
(Section 4.2.1) and hurts coarse retrieval matching. The property that makes a description good
for one downstream use (direct selection in a fully-listed catalog) makes it worse for another
(retrieval against a partial query) — this is the central non-obvious finding connecting
Sections 4.2 and 4.3.

#### 4.3.4 Single-score judging cannot localize which pairs are confusable

Both real-server mirrors were also scored with AgentGauge's existing `discoverability` judge,
whose sub-score returns a single number per catalog. On GitHub, the score is flat at ~70/100
across every family, and does not flag either of the two families GitHub's own maintainers
consolidated to reduce confusion (0/2 overlap). On AWS IAM, the score is flat at ~68.7/100, and
does not flag any of the three contested families (0/3 overlap); the accompanying name-collision
heuristic instead flags verb-antonym pairs (`attach_user_policy`/`detach_user_policy`) that
caused zero real confusion. A single number per catalog is structurally incapable of naming
*which* pair is the problem — this is the motivating gap for the localizer tested in Section 6,
not a calibration issue that more judge tuning would fix.

### 4.4 Mechanism throughline

```
Description precision HELPS within-family discrimination when:
 - Catalog density is high enough (>=60 tools / >=10 families) that
   names alone are ambiguous, AND
 - Source access includes docstrings (safe generation requires this;
   body-only source opens a fabrication vector), AND
 - Arm A shows real headroom (the agent is not already resolving from
   task-context wording).

The same precision is ORTHOGONAL or ANTI-CORRELATED to:
 - what context-rich agents need (RW1, RW2, and P2-A's high-stakes
   families all resolve at 100% from context alone, regardless of
   description quality),
 - what retrieval rewards (F2: harm across all three retriever types), and
 - what a single-score judge can report (localization requires a
   pairwise comparison, tested next in Section 6).
```

---

## 5. EXP-1 — Server-Population Prevalence

### 5.1 Question and regime definition

Section 4 establishes *where* the effect exists; it does not establish *how common* that
regime is among real MCP servers. We define "in-regime" behaviorally, not by any static
description-quality property (which would be circular): a confusable family on a server is
in-regime iff, under the frozen protocol, (a) the server's real shipped descriptions fail at
least one contested task, **and** (b) an oracle description recovers it. "Thin descriptions" is
an input property; only behavior the fix actually repairs counts as in-regime.

### 5.2 Sampling frame

The frame was pre-registered and rebuilt five times over the course of the experiment, each
rebuild escalated and ratified before proceeding, never silently:

- v1 (star-stratified GitHub-topic pool) → v2 (doc-density-stratified, N=23) → v3–v4 (three,
  then a fourth, confirmed Python-AST-extractor bug found and fixed while preparing the trial
  batch) → v5 (final): a systematic audit found that the generic regex fallback used for
  **every non-Python server** pulls in systemic noise (template literals, parameter names,
  category labels, unrelated example data) — a capability limit of blind text-proximity
  matching, not a fixable parsing bug. All 11 non-Python servers were dropped.

The final, ratified frame is **N=10, Python-only**, sourced from public GitHub. This is a
narrower claim than "public MCP servers" — it is "Python MCP servers on GitHub, N=10 pilot" —
stated as such everywhere this number appears in this paper.

### 5.3 Result

| Server | Tier | Arm A | Arm B (oracle) | Effect | Verdict |
|---|---|---|---|---|---|
| github-mcp (RW1, anchor) | anchor | 100% (21/21) | — | n/a | OUT-OF-REGIME |
| aws-iam-mcp (RW2, anchor) | anchor | 100% (29/29 incl. 12 contested) | — | n/a | OUT-OF-REGIME |
| lucasastorian-llmwiki | near_empty | 100% | — | n/a | OUT-OF-REGIME |
| stefanoamorelli-sec-edgar-mcp | thin | 100% | — | n/a | OUT-OF-REGIME |
| stickerdaniel-linkedin-mcp-server | thin | 100% | — | n/a | OUT-OF-REGIME |
| mrexodia-ida-pro-mcp | near_empty | 90% | — | n/a | OUT-OF-REGIME (above headroom ceiling) |
| AminForou-mcp-gsc | well_documented | 75% | 75% | +0pp | OUT-OF-REGIME (real functional overlap; no description fixes it) |
| taylorwilsdon-google_workspace_mcp | thin | 0% | 0% | +0pp | OUT-OF-REGIME (catalog-overwhelm failure mode, not confusability) |
| datalayer-jupyter-mcp-server | near_empty | 70% | 55% | **−15pp** | OUT-OF-REGIME (HARM — replicates the P2-A account_query pattern on a fresh real server) |
| Dataojitori / blazickjp-arxiv / LycheeMem | well_documented | — | — | — | no testable confusable family (3 servers) |

**Headline: 0 of 9 servers with a testable confusable family show in-regime behavior** (7
freshly scored + 2 RW1/RW2 anchors cited from Section 4.3.1). Per fresh-only tier:
well_documented 0/1 testable, thin 0/3, near_empty 0/3 — a clean null across every tier of this
pilot. Three of the ten servers had no genuinely confusable family at all (mechanical
clustering found none, or the one candidate was rejected on manual review as not genuinely
confusable).

### 5.4 The seed-bug episode

A first trial run passed a single fixed seed (`seed=42`) to every one of five nominal repeated
trials per task, instead of the codebase's established `seed=42+trial_idx` convention — meaning
the first run sampled zero real trial-to-trial variance. That run reported two servers as
in-regime (`mrexodia-ida-pro-mcp` +50pp; `datalayer-jupyter-mcp-server` +25pp). Fixing the seed
and re-running **reversed both findings**: ida-pro's real Arm A accuracy is 90% (correctly
aborts, no headroom), and jupyter's Arm B is a genuine harm (−15pp, not a +25pp recovery). Both
apparent in-regime results were seed artifacts, caught before being reported as findings — we
report this as a credibility asset for the pipeline's own error-detection, and separately, in
Section 8.3, as a threat to validity in the opposite direction (a bug that suppressed a real
signal, rather than manufacturing a false one, would not have an analogous "surprising result"
trigger to catch it by).

### 5.5 Scope

Public servers skew documented relative to the internal/custom long tail; this prevalence
figure is a **lower bound** on how common the regime is, not a closed population estimate. We
do not claim the regime "does not occur" — we claim it is rare in this sampled population of
public, source-available Python MCP servers as of the frame's fixed date, and that the
under-documented internal segment this bounds is, by construction, unsampleable from public
data.

---

## 6. EXP-3 — Confusability Localization

### 6.1 Motivation

Section 4.3.4 established that the existing single-score `discoverability` judge cannot say
*which* tool pair in a catalog is confusable — a structural limit of returning one number per
catalog. If the confusable-at-scale regime (Section 4.2.1) is to be found cheaply, before
running the full behavioral protocol against every server, a localizer is needed that outputs a
per-pair signal. This section builds and tests the natural next attempt: ask the same frozen
judge a pairwise question directly.

### 6.2 Method

For each candidate tool pair (A, B), one judge call (`llama3.1:8b`, frozen) asks whether a task
intended for A could plausibly select B instead, and vice versa. Ground truth is a
pre-registered, 24-pair fixture (4 CONFUSED / 20 NOT_CONFUSED) built entirely from
already-collected behavioral trial data — six servers from Section 5's fresh EXP-1 scoring, plus
nine pairs from the RW1/RW2 anchors, including several pairs the *old* Levenshtein-based
heuristic had already false-positived (a deliberately adversarial inclusion). 3 trials per pair
(seed 42+trial_idx), majority vote. The pre-committed bar for "a real positive method": precision
≥ 0.50 **and** recall ≥ 0.50.

### 6.3 Binary result

Confusion matrix: TP=4, FP=20, FN=0, TN=0. **Precision = 0.167, recall = 1.00** — recall clears
the bar; precision does not. All **24 of 24** pairs were verdicted CONFUSABLE, including all
nine sampled pairs from the two 100%-accuracy anchor servers (GitHub, AWS IAM) and both pairs
where the old heuristic already false-positived. The judge catches every real behavioral
confusion (perfect recall) by flagging almost everything — a direct yes/no confusability
question elicits a near-uniform "yes" from this judge on this fixture, not a discriminating
per-pair signal.

### 6.4 Graded-confidence retry

One further, pre-registered, time-boxed retry (ratified before running, per the
"is this a framing artifact" question) replaced the binary question with a 0–10 confidence
score, using the same aggregation and ground truth, threshold ≥5.0 (scale midpoint, fixed
before any result was seen). Result: **every one of the 24 pairs'** mean score landed in a
**5.00–5.67 band** — identical confusion matrix to the binary run (precision 0.167, recall
1.00). This is a *different* degenerate failure mode from the binary run's uniform-yes: rather
than defaulting to one categorical answer, the judge anchors near the numeric midpoint of its
own scoring guide regardless of input — genuinely confused pairs and 100%-resolved anchor pairs
score in the same narrow band.

### 6.5 Conclusion

The negative is robust to framing, not an artifact of question phrasing: two structurally
different question formats (categorical yes/no; graded 0–10 confidence) produce the same
confusion matrix via two different degeneracy mechanisms. **Pairwise judging, binary or
graded, with this frozen judge, is not a usable per-pair confusability signal on this fixture.**
Per pre-registration, this is a hard stop — no third variant was attempted. We note the scope
of what this rules out: the experiment validates the *judging* step only, given a candidate
pair; it does not test an automatic candidate-*generation* mechanism (which pairs to even
consider from a full catalog), and two of the four real confusions in the ground truth cross
mechanical name-prefix family boundaries that a family-scoped candidate generator would not
have proposed in the first place.

---

## 7. Discussion

Read together, Sections 4–6 answer the paper's title question precisely rather than broadly.
Tool-description quality *does* change agent selection behavior — but only inside an
intersection of conditions (catalog density, source documentation, real headroom) that a
pre-registered pilot sample of real public servers places at 0 of 9 tested servers, and that
cannot currently be located cheaply by asking an LLM judge pairwise whether two tools are
confusable. Outside that intersection, the same intervention that helps direct selection can
be neutral, harmful to selection on already-resolved families, or harmful to retrieval — three
independently-measured non-regimes, not one.

The practical implication for MCP server authors and tool-catalog builders is not "descriptions
don't matter" — it is "check whether you are in the regime before investing in description
tooling." A server with fewer than ~60 tools and no dense within-family collisions, whose
agent already resolves tasks from context, gains nothing from more precise descriptions and
risks the account_query-style harm pattern (Section 4.3.2) if it applies them blanket. A server
that *is* in the regime should generate descriptions from documented source with a
target-grounded, non-comparative prompt (Section 4.2.2's Q5/Q6 configuration), not from the
interface alone.

What would change this picture: a larger or non-Python-verified EXP-1 sample (Section 5.5); a
true proprietary-frontier-model replication of Section 4.2.3; or a localizer signal that does
not route through this frozen judge's pairwise-question failure mode (Section 6.5) — for
example, a signal derived from name-embedding distance plus schema overlap rather than an LLM
judgment call.

---

## 8. Threats to Validity / Limitations

Full list: `docs/paper/threats_to_validity.md`. Summarized here by category; every item there
traces to a specific finding already reported in Sections 4–6, not a hedge added at write-up
time.

### 8.1 Sampling / generalizability
N=10, Python-only, public-GitHub pilot. The strength claimed is *convergence* — the EXP-1 null,
the RW1/RW2 anchors, the P2-A account_query harm, and the doc-density-rarity pattern across
tiers all point the same direction independently — not N=10 in isolation. Non-Python mechanical
extraction was dropped as a capability limit of the method, not a data-availability
inconvenience. Tier labels (well_documented/thin/near_empty) are relative ranks within the
sampled pool, not absolute bands.

### 8.2 Agent / model scope
One default agent (gemma2:9b) across the regime map, Q-series, RW1/RW2, and P2-A. The
controlled capability ladder that would test agent-capability sensitivity directly (EXP-2) was
dropped from this paper's scope — ratified, justified by the regime already being uncommon in
the sampled population (a ladder over a rare regime has limited external relevance). FRONTIER-T18
is one model, one data point, not apples-to-apples with the gemma2:9b harness, and not a
proprietary-frontier-model result.

### 8.3 Measurement / judge validity
Two seed-bug false positives were caught and reversed before reporting (Section 5.4) — a
credibility asset for the pipeline's self-correction, paired with a genuine asymmetry threat: a
bug that silently suppressed a real signal (a false negative) would not have the same
"surprising result triggers a recheck" property that caught these false positives. EXP-3's
negative is robust across two framings, not a single-question artifact, but validates the
judging step only, not candidate-pair generation. Trial counts deviate from the 5-per-arm
default for FRONTIER-T18 and EXP-3 (3 each), independently pre-registered and justified.

### 8.4 Harm / asymmetric risk
Blanket description-fixing is not universally safe: P2-A's account_query family shows
reproducible −20pp harm under two independent generation strategies. Do-no-harm testing (Q6)
covers only the case where honest descriptions remain semantically distinct across sibling
tools; total description collapse to identical phrasing is explicitly untested.

### 8.5 Reproducibility-artifact note
The FRONTIER-T18 result (Section 4.2.3) required, during this paper's preparation, recovering a
raw result file that existed only as a gitignored local artifact and independently re-deriving
its numbers before committing it as a hashed fixture (Section 9.2). This is now resolved for the
reported number; the harness code that produced it remains in an unmerged branch (Section 9.2).

---

## 9. Reproducibility Artifact

### 9.1 Claim

Every figure in Sections 4–6 traces to a committed file on this paper-writing branch, verified
against a specific commit reachable from `HEAD` (full trace: `docs/paper/evidence_table.md`).
Fixture files carry pre-registered SHA-256[:12] hashes recorded at pre-registration time
(protocol appendix: `docs/research/frozen_protocol.md`).

### 9.2 FRONTIER-T18 data/code split (state plainly, not silently)

The result data underlying Section 4.2.3 is committed and independently re-derivable from this
branch: `evals/fixtures/frontier_t18_step2_result.json` (per-task, sha256[:12]=`3ca4a25dbd25`)
and `evals/fixtures/frontier_t18_step2_raw_calls.json` (all 240 raw per-call LLM responses,
sha256[:12]=`93fb0d77262d`) — re-counting `SELECTED-CORRECT` directly from the raw calls
reproduces 71/120 (Arm A) and 120/120 (Arm B) exactly. The **harness code** that produced these
files (`agentgauge/frontier.py`, `scripts/run_frontier_t18.py`) still lives only in an unmerged
branch (`claude/frontier-t18`, open draft PR #50) — a from-scratch re-run of this experiment
requires merging that code first, even though the reported number is verifiable from committed
data today. This split — data committed, harness code pending merge — should be resolved (by
merging PR #50) before final submission if a fully push-button re-run is required by a venue.

### 9.3 Governance

All research-program branches route through draft, human-reviewed PRs; any change touching the
judge, scorer, rubric, or calibration constants is escalated before merge (Section 3.1). No PR
in this research program has auto-merge; a human merges every one.

---

## 10. Conclusion

Tool-description quality changes agent tool-selection behavior in a real, measurable, and
mechanistically legible way — but only inside a narrow, checkable regime: catalogs dense enough
that names stop disambiguating themselves, and generation with access to documented source. That
regime survives a substantial capability increase in the agent tested (Section 4.2.3), which
rules out "weak agent artifact" as an explanation for it being real. But it appears in 0 of 9
servers with a testable confusable family in a pre-registered pilot sample of real, public,
documented MCP servers (Section 5), the same intervention harms selection on already-resolved
families and harms retrieval across every retriever type tested outside that regime (Section
4.3), and the regime cannot currently be located cheaply by asking an LLM judge pairwise whether
two tools are confusable (Section 6). The field's assumption that description-quality
improvement is a broadly beneficial, low-risk lever is not wrong so much as over-general: this
paper's contribution is the boundary that makes "broadly" precise enough to check.

---

## Appendix

- **A.1** Full cross-experiment regime table: `docs/research/exp4_regime_map.md` §Cross-Experiment
  Regime Table.
- **A.2** Frozen judge/generator prompts (Guard-B target-grounded prompt; pairwise
  binary/graded confusability prompts): `agentgauge/fixer.py` (`_DESC_GENERATOR_GUARD_B_PROMPT`),
  `docs/research/exp3_pre_registration.md` §2, §7.
- **A.3** Fixture hash manifest: generate per `docs/research/frozen_protocol.md` Appendix; the
  two FRONTIER-T18 hashes added this session are recorded in Section 9.2 above and in
  `docs/paper/evidence_table.md` §1.3.
- **A.4** Per-server EXP-1 table: Section 5.3 above (reproduced from `STATUS.md` EXP-1 section).
