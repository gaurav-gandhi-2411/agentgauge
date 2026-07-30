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

> **SUPERSEDED (2026-07-26).** The table and confound-guard numbers below were measured against a
> benchmark generator later found to have a construction bug (measurement artifact #9: the injected
> culprit's textual diff size correlated with its role instead of being independent of it — see
> `reports/v0_5_attribution_benchmark.md` section 7, "CORRECTION"). **The corrected numbers change
> the ship-bar conclusion: `sampled_shapley` no longer clears the bar (68.0% top-1, was 74.0%);
> only `greedy_bisection` still clears it** (was 2 of 3 strategies, now 1 of 3). Read
> `reports/v0_5_attribution_benchmark.md` section 7 for the corrected table, not this section.

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

---

## 8. Wave 1.5 — attribution validation (2026-07-26), consolidated

Six tasks were run against exactly the question section 7 above left open: does
Component 1.2 (failure attribution) hold up under scrutiny, or was the original
50-case benchmark's "2 of 3 strategies clear the ship bar" headline an artifact of an
under-tested benchmark? **It was an artifact — twice over, in two different ways —
and the corrected picture is a genuine rescope, not a simple ship/kill binary.**
Every number below is independently re-verified by the orchestrating session (test
suite re-run, key scripts re-executed, commits checked for clean trailers), not
solely subagent-reported. Full detail lives in the four reports this section
consolidates: `reports/v0_5_attribution_benchmark.md`, `reports/
v0_5_effect_size_sensitivity.md`, `reports/v0_5_scale_curve.md`, `reports/
v0_5_real_agent_validation.md`.

### 8.1 Two real bugs found, not one

1. **Measurement artifact #9** (Task 3): the injected culprit's textual diff size was
   systematically correlated with its role (culprit vs. decoy) by construction, not
   randomized independently — the exact class of confound the doctrine's guard was
   supposed to catch and didn't, because the guard checked two edge conditions, not
   the underlying distribution. Fixed; logged as artifact #9 in `agentgauge/audit.py`;
   a standing check (`check_benchmark_construction_diffsize_bias`) now runs as part of
   `run_audit` whenever benchmark cases are supplied.
2. **A real implementation bug in `agentgauge/attribution.py`** (found investigating
   Task 1, fixed as its own unit of work, commit `f432f5a`): `attribute_greedy_bisection`
   silently dropped the probe cost of every failed bisection sub-search from its
   reported `probes_consumed`, and degenerated to positional-list-order ranking (not
   measured signal) on total search failure. This was not a benchmark artifact — it
   was a bug in the shipped strategy code itself, invisible in the original benchmark
   only because search never happened to fail there.

