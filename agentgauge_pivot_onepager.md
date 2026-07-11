# AgentGauge → Agent-Readiness Testing (product pivot)

## The pivot in one line
Stop selling **"we fix your tool descriptions"** (weak — agents resolve from task context, the fix is
low-stakes and can even harm). Start selling **"we test your MCP server with a real agent and catch
the failures before you ship"** — a CI gate / regression test for agent-tool usability.

## The USP (evidence-grounded)
GitHub built an *internal* offline-eval pipeline — confusion matrices, before/after testing — to catch
tool-confusion regressions when they change their MCP server. So did the other top players. That proves
the use case is real and valued *at the top*. But it also means the biggest teams self-serve.

**USP: give every team that *can't* build GitHub's internal eval pipeline the same capability —
a one-command, CI-native "will an agent use my server correctly?" gate.**

Nobody else runs a *real agent against your server* and reports the concrete failure modes. Linters
check schemas; security scanners check vulns; nobody tests *agent behavior*. That's the open lane.

## What it does (concrete)
Point it at an MCP server. It runs a real agent against realistic tasks and returns a report:
- Which tasks the agent got **wrong** (picked the wrong tool).
- Which tool **families are confusable** (the agent mixes them up) — localized, per-pair.
- Whether any task risks a **wrong destructive action** under ambiguous phrasing.
- Whether tool **calls are malformed** (bad arguments).
- **Regression mode:** you changed your server (added/renamed/refactored tools) — did agent
  usability get *worse*? Before-vs-after diff. (This is the highest-value mode — see below.)
- A single **agent-readiness score** + a CI gate (`exit 1 if score < threshold`) — already built.

## What it reuses (most of it already exists)
- The agent-vs-server harness (scan/score), the 8 scoring dimensions, the `ci` gate command, the
  before/after A/B machinery, the UX1 one-command flow, the mirror-fixture approach for safe testing.
- The whole experimental rigor (pre-registration, headroom/confound discipline) becomes the product's
  *credibility* — "our scores are validated, not vibes."

## What's genuinely new / on the critical path (be honest)
- **Score localization (the deferred SCORE-FIX).** RW1/RW2 showed the current score gives a flat
  catalog number and can't pinpoint *which* tools are confusable. A *testing* product lives or dies on
  pinpointing failures — so the per-pair confusability metric is now core work, not optional. This
  touches the judge (the careful, gated kind of change).
- **The regression mode** as a first-class feature (before/after on a real diff), since that's the
  use case with proven demand (GitHub does exactly this).

## Who buys / who doesn't
- **Buys:** teams building/maintaining their *own* MCP servers — internal tooling, custom/product
  servers — who iterate often (so regressions bite) and have no platform team to build eval infra.
- **Doesn't:** GitHub/Anthropic/Salesforce-tier (self-serve, F6) and tiny weekend servers (3 tools,
  no confusion to find).

## Pricing / packaging
- **Free OSS core** (like tracegauge) — one-command local test, builds adoption + credibility.
- **Paid:** CI integration, hosted runs (running a real agent costs compute), team dashboards,
  regression history/baselines, and the localized confusability report. Usage-based on test runs is
  the natural meter.

## The demo (what the buyer sees)
```
$ agentgauge test ./my-mcp-server
Agent-Readiness: 72/100   CI gate: FAIL (threshold 80)
✗ 3 of 12 tasks → wrong tool selected
✗ Confusable pair: update_record ↔ upsert_record (agent picks wrong 2/3)
⚠ Destructive risk: under vague phrasing, agent picked purge_item over archive_item
✓ All tool calls well-formed
→ Run `agentgauge test --baseline` before/after your next change to catch regressions.
```

## Honest open risks (the things to validate, not assume)
1. **Failure frequency.** Capable agents often *pass* on real servers (RW1/RW2 hit 100%). A tester
   that mostly reports "all good" is worth less — UNLESS buyers value pre-deploy confidence + regression
   safety the way they value a test suite that usually passes (they do, for regression; unproven here
   for a paid product).
2. **Willingness to pay.** Zero WTP signal surfaced in research. Top teams self-build; the question is
   whether the *next tier down* pays a third party. **Unknown — only a buyer can answer.**
3. **Score must localize** (the SCORE-FIX) or the report is too vague to act on.

## The ONE next step (do this before building anything)
Not another experiment. **One conversation with one team that runs an internal/custom MCP server:**
"If a tool could run a real agent against your server in CI and flag where it'll pick the wrong tool —
especially after you change something — would that be worth paying for?"

If yes → build the regression mode + score localization. If no → you've saved a month, and the
portfolio question is open.
