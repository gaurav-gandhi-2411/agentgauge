# spec.md — T15/T16: Ground-truth A/B — does a fix make a real agent better?

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 2d2d616 ·
**Branch:** `claude/ab-ground-truth`
**Routing:** DRAFT PR. Trips draft-forcing #2 (runs a real agent against a served MCP server) and
#3 (acceptance requires comparing real-model outputs / measured deltas). NOT in `AUTO_MERGE_TASKS`.
Harness code is CI-testable with mocks; the A/B RESULT is the human-reviewed artifact.

**This spec, committed at the start of the branch, IS the pre-registration.** Do not edit the
hypothesis, metric, or threshold after seeing results.

---

## Why this is make-or-break

Every prior increment proved the fixer raises a *heuristic/judged score* on a fixture. None proved
the thing the product sells: that a fix makes a **real agent complete tasks better** against the
server. This increment measures the behavioral delta in `selection_accuracy` and `call_correctness`
(real agent picks the right tool, calls it with right args) between the original server and the
fixed server. If the score does not predict this, the score is theater.

## The null result is a valid outcome — protect it

A capable agent may already infer intent from a bad description, making the fix behaviorally
worthless even when the score jumps. If so, that is THE finding: the score does not predict agent
success on this fixture. Rules:
- Pre-register hypothesis + threshold here, before the run.
- Paired design, fixed task set, fixed seeds, pre-specified metric. No peeking-and-adjusting.
- Do NOT tune the fixture, the fixer, or the agent prompt to turn a null into a positive. Report
  null or negative deltas as-is. A manufactured positive is worse than a real null.

---

## Hypotheses (pre-registered)

- H1: fixed server raises `selection_accuracy` by > noise floor.
- H2: fixed server raises `call_correctness` by > noise floor.
- Noise floor = the A-vs-A delta from re-running the SAME (original) server twice with different
  seeds. Threshold to claim an effect: delta > max(noise_floor, a fixed minimum TBD-in-code).
- Learn criterion: if delta ≈ 0 or negative on a capable agent, do not bury it — diagnose whether
  (a) the agent was saturated (bad description still guessable) or (b) the score measures the wrong
  thing. Both are first-class product findings.

---

## Scope

**IN:**
- Paired A/B harness over `runner.py`: arm A = original server, arm B = fixed server (diff applied),
  identical task set and seeds, N tasks x K trials.
- A held-out, REALISTICALLY-degraded fixture server (see Fixture) — NOT echo_server, which the fixer
  was tuned on and which is a softball.
- Metric computation reusing the existing `selection_accuracy` / `call_correctness` definitions,
  computed IDENTICALLY on both arms (confirm from code first), plus a paired statistic and the
  A-vs-A noise floor.
- Pre-registered result table: per-metric A, B, delta, noise floor, verdict.

**OUT:**
- Real third-party / live-API server (next increment — the external-validity check).
- Frontier-agent headline number (costs API spend — escalate separately).
- Remaining dimensions.

---

## Design

- **Agent model ≠ judge ≠ generator.** Judge is llama3.1:8b, generator qwen3:8b. The runner agent
  MUST be a third family (e.g. gemma2 or mistral; confirm it fits 8 GB VRAM via `ollama`). Sharing a
  family contaminates the test — a fix tuned to please a model class, tested by a kin model.
