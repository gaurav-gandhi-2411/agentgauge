# AgentGauge v0.5 — Applied-AI Features + Production Platform

**Repo:** `C:\Users\gaura\ml-projects\agentgauge`
**Current shipped state:** v0.4.0, published to PyPI as `agentgauge-harness`
**Target buyers:** platform / agent-infrastructure teams at Google, Uber, Meta, and
comparable orgs running many internal MCP servers.

---

## 1. What v0.4.0 actually does today

**Surfaces:** CLI only. Plus a generated GitHub Action that posts a PR comment.
**There is no UI, no API, no daemon, no dashboard.**

| Command | Function | Validation status |
|---|---|---|
| `agentgauge diff` | Paired before/after regression harness. Runs agent tasks against both tool-description variants, reports task-success delta with bootstrap CI, decomposed into selection accuracy vs. argument accuracy. Abstains (`INSUFFICIENT_SENSITIVITY`) when CI width exceeds 2× threshold. | MDE 0.0537 at n=253; false-alarm under null 0.59%; replay determinism 100% |
| `agentgauge lint` | Deterministic schema-consistency checks over tool descriptions. | Only `type_enum_contradiction` has a measured causal effect (−13.3 to −28.9pp, 3 model families). All other rules measured null or unmeasured, and labelled as such. |
| `agentgauge eval` | Single-variant evaluation run. | Shares the `diff` harness. |
| `agentgauge audit` | Standing pre-report gate blocking measurements when task leakage, scoring-reference mismatch, degenerate metrics, or 5 other artifact classes are detected. | 8 artifact classes encoded; 17 regression tests seeded from real historical cases. |
| `agentgauge init` | Scaffolds a task file + GitHub Action. | — |
| `scan` / `fix` / `ci` / `try` | v1 legacy (the falsified 8-axis scorer). | Retained, marked legacy. |

**Corpus:** 253 tasks, including 10 real-API gold-constraint fixtures (GitHub, Stripe,
Google Calendar, Jira, Slack, Docker, Kubernetes, Twilio, AWS S3, Spotify), each
validated against live official docs — 3 of 10 had factual defects found and fixed.

**Competitive number:** the single-prompt LLM-judge alternative false-alarms on 97.1%
of clean tools (degenerate always-flag). AgentGauge's blocking tier false-alarms 0%
per tool set.

---

## 2. Gap analysis against the target buyer

| Gap | Why it blocks Google / Uber / Meta | Severity |
|---|---|---|
| **Ollama-only inference** | These orgs run their own model endpoints (Vertex, Bedrock, internal serving). A harness that cannot run against the actual agent stack measures nothing they care about. | **Blocker** |
| **No failure attribution** | `diff` reports "the server regressed 15pp." A platform team with a 40-tool server and a 12-file PR needs to know *which* description caused it. Without localization the signal is not actionable. | **Blocker** |
| **Full-eval cost per PR** | Running the harness across every tool on every PR is expensive at hundreds of servers. Needs selective triage. | High |
| **No UI / API / persistence** | No run history, no trend, no cross-team visibility, no way to integrate outside CI. | High |
| **CI-only, no production monitoring** | Regressions also arrive from model upgrades and prompt changes, not just description edits. | Medium |
| **No multi-tenancy / SSO / audit log** | Enterprise procurement requirement. | Medium (later) |

---

## 3. Two-directional framing

### 3a. Research direction — what the next paper is

The existing paper ("Tool-Description Quality Is Not One Axis") is scoped to
tool-selection regime-boundedness and is unaffected by the v2 work.

**The new paper is a methods paper the field currently lacks:**

> *Powering Agent Evaluations: Variance Structure, Measurement Artifacts, and
> Minimum Detectable Effects*

Contributions, all already measured in this repo:

1. **Variance structure of agent task outcomes.** ICC = 0.793 within (tool set, task);
   56.1% of variance is between-task; before/after task correlation r = 0.881.
   Direct consequence: repeated trials on the same task are near-worthless, and
   published agent evals that scale trials rather than tasks are systematically
   underpowered.
2. **An estimator that reaches usable power.** Paired design with common random
   numbers + task-clustered bootstrap + CUPED + O'Brien-Fleming sequential testing,
   with an ablation showing each component's contribution. MDE improves 0.433 → 0.188
   at n = 20, and reaches 0.0537 at n = 253.
