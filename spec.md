# spec.md — Ty2: call_correctness, guessable-but-error-prone constraints (last fixture attempt on gemma)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ d138369 ·
**Branch:** `claude/ty2-guessable-constraints`
**Routing:** DRAFT PR (conservative policy). Draft-forcing #2/#3. NOT condition #1.

**This spec, committed at branch start, IS the pre-registration.** Fixture, gold calls, oracle
schemas, headroom target, constraint band, and analysis plan are fixed before the run, not edited after.

---

## Why this run, and why it is the LAST fixture attempt on gemma2:9b

Ty aborted twice: Run 1 (arbitrary enums) -> Arm A hard = 0% (floor, tautological — oracle just
hands over an unguessable token). Run 2 (exotic formats/units) -> 33% (floor, too hard). Neither hit
the partial-ability band. The ONLY untested band is **guessable-but-error-prone**: constraints where
CONVENTION gives the agent a noisy prior it gets right SOMETIMES and wrong OFTEN. That is the only
regime where a positive delta means "schema improves the RELIABILITY of a partially-capable agent"
(the real product claim) rather than "schema supplies a fact that exists nowhere else" (Run 1's
near-tautology).

**Pre-registered contingency:** if a well-targeted guessable band still cannot land contested Arm A
in 40-70%, this experiment ABORTS and the conclusion is that the partial regime is unreachable by
fixture design on gemma2:9b. That abort triggers the WEAKER-AGENT construct-validity test (own spec)
— NOT a fourth gemma fixture. Do not rebuild on gemma again after this.

## The constraint band (design core)

Constraints must be GUESSABLE-BUT-ERROR-PRONE: the agent's conventional prior is right part of the
time, wrong part of the time. Not arbitrary (Run 1 floor), not exotic (Run 2 floor), not obvious
(ceiling). Candidates:
- **Near-miss enums:** plausible-English values that aren't the agent's first guess
  (status="settled" not "completed"/"done"; priority="P1" not "high"; visibility="unlisted" not
  "private"). Agent often picks a synonym the schema rejects.
- **Format-precision:** a field the agent gets approximately right but mis-specifies — e.g. requires
  full RFC3339 with timezone offset where the agent often emits a naive date; a code the schema
  pins (HTTP 301 vs 302, currency as ISO-4217 "USD" not "$").
- **Unit-magnitude:** real SI conventions where the agent sometimes uses the wrong magnitude
  (grams vs kg, ms vs s) — partially right.
- **Commonly-omitted required field:** a required arg with a conventional name the agent forgets
  ~half the time (idempotency_key, api_version).

Target: each contested task is one where gemma, with only Arm A's vague schema, succeeds ~40-70% of
the time. Arm B's oracle schema states the exact member/format/unit/required so reliability can rise.

## Anti-tautology + inferability (refined for this band)

- The task states INTENT or CATEGORY only, never the exact value (no copying). Convention supplies a
  noisy signal; the oracle schema supplies the exact requirement.
- Inferability CI test (refined): the EXACT correct value must not appear in the task text or param
  name (so Arm B isn't lookup), BUT the value must be CONVENTIONALLY PLAUSIBLE (so Arm A isn't floor).
  Assert the first half in CI; justify the second half per-task in the fixture doc.

---

## Scope

**IN:** a guessable-constraint fixture (Arm A vague schema; Arm B oracle); powered, stability-screened
contested task set; oracle A/B on `call_correctness` via the T15 harness. Selection trivially easy
(one obvious tool/task) so the only measured variable is call well-formedness.

**OUT:** the fixer / generated schemas (downstream, only if positive); weaker-agent swap (the
contingent NEXT experiment, own spec); rubric/scorer changes; inert easy padding tasks (drop them —
Run 1's 16 easy tasks polluted the aggregate; keep at most a tiny sanity control, excluded from
headroom and the test).

## Rigor (unchanged from T17/Ty)

- Headroom: contested Arm A `call_correctness` ~40-70%, measured on CONTESTED tasks only (not padded).
  CONFIRM before interpreting. Outside the band (either direction) -> ABORT per contingency above.
- Stability pre-screen: run Arm A twice; drop tasks flipping >1 trial; report count.
- Power: >= 30 contested surviving tasks. Task-clustered analysis (sign/Wilcoxon on task-level
  deltas), NOT trial-level McNemar; report effective N = contested (non-tied) tasks.
- Manipulation check: Arm A vs Arm B schemas differ in the served listing (assert).
- Agent = gemma2:9b, != judge != generator. call_correctness deterministic. `_is_correct_call`
  must reward the SPECIFIC correctness (right member/format/unit/required), across the band — not a
  single exact-string match on one field.
- No post-hoc tuning after seeing results.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** fixture loads; one gold call per task; stability-screen
   logic; manipulation check; inferability test (exact value absent from task text + param name);
   gold-validity (each gold value is a valid member of its oracle constraint). No real model in tests.
2. **Real-agent oracle A/B (manual, in PR description):**
   - Pre-checks FIRST: contested Arm A in 40-70% and stable, N>=30 contested, manipulation pass.
     If Arm A is outside 40-70% -> STOP, report ABORT + recommend the weaker-agent pivot. Do not interpret.
   - Task-clustered table: Arm A, Arm B(oracle), per-task delta, sign/Wilcoxon, effective N.
   - Honest verdict:
     - POSITIVE (oracle > A): schema quality improves call reliability for a partially-capable agent
       — the first located behavioral effect for a description-facing dimension. -> fixer-realization
       experiment next, on this fixture.
     - NULL (oracle ~ A): even when partially capable, gemma's call reliability is schema-insensitive
       — strong construct-validity finding across both selection and calls.
3. scorer.py / judge / rubrics / calibration / generator untouched; verify.sh green; coverage >= 60%.

## Housekeeping

- TASKS.md: Ty2 (TODO -> IN-REVIEW). STATUS.md: record the measured result precisely. If ABORT,
  record that the partial regime is unreachable by fixture design on gemma2:9b and queue the
  weaker-agent construct-validity test as the next item.