- **Confirm how selection_accuracy / call_correctness are scored** (read runner.py + scorer.py
  first). If deterministic (check chosen tool/args vs the task's gold), good — no judge involved.
  If any LLM scoring is used, it must be the SAME pinned scorer on both arms so it cancels.
- **Apply-the-fix mechanism:** produce arm B by applying the fixer's emitted diff to a copy of the
  fixture source, then serve it. The ONLY difference between A and B is the advertised tool metadata;
  task set, seeds, agent, and scoring are identical.
- **Fixture (held-out):** start from well-formed tools, apply realistic degradations — vague verbs,
  dropped param descriptions, missing `required`, ambiguous names — calibrated to a MEDIOCRE real
  server, not a cartoon. It must NOT be tuned against the fixer's behavior. Document each degradation
  and the pre-registered expected direction. This is a MECHANISM check; it is not sufficient for the
  enterprise claim (that needs the real-server follow-up).
- **Stochasticity:** N tasks x K trials, same seeds across arms. Report paired delta with a CI or a
  paired test (McNemar for binary task success; Wilcoxon signed-rank for scores). Establish the
  noise floor from A-vs-A before interpreting A-vs-B.

---

## Acceptance criteria

1. **CI (deterministic, mocked agent, seed 42, no network):**
   - Paired harness runs both arms over a fixed task set; metric deltas computed correctly against a
     mock agent with scripted tool choices (e.g. mock gets a tool right under arm B's schema, wrong
     under arm A's) — assert the delta and the paired stat are computed correctly.
   - A-vs-A on the mock yields zero delta (noise floor sanity).
   - Arms differ ONLY in served metadata — assert task set + seeds identical across arms.
2. **Real-agent A/B (manual, in PR description — the actual deliverable):**
   - Run on the held-out fixture with a third-family agent. Report the pre-registered table:
     selection_accuracy and call_correctness for A, B, delta, noise floor, paired-stat verdict.
   - State the outcome honestly: effect / null / negative. If null or negative, include the
     (a)-vs-(b) diagnosis. Do NOT adjust anything to chase a positive.
3. scorer.py rubrics/calibration untouched; runner agent ≠ judge ≠ generator (asserted);
   verify.sh green; coverage >= 60%; committed tests use a mock agent.

---

## Task breakdown

- **T15** — paired A/B harness: arm runner, identical-task/seed enforcement, metric deltas, noise
  floor, paired stat. Fully CI-testable with a mock agent. (draft via #3, but CI-provable)
- **T16** — held-out fixture server + apply-diff-to-serve wiring + the real-agent A/B run producing
  the pre-registered result. (draft-forcing #2 + #3; human-reviewed)

---

## Validity condition (pre-registration refinement, 2026-06-02)

**A run is VALID only if arm A scores ≤ 80% on at least one metric.** A run where arm A is
saturated near 100% on ALL metrics is VOID — the instrument could not detect an effect — and must
not be reported as a null about the thesis. A VOID run must be described as a ceiling effect, not
as evidence that the fix has no behavioral impact.

**Run #1 was VOID (TaskTracker fixture, 2026-06-02):** arm A scored 100% on both selection_accuracy
and call_correctness. Root cause: parameter names (`title`, `task_id`, `priority`, `due_date`) carry
enough semantic signal for gemma2:9b to infer correct types without schema metadata. The fixer did
raise the heuristic/judge score; the effect just doesn't show in agent behavior on obviously-named
parameters.

Secondary finding (recorded, not suppressed): schema metadata appears redundant for capable
LLMs when parameter semantics are unambiguous. This is a product-relevant boundary condition — the
score predicts agent difficulty on genuinely ambiguous schemas, not on semantically transparent ones.

**Run #2 (current run):** redesigned fixture (`ObsStore`) with opaque tool names (`put_x`,
`get_a`, `get_b`, `del_a`, `del_b`), confusable tool pairs with identical arm-A descriptions
("Get." / "Del."), and 10 pre-specified tasks describing intent without naming the tool. Validity
check is REQUIRED before interpreting A-vs-B: confirm arm A ≤ 80% on at least one metric first.

---

## Known limits (state them)

- The held-out fixture is hand-degraded; it tests the MECHANISM, not external validity. The
  enterprise claim requires the real-third-party-server follow-up (next increment).
- A local third-family agent establishes the effect cheaply; the headline number customers will
  weigh needs the real target agent class (frontier / Claude), which is API spend — escalate.
- Run #1 (VOID): gemma2:9b saturated on semantically obvious parameter names. The effect of the
  fix on agent behavior is untested until a valid (arm A ≤ 80%) run is completed.

## Housekeeping

- TASKS.md: add T15, T16. STATUS.md: do NOT add any "fixes improve real agent performance" claim
  until the A/B result supports it; record the measured delta (including null) instead.
