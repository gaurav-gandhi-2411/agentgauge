> DRAFT. NOT POSTED. PREREQUISITE: merge `docs/gw-truncation-correction` before posting. Links point at paths
> as they will be on main after that merge.

**Flair suggestion:** [P] Project

**Title:** [P] AgentGauge: a paired, cluster-bootstrap harness for "did my MCP tool-description change help?", with its null results

**Body:**

AgentGauge compares two variants of an MCP server by running an agent model (a local Ollama model by
default; other providers are supported) on the same tasks and estimating the change in task success
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). This post covers the
statistics and the negative results the repo reports.

**Estimator and power.** The estimator is paired, task-clustered and uses CUPED with a bootstrap CI.
Trial-level repeats within a task carried almost no independent information (ICC=0.793), so the
allocation is 100 tasks per arm at 1 trial per task, giving a minimum detectable effect of
8.5 percentage points at 80% power ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)),
assuming you supply about 100 tasks of your own
([report](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/reports/v2_2_optimal_allocation.md)).
The harness can abstain with `insufficient_sensitivity` instead of reporting a verdict. The 21.6%
abstention rate in the README is from the earlier v2.1 estimator, before the move to 100 tasks per arm:
the v2.1 estimator abstained in 21.6% of runs on 44 historical tool sets (2200 bootstrap null
comparisons), so it is not a measurement at the 100-task allocation
([report](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/reports/v2_1_estimator_rebuild.md)).
A t(G-1)-adjusted interval keeps the false-alarm rate under 5% in every
cluster-count stratum, with 1.57% (11 of 700 null comparisons on resampled historical data) for fewer
than 10 tasks
([report](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/reports/v2_2_few_clusters_correction.md)).

**Audit gate.** `diff` and `eval` pass through `agentgauge audit` first (task leakage,
ceiling/floor verdicts, degenerate metrics, scoring-reference consistency), and a failing check blocks
the result from being reported ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). Each check was seeded from a real artifact
found in this project, for example a scoring bug that had inflated one effect to -76.7 to -80.0pp
before it was corrected to a null ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).

**Null and negative results, as a feature.**

- Only one lint rule has a validated causal effect on task success (-13.3 to -28.9pp, three model
  families); two others are measured nulls ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).
- An argument-degradation study over 253 tasks (MDE 0.0537) found no practically significant effect
  in any of three models; llama3.1:8b's CI excludes zero at +0.055 but does not clear the 0.05
  practical-significance threshold
  ([report](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/reports/v0_4_0_task1_argument_degradation.md),
  [README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).
- A failure-attribution feature is more expensive than re-running the full evaluation (1.01x to
  20.24x), so it is gated behind `--experimental` ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).
- In a pilot of ten public Python MCP servers, 7 had a testable confusable family; counting 2 earlier anchor
  servers, 0 of those 9 were in the regime where better descriptions help. "In the regime" means the
  shipped descriptions fail at least one contested task and a hand-written oracle description recovers
  it. Small n; a lower bound, because the sampled public servers are more often documented than internal or custom servers
  ([paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)).

**A correction.** The paper's EXP-1 table reported 0%/0% for a 116-tool Google Workspace server and
read it as "catalog overwhelm". Ollama had silently truncated the roughly 7k-token tool listing at
its default 4096-token window. With the window sized, both arms score 65% (13/20), +0pp, in a small
rerun (4 tasks x 5 trials on gemma2:9b)
([STATUS.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md), [paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)). The out-of-regime label stands; the
mechanism claim is withdrawn. The paper was corrected in place with a dated correction note and the raw
fixtures were kept. The window fix (sizing `num_ctx` to the prompt, plus a guard that raises on
truncation) is on the unmerged branch
[fix/ollama-num-ctx](https://github.com/gaurav-gandhi-2411/agentgauge/blob/fix/ollama-num-ctx/agentgauge/providers.py);
it is not on main yet, so the shipped tool does not size the window itself.

**Limits.** Rubric scores from `agentgauge scan` (the legacy v1 interface) depend on the judge model,
pinned to llama3.1:8b, and are not comparable across judges
([CLAUDE.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/CLAUDE.md)). `diff` effects are
task success measured on the specific agent models tested (gemma2:9b, llama3.1:8b, qwen2.5:7b) and may
differ on other models. The agent models are small local ones.

Code and reports: https://github.com/gaurav-gandhi-2411/agentgauge. Criticism of the estimator is
welcome.
