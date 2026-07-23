# AgentGauge

**AgentGauge is a deterministic defect linter and a statistical regression harness for MCP tool
descriptions — and is the research program behind
["Tool-Description Quality Is Not One Axis"](docs/paper/latex/main.pdf), a study of where fixing
tool descriptions helps, does nothing, or backfires.**

[![CI](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml/badge.svg)](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml)

> **v2.** A predictive-validity study (`reports/predictive_validity_study.md`) found that v1's
> 8-axis LLM-judged quality score does not predict real agent task success by a margin surviving
> both multiple-comparison correction and controlling for description length — every axis was
> either degenerate (zero variance) or explainable by description length alone. v2 is a rebuild
> around what that study showed actually works: detecting named defects, and testing whether a
> change caused a measurable success-rate regression. Every number below is measured in this
> repo — see `reports/v2_linter_evaluation.md` and `reports/v2_harness_evaluation.md` for the
> full methodology. v1's `scan`/`fix`/`ci`/`try` commands still exist in the code but are not the
> recommended product surface; `lint`/`eval`/`diff`/`init` are.

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
methodology and every number's provenance: `reports/v2_linter_evaluation.md`,
`reports/v2_harness_evaluation.md`.

### 1. Deterministic linter (`agentgauge lint`) — zero LLM calls

Detects four classes of description-vs-schema defect (a schema-required parameter that references
a nonexistent property; description text describing a parameter as boolean when its schema type
isn't; identifier-like tokens in a description that don't match any real parameter; near-duplicate
tool names). Measured on this repo's fixtures:

| Metric | Measured value | How |
|---|---|---|
| False-alarm rate, per tool, on a 21-tool-set clean corpus (521 tools) | **3.45%** | `reports/v2_linter_evaluation.md` §2c |
| False-alarm rate, per tool **set** (≥1 flag anywhere), same corpus | 66.67% | reported alongside — a CI gate keyed to "any flag" would be noisier than the per-tool number suggests |
| Recall on injected `contradictory_required_claim` / `type_flipped` / `enum_dropped` defects (276 total injected, 21 base tool sets) | **94–100%** | `reports/v2_linter_evaluation.md` §2d |
| Recall on injected `param_renamed` defects | **22.9%** overall — 76.9% when the renamed property is multi-word, **2.9%** when single-word | same, measured cause, not glossed over |
| Recall vs. raw JSON-Schema structural validation baseline | Linter beats it on every defect type; the baseline scores **0%** (all injected defects are semantically, not syntactically, invalid) | `reports/v2_linter_evaluation.md` §2e |

### 2. Regression harness (`agentgauge diff`) — bootstrap-CI hypothesis test

Compares real task-success rate between two tool-set variants, decomposed into tool-selection
accuracy and argument-construction accuracy (measured separately — a joint metric cannot see the
common real-world case where selection is unaffected but argument construction degrades).

| Metric | Measured value | How |
|---|---|---|
| False-alarm rate under the null (2200 resampled comparisons of 44 real historical tool sets against themselves) | **0%** | `reports/v2_harness_evaluation.md` §3c — but 71.5% of those correctly abstain (`INSUFFICIENT_SENSITIVITY`) rather than confidently confirm no-change; only 28.5% are confident correct nulls |
| Replay determinism (50 repeated runs, identical input) | **100%** | §3d |
| Minimum detectable effect at n=50 trials/arm, 80% power | **27–35 percentage points** | §3b — this is the honest number, not a marketing one: at realistic CI trial budgets, only a large regression is reliably caught |
| Minimum detectable effect at n=5–10 trials/arm, 80% power | **47–75 percentage points** | same |

**What's not yet measured:** a single-prompt LLM baseline for the linter, and cross-model
replication of the harness's findings (both require live Ollama inference; deferred pending GPU
availability in the session that built this — see `reports/v2_product_readiness.md`, "What would
falsify this").

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
# 1. Lint your server — zero LLM cost, exits 1 on a HIGH-severity finding
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
6 HIGH-severity violation(s):
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
and CLI-integrated (this README's numbers). Remaining, explicitly not yet done:
Task 5 cross-model replication (blocked on GPU availability) and a single-prompt LLM baseline for
the linter (`reports/v2_product_readiness.md` tracks exactly what's measured vs. assumed).

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
