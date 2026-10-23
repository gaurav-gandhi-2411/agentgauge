# Project structure (moved out of the README on 2026-10-11)

Layout of the `agentgauge/` package at v0.5.3. `agentgauge/demo/` (bundled first-run demo) and
`py.typed` were added after this listing was written; see `CHANGELOG.md`.

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
