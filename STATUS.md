# AgentGauge — Project Status

> Current as of 2026-07-04. Update this file when significant milestones land.

---

## EXP-3 — Pairwise confusability localizer (COMPLETE, DRAFT — condition #1, escalated to GG)

**Branch:** `claude/exp3-localizer`. **Pre-registered** (`docs/research/exp3_pre_registration.md`,
commit `603bfb2`, before any judge run): a 24-pair behavioral ground truth (4 CONFUSED / 20
NOT_CONFUSED) built entirely from already-collected EXP-1 `raw_log_a` trials + the RW1/RW2
validation anchors — no new agent runs. Judge design frozen before any call: `llama3.1:8b`,
3 trials/pair at `seed=42+trial_idx`, majority vote, parse-failed reported separately, and a
pre-committed bar (precision ≥ 0.50 AND recall ≥ 0.50 = "real positive method", else "honest
negative") fixed before results were in hand.

**Method:** `agentgauge/localizer.py` — for each candidate pair (A, B), one judge prompt asking
whether a task for A could plausibly select B and vice versa, given both descriptions. This
directly targets Non-Regime 4's structural limit (the single-score `discoverability` judge
returns one number per catalog and cannot name which pair is confusable).

**Result (real judge, `llama3.1:8b` — VRAM confirmed free, no residency conflict):**

Confusion matrix: TP=4, FP=20, FN=0, TN=0, undetermined=0. **Precision = 4/24 = 0.167, Recall =
4/4 = 1.00.** Per the pre-committed bar: **honest negative** (recall clears the bar; precision
does not).

**24/24 pairs were verdicted CONFUSABLE** — including both fully-resolved 100%-accuracy anchor
servers (RW1 GitHub, RW2 AWS IAM) in every one of their 9 sampled pairs, and both adversarial
pairs where the OLD Levenshtein heuristic already produced a false positive (RW1
`get_pull_request_diff`/`get_pull_request_files`; RW2 `attach_user_policy`/`detach_user_policy`,
`put_user_policy`/`get_user_policy`). The judge caught every real behavioral confusion (perfect
recall) but did so by flagging almost everything — a direct yes/no confusability question to
`llama3.1:8b` is close to a constant-YES predictor on this fixture, not a discriminating signal.

**This is a different failure mode than the single-score baseline, not a better one.** The
single-score judge structurally localizes nothing (0/24, by construction — one number per
catalog). The pairwise judge *does* localize (it outputs a verdict per pair), but with precision
indistinguishable from chance-at-base-rate on this class-imbalanced fixture (4/24 = 16.7%
positive rate; the judge's un-discriminating positive rate is 24/24 = 100%). Neither construction
is a usable ranking signal as built. **Pairwise localization is not automatically better just
because it asks a pair-level question — asking a binary judge to answer a leading yes/no
question elicits yes.**

**Scope-bound, pre-declared (not discovered after the fact):** this experiment validates the
*judging* step only, given a candidate pair — not an automatic candidate-*generation* mechanism.
2 of the 4 real confusions (`AminForou-mcp-gsc` delete_sitemap/manage_sitemaps; `datalayer`
read_notebook/list_notebooks) cross mechanical prefix-family boundaries; a family-scoped
generator would not have proposed them as candidates at all, independent of this result.

**Candidate next step (not run this session, GG decision):** the binary forced-choice format may
be the cause of the over-flagging — a graded confidence prompt (0–10 confusability score with a
tuned threshold) or a comparative framing (rank pairs by confusability rather than yes/no per
pair) could recover discrimination the binary question destroys. Flagged for GG rather than
run unilaterally, since it is itself a condition-#1 change requiring its own pre-registration.

**Verdict for the paper:** a real, clean negative result, reported per the frozen protocol's
null-first-class rule. "The single-score judge localizes nothing; naively asking the judge
pairwise localizes everything — neither construction, as tested, gives a usable per-pair
confusability signal." Full per-pair votes: `evals/fixtures/exp3_localizer_result.json`.
Condition #1 (new judge mechanism) — this PR is DRAFT, escalated to GG before merge.

CI: 696 tests (24 new in `tests/test_localizer.py`), 94.67% coverage, 100% on `localizer.py`.
`verify.sh` PASSED (ruff, ruff format, mypy non-blocking, pytest).

---

## EXP-1 — Server-population prevalence (COMPLETE — 0/9 scored servers IN-REGIME)

**Branch:** `claude/exp1-prevalence`. **Status:** frame ratified at N=10 (v5, commit `538affe`);
all 10 servers processed (7 behaviorally scored + 3 with no testable confusable family), plus
2 anchors cited from prior published work. **Headline: 0/9 scored servers (7 fresh + 2 anchors)
show IN-REGIME behavior.** EXP-2 (capability ladder) held pending GG's scope decision — see
scope-decision escalation below.

**Frame history (5 rebuilds, each re-escalated to GG, none silent):** started as a 30-server
GitHub-topic-search pool, star-stratified (v1) → corrected to doc-density-stratified (v2, N=23,
2 excluded as extraction-failed) → 3 confirmed Python-AST-extractor bugs found and fixed while
preparing the trial batch (v3, N=22 → protocol-handler false-positive, MCP Prompt/Tool conflation,
decorator-kwarg-vs-docstring blind spot) → a 4th bug found investigating the next candidate (v4, N=21
→ decorator string-argument false-positive; oraios-serena additionally excluded, real architecture is
class-based `Tool` subclasses, unsupported) → a systematic audit found the generic regex fallback used
for ALL non-Python servers pulls in systemic noise (template literals, parameter names, category
labels, unrelated example data) — not a fixable bug, a capability limit of blind text-proximity
matching. **All 11 non-Python (regex_best_effort) servers dropped** (v5, ratified, commit `538affe`).

**SCOPE, state explicitly wherever this number appears:** the frame is now **N=10, PYTHON-ONLY**.
The pre-reg's "ALL languages included" criterion is violated for reliability reasons, not choice.
The headline claim is **"Python MCP servers on GitHub, N=10 pilot"** — NOT a general public-MCP-server
population estimate. Extending trustworthy mechanical extraction to TypeScript/JavaScript/Go/Rust
would require real per-language AST parsers, not regex heuristics — out of scope for this pass.

**Final result (7 fresh scored + 3 no-family + 2 anchors cited):**

| Server | Tier | Family | Arm A | Arm B | Effect | Verdict |
|---|---|---|---|---|---|---|
| github-mcp (RW1 anchor) | anchor | 5 families, 21 tasks | 100% (21/21) | — | n/a | OUT-OF-REGIME (cited) |
| aws-iam-mcp (RW2 anchor) | anchor | 3 families, 12 tasks | 100% (29/29 incl. 12 contested) | — | n/a | OUT-OF-REGIME (cited) |
| lucasastorian-llmwiki | near_empty | create vs create_knowledge_base | 100% | — | n/a | OUT-OF-REGIME |
| stefanoamorelli-sec-edgar-mcp | thin | discover_xbrl_concepts vs discover_company_metrics | 100% | — | n/a | OUT-OF-REGIME |
| stickerdaniel-linkedin-mcp-server | thin | search_companies/jobs/people/conversations | 100% | — | n/a | OUT-OF-REGIME |
| mrexodia-ida-pro-mcp | near_empty | xrefs_to vs xrefs_to_field | 90% | — | n/a | OUT-OF-REGIME |
| AminForou-mcp-gsc | well_documented | delete_site vs delete_sitemap | 75% | 75% | +0pp | OUT-OF-REGIME (real functional overlap — manage_sitemaps can also delete; no description fixes that) |
| taylorwilsdon-google_workspace_mcp | thin | send_message vs send_gmail_message | 0% | 0% | +0pp | OUT-OF-REGIME (catalog-overwhelm failure mode — 116-tool listing produces malformed/hedged output, not confident wrong-tool picks; oracle description can't fix a different failure mode) |
| datalayer-jupyter-mcp-server | near_empty | read_notebook vs read_cell | 70% | 55% | −15pp | OUT-OF-REGIME (HARM — oracle description made selection WORSE, replicating P2-A's account_query HARM pattern in a fresh real-world server) |
| Dataojitori-nocturne_memory | well_documented | none found | — | — | — | no testable family |
| blazickjp-arxiv-mcp-server | well_documented | none found | — | — | — | no testable family |
| LycheeMem-LycheeMem | well_documented | candidate rejected on review (not genuinely confusable) | — | — | — | no testable family |

**Headline: 0/9 scored servers (7 fresh + 2 anchors) show IN-REGIME behavior.** 0/7 testable fresh
families recover under oracle descriptions; 3/10 fresh servers have no genuinely confusable family
at all (mechanical prefix clustering found none, or the candidate was rejected on manual review).
Per-tier (fresh only): well_documented 0/1 testable, thin 0/3, near_empty 0/3 — a clean null across
every tier of this N=10 pilot, consistent with the relative-tercile caveat (tier names are
within-sample rank, not absolute doc-quality bands).

**Methodological note — a seed bug was caught and fixed before reporting:** the first trial run
passed a fixed `seed=42` to every one of the 5 trial repetitions per task, instead of the codebase's
established `seed=42+trial_idx` convention (`agentgauge/scorer.py`, `agentgauge/fixer.py`) — meaning
the first run sampled ZERO real trial-to-trial variance. That buggy run showed 2 servers as
IN-REGIME (`mrexodia-ida-pro-mcp` +50pp, `datalayer-jupyter-mcp-server` +25pp). Fixing the seed and
re-running **completely reversed both findings**: ida-pro's real Arm A accuracy is 90% (not 50%,
correctly aborts with no headroom), and jupyter's Arm B is a genuine HARM (−15pp, not +25pp
recovery). Both "IN-REGIME" results were seed artifacts, not real effects — caught before being
reported as findings. Real per-trial variance matters; a fixed seed across nominal "trials" silently
converts a 5-trial design into 5 identical repeats.

**Two genuinely interesting non-recovery negatives (real, seed-confirmed):** (1) AminForou-mcp-gsc's
`delete_sitemap`/`manage_sitemaps` confusion reflects real overlapping tool CAPABILITY, not a wording
ambiguity — no description can fix a case where two tools can legitimately both do the same thing.
(2) taylorwilsdon-google_workspace_mcp's 0%/0% result is driven by malformed/hedged model output
under a 116-tool catalog, not confident wrong-tool selection — a catalog-SIZE failure mode, orthogonal
to the paper's description-QUALITY thesis, and correctly not fixed by an oracle description either.

**Scope decision — RATIFIED by GG, 2026-07-04:** paper = EXP-4 + EXP-1 + EXP-3. EXP-2 (capability
ladder) is DROPPED, justification "regime uncommon in sampled population → capability-ladder
external relevance limited" (see `spec.md` EXP-2 section, updated to record the decision and
preserve the design notes for reference). EXP-3 (localizer) is next — a confusable-pair localization
method is valuable independent of how often the regime occurs.

