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
  scorer.py     # Rubric scoring: schema-completeness + description-quality fully implemented;
                # other dimensions stubbed
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
| selection_accuracy   | 15%    | TODO          |
| call_correctness     | 10%    | TODO          |
| error_legibility     | 5%     | TODO          |
| robustness           | 3%     | TODO          |
| docs_manifest        | 2%     | TODO          |

## MCP SDK notes

- `mcp>=1.3.0` — `mcp.client.stdio.stdio_client`, `mcp.client.sse.sse_client`
- Server: `mcp.server.Server`, `mcp.server.stdio.stdio_server`,
  `mcp.server.models.InitializationOptions`
- SDK API paths can shift across minor versions; check import paths after upgrade.
