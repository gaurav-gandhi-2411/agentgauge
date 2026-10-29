> DRAFT. NOT POSTED. PREREQUISITE: merge `docs/gw-truncation-correction` before posting. Links point at paths
> as they will be on main after that merge.

**Flair suggestion:** [P] Project

**Title:** [P] AgentGauge: a paired, cluster-bootstrap harness for "did my MCP tool-description change help?", with its null results

**Body:**

AgentGauge compares two variants of an MCP server by running a local agent model on the same tasks
and estimating the change in task success ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). The interesting part is the
statistics and the amount of negative evidence it ships with.

**Estimator and power.** The estimator is paired, task-clustered and uses CUPED with a bootstrap CI.
Trial-level repeats within a task carried almost no independent information (ICC=0.793), so the
allocation is 100 tasks per arm at 1 trial per task, giving a minimum detectable effect of
8.5 percentage points at 80% power ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). Under the null, 21.6% of runs
abstain with `insufficient_sensitivity` instead of reporting a verdict
([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)). A t(G-1)-adjusted interval keeps the false-alarm rate under 5% in every
cluster-count stratum, with 1.57% for fewer than 10 tasks
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
  in any of three models ([report](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/reports/v0_4_0_task1_argument_degradation.md),
  [README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).
- A failure-attribution feature is more expensive than re-running the full evaluation (1.01x to
  20.24x), so it is gated behind `--experimental` ([README](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/README.md)).
- In a pilot of ten public MCP servers, 0 of 9 with a testable confusable family were in the
  regime where better descriptions help. Small n; a lower bound ([paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)).

**A correction.** The paper's EXP-1 table reported 0%/0% for a 116-tool Google Workspace server and
read it as "catalog overwhelm". Ollama had silently truncated the roughly 7k-token tool listing at
its default 4096-token window. With the window sized, both arms score 65% (13/20), +0pp
([STATUS.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/STATUS.md), [paper](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md)). The out-of-regime label stands; the
mechanism claim is withdrawn.

**Limits.** Absolute scores depend on the judge model, pinned to llama3.1:8b, and are not
comparable across judges ([CLAUDE.md](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/CLAUDE.md)). The agent models are small local ones.

Code and reports: https://github.com/gaurav-gandhi-2411/agentgauge. Criticism of the estimator is
welcome.
