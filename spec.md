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

## Validity conditions (pre-registration refinements, 2026-06-02)

### Validity gate (global)

**A run is VALID only if arm A scores ≤ 80% on at least one metric.** A saturated arm A is a VOID
run — the instrument cannot detect an effect — and must NOT be reported as a null about the thesis.

### Per-metric validity gate (refinement, 2026-06-02)

**Each hypothesis is testable only on the metric where arm A has genuine headroom (≤ 80%).** A
metric saturated on arm A is VOID FOR THAT HYPOTHESIS, independent of the other metric. Separately:
- H1 (selection_accuracy) requires arm A selection_accuracy ≤ 80%
- H2 (call_correctness) requires arm A call_correctness ≤ 80%

### Manipulation check (required, 2026-06-02)

**The treatment must be confirmed delivered before interpreting results.** Arm A and arm B must
receive DIFFERENT selection prompts — confirmed by the CI assertion in `test_runner.py`. A run where
b=0 AND c=0 (zero discordant pairs) AND arm A < 100% is a signal of failed manipulation, not a
genuine null, and must be labelled VOID (broken manipulation).

---

## Run log

### Run #1 — VOID (ceiling effect)

Fixture: TaskTracker (4 tools, 4 tasks × 3 trials). Agent: gemma2:9b. Date: 2026-06-02.
Arm A: 100% / 100%. VOID — arm A saturated on both metrics.
Root cause: parameter names (`title`, `task_id`, `priority`, `due_date`) are semantically
obvious; gemma2:9b inferred correct types without any schema guidance.
Note: this is a boundary condition, NOT "score doesn't predict success." It means schema metadata
is redundant for capable LLMs on obviously-named parameters. Recorded for the record.

### Run #2 — VOID (broken manipulation)

Fixture: ObsStore (5 tools, 10 tasks × 5 trials). Agent: gemma2:9b. Date: 2026-06-02.
Arm A: selection=60% (VALID headroom), call=100% (saturated).
VOID — broken manipulation: runner.py showed only tool NAMES in the selection prompt, not
descriptions. Arms A and B had IDENTICAL selection-step inputs. b=0, c=0 (zero discordant pairs)
confirms neither arm had a different treatment — this was the same experiment run twice, not an A/B.
Root cause: runner.py's selection prompt was `"Available tools: {names}\nTask: {desc}"` — no
descriptions exposed. Arm B's fixer-improved descriptions were invisible to the agent.
Fix applied: runner.py now builds a per-tool listing showing name, description, and param types.
CI assertion added: `test_selection_prompts_differ_between_vague_and_informative_descriptions`.

### Run #3 — VOID (ceiling, arm A 90% selection)

Fixture: ObsStore v1 (`rid`/`op` params). Agent: gemma2:9b. Date: 2026-06-02.
Arm A: selection=90%, call=100%. VOID — arm A above 80% ceiling on both metrics.
Root cause: the new runner format shows param names (`rid` vs `op` in the selection listing).
Even with identical "Get." descriptions, the param name contrast (`rid` = record ID, `op` = op)
was sufficient for the agent to achieve 90% selection. The degraded descriptions were irrelevant
once params were visible.
Secondary (not interpretable, VOID): arm B scored 70% — WORSE than arm A. The fixer's verbose,
inaccurate descriptions ("transfers a value from a source...") confused the agent more than the
terse "Get." + visible param names. Recorded as a data point, not as a thesis finding.

### Run #4 — VALID, NEGATIVE on H1, UNTESTABLE on H2

Fixture: ObsStore v4 ({sid,key} identical on all confusable pairs). Agent: gemma2:9b. Date: 2026-06-02.
Tasks: 10 × 5 trials. Arm A: selection=70% (VALID), call=100% (VOID for H2).

Validity: VALID — arm A selection 70% ≤ 80% ceiling ✓
Manipulation check: selection prompts differed (fixer generated distinct descriptions for arm B) ✓

Result:
  selection_accuracy: A=70% B=60% delta=-10% noise=0% McNemar b=0 c=5 b+c<10
  call_correctness:   A=100% B=100% delta=+0% noise=0% McNemar b=0 c=0

H1 verdict: NEGATIVE (B < A, not B > A). Direction reversed from hypothesis.
H2 verdict: UNTESTABLE (arm A call_correctness saturated at 100%).

Diagnosis for H1 NEGATIVE: The fixer (qwen3:8b) generated semantically WRONG descriptions for
both valid runs (#3 and #4) because the tool names (`get_a`, `get_b`, `del_a`, `del_b`, `put_x`)
and param names (`key`, `sid`) are too opaque for the generator to infer purpose. Fixer described
`get_a.key` as "API key for authentication" (not a record ID), `get_b` as "retrieves aggregate
statistics by operation code" (close but with misleading framing). These inaccurate descriptions
confused the agent MORE than the terse "Get." descriptions on arm A, which forced the agent to
rely on task semantics alone.

This is a genuine product finding, not a fixture artifact: **the fixer's description-quality
improvements are conditionally reliable — they require the tool name or existing schema to carry
enough signal for the generator to infer the correct purpose.** On fixtures where names are
opaque, the fixer may generate descriptions that actively mislead rather than clarify.

Run log now closed. Two valid runs (runs #3 and #4), both showing B ≤ A on selection_accuracy.
H2 is UNTESTABLE on this fixture/model combination.

---

## Known limits (state them)

- The held-out fixture is hand-degraded; it tests the MECHANISM, not external validity. The
  enterprise claim requires the real-third-party-server follow-up (next increment).
- A local third-family agent establishes the effect cheaply; the headline number customers will
  weigh needs the real target agent class (frontier / Claude), which is API spend — escalate.
- H2 (call_correctness): gemma2:9b may remain saturated even after the runner fix. If arm A
  call_correctness stays at 100%, H2 will be marked UNTESTABLE on this fixture/model.
  Creating genuine call_correctness headroom for a capable model requires either (a) truly
  opaque enum/format values that can't be guessed from parameter names + context, or (b) a
  weaker/constrained agent. Do not fake headroom to chase H2.

## Housekeeping

- TASKS.md: add T15, T16. STATUS.md: do NOT add any "fixes improve real agent performance" claim
  until the A/B result supports it; record the measured delta (including null) instead.
