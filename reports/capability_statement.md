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
| Causal effect of a BLOCKING lint violation on real task success (gemma2:9b -25.2pp / llama3.1:8b -28.9pp / qwen2.5:7b -13.3pp) | -13.3 to -28.9 percentage points, 95% CI excludes zero in every model | `reports/v2_4_task1_blast_radius_audit.md` |
| Lint false-alarm rate, 521 tools, BLOCKING+ADVISORY combined | 4.22% | `reports/v2_1_severity_gate.md` |
| Replay determinism (identical inputs -> identical verdict) | 100%, 50/50 runs | `reports/v2_harness_evaluation.md` |
| Effect of improved tool descriptions on argument construction, 253 tasks x 3 model families (gemma2:9b/llama3.1:8b/qwen2.5:7b), MDE=5.37pp | no practically significant effect in any model | `reports/v0_4_0_task1_argument_degradation.md` |

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

A separate live measurement (253 tasks, 3 model families, 1 trial/task, MDE=5.37pp)
found no practically significant effect from improving tool descriptions on
argument-construction accuracy in any of the 3 models tested
(`reports/v0_4_0_task1_argument_degradation.md`). Reported as measured, not
smoothed into a general "better descriptions help" claim: the one causal effect
this repo can support is BLOCKING-violation detection (row above), not a general
claim about description quality.

## A structural negative result: regression localization is uneconomical

v0.5.0 built and honestly evaluated a failure-attribution feature: given a multi-tool server
already known (via `agentgauge diff`) to have regressed, identify *which* changed tool's
description caused it — the natural next question after detection. **It does not ship.** Not
because it doesn't work — accuracy was fixed — but because fixing accuracy makes it cost more
than the thing it exists to make unnecessary, at every tested configuration. This is reported here
as a methods contribution in its own right, not buried in a superseded PR comment.

### The finding

| Metric | Value | Source |
|---|---|---|
| Per-probe minimum detectable effect at `n_tasks=24` (the original probe budget) | ≥16.91-18.18pp — worse than the harness's own server-level MDE (5.37pp at n=253), not better | `reports/v0_5_probe_power_fix.md` §2-3 |
| Smallest `n_tasks` clearing an 8pp per-probe MDE target | 128 (7.34pp measured; n=112 misses by 0.12pp) | same |
| Accuracy at that `n_tasks` | Both tested localization strategies clear the ship bar (top-1≥70%, top-3≥90%) at every single-culprit candidate-set size ≥10 tools | same, §4 |
| Cost vs. simply re-running the full 253-task evaluation, at that same `n_tasks` | **1.01x-20.24x more expensive**, at EVERY tested configuration — the cheapest case in the entire study (4 changed tools, the cheapest strategy) is already a coin flip against just re-measuring everything | same, §5 |
| Crossover to cheaper-than-re-evaluating-everything | ~2-4 changed tools, at the `n_tasks` accuracy requires — below the scale at which localization has any practical purpose | same |

### Why this is structural, not a tuning miss

Minimum detectable effect scales as the classic `1/√n_tasks` law (confirmed numerically:
`18.18pp × √24 ≈ 89`; `5.37pp × √253 ≈ 85` — the same constant, within measurement noise, at two
very different sample sizes). Reliable localization needs a real per-probe task sample; that
sample **is** the cost a localizer exists to avoid paying by not re-running everything. Two
regimes were tested and both fail one bar:

- **Low `n_tasks` (cheap, unreliable)**: at the original `n_tasks=24`, individual probes are cheap
  enough that most localization strategies genuinely do cost less than a full re-eval up to
  realistic candidate-set sizes (~10-20 changed tools) — but per-probe MDE (≥16.91pp) is too weak
  to reliably localize anything below that effect size, and accuracy collapses with candidate-set
  size for the strategy whose probe budget doesn't scale with `n` (`reports/v0_5_mde_discrepancy.md`
  §4c: 93%→47% top-1 as candidate-set size grows 4→40).
- **High `n_tasks` (reliable, uneconomical)**: raising `n_tasks` to 128 fixes accuracy
  completely — but each individual probe then costs 256 trial-equivalents, more than half a full
  re-evaluation on its own, and any strategy needing more than 1-2 probes (i.e. any realistic
  localization problem with more than a couple of candidate tools) loses to just re-measuring the
  whole server.

No `n_tasks` value tested, and none implied by the `1/√n` scaling law, clears both bars at once.
This is not a search problem (more compute, a smarter search strategy) — the entire genus of
"probe a subset, measure a delta, repeat" localization approaches this repo tested pays a real,
irreducible statistical cost per probe that a full re-evaluation pays exactly once. Closing this
gap would need a fundamentally different signal source (something cheaper than re-running task
trials to estimate an effect size), not a better search over the same signal.

### Two adversarial audits before trusting the result

Ten measurement artifacts were found and fixed across this project's development before this
finding was reported, including one directly on this feature's own path
(`reports/v0_5_mde_discrepancy.md`: the benchmark's synthetic probe noise floor measured at 34% of
the harness's own calibrated reference — fixed, standing audit check added). A second, secondary
finding from the same investigation (`sampled_shapley`'s accuracy improving with candidate-set
size, counter to naive intuition) was independently audited before being trusted rather than
accepted at face value or dismissed as suspicious — confirmed real and arithmetically consistent
with the strategy's own probe-budget design, not an eleventh artifact
(`reports/v0_5_shapley_scaling_audit.md`). The uneconomical-cost finding above survived that same
level of scrutiny: it is reported as measured, not assumed.

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