Both were found by *using* the feature under conditions (near-MDE effect sizes; a
generator built to specifically test the doctrine's stated confound requirement) that
the original single-scenario benchmark never exercised — exactly the value a
dedicated validation pass is supposed to provide, and exactly why spec section 8's
own risk list flagged attribution's probe budget as the thing most likely to fail an
honest look.

### 8.2 The corrected picture: accurate almost everywhere, but the *budget* claim is scale-dependent

With both bugs fixed, `greedy_bisection`'s **accuracy** was never in question — it is
100% top-1/top-3 in every single-culprit configuration tested, at every effect size
from 3.0pp (below the doctrine's own n=253 MDE of 5.37pp) to 33.0pp, and at every
candidate-set size from 4 to 40 tools. What collapses and re-emerges, twice, is the
**sub-exhaustive budget** requirement — the third, equally mandatory leg of the
doctrine's ship bar:

| Regime | Accuracy | Budget vs. exhaustive | Clears full ship bar? |
|---|---|---|---|
| Original benchmark (2-6 tools, 1 culprit, favorable 13.3-28.9pp effect) | 100%/100% | **+34% (more expensive)** | **No** |
| Same small scale, effect swept 3-33pp | 100%/100% at every band | **+34% to +40% in 3 of 5 bands** (only cheap in bands where it's *failing* to find anything) | **No**, anywhere in this scale regime |
| Single culprit, ≥10 changed tools | 100%/100% | **-6% to -66%**, improving with scale | **Yes**, at every size ≥10 |
| 2 simultaneous culprits, 20 tools | 100%/100% | -17% | **Yes** |
| 3 simultaneous culprits, 20 tools | 98.9% recall / 96.7% top-3 | **+9% (more expensive)** | No (budget only — accuracy is fine) |
| 3 simultaneous culprits, 40 tools | 100%/100% | -33% | **Yes** |

The mechanism is fully diagnosed, not hand-waved (`v0_5_scale_curve.md` section 5):
`greedy_bisection`'s outer loop always pays for one extra, always-failing "confirm
there's no additional culprit" search once every real culprit is found. That fixed,
`~⌈log2(n_changed)⌉`-cost pass is genuinely wasted overhead in every case — it never
stops being wasted — but it shrinks as a *fraction* of total cost as `n_changed`
grows, while `exhaustive_ablation`'s cost grows linearly in `n_changed`. Below
roughly 10 changed tools, the fixed overhead dominates and the strategy loses to
exhaustive ablation despite being perfectly accurate. Above it, log-scaling wins.

`sampled_shapley` is sub-exhaustive everywhere by construction (fixed ~50% budget),
but its accuracy is the limiting factor: inconsistent at small single-culprit scale
(54-90% depending on effect size), solid at moderate-to-large single-culprit scale
(90-100% at n≥20), and it **never once clears `top3_strict ≥ 90%` at any tested
multi-culprit configuration**, regardless of candidate-set size. Its multi-culprit
failure mode was measured but not mechanistically diagnosed (out of scope for this
wave) — flagged as open follow-up work, not resolved.

### 8.3 Real-agent data point (Task 4): consistent in direction, not statistically informative

One real case, on live local `gemma2:9b`, no paid provider, ran end-to-end after two
infrastructure stalls (both disclosed with evidence in `v0_5_real_agent_validation.md`
section 3, not smoothed over) — `exhaustive_ablation` and `greedy_bisection` both hit
top-1/top-3 on the true culprit. This is a genuine "the real pipeline runs end-to-end
against a real agent" data point, and its direction doesn't contradict the synthetic
findings — but n=1 carries zero population-level statistical information, and
`sampled_shapley` has no real-agent data at all. This remains the single biggest gap
before the feature could be shipped with full confidence, exactly as flagged in the
original Wave 1 report's NOT MEASURED section.

### 8.4 Recommendation: RESCOPE, not ship-as-originally-claimed, not kill

Neither extreme fits the evidence:

- **Not "ship as Wave 1 originally reported."** The original claim ("2 of 3
  strategies clear the ship bar") does not hold at the small candidate-set scale that
  benchmark actually tested, under honest measurement. Shipping that claim
  unqualified would be exactly the kind of uncorrected, discovered-by-a-customer
  bound this validation wave's Task 1 instruction explicitly warned against.
- **Not "kill it."** `greedy_bisection` has a real, decisively-clearing, mechanistically
  understood operating regime — and that regime (candidate-set size ≥ 10 changed
  tools) is closer to the target buyer's actual stated pain point (spec section 2:
  "a platform team with a 40-tool server and a 12-file PR") than the original 2-6-tool
  test benchmark ever was. The feature's real value proposition may be *stronger* at
  realistic enterprise scale than the initial small-benchmark evaluation suggested.

Concretely, before this ships as a product surface:

1. **Ship `greedy_bisection` only**, with an explicit, README-documented operating
   envelope: recommended at candidate-set sizes ≥ 10 changed tools; below that,
   recommend exhaustive ablation directly (it's cheap enough at small n to not need a
   probe-budget optimization anyway). This bound must appear in the README per this
   validation wave's own Task 1 instruction — not left for a customer to discover.
2. **Demote or exclude `sampled_shapley`** from the shipped feature surface until its
   multi-culprit accuracy collapse is understood — currently it would silently
   under-perform on exactly the multi-file-PR scenario the feature exists to serve.
3. **Fix the wasted "confirm no additional culprit" pass before general release**,
   not just document around it — a caller-specified "assume single culprit" mode (or
   a cheaper confirmation strategy) would extend the sub-exhaustive regime below
   n_changed=10 and likely rescue the one remaining multi-culprit budget failure
   (3 culprits @ 20 tools) as well. This is diagnosed, not yet fixed — flagged as
   required follow-up, not optional polish.
4. **Do not claim real-agent validation** beyond "the pipeline runs end-to-end
   against a real local model, on one case" until a larger real-agent pass (5-10
   cases, at the ≥10-tool scale where the feature is actually recommended) is run.
   This is the natural next real-inference task, budgeted and gated the same way
   Task 4 was.

This recommendation is an engineering/measurement synthesis, not a final product
decision — per this report's own section 7, sequencing (ship narrowed Wave 1 now vs.
close the real-agent-at-scale gap first vs. fix the wasted-pass design issue first)
is GG's call to make, not decided unilaterally here.

### 8.5 MEASURED vs. NOT MEASURED (Wave 1.5, consolidated)

**MEASURED:** two real bugs found and fixed with regression tests; accuracy and
probe-budget curves across effect size (3-33pp, 5 bands), candidate-set size
(4/10/20/40 tools), and culprit count (1/2/3 simultaneous), all against the real
`agentgauge.harness.diff_server_level` estimator; one real end-to-end case against a
live local agent. Full test suite green throughout (1034 passed at time of writing,
93%+ coverage, independently re-run after every task in this wave, not solely
subagent-reported).

**NOT MEASURED:** real-agent validation beyond n=1; `sampled_shapley` against any
real agent; the multi-culprit accuracy collapse's root cause; whether the
"confirm no additional culprit" pass's proposed fix actually rescues the affected
regime (a design change, not yet attempted); any of this against a candidate-set size
above 40 tools or a culprit count above 3; any live paid-provider adapter's real
response-variance behavior (unchanged from Wave 1 section 5).

## SESSION-CLOSE (2026-07-26) — RESOLVED (2026-07-30), see `reports/v0_5_mde_discrepancy.md`

**RESOLVED.** This was explanation 2, a measurement artifact (logged as #10), not explanation 1
(benign probe-power difference). `agentgauge.attribution_benchmark.make_probe_fn`'s synthetic
ground-truth noise model omitted the harness's own calibrated between-task variance component
(`CALIBRATED_SIGMA_TASK`/`CALIBRATED_RHO`), giving every probe a noise floor 3-7x quieter than a
real deployment would show at the same trial count. Fixed; standing audit check added
(`agentgauge.audit.check_probe_variance_calibration`); every attribution accuracy/budget table in
this repo recomputed against the fix. `greedy_bisection`'s real accuracy at 3-5pp is 58.33% top-1
(not 100%) and correctly fails the ship bar there -- a genuine detection-power limit, confirmed
100% Mode-A / 0% Mode-B. **The correction also inverts this report's own section 8.4
recommendation**: at the corrected single-culprit scale curve, `greedy_bisection`'s accuracy
collapses with candidate-set size (47% top-1 at n=40) while `sampled_shapley` now clears the full
ship bar at every size >=10 tools including n=40 -- the opposite of "ship `greedy_bisection` only,
demote `sampled_shapley`." See `reports/v0_5_mde_discrepancy.md` sections 4c and 6 before acting on
any part of section 8.4 below; it is superseded, not merely caveated. Original open question
preserved verbatim below for the record.

Open question carried into next session, before attribution ships: section 3
reports `greedy_bisection` at 100% top-1/top-3 down to a 3.0pp effect size, but
the harness's own server-level MDE (n=253) is 5.37pp — a nominal effect below the
detectable floor is being attributed perfectly. Two explanations are live and
unresolved:

1. **Probe-level power differs from server-level MDE.** The 5.37pp MDE is
   computed for `diff_server_level`'s aggregate significance test; per-probe
   attribution inside `greedy_bisection` may operate on a different (larger, more
   controlled) effective sample per comparison, giving it detection power the
   server-level headline number doesn't reflect. If so, 100% top-1 at 3pp is real
   and the MDE comparison is apples-to-oranges.
2. **Measurement artifact**, in the vein of the confound-guard and diff-size-bias
   findings already logged in this wave (artifacts #9, #10-adjacent) — e.g. the
   benchmark's ground-truth injection at 3pp may be systematically easier to
   detect than a genuine field-observed 3pp effect, or a rounding/threshold
   interaction in the effect-band generator.

Do not resolve this by re-running the same measurement again — it replicated
cleanly already. Next step: read `greedy_bisection`'s probe comparison logic
against `diff_server_level`'s significance test directly and determine
analytically whether they operate on the same statistical unit. This must be
closed, one way or the other, before attribution ships per this report's own
section 8.4 recommendation.