3. **Eight measurement-artifact classes**, each found in real experiments in this
   repo, each with an automated detector: task/answer leakage, tool-name ceiling,
   zero-vector empty-string embedding, self-descriptive-name confound,
   subset-vs-catalog mismatch, LCG index saturation, scoring-reference mismatch,
   fixture-schema hallucination. **This is the strongest contribution** — the field
   has no standard artifact taxonomy for agent evals.
4. **Falsification record.** Four pre-registered hypotheses falsified honestly,
   including the authors' own commercial thesis.

Wave outputs below (attribution, triage) each add a further section; do not start
paper writing until Wave 2 lands.

### 3b. Product direction — what makes a platform team adopt it

Positioning: **the regression-detection layer for agent tool surfaces.** Not a
quality score, not a linter. The claim is a stated detection floor with a stated
false-alarm rate, deterministically reproducible.

Open-core:
- **OSS core (Apache-2.0):** CLI, harness, linter, audit gate, GitHub Action, model
  adapters. Adoption engine and standards play.
- **Cloud tier:** hosted run history, cross-model matrix, dashboards, trend alerts,
  team-level rollups.
- **Enterprise:** on-prem, private model endpoints, SSO, audit log, SLA.

---

## 4. Wave 1 — Unblock the enterprise path

### 1.1 Model-adapter abstraction (**highest priority in the whole spec**)

Replace the Ollama-coupled inference path with a provider interface.

- Adapters: Ollama (local), OpenAI-compatible HTTP, Anthropic Messages API, AWS
  Bedrock, Google Vertex, and a generic "custom endpoint" adapter taking a base URL
  + auth header (this is what internal enterprise serving looks like).
- Config-driven selection; no code change to switch providers.
- **Replay determinism must survive the abstraction** — cassette record/replay keyed
  on (provider, model, prompt hash). Verify the 100% determinism figure still holds
  per adapter.
- Cost accounting per run: tokens in/out, wall-clock, estimated spend, surfaced in
  the diff output. Platform teams will not adopt an eval whose cost they cannot see.

**Eval doctrine.** Task: faithful provider abstraction. Metric: replay determinism
rate per adapter (target 100%), plus agreement of harness verdicts across adapters on
a fixed fixture set. Baseline: current Ollama-only path. Ship bar: no verdict flips
attributable to the abstraction layer.

### 1.2 Failure attribution / regression localization

Given a multi-tool, multi-file change that regressed, identify which tool
description(s) caused it.

- Implement a budgeted ablation search: revert candidate subsets, re-measure,
  localize. Use the existing paired + CUPED estimator so each probe is cheap.
- Compare three strategies: (a) exhaustive single-tool ablation, (b) Shapley-style
  sampled attribution, (c) greedy bisection over the changed set.
- Output: ranked list of suspected tools with attributed effect size and CI, plus the
  measurement budget consumed.

**Eval doctrine.** Task: credit assignment. Metric: **top-1 and top-3 localization
accuracy** against known injected culprits, and **probe budget consumed** at fixed
accuracy. Baselines to beat: (i) blame the largest textual diff, (ii) blame the tool
with the most lint violations, (iii) uniform random. Ship bar: top-1 ≥ 0.70 and top-3
≥ 0.90 on injected-culprit benchmarks, at a probe budget below exhaustive ablation.
**USP:** no competing tool performs credit assignment for agent regressions at all.

---

## 5. Wave 2 — Applied-AI cost and interpretability layer

### 2.1 Predictive triage model

Running the full harness on every PR does not scale. Train a cheap predictor that
decides which changes warrant expensive evaluation.

- Features (all cheap, no inference): textual diff magnitude and type, schema-delta
  features, lint-violation deltas, tool-usage frequency, historical regression rate
  per tool, embedding shift of the description, whether required/enum fields changed.
- Label: did the full harness detect a practically significant regression.
- Training data: the existing corpus plus injected-defect runs; augment as needed.
- Ship as `agentgauge triage` — emits RUN_FULL / RUN_REDUCED / SKIP with a
  calibrated probability.

**Eval doctrine.** Task: cost-sensitive screening. Metric: **compute saved at fixed
detection recall** — report the full Pareto curve (recall retained vs. eval compute
consumed), plus calibration (reliability diagram, Brier score). Baselines to beat:
(i) run everything, (ii) random sampling at matched budget, (iii) heuristic
"diff-size threshold". Ship bar: ≥ 60% compute reduction at ≥ 95% detection recall.
**USP:** a stated cost/recall operating curve — nobody else can quote one.

