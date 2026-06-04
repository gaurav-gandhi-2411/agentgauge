# spec.md — Ty: Does description/schema reduce malformed CALLS? (call_correctness)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 54f8593 ·
**Branch:** `claude/ty-call-correctness`
**Routing:** DRAFT PR (all PRs are DRAFT — conservative policy). Draft-forcing #2/#3 (real agent vs
served server, measured deltas). **NOT condition #1** — adds a fixture + task set + an oracle A/B; no
judge/scorer/rubric/calibration/generator changes.

**This spec, committed at branch start, IS the pre-registration.** Fixture, gold calls, oracle
schemas, headroom target, and analysis plan are fixed before the run and not edited after.

---

## The question

Selection turned out to be description-insensitive for a capable agent (run #1, ObsStore, T17): the
agent picks the right tool from the name. Ty tests the next behavioral stage: once the right tool is
selected, does a good description/schema reduce MALFORMED CALLS (wrong enum, wrong format/units,
missing/!wrong required args)? This is where description_quality + schema_completeness are most
likely to actually bite. Oracle schema = upper bound of what any fix could achieve.

## The headroom wall (primary design constraint — read first)

`call_correctness` saturated at 100% on EVERY prior fixture because gemma2:9b builds valid args from
convention (op="mean", ISO dates, obvious types). A fixture where schema info CAN help must require
information the agent CANNOT guess from convention or param names. Otherwise it aborts at the
headroom gate exactly like T17 (which died at 81.2% selection). Design the calls to need:
- **Arbitrary enums:** valid value is a non-semantic token set, e.g. mode in ["xR2","xR7","xR9"] —
  NOT "fast"/"slow"/"mean" which the agent guesses.
- **Non-standard units/formats:** e.g. timestamp in centiseconds-since-boot (not epoch/ISO); weight
  in grams with a 0-1000 bound; an ID format like "Z-####-Q".
- **Required fields with no conventional default:** a mandatory arg the agent won't supply unless told.
- **Inferability check:** for each, confirm the value is genuinely NOT derivable from the param name,
  the task text, or common API convention. If gemma can guess it, it doesn't create headroom.

Arm A (vague/empty schema) must therefore cause genuine call FAILURES; Arm B (oracle schema) supplies
the non-guessable info.

## Anti-tautology guard

Do NOT phrase the task so it states the enum value / format directly (that tests copying, not schema
use). The agent must get the constraint from the SCHEMA, not the prompt. Tasks describe intent; the
schema carries the machine-level requirement.

---

## Scope

**IN:** a call-correctness fixture (Arm A vague schema; Arm B oracle schema with correct
enums/formats/units/required); a powered, stability-screened task set; the oracle A/B on
`call_correctness` via the T15 harness.

**OUT:** the fixer / generated schemas (downstream Q2, only if oracle is positive); `selection_accuracy`
(answered — insensitive); rubric/scorer changes; other dimensions.

## Fixture design

- 6-10 tools, each with at least one call-critical constraint from the categories above. The CORRECT
  selection must be easy (don't reintroduce the selection problem) — single obvious tool per task —
  so the only variable measured is whether the CALL is well-formed.
- Arm A: vague/empty parameter schemas (type only, or missing constraints) — realistic sloppy server.
- Arm B: ORACLE schema — correct enum members, format/unit descriptions, required flags. Committed up front.
- Gold call per task: the exact correct arguments (tool + arg values). call_correctness is scored
  deterministically against this. Document, per tool, WHICH constraint is non-guessable and why.

## Rigor (carry forward T17's lessons)

- Headroom: target Arm A call_correctness ~40-70% (real room; not saturated). CONFIRM before
  interpreting — this is the gate that killed T17; expect it to be the hard part here too.
- STABILITY pre-screen: run Arm A twice; DROP tasks whose success flips by >1 trial; report count.
  If too many drop -> fixture-quality failure, report, don't proceed.
- Power: >= 30 surviving tasks. Analysis CLUSTERED BY TASK (sign test / Wilcoxon on task-level
  deltas), NOT trial-level McNemar.
- Manipulation check: Arm A vs Arm B schemas differ in the served listing (assert).
- Agent = gemma2:9b, != judge (llama3.1:8b) != generator (qwen3:8b). call_correctness deterministic.
- No post-hoc tuning of fixture, gold calls, or oracle after seeing results.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** fixture loads; each task has exactly one gold call;
   stability-screen drop logic works on a synthetic flaky case; manipulation check holds (Arm A vs B
   schemas differ); an inferability unit test asserts at least one constraint is absent from both the
   param name and the task text. No real model in committed tests.
2. **Real-agent oracle A/B (manual, in PR description — the deliverable):**
   - Pre-checks reported FIRST: Arm A ~40-70% call_correctness and stable (post-screen), N>=30
     surviving, manipulation pass. If headroom is wrong or too many drop -> STOP and report
     (fixture-quality), do not interpret.
   - Task-clustered table: Arm A, Arm B(oracle), per-task delta, sign/Wilcoxon result.
   - Honest verdict on the pre-registered branch:
     - POSITIVE (oracle > A): schema info reduces malformed calls — description_quality/
       schema_completeness have real behavioral headroom on CALLS. -> Tx-val / a fixer-realization
       experiment should run on THIS fixture.
     - NULL (oracle ~ A): gemma builds correct calls without the schema even when info is
       non-guessable -> the dimensions are behaviorally inert on calls too; combined with the
       selection finding, a foundational result about the score's construct validity.
3. scorer.py / judge / rubrics / calibration / generator untouched; verify.sh green; coverage >= 60%.

## Housekeeping

- Promote Ty into TASKS.md TODO with this spec referenced (makes it the one eligible item if the
  scheduled task fires — but it's draft-forcing, so it would force DRAFT, not auto-anything).
- STATUS.md: record the measured Ty result (positive or null) precisely; claim nothing beyond it.
