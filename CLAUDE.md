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
  scorer.py     # Rubric scoring: all 8 dimensions implemented — schema-completeness,
                # description-quality, selection-accuracy, call-correctness, error-legibility,
                # robustness, docs-manifest, discoverability
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
| discoverability      | 15%    | implemented   |
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

## discoverability calibration notes

**Judge sub-score is DISTINGUISH, not a holistic clarity score.**
The prompt asks for two labeled lines (`CLARITY: N` / `DISTINGUISH: N`).  Only
`DISTINGUISH` is extracted (via `_parse_distinguish_score` — label → last-number →
first-number fallback).  This fixes the pre-calibration bug where the model's
internally computed distinguishability score (e.g. 4/10) was discarded because the
parser grabbed the first number (the CLARITY score, e.g. 8/10).

**Blend: 60% heuristic / 40% judge (`_HEURISTIC_BLEND_WEIGHT = 0.60`).**
The heuristic sub-score includes a Levenshtein collision penalty (−15 pts per near-
duplicate pair, capped at −30 pts).  The ≥0.50 heuristic weight ensures this penalty
is never fully overridden by a noisy judge trial.

**Measured calibration (Cloud Run llama3.1:8b, 5 trials, 2026-05-31):**

| Catalog | DISTINGUISH trials | Mean | σ | Judge | Blended |
|---------|-------------------|------|---|-------|---------|
| clear/distinct | 8, 9, 9, 6, 6 | 7.60 | 1.36 | 76/100 | 90.4 |
| confusable pair | 8, 6, 6, 6, 4 | 6.00 | 1.26 | 60/100 | 75.0 |
| placeholder | 2, 6, 6, 2, 2 | 3.60 | 1.96 | 36/100 | 47.7 |

Gap clear→confusable: +16 pts judge, +15.4 pts blended. Both exceed σ_confusable
(1.26 pts) — separation is stable but not wide (~1σ). Format compliance: 100%.

**What this dimension GUARANTEES (model-independent, locked by mock tests):**
- Ordering: good catalog (clear names, no collisions) beats bad by ≥ 40 pts.
- Heuristic collision floor: near-duplicate pair always deducts ≥ 15 pts regardless
  of judge output.

**What is NOT guaranteed (absolute bands are model-dependent):**
Absolute blended scores shift with the judge model. Use ordering and gap comparisons,
not absolute thresholds. The confusable catalog will always score below the clear
catalog, but the exact margin depends on the model's interpretation of "distinguishable".

## Remote judge (GCP) — use when local VRAM is contended

When `nvidia-smi` shows < 5 GB free VRAM (e.g. other models or apps occupying the GPU),
run the judge on Cloud Run instead of local Ollama:

```bash
gcloud run services proxy agentgauge-judge --port=11434 --region=us-central1 --project=expense-tracker-498014
```

AgentGauge's existing `OllamaProvider` (`BASE_URL = http://localhost:11434`) picks this
up transparently — no code change needed. Run the proxy in one terminal, then run
`agentgauge scan` (or any spot-check script) in another.

**Port conflict:** if local Ollama is already on 11434, stop it first
(`ollama stop` / kill PID) or use `--port=11435` and point scripts at `localhost:11435`.

**Service details:**
- Service name: `agentgauge-judge`
- Region: `us-central1`, project: `expense-tracker-498014`
- Private (IAM-auth only, `--no-allow-unauthenticated`)
- Scale-to-zero, max 1 instance, NVIDIA L4 GPU, 32 GB RAM
- Model weights stored in GCS bucket `agentgauge-judge-models-expense-tracker`
  (persists across cold starts — no re-pull needed)

**Latency (measured 2026-05-31):**
- Cold start (container + GPU init + Ollama ready): ~3–4 min (Cloud Run startup probe)
- First inference after cold start (load weights GCS→VRAM): ~8s additional
- Warm inference (model already in VRAM): ~1.2s end-to-end

**CRITICAL — do NOT change the model:**
The judge MUST remain `llama3.1:8b`. All rubric calibration (error_legibility,
description_quality, discoverability) was done against this exact model. Substituting
a different or larger model (e.g. qwen3:8b, llama3.1:70b) invalidates score comparability
with any previously recorded results. If you pull a different model for experimentation,
pull it into a separate Ollama instance, not this service.

## Real-model spot checks — VRAM prerequisite

Before running any real-model validation script (e.g. `scripts/validate_error_judge.py`),
run `ollama ps` and confirm no large model is currently resident in GPU memory. VRAM
contention can starve the 8B judge into CPU fallback or timeouts, producing artificially
low or unstable scores that are not representative of normal operation.

If local VRAM is unavailable, use the remote judge above instead.

## MCP SDK notes

- `mcp>=1.3.0` — `mcp.client.stdio.stdio_client`, `mcp.client.sse.sse_client`
- Server: `mcp.server.Server`, `mcp.server.stdio.stdio_server`,
  `mcp.server.models.InitializationOptions`
- SDK API paths can shift across minor versions; check import paths after upgrade.
