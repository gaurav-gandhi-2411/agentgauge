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
- Test suite: 89.35% coverage (210 tests), all LLM calls mocked — CI runs with no network and no credentials.

## What is NOT built yet

- **T15/T16 A/B ground truth (in-review, PR #31 open):** Paired A/B harness (`ab_harness.py`)
  implemented. Four real-agent runs completed with gemma2:9b (2026-06-02). Run log:

  **Run #1 (TaskTracker) VOID — ceiling.** Arm A 100%/100%. Parameter names semantically obvious.
  **Run #2 (ObsStore v1) VOID — broken manipulation.** Runner showed only tool names in selection
    prompt; arms A/B had identical inputs. Not a null — same experiment twice. Fixed in runner.py.
  **Run #3 (ObsStore v1, runner fixed) VOID — ceiling.** Arm A selection 90% (> 80%). Param names
    `rid` vs `op` distinguished tools without descriptions. arm B was WORSE (70%) — not interpretable.
  **Run #4 (ObsStore v4, identical {sid,key} params) VALID — NEGATIVE result on H1.**
  - selection_accuracy: A=70% B=60% delta=-10% McNemar b=0 c=5 — arm B WORSE than arm A
  - call_correctness:   A=100% B=100% delta=0% — H2 UNTESTABLE (arm A saturated)

  **Genuine thesis finding (runs #3 and #4 both valid, both B ≤ A):**
  The fixer's description improvements do not improve — and in two valid runs, actively hurt —
  selection accuracy when tool names are opaque. Root cause: the fixer (qwen3:8b) generates
  semantically wrong descriptions when names like `get_a`/`get_b` give no semantic signal.
  Fixer described `get_a.key` as "API key for authentication" instead of "record key." These
  inaccurate descriptions confused the agent more than the terse arm A descriptions.

  **Conditional finding:** fixer description quality is reliable when tool names or existing schemas
  carry enough signal for the generator to infer purpose; it degrades to hallucination on opaque names.

  **Do NOT claim "fixes improve real agent performance."** Neither valid run supports this.
  H2 (call_correctness) is UNTESTABLE on this fixture/model — gemma2:9b saturated at 100%.
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

**Auto-merge allowlist** (in `.claude/operator-prompt.md`): `AUTO_MERGE_TASKS = [T3, T4, T7]`.
This list is the ONLY grant of unattended merge — task descriptions in TASKS.md do not confer
auto-merge eligibility. Any task not in the list gets a DRAFT PR.

**Three conditions that force DRAFT regardless of the allowlist:**
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

**The allowlist is the ONLY grant of auto-merge.** Task descriptions in TASKS.md or commit messages
do not confer eligibility. If a task ID is not in `AUTO_MERGE_TASKS`, it gets a DRAFT PR regardless
of how mechanical the change looks.
