# AgentGauge

**AgentGauge is a deterministic defect linter and a statistical regression harness for MCP tool
descriptions — and is the research program behind
["Tool-Description Quality Is Not One Axis"](docs/paper/latex/main.pdf), a study of where fixing
tool descriptions helps, does nothing, or backfires.**

[![CI](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml/badge.svg)](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml)

## `agentgauge lint` vs. an LLM judge — measured, not asserted

The deterministic linter is the shipped, production-ready surface (v0.3.0). Both rows below are
measured on the same clean corpus and defect-injection corpus in this repo — not cherry-picked.

| | Per-tool-set false-alarm rate (BLOCKING checks, 21 clean tool sets) | Recall (defect-injection corpus) |
|---|---|---|
| **`agentgauge lint`** (zero LLM calls) | **0%** | **100%** (`type_enum_contradiction`, `required_references_missing_property`) |
| Single-prompt LLM judge (llama3.1:8b) | **97.1%** (169/174 clean tools flagged — a degenerate always-flag baseline) | 100% (not a meaningful number given the false-alarm rate) |

The LLM baseline's 100% recall is not a real signal: a judge that flags 97.1% of genuinely clean
tools will trivially also flag 100% of defective ones. Spot-checked directly (not assumed): the
model hallucinated a fabricated claim about a schema property being "missing" when the same
prompt's JSON schema plainly contained it — confirmed as a real model failure, not a measurement
bug. Full methodology: `reports/v2_1_linter_recall_fix.md`, `reports/v2_1_severity_gate.md`,
`reports/v2_1_cross_model_validation.md` §Task 2e.

---

> **v2.2.** A predictive-validity study (`reports/predictive_validity_study.md`) found that v1's
> 8-axis LLM-judged quality score does not predict real agent task success by a margin surviving
> both multiple-comparison correction and controlling for description length. v2 rebuilt around
> what that study showed actually works: a deterministic defect linter and a statistical
> regression harness. v2.1 rebuilt the harness's estimator after measuring that trial-level
> repeats within a task carry almost no independent information (ICC=0.793) — the v2 estimator's
> minimum detectable effect was optimistic, not conservative. Pairing + task-clustering + CUPED
> cuts the MDE at n=20 tasks/arm from 43.3 to 18.8 points (2.3×) — still short of the 10-point ship
> target, reported as a real gap, not rounded away. Every number in this README is measured in
> this repo — see `reports/v2_product_readiness.md` for the full consolidated methodology and
> what's measured vs. assumed. v1's `scan`/`fix`/`ci`/`try` commands still exist in the code but
> are not the recommended product surface; `lint`/`eval`/`diff`/`init` are.

---

## The paper

