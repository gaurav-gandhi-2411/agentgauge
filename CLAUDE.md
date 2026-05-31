# AgentGauge — Claude Code Conventions

AgentGauge is a CLI that scores how well an AI agent can use an MCP server.
`agentgauge scan <target>` connects to an MCP server, introspects its tools/resources/prompts,
runs an LLM agent against generated tasks, and prints a scored report.

## Architecture

```
agentgauge/
  client.py     # MCP client: connect (stdio/HTTP/SSE), introspect, call tools
  providers.py  # Provider protocol + OllamaProvider + MockProvider
  tasks.py      # Task generator (stub — see TASKS.md)
  runner.py     # Agent runner (stub — see TASKS.md)
  scorer.py     # Rubric scoring: schema-completeness, description-quality, selection-accuracy,
                # call-correctness, error-legibility, robustness, docs-manifest implemented;
                # discoverability stubbed
  report.py     # Rich text report renderer
  cli.py        # typer CLI: agentgauge scan <target> [--model] [--trials N] [--out] [--mock]
examples/
  echo_server.py  # Minimal MCP server with good + bad tools for local demos
tests/          # pytest unit tests — LLM is ALWAYS mocked; no network; no paid calls
scripts/
  verify.sh     # CI gate: install -> lint -> typecheck -> test
```

## Install & run

```bash
uv sync
agentgauge --version
agentgauge scan examples/echo_server.py --mock
```

## Test

```bash
uv run pytest
# or
./scripts/verify.sh
```

## Code conventions

- `from __future__ import annotations` as first line of every Python file.
- Line length 100. Ruff rules: E, F, I, UP, B, SIM.
- Type annotations on all function signatures.
- `Provider` is a `Protocol`, not an ABC. Adapters implement it structurally.
- `MockProvider` in `providers.py` — deterministic, no network, used in all tests.
- **The LLM is always mocked in tests.** Never add a test that calls Ollama or any hosted API.
  CI must pass with no network access and no paid credentials.
- `seed: 42` in all stochastic contexts.
- Pydantic for API-boundary types; dataclasses for internal value objects.

## Scoring dimensions (0-100 each, weighted to an overall)

| Dimension            | Weight | Status        |
|----------------------|--------|---------------|
| schema_completeness  | 25%    | implemented   |
| description_quality  | 25%    | implemented   |
| discoverability      | 15%    | TODO          |
| selection_accuracy   | 15%    | implemented   |
| call_correctness     | 10%    | implemented   |
| error_legibility     | 5%     | implemented   |
| robustness           | 3%     | implemented   |
| docs_manifest        | 2%     | implemented   |

## Judge model and calibration

**Pinned judge model:** `llama3.1:8b` (via Ollama). This is the model the
error_legibility and description_quality rubrics were calibrated against.
It is the default for `agentgauge scan --model`.

**Score comparability:** Scores are NOT comparable across judge models. Changing
`--model` shifts absolute band values — a 70/100 on `llama3.1:8b` is a different
thing than a 70/100 on another model. Always record the judge model alongside
any score you store or publish.

**What the dimension guarantees (model-independent):**
- Ordering: what+how > diagnosis-only > opaque (always true by rubric design)
- Actionability gap: what+how − diagnosis-only ≥ 20 pts (locked by mock tests)
- Opaque errors score low: ≤ 25/100

**Absolute bands are model-dependent and NOT guaranteed:**
The 5-6 rubric anchor for "diagnosis-only" is the intended target but is
aspirational for llama3.1:8b. Measured values (5 trials, 2026-05-31):
- Opaque ("Error 500"): ≈ 10/100
- Diagnosis-only ("Required field X is missing."): ≈ 68/100
  (rubric intends 5-6/10; 8B treats clear field-naming as near-actionable)
- What+how ("...add it and retry."): ≈ 90/100, stable across seeds

**Updating calibration:** Run `scripts/validate_error_judge.py` (ad-hoc, not
committed), record before/after tables, update the `CALIBRATED_JUDGE_MODEL`
constant in `cli.py` and these notes.

## docs_manifest calibration notes

**Fetch path validation (real sites, 2026-05-31):**
- redirect-following confirmed working: docs.anthropic.com (301→200, 166k chars) is fetched.
- 404 / connection-error / stdio (no base_url) confirmed: all floor at exactly 20.0 with
  fix hint "No llms.txt found — add one at /llms.txt."
- fetch_llms_txt uses follow_redirects=True and swallows all errors; never raises into scorer.

**Judge prompt confirmed (agent-usefulness framing, not generic doc quality):**
The prompt explicitly asks whether the document lets an AI agent understand:
(a) what the server does overall, (b) which tools exist and their purpose,
(c) when and how to use each tool.
Verified against the live built string — no collapse to generic "is this good documentation?".

**What this dimension GUARANTEES (model-independent, locked by mock tests):**
- Ordering: present-good scores above present-poor (gap ≥ 40 pts asserted)
- Floor: absent / stdio / 404 always returns exactly 20.0 (deliberate signal)

**What is NOT guaranteed (absolute bands are model-dependent):**
Unlike error_legibility, docs_manifest has no real-model calibration run. Real-judge
validation was blocked by VRAM contention (see PR #17 discussion). The 20–100 linear
mapping is structurally sound but exact band values (where a "good" llms.txt actually
lands on llama3.1:8b) are unmeasured. Use ordering and gap comparisons only.

**Known limitation:** Only the first 8000 chars of the fetched document are fed to the
judge (~4000 tokens). Files where tool descriptions start after that window will score
lower than their full content warrants. Run a calibration pass when this matters.

## Real-model spot checks — VRAM prerequisite

Before running any real-model validation script (e.g. `scripts/validate_error_judge.py`),
run `ollama ps` and confirm no large model is currently resident in GPU memory. VRAM
contention can starve the 8B judge into CPU fallback or timeouts, producing artificially
low or unstable scores that are not representative of normal operation.

## MCP SDK notes

- `mcp>=1.3.0` — `mcp.client.stdio.stdio_client`, `mcp.client.sse.sse_client`
- Server: `mcp.server.Server`, `mcp.server.stdio.stdio_server`,
  `mcp.server.models.InitializationOptions`
- SDK API paths can shift across minor versions; check import paths after upgrade.
