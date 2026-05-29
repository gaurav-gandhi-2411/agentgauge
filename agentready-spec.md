# Spec — AgentReady: Agent-Readiness Scorer + Monitor

> Working name `AgentReady` (CLI: `agentready`). Rename before first commit if you have a better one.
> "Lighthouse / PageSpeed, but for agent interfaces." Point it at an MCP server (later: an OpenAPI
> spec or a CLI), and it tells you whether a real LLM agent can actually discover, understand, call,
> and recover from errors against that target — with a score, a diagnosis, and the fixes.

## 1. Why this exists

Across ~3,000+ public MCP servers, the median server passes only ~71% of agent tasks while agents
need 95–99% per call, and there is almost no public reliability data. Agents fail mostly because the
interface and docs they're handed are bad (ambiguous tool names, missing param descriptions,
unparseable errors), not because the underlying code is broken. Generating the agent-facing layer
(`llms.txt`, tool docs) is commoditized; **verifying and improving whether agents succeed with it is
not, and nobody owns the neutral, standard score.** That score is the product.

## 2. Positioning / moat

Three things keep this defensible against existing test runners (Arcade Evals, TestSprite, Lunar):
1. **Neutral public standard** — the score everyone cites (MCP is now under the Linux Foundation, so
   a vendor-neutral scorer is well-placed).
2. **Eval quality** — statistically sound, multi-trial scoring that accounts for LLM
   non-determinism. This is the ML edge and the hardest part to copy.
3. **Closing the loop** — not just "here's what's wrong" but auto-generated fixes (better
   descriptions/schemas/examples) as a PR.

## 3. Scope (staged; v1 is the only thing we build first)

**v1 — CLI scanner (ship this first).**
`agentready scan <target>` connects to an MCP server (stdio or HTTP/SSE), introspects its
tools/resources/prompts, runs an eval harness where a real LLM agent attempts a battery of tasks,
and prints a scored report (+ JSON + HTML). No backend, no accounts. This alone is demoable and
shareable.

**v2 — Fix + monitor (the revenue core).**
Auto-generate improved tool descriptions/schemas/examples and open them as a PR against the target
repo. A CI action (`agentready ci`) that fails the build on score regression. A hosted dashboard with
per-server history and regression alerts (subscription).

**v3 — Expand surface + flywheel.**
Same harness against OpenAPI/REST and CLIs. A public scanner + leaderboard + "certified
agent-ready" badge/directory as the distribution engine (publishing scores is itself the marketing —
the public stress-test studies got attention purely by publishing numbers).

## 4. Scoring rubric (the IP — each dimension 0–100, weighted to an overall score)

| Dimension | What it measures | How |
|---|---|---|
| Discoverability | Tool/resource names are clear and distinct | heuristic + LLM judge |
| Description quality | An agent can choose & call from the description alone | LLM judge, multi-trial |
| Schema completeness | types, required/optional, enums, examples present | static analysis of schema |
| Selection accuracy | Given an ambiguous task, agent picks the RIGHT tool | agent runs, N trials, % correct |
| Call correctness | Agent constructs valid calls on generated inputs | agent runs, success rate |
| Error legibility | Error responses are understandable & actionable to an agent | inject bad input, LLM judge |
| Robustness | Behavior under malformed / missing params | fuzz-lite, no crashes/leaks |
| Docs/manifest | Presence + quality of agent-facing docs (llms.txt / tool docs) | fetch + judge |

Report: overall score, per-dimension breakdown, a **prioritized fix list** (highest score-impact
first), and per-metric **variance/confidence** (because LLM behavior is probabilistic — single-shot
testing is misleading).

## 5. Architecture (v1)

```
agentready/
  client.py     # MCP client: connect (stdio/HTTP/SSE), list tools/resources/prompts, call tools
  tasks.py      # task generator: per tool, synthesize realistic invocations + edge cases
  runner.py     # agent runner: an LLM attempts the tasks using the server (N trials)
  scorer.py     # rubric scoring: heuristics + LLM-as-judge; aggregates with variance
  report.py     # CLI/text + JSON + HTML report
  providers.py  # model-agnostic LLM provider (local Ollama, or hosted via API key)
  cli.py        # `agentready scan <target> [--model ...] [--trials N] [--out report.html]`
tests/          # unit tests with the LLM MOCKED so CI is deterministic and free
```

Design rules:
- **Model-agnostic.** The harness needs an LLM to act as the test agent; make the provider
  configurable. Default to a local model (Ollama) for free dev; allow a hosted key for real scans.
  This keeps the product's runtime cost off your Max plan.
- **Tests mock the LLM** so `verify.sh` runs deterministically with no paid calls in CI.
- **Multi-trial + seeded** wherever possible; always report variance.
- Python for v1 (MCP Python SDK, ML/evals ergonomics). TS later for the web dashboard.

## 6. Monetization

Free public CLI (top of funnel) → paid CI monitoring + hosted dashboard, per-server/month
subscription (recurring core) → team/enterprise tier (private servers, SSO, audit history) →
usage-based scans on top. Build none of the billing now; v1 has no accounts. Defer Stripe until the
dashboard exists and people are asking to pay.

## 7. How this project builds itself (autonomy wrapper)

The repo is made "autonomy-ready" and driven by a Claude Code **cloud scheduled task**
(claude.ai/code/scheduled) running on Opus, so it keeps building with the laptop off. Each run picks
one backlog item, implements it on a `claude/` branch, runs `verify.sh`, and opens a draft PR for
you to review. Committed into the repo: `.claude/agents/` (your orchestrator/executor/verifier),
`.claude/operator-prompt.md`, `CLAUDE.md`, `AUTONOMY.md`, `TASKS.md`, `scripts/verify.sh`,
`.github/pull_request_template.md`. Guardrails: `claude/`-branches only, one task per run, no
weakening tests, draft PRs gated by a human. (Full operator prompt + contract are generated into the
repo by the kickoff prompt.)

## 8. v1 backlog seed (goes into TASKS.md)

- (P1) MCP client: connect over stdio + HTTP/SSE; list tools/resources/prompts; call a tool.
- (P1) Provider layer: pluggable LLM provider; Ollama default; mockable for tests.
- (P1) Scorer: schema-completeness + description-quality dimensions end-to-end with a printed score.
- (P1) CLI: `agentready scan` wiring client -> scorer -> text report.
- (P2) Task generator + agent runner: selection-accuracy & call-correctness dimensions, N trials.
- (P2) Error-legibility + robustness dimensions.
- (P2) JSON + HTML report output.
- (P3) Docs/manifest dimension (fetch + judge llms.txt / tool docs).

Each item gets explicit, testable acceptance criteria when it enters TODO.

## 9. Honest limitations

- The eval harness quality *is* the product; a weak harness makes the score meaningless. This is
  where your effort should concentrate.
- Existing movers in MCP testing mean speed + neutrality + the fix-loop are what differentiate you,
  not "a test runner."
- MCP spec moves fast; the client/harness must track it.
- Real scans cost model calls — keep the harness provider-agnostic so neither you nor users are
  forced onto one vendor.
