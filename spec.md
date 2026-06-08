# spec.md — Q6: do-no-harm on already-passing tasks (is Guard-B safe to run BLANKET?)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 40857c7 ·
**Branch:** `claude/q6-do-no-harm`
**Routing:** DRAFT PR. Fixture extension + run existing Guard-B generator + real-agent A/B.
Draft-forcing #2/#3. **NOT condition #1** (no judge/scorer/rubric/calibration/generator-logic
changes — Guard B is reused as-is from Q5).

**Pre-registration:** committed at branch start. The extended fixture, the harm threshold, the
headroom INVERSION, and the regression metric are fixed before the run.

---

## Why

Every recovery result (T18, Q3-Q5) was measured on the ARM-A-FAILURE SUBSET — tasks selected
because empty descriptions fail them. We have NEVER measured whether the fixer DEGRADES a task the
agent already passes. Until that's ruled out, "run the safe Guard-B fixer across a whole server" is
unjustified — it could help the confusable tools and silently harm the already-fine ones. Q6 is the
do-no-harm test that gates blanket deployment.

## The headroom INVERSION (this gate is the opposite of all prior ones)

For T18/Q3/Q4/Q5: "Arm A near 100% = abort, no headroom." For Q6: **Arm A at/near 100% on a task is
the PRECONDITION** — you can only measure HARM where there was nothing to gain. The metric is a
REGRESSION check, not a recovery check: count tasks that go PASS (empty) -> FAIL (Guard-B). Any such
flip is a do-harm regression.

## The harm mechanism to design FOR (not just against)

Guard B forbids comparative claims -> target-only positive descriptions. Risk: two tools the agent
currently distinguishes BY NAME get target-only descriptions MORE similar than their names were,
creating NEW confusability. The already-passing set MUST include collision-prone pairs — tools with
DISTINCT names but OVERLAPPING target-only descriptions (e.g. list_users / list_accounts, both
"returns a list of records") — or Q6 cannot detect the failure it exists to find.

---

## Scope

**IN:** extend the Q3/Q5 source-bearing fixture with already-passing (name-resolvable) tools that have
REAL implementations; run the Q5 Guard-B fixer across the FULL extended catalog; measure regressions
on the already-passing subset + confirm contested recovery preserved + net aggregate effect.

**OUT:** any change to Guard B / generator logic (reused as-is); new dimensions; scorer changes; the
T18 echo-stub catalog (no source).

## Fixture extension

- Add >= 8 already-passing tools with real, distinct implementations and DISTINCT names such that
  empty-description Arm A selects them correctly (name-resolvable; NOT confusable families).
- Of these, deliberately include >= 3 COLLISION-PRONE pairs: distinct names, but whose honest
  target-only (Guard-B-style) descriptions risk overlapping (same verb + same generic object).
  Document each pair and why its names disambiguate but its target-only descriptions might not.
- Keep the existing 6 structural contested tasks + the Q5 Guard-B descriptions for them, so contested
  recovery can be re-confirmed on the extended catalog.
- Independence/realism rules from Q3 apply: real bodies, written without gaming the descriptions.

## Rigor

- STABILITY: the already-passing tasks must pass empty-Arm-A STABLY (run twice, drop any that flip
  >1 trial). A task that only "passes" by luck can't anchor a regression claim. Report dropped count.
- Headroom precondition: confirm already-passing Arm A is at/near 100% before measuring harm.
- Task-clustered; agent gemma2:9b (!= judge != generator); generator qwen3:8b; phase-separated GPU,
  silence qwen3:30b first.
- No post-hoc fixture tuning after seeing results.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** extended fixture loads; already-passing tools have
   real bodies + distinct names; collision-prone pairs documented + asserted (distinct names,
   flagged for target-only overlap risk); gold mapping intact; Guard-B generation path unchanged from
   Q5. No real model in committed tests.
2. **Real-agent A/B (manual, in PR description):**
   - GPU exclusivity + parse_failed FIRST.
   - HEADROOM PRECONDITION: already-passing subset empty-Arm-A at/near 100% (post stability-screen,
     dropped count reported). If they're NOT already passing, the harm test is void on those — report.
   - REGRESSION (the headline): empty vs Guard-B on the already-passing subset. Count PASS->FAIL
     flips. ZERO regressions = do-no-harm holds. Show EACH regression with the Guard-B description
     and the collision it caused (which sibling the agent flipped to).
   - CONTESTED CHECK: confirm Guard-B still recovers the 6 structural contested tasks on the extended
     catalog (the Q5 result didn't break under more tools).
   - NET EFFECT: aggregate empty vs Guard-B across ALL tasks (contested + already-passing). Net
     positive only if recovery gains aren't cancelled by regressions.
   - Verdict:
     - ZERO regressions + recovery preserved: Guard-B is SAFE TO RUN BLANKET — the full deployment
       claim closes.
     - REGRESSIONS on collision-prone pairs: Guard-B can introduce confusability via target-only
       phrasing; blanket use needs a collision check (the regressions localize what Q7 would fix).
     - Recovery broke on extended catalog: scale interaction; report.
3. scorer.py / judge / rubrics / calibration / Guard-B generator logic untouched; verify.sh green;
   coverage >= 60%.

## Housekeeping

- TASKS.md: Q6 (TODO -> IN-REVIEW). STATUS.md: record regression count on already-passing tasks +
  net aggregate effect + the blanket-safety verdict. Do NOT claim "safe to run blanket" unless ZERO
  (or quantified-and-acceptable) regressions AND contested recovery preserved.
