# AgentGauge — capability statement

## What it measures

`agentgauge diff` is a statistical regression harness: it answers whether a change
to an MCP server's tool schemas/descriptions caused a measurable change in real
agent task success — a hypothesis test with a bootstrap confidence interval, not a
single-number quality score.

## Headline numbers (source: committed reports, this repo)

| Metric | Value | Source |
|---|---|---|
| Minimum detectable regression, 80% power, full 253-task corpus | 5.37 percentage points | `reports/v2_5_task3_mde_completion.md` |
| Ship target (detect a 10-point regression at 80% power) | met, ~2x margin | same |
| Causal effect of a BLOCKING lint violation on real task success, 3 model families (gemma2:9b/llama3.1:8b/qwen2.5:7b) | -13.3 to -40.0 percentage points, 95% CI excludes zero in every model | `reports/v2_4_task1_blast_radius_audit.md` |
| Lint false-alarm rate, 521 tools, BLOCKING+ADVISORY combined | 4.22% | `reports/v2_1_severity_gate.md` |
| Replay determinism (identical inputs -> identical verdict) | 100%, 50/50 runs | `reports/v2_harness_evaluation.md` |

## The differentiated claim

A regression whose 95% bootstrap CI excludes zero is flagged; at the full 253-task
corpus and 80% power, that reliably means any real regression of 5.37 points or
larger. This runs deterministically — same inputs produce the same verdict every
time (`reports/v2_harness_evaluation.md`).

The alternative most teams reach for first — a single LLM-judge prompt asking "did
this get worse?" — false-alarms 97.1% of the time at 100% recall on the same test
corpus: a degenerate always-flag baseline (`reports/v2_1_cross_model_validation.md`
Task 2e). AgentGauge's linter false-alarm rate on the same class of question is
4.22%.

## Who it's for

Teams shipping internal MCP servers where agent reliability is production-critical:
a schema or description change ships, and the team needs to know — with a number,
not a vibe — whether it changed how often their agent actually completes real
tasks against that server, before the change reaches production traffic.

## Free / paid split

- **Free, Apache-2.0, CLI**: `agentgauge lint` (deterministic, no LLM calls, no
  network) and `agentgauge diff`/`eval` (harness, local Ollama by default) — the
  entire measurement methodology in this document, runnable with zero API spend.
- **Paid (not yet built)**: a hosted judge endpoint (skip local GPU/Ollama setup),
  scheduled regression runs wired into CI, and a dashboard over historical
  diff/eval results across multiple servers. No pricing or ship date is stated
  here — this section describes the intended product boundary, not a shipped SKU.
