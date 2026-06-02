# spec.md — T17: Selection-limited fixture — does description-help exist at all?

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ a4652b5 ·
**Branch:** `claude/t17-selection-limited`
**Routing:** DRAFT PR. Draft-forcing #2/#3 (real agent vs served server, measured deltas).
**NOT condition #1** — adds a fixture + task set + an oracle A/B run; no judge/scorer/rubric/
calibration/generator changes. NOT in `AUTO_MERGE_TASKS`.

**This spec, committed at branch start, IS the pre-registration.** Fixture clusters, gold mappings,
oracle descriptions, headroom target, and analysis plan are fixed before the run and not edited after.

---

## What this tests (and what it is NOT)

This is a CONSTRUCT-VALIDITY test of the description-facing score dimensions, not a fixer test. The
question: when an agent is GENUINELY selection-limited (the tool name alone is insufficient to pick
correctly), does a best-possible (ORACLE) description improve `selection_accuracy`? The oracle is the
upper bound of what any description-fix could ever achieve. If the oracle does not move selection
here, no fixer can, and `description_quality` (25%) + `discoverability` (15%) are measuring something
behaviorally inert for this agent class.

The fixer is deliberately EXCLUDED (oracle-only). The fixer cannot generate a disambiguator from an
ambiguous-name + empty-description — the information is not in the source to recover (the same wall
the agent hits). Whether the fixer can realize description-help where the info IS recoverable from
the tool definition is Q2 — a separate downstream experiment, only worth running if Q1 is positive.

## Why CONFUSABLE, not opaque or obvious (the design core)

Three regimes; prior runs each hit a different one:
- Self-describing names (run #1): agent picks from the name -> no headroom.
- Opaque names (ObsStore get_a): no disambiguating signal exists anywhere -> unfixable, hallucination-bait.
- CONFUSABLE (this fixture): names are individually plausible but ambiguous between candidates; the
  disambiguator legitimately lives in the description. The only regime where description_quality is
  supposed to matter.

## Anti-tautology guard (read before building the fixture)

Do NOT build clusters where the description trivially IS the answer, or where the task text lexically
echoes the oracle description — that re-derives "text the agent can read helps" by fiat. The real
question is whether gemma2:9b ATTENDS TO and USES a description to disambiguate when names are
ambiguous, vs picking by name lexical-match regardless (what it did on easy tasks). So:
- Task phrasing must NOT copy oracle-description vocabulary; phrase tasks by user intent.
- The null (oracle does NOT beat Arm A even here -> gemma ignores descriptions when it needs them)
  is a FIRST-CLASS outcome. Report it straight; do not adjust the fixture to force a positive.

---

## Scope

**IN:** a confusable-cluster fixture (Arm A realistically-vague descriptions; Arm B oracle
descriptions); a powered, stability-screened task set; the Q1 oracle A/B on `selection_accuracy`
using the existing T15 harness.

**OUT:** the fixer / generated descriptions (Q2, downstream); `call_correctness` (Ty); rubric/scorer
changes; the other dimensions (discoverability shares this premise and is implicated by the result,
but is not separately run here).

## Fixture design

- 6-10 confusable CLUSTERS, each 2-3 tools whose names are individually plausible for overlapping
  intents but only one is correct per task; the disambiguator lives only in the description (e.g.
  search/query/lookup; list/enumerate; send/post/dispatch). Real-server-plausible, not gibberish.
- Arm A: realistically-vague or empty descriptions (what a sloppy real server ships) -> the agent
  must guess among the cluster.
- Arm B: ORACLE descriptions -- factual, correct, what a careful author writes. Committed up front.
- Gold mapping: each task -> exactly one correct cluster member. Document, per cluster, WHY the name
  is ambiguous (the headroom mechanism) and the pre-registered expected direction.

## Rigor (carry forward every lesson)

- Headroom: target Arm A selection_accuracy ~50-60% (real room for an effect; not 80% boundary, not
  saturated). Confirm before interpreting.
- STABILITY pre-screen: run Arm A twice; DROP any task whose success flips by >1 trial; report how
  many dropped. (This is the normalize-instability fix that burned Tx step 2.) If too many drop,
  that's a fixture-quality failure -- report, don't paper over.
- Power: >= 30 surviving tasks. Analysis CLUSTERED BY TASK (task is the unit; trials are repeated
  measures): sign test / Wilcoxon on task-level deltas, NOT trial-level McNemar.
- Manipulation check (already CI-asserted in the harness): Arm A vs Arm B prompts differ.
- Agent = gemma2:9b, != judge (llama3.1:8b) != generator (qwen3:8b). selection_accuracy is
  deterministic (no LLM scorer in the loop). Assert agent identity.
- No post-hoc tuning of fixture, gold, or oracle after seeing results.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** fixture loads; each task has exactly one gold member;
   the stability-screen drop logic works on a synthetic flaky-task case; the manipulation check holds
   (Arm A vs Arm B prompts differ given the two description sets). No real model in committed tests.
2. **Real-agent Q1 oracle A/B (manual, in PR description -- the deliverable):**
   - Pre-checks reported FIRST: Arm A ~50-60% and stable (post-screen), N>=30 surviving tasks,
     manipulation check pass.
   - Report the task-clustered table: Arm A, Arm B(oracle), task-level delta, sign/Wilcoxon result.
   - Honest verdict on the pre-registered branch:
     - POSITIVE (oracle > A): description-help EXISTS in the selection-limited regime. The
       description dimensions have real behavioral headroom here. -> Tx-val should be re-pointed to
       THIS fixture, and Q2 (fixer realizes it) becomes the next experiment.
     - NULL (oracle ~ A): gemma ignores descriptions even when provably selection-limited ->
       foundational finding: description_quality/discoverability are behaviorally inert for this
       agent class on tool selection. Report it; do not engineer around it.
3. scorer.py / judge / rubrics / calibration / generator untouched; verify.sh green; coverage >= 60%.

## Housekeeping

- TASKS.md: add T17. If Q1 POSITIVE, update Tx-val to run on the T17 fixture (not easy tasks) and
  queue Q2 (fixer-realization on an info-recoverable variant). If NULL, record the construct-validity
  finding in STATUS.md against description_quality + discoverability.
- STATUS.md: record the measured Q1 result (positive or null) precisely; claim nothing beyond it.