---

## P2-A — Synthetic internal-proxy experiment (gemma2:9b complete; 70B pending)

**Branch:** `claude/p2a-internal-proxy`. **Status:** gemma2:9b arm complete. 70B confirmatory arm
parked (Groq daily quota; run `python scripts/p2a_frontier_gate.py --trials 1 --mode ab` when it
resets — not blocking).

**Setup:** 48-tool synthetic internal-proxy catalog. 7 verb-collision families. 31 contested tools
(identical schemas, name-only disambiguation within family). 17 thorough tools (controls). Three arms:
A (thin descriptions — "Get the order."), Guard-B (qwen3:8b generated from mirror handler docstrings,
target-grounded only), Oracle (hand-crafted from mirror handler docstrings, encodes behavioral axis per
family). Agent: gemma2:9b, 3 trials. Gate: contested-set accuracy < 85% required for headroom.
Gate bug fixed (06122dd: was gating on overall 85.4%, would have false-aborted; contested = 77.4%,
correctly passes).

**Per-family results:**

| Family | n | A% | GB% | O% | GB-A | O-A | Flag |
|---|---|---|---|---|---|---|---|
| order_read_family | 4 | 0.0% | 100.0% | 100.0% | +100pp | +100pp | RECOVERED |
| invoice_write_family | 5 | 100.0% | 100.0% | 100.0% | +0pp | +0pp | — |
| ticket_lifecycle_family | 4 | 100.0% | 100.0% | 100.0% | +0pp | +0pp | — |
| account_query_family | 5 | 100.0% | 80.0% | 80.0% | −20pp | −20pp | HARM |
| notification_family | 5 | 60.0% | 100.0% | 80.0% | +40pp | +20pp | — |
| order_status_family | 4 | 75.0% | 100.0% | 100.0% | +25pp | +25pp | — |
| invoice_schedule_family | 4 | 100.0% | 100.0% | 100.0% | +0pp | +0pp | — |

Aggregate: A=77.4%, Guard-B=96.8%, Oracle=93.5%. Sign tests: GuardB vs A p=0.07, Oracle vs A p=0.125
(N=31; neither significant at α=0.05). Thorough-set do-no-harm: 0/17 regressions (PASS).

**Finding 1 — order_read [RECOVERED, both Guard-B and Oracle]:**
`order_read` is the one family with complete thin-description failure (A=0/4). Both Guard-B (+100pp)
and Oracle (+100pp) fully recover it. Return-shape disambiguation (summary vs full-record vs cached vs
computed) is description-fixable. **Fixer has a real, consistent job here.** Scope: read-shape
confusion is not a destructive outcome — the agent picks the wrong data shape, not the wrong action
class.

**Finding 2 — high-stakes families [CONFIRMED CONTROLS, 0pp delta all arms]:**
`ticket_lifecycle` (delete/purge/archive/expire — permanence axis) and `invoice_write`
(update/upsert/patch/replace/amend — mutation-scope axis): A=100%, Guard-B=100%, Oracle=100% across all
arms. Gemma resolves these from task context alone — task descriptions contain signals like "this cannot
be undone" and "leave all other fields exactly as they are." Good descriptions provide no incremental
accuracy on the dangerous confusions. **The destructive-confusion (painkiller) framing is not supported
by this proxy.** Context resolves danger; descriptions add no safety lift.

**Finding 3 — account_query [HARM, both Guard-B and Oracle]:**
`account_query` was 5/5 correct under thin descriptions — the SQL-like WHERE-clause syntax in the task
("Get all accounts where status='TRIAL' AND created_at > '2026-01-01'") maps heuristically to
`query_accounts` by name. Under oracle descriptions ("Executes a parameterized SQL-like WHERE clause"),
detailed phrasing creates disambiguation noise among the five account tools; gemma makes one wrong call
per arm. The harm reproduces at the same −20pp magnitude under both Guard-B and Oracle — not noise.
**More precise descriptions can regress families where thin descriptions already work via name-task
heuristic alignment.** This argues against blanket fixing and for targeted per-family application.

**Stats note:** Do not report "96.8% / 120% recovery" as headlines. The 96.8% vs 93.5% aggregate gap
and the >100% recovery fraction are artefacts of the account_query HARM dragging Oracle below Guard-B
(notification_family also shows Guard-B > Oracle on one task). The N=31 contested tasks produce a
sign test p=0.07 — directional, underpowered, not significant. Effect size is real at the per-family
level for order_read; aggregate numbers obscure more than they reveal.

**Scope caveat:** Synthetic proxy, gemma2:9b, one trial-set (3 trials per arm per task). 70B
(Llama-3.3-70B via Groq) gate arm confirmed headroom exists at 70B (77.4% contested). 70B A-vs-Oracle
per-family pending — will confirm whether the per-family pattern (order_read recovered, account_query
harmed, high-stakes at ceiling) is regime-shaped (consistent across model tiers) or specific to
gemma2:9b. Not blocking the interpretation below.

---

**ESCALATION TO GG — F2 direction decision (do not execute unilaterally):**

The P2-A frequency-probe result is bearish on the direct-selection thesis as the primary value
proposition. The finding that "agents already resolve the dangerous confusions from task context"
is actually good news for a different thesis: **retrieval-readiness**. A retrieval index (BM25 or
embedding-based tool lookup) ranks tools on description text alone — with no task context, no tool
name, no agent prior. This is the regime where thin descriptions most clearly fail and where
Guard-B's behavioral axis encoding directly adds signal. The "task context saves you" finding that
sinks the direct-selection painkiller explicitly does NOT apply to a retrieval index.

**F2 retrieval test RUN — result: NOT SUPPORTED (BM25 + TFIDF, underspecified queries):**

Pre-registered spec committed before scoring: `evals/fixtures/p2a_f2_retrieval_spec.json`.
Script: `scripts/p2a_f2_retrieval.py` (BM25 + TFIDF cosine-sim, description-only indexing, 93
queries across 31 contested tools × 3 queries each).

Aggregate MRR (all 31 contested tools, 93 queries):

| Arm | BM25 MRR | TFIDF MRR |
|---|---|---|
| thin | **0.304** | **0.317** |
| guardb | 0.225 | 0.204 |
| oracle | 0.234 | 0.228 |

Thin descriptions outperform Guard-B on underspecified queries across both lexical retrievers
and across 5 of 7 families. **F2 (retrieval-readiness) is NOT supported for BM25/TFIDF.**

