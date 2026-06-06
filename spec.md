# spec.md — T18: discoverability at scale (DISTINGUISH among confusable tools)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` (after #39 merge) ·
**Branch:** `claude/t18-discoverability-scale`
**Routing:** DRAFT PR. Draft-forcing #2/#3. NOT condition #1.

**This spec, committed at branch start, IS the pre-registration.** Fixture, gold mapping, oracle
descriptions, headroom target, analysis plan fixed before the run, not edited after.

---

## What this tests

The `discoverability` dimension (15%) scores DISTINGUISH: how well an agent tells confusable,
similarly-named tools apart and picks the right one (per scorer.py:_judge_discoverability). Its
behavioral analog is selection_accuracy UNDER CONFUSABILITY. T17 tested this at tiny scale (2-3-tool
clusters) and saturated — gemma resolves a 3-tool toolbox from names. T18 tests the regime the
dimension is actually about: **many tools, organized into dense families of near-neighbors**, where
the target is buried among look-alikes and a DISCRIMINATING description is what separates it.

## Why scale, not a weaker agent (strategic note, pre-registered)

The product's real agents are frontier (more capable than gemma2:9b); a null on gemma predicts a
stronger null on frontier. A weaker agent (gemma2:2b) tests AWAY from product reality and re-imports
the "model helped by being handed the answer" tautology. The mechanism that could bite even for a
CAPABLE agent is distractor density at scale, not lower capability. So T18 holds the agent at
gemma2:9b and changes the toolbox SCALE + CONFUSABILITY, not the model.

## New headroom mechanism (why this might finally clear the gate)

- Run 1/Ty: floored on un-guessable constraints. T17: saturated on tiny confusable clusters.
- T18 headroom source = DISTRACTOR DENSITY: 60-80 tools in families of 6-8 confusable near-neighbors.
  Within a family, names are individually plausible for overlapping intents; only the description
  discriminates. At this scale, name-skimming should degrade — that is the testable hypothesis.

---

## Scope

**IN:** a large confusable-catalog fixture (60-80 tools, ~8-10 families of near-neighbors); Arm A
vague/empty descriptions; Arm B oracle discriminating descriptions; powered, stability-screened task
set; oracle A/B on selection_accuracy via the T15 harness.

**OUT:** call construction (selection only — one arg or none; the variable is WHICH tool, not how
it's called); the fixer (downstream, only if positive); weaker-agent swap (down-ranked, see above);
scorer changes.

## Fixture design

- 8-10 FAMILIES, each 6-8 tools that are genuine near-neighbors: similar names + overlapping apparent
  purpose (e.g. a "fetch" family: get_record / fetch_record / read_entry / load_item / retrieve_row /
  pull_document — surface-synonymous), where the correct choice for a task depends on a distinction
  carried only by the description (scope, source, side effect, format).
- Catalog size 60-80 tools total. All families present in every prompt (the agent sees the full
  catalog — that is the scale condition).
- Arm A: vague/empty descriptions -> within a family, the agent must pick among 6-8 look-alikes from
  names alone. Arm B: ORACLE descriptions that discriminate within-family. Commit both.
- One gold tool per task; tasks distributed across families. Document, per family, WHY the names are
  confusable and WHAT distinction the description carries.
- ANTI-TAUTOLOGY: task states user intent; it must NOT name the target tool or quote its description.

## Rigor (carry forward all lessons, incl. the new parse_failed instrument)

- Headroom: Arm A selection_accuracy ~40-70% on CONTESTED tasks. CONFIRM before interpreting;
  outside the band -> ABORT (do not rebuild blindly; report).
- parse_failed rate reported FIRST (selection is one token, but report it anyway as a harness check).
- Stability pre-screen: Arm A twice, drop tasks flipping >1 trial, report count.
- Power: >= 30 contested surviving tasks. Task-clustered analysis (sign/Wilcoxon on task-level
  deltas), effective N = contested tasks. NOT trial-level McNemar.
- Manipulation check: Arm A vs Arm B catalogs differ in the served listing (assert).
- Agent = gemma2:9b, != judge != generator. selection_accuracy deterministic.
- No post-hoc tuning after seeing results.

---

## Acceptance criteria

1. **CI (deterministic, seed 42, no network):** catalog loads (60-80 tools, families well-formed);
   each task has exactly one gold tool; stability-screen logic; manipulation check (Arm A vs B
   catalogs differ); anti-tautology test (target tool name + its description tokens absent from task
   text). No real model in committed tests.
2. **Real-agent oracle A/B (manual, in PR description):**
   - parse_failed rate + pre-checks reported FIRST: contested Arm A in 40-70% and stable, N>=30,
     manipulation pass. Outside band -> STOP, report ABORT.
   - Task-clustered table: Arm A, Arm B(oracle), per-task delta, sign/Wilcoxon, effective N.
   - Honest three-way verdict:
     - POSITIVE (oracle > A): at scale, discriminating descriptions improve confusable-tool
       selection -> the first located behavioral effect for a description-facing dimension; the
       discoverability 15% has real teeth in the regime it was designed for.
     - NULL (oracle ~ A): even buried among dense look-alikes, gemma picks from names; descriptions
       don't move it -> with T17 + Ty, a strong cross-dimensional construct-validity finding.
     - ABORT (Arm A outside 40-70%): scale didn't create the expected headroom (saturated = even at
       scale names suffice; floored = catalog too hard to navigate at all). Report which.
3. scorer.py / judge / rubrics / calibration / generator untouched; verify.sh green; coverage >= 60%.

## Housekeeping

- TASKS.md: T18 (TODO -> IN-REVIEW). STATUS.md: record the measured result. If POSITIVE, this is the
  regime where description_quality/discoverability matter — note it as the validated use-case. If
  NULL/ABORT, record the cross-dimensional finding across selection (T17), calls (Ty), discoverability
  (T18).
