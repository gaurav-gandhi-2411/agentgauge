# AgentGauge

**AgentGauge is a statistical regression harness that measures whether a change to your MCP
server's tool descriptions actually changed agent task success — plus a fast, deterministic defect
linter as a secondary utility. It is also the research program behind
["Tool-Description Quality Is Not One Axis"](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/latex/main.pdf), a study of where fixing
tool descriptions helps, does nothing, or backfires.**

[![CI](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml/badge.svg)](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml)

## `agentgauge diff` — measured, not asserted

The harness is the primary interface: `agentgauge lint`'s static rules mostly do not have a
validated effect on real task success on their own (see the per-rule table below) — the harness is
what actually measures whether a change helped. Every number below is measured in this repo, not
estimated.

| Metric | Measured value | Report |
|---|---|---|
| Minimum detectable effect, 100 tasks/arm × 1 trial/task, 80% power | **8.5 percentage points** | `reports/v2_2_optimal_allocation.md` |
| Ship target (detect a 10-point regression at 80% power) | **MET** | same |
| False-alarm rate under the null, by cluster-count stratum | **<5% in every stratum** (<10 tasks: 1.57%; 10–29: 0.08%; ≥30: 0.00%) | `reports/v2_2_few_clusters_correction.md` |
| Replay determinism (identical inputs → identical verdict) | **100%** (50/50 runs) | `reports/v2_harness_evaluation.md` |
| Abstention rate under the null (`INSUFFICIENT_SENSITIVITY`, correctly declining to call a verdict rather than over-claim) | **21.6%** | `reports/v2_1_estimator_rebuild.md` |
| **Causal chain — does a BLOCKING linter violation actually cause task failure?** (previously assumed, now measured, re-verified on a freshly rebuilt instance) | **Yes: -13.3 to -28.9pp** task success, CI excludes zero in all 3 model families tested (gemma2:9b/llama3.1:8b/qwen2.5:7b) | `reports/v2_4_task1_blast_radius_audit.md` |
| Single-prompt LLM-judge baseline (an alternative to this harness/linter) | **97.1% false-alarm rate** / 100% recall — a degenerate always-flag baseline, spot-checked to confirm genuine model hallucination, not a scoring bug | `reports/v2_1_cross_model_validation.md` §Task 2e |

### Every lint rule's measured task-success effect — including the nulls

`agentgauge lint`'s rules are NOT all equally validated. Severity tier tracks measured causal
impact × precision (v2.3 re-tiering), not just false-alarm rate — a rule with no measured effect
is labeled as such below, not presented as if it were proven:

| Rule | Tier | Measured causal effect on task success | False-alarm | Recall |
|---|---|---|---|---|
| `type_enum_contradiction` | **BLOCKING** | **-13.3 to -28.9pp** (gemma2:9b -25.2, llama3.1:8b -28.9, qwen2.5:7b -13.3), CI excludes zero in all 3 models | 0% | 100% |
| `required_references_missing_property` | INFO (demoted from BLOCKING) | **0.0pp in all 3 models — a measured null**, despite perfect precision | 0% | 100% |
| `described_not_in_schema` (catches `param_renamed`) | ADVISORY | **~0pp in all 3 models — a measured null** (corrected in v2.3 from a falsely-reported -76.7 to -80.0pp: a scoring bug looked up a pre-rename parameter name against post-rename arguments) | 23.81% | 81.2% |
| `param_possibly_renamed` | ADVISORY | Not independently measured (fires alongside `described_not_in_schema`, not separated in the causal-chain design) | 0.77%/tool | part of the 81.2% combined |
| `name_collision` | ADVISORY | **Not measured** (no defect-injection instance targets this check) | 47.62% | n/a |
| `required_not_mentioned` | INFO (opt-in) | Not tested for causal effect (demoted on a different basis: fires at nearly the same rate on real professional docs as on bad synthetic ones) | n/a | 94.1% |

