# AgentGauge — Phase-1 buyer/competitive research (findings, web-sourced & adversarially verified)

> Generated 2026-06-14 via deep-research harness (5 search angles, 22 sources, 102 claims →
> 25 verified → 18 confirmed / 7 refuted → 6 synthesized findings). Each finding carries the
> adversarial vote. **Findings only — no positioning/roadmap.** Citations are as-gathered by the
> research agents; arXiv IDs not independently re-resolved.

## Bottom line (the reframe, answered)
The central question is **frequency-of-regime**, not durability. Evidence is **mixed, leaning
favorable on value-per-hit, but the load-bearing frequency question is UNMEASURED.** Bad tool
descriptions are pervasive, and vendors (Anthropic, GitHub) explicitly name confusable/overlapping
tools as a real selection-failure driver — but **no source measures how often real catalogs hit the
specific "confusable-at-scale" regime** (near-duplicates unresolvable from names + good docs), and the
buyer segment (large internal/custom under-documented catalogs) has **essentially no public evidence**.

## Confirmed findings
**F1 — Bad descriptions are pervasive; the confusable-at-scale *regime frequency* is not measured. [high · 3-0]**
Empirical study of 856 tools / 103 real MCP servers (23 official incl. Anthropic/GitHub/PayPal/Microsoft/
Airbnb + 80 community): **56% fail to state purpose clearly; 97.1% have ≥1 description "smell"**
(arXiv:2602.14878). BUT this measures *description quality*, a different axis from *near-duplicate
confusability*. The only benchmark proving the confusable regime is harmful (ToolChoiceConfusion,
arXiv:2606.06284v1) is **fully synthetic** and explicitly offers "no empirical measurement of how
frequently this confusion regime occurs in practice."

**F2 — The retrieval-layer trend RELOCATES description value into the search index (does not kill it). [high · 3-0 / 2-1]**
Anthropic Tool Search Tool loads tools on-demand and "matches against names and descriptions, so clear,
descriptive definitions improve discovery accuracy"; BM25/regex variants "search tool names, descriptions,
argument names…"; selection accuracy "degrades significantly once you exceed 30-50 tools"
(anthropic.com/engineering/advanced-tool-use). GitHub dynamic toolsets ship ~4 base tools to avoid models
"confused by the sheer number of tools" (github-mcp-server#275). Retrieval quality is "fundamentally
bounded by the informativeness of tool descriptions" (arXiv:2603.20313); LLM-based description *expansion*
yields SOTA retrieval gains (Tool-DE, arXiv:2510.22670). **Caveat:** usage-driven embeddings (Tool2Vec)
can bypass descriptions — but need usage data that under-documented internal catalogs lack.

**F3 — Vendors explicitly name confusable/overlapping tools as a dominant selection-failure driver. [high · 3-0]**
Anthropic: "most common failures are wrong tool selection… especially when tools have similar names like
notification-send-user vs notification-send-channel"; "too many tools or overlapping tools can distract
agents." GitHub: 101 tools / 64.6k tokens caused "tool confusion" (motivation for dynamic toolsets, #275).
Qualitative/experience-based, **not** a measured failure-rate distribution.

**F4 — Description quality is a real accuracy lever (value-per-hit), per first-party vendor data. [high · 3-0]**
Anthropic: "even small refinements to tool descriptions can yield dramatic improvements"; Claude Sonnet 3.5
hit SOTA on SWE-bench Verified "after precise refinements to tool descriptions." First-party self-report;
supports **value-per-hit (durability)**, NOT frequency.

**F5 — Off-the-shelf retrievers & frontier LLMs fail at tool selection at scale — with qualifiers that cut against AgentGauge. [high · 3-0 / 2-1]**
ToolRet (7,615 tasks / 43,215 tools): best IR model nDCG@10 only 33.83; retrieved-vs-oracle toolsets drop
GPT-3.5 pass rate ~10pts (ACL 2025 Findings 1258). WildToolBench (arXiv:2604.06185): Grok-4 24.07% "wrong
name" error; specialized models >30%. **Qualifiers against:** (1) these are large-corpus retrieval from NL
queries, harder than small-catalog selection with good docs; (2) **WildToolBench attributes failures to
intent/context understanding, NOT confusable catalogs** — i.e., not the regime a description-fixer fixes.

**F6 — Confusable tools occur in real public servers, but the biggest authors self-fix in-house. [high · 3-0]**
GitHub MCP team: "two similar tools that used to be confused often — list_issues and search_issues"; they run
an offline-eval pipeline with confusion matrices and "tweak their descriptions to minimize confusion."
Framing is past-tense and self-fixed. **Buyer signal: demand validation AND competitive threat — the largest
catalogs build the fix internally.**

## Refuted (did NOT survive adversarial review)
- "Clear names + good docs already resolve selection (RW1/RW2-consistent)" — **0-3 refuted** (so don't lean
  on RW1/RW2 as a general external rule either).
- "Description augmentation reliably pays off" — **0-3 refuted**; augmentation regressed performance in
  16.67% of cases (arXiv:2602.14878). Median gain only +5.85pp.
- "Filesystem near-duplicates degrade retrieval (MRR 0.84-0.89)" — 0-3; "confusable regime persists on
  strong agents in ToolChoiceConfusion" — 0-3; "100-tool near-duplicate catalog → 0.83 success" — 1-2;
  cross-server create_issue collision — 1-2. (Most were weakened or context-dependent under scrutiny.)

## What we could NOT determine (load-bearing gaps)
1. **Frequency-of-regime in the buyer segment — UNMEASURED.** No public data on what fraction of large
   (50+ tool), under-documented, internal/custom catalogs hit the near-duplicate confusable-at-scale regime.
   RW1/RW2's negative public-server findings are the only data points either way; enterprises don't publish
   internal tool inventories.
2. **Does the retrieval trend NET expand or shrink the buyer?** It relocates description value into the index
   (expands "who needs good descriptions"), but vendor-shipped retrieval + usage-driven embeddings may absorb
   the fix into the platform (commoditization risk).
3. **Willingness-to-pay / does anyone pay a 3rd party?** GitHub/Anthropic self-fix in-house; no WTP signal
   surfaced among agent-platform or internal-tooling teams.
4. **Competitive landscape under-resourced** — no concrete MCP linting/registry/observability/quality-scanner
   products were surfaced for head-to-head comparison; a dedicated competitive scan is still needed.

## Key sources (primary)
arXiv:2602.14878 (856-tool description-quality study) · arXiv:2606.06284v1 (ToolChoiceConfusion, synthetic) ·
arXiv:2603.20313 (retrieval bounded by description quality) · arXiv:2510.22670 (Tool-DE description expansion) ·
ACL 2025 Findings 1258 (ToolRet) · arXiv:2604.06185 (WildToolBench) ·
anthropic.com/engineering/{advanced-tool-use, writing-tools-for-agents} · github.com/github/github-mcp-server#275 ·
github.blog offline-eval-of-github-mcp-server · github.com/openai/openai-agents-python#464