**Mechanism (explains the direction):** Thin descriptions are compact verb-noun patterns ("Delete a
ticket.", "Notify the customer.", "Get the order.") that keyword-match natural-language queries
("remove a ticket", "notify a customer", "get an order") directly. Guard-B descriptions are richer
prose ("Permanently removes the ticket from all stores. IRREVERSIBLE...") that reduces keyword overlap
with underspecified queries. Lexical retrieval rewards term overlap; thin descriptions have more of it.

**Per-family notable findings:**
- order_read: thin=0.229, Guard-B=0.183 BM25 (NEUTRAL) / 0.116 TFIDF (HARM). Guard-B does NOT
  improve retrieval on the family it fully recovered in selection — opposite of F2 prediction.
- ticket_lifecycle + notification: largest Guard-B harms (−0.192 and −0.258 BM25). Thin descriptions
  for these families align tightly with the query vocabulary.
- account_query: thin=0.453, Guard-B=0.425 (NEUTRAL, −0.029). The selection harm (−20pp) does NOT
  propagate to retrieval here — descriptions are neutral, not harmful, on this family for retrieval.
  This is a small supporting signal for F2 (no inherited harm) but swamped by the overall result.
- order_status + invoice_schedule: only families where Guard-B improves over thin (+0.016/+0.051).
  Thin descriptions ("Confirm an order.", "Schedule an invoice.") are less keyword-aligned with
  queries like "advance an order" / "create an invoice" than Guard-B prose.

**Embedding arm RUN — nomic-embed-text, same 93 queries:**

| Arm | embed MRR | embed R@1 | embed MeanRk |
|---|---|---|---|
| thin | **0.510** | **0.269** | 3.0 |
| guardb | 0.286 | 0.129 | 6.3 |
| oracle | 0.362 | 0.161 | 5.2 |

Guard-B harms **all 7 families** in embedding retrieval (−0.037 to −0.389 vs thin). No family
improves. Oracle harms 5 of 7. Pre-committed interpretation `f2_closed` applies:

**F2 is CLOSED across all three retriever types (BM25, TFIDF, embedding).**

The result is stronger in embedding than lexical: thin outperforms Guard-B by 0.224 MRR in semantic
search vs 0.079 in BM25. **Mechanism:** thin descriptions ("Get the order.", "Notify the customer.")
match queries at the intent level; Guard-B descriptions ("Returns order summary fields including
status, total, item count...") match at the implementation level. Underspecified queries operate at
the intent level — precision-optimized descriptions are a semantic mismatch regardless of retriever
type. This is a genuine, non-obvious finding: a description system designed to discriminate
within-family variants hurts retrieval when queries are coarse and intent-level.

The account_query BM25-neutral (−0.029) also does NOT hold in embedding (−0.148 HARM). No partial
F2 signal survives the full three-retriever picture.

Pre-committed interpretation applied: `f2_closed`. No further retriever testing. See consolidated
picture below.

---

**CONSOLIDATED P2-A + F2 PICTURE FOR GG (direction escalation):**

Three experiments, one proxy (synthetic internal-proxy, gemma2:9b, 31 contested tools):

**1. Direct selection (P2-A Phase 2A):**
- Fixer value is REAL but NARROW + LOW-STAKES: order_read 0%→100% (Guard-B and Oracle both).
  Return-shape disambiguation is description-fixable.
- High-stakes families (ticket_lifecycle permanence, invoice_write mutation-scope): 100% all arms.
  Task context resolves danger. Painkiller framing NOT supported.
- account_query HARM (−20pp, both Guard-B and Oracle): descriptions regress a family that thin
  descriptions already handled via name-task heuristic alignment.
- Stats: p=0.07 (underpowered, N=31). Directional, not confirmed.

**2. F2 retrieval — lexical (BM25 + TFIDF):**
- Thin descriptions outperform Guard-B on underspecified queries across both retrievers (5/7 families
  harmed). Mechanism: thin verb-noun patterns keyword-match short generic queries directly.
- NOT SUPPORTED.

**3. F2 retrieval — semantic (nomic-embed-text embedding):**
- Thin descriptions outperform Guard-B on ALL 7 families. Margin larger than lexical.
  Guard-B descriptions optimized for within-family discrimination are a semantic mismatch against
  intent-level queries.
- NOT SUPPORTED. F2 CLOSED.

**What the data says (factual, no positioning):** On this synthetic proxy, Guard-B descriptions
improve direct tool selection on one low-stakes family (order_read) and degrade it on one family
(account_query). They do not improve tool retrieval under any retriever type tested. The property
that makes Guard-B descriptions good at direct-selection discrimination (encoding the behavioral axis
precisely) is the same property that makes them poor retrieval targets for coarse intent queries.

Bringing to GG as a consolidated direction escalation. No new thesis proposed unilaterally.

---

## UX1 — Presentation + safety pass (DONE, PR #51)

**Scope:** CLI/UX changes only — engine (scoring/judge/generator/rubric/calibration) unchanged.
Not condition #1. Presentation and safety layer over the existing scan/fix engine.

**`agentgauge try <server>` — one-command first-touch flow:**
Run scan + fix-preview in a single read-only command. Prints the score table, prioritized fix
list, and an inline before→after for every accepted fix (colorized on TTY; `+/-` markers
otherwise). Ends with the exact `agentgauge fix <server> --apply` command. Never writes any
files. Verified by smoke: echo_server.py rendered score + inline diff for mystery/greet, git
status clean after.

**Non-destructive default — backup-before-write:**
`fix --apply` now ALWAYS writes `<file>.bak` before rewriting the target in place. If `.bak`
already exists, increments to `.bak.1`, `.bak.2`, etc. (never stomps). Backup path printed.
Eliminates the silent-clobber footgun. Smoke-verified: `.bak` checksum = original; second
`--apply` produced `.bak.1` with the first `.bak` intact.

**Inline before/after replaces the patch-file step:**
Each accepted fix renders old (red/`-`) → new (green/`+`) text inline in the console.
Degrades to plain `+/-` markers on non-TTY. `--out-diff` remains optional.

**Bug fixed (was pre-existing on main — apply-path source corruption):**
`_patch_source_description` used raw string splicing (`f'description="{new_desc}"'`) — a
generated description containing a double-quote (e.g. the smoke's `'The "mystery" tool...'`)
produced a `SyntaxError` in the patched file on `--apply`. Fixed: `repr(new_desc)` as the
replacement literal; lambda passed to `re.sub` so backslashes in the output are never
re-interpreted as escape sequences. Same lambda guard applied to `_patch_source_schema_props`
(where `json.dumps` can emit `\\n`/`\\t` that `re.sub` would misread as newlines). Three
regression tests added (`ast.parse` confirms the patched file parses for `"`, `\`, `\n` in
generated descriptions).

**Known limitation (not fixed — acceptable for common case):**
`_patch_source_schema_props` matches only empty `{}` parameter entries. A second `--apply`
will not re-refine already-filled schema props (`{"default": "Hello"}` is not empty, so the
regex skips it). The apply path is not idempotent for schema fixes. Fine for the primary use
case (one-shot improvement on a fresh server file).

**CI:** 553 tests, 93.74% coverage, ruff + mypy clean. Tests in `tests/test_ux1.py` (16) and
`tests/test_fixer.py` (+3 regression). No scoring/judge/rubric/calibration changes; all
550 prior tests pass unchanged.

---

## RW2 — Real-world experiment: AWS IAM MCP server (DONE, PR #49)

**Goal:** External validity on a second real server — does Guard-B recover selection accuracy
on AWS IAM's confusable policy-management families, and does the skip-above-band gate protect
already-passing tools from do-no-harm regression?

**Setup:** 29-tool mirror of the AWS IAM MCP server (`awslabs/mcp src/iam`, real docstrings,
stub bodies). 12 CONTESTED tools (Family A: attach/detach user/group — 4 tools; Family C:
list_* scope variants — 6 tools; Destructive pair: delete_user/role_policy — 2 tools);
14 THOROUGH tools (name-resolvable or richer docstrings). 3 DESTRUCTIVE_CONFUSABLE_PAIRS.
Judge: llama3.1:8b. Generator: qwen3:8b. Agent: gemma2:9b. 5 trials per arm.

**FINDING 1 — NO HEADROOM (2nd real server):**

Arm A (real AWS IAM docstrings) correctly selected the right tool for all 29 tasks:
**100.0% accuracy, including all 12 pre-registered contested tasks (Family A: all 4 correct,
Family C: all 6 correct, Destructive pair: both correct)**. PAINKILLER metric (wrong-DESTRUCTIVE
rate): 0% for both arms. Guard-B has nothing to recover.

The agent resolved every contested task from task context alone — AWS IAM's 1-sentence
docstrings ("Attach a managed policy to an IAM user.") are sufficient for gemma2:9b even on
the most confusable family (attach/detach × user/group, 4 tools sharing the same parameter set).

**Buyer bound confirmed across two servers (GitHub + AWS IAM, gemma2:9b):** Guard-B's
expected-value case is servers with thin, name-colliding, context-poor documentation — not
GitHub-class or AWS IAM-class servers. The buyer segment is the under-documented long tail.
Do not generalize beyond these two servers and this agent.

**FINDING 2 — SCORE-VALIDITY GAP (2 servers, confirmed):**

The discoverability scorer does NOT flag AWS IAM's contested families. Two separate failures:

*Heuristic wrong pairs:* The Levenshtein collision detector flags 4 pairs
(`attach_user_policy` ↔ `detach_user_policy`, `put_user_policy` ↔ `get_user_policy`, etc.) —
these are verb-antonym pairs, not cross-principal-type scope pairs. The 3 contested families
that cause actual agent confusion are NOT penalized by the heuristic.

*Judge DISTINGUISH:* Structurally cannot name the contested families. Real judge (5 trials,
llama3.1:8b): DISTINGUISH mean 6.67/10, blended score 68.7. **Mock-vs-real catch:** the
prior session scan result (70/100) came from `--mock` (MockProvider returns literal string "7"
→ judge output = 70/100 flat). The real judge gives 68.7. The gap is small but the
mechanism is important: any scan run with `--mock` produces a flat 70 regardless of catalog
quality, not a meaningful score.

**Implication (confirmed across GitHub + AWS IAM):** The DISTINGUISH metric requires a
per-pair confusability redesign before it can be used as a ranking signal for real servers with
prefix-sharing or principal-type-variant naming. This is a CONDITION #1 / judge-touching fix —
tracked as SCORE-FIX in FUTURE/DEFERRED.

**FINDING 3 — DO-NO-HARM REGRESSION (corrected + scoped):**

Phase 2 do-no-harm section: **2/14 THOROUGH tools regressed** (`get_user_policy`: 100% → 0%,
`get_group`: 100% → 0%). Initial post-Phase-2 framing suggested the skip-above-band gate (90.0)
would protect these tools in the real `agentgauge fix` CLI path. **This claim was verified and
found to be WRONG:**

- `get_user_policy`: baseline discoverability score = 82.0 → REGENERATE (below 90.0 threshold)
- `get_group`: baseline discoverability score = 82.0 → REGENERATE (below 90.0 threshold)

Only 4 of the 29 tools score at or above 90.0 (all at exactly 90.0):
`detach_user_policy`, `delete_user_policy`, `delete_role_policy`, `delete_user`.
The skip gate does NOT protect `get_user_policy` or `get_group`.

**Path distinction (important scope):** The stub→artifact regression fires ONLY in source-aware
code paths (Phase-1 harness, Q3/Q4/Q5/Guard-B paths that call `_generate_description` with
`scoped_source` and `guard_b=True`). The base `agentgauge fix` CLI path (default) uses
`_DESC_GENERATOR_PROMPT` — name + current description + input schema only, no source
reading — and CANNOT produce stub→artifact regressions. The regression is real in
source-aware mode; the base CLI path is unaffected.

**Stub→artifact mechanism:** When `scoped_source` is a stub/dispatcher body (e.g. the rw2
mirror's `_handle_get_user_policy()` returns a hardcoded JSON `{"user_name": ..., "tool":
"get_user_policy"}`), the generator describes what it sees — the JSON return value — not the
tool's semantic purpose. Result: "Returns a JSON string with a stub response containing the
user name and tool identifier." Technically accurate about the stub body; useless as a
description of what the real tool does.

**Mirror over-exposes the vulnerability:** All 29 rw2 mirror tools use uniform stubs. The real
AWS IAM MCP server has working implementations. The stub regression rate on a real deployment
(partial stubs, mixed real + stub bodies) is **unmeasured** — the regressions here reflect the
mirror's construction, not a confirmed property of the real server.

**Known gap, not fixed:** Thin-body detection (detecting stubs/dispatchers before generating
and abstaining or warning) is not implemented. The `is_low_grounding` guard fires on opaque
tool names, not on opaque tool bodies. A body-complexity heuristic or stub-pattern detector
is the candidate fix, but requires its own spec and pre-registration.

**Caveats — do not over-generalize:**
- Mirror artifact: stub→artifact regressions occur on all 29 tools because all 29 are uniform
  stubs. Real-server regression rate is unknown.
- Path specificity: only source-aware Guard-B paths are vulnerable; base `agentgauge fix` CLI
  is not.
- Two servers (GitHub + AWS IAM), one agent (gemma2:9b). All three findings are pending
  replication with a different agent or a live-API connection.

**CI:** verify.sh PASSED. 29-tool mirror, arm servers, Phase 1/2 scripts, and new CI tests —
all deterministic, no live API, no network calls.

---

## RW1 — Real-world experiment: GitHub MCP server (DONE, PR #48)

**Goal:** External validity — do the AgentGauge scores and Guard-B fixer predict and fix real
confusion on a real production MCP server (github/github-mcp-server)?

**Setup:** 21-tool mirror of the 162-tool GitHub MCP server (real docstrings from
`pkg/github/*.go`, real schemas, stub bodies, no live API). 5 confusable families, 21
anti-tautological tasks, 4 DESTRUCTIVE_CONFUSABLE_PAIRS. Judge: llama3.1:8b. Agent: gemma2:9b.
5 trials per arm. GPU-exclusive throughout.

**FINDING 1 — SCORE-VALIDITY GAP (most important finding):**

The discoverability scorer does NOT distinguish GitHub's historically-confusing families from
clean ones on real naming. Per-family DISTINGUISH scores were flat at 70/100 for every family;
overlap with GitHub's own hand-fixed families: **0/2** (pr_read_variants 70/100,
search_variants 70/100 — both above the 60-pt flagging threshold, neither flagged).

Heuristic detected the `get_pull_request_diff` ↔ `get_pull_request_files` name collision
(heuristic 85.0, judge 60.0, blend 75.0), but the judge's DISTINGUISH discriminator did not
differentiate the families GitHub themselves consolidated to reduce confusion.

**Implication for the product:** the discoverability dimension does NOT yet provide a reliable
"directory/gateway ranking signal" for real servers with prefix-sharing naming patterns.
The DISTINGUISH metric must be improved to model prefix-collision confusability before the
score is meaningful for ranking real MCP servers against each other. This is a
CONDITION #1 / judge-touching fix — its own gated task, not done here.

**FINDING 2 — BUYER BOUND (confirmed):**

Arm A (real GitHub docstrings) correctly selected the right tool for all 21 tasks:
**100.0% accuracy, 0/21 contested tasks**. Guard-B has nothing to recover.
PAINKILLER metric (wrong-DESTRUCTIVE-tool rate): 0% for Arm A — mathematical necessity given
100% accuracy.

**Implication for the product:** GitHub's real terse docstrings already saturate gemma2:9b.
The Guard-B fixer's value is in UNDER-documented servers — the long tail of hobby/internal
MCP servers with minimal or missing docstrings. GitHub-class servers self-serve; they are
not the buyer. This is consistent with Q3–Q6 where source-aware fixing recovered contested
tasks on servers without adequate documentation.

**Fixer limitation note:** 3/21 Guard-B descriptions degraded to stub language (generator
read stub body instead of docstring for `get_pull_request_files`, `list_commits`,
`list_repositories`). This is a real Guard-B limitation on mirror/stub servers, irrelevant
to the main finding since Arm A had no misses to recover, but relevant to any deployment on
servers whose bodies are stubs or thin wrappers.

**Caveats — do not over-generalize:**
- One server (github/github-mcp-server — among the best-documented MCP servers in the ecosystem).
- One agent model (gemma2:9b). A smaller or weaker agent might show headroom even on
  GitHub-class docs.
- "Score is invalid" is too strong: the score is invalid for the *ranking-signal use-case* on
  real prefix-sharing naming. Ordering and gap comparisons on synthetic catalogs (where naming
  is designed to test the dimension) remain valid.
- "Guard-B has no value" is too strong: the finding is scoped to well-documented servers.
  The under-documented long tail is the needed follow-up (RW2).

**CI:** verify.sh PASSED. 53 new deterministic tests, no live API, no network calls.

---

## Q6 — Do-no-harm (DONE, PR #47 merged)

**Verdict: SAFE TO RUN BLANKET on documented servers** (zero regressions on 11 already-passing
tasks including all 3 collision-prone pairs; contested recovery 6/6 preserved; harm mechanism
did not trigger). See full entry in **What is DONE** below.

---

## What AgentGauge is

AgentGauge is a CLI that scores how well an AI agent can use an MCP server. It connects to a server
(stdio subprocess or HTTP/SSE), introspects its tools, runs a real LLM agent against generated tasks,
and produces a weighted score across eight dimensions — plus a prioritised fix list. The aim is to be
the neutral, standard score for MCP interface quality: "Lighthouse / PageSpeed, but for MCP."

---

## Scoring dimensions (v1 — all implemented)

| Dimension            | Weight | Status        |
|----------------------|--------|---------------|
| schema_completeness  | 25%    | implemented   |
| description_quality  | 25%    | implemented   |
| discoverability      | 15%    | implemented   |
| selection_accuracy   | 15%    | implemented   |
| call_correctness     | 10%    | implemented   |
| error_legibility     | 5%     | implemented   |
| robustness           | 3%     | implemented   |
| docs_manifest        | 2%     | implemented   |

Overall score = weighted sum (0–100). JSON output via `--out report.json`; stable schema at
`schema_version: "1.0"`. Exit-code gate available as `agentgauge ci`.

**Judge model:** `llama3.1:8b` (pinned; see CLAUDE.md). Scores are NOT comparable across judge
models — always record the model alongside any stored score.

---

## What is DONE

- All eight scoring dimensions implemented and passing CI.
- `agentgauge scan` end-to-end: connects, introspects, scores, prints report.
- `agentgauge ci` subcommand: exits non-zero if overall score is below a threshold.
- JSON output (`--out report.json`) with stable `schema_version: "1.0"` schema.
- HTML output (`--out report.html`).
- Remote judge on GCP Cloud Run (`agentgauge-judge`, us-central1, NVIDIA L4) for when local VRAM is
  unavailable — proxy command in CLAUDE.md.
- Calibration runs completed for `error_legibility` and `discoverability` against `llama3.1:8b`
  (5 trials each, 2026-05-31). Results recorded in CLAUDE.md.
- `agentgauge fix` command (T9/T10/T11/T12): generates improved descriptions and schema metadata
  for low-scoring tools. Uses a configurable generator model (default: `qwen3:8b`, must differ from
  the judge) and validates each fix via deterministic re-score (schema_completeness) or an LLM-judge
  trial gate (description_quality). Schema fixes add type, description, and `required` arrays to each
  parameter; fixes are accepted only when the delta exceeds a configurable threshold. An over-marking
  guard prevents params with defaults from being added to `required`. Schema fixes are
  non-destructive: existing per-param keywords (`default`, `enum`, `minimum`, `format`, `items`,
  nested `properties`) are preserved; the generator's `type` and `description` overlay them without
  replacing the entire param schema. A cost pre-filter (`--skip-above-band`, default 90) skips
  generation entirely for tools already scoring at or above the band — these appear as SKIPPED with
  reason `already_above_band` and make zero generator calls. Emits a unified diff;
  `--apply` writes fixes back to the source file. Real-judge validation (T11) run against
  `llama3.1:8b` on `examples/echo_server.py` — results recorded in CLAUDE.md.
- **A/B ground-truth harness (T15/T16, PR #31):** `agentgauge/ab_harness.py` added — paired A/B
  harness with McNemar's test, A-vs-A noise floor, identical-task-set enforcement. Selection step
  in `runner.py` now presents tool descriptions + param types to the agent (not just names);
  manipulation-check CI-asserted (`test_selection_prompts_differ_between_vague_and_informative_descriptions`).
  **Finding (scoped to opaque-named tools):** on a fixture where tool names carry no semantic signal
  (`get_a`/`get_b`/`del_a`/`del_b`), qwen3:8b fabricated plausible-but-wrong descriptions (e.g.
  record-key param labelled "API key for authentication"). Two valid A/B runs both showed arm B ≤
  arm A on `selection_accuracy` (delta −10%, McNemar b=0 c=5). The heuristic/judge score can point
  opposite to agent behavior in this regime. This is NOT a general claim that the fixer harms —
  `schema_completeness` gains on `echo_server.py` (mystery/greet tools) stand as previously
  validated. H2 (`call_correctness`) was UNTESTABLE on this fixture/model: gemma2:9b saturated
  at 100% from training priors regardless of schema quality. Not a null — the agent didn't need
  schema guidance to construct valid calls. Candidate next steps in TASKS.md (Tx/Ty/Tz).
- **Tx (IN-REVIEW, branch `claude/tx-abstain-no-harm`):** Generator now abstains on
  low-grounding tool names (0 meaningful semantic tokens after stripping generic verbs and
  single-char suffixes). New `ABSTAINED` status in `FixReport`, distinct from
  ACCEPTED/REJECTED/SKIPPED. Degenerate-guard CI test prevents abstain-everything. Real-agent
  A/B results (gemma2:9b, 10 tasks x 5 trials):
  - **Harm gate (ObsStore):** PASS. Abstain fired on all 5 opaque tools; Arm B = Arm A = 70.0%
    selection (delta +0.0%); regression removed.
  - **Upside step 1 (grounded + oracle):** POSITIVE, pending reproduction. Oracle descriptions
    improved Arm B to 100% vs Arm A 80.0% (delta +20pp; McNemar b=10 c=0 chi2=8.10 p<0.05).
    Upside appears real on this fixture, BUT the only task with headroom was transform_normalize
    (0/5 arm A), and that task proved unstable run-to-run in step 2 (0/5 arm B in run 2).
    Result is directionally strong but not independently reproduced. Pending Tx-val re-run.
  - **Upside step 2 (grounded + fixer output):** NO TASK-LEVEL EFFECT. Two independent A/B runs
    with fixer output: run 1 showed +10pp (trial-level McNemar b=5 c=0, b+c=5); run 2 showed
    +0pp. Per-task breakdown reveals both runs had Arm A errors confined to transform_normalize
    tasks only (0/5 each); all other 8 tasks were 5/5 in both arms on both runs. Run 1's b=5
    flips were concentrated in the 2 normalize tasks and did not reproduce in run 2. Task-level
    sign test (task is the unit): discordant=0 in run 2; no task showed consistent improvement.
    Conclusion: no reproducible task-level upside demonstrated for fixer descriptions on this
    fixture. Powered re-run required (>=30 tasks, Arm A ~50-60%). Tracked as Tx-val in TASKS.md.
- **Ty (IN-REVIEW, branch `claude/ty-call-correctness`):** Two-run oracle A/B on
  `call_correctness`. CI: 268 tests, 89.61% coverage, all LLM mocked.
  **Run 1 (PRELIMINARY — floor-effect):** 32 tasks, 16 hard with arbitrary enum codes
  (ACQ_BURST/CODEC_R8 etc.). Hard-task Arm A = 0% by construction; aggregate 50% carried
  by 16 inert easy tasks. Sign test on contested tasks: n_plus=16, n_minus=0, p=0.0000.
  Technically POSITIVE but near-tautological (oracle supplied unguessable tokens; agent
  echoed them). Not evidence of reliability improvement where agent had partial ability.
  **Run 2 (FIXTURE FAILURE — partial-headroom design):** 30 tasks, all hard, mixed
  constraints (format patterns [A-Z]{2}[0-9]{2}/ERR[0-9]{3}, semi-conventional enums,
  non-standard units centiseconds/deciseconds). Stability screen: 0 dropped.
  Arm A baseline = 33.3% < 40% gate → STOP. No A/B comparison made.
  Format patterns and non-standard units proved harder for gemma2:9b than expected.
  **Combined verdict: ABORTED.** Cannot establish a partial-headroom regime with these
  constraint types for gemma2:9b. Schema quality in the call-construction stage remains
  untested in a genuine partial-ability regime. A design with more conventional constraints
  (standard integer ranges, familiar enum terms) is the candidate path to a non-tautological
  partial-headroom test, but requires a fresh pre-registration.
- **T17 (IN-REVIEW, branch `claude/t17-selection-limited`):** 8 confusable clusters (16 tools,
  32 pre-registered tasks). CI: 8 new tests pass (fixture integrity, stability-screen logic,
  manipulation check). Q1 oracle A/B (gemma2:9b, 2026-06-03): **ABORTED — fixture-quality,
  headroom 81.2% > 70% target. NOT a null result** (oracle was never run; no comparison made).
  Arm A resolved 81.2% correctly from names alone (all 32 tasks surviving stability screen);
  task-clustered oracle table not run per pre-registration.

  **Cross-run through-line (3 fixtures, no description-recoverable selection-limited regime found):**
  Every fixture to date has landed in one of two dead zones for gemma2:9b:
  - *Self-describing names* (run #1 — `transform_scale`, `transform_normalize`, etc.):
    agent picks from the name → Arm A saturated, no headroom.
  - *Verbose-domain names* (T17 — `search_documents`/`query_records`, `send_message`/
    `dispatch_event`, etc.): names are drawn from standard software vocabulary gemma2:9b
    has strong priors for → 81.2% from names alone, no headroom.
  - *Opaque names* (ObsStore — `get_a`/`get_b`/`del_a`/`del_b`): names carry no semantic
    signal, but descriptions cannot recover it either (fixer hallucinated plausible-but-wrong
    descriptions; real-agent A/B arm B ≤ arm A). No headroom AND not description-recoverable.

  Taken together: at T17's scale (16 tools, 8 clusters), no fixture design placed Arm A in
  the 40–70% headroom window. Standard API vocabulary saturated Arm A at 81.2%; opaque names
  showed no description-recoverable signal.

  **Update (T18, 2026-06-07): The confusable regime was found at catalog scale.** A 60-tool
  catalog (10 families × 6 near-neighbors) placed Arm A at 55.0% and oracle descriptions
  raised discrimination accuracy to 97.4% (+34.5 pp on parse-success calls). The through-line
  below applied at T17's scale; density was the missing variable, not a fundamental limit.

  **Implication (pre-T18):** `selection_accuracy` may be behaviorally description-insensitive
  for capable agents at small catalog sizes. A model either resolves the tool from its name
  (descriptions irrelevant) or the name is so opaque descriptions carry no useful signal.
  T18 showed this is scale-dependent: the description signal becomes necessary at 60 tools /
  10 families, where names alone cannot distinguish within-family variants. `discoverability`
  (15%) is validated for the regime it was designed for; the construct-validity concern from
  T17 is resolved for that dimension. `description_quality` (25%) remains untested in an
  analogous behavioral experiment. Design decision required — see TASKS.md.

**Cross-experiment meta-finding (selection T17 + calls Ty):** The 40–70% partial-ability
  window — where the agent has meaningful but imperfect ability in Arm A, leaving headroom
  for oracle Arm B to improve — has proved narrow and hard to construct for gemma2:9b across
  both dimensions tested:
  - *Selection (T17):* Agent resolves tool selection at 81.2% from names alone on domain
    vocabulary → Arm A above the 70% ceiling; no headroom.
  - *Calls (Ty Run 2):* Agent succeeds at only 33.3% in Arm A on format/unit constraints →
    below the 40% floor; still effectively a floor-effect regime.
  Both dimensions landed outside the target window on the first attempt and require fixture
  redesign to test. The window exists in principle but is sensitive to the agent's prior
  knowledge about the specific vocabulary used.

  **Candidate explanations to test next:**
  - *(a) Guessable-but-error-prone constraints:* Use constraints the agent "knows" but
    applies inconsistently — e.g., ISO date formats, HTTP status codes, standard SI units.
    These should land in the 40–70% zone because the agent has partial exposure but not
    perfect recall. Requires pre-registration and inferability guard.
  - *(b) Weaker runner agent:* gemma2:9b may simply be too capable for 9B-class schema
    vocabulary. A smaller model (e.g., gemma2:2b, phi3:mini) would have a lower knowledge
    floor and more constraint-sensitive behavior, potentially landing Arm A in range without
    fixture redesign. Trade-off: harder to generalize findings to production-grade agents.

  Which fork to take (another Ty attempt vs. weaker-agent pivot vs. write the meta-finding
  as the deliverable) is a design decision — tracked as open in TASKS.md.

- **T18 (IN-REVIEW, branch `claude/t18-discoverability-scale`):** Oracle A/B on `selection_accuracy`
  with a 60-tool confusable catalog (10 families × 6 near-neighbors). Arm A = empty descriptions;
  Arm B = oracle discriminating descriptions (each targets the within-family distinguishing
  dimension: source, scope, permanence, channel, computation type, etc.). 40 pre-registered tasks,
  5 trials per arm, gemma2:9b agent. GPU-exclusive run (watchdog-confirmed clean, 2026-06-07).

  **POSITIVE. First located behavioral effect for a description-facing dimension.**

  Decomposed result — the +40.0 pp aggregate contains two distinct effects:

  **Effect 1 — discrimination (parse-success calls only):**
  Arm A: 175/200 parse-success trials → 62.9% correct.
  Arm B: 195/200 parse-success trials → 97.4% correct.
  Discrimination delta: **+34.5 pp**. This is the gain from descriptions that target the within-family
  distinguishing dimension. On the 16 contested tasks (A=0%, B=100%): all 16 improved, none
  regressed. Sign test: n_plus=16, n_minus=0, ties=24, p=0.0000.

  **Effect 2 — parse stabilization (separate finding):**
  Parse-failure rate: A=12.5% (25/200) → B=2.5% (5/200). At 60-tool catalog density with empty
  descriptions, the model intermittently failed to produce a valid structured call at all — it
  selected nothing rather than the wrong thing. Oracle descriptions suppressed this. Mechanism:
  catalog ambiguity destabilizes call formation, not just tool selection. This contributes
  ~5–6 pp of the aggregate delta and is mechanistically distinct from the discrimination effect.

  **Scope — effect is on the confusable subset only:**
  16/40 tasks were contested (A=0%, B=100%). 22 tied at ceiling (A=100%, B=100%) — names alone
  were sufficient for these. 2 tied at floor (A=0%, B=0%) — ambiguous gold, not agent failure:
  `find_entries` competes with `lookup_data` (both exact-key lookup; task text doesn't specify
  backend), `book_slot` competes with `plan_event` (both calendar tools; "prevents double-booking"
  criterion is not cued by the task). The "+40 aggregate" should not be read as "+40 across all
  tool use" — the behavioral effect is entirely on the 16 confusable-but-discriminable tasks.

  **Cross-experiment map and scope:**

  | Experiment | Dimension | Verdict | Why |
  |------------|-----------|---------|-----|
  | T17 (16 tools, 8 clusters) | selection | **inert** — ABORTED above ceiling | names saturated Arm A at 81.2%; descriptions never tested |
  | Ty (call construction) | calls | **inconclusive** — ABORTED all runs | unguessable tokens → tautological; format/unit constraints → floor |
  | T18 (60 tools, 10 families) | selection | **POSITIVE** | density created the confusable regime; discrimination +34.5 pp |

  Effect is **scale-gated**: the confusable regime required 60-tool density. At T17's scale,
  standard API vocabulary was self-disambiguating. This is NOT a general claim that "descriptions
  help agents" — the effect is specific to large (≥60-tool) catalogs with real within-family
  semantic distinctions (source, scope, permanence, channel, computation type). `discoverability`
  (15%) is validated for the regime it was designed for. `description_quality` (25%) and
  `call_correctness` effects remain unestablished.

- **Q2a (DONE, PR #42, 2026-06-07):** Three-arm fixer recovery experiment on the T18 60-tool
  confusable catalog. Arm A (empty) / Arm F (fixer-generated, qwen3:8b per-tool, seed=42) /
  Arm O (oracle). Metric: parse-success `selection_accuracy` on 18 contested tasks (Arm A = 0%).
  Agent: gemma2:9b, 5 trials. GPU-exclusive (watchdog-confirmed clean throughout).

  **Result: LOW RECOVERY. Recovery fraction (F−A)/(O−A) = 0.125 (12.5%).**
  - Arm A: 0.0% | Arm F: 11.1% (+11.1 pp) | Arm O: 88.9% (+88.9 pp)
  - F-vs-A sign test: p = 0.5000 — **not significant**. Fixer adds no reliable discrimination.
  - F-vs-O sign test: p = 0.0001 — F is significantly below O (14 tasks F=0%, O=100%).
  - Parse-failed: 0/200 in all three arms (improvement over T18's 12.5% Arm A rate; within run-to-run variance).

  **Root cause (structural):** The generator receives one tool at a time — `{name, current_desc, schema}`.
  The T18-decisive distinctions are cross-tool: storage medium (cache vs SQL vs queue), operation
  scope (single-field vs full-record), permanence (soft vs hard delete), channel (mobile push vs
  SMS vs UI alert), directionality (HTTP push vs pull). None of these can be encoded without
  seeing sibling tools. All 14 misses were classified (i): cross-tool distinction only. With
  identical `{query: string}` schemas across all 60 tools, classification (ii) — per-tool schema
  gap — was impossible by construction; no per-tool signal existed to surface.

  **Liability finding:** On ≥2 tools the generator produced confidently wrong descriptions:
  `store_item` (in-memory cache with TTL) was described as "designed for **persistent** storage";
  `forward_record` (HTTP POST to external webhook) was described as "straightforward **record
  retrieval**". These mislead worse than empty descriptions — an agent reading them will
  actively pick the wrong tool. The Tx fabrication failure mode recurs on confusable catalogs.
  The 2 Arm F "successes" (`read_entry`, `alert_contact`) were name-overlap luck, not
  discrimination: "read" matched "entries" and "alert contact" matched "contact" in the task
  text, not genuine within-family disambiguation.

  **Product implication:** The `description_quality` fixer, as currently built (per-tool
  generation), does not deliver the validated T18 behavioral value and is net-negative on
  confusable tools due to confident mis-description. Delivering the T18 gain requires
  catalog-aware generation: the generator must see sibling tools when writing each description
  so it can explicitly encode the within-family distinguishing dimension. This is Q2b.

- **Q2b (DONE, PR #43, 2026-06-07):** Three-arm catalog-aware fixer recovery on the T18 60-tool
  confusable catalog. Neighbor selection: Jaccard token-overlap K=6, no family labels. Catalog-aware
  prompt with explicit NO-FABRICATION guard. Phase 1: qwen3:8b generator (GPU-exclusive, 600 s timeout
  for thinking mode). Phase 2: gemma2:9b agent, 40 tasks × 5 trials, GPU-exclusive (watchdog-confirmed
  clean throughout).

  Numbers: Arm A=0.0% / Arm F=11.1% (+11.1 pp) / Arm O=88.9% (+88.9 pp). Recovery fraction
  (F−A)/(O−A)=0.125. F-vs-A p=0.5000 (not significant). Parse-failed: A=0%, F=2.5% (5/200), O=0%.

  **Finding 1 — SAFETY (the win):** Under catalog-aware prompting — the condition that maximally
  enables fabricated distinctions, because the generator sees sibling tool names and is explicitly
  asked to encode within-family differences — the no-fabrication guard held. All four pre-registered
  ambiguous tool pairs (find_entries/lookup_data, book_slot/plan_event) received FAITHFUL descriptions:
  no invented distinctions. The guard fired correctly on `compute_metric` ("No meaningful difference
  from neighbors" — correct abstain, not fabrication). The generator stayed honest when it had the most
  license to lie.

  **Finding 2 — RECOVERY (information-theoretic, not a prompt gap):** Catalog-awareness recovered only
  12.5% of the T18 oracle gain — not significant (F-vs-A p=0.50). The cause is structural, not a
  context or prompt deficiency: the T18-decisive distinctions (storage backend, operation scope, delete
  permanence, notification channel) live in tool **behavior**, and are present in **neither** the tool
  names **nor** the identical `{query: string}` schemas. No generator can recover information the catalog
  does not contain. The oracle had it only because a human who knew the implementations supplied it
  directly. This result is confirmed across **two independent experiments** — Q2a (per-tool generator,
  12.5%) and Q2b (catalog-aware generator, 12.5%) — ruling out a per-tool context gap as the
  explanation.

  **Implication:** Closing the T18 discrimination gap requires an information source **beyond the tool
  interface** — the server's source code, docstrings, or README. Pure interface-text generation (names +
  schemas, with or without neighbor context) cannot encode distinctions that are absent from the
  interface. This bounds what AgentGauge's description fixer can achieve from the interface alone; the
  next meaningful step is source-level context injection, not prompt refinement.

- **Q3 (DONE, PR #44, 2026-06-07):** Source-aware description generation — confirmed the missing
  ingredient from Q2a/Q2b and defined the boundary condition for safe use.

  **Setup:** 12-tool fixture with real working implementations (TTL store, raise-on-dup, audit-log
  append, archived/retired/hidden flags, del statement). Two source conditions — F-DOC (source +
  docstrings) and F-BODY (source body only, docstrings stripped). 6 genuine contested tasks
  (1 control task excluded — see Control note below). gemma2:9b agent, 5 trials/arm, GPU-exclusive.

  **RECOVERY axis — source closes the T18 gap.**
  F-DOC: 83.3% recovery (5/6 contested tasks correct, sign test n+=5, n-=0, **p=0.0625 marginal**).
  This confirms Q2a/Q2b's diagnosis: the T18 ceiling was information-theoretic — the distinguishing
  facts were absent from the interface. Source supplies them. The fixer's effective input is the
  server's **repo (source + docstrings)**, not the running server's tool list. That is the
  architectural boundary this experiment establishes.

  F-BODY recovery: numerically 83.3% but invalidated by fabrication — see Safety axis.

  **SAFETY axis — two outcomes, one new failure mode.**
  F-DOC no-fabrication: **PASS** (4/4 control descriptions FAITHFUL; find_entries/lookup_data and
  book_slot/plan_event both correctly classified as equivalent). Source-aware generation with
  docstrings is safe.

  F-BODY no-fabrication: **FAIL**. find_entries generated: "differs from lookup_data by using
  _search_store **instead of the _db**" — false; both functions use `_search_store`. This is a new
  failure mode: **cross-tool source misattribution**. The generator correctly read find_entries'
  implementation but misattributed a backing store (`_db`) seen in *other* tools in the file to the
  confusable neighbor lookup_data. The fabrication is grounded-sounding (cites a real symbol from the
  source file) and structurally plausible, making it harder to catch than prose fabrication that
  invents non-existent concepts. This failure mode is created by source-access itself — the context
  includes neighboring implementations, and without docstrings to anchor each tool's true behavior,
  the generator cross-contaminates.

  **BOUNDARY — the product takeaway: documented source is required.**
  Docstrings are load-bearing for **both** axes:
  - *Recovery:* BODY-only missed the retire_data "read-only" distinction (in the docstring, absent
    from the body) and the archive/remove multi-way disambiguation. Body-only fails on semantically
    equivalent-looking flag operations (`_records[q]["x"] = True`).
  - *Safety:* BODY-only opened the cross-tool source misattribution failure mode that DOC-only closed.
  On undocumented servers, source-aware fixing is unsafe as built. The fixer should not be applied to
  source without docstrings.

  **Control note:** control_search task excluded from recovery statistics. The F-BODY fabrication on
  find_entries created a self-contradictory description pair that confused the agent (F-BODY=0% on
  that task — fabrication did not produce accidental solvability). The F-DOC=100% on the same task
  reflects an asymmetric anchor in the lookup_data F-DOC description ("functionally equivalent to
  find_entries") rather than a genuine behavioral distinction. No-fabrication is established for
  **F-DOC only** (F-BODY is disqualified by the fabrication finding).

- **Q4 (DONE, PR #45, 2026-06-08):** Scoped-source description generation — per-tool function
  extraction to eliminate Q3's cross-tool source misattribution. Four-arm A/B: A (empty) /
  Q4-DOC-scoped / Q4-BODY-scoped / O (oracle). 12-tool Q3 fixture reused. qwen3:8b generator
  (Phase 1, GPU-exclusive). gemma2:9b agent, 5 trials/arm, GPU-exclusive (watchdog-confirmed clean
  throughout). 383 tests, 90% coverage — verify.sh green.

  **HEADLINE — safety inversion: docstrings are a liability in the scoped regime.**

  Scoping eliminates Q3's cross-tool `_db` misattribution in **both** conditions — neither cites
  `_db`; the Q3 failure mode is gone by construction. But a new fabrication vector opens when
  docstrings are present: the generator reads the target's precise scoped body, reads a neighbor's
  imprecise docstring, and invents a false distinction. Concretely: `find_entries`' body returns
  `{len(matches)} result(s)` (a count-format string); `lookup_data`'s neighbor surface shows
  docstring `"Return all entries"`. The generator concludes find_entries returns a count while
  lookup_data returns the actual entries — false; both return identical count strings. Result:
  Q4-DOC-scoped FABRICATED on 4/4 control pairs.

  **This reverses Q3's whole-file lesson.** In the whole-file regime, docstrings were safer
  (they aligned vocabulary with behavior and prevented cross-tool body misattribution). In the
  scoped regime, the cross-tool body risk is already eliminated; docstrings then become the
  fabrication source by exposing a docstring-body vocabulary gap.

  | Regime | With docstrings | Without docstrings |
  |--------|----------------|--------------------|
  | Whole-file (Q3) | **SAFE** — vocabulary anchors each tool, prevents body misattribution | **UNSAFE** — foreign body symbols contaminate (`_db` misattribution) |
  | Scoped (Q4) | **UNSAFE** — docstring-body gap is exploitable for fabrication | **SAFE** — no foreign bodies, no misleading neighbor docstrings |

  **Deployment implication (not a test artifact):** The Q4-DOC-scoped failure fires on any real
  MCP server whose docstring English is less precise than its code. "Return all entries" is a
  docstring that could describe either function; the body's return format makes one look different
  in isolation. This is not a fixture quirk — it is the normal condition for real servers whose
  docstrings summarise intent rather than format. The BODY-scoped path sidesteps this by
  stripping neighbor docstrings; both the scoped target body and the neighbor def-lines are
  the only signals in the assembled prompt.

  **No-fabrication results:**

  | Condition | Control pairs | Classification | Result |
  |-----------|--------------|----------------|--------|
  | Q4-DOC-scoped | find_entries, lookup_data, book_slot, plan_event | FABRICATED (4/4) | **FAIL** |
  | Q4-BODY-scoped | find_entries, lookup_data, book_slot, plan_event | INCIDENTAL-BUT-TRUE (4/4) | **PASS** |

  Q4-DOC-scoped failure mechanism: semantic inference against docstring-body gap (not body symbol
  misattribution). Q4-BODY-scoped pass: neighbor surfaces are bare def lines only; no misleading
  docstring vocabulary to infer against.

  **Recovery — full on the Arm-A-failure subset (with caveats).**

  Six structural contested tasks: `store_item`, `persist_row`, `write_entry`, `delete_record`,
  `retire_data`, `remove_entry` (tasks where Arm A parse-success = 0% in both Q3 and Q4 runs).
  Both Q4-DOC-scoped and Q4-BODY-scoped reached 100% on all 6. sign test: n=6, n+=6, n-=0,
  **p=0.0313** — significant at α=0.05.

  **Caveats on the recovery number:**
  - *control_search excluded* — the 7th Arm-A=0% task (`find_entries`, "Retrieve the records where
    the key contains 'invoice-2024'") is an ambiguous-equivalent pair where `lookup_data` is equally
    valid. The gold label is `find_entries` (arbitrary pre-registration; either tool is correct). Arm
    A scored 0/5 because it consistently preferred `lookup_data` by name. Including it would inflate
    recovery by scoring an arbitrary label; Q3 excluded it for the same reason (Arm A happened to
    pick `find_entries` ≥1/5 that run). Excluded here for comparability.
  - *2 structural tasks untested for description effect* — `save_record` and `archive_item` were not
    contested (Arm A > 0% on both). Whether descriptions help those tasks is unknown.
  - *No formal stability pre-screen* — contested set is this run's post-hoc A=0% output. The same 6
    tasks were A=0% in both Q3 and Q4 independent runs; that cross-run consistency is informal
    evidence of genuine difficulty, not a formal pre-screen.

  **Verdict: Q4-BODY-scoped is the first condition both fully-recovering and safe.**

  | Condition | Recovery (n=6 failure subset) | p | No-fabrication |
  |-----------|-------------------------------|---|----------------|
  | Q3 F-DOC | 83.3% | 0.0625 (marginal) | **PASS** |
  | Q3 F-BODY | 83.3% (invalidated by fabrication) | — | **FAIL** (_db misattribution) |
  | Q4-DOC-scoped | 100% | 0.0313 | **FAIL** (docstring-body inference) |
  | **Q4-BODY-scoped** | **100%** | **0.0313** | **PASS** |

  Q4-BODY-scoped beats Q3 F-DOC on both axes (full vs. 83.3% recovery; same safety standard).
  The scoped+body-stripped path is the recommended configuration for source-aware fixing:
  target's own function body only, neighbor surfaces as bare def lines.

  **Architectural change:** `fixer.py` — `_extract_scoped_function`, `_extract_function_surface`,
  `_DESC_GENERATOR_SCOPED_SOURCE_PROMPT`, extended `_generate_description` with `scoped_source`
  and `neighbor_surfaces_text` params. CI: 383 tests, 90% coverage, 18 new tests in
  `tests/test_q4_scoped.py` asserting scoped extraction, body-exclusion guarantee, prompt
  composition, and priority ordering.

- **Q5 (DONE, PR #46, 2026-06-08):** Distinction guard (Guard B) — target-grounded phrasing,
  docstrings kept. Four-arm A/B: A (empty) / Q4-DOC-scoped (reference) / Q5-guarded / O (oracle).
  12-tool Q3 fixture reused. qwen3:8b generator (Phase 1, GPU-exclusive). gemma2:9b agent,
  5 trials/arm, GPU-exclusive (watchdog-confirmed clean throughout). 397 tests, 90% coverage —
  verify.sh green.

  **HEADLINE — Guard B closes the Q4 deployment question: documented source is now safe.**

  Guard B prompt instructs the generator to state distinctions ONLY as positive facts about the
  TARGET grounded in its own body, and explicitly forbids "unlike X, which does Y" comparative
  claims. Neighbor surfaces (signature + docstring) are still shown — to indicate which axes may
  discriminate — but may not be cited to assert a neighbor's behavior. The no-fabrication guard
  plus the target-grounded example pair eliminate the Q4-DOC-scoped failure mode without discarding
  the docstring signal.

  **No-fabrication results (4 equivalent-control pairs, human classification):**

  | Condition | Control pairs | Classification | Result |
  |-----------|--------------|----------------|--------|
  | Q4-DOC-scoped | find_entries, lookup_data, book_slot, plan_event | FABRICATED (4/4) | **FAIL** |
  | **Q5-guarded** | find_entries, lookup_data, book_slot, plan_event | INCIDENTAL-BUT-TRUE (4/4) | **PASS** |

  Q4-DOC-scoped fabrication mechanism: generator read target's precise body, read neighbor's
  imprecise docstring, and inferred a false distinction (e.g., "differs from lookup_data by
  returning a count instead of the actual entries" — both return identical count strings). Q5
  eliminated all 4 fabrications by removing the asymmetric-evidence inference path.

  **Recovery — full on the 6 structural contested tasks:**

  | Condition | Recovery (n=6 structural) | p | No-fabrication |
  |-----------|--------------------------|---|----------------|
  | Q3 F-DOC | 83.3% | 0.0625 (marginal) | PASS |
  | Q3 F-BODY | 83.3% (invalidated) | — | FAIL |
  | Q4-DOC-scoped | 100% | 0.0313 | FAIL |
  | Q4-BODY-scoped | 100% | 0.0313 | PASS |
  | **Q5-guarded** | **100%** | **0.0313** | **PASS** |

  Q5 = Q4-DOC on recovery AND safe. No structural contested task where Q5 missed that Q4-DOC
  passed — no over-suppression failure. Guard B is non-regressing.

  **Source-aware generation progression:**
  - Q3 (whole-file): DOC safe (83.3% recovery, marginal) / BODY unsafe (cross-tool body misattribution)
  - Q4 (scoped): DOC fabricates via docstring-body gap / BODY safe but discards docstring signal
  - **Q5 (scoped + Guard B): DOC safe AND 100% recovering — the shippable config**

  **Deployment answer:** Documented source can now be fixed safely. The fixer's source-aware path
  (`guard_b=True`) is production-viable for real MCP servers with docstrings. No need to strip
  docstrings.

  **Detector gap (diagnostic, not a safety net):** The `_contains_comparative_neighbor_claim()`
  regex catches "unlike/whereas/while/compared to \<neighbor\>" but misses "differs from \<neighbor\>
  by…" — the dominant Q4-DOC fabrication phrasing. It caught only 1/4 Q4-DOC fabrications (book_slot
  via "while plan_event"). On Q5, detector and human reading agree (0/4). The detector is a tripwire
  only: safety verdict rests on human classification.

  **Ambiguous-task finding (strongest argument for the guard):** On control_search (genuinely-equivalent
  pair, arbitrary gold label), Q4-DOC scored 100% by FABRICATING a false asymmetry that accidentally
  hit the gold label; Q5 scored 0% by correctly refusing to invent a distinction. Implication: on
  ambiguous tools, fabrication can INFLATE measured recovery — a faithful generator scores LOWER there
  precisely because it is honest. This is why control_search is excluded from the pre-registered 6,
  and it is the clearest illustration of why the guard matters.

  **Architectural change:** `fixer.py` — `_DESC_GENERATOR_GUARD_B_PROMPT` constant,
  `_contains_comparative_neighbor_claim()` detector, `guard_b: bool = False` kwarg on
  `_generate_description()`. CI: 397 tests, 90% coverage, 14 new tests in `tests/test_q5_guarded.py`
  asserting prompt content, detector correctness (5 cases), and MockProvider routing.

- **Q6 (DONE, PR #47, 2026-06-08):** Do-no-harm on already-passing tasks — is Guard-B safe to run
  blanket across a full documented MCP server?

  **Setup:** Extended fixture to 23 tools (12 Q3 + 11 new already-passing): 5 non-collision tools
  (compress_file, hash_value, parse_date, count_words, generate_token) and 3 collision-prone pairs
  (list_active_users/list_active_sessions, close_ticket/close_request, reset_pin/reset_password).
  Each pair documented with why names disambiguate and why target-only descriptions might collapse.
  qwen3:8b generator, seed=42 hardcoded (Phase 1, GPU-exclusive). gemma2:9b agent, 5 trials,
  two Arm A stability runs + one Guard-B run, GPU-exclusive (watchdog-confirmed clean throughout).
  432 tests, 90% coverage — verify.sh green.

  **Inverted gate:** For Q6, Arm A at/near 100% on already-passing tasks is the PRECONDITION (not
  the abort). The metric is PASS→FAIL regression count, not recovery fraction.

  **Section B — Headroom precondition:** 11/11 already-passing tasks stable across both Arm A runs
  (run1=run2=100% on all 11). 0 tasks dropped by stability screen. Precondition: MET.

  **Section C — Regression (zero):**

  | Tool | Family | A% | Guard-B% | Status |
  |------|--------|----|----------|--------|
  | compress_file | non-collision | 100% | 100% | OK |
  | hash_value | non-collision | 100% | 100% | OK |
  | parse_date | non-collision | 100% | 100% | OK |
  | count_words | non-collision | 100% | 100% | OK |
  | generate_token | non-collision | 100% | 100% | OK |
  | list_active_users [C1] | collision_c1 | 100% | 100% | OK |
  | list_active_sessions [C1] | collision_c1 | 100% | 100% | OK |
  | close_ticket [C2] | collision_c2 | 100% | 100% | OK |
  | close_request [C2] | collision_c2 | 100% | 100% | OK |
  | reset_pin [C3] | collision_c3 | 100% | 100% | OK |
  | reset_password [C3] | collision_c3 | 100% | 100% | OK |

  **REGRESSIONS: 0.** Do-no-harm holds on all 11 already-passing tasks including all 3 collision-prone pairs.

  **Section D — Contested check:** 6/6 structural contested tasks recovered (Arm A=0% → Guard-B=100%).
  Sign test: n+=6, n-=0, p=0.0312.

  **Section E — Net effect:** Arm A=63.2% → Guard-B=100.0%, delta +36.8%. Headline sign test
  on contested tasks only (control_search excluded — find_entries/lookup_data are equivalent tools,
  gold label is arbitrary, same exclusion as Q3–Q5): n+=6, n-=0, p=0.0312.

  **MECHANISM (bounds the claim):** No regression occurred because qwen3:8b's honest Guard-B
  descriptions RETAINED a distinguishing token for every collision pair:
  - C1 (list_active_users/list_active_sessions): `_user_store` vs `_session_store`, "users" vs
    "sessions" (description common-prefix 28 chars, below collapse threshold).
  - C2 (close_ticket/close_request): "support ticket"/`_ticket_store` vs "service request"/
    `_request_store` (common-prefix 9 chars — clearly distinct).
  - C3 (reset_pin/reset_password): "PIN"/"0000"/`_pin_store` vs "password"/"changeme"/
    `_password_store` (common-prefix 12 chars — clearly distinct).

  Total description-collapse to identical phrasing did NOT trigger. Therefore **harm-via-collapse
  is UNTESTED on this run, not ruled out.** The safe-to-blanket claim holds for documented servers
  where honest descriptions remain semantically distinct. It is consistent with — but does not
  prove — safety under total description collapse (a condition requiring Q7 to test).

  **Verdict: SAFE TO RUN BLANKET on documented servers (no observed regression; harm mechanism
  did not trigger).** Guard-B can be applied to any tool in a documented MCP server where honest
  descriptions stay semantically distinct. Not an unconditional safety claim — servers where Guard-B
  collapses to identical phrasing for sibling tools are outside the tested scope.

  **Source-aware generation progression (complete):**

  | Condition | Recovery (n=6) | p | No-fabrication | Blanket-safe |
  |-----------|---------------|---|----------------|-------------|
  | Q3 F-DOC | 83.3% | 0.0625 | PASS | — |
  | Q3 F-BODY | 83.3% (invalidated) | — | FAIL | — |
  | Q4-DOC-scoped | 100% | 0.0313 | FAIL | — |
  | Q4-BODY-scoped | 100% | 0.0313 | PASS | — |
  | Q5-guarded | 100% | 0.0313 | PASS | untested |
  | **Q6-guarded (23 tools)** | **100%** | **0.0312** | **PASS** | **YES (documented servers)** |

- Test suite: 432 tests, 90% coverage, all LLM calls mocked — CI runs with no network and no credentials.

## What is NOT built yet

- **CI action** beyond `agentgauge ci`: a GitHub Actions action that installs and runs AgentGauge
  inside a user's own CI workflow.
- **Hosted dashboard**: per-server history, regression alerts, subscription tier.
- **≥30B judge re-calibration**: config change (`CALIBRATED_JUDGE_MODEL` in `cli.py`) + re-measure.
  No rebuild required; blocked on access to a ≥64 GB host. Tracked in TASKS.md under FUTURE/DEFERRED.

---

## Autonomy setup

The repo is configured to be driven by a **Claude Code cloud scheduled task**. Each autonomous run:
1. reads `.claude/operator-prompt.md` from `main` to get its instructions,
2. picks the single highest-priority TODO from TASKS.md with clear acceptance criteria,
3. implements on a `claude/<task>` branch, runs `./scripts/verify.sh`, and opens a PR.

**Merge policy: all PRs are DRAFT.** There is no auto-merge allowlist; every PR opened by the
autonomous loop requires human review before merging. Three categories of task especially warrant
careful review beyond CI green:
1. Touches the LLM judge (rubric prompts, scoring logic, calibration constants, blending weights).
2. Generates fixes or actions against real servers or live APIs.
3. Acceptance criteria require measuring calibration or comparing real-model outputs.

**Current status: ACTIVE — idle.** The scheduled task runs daily at approximately 03:35 UTC. The
TASKS.md TODO queue is currently empty, so each run takes the idle path: writes a `BLOCKER.md` and
opens a draft blocker PR. All PRs opened by the loop are DRAFT; there is no auto-merge. The loop
will pick up real work automatically when a new TODO item is queued with clear acceptance criteria.

---

## Hard-won lessons

**Mock-green ≠ correct.** In T1, T2, T3, T5, and T6, tests passed while the real judge behavior
was wrong — selection logic, scoring logic, or rubric response parsing was broken in ways the mocks
didn't catch. Every judge-touching dimension required a real-model spot check before the score could
be trusted. Do not treat a green CI as validation of judge output quality; treat it as validation of
the code path.

**Judge dimensions need a real-model spot check before trust.** Run
`scripts/validate_error_judge.py` (ad hoc) or the discoverability equivalent against real
`llama3.1:8b` output when you change scoring logic. VRAM contention (< 5 GB free) silently
degrades results — always check `ollama ps` first, or use the GCP Cloud Run proxy.

**All PRs are DRAFT — the human merges.** Task descriptions in TASKS.md or commit messages do not
confer merge eligibility. No autonomous run may call `gh pr merge` or push directly to main.
