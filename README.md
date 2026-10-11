# AgentGauge

[![CI](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml/badge.svg)](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agentgauge-harness.svg)](https://pypi.org/project/agentgauge-harness/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://pypi.org/project/agentgauge-harness/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/LICENSE)

**AgentGauge tells you whether a change to your MCP server's tool descriptions changed how well an
agent uses it.** `agentgauge diff` runs the same task set against a "before" and an "after" server,
compares task success with a bootstrap confidence interval, and says so plainly when it does not
have enough data to call it (`INSUFFICIENT_SENSITIVITY`). `agentgauge lint` is a fast, zero-LLM
defect check for tool schemas and descriptions; it is a secondary utility, and most of its rules
have no validated effect on task success. Live runs need a local [Ollama](https://ollama.com) model
(default `gemma2:9b`); the tooling is calibrated on 7-9B open models only. The papers in this
repository are unreviewed research drafts (see below).

## 60-second demo

No model, GPU, API key or network is used: the demo replays 24 bundled, pre-recorded `gemma2:9b`
trials per arm.

```bash
pip install agentgauge-harness
agentgauge demo
```

```
agentgauge demo: replaying 24 recorded gemma2:9b trials per arm (no model, GPU,
keys or network used)

before (n=24 trials)
  selection accuracy:          0.667
  argument accuracy | correct: 1.000
  joint success rate:          0.667

after (n=24 trials)
  selection accuracy:          1.000
  argument accuracy | correct: 1.000
  joint success rate:          1.000

before cost: replay mode -- no live cost to report.
after cost: replay mode -- no live cost to report.

INSUFFICIENT_SENSITIVITY: Delta point estimate is +0.333, but the 95% CI
[+0.125, +0.500] is wider than 2x the regression threshold (0.050) -- this run
does not have enough trials to reliably distinguish a real regression of this
size from sampling noise. Descriptions may or may not be the bottleneck for
this tool set; this result does not resolve that question. Increase trial count
or widen the threshold.

What happened: with identical tool names, only the descriptions changed --
joint success went 0.67 -> 1.00 (delta +0.33, 95% CI [+0.12, +0.50], 24 tasks).
Why this verdict: 24 tasks is too few for the CI to be narrower than 2x the
0.05 threshold, so the harness declines to call it either way; a real gate
needs ~100 tasks per arm.

Run it live on the same pair: `agentgauge demo --extract demo_files`, then
`agentgauge diff demo_files/before_server.py demo_files/after_server.py --tasks
demo_files/tasks.json` (needs Ollama + gemma2:9b).
```

The point estimate is large, but with 24 tasks the harness will not call it. The pair is a
constructed illustration (six near-synonym tools, vague vs. clear descriptions), not a benchmark; a
first pair with REST-style names showed no effect because the model read the answer off the names.
Recording details:
[`agentgauge/demo/PROVENANCE.md`](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/agentgauge/demo/PROVENANCE.md).
Note that `agentgauge lint` reports nothing on either server: static rules cannot see this difference.

## Install

```bash
pip install agentgauge-harness     # the PyPI name; the command is `agentgauge`
agentgauge --version
```

From source: `git clone https://github.com/gaurav-gandhi-2411/agentgauge && cd agentgauge && pip install uv && uv sync`.

## Quickstart

```bash
# 1. Replay the demo pair with no model (no dummy paths needed)
agentgauge demo --extract demo_files
agentgauge diff --replay-before demo_files/replay_before.json --replay-after demo_files/replay_after.json

# 2. Lint the demo servers (no LLM)
agentgauge lint demo_files/before_server.py

# 3. Run the same comparison live (needs `ollama pull gemma2:9b`)
agentgauge diff demo_files/before_server.py demo_files/after_server.py --tasks demo_files/tasks.json

# 4. Your own server: scaffold a tasks file and a CI workflow, then edit the tasks
agentgauge init
agentgauge diff before_server.py after_server.py --tasks agentgauge_tasks.json
```

- **Write your own tasks.** Never quote the gold tool name or a required literal value in the task
  text; that makes selection trivial. The scaffold ships one placeholder task. Plan on the order of
  100 tasks per arm, one trial each: repeat trials on one task add little, more distinct tasks add
  power (variance and MDE table below). The demo's 24 tasks return `INSUFFICIENT_SENSITIVITY`.
- **`--mock` cannot give a verdict.** The mock provider returns one canned reply, so `diff`/`eval`
  refuse it with exit code 2. It is for plumbing tests only.
- **Exit codes:** `0` ok, `1` regression verdict or a blocking lint finding, `2` usage error, failed
  pre-report audit, or the model backend is unreachable.
- **Audit gate.** `diff`/`eval` first check task leakage, ceiling/floor, degenerate metrics and
  scoring consistency; a failing check blocks the result.
- **CI workflow from `init`** is lint-only by default. Set the repository variable
  `AGENTGAUGE_LIVE_DIFF=true` to opt in to a live `diff` job (it installs Ollama and pulls a model on
  the runner; slow on CPU-only runners).
- **Other providers:** `--provider-config <yaml>` selects a hosted adapter instead of Ollama (example
  configs are in the repo under `configs/`; see [model adapters](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/history/model-adapters.md)).
- **Legacy:** `scan`, `fix`, `ci`, `try` are the v1 eight-axis score, which did not predict task
  success in this project's own study; unsupported surface.

## Measured numbers

Each figure names its sample, source file and whether it reproduces without a GPU ("clone" = a
checkout of this repository; scripts and fixtures are not in the wheel).

| Number | What it measures | n | 95% CI | Source | Reproduce without GPU |
|---|---|---|---|---|---|
| +0.333 joint-success change (0.667 to 1.000) | Bundled demo pair, recorded `gemma2:9b` | 24 tasks per arm, 1 trial | [+0.125, +0.500]; verdict `INSUFFICIENT_SENSITIVITY` | `agentgauge/demo/replay_*.json` | Yes: `agentgauge demo` |
| 4.22% (22 of 521 tools; 0 BLOCKING) | Tools flagged by BLOCKING + ADVISORY lint rules in the repo's "clean" corpus | 521 tools, 21 tool sets | Wilson [2.80%, 6.31%] (upper bound is above 5%) | `evals/fixtures/v2_1_severity_gate.json` | Yes, clone: `python scripts/v2_1_severity_gate_measurement.py` |
| 50 of 50 identical outputs | The diff engine returns byte-identical results for identical input (says nothing about model determinism) | 50 reruns of one input | n/a | `evals/fixtures/v2_false_alarm_determinism.json` | Yes, clone: `python scripts/v2_false_alarm_and_determinism.py` |
| 97.1% (169 of 174 clean tools flagged) | A single-prompt `llama3.1:8b` judge as a linter substitute; flags every defect (138 of 138) but almost every clean tool too | 174 clean tools; 138 defect cases | Wilson [93.5%, 98.8%] | `evals/fixtures/v2_1_llm_linter_baseline.json` | No (needs the 8B judge); the fixture can be re-tallied |
| gemma2:9b +0.022, llama3.1:8b +0.055, qwen2.5:7b +0.004 | Joint-success change when empty descriptions are replaced by authored, constraint-revealing ones | 253 tasks, 1 trial, per model | [-0.004, +0.051], [+0.023, +0.089], [-0.021, +0.029] | `evals/fixtures/v2_5_argument_degradation_summary.json` | No (live models); the stored per-task results can be re-analysed |

gemma2:9b and qwen2.5:7b are indistinguishable from zero; llama3.1:8b shows a small
positive effect (point estimate above the harness's 0.05 threshold, CI excludes zero). These CIs
treat tasks as independent although they are nested in 52 tools.

**Causal effect of the `type_enum_contradiction` defect.** Injecting this defect (a type flipped or an
enum dropped) into an oracle-described server lowers joint task success. n=30 tasks per model
(2 defect types x 15 tasks), spread over only 6 tool sets, so the tool set is the independent unit:

| Model | Effect | Cluster-bootstrap 95% CI | t(5) cluster-robust 95% CI | Task-level CI (ignores clustering) |
|---|---|---|---|---|
| gemma2:9b | -37.8 pp | [-66.7, -8.3] | [-87.2, +11.7] | [-55.6, -21.1] |
| llama3.1:8b | -33.3 pp | [-55.9, -2.9] | [-77.4, +10.7] | [-53.3, -13.3] |
| qwen2.5:7b | -16.7 pp | [-34.4, -2.8] | [-40.9, +7.6] | [-33.3, 0.0] |

The direction is consistent across models, but with 6 clusters the t-based interval includes zero for
every model, so the size of the effect is not pinned down. These are synthetic injections into
hand-built mock servers. Source: `evals/fixtures/type_enum_contradiction_clustered.json`, produced
by `scripts/type_enum_clustered_ci.py` (clone; pure Python, seed 42, 10,000 resamples; `--check`
verifies the committed file). An earlier README quoted a pooled figure that mixed in a defect type
with no measurable effect; it is withdrawn.

### Variance, power and false-alarm figures (re-measured with per-trial seeds)

<!-- BEGIN recalibration-metrics (generated) -->

**Re-measured with per-trial seeds** (replaces the fixed-seed figures; those are retired).

- Source: `evals/fixtures/recalibration_seedfix/results.json`
- Tool sets in the new data: 44 (`call_constraints_server`, `call_constraints_server_fixed`, `call_constraints_server_oracle`, `call_constraints_v2_server`, `call_constraints_v2_server_fixed`, `call_constraints_v2_server_oracle`, `confusable_server`, `confusable_server_fixed`, `confusable_server_oracle`, `echo_server`, `exp1_blazickjp_arxiv_mcp_server_mirror`, `exp1_datalayer_jupyter_mcp_server_mirror`, `exp1_datalayer_jupyter_mcp_server_mirror_oracle`, `exp1_dataojitori_nocturne_memory_mirror`, `exp1_stickerdaniel_linkedin_mcp_server_mirror`, `grounded_server`, `grounded_server_fixed`, `grounded_server_oracle`, `mediocre_server`, `mediocre_server_fixed`, `p2a_arm_a`, `p2a_arm_guardb`, `p2a_arm_oracle`, `p2a_internal_proxy_mirror`, `q3_arm_a`, `q3_arm_o`, `q3_real_server`, `q6_arm_a`, `q6_arm_f_doc_guarded`, `q6_real_server`, `rw1_arm_a`, `rw1_arm_guardb`, `rw1_arm_oracle`, `rw1_github_mirror`, `rw2_arm_a`, `rw2_aws_iam_mirror`, `t18_fixer_server`, `t18_fixer_server_set2`, `t18_oracle_server`, `t18_oracle_server_set2`, `t18_q2b_server`, `t18_q2b_server_set2`, `t18_vague_server`, `t18_vague_server_set2`); trials used: 5535; dropped as partial/incomplete: none.
- 'Old, same subset' restricts the original fixed-seed corpus to those tool sets, so the paired comparison is like-for-like; 'old, all' is the original 44 tool sets.
- CIs are 95%, cluster bootstrap over tool sets (variance table) and Wilson (rates). With few tool sets the intervals are degenerate or optimistic; read n first.

| Quantity | Old, all tool sets | Old, same subset as new | New (per-trial seeds) | New - old (paired) |
|---|---|---|---|---|
| Zero-variance share of (tool set, task) groups, % | 90.3 [84.9, 94.1] | 90.3 [84.9, 94.1] | 82.9 [75.9, 88.2] | -7.4 [-10.7, -4.5] |
| ICC(1) | 0.793 [0.721, 0.866] | 0.793 [0.721, 0.866] | 0.731 [0.653, 0.809] | -0.063 [-0.117, -0.019] |
| Between-task share of variance, % | 56.1 [46.4, 65.9] | 56.1 [46.4, 65.9] | 50.8 [41.7, 60.7] | -5.2 [-9.8, -1.2] |
| Between-trial (within-task) share, % | 18.0 [11.5, 24.5] | 18.0 [11.5, 24.5] | 23.5 [16.4, 30.4] | 5.5 [1.6, 10.2] |
| Baseline success rate | 0.775 [0.705, 0.834] | 0.775 [0.705, 0.834] | 0.789 [0.718, 0.847] | 0.014 [0.002, 0.026] |
| sigma_task | 0.359 [0.313, 0.401] | 0.359 [0.313, 0.401] | 0.334 [0.286, 0.379] | -0.025 [-0.038, -0.012] |
| resid_sd (within-task trial noise) | 0.139 [0.107, 0.176] | 0.139 [0.107, 0.176] | 0.169 [0.139, 0.203] | 0.030 [0.011, 0.050] |

**Correction to an earlier diagnosis.** The original corpus drew every repeat trial with the same sampler seed, and an October 2026 audit concluded that this explained the high share of groups with zero variance. Re-measuring with per-trial seeds shows that diagnosis was mostly wrong. The zero-variance share moved from 90.3 [84.9, 94.1]% to 82.9 [75.9, 88.2]% (paired change -7.4 [-10.7, -4.5] points) and ICC(1) from 0.793 [0.721, 0.866] to 0.731 [0.653, 0.809]: about 83% of (tool set, gold tool) groups still score identically on every repeat when the seed varies.

That is not because the model repeats itself: of the 597 zero-variance groups, 235 issued the identical tool call on every trial and 362 issued different calls that scored the same (345 differ only in arguments, 17 in the selected tool). Source: `output_diversity.json`.

All 17 groups whose selected tool differs are all-fail (0 all-pass with a non-gold tool); a wrong tool always scores 0. The identical scores in the argument-only groups (299 all-pass, 46 all-fail) come from a lenient argument check: of 343 all-pass tasks whose arguments differ across trials, 134 have no registered constraint at all (any call scores 1.0), 115 are constrained but the arguments that differ are not, and only 94 vary in an argument the scorer checks. A score of 1.0 therefore means "right tool plus the checked identifiers", not "fully correct call". Source: `zero_variance_audit.json`.

Practical reading: repeat trials on the same task still add little independent information (ICC above), so spend effort on more distinct tasks, not more trials per task. The coarse outcome metric, not sampler determinism, is what limits the variance structure.

| Tasks per arm x trials | MDE, old constants | MDE, new constants (gold grouping) | MDE, new constants (true-task grouping) | New-constant sensitivity range |
|---|---|---|---|---|
| 100 x 1 | 0.0848 | 0.0878 | 0.0839 | 0.0768 to 0.1001 |
| 253 x 1 | 0.0537 | 0.0562 | 0.0539 | 0.0485 to 0.0639 |

Ship target (detect a 10-point regression, i.e. 0.10, at 80% power with 100 tasks x 1 trial), evaluated on the new gold-grouping constants: **met** (MDE 0.0878). The target is met at the point estimate but not across the sensitivity range (0.0768 to 0.1001): with resid_sd at its upper bootstrap quantile the MDE exceeds it. MDE is a Monte-Carlo simulation of a Gaussian task model, not a measurement on a corpus; it has no CI of its own.
MDE simulations per cell: 2000.

| Cluster stratum | False alarm, old (all) | False alarm, new | Abstention, old (all) | Abstention, new |
|---|---|---|---|---|
| **All strata** | 10/2200 = 0.45% [0.25, 0.83] | 7/2200 = 0.32% [0.15, 0.66] | 572/2200 = 26.00% [24.21, 27.87] | 616/2200 = 28.00% [26.16, 29.91] |
| <10 tasks | 7/700 = 1.00% [0.49, 2.05] | 7/700 = 1.00% [0.49, 2.05] | 262/700 = 37.43% [33.92, 41.07] | 183/700 = 26.14% [23.02, 29.52] |
| 10-29 tasks | 3/1300 = 0.23% [0.08, 0.68] | 0/1300 = 0.00% [0.00, 0.29] | 310/1300 = 23.85% [21.61, 26.24] | 431/1300 = 33.15% [30.65, 35.76] |
| >=30 tasks | 0/200 = 0.00% [0.00, 1.88] | 0/200 = 0.00% [0.00, 1.88] | 0/200 = 0.00% [0.00, 1.88] | 2/200 = 1.00% [0.27, 3.57] |

Null-comparison caveat: Repeats within a tool set share one trial pool, so the Wilson intervals treat correlated comparisons as independent and are optimistic.

Input hashes (sha256): rows `dd349057f781`; old `7d7c0caa02e8`; run_status `3450be6ec81c`

Rendered at commit: `64efda0`

<!-- END recalibration-metrics -->

## Limitations

- **Calibrated on local open models.** All measurements use `gemma2:9b`, `llama3.1:8b` and
  `qwen2.5:7b` through Ollama on one machine. Nothing here is validated on frontier or hosted models.
- **Judge-dependent scores.** Rubric-judged scores are not comparable across judge models (pinned:
  `llama3.1:8b`).
- **Stubbed mirrors, not real servers.** The corpus is hand-built mock MCP servers and mirrors of
  real ones; tasks and gold labels were largely authored by AI assistants, and 3 of the 10 newest
  fixtures contained a factual error when checked against vendor docs
  (`reports/v2_5_task2_fixture_validation.md`).
- **Small and pilot samples.** The causal-effect figures use 6 tool sets and 30 to 45 tasks per model;
  the regime study behind the papers used a 10-server pilot from one source.
- **You need many tasks (~100 per arm).** The table above gives the MDE at 100 and 253 tasks. With fewer, expect
  `INSUFFICIENT_SENSITIVITY`; the demo shows this at 24. Writing and validating tasks is the real
  cost, not compute.
- **Hosted APIs are not deterministic.** `--seed` applies to Ollama only; hosted adapters ignore it,
  and their replay determinism is measured on recorded responses, not live calls.
- **Research drafts are not peer-reviewed.** Their claims are being re-verified (below).

## Research drafts

Two drafts live under `docs/` and are **under revision: not peer-reviewed, claims being
re-verified, no arXiv version exists.** They are kept for transparency, not as established results.

- Draft 1, tool-description quality as a regime-bounded effect: `docs/paper/`.
- Draft 2, power analysis and measurement-artifact screening for tool-description evaluation: `docs/paper2/`.

Earlier framing that these experiments ran under a pre-registered, frozen protocol was wrong for
most of them; see
[`docs/history/research-drafts.md`](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/history/research-drafts.md).
History and the per-rule lint measurements (with corrections) are in
[`docs/history/`](https://github.com/gaurav-gandhi-2411/agentgauge/tree/main/docs/history).

## Development

```bash
bash scripts/verify.sh   # ruff, mypy, pytest + coverage (LLM always mocked, no network)
uv run pytest            # tests only
```

See [`CHANGELOG.md`](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/CHANGELOG.md) and [`RELEASING.md`](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/RELEASING.md).

## License

Apache License 2.0 - see [LICENSE](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/LICENSE).
