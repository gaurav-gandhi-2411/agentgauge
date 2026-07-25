# AgentGauge v0.5 Wave 1 — end-of-wave report

Branch: `feat/v0-5-wave1` (off `main` @ `369eb5a`). Scope: spec-agentgauge-v0.5.md
section 4 (Wave 1) only — model-adapter abstraction (1.1) and failure attribution
(1.2). Wave 2 (triage, failure clustering) and Wave 3 (persistence/API/dashboard/MCP
server/OTel) were **not started**, per the spec's own explicit instruction not to
begin them before Wave 1's numbers are verified.

All numbers in this report were independently re-run by the orchestrating session
(not taken solely on a subagent's self-report) — see each section's "verified by"
note.

## 1. What shipped

| Commit | What |
|---|---|
| `b3eabc8` | spec-agentgauge-v0.5.md committed to repo root |
| `1498a48` | `reports/v0_5_eval_doctrine.md` — doctrine written before any implementation |
| `46aaeda` | `agentgauge/cassette.py` — cassette key/record/replay mechanism; determinism proof on the 3 pre-existing adapters (riskiest assumption, checked first) |
| `0c916e4` | `BedrockProvider`, `VertexProvider`, `CustomEndpointProvider` added to `agentgauge/providers.py` |
| `460b2de` | `agentgauge/provider_config.py` (config-driven provider selection) + cost/timing accounting wired into `agentgauge diff`/`eval` |
| `7cfce82` | fix-forward for a git-workflow collision between the two parallel subagents (disclosed in section 6) |
| `1e7bcb8` | cassette determinism proof extended to all 6 adapters |
| `2976893`, `ba20347` | `agentgauge/attribution.py`, `agentgauge/attribution_benchmark.py`, `scripts/attribution_benchmark_report.py`, `reports/v0_5_attribution_benchmark.md` |
| `55fa4e8` | `reports/v0_5_wave1_audit_gate.md` — orchestrator audit-gate pass over both new result sets |

## 2. Per-adapter replay determinism (Component 1.1 ship bar: 100% on every adapter)

**Verified by:** re-ran `uv run pytest tests/test_cassette.py -q -s` directly in this
session; the table below is this run's actual printed output, not a copy of a
subagent's claim.

| Adapter | Determinism rate | Replays |
|---|---|---|
| ollama | 100.0% | 20/20 |
| anthropic | 100.0% | 20/20 |
| openai_compatible | 100.0% | 20/20 |
| bedrock | 100.0% | 20/20 |
| vertex | 100.0% | 20/20 |
| custom_endpoint | 100.0% | 20/20 |

**Ship bar: MET.** Zero verdict flips attributable to the abstraction layer across
all six adapters — harness verdicts (`diff_from_trials`) built from replayed output
were identical across all 20 replays, for every adapter, in every run. Per
`reports/v0_5_eval_doctrine.md` Component 1.1's scope note: this measures the
adapter+cassette code path given an identical (mocked, via `respx`) wire response —
it does not measure live-provider response variance, which is out of scope and NOT
MEASURED (see section 5).

## 3. Attribution accuracy / budget table (Component 1.2 ship bar: top-1≥0.70, top-3≥0.90, sub-exhaustive budget)

**Verified by:** independently re-read `reports/v0_5_attribution_benchmark.md` in full
(not just its summary) and cross-checked its confound-guard numbers and MEASURED/NOT
MEASURED section against the doctrine's requirements before accepting the table below.

n=50 injected-culprit benchmark cases, seed=42, synthetic ground truth calibrated to
the real measured `type_enum_contradiction` effect (−13.3 to −28.9pp, 3 model
families):

| Method | top-1 | top-3 | mean probes | Sub-exhaustive? | Verdict |
|---|---|---|---|---|---|
| exhaustive_ablation (a) | 100.0% | 100.0% | 4.22 | No (reference) | reference, not a candidate |
| **sampled_shapley (b)** | 74.0% | 96.0% | 2.22 | Yes | **CLEARS** |
| **greedy_bisection (c)** | 100.0% | 100.0% | 2.98 | Yes | **CLEARS** |
| largest_textual_diff (i) | 4.0% | 66.0% | 0 | — | baseline |
| most_lint_violations (ii) | 64.0% | 80.0% | 0 | — | baseline |
| uniform_random (iii), analytic expectation | 26.7% | 75.1% | 0 | — | baseline (floor) |

**Ship bar: MET by 2 of 3 probe-based strategies** (`greedy_bisection`,
`sampled_shapley`). This is reported as a genuine positive finding — not the "kill it"
outcome spec section 4 explicitly authorized as an acceptable result, but also not
without a real caveat (below). Both clearing strategies beat all three baselines by a
wide margin, and `largest_textual_diff` — the most intuitive zero-probe heuristic —
actually performs *worse than the random floor* on this benchmark (4.0% vs 26.7%
top-1), which is itself only trustworthy because the confound guard (section 5)
confirms the benchmark doesn't let diff-size win or lose by construction.

**Confound guard: run and passed.** True culprit position took 6 distinct values
across 50 cases (not fixed to a single slot); 48/50 cases (96%) have at least one
decoy with a strictly larger textual diff than the true culprit, directly explaining
why the diff-size baseline underperforms random rather than trivially winning.

## 4. Cost accounting sample (Component 1.1: "cost accounting per run... surfaced in the diff output")

**Verified by:** wrote and ran a standalone script (not part of the test suite)
invoking `agentgauge diff` exactly as a user would, via `CliRunner`, against
`examples/echo_server.py`/`echo_server_fixed.py` with `--mock`. Actual captured output,
this session, this run:

```
AUDIT WARN (ceiling_floor):  joint success rate 0.000 is at the floor (n=1) --
little to no room for a before/after delta to show up
AUDIT WARN (ceiling_floor):  joint success rate 0.000 is at the floor (n=1) --
little to no room for a before/after delta to show up
before (n=1 trials)
  selection accuracy:          0.000
  argument accuracy | correct: n/a (0 correct-selection trials)
  joint success rate:          0.000

after (n=1 trials)
  selection accuracy:          0.000
  argument accuracy | correct: n/a (0 correct-selection trials)
  joint success rate:          0.000

before cost: provider=mock duration=0.00s tokens=n/a (provider has no token
accounting) est_spend=n/a
after cost: provider=mock duration=0.00s tokens=n/a (provider has no token
accounting) est_spend=n/a

NO_CHANGE: No detectable change (delta=+0.000, 95% CI [+0.000, +0.000] does not
clear the 0.050 threshold in either direction). Descriptions are not the
bottleneck for this tool set's task success at the trial count used here.
```

Two things worth pointing out in this real sample, both by design: (1) the standing
audit gate (`ceiling_floor` WARN) still fires unconditionally — the new adapter/config
path did not bypass it; (2) `MockProvider` correctly reports `tokens=n/a` /
`est_spend=n/a` rather than a fake `$0.000000` that would look like a real free run.
Separately (per `tests/test_cli_provider_cost.py`, independently executed this
session): replay-mode (`--replay-before`/`--replay-after`) prints `"before cost:
replay mode -- no live cost to report."` and JSON mode emits `{"live": false, "note":
"replay mode -- no live cost to report"}` — never a printed zero for a mode that made
no live calls at all.

## 5. MEASURED vs. NOT MEASURED

**MEASURED, this wave, reproducibly (seed=42, zero live network calls):**
- 100% cassette-replay determinism, all 6 adapters, against mocked wire responses.
- Harness-verdict stability across 20 replays per adapter (no flips).
- Attribution top-1/top-3 accuracy and probe budget, 3 strategies + 3 baselines, on a
  50-case synthetic injected-culprit benchmark.
- Confound-guard properties of that benchmark (culprit position spread, decoy-vs-culprit
  diff-size comparison).
- Cost/timing accounting is live in `diff`/`eval` output for both live-mode and
  replay-mode paths, correctly distinguishing "n/a" from a real zero.
- Full test suite (969 tests, 93.02% coverage), ruff, and mypy, all clean, re-run
  independently by the orchestrating session (not solely subagent-reported).

**NOT MEASURED — explicitly, so no reader mistakes wave-1 scope for more than it is:**
- **Live-provider determinism/response variance** for Anthropic, Bedrock, Vertex, or
  any real custom-endpoint. Per spec section 7's cost constraint, no paid-provider call
  was attempted this wave (no bounded estimate was sought or approved) — everything
  above is measured against mocked wire responses, which proves the *code path* adds no
  nondeterminism, not that a live provider's real response distribution is
  reproducible (it structurally isn't, for most APIs, without a real record/replay
  pass against a live account).
- **Attribution accuracy against a real agent + real LLM judge.** The 50-case
  benchmark's ground truth is a synthetic model calibrated to a real, previously
  measured effect size range — it is not itself a live measurement. The benchmark's own
  report (section 4 there) states this is a "favorable-regime" synthetic proxy: zero
  variance on decoys and a large, well-separated true effect, both cleaner than a real
  agent run would likely produce. Whether `greedy_bisection`/`sampled_shapley` still
  clear the ship bar against noisier real trial data is open.
- **`CassetteProvider` is not wired into any CLI command.** It is a proven library
  mechanism (tests/test_cassette.py), not yet a user-facing `agentgauge diff
  --provider-config ...` feature with actual replay-caching behavior. A reader should
  not assume cassette-backed caching ships this wave — it doesn't, yet.
- **Google Vertex auth (ADC/service-account token refresh) and AWS Bedrock's ambient
  credential chain** were deliberately scope-limited to "accept a pre-obtained token/key
  via an explicit env var" — full SDK-driven auth flows are not implemented and not
  measured.
- **PyYAML** was deliberately not added as a dependency; `provider_config.py` uses a
  small bounded flat-YAML parser instead, flagged by the executor as a judgment call
  worth revisiting if the config schema ever needs nesting/lists.
- **`run_audit` was not extended to accept the attribution benchmark's data shape.**
  The orchestrator audit-gate pass (`reports/v0_5_wave1_audit_gate.md`) was a manual
  code/report review, not an automated gate run, for that specific new surface.

## 6. Process note — disclosed, not hidden

The two Wave 1 workstreams (adapters, attribution) ran as parallel background
subagents on the same branch and briefly collided: one subagent's `git commit` swept
the other's already-staged, uncommitted files into its own commit (`460b2de`). The
affected subagent detected this itself, within the same session, and fixed forward
with a content-preserving `git rm --cached` (never a destructive reset/checkout) —
`7cfce82` — restoring the other task's files to untracked so they could be committed
independently, which they then were, cleanly, as `2976893`. Verified independently
this session: `git log` shows no content loss, no stray `Co-Authored-By` trailer on
any of the 10 commits on this branch, and both final file sets are exactly what each
task's own scope specified (adapters touched only `providers.py`/`cli.py`/
`provider_config.py`/`configs/`/cassette tests; attribution touched only its own new
files) with zero cross-contamination in the final state.

## 7. What's next (not started, not implied as committed)

Per spec section 8 risk 5: "Wave 1 alone is shippable as v0.5.0... do not start Wave 3
before Wave 1's numbers are verified." Wave 1's numbers are now verified (this
report). Recommended next step, at GG's direction, not decided unilaterally here: open
the draft PR (task in progress separately), and decide whether to (a) validate
attribution against a real local-Ollama agent run before calling 1.2 done, (b) start
Wave 2, or (c) ship Wave 1 as v0.5.0 first and treat real-agent attribution validation
as a fast-follow. This report takes no position on that sequencing choice — it is a
product/roadmap call, not an engineering one.
