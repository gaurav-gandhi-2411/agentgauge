# Model adapters (v0.5.0), moved out of the README on 2026-10-11

Status: reference. `agentgauge diff`/`eval` are not Ollama-only; six provider adapters share one
config-driven interface. The example configs live in the repository under `configs/` and are
**not** in the PyPI wheel. The per-adapter determinism result below is measured on
recorded/mocked responses only (stated in the Scope paragraph). Hosted-API sampling is
non-deterministic and `--seed` is ignored by hosted APIs.

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
