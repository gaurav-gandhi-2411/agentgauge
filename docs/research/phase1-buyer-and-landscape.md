# Phase 1 Findings — The Validated Buyer & Competitive/Ecosystem Landscape

**Date:** 2026-06-13 · **Author:** orchestrator (Opus 4.8), synthesized from two parallel
web-research passes · **Status:** internal research input to the Phase 2 roadmap. Not a
customer-facing claim. All non-obvious claims carry a source URL; confidence/gaps noted per section.

> Scope note: this is desk research over a ~12–18-month-old ecosystem. Most sources are vendor
> blogs, dev.to posts, and pre-print arXiv. Treat precise percentages as approximate and read the
> "Confidence & gaps" blocks. One company ≠ the market.

---

## Part A — The buyer

### Who
Platform / developer-experience / AI-infra teams at orgs that have built MCP servers wrapping
their **own internal** APIs, DBs, and tools, and are now wiring many agents to many servers.
Named, at-scale examples:
- **Block** — MCP to 12,000 employees across 15 job functions in two months; 60+ internal servers
  built in one Hack Week, "every internal app has an MCP server"; built **in-house for
  security/control**
  ([allthingsopen](https://allthingsopen.org/articles/block-scaled-mcp-12000-employees-15-job-functions),
  [dev.to/blockopensource](https://dev.to/blockopensource/mcp-in-the-enterprise-real-world-adoption-at-block-ci5),
  [cdata](https://medium.com/cdata-software/10-real-world-enterprise-mcp-use-cases-every-cio-should-know-dc9fc62c46b8)).
- **Cloudflare** — centralized MCP platform; **4 internal servers expose 52 tools** wrapping PM,
  wiki, docs, code; new servers require AI-governance approval
  ([blog.cloudflare.com](https://blog.cloudflare.com/enterprise-mcp/)).
- **Amazon, Bloomberg** — MCP added to most internal tools / adopted org-wide
  ([cdata](https://medium.com/cdata-software/10-real-world-enterprise-mcp-use-cases-every-cio-should-know-dc9fc62c46b8)).

**Tool counts** cluster from ~50 (Cloudflare's 4 servers) into the hundreds of servers per
enterprise. The public GitHub MCP server alone burns **~42k tokens** in tool definitions
([dev.to/thedailyagent](https://dev.to/thedailyagent/mcp-tool-overload-why-more-tools-make-your-agent-worse-5a49)).

### Pain (painkiller, not vitamin — at scale)
- **Selection accuracy decays with tool count.** Secondary reports: >90% (5–7 tools) → ~13%
  (100+); GitHub MCP ~95% (focused) → ~71% (full server)
  ([dev.to/thedailyagent](https://dev.to/thedailyagent/mcp-tool-overload-why-more-tools-make-your-agent-worse-5a49)).
- **Context blowup.** Cloudflare's 52 tools = ~9.4k tokens of definitions; 4–5 servers can exceed
  60k tokens before any work ([blog.cloudflare.com](https://blog.cloudflare.com/enterprise-mcp/)).
- **Poor/missing descriptions dominate.** ToolBench: 167,333 / 218,422 tools graded **F**, only
  0.5% A+, 6,568 with missing descriptions
  ([arcade.dev](https://www.arcade.dev/blog/introducing-toolbench-quality-benchmark-mcp-servers/)).
- **Small description edits move the needle** — Anthropic: "even small refinements yield dramatic
  improvements"; GitHub built an offline eval harness because tightening a description "shifts
  results a lot"
  ([anthropic.com](https://www.anthropic.com/engineering/writing-tools-for-agents),
  [github.blog](https://github.blog/ai-and-ml/generative-ai/measuring-what-matters-how-offline-evaluation-of-github-mcp-server-works/)).
  This directly validates the fix-the-descriptions thesis.

### Adoption requirements / blockers
- **Local / no exfiltration.** In-house builds are security-motivated; sending internal tool
  schemas to a hosted LLM is a likely blocker. AgentGauge's local-Ollama default + self-hosted
  judge is a direct fit. *(Inferred from security posture, not a verbatim buyer quote.)*
- **CI/CD gating.** Buyers already gate on eval scores ("block deployments if scores drop");
  a non-zero exit on regression fits.
- **Score stability/comparability** — because edits "shift results a lot," reproducible scoring
  matters (maps to AgentGauge's pinned-judge calibration discipline).
- **Transports + batch.** stdio+HTTP+SSE and multi-server scanning are table stakes.

### Where budget sits
A funded **MCP gateway/governance** category exists with real pricing (MintMCP $1,250/mo/50 seats;
Portkey, Lunar.dev, Maxim, MCP Manager). **Risk:** budget concentrates in *runtime
gateways/observability*, not *static pre-deploy quality scoring/fixing*. No evidence found of any
org paying specifically for MCP quality scoring/fixing.

---

## Part B — Competitive & ecosystem landscape

### The map (three layers; our wedge is the gap between them)
- **Protocol debuggers (low overlap).** Official **MCP Inspector** validates handshake/schema
  conformance, not agent usability ([modelcontextprotocol.io](https://modelcontextprotocol.io/docs/tools/inspector)).
- **Registry quality scores (high overlap, rising).** **Smithery** scores servers and penalizes
  thin/absent descriptions; **Glama** "scored for quality and safety"; **MCPskills** 13–15 trust
  signals. But these are **registry-side, post-publish gatekeepers** — they score, they don't
  auto-fix, and they're not author-side CLIs
  ([Smithery writeup](https://medium.com/@francofuji/your-mcp-server-scores-60-100-on-smithery-what-it-means-and-how-to-hit-100-edd924758268),
  [glama.ai](https://glama.ai/), [mcpskills.io](https://mcpskills.io/)).
- **Agent/tool eval harnesses (medium overlap).** **Arcade Evals** scores tool selection +
  argument quality and advises tuning names/params/descriptions — but no auto-fix and no doc
  scoring ([arcade.dev](https://www.arcade.dev/blog/evaluate-mcp-tools/)). **Braintrust**,
  **LangSmith** are general, paid agent-eval platforms, not MCP-quality-specific.

**No single tool combines (a) author-side CLI + (b) multi-dimension rubric scoring of
description/schema quality + (c) measured auto-fix.** That is the open niche.

### The tool-search / tool-retrieval trend (the decisive finding for Phase 0)
This is **shipped, not speculative**. Anthropic's **Tool Search Tool** defers MCP schemas until
needed (~85% fewer tool-def tokens; reported accuracy 49%→74% on Opus 4, 79.5%→88.1% on Opus 4.5)
and **retrieves via BM25 over tool names + descriptions + parameter names**, substring fallback
only when BM25 scores zero
([marktechpost](https://www.marktechpost.com/2026/05/29/hermes-agent-ships-tool-search-for-mcp-anthropic-evals-show-49-to-74-accuracy-gain-on-opus-4/),
[tessl.io](https://tessl.io/blog/anthropic-brings-mcp-tool-search-to-claude-code/)).
**Programmatic tool calling** (GA Sonnet 4.6) and OpenAI's Responses-API orchestration push the
same direction.

**Does retrieval raise or lower the value of good descriptions?**
- **Raises (stronger argument):** the description *is the retrieval index*. BM25 is lexical — a
  tool whose description omits the query's vocabulary becomes **un-retrievable**, not merely
  confusing. Independent research: 97.1% of MCP tool descriptions contain a "smell," 56% unclear
  purpose; augmenting descriptions lifted task success +5.85pp
  ([arXiv 2602.14878](https://arxiv.org/html/2602.14878v2)). Retrieval turns description quality
  from a soft nicety into a **hard recall gate**.
- **Lowers (counter):** a router/embedding/reranking layer may absorb selection and recover signal
  from weak text; naive augmentation also regressed ~1-in-6 cases and raised steps +67% (same
  paper) — more text isn't free.
- **Net:** retrieval **increases** the value of *measured, scored* descriptions (not just longer
  ones) — which is an evaluator's job.

---

## Part C — Orchestrator synthesis: how this steers Phase 0 and Phase 2

1. **The tool-search trend reframes the Phase-0 durability question — possibly rescuing it.**
   The original worry: a frontier agent resolves the T18 confusable catalog from names alone →
   the description effect collapses → the fixer is weak-agent-bound. But the *whole industry is
   moving the other way*: strong agents increasingly **don't see all tools** — they retrieve via
   BM25 over descriptions. In that regime, description quality is load-bearing *because of*
   capability, not in spite of it. **FRONTIER-T18 measures the wrong half if read narrowly.** It
   still answers "does oracle-vs-empty matter when ALL tools are in-context for a strong agent?" —
   a valid datapoint — but the durable thesis increasingly lives in the **retrieval-readiness**
   frame, which T18 does not test. *(See recommendation in the Phase-0 report.)*

2. **The defensible niche is "retrieval-readiness + actionable-fix linter that runs in CI."**
   Author-side, pre-publish, CI-gateable, local-by-default, calibrated/reproducible, emitting a
   *measured* fix (proves it didn't regress). Every incumbent misses at least one of these axes.

3. **Commoditizing:** protocol conformance, registry post-publish scores, naive "make it longer"
   generation. **Staying valuable:** pre-deploy CI scoring, retrieval-aware scoring, measured
   auto-fix with delta proof, calibrated reproducible judging.

4. **Honest market caveat:** today's *money* is in runtime gateways/observability. AgentGauge's
   wedge is the under-served **pre-deploy fix-the-descriptions** gap — real pain (ToolBench's F
   distribution; GitHub's edit-and-eval loop) but not yet a proven *budget line*.

### Confidence & gaps (consolidated)
- **Strong:** failure modes & tool counts (Cloudflare 52/9.4k, GitHub ~42k, ToolBench F
  distribution); Block scale; existence of paid governance market; Tool Search uses BM25 over
  name/description/params; Inspector/Smithery/Glama/Arcade roles.
- **Medium:** 95%→71% and >90%→13% selection figures are secondary-source paraphrase, not verified
  against a primary benchmark; Tool Search accuracy/token percentages are tech-press paraphrase of
  Anthropic evals.
- **Could NOT verify:** any org paying *specifically* for MCP quality scoring/fixing; a verbatim
  "won't send schemas to a hosted LLM" buyer quote (inferred); whether Arcade/Smithery scoring is
  OSS vs paid; no incumbent marketing "retrieval-readiness scoring" found, but absence ≠ proof.
- **Speculation (labeled):** "retrieval net-increases description value" and the
  commoditization timeline are orchestrator synthesis, not measured claims.
