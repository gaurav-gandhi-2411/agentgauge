# AgentGauge

**AgentGauge scores how well an AI agent can actually use an MCP server.**

[![CI](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml/badge.svg)](https://github.com/gaurav-gandhi-2411/agentgauge/actions/workflows/ci.yml)

> **v1 complete.** All eight scoring dimensions are implemented. The core CLI scanner is functional.

---

## Why

MCP servers vary wildly in agent-usability. An agent fails not because the server's underlying code is broken, but because the interface it's handed is bad: ambiguous tool names, missing parameter descriptions, unparseable errors. AgentGauge measures exactly this — it runs a real LLM agent against your server and tells you where it struggles.

Think of it as Lighthouse/PageSpeed, but for MCP interfaces.

---

## Install

```bash
git clone https://github.com/gaurav-gandhi-2411/agentgauge
cd agentgauge
pip install uv && uv sync
```

---

## Quickstart

```bash
# Score your server and preview all suggested fixes — nothing is written
agentgauge try path/to/your_server.py

# Apply the fixes when you're ready
agentgauge fix path/to/your_server.py --apply

# Quick scan with a mock LLM (no Ollama needed)
agentgauge scan path/to/your_server.py --mock
```

`agentgauge try` is the recommended first command. It runs scan + fix-preview in one step,
shows the score table and inline before/after for every suggested change, and ends with the
exact `fix --apply` command to run when you're ready. It never writes any files.

When `--apply` is used, a `.bak` file is written before the original is overwritten.
If `.bak` already exists, it increments to `.bak.1`, `.bak.2`, etc.

Example output (`agentgauge scan examples/echo_server.py --mock --trials 1`):

```
  AgentGauge Score: 57.4/100
  Tools inspected: 3

  Dimension Breakdown
  ┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━┓
  ┃ Dimension              ┃  Score ┃ Status         ┃
  ┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━┩
  │ schema_completeness    │   77.8 │ good           │
  │ description_quality    │   70.0 │ fair           │
  │ discoverability        │    0.0 │ not yet        │
  │ selection_accuracy     │   75.0 │ good           │
  │ call_correctness       │   60.0 │ fair           │
  │ error_legibility       │   65.0 │ fair           │
  │ robustness             │    0.0 │ not yet        │
  │ docs_manifest          │    0.0 │ not yet        │
  └────────────────────────┴────────┴────────────────┘

  Prioritized Fixes
    1. [schema_completeness] Tool 'mystery': add parameter definitions to inputSchema
    2. [description_quality] Tool 'mystery' scored 3.0/10 — improve its description
```

---

## Scoring dimensions

| Dimension | Weight | What it measures | Status |
|---|---|---|---|
| `schema_completeness` | 25% | Parameter types, descriptions, required/optional present | **Implemented** |
| `description_quality` | 25% | An agent can choose and call the tool from its description alone (LLM judge) | **Implemented** |
| `selection_accuracy` | 15% | Given a task description, agent picks the right tool (N trials, % correct) | **Implemented** |
| `call_correctness` | 10% | Agent constructs valid arguments; server accepts the call | **Implemented** |
| `discoverability` | 15% | Tool names are distinct and self-explanatory (heuristic + LLM judge) | **Implemented** |
| `error_legibility` | 5% | Error responses are understandable and actionable to an agent | **Implemented** |
| `robustness` | 3% | Server handles malformed inputs gracefully without crashing | **Implemented** |
| `docs_manifest` | 2% | Quality and presence of `llms.txt` / tool-level docs | **Implemented** |

Overall score = weighted sum across all eight dimensions (0–100).

---

## How it works

```
agentgauge scan <target>
       │
       ├─ connects to MCP server (stdio subprocess or HTTP/SSE)
       ├─ introspects tools / resources / prompts
       ├─ static analysis  →  schema_completeness score
       ├─ LLM-as-judge     →  description_quality score
       ├─ generates tasks, runs agent (N trials) → selection_accuracy + call_correctness
       └─ prints weighted report + prioritized fix list
```

**Model-agnostic.** The LLM that acts as the test agent is pluggable:

| Provider | How to use |
|---|---|
| Mock (deterministic) | `--mock` — no network, no cost; used in all tests |
| Ollama (local) | default; `--model llama3.1:8b` (or any model you have pulled) |
| Any hosted model | implement the `Provider` protocol in `providers.py` |

**Tests never call a real LLM.** `MockProvider` returns preset responses deterministically, so `./scripts/verify.sh` runs with no network access and no credentials.

**Judge model and score comparability.** The default judge model is `llama3.1:8b` — the model the scoring rubric was calibrated against. Scores produced with a different `--model` are not directly comparable to scores produced with the default: the absolute band values shift as the model changes. Always record which judge model produced a score alongside the score itself. A future calibration run may update the pinned default; that change will be noted in CLAUDE.md.

---

## JSON output schema

When using `--out report.json`, the emitted file has exactly this structure:

```json
{
  "schema_version": "1.0",
  "overall_score": 72.5,
  "dimensions": [
    {"name": "schema_completeness", "score": 77.8, "weight": 0.25},
    {"name": "description_quality",  "score": 70.0, "weight": 0.25},
    {"name": "discoverability",      "score": 60.0, "weight": 0.15},
    {"name": "selection_accuracy",   "score": 75.0, "weight": 0.15},
    {"name": "call_correctness",     "score": 60.0, "weight": 0.10},
    {"name": "error_legibility",     "score": 65.0, "weight": 0.05},
    {"name": "robustness",           "score": 50.0, "weight": 0.03},
    {"name": "docs_manifest",        "score": 20.0, "weight": 0.02}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `schema_version` | `string` | Fixed at `"1.0"` for this schema generation |
| `overall_score` | `float` | Weighted sum across all eight dimensions (0–100) |
| `dimensions` | `list` | One entry per dimension, any order |
| `dimensions[].name` | `string` | Dimension identifier (see scoring table above) |
| `dimensions[].score` | `float` | Dimension score (0–100) |
| `dimensions[].weight` | `float` | Contribution weight (all weights sum to 1.0) |

---

## Development

```bash
# Run all checks (ruff, mypy, pytest + coverage)
bash scripts/verify.sh

# Run tests only
uv run pytest

# Scan the bundled echo server
agentgauge scan examples/echo_server.py --mock
```

Coverage: **87%** across 41 tests. Threshold enforced at 60%.

---

## Roadmap

v1 is complete — all eight scoring dimensions are implemented and `agentgauge ci` provides an exit-code gate for CI pipelines. See [ROADMAP.md](ROADMAP.md) for the v2 plan.

v2 (not started): auto-fix loop (generate improved tool descriptions as a PR); hosted dashboard with per-server history; CI action that fails on score regression.

---

## Project structure

```
agentgauge/
  client.py     # MCP client: stdio + HTTP/SSE, introspect, call tools
  providers.py  # Provider protocol + OllamaProvider + MockProvider
  tasks.py      # Task generator: sample args from JSON schema
  runner.py     # Agent runner: LLM selects tool + constructs args, N trials
  scorer.py     # Rubric scoring: static analysis + LLM-as-judge
  report.py     # Rich text report renderer
  cli.py        # typer CLI: agentgauge scan <target>
examples/
  echo_server.py  # Minimal MCP server (good + bad tools) for local demos
tests/            # pytest; LLM always mocked; no network; no paid calls
```

---

## License

MIT — see [LICENSE](LICENSE).