### 2.2 Failure-mode clustering

The harness currently reports selection vs. argument. Platform teams need to know
*what kind* of failure.

- Cluster failure traces into interpretable modes (wrong tool from a confusable pair,
  hallucinated parameter, missing required arg, wrong enum value, malformed call,
  refusal, timeout).
- Assign labels via **multi-LLM consensus across different model families, run blind,
  with inter-judge agreement measured and calibrated on unambiguous cases.** Label
  the output as LLM-consensus, never as human ground truth. **No workflow step may
  require hand-labelling.**
- Surface as a per-run breakdown in `diff` output and in the dashboard.

**Eval doctrine.** Task: failure taxonomy assignment. Metric: cluster purity and
inter-judge agreement (Krippendorff's α or Fleiss' κ) against the consensus label
set; calibration accuracy on the unambiguous control cases. Baseline: the existing
binary selection/argument split. Ship bar: κ ≥ 0.60 across judges, and modes that
predict distinct remediation actions.

---

## 6. Wave 3 — Production surfaces

### 3.1 Persistence + REST API + daemon

- Run store (SQLite local, Postgres for hosted): runs, verdicts, effect sizes, CIs,
  audit-gate status, provider/model, cost, commit SHA.
- `agentgauge serve`: REST API over the same operations as the CLI.
- Baseline/golden-run management with versioning, so "regression vs. what" is explicit.

### 3.2 Web dashboard (the missing UI)

Single-page app served by `agentgauge serve`:
- Run history with pass/fail/abstain verdicts and effect sizes with CIs.
- Per-tool trend lines; regression alerts.
- Attribution view from Wave 1.2 — which tool caused which regression.
- Failure-mode breakdown from Wave 2.2.
- Audit-gate status per run, surfaced prominently: a run that failed the artifact
  gate must be visually distinct from a clean one.
- Cost per run and cumulative.

**Design requirement:** AgentGauge gets its own distinct logo and visual identity,
designed first and then applied consistently — favicon, header, OG preview, docs.
Do not reuse any other project's identity.

### 3.3 AgentGauge as an MCP server

Expose `lint`, `diff`, `triage`, `attribute` as MCP tools so agents and agentic IDEs
can invoke the harness directly. Dogfoods the product and is a distribution channel
inside the ecosystem it serves.

### 3.4 OpenTelemetry export

Emit runs and verdicts as OTel spans/metrics so enterprises can route into existing
observability stacks rather than adopting a new pane of glass.

---

## 7. Standing constraints

- Local Ollama by default. **No GCP or any paid provider without an explicit,
  bounded cost estimate approved in advance.**
- Never `ANTHROPIC_API_KEY` (Claude Max — pay-per-token double-billing).
- Every measured number independently verified before it enters a report or README.
- MEASURED vs. NOT MEASURED kept strictly separated everywhere.
- Eight measurement artifacts found to date; assume a ninth. Run `agentgauge audit`
  against every new result set, including all Wave 1–3 outputs.
- No workflow may depend on manual data labelling. Use multi-LLM consensus, blind,
  with agreement measured, and label it honestly as consensus.
- Every component declares its task, best-suited metric, baseline, and target margin
  **before** implementation, recorded in `reports/v0_5_eval_doctrine.md`.
- Orchestrator / executor / verifier pattern. No merges to `main` without review.
- Ensure all agents and monitors terminate cleanly — stale-wakeup loops have recurred
  across five sessions.

---

## 8. Top risks

1. **Model adapters break replay determinism.** The 100% determinism figure is a
   headline claim; a provider abstraction that introduces nondeterminism invalidates
   it. Verify per adapter before anything is built on top.
2. **Attribution may need an infeasible probe budget.** If localizing a culprit in a
   40-tool server costs more compute than a full re-eval, the feature has no value.
   Measure budget-vs-accuracy early and kill it if the curve is bad.
3. **Triage training data is thin.** 253 tasks and a few hundred injected defects may
   not support a calibrated model. If calibration fails, ship a transparent heuristic
   with a measured operating curve rather than an uncalibrated model.
4. **Ninth measurement artifact.** Each new component is a new surface for one.
5. **Scope.** Three waves is a lot. Wave 1 alone is shippable as v0.5.0 and is the
   part that unblocks enterprise evaluation; do not start Wave 3 before Wave 1's
   numbers are verified.
