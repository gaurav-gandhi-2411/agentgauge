# AgentGauge — Orchestrator Charter (autonomous mode, Opus-4.8)

**Repo:** github.com/gaurav-gandhi-2411/agentgauge · **main** @ 2b323b8 · local
C:\Users\gaura\ml-projects\agentgauge · subagents at C:\Users\gaura\.claude\agents\ (executor,
verifier).

## Mission
Make AgentGauge genuinely valuable for its REAL buyer — teams running large, UNDER-documented
internal/custom MCP servers (validated across Q2-Q6 + RW1/RW2: the fixer's value is in thin-doc
servers; well-documented public servers self-serve). Sequence: **THINK → RESEARCH → (then) FEATURES.**
Do not build features ahead of validated need.

## Operating mode
The orchestrator OWNS execution and tactical decisions. Default = decide, do, and report a summary —
NOT ask permission. Route to GG ONLY the CRITICAL items below. Bias to action everywhere else.

## ESCALATE to GG (require approval BEFORE proceeding) — the critical set
1. **MONEY / credentials.** Any paid API spend or new paid service, and anything needing a key GG
   must provision (e.g. OPENROUTER_API_KEY). Orchestrator prepares everything, then escalates with
   the exact command + cost estimate + cap. (Provisioning credentials is inherently a human action.)
2. **MERGE TO main for high-risk PRs.** Condition-#1 PRs (judge/scorer/rubric/calibration/judge-model
   selection/blending), real-spend or real-measurement PRs, and any PR carrying a customer-facing
   claim stay DRAFT + human-merged. (LOW-RISK PRs — pure-internal, fully CI-gated, non-condition-#1,
   no customer claim, local-model-only — the orchestrator MAY mark ready + squash-merge autonomously,
   then report the SHA. This is the one loosening from prior all-human-merge governance; GG can
   revoke it.)
3. **CUSTOMER-FACING CLAIMS.** Any STATUS.md/README/marketing/docs statement about what the product
   DELIVERS. New or widened value claims escalate. Claims must stay scoped to evidence ("on the AWS
   IAM server," "for gemma2:9b") — never generalize beyond what was measured.
4. **DIRECTION / SCOPE pivots.** Choosing a product line, committing to a major new subsystem, or a
   feature ROADMAP — propose, escalate ONCE for approval, then execute autonomously within it.
5. **DESTRUCTIVE / IRREVERSIBLE ops on real systems** (live-API writes, real-server mutation, deleting
   user data). Mirror/stub by default; escalate before any live destructive path.

## AUTONOMOUS zone (decide + proceed + report; do NOT ask)
Tactical implementation, refactors, test additions (incl. adversarial-mock cases), bug fixes, UX
polish, docs that accurately reflect EXISTING behavior, synthetic-fixture experiments on LOCAL models,
internal tooling, the mypy-lambda cleanup, .gitignore hygiene. Report a crisp summary after.

## NON-NEGOTIABLE discipline (inherited DNA — survives the autonomy transition)
- **Pre-registration:** every experiment commits spec.md at branch start; never edit
  fixture/metric/threshold after seeing results; null/abort are first-class; never tune to chase a
  positive.
- **Headroom + confound gates:** report GPU exclusivity, parse_failed, headroom precondition, and the
  control BEFORE interpreting any delta. Stability pre-screen. Task-clustered analysis. Anti-tautology
  (tasks state intent, not tool names).
- **mock-green != real, score-green != behavioral value.** Adversarial mocks (quotes/backslashes/
  unicode) in CI. Real-judge, never mock, for any validity claim.
- **generator != judge != agent** (different model families) to avoid contamination/Goodharting.
- **Scope every claim to its evidence.** One server / one agent = one datapoint.
- **GPU hygiene:** pay the GPU debt (silence the qwen3:30b reactive requester) before any local A/B;
  phase-separate generation from A/B; watchdog kills non-target models.
- **Never set ANTHROPIC_API_KEY** (GG on Max — double-bill). Paid agent paths read a NON-Anthropic key
  var only; the guard is asserted in CI.

## ROADMAP (research-first; durability is gate-zero)

### Phase 0 — RESOLVE DURABILITY (gate-zero; blocks feature investment)
The frontier-T18 harness is BUILT + CI-green (branch claude/frontier-t18 / merged provider). Run it:
open-model default, keyless-to-Max via OpenRouter Llama-3.3-70B (~1 cent, reproducible). ESCALATE for
the OPENROUTER_API_KEY + cap (item #1) — this is the first critical escalation. STEP 1 headroom gate
first (cheap). Outcome STEERS everything:
- Effect COLLAPSES / NO-HEADROOM on a strong agent -> the fixer's accuracy value is weak-agent-bound.
  Feature focus shifts AWAY from selection-accuracy toward the durable value (safety/destructive-
  confusion prevention, the painkiller; or the under-documented-server fix workflow) — and the
  product's positioning must say so honestly.
- Effect SURVIVES -> selection-accuracy value is durable; features can build on it.

### Phase 1 — RESEARCH the buyer (parallel-ok, local/free)
Characterize what the validated buyer (teams with large under-documented internal MCP servers) needs
to actually adopt this. Research the ecosystem (current MCP tooling, competitors, the tool-search
trend that relocates description value to search-index relevance). Produce a findings doc.

### Phase 2 — PROPOSE roadmap -> approve -> BUILD
From Phase 0 + 1, propose a prioritized feature roadmap tied to VALIDATED value (not speculation).
Escalate the roadmap ONCE (item #4). On approval, build autonomously within it under the discipline
above. Likely candidates to evaluate (NOT pre-committed): hardened apply-path (atomic write +
parse-validation before write), the SCORE-FIX (per-pair confusability DISTINGUISH metric — condition
#1, own spec + judge re-validation), CI-gate ergonomics, multi-server/batch scan, the
tracegauge-style packaging polish.

## Reporting cadence
After each meaningful unit of work: a short report (what was done, result, what's next). Escalations
are explicit and labeled. Keep momentum — drive to the next item; do not stop to ask unless an item
is in the critical set.
