# spec.md — Q2a: does the CURRENT fixer recover the T18 discrimination gain?

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ fa766c9 (T18 merged) ·
**Branch:** `claude/q2a-fixer-recovery`
**Routing:** DRAFT PR. Draft-forcing #2 (fixer generates against the catalog) + #3 (real-agent A/B).
**NOT condition #1** — uses the existing fixer/generator unchanged; no scorer/judge/rubric/
calibration changes.

**Pre-registration:** this spec is committed at branch start. The metric (recovery fraction on
parse-success contested tasks) and the analysis are fixed before the run.

---

## What Q2a tests

T18 established that ORACLE discriminating descriptions recover +34.5pp (62.9% -> 97.4%, parse-success
contested tasks) in the 60-tool confusable catalog. Q2a asks the product question: does AgentGauge's
OWN fixer, as currently built, produce descriptions good enough to recover that gain? I.e. does our
tool move the dimension we just validated.

## Structural hypothesis (from code, to be measured not assumed)

`_DESC_GENERATOR_PROMPT` is invoked PER TOOL with only {name, current, schema} of that single tool.
The generator never sees sibling tools, so it cannot know WHAT distinction to encode. T18's oracle
power came from cross-tool distinctions (HTTP-vs-DB-vs-cache source, insert-vs-upsert, single-field-
vs-replace). Prediction: the per-tool fixer recovers LITTLE — UNLESS a given distinction happens to
live in that tool's own schema (param name/type), which the generator can surface. Q2a measures the
recovery fraction and DIAGNOSES which distinctions were recoverable per-tool vs only cross-tool.

## No headroom-gate risk

Unlike T17/Ty/T18, the regime is already validated: Arm A ~63%, oracle ~97% on parse-success
contested tasks. Q2a measures where the FIXER lands on that ruler. There is no abort gate — every
outcome is interpretable.

---

## Scope

**IN:** reuse the T18 fixture UNCHANGED (60-tool catalog, families, 40 tasks). Generate descriptions
with the CURRENT fixer (per-tool prompt, generator qwen3:8b). Three-arm A/B on selection_accuracy.
Diagnose unrecovered tasks.

**OUT:** any change to the fixer/generator (that is Q2b, contingent on this result); new fixtures;
call_correctness; scorer changes.

## Design — three arms, sequential GPU

- **Arm A** = empty descriptions (T18 Arm A, reference floor).
- **Arm F** = the FIXER's generated descriptions (run current fixer over the catalog; persist output).
- **Arm O** = T18 oracle descriptions (reference ceiling).
- Metric: parse-success selection_accuracy on the 16 CONTESTED tasks (where the effect lives).
  Report **recovery fraction = (F - A) / (O - A)** plus absolute F.
- Agent = gemma2:9b (!= judge != generator). Generator = qwen3:8b (NOTE: this is the 8B generator,
  NOT qwen3:30b which was the GPU contaminator — different model).
- **Phase separation for GPU safety:** (1) generate all Arm F descriptions with qwen3:8b, persist to
  a file; (2) `ollama stop`; (3) run the 3-arm A/B with gemma2:9b ONLY. The A/B-phase watchdog kills
  on ANY non-gemma model. This keeps generation and evaluation from contending and keeps the watchdog
  rule simple. Identify/silence the qwen3:30b reactive requester before launching (prior contamination).

## Diagnosis (required, the point of Q2a)

For each contested task where Arm F < Arm O (fixer failed to recover):
- Show the fixer's generated description for the gold tool.
- State whether it encodes the distinguishing feature T18's oracle used.
- Classify WHY it missed: (i) the distinction is cross-tool only (generator couldn't know it
  per-tool) -> motivates Q2b catalog-aware generation; or (ii) the distinction WAS in the tool's own
  schema but the generator didn't surface it -> a prompt/generation-quality gap, not a context gap.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** the three-arm wiring works with a MockProvider
   (Arm F sourced from a persisted descriptions file); recovery-fraction computation correct;
   contested-subset + parse-success filtering correct. No real model in committed tests.
2. **Real-agent 3-arm (manual, in PR description):**
   - GPU exclusivity FIRST (gemma-only during A/B; report any eviction). parse_failed per arm.
   - Table: Arm A / Arm F / Arm O on parse-success contested tasks; recovery fraction; task-clustered
     sign test F-vs-A and F-vs-O.
   - Diagnosis breakdown (i vs ii) across unrecovered tasks.
   - Honest verdict:
     - HIGH recovery (F ~ O): the current fixer works at scale — the product claim closes
       (dimension validated AND tool moves it).
     - LOW recovery (F ~ A): per-tool generation can't encode cross-tool distinctions -> Q2b
       (catalog-aware generator) is the warranted next increment; the diagnosis says so explicitly.
     - PARTIAL: report which distinction types recovered (schema-encoded) vs not (cross-tool only).
3. scorer.py / judge / rubrics / calibration untouched; generator != judge asserted; verify.sh green;
   coverage >= 60%.

## Housekeeping

- TASKS.md: Q2a (TODO -> IN-REVIEW). STATUS.md: record the recovery fraction + diagnosis. If LOW/
  PARTIAL, queue Q2b (catalog-aware description generation) with this diagnosis as its motivation.
