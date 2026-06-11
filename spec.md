# spec.md — FRONTIER-T18: does the T18 description effect survive a frontier agent?

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **Base:** `main` @ 8cb679b ·
**Branch:** `claude/frontier-t18`
**Routing:** DRAFT PR. New API-agent provider + re-run the T18 three-arm with a frontier agent.
Draft-forcing #2/#3 (real-model measurement; new live-API path). **NOT condition #1** (no
judge/scorer/rubric/calibration changes; reuses the T18 fixture + Arm A/Arm B-oracle unchanged).

**Pre-registration:** committed at branch start. The headroom-abort gate, the abstain/hedge
handling, the cost ceiling, and the collapse-vs-ceiling decision rule are fixed before any spend.

## *** ESCALATION — API SPEND, EXPLICIT KEY REQUIRED ***

This is the FIRST experiment needing a paid frontier API. GG's standing rule: NEVER use the Max-plan
`ANTHROPIC_API_KEY` (double-billing). Therefore:
- This test requires a SEPARATELY-BILLED API key with a HARD SPEND CAP, provided/confirmed by GG
  explicitly. CC must NOT wire up or assume any ambient ANTHROPIC_API_KEY.
- Pre-register a cost ceiling (e.g. <= a fixed USD cap); the runner must track token spend and ABORT
  if the projected full-matrix cost exceeds it.
- If no separately-billed key is confirmed, STOP and report — do not run.

## Why

The whole AgentGauge through-line predicts the description effect is AGENT-DEPENDENT: capable agents
resolve tool selection from names + task context, so descriptions matter only in the confusable-at-
scale regime (T18, +34.5pp on gemma2:9b). FRONTIER-T18 tests whether that effect SURVIVES a frontier
agent (Claude/GPT-class) or COLLAPSES (the strong agent resolves the confusable catalog from names
alone). This is the single result that decides whether the fixer's market is durable or weak-agent-
only and shrinks with each model release.

## The two traps to design against (NOT discover)

### Trap 1 — CEILING vs COLLAPSE (the experiment-killer)
A frontier agent may clear Arm A (empty descriptions) on T18 outright -> ~100% in BOTH arms -> ~0pp
delta. That is "fixture too easy" (instrument failure), NOT "effect collapsed" (real finding). They
produce identical numbers. MITIGATION — HEADROOM-ABORT GATE, run FIRST and CHEAP:
- Run ONLY Arm A (empty descriptions) on the frontier agent on the T18 contested set.
- If Arm A >= ~85%: NO HEADROOM for this agent. The result is "T18 is name-resolvable by this agent"
  — REPORT that as the finding (it IS informative: a strong agent doesn't need descriptions even on
  a 60-tool confusable catalog) and STOP. Do NOT run the full matrix; do NOT manufacture difficulty.
- If Arm A < ~85%: real headroom exists -> proceed to the full three-arm.
- Pre-register the 85% gate; do not adjust it after seeing the number.

### Trap 2 — ABSTAIN/HEDGE (frontier agents behave unlike gemma)
A strong agent may refuse to guess between indistinguishable tools, ask a clarifying question, or
hedge — none of which gemma did. The parse-success/selection-accuracy metric must NOT score
thoughtful uncertainty as "wrong selection." Instrument THREE outcomes, separately:
- SELECTED-CORRECT / SELECTED-WRONG / ABSTAINED-OR-HEDGED (no clear single tool selected).
- parse_failed reported separately as before.
Report all three per arm; do not collapse ABSTAINED into WRONG.

## Design

- New `ApiAgentProvider` implementing the same agent interface as `OllamaProvider` (the call the T18
  harness already uses). Configurable model; reads key from an explicitly-passed env var (NOT a
  hardcoded ANTHROPIC_API_KEY); token-spend tracking + cost-ceiling abort; retry/backoff on rate
  limits. The ollama `ps` foreign-model watchdog is N/A for API — replace with spend tracking.
- Reuse the T18 fixture + tasks UNCHANGED. Arms: Arm A = empty descriptions (floor / headroom gate);
  Arm B = T18 ORACLE discriminating descriptions (the +34.5pp ceiling on gemma). (Guard-B arm
  optional, only if Arm A shows headroom AND budget allows — the primary question is oracle-vs-empty,
  i.e. does the BEST POSSIBLE description still move a frontier agent.)
- Metric: per-arm SELECTED-CORRECT rate on the T18 contested set; effect = B - A; task-clustered
  sign test on contested tasks (effective N = contested tasks, as in T18). Trials kept low to bound
  cost (e.g. 3), pre-registered.

## Acceptance criteria

1. **CI (deterministic, no network):** `ApiAgentProvider` interface-conforms (MockProvider-style
   test, NO real API call in CI); cost-ceiling abort logic unit-tested; abstain/hedge classification
   unit-tested (a hedged response classifies as ABSTAINED not WRONG); key read from passed env var,
   never a hardcoded ANTHROPIC_API_KEY (assert). verify.sh green.
2. **Frontier run (manual, in PR description) — ONLY with a confirmed separately-billed key:**
   - STEP 1 (cheap): Arm A headroom gate. Report Arm A SELECTED-CORRECT on contested set + total
     token spend. If >= 85% -> NO-HEADROOM finding, STOP, report.
   - STEP 2 (only if headroom): Arm A vs Arm B(oracle) full matrix. Report the 3-outcome breakdown
     per arm, effect (B-A), task-clustered sign test, and total spend (must be under ceiling).
   - VERDICT:
     - Effect SURVIVES (B significantly > A on frontier agent): description quality matters even for
       strong agents in the confusable-at-scale regime -> the fixer's value is DURABLE. Strongest
       possible commercial result.
     - Effect COLLAPSES (A ~ B, both well below ceiling, agent resolves from names): the fixer's
       value is weak-agent-specific -> market shrinks as agents improve. Defining negative.
     - NO HEADROOM (A >= 85%): frontier agent doesn't need descriptions on T18 at all -> same
       strategic implication as collapse, reached more cheaply.
3. No judge/scorer/rubric/calibration changes; verify.sh green; coverage >= 60%. No ambient
   ANTHROPIC_API_KEY used anywhere.

## Housekeeping

- TASKS.md: FRONTIER-T18 (TODO -> IN-REVIEW). STATUS.md: record the headroom-gate result and (if run)
  the frontier effect size vs gemma's +34.5pp, framed as the DURABILITY verdict for the fixer's
  market. Scope to "one frontier model, the T18 fixture"; one model is one datapoint.
