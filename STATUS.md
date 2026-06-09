# AgentGauge — Project Status

> Current as of 2026-06-09. Update this file when significant milestones land.

---

## RW1 — Real-world experiment: GitHub MCP server (IN-REVIEW, branch `claude/rw1-github-mcp`)

**Goal:** External validity — do the AgentGauge scores and Guard-B fixer predict and fix real
confusion on a real production MCP server (github/github-mcp-server)?

**MEASURED RESULTS (2026-06-10, judge llama3.1:8b, agent gemma2:9b, 5 trials):**

*Part 1 — Score validity:*
- Heuristic: 85.0/100; detected `get_pull_request_diff` ↔ `get_pull_request_files` name collision
- Judge (llama3.1:8b, 3 trials): full catalog DISTINGUISH = 60.0/100 (σ²=0.00); per-family all 70.0/100
- Blend: 75.0/100
- **Overlap with GitHub hand-fixed families: 0/2** (pr_read_variants scored 70/100, search_variants
  scored 70/100 — both above the 60-pt flagging threshold)
- **VERDICT: SCORE-VALIDITY GAP** — the discoverability scorer does NOT flag the same families
  GitHub's own engineers consolidated. The judge scores every family at 70/100 regardless of
  whether it was historically confusing. Not an indictment of scoring on synthetic servers —
  the real-world naming patterns (shared `get_pull_request_` prefix, terse descriptions) apparently
  do not trigger the judge's DISTINGUISH discriminator.

*Part 2 — Fix value:*
- GPU: exclusive throughout; 0/105 parse-failed in all three arms
- **Arm A accuracy (real GitHub docstrings): 100.0%, 0/21 contested tasks**
- **VERDICT: NO HEADROOM / BUYER-BOUNDED** — Arm A (real GitHub docstrings) correctly selected
  the right tool for all 21 tasks. Guard-B has nothing to recover.
  PAINKILLER metric implied: 0% wrong-DESTRUCTIVE-tool rate for Arm A (mathematical necessity).
- Phase 1 note: 3/21 Guard-B descriptions degraded to stub language (generator read stub body
  instead of docstring: `get_pull_request_files`, `list_commits`, `list_repositories`) — a
  real Guard-B limitation, but irrelevant since Arm A had no misses to recover.

**Joint interpretation:** Both findings are consistent. GitHub's real terse docstrings are
sufficient for gemma2:9b — the agent is not confused even by the highly confusable families
(5 PR read tools with identical schemas, terse "Get the X of a pull request" descriptions).
Guard-B adds value on POORLY-DOCUMENTED servers (Q3–Q6 finding stands). The discoverability
scorer's DISTINGUISH metric may not capture the name-collision confusability that humans find
problematic on prefix-sharing tool families.

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
