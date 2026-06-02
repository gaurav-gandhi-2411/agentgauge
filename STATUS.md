# AgentGauge — Project Status

> Current as of 2026-06-02. Update this file when significant milestones land.

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

  Taken together: there is no fixture design tested so far where (a) names are ambiguous enough
  that gemma2:9b cannot pick correctly from them, AND (b) descriptions contain recoverable
  signal that would close the gap. The middle regime — confusable names where descriptions
  disambiguate — may not exist for this model class on standard API vocabulary.

  **Implication:** `selection_accuracy` may be behaviorally description-insensitive for
  capable agents. A model either resolves the tool from its name (and descriptions are
  irrelevant) or the name is so opaque that descriptions carry no useful signal either.
  `description_quality` (25%) and `discoverability` (15%) are measuring something that does
  not appear to move agent behavior on selection for gemma2:9b. This is a construct-validity
  concern for these dimensions, not just a fixture-design failure. Design decision required
  before any re-run — see TASKS.md.
- Test suite: 236 tests, 89.61% coverage, all LLM calls mocked — CI runs with no network and no credentials.

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

**Current status: PAUSED.** The TASKS.md TODO queue is empty; there is no eligible work for the
scheduled task to pick up. The autonomy infrastructure is in place and will resume when new TODOs
are queued.

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