Full methodology: `reports/v2_1_linter_recall_fix.md`, `reports/v2_1_severity_gate.md`,
`reports/v2_linter_evaluation.md` (`required_not_mentioned`'s 94.1% recall),
`reports/v2_3_task2_retiering.md`, `reports/v2_4_task1_blast_radius_audit.md`.

---

## v0.5.0 — model adapters (the headline feature this release)

`agentgauge diff`/`eval` are no longer Ollama-only. Six provider adapters share one config-driven
interface — switch providers with no code change:

| Adapter | What it targets |
|---|---|
| `ollama` | Local Ollama (the original, still the default) |
| `anthropic` | Anthropic Messages API |
| `openai_compatible` | Any OpenAI-compatible HTTP endpoint |
| `bedrock` | AWS Bedrock |
| `vertex` | Google Vertex AI |
| `custom_endpoint` | Generic base-URL + auth-header endpoint (internal/enterprise serving) |

| Metric | Measured value | Report |
|---|---|---|
| Replay determinism, per adapter | **100%** on all 6 adapters (20/20 replays each, byte-identical output, identical harness verdict) | `reports/v0_5_wave1_report.md` §2 |
| Verdict fidelity across the abstraction layer | **Zero verdict flips** attributable to the adapter/config layer | same |
| Cost/timing accounting | Live in `diff`/`eval` output (text and JSON), correctly distinguishing `n/a`/replay-mode from a real zero-cost run | `reports/v0_5_wave1_report.md` §4 |

**Scope, stated plainly**: determinism for the four non-local adapters (Anthropic, Bedrock, Vertex,
any paid custom endpoint) is measured against recorded/mocked wire-format responses, not live paid
calls (no paid-provider spend without an approved bounded estimate, per this repo's standing cost
constraint) — this proves the adapter code path (parsing, hashing, cassette I/O) adds no
nondeterminism given an identical response; it does not measure a live provider's own response
variance, which remains open. See `agentgauge/provider_config.py` and `configs/` for example YAML
configs — point `--provider-config` at one to switch providers.

---

## Experimental — failure attribution (research only, NOT shipped for production use)

`agentgauge attribute` exists in the CLI and is gated `--experimental`, off by default, because it
is **measured uneconomical**, not because it doesn't work — accuracy is genuinely solved; the
numbers below are why it isn't a product surface:

| Metric | Measured value | Report |
|---|---|---|
| Accuracy at the probe power needed for reliable localization (`n_tasks=128`) | Both tested strategies clear the ship bar (top-1≥70%, top-3≥90%) at every single-culprit candidate-set size ≥10 tools | `reports/v0_5_probe_power_fix.md` §4 |
| Cost vs. simply re-running the full evaluation | **1.01x–20.24x more expensive**, at every tested configuration — the cheapest case in the whole study (4 changed tools) is already a coin flip against a full re-eval | same, §5 |
| Crossover to cheaper-than-re-evaluating-everything | **~2-4 changed tools** — below the scale at which localization has any practical use | same |
| Multi-culprit (2-3 simultaneous regressions — the realistic multi-file-PR shape) | Does not clear the accuracy ship bar at any tested configuration | same, §4 |

**Why it isn't fixable by tuning**: minimum detectable effect scales as `1/√n_tasks` — reliable
localization needs real per-probe task volume, and that volume is exactly the cost a localizer
exists to avoid paying. Lower `n_tasks` is cheap but statistically unreliable; higher `n_tasks` is
reliable but each probe alone costs a meaningful fraction of a full corpus re-evaluation. No
`n_tasks` value clears both the accuracy and cost bars at once (`reports/v0_5_probe_power_fix.md`
§5-6) — a structural finding, recorded for the methods paper as a negative result
(`reports/capability_statement.md`), not a bug to be fixed in a later release.

The code, benchmarks, and every measurement behind this table remain in the repo — nothing was
deleted. Research use only, via direct library import
(`agentgauge.attribution`/`agentgauge.attribution_benchmark`) or the scripts under `scripts/`; run
`agentgauge attribute --help` for the gate, or `agentgauge attribute` (no flag) to see the cost
finding printed at the command line.

---

> **v2.2.** A predictive-validity study (`reports/predictive_validity_study.md`) found that v1's
> 8-axis LLM-judged quality score does not predict real agent task success by a margin surviving
> both multiple-comparison correction and controlling for description length. v2 rebuilt around
> what that study showed actually works: a deterministic defect linter and a statistical
> regression harness. v2.1 found the v2 estimator's minimum detectable effect was optimistic —
> trial-level repeats within a task carry almost no independent information (ICC=0.793) — and cut
> MDE at n=20 tasks/arm from 43.3 to 18.8 points (2.3×) via pairing + task-clustering + CUPED,
> still short of the 10-point ship target. **v2.2 closed that gap**: the ICC finding itself implied
> the fix — reallocate trials to tasks (1 trial/task, 100 tasks/arm) instead of repeating trials on
> fewer tasks. Measured MDE at that allocation: **0.0848 — ship target met.** v2.2 also measured,
> for the first time, whether a BLOCKING linter violation actually *causes* agent task failure
> (previously assumed, never tested): it does — a 13.3–28.9 point drop in real task success,
> replicated across three model families. **v2.3 audited a v2.2 ADVISORY-defect finding before
> trusting it and found the effect was ~77–100% a scoring artifact** (the checker looked up a
> pre-rename parameter name against post-rename arguments, scoring correct agent responses as
> failures) — corrected, the ADVISORY (`param_renamed`) effect is a clean null in all three models,
> not the originally-reported 76.7–80.0pp drop. v2.3 re-tiered the linter by the corrected numbers:
> `required_references_missing_property` demoted BLOCKING→INFO (zero measured task-success effect
> in every model); `described_not_in_schema`'s false-alarm rate improved 28.57%→23.81% via real
> precision fixes but did not clear the promotion bar. **v2.4 audited the blast radius of that
> scoring bug**: only `param_renamed` was ever affected (the other four defect-injection classes
> never rename a schema key — confirmed from source, not assumed), and the ICC/variance-
> decomposition/rho/MDE-calibration numbers above all trace to a 5,535-trial corpus the bug never
> touched — no recomputation needed. The one surviving BLOCKING claim was re-measured on a freshly
> rebuilt instance and holds (**-13.3 to -28.9pp**, unchanged). v2.4 also shipped `agentgauge audit`:
> a standing pre-report gate (task/answer leakage, ceiling/floor, degenerate metrics, and — the
> class this exact bug belongs to — scoring-reference consistency) wired into `diff`/`eval` so a
> failing check blocks the result from being reported as a measurement, and repositioned the
> package around the harness (`diff` is now the primary interface; `lint` a secondary utility — see
> the per-rule table above). **v2.4 also expanded the gold-constraint task pool** from 62 to 253
> tasks across 10 real-API domains (GitHub, Stripe, Google Calendar, Jira, Slack, Docker,
> Kubernetes, Twilio, AWS S3, Spotify), closing the sample-size ceiling that left the
> argument-degradation cross-model question underpowered. **v2.5 found the audit gate's own
> scoring-reference-consistency check (the guard against the exact bug v2.3/v2.4 found) had a gap
> in the shipped product code path itself** — `agentgauge diff`/`eval` ran live inference before
> checking a user's task file against the actually-connected schema, not after — closed by
> reordering to a schema-only pre-check that runs before any inference (`reports/v2_5_task1_shipped_fix.md`).
> **v2.5 also found that 3 of the 10 new real-API fixtures had a hallucinated fact** (GitHub's
> `state_reason` enum was missing a real 4th value, Stripe modeled an optional field as required
> under the wrong name, a Kubernetes naming regex allowed an invalid leading character) — all three
> independently re-verified against live official API docs and fixed in place, logged as
> measurement artifact #8, and closed with a new standing `agentgauge audit` check,
> `check_enum_schema_fidelity` (`reports/v2_5_task2_fixture_validation.md`). **The MDE grid is now
> complete across the full 253-task corpus: 0.0537 at 80% power** (`reports/v2_5_task3_mde_completion.md`)
> — roughly half the 0.10 ship target, up from 0.0848 at the previous 100-task allocation.
> **v0.4.0 closed the loop**: the argument-degradation question is now live-measured at that power
> across all 3 model families — a real, adequately-powered null (no model clears the 0.05
> practical-significance threshold), not the old n=62 "inconclusive"
> (`reports/v0_4_0_task1_argument_degradation.md`). Every
> number in this README is measured in this repo — see `reports/v2_product_readiness.md` for the
> full consolidated methodology and what's measured vs. assumed. v1's `scan`/`fix`/`ci`/`try`
> commands still exist in the code but are not the recommended product surface;
> `diff`/`eval`/`lint`/`init` are.

---

## The paper

**["Tool-Description Quality Is Not One Axis: A Regime Analysis of Where It Helps and Where It
Backfires"](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/latex/main.pdf)** — arXiv:XXXX.XXXXX *(TO FILL after upload)*.

Tool-description quality is widely treated as a broadly-applicable lever for agent tool-use —
but it is not a single better/worse axis: the precision that helps an agent disambiguate within
a family of confusable tools is orthogonal to, or actively harmful for, context-rich selection
and for tool retrieval. The effect is real but **regime-bounded**, not a general law — the paper
maps the exact boundary (catalog density, headroom, documented source) and finds it rare in a
pilot sample of real servers.

### The practitioner takeaway: the Two-Condition Regime Test

Before investing in description tooling on a given MCP server, ask two questions:

1. **Fail** — does the agent fail at least one contested task under the server's real, shipped
   descriptions?
2. **Recover** — if it fails, does a hand-written, ground-truth description recover it?

If (1) is NO, the agent already resolves the task from context — there's nothing to fix. If (1)
is YES but (2) is also NO, the failure isn't description-shaped (functional overlap, catalog
overwhelm) — description tooling won't help either. Only if both are YES is the server inside
the regime where better descriptions help. This is the same two-step check the paper's own
results were produced with, not a separately validated general instrument.

### Reproducibility

Every experiment in the paper runs under a single frozen evaluation protocol — one classifier,
one judge, one generator family, pre-registered thresholds:
[`docs/research/frozen_protocol.md`](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/research/frozen_protocol.md). Every figure in the
paper traces to a committed, hash-verified fixture:
[`docs/paper/evidence_table.md`](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/evidence_table.md). `./scripts/verify.sh` runs the
same test suite (LLM always mocked, no network, no credentials) that gates every
research-program pull request.

### Building the PDF

[`docs/paper/paper.md`](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/docs/paper/paper.md) is the canonical source; the LaTeX build in
[`docs/paper/latex/`](https://github.com/gaurav-gandhi-2411/agentgauge/tree/main/docs/paper/latex) is a maintained mirror (CI fails if a commit changes
one without the other). To rebuild the PDF:

```bash
export PATH="$HOME/.local/tectonic:$PATH"
cd docs/paper/latex
tectonic main.tex
```

**Scope note:** this is a pilot-scale research artifact — synthetic fixtures, two real-server
mirrors, and a 10-server pilot sample — not a validated product claim. The paper's own Section 8
states plainly what is and isn't supported by the evidence.

---

## Additional measured detail

Headline harness and per-rule numbers are above. A few more measured results that don't fit that
table:

| Metric | Measured value | Report |
|---|---|---|
| Linter false-alarm rate, per tool, BLOCKING+ADVISORY combined (521 tools) | 4.22%, still <5% | `reports/v2_1_severity_gate.md` |
| Linter recall vs. raw JSON-Schema structural validation baseline | Linter beats it on every defect type — baseline scores **0%** | `reports/v2_linter_evaluation.md` §2e |
| Cross-model replication, causal chain (gemma2:9b, llama3.1:8b, qwen2.5:7b) | BLOCKING effect significant in **all 3 model families**; qwen2.5:7b measurably more robust to `type_enum_contradiction` specifically than the other two | `reports/v2_4_task1_blast_radius_audit.md` |
| Cross-model replication, argument-degradation (a *separate* question from the causal chain above — does description quality fix argument construction?) | **Measured, real null.** Full 253-task corpus, 1 trial/task (MDE=0.0537), live on all 3 models: gemma2:9b Δ+0.022 95% CI [-0.004,+0.051]; llama3.1:8b Δ+0.055 CI [+0.023,+0.089] (CI excludes zero but doesn't clear the 0.05 practical-significance threshold); qwen2.5:7b Δ+0.004 CI [-0.021,+0.029]. No model shows a practically significant effect — this is an adequately-powered null, not an underpowered "inconclusive" | `reports/v0_4_0_task1_argument_degradation.md` |

**What's not yet measured:** an independent fuzz-test of the shipped
`agentgauge/constraints.py`/`agentgauge diff`/`agentgauge eval` product path's
scoring-reference-consistency exposure (the class that caused the v2.3 ADVISORY scoring bug) is
now closed in the CLI itself, not just guarded after the fact: v2.5 moved the `agentgauge audit`
schema check to run *before* any live inference, and it is covered by integration-level regression
tests exercising the real `diff`/`eval` commands end-to-end (`reports/v2_5_task1_shipped_fix.md`) —
not yet independently fuzz-tested against arbitrary, adversarially-malformed user task files, which
remains open — see `reports/v2_product_readiness.md` for the complete list.

---

## Install

```bash
pip install agentgauge-harness
agentgauge --version
```

The PyPI distribution is named `agentgauge-harness` (the name `agentgauge` was
already taken); the installed CLI command is still `agentgauge`.

For contributing or running from source:

```bash
git clone https://github.com/gaurav-gandhi-2411/agentgauge
cd agentgauge
pip install uv && uv sync
```

---

## Quickstart (under 5 minutes)

```bash
# 1. Scaffold a starter anti-tautology tasks file + GitHub Action
agentgauge init

# 2. Edit agentgauge_tasks.json with real tasks for your tools (never quote the
#    gold tool name or a required literal value in the task text -- that makes
#    selection trivial regardless of description quality)

# 3. Compare two variants of your server before merging a description change --
#    THIS is the number that matters: did the change move real task success?
agentgauge diff before_server.py after_server.py --tasks agentgauge_tasks.json

# 4. (Optional) fast, zero-LLM-cost static check -- exits 1 on a BLOCKING finding.
#    Only one rule has a validated causal effect (see the per-rule table above);
#    `diff` above is what actually tells you whether a change helped.
agentgauge lint path/to/your_server.py
```

`agentgauge diff` needs a live agent model (Ollama, default `gemma2:9b`) or a `--mock`/`--replay`
run for testing without inference. See `reports/predictive_validity_study.md`'s `blind_tasks.py`
for worked examples of anti-tautology task authoring. Every `diff`/`eval` run passes through
`agentgauge audit` first (task leakage, ceiling/floor, degenerate metrics, scoring-reference
consistency) — a failing check blocks the result from being reported, rather than silently
shipping a bad measurement.

```bash
# Point at a different provider with --provider-config instead of --model -- no code change.
# See configs/provider.*.yaml for one example per adapter (ollama/anthropic/openai_compatible/
# bedrock/vertex/custom_endpoint).
agentgauge diff before_server.py after_server.py --tasks agentgauge_tasks.json \
  --provider-config configs/provider.anthropic.yaml
```

`agentgauge lint` needs no LLM at all — try it right now against the bundled example fixture,
which demonstrates the re-tiering story directly: this file's only defects are
`required_references_missing_property` and `required_not_mentioned`, both of which measured a null
causal effect on task success (the per-rule table above) and are demoted to INFO — so the default,
CI-gating view is clean:

```bash
agentgauge lint examples/call_constraints_server_fixed.py
```

```
No violations found.
```

```bash
# --show-info surfaces the demoted, non-gating findings anyway (still 0% false-alarm,
# just no longer BLOCKING now that they're measured to have zero task-success effect)
agentgauge lint examples/call_constraints_server_fixed.py --show-info
```

```
13 INFO-severity hint(s) (off by default):
  -  ping_server: 'host' is in the schema's required list but is not a key in properties
  -  get_server_info: 'hostname' is in the schema's required list but is not a key in properties
  ...
```

---

## v1 (legacy — not the recommended surface)

`agentgauge scan`/`fix`/`ci`/`try` implement an 8-axis LLM-judged correlational score. The
predictive-validity study found none of the 8 axes predicts real task success by a margin
surviving both multiple-comparison correction and length-control (`reports/
predictive_validity_study.md`, `reports/v2_axis_triage.md`). The commands still exist and still
work — deleting working code that some users may already depend on wasn't in scope for this
rebuild — but `diff`/`eval`/`lint`/`init` are the supported product surface going forward.

---

## Development

```bash
# Run all checks (ruff, mypy, pytest + coverage)
bash scripts/verify.sh

# Run tests only
uv run pytest

# Lint the bundled echo server (zero LLM cost)
agentgauge lint examples/echo_server.py
```

---

## Roadmap

v1's 8-axis scoring is complete but methodologically falsified as a predictor of task success
(`reports/predictive_validity_study.md`). v2's linter and regression harness are built, measured,
and CLI-integrated. v2.1 rebuilt the harness's estimator (paired + task-clustered + CUPED) and
found the v2 estimator's MDE was optimistic (ICC=0.793 within task) — the 10-point-regression
ship target was not yet met at the allocation tested (n=20 tasks/arm, 5 trials/task). **v2.2
closed that gap** by reallocating to 100 tasks/arm at 1 trial/task (MDE=0.0848 — ship target
met) and fixed the few-clusters false-alarm concentration v2.1 found (t(G-1)-adjusted CI, <5% in
every stratum). v2.2 also measured, for the first time, that BLOCKING linter violations actually
cause agent task failure (previously assumed) — and that ADVISORY violations cause a *larger*
drop, in every one of the three model families tested (gemma2:9b, llama3.1:8b, qwen2.5:7b).
v2.3 audited the largest v2.2 finding before trusting it (a scoring bug had inflated an ADVISORY
effect to -76.7/-80.0pp; corrected to a clean null) and re-tiered the linter by the corrected
numbers. **v2.4 audited that bug's full blast radius**: confirmed only one of five defect-injection
classes was ever affected (the other four never rename a schema key — verified from source), traced
the ICC/variance/rho/MDE-calibration constants to a corpus the bug never touched (no recomputation
needed), and re-measured the one surviving BLOCKING claim on a freshly rebuilt instance (holds:
-13.3 to -28.9pp, unchanged). v2.4 shipped `agentgauge audit` — a standing pre-report gate encoding
every measurement-artifact class found during this project's development (task/answer leakage,
ceiling/floor, degenerate metrics, and the scoring-reference-consistency class the v2.3 bug
belongs to) as an automated check wired into `diff`/`eval`, with a regression test per class seeded
with the real historical case — and repositioned the package around the harness (`diff` primary,
`lint` secondary, every lint rule labeled with its measured causal effect or lack of one).
**v0.4.0 closed the last open item**: the argument-degradation cross-model question (separate from
the causal-chain question above) is now measured, not inconclusive — the 10-fixture corpus expansion
this section once flagged as "in progress" landed in v2.4/v2.5 (253 real tasks, all validated
against live official API docs), and a live 3-model measurement at that corpus's full power
(MDE=0.0537) found a real, adequately-powered null: no model shows a practically significant effect
from better tool descriptions on argument construction (`reports/v0_4_0_task1_argument_degradation.md`).
**v0.5.0 ships model adapters** (six providers, 100% replay determinism, config-driven — see the
section above) as the release headline. It also built and honestly evaluated a failure-attribution
feature (localize which tool description caused a measured regression): accuracy was fixed (both
strategies clear the ship bar at realistic candidate-set sizes), but the cost of doing so — 1.01x
to 20.24x a full re-evaluation, at every tested configuration — means it is **not shipped as a
product surface**, gated `--experimental` and off by default (see the section above and
`reports/capability_statement.md` for the negative-result writeup). Ten measurement artifacts were
found and fixed across this project's development, each with a standing `agentgauge audit` check
seeded from the real historical case.
Every product claim in this README is now measured — `reports/v2_product_readiness.md` tracks the
complete, current MEASURED vs. NOT MEASURED breakdown.

---

## Project structure

```
agentgauge/
  client.py                 # MCP client: stdio + HTTP/SSE, introspect, call tools
  providers.py               # Provider protocol + 6 adapters (ollama/anthropic/
                              # openai_compatible/bedrock/vertex/custom_endpoint) + MockProvider
  provider_config.py         # config-driven provider selection (YAML, see configs/)
  cassette.py                # record/replay for Provider.chat() -- proves replay determinism
                              # survives the adapter abstraction
  tasks.py                   # Task generator: sample args from JSON schema
  runner.py                  # Agent runner: LLM selects tool + constructs args, N trials
  scorer.py                  # v1 rubric scoring: static analysis + LLM-as-judge (legacy surface)
  linter.py                  # deterministic defect linter, zero LLM calls -- secondary utility
  harness.py                 # bootstrap-CI regression harness, MDE simulation -- PRIMARY interface
  constraints.py             # anti-tautology blind-task constraint checking
  audit.py                   # pre-report measurement-validity gate (task leakage, ceiling/floor,
                              # degenerate metrics, scoring-reference consistency, probe-variance
                              # calibration, ...) -- ten measurement-artifact classes, each with a
                              # standing check seeded from the real historical case
  attribution.py             # failure attribution strategies (exhaustive/Shapley/bisection) --
                              # EXPERIMENTAL, gated `agentgauge attribute --experimental`, not a
                              # recommended product surface (see the section above)
  attribution_benchmark.py   # injected-culprit benchmark generator for attribution -- research use
  report.py                  # Rich text report renderer
  cli.py                     # typer CLI: diff / eval / lint / init (primary surface) +
                              # attribute (experimental, gated) + scan / fix / ci / try (v1, legacy)
examples/
  echo_server.py  # Minimal MCP server (good + bad tools) for local demos
configs/          # example provider-config YAML files for each of the 6 adapters
tests/            # pytest; LLM always mocked; no network; no paid calls
```

---

## License

Apache License 2.0 — see [LICENSE](https://github.com/gaurav-gandhi-2411/agentgauge/blob/main/LICENSE).