**["Tool-Description Quality Is Not One Axis: A Regime Analysis of Where It Helps and Where It
Backfires"](docs/paper/latex/main.pdf)** — arXiv:XXXX.XXXXX *(TO FILL after upload)*.

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
[`docs/research/frozen_protocol.md`](docs/research/frozen_protocol.md). Every figure in the
paper traces to a committed, hash-verified fixture:
[`docs/paper/evidence_table.md`](docs/paper/evidence_table.md). `./scripts/verify.sh` runs the
same test suite (LLM always mocked, no network, no credentials) that gates every
research-program pull request.

### Building the PDF

[`docs/paper/paper.md`](docs/paper/paper.md) is the canonical source; the LaTeX build in
[`docs/paper/latex/`](docs/paper/latex/) is a maintained mirror (CI fails if a commit changes
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

## What this actually measures (numbers, not adjectives)

Two components, each evaluated on the task it actually does — never on correlation. Full
methodology and every number's provenance: `reports/v2_1_linter_recall_fix.md`,
`reports/v2_1_severity_gate.md`, `reports/v2_1_estimator_rebuild.md`,
`reports/v2_1_cross_model_validation.md`.

### 1. Deterministic linter (`agentgauge lint`) — zero LLM calls

Detects five classes of description-vs-schema defect (a schema-required parameter that references
a nonexistent property; description text describing a parameter as boolean when its schema type
isn't; identifier-like tokens in a description that don't match any real parameter; a schema
property that was renamed while the description still refers to the old name; near-duplicate tool
names). Severity is tiered: **BLOCKING** checks fail CI, **ADVISORY** checks are surfaced but don't
gate — because a naive single-tier gate would reject 66.67% of genuinely clean tool sets.

| Metric | Measured value | How |
|---|---|---|
| False-alarm rate, per tool set, BLOCKING-only (21 tool sets) | **0%** | `reports/v2_1_severity_gate.md` — clears the <10% target decisively |
| False-alarm rate, per tool, BLOCKING+ADVISORY combined (521 tools) | 4.22% | same, still <5% |
| Recall on injected `contradictory_required_claim` / `type_flipped` / `enum_dropped` defects | **100%** | `reports/v2_linter_evaluation.md` §2d |
| Recall on injected `param_renamed` defects (48 cases) | **83.3%** overall — 82.9% when the renamed property is single-word (was 2.9% before this check existed) | `reports/v2_1_linter_recall_fix.md` |
| Recall vs. raw JSON-Schema structural validation baseline | Linter beats it on every defect type — baseline scores **0%** | `reports/v2_linter_evaluation.md` §2e |
| Recall vs. single-prompt LLM baseline (llama3.1:8b, 174+138 sampled cases) | Linter beats it once precision is counted — the LLM baseline scores 100% recall but **97.1% false-alarm rate** (a degenerate always-flag baseline; spot-checked to confirm it's genuine model hallucination, not a scoring bug) | `reports/v2_1_cross_model_validation.md` §Task 2e |

### 2. Regression harness (`agentgauge diff`) — paired, task-clustered, CUPED-adjusted bootstrap test

Compares real task-success rate between two tool-set variants at the **server level** (paired on
task, cluster-robust across tasks, CUPED-adjusted), decomposed into tool-selection accuracy and
argument-construction accuracy.

| Metric | Measured value | How |
|---|---|---|
| Minimum detectable effect at n=20 tasks/arm, 80% power | **18.8 percentage points** (down from 43.3 pre-redesign — a 2.3× improvement) | `reports/v2_1_estimator_rebuild.md` |
| **Ship target — detect a 10-point regression at 80% power, ≤20 tasks/arm** | **NOT MET** (gap: 8.8 points, ≈47% further variance reduction needed) | same — reported as a real gap, not rounded away |
| Minimum detectable effect at n=50 tasks/arm, 80% power | 11.9 percentage points | same |
| False-alarm rate under the null (2200 resampled comparisons, 44 real historical tool sets) | **0.59%** (still <5%) | same — not uniform: 1.71% on tool sets with <10 tasks vs. 0.07% on ≥10 tasks (the well-documented "few clusters" cluster-robust-inference effect) |
| Abstention rate under the null (correctly declining to call a verdict) | 21.6% (down from 71.5% pre-redesign — the harness is far more decisive) | same |
| Cross-model replication (gemma2:9b, llama3.1:8b, qwen2.5:7b) | Selection-accuracy-flat pattern **replicates across all 3 models** (0.938–1.000 every cell); argument-accuracy-degrades pattern **inconclusive** at the sample size tested (n=16/model, diluted by unconstrained tools) | `reports/v2_1_cross_model_validation.md` |

**What's not yet measured:** determinism was not independently re-verified for the new estimator
(inherits the prior 100%/50-run result via unchanged PRNG code); the full 32-task/trials≥3
cross-model replication and the full-corpus LLM baseline were reduced to bounded samples for
infrastructure-reliability reasons — see `reports/v2_product_readiness.md` §2 for the complete list
and §4 "what would falsify this."

---

## Install

```bash
git clone https://github.com/gaurav-gandhi-2411/agentgauge
cd agentgauge
pip install uv && uv sync
```

---

## Quickstart (under 5 minutes)

```bash
# 1. Lint your server — zero LLM cost, exits 1 on a BLOCKING finding
agentgauge lint path/to/your_server.py

# 2. Scaffold a starter anti-tautology tasks file + GitHub Action
agentgauge init

# 3. Edit agentgauge_tasks.json with real tasks for your tools (never quote the
#    gold tool name or a required literal value in the task text -- that makes
#    selection trivial regardless of description quality)

# 4. Compare two variants of your server before merging a description change
agentgauge diff before_server.py after_server.py --tasks agentgauge_tasks.json
```

`agentgauge lint` needs no LLM at all — try it right now against the bundled example fixture,
which reproduces a real defect this linter was built to catch:

```bash
agentgauge lint examples/call_constraints_server_fixed.py
```

```
6 BLOCKING violation(s) (fails CI):
  x  ping_server: 'host' is in the schema's required list but is not a key in properties
  x  get_server_info: 'hostname' is in the schema's required list but is not a key in properties
  ...
```

`agentgauge diff` needs a live agent model (Ollama, default `gemma2:9b`) or a `--mock`/`--replay`
run for testing without inference. See `reports/predictive_validity_study.md`'s `blind_tasks.py`
for worked examples of anti-tautology task authoring.

---

## v1 (legacy — not the recommended surface)

`agentgauge scan`/`fix`/`ci`/`try` implement an 8-axis LLM-judged correlational score. The
predictive-validity study found none of the 8 axes predicts real task success by a margin
surviving both multiple-comparison correction and length-control (`reports/
predictive_validity_study.md`, `reports/v2_axis_triage.md`). The commands still exist and still
work — deleting working code that some users may already depend on wasn't in scope for this
rebuild — but `lint`/`eval`/`diff`/`init` are the supported product surface going forward.

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
and CLI-integrated. v2.1 rebuilt the harness's estimator (paired + task-clustered + CUPED) after
measuring that the v2 estimator's MDE was optimistic (ICC=0.793 within task) — 2.3× improvement,
but the 10-point-regression-at-n=20 ship target is not yet met. Remaining, explicitly not yet done:
the full 32-task/trials≥3 cross-model replication (a 16-task/trials=1 reduced version ran; the
selection-flat half of the pattern replicated across 3 models, the argument-degrades half is
inconclusive at that sample size) and the full-corpus single-prompt LLM baseline (a 174+138
stratified sample ran instead) — `reports/v2_product_readiness.md` tracks exactly what's measured
vs. assumed.

---

## Project structure

```
agentgauge/
  client.py       # MCP client: stdio + HTTP/SSE, introspect, call tools
  providers.py    # Provider protocol + OllamaProvider + MockProvider
  tasks.py        # Task generator: sample args from JSON schema
  runner.py       # Agent runner: LLM selects tool + constructs args, N trials
  scorer.py       # v1 rubric scoring: static analysis + LLM-as-judge (legacy surface)
  linter.py       # v2: deterministic defect linter, zero LLM calls
  harness.py      # v2: bootstrap-CI regression harness, MDE simulation
  constraints.py  # v2: anti-tautology blind-task constraint checking
  report.py       # Rich text report renderer
  cli.py          # typer CLI: lint / eval / diff / init (v2) + scan / fix / ci / try (v1)
examples/
  echo_server.py  # Minimal MCP server (good + bad tools) for local demos
tests/            # pytest; LLM always mocked; no network; no paid calls
```

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
