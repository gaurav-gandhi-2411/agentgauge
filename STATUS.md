# AgentGauge — Project Status

> Current as of 2026-06-07. Update this file when significant milestones land.

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

- Test suite: 328 tests, 90.32% coverage, all LLM calls mocked — CI runs with no network and no credentials.

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
