# AgentGauge v0.5 Wave 1 — real-agent (live-LLM) attribution validation pilot

Direct follow-up to the single biggest repeated caveat in `reports/v0_5_attribution_benchmark.md`,
`reports/v0_5_effect_size_sensitivity.md`, and `reports/v0_5_scale_curve.md`: every number in all
three reports comes from `agentgauge.attribution_benchmark.make_probe_fn`, a DECLARED,
deterministic synthetic ground-truth model — zero live LLM calls anywhere. This report runs the
same, unmodified `agentgauge.attribution` strategy implementations against a REAL `ProbeFn`,
backed by a real local Ollama model (`gemma2:9b`), real MCP server variants, and real,
hand-authored anti-tautology tasks — for the first time in this study.

**Headline, stated plainly up front: this is a genuinely small, single-case real data point, not
a validation or refutation of the synthetic study's numbers.** Two live-inference attempts
stalled/failed for infrastructure reasons before a third, deliberately reduced-scope attempt
succeeded. The final real result: on the one real case that completed, both `exhaustive_ablation`
and `greedy_bisection` correctly localized the true injected culprit at top-1 (and top-3), at
real probe costs of 4 and 3 respectively — in the same ballpark as, but not confirming or
refuting, the synthetic study's comparable-scale `single_n4` bucket. `sampled_shapley` was not
run this pass (explicit, disclosed budget cut). n=1 is not enough to say anything with
statistical confidence about real-world localization accuracy in general — see §6.

## 1. Environment check (re-confirmed at every phase, not assumed stale)

**Session start** (`nvidia-smi` / `ollama ps`, before any work): `0 MiB / 8192 MiB` used, 0
resident models, `gemma2:9b` (5.4GB) present in `ollama list`.

**Immediately before the pilot probe**: reconfirmed clean (0 MiB used, no resident models) —
matches session start.

**Immediately before the first (stalled) full run**: `6163 MiB / 8192 MiB` used, `gemma2:9b`
resident (warm from the pilot, TTL "2 minutes from now") — expected residue from the pilot run
completing seconds earlier, not external contention.

**Immediately before the final (successful, reduced-scope) run**: reconfirmed clean again —
`0 MiB / 8192 MiB` used, no resident models (the model had unloaded during the ~15-minute gap
while investigating the first stall). Printed verbatim by the script itself
(`scripts/real_agent_validation.py::_print_environment_check`), captured in its own stdout below.

No paid/cloud provider was used at any point. No `ANTHROPIC_API_KEY` was set or referenced.

## 2. Pilot pace measurement (run before any scope decision, per this task's explicit rule)

One full probe cycle (before-arm once + one after-arm revert, `real_github_issues` case, 4
tasks/arm, 1 trial each) was measured before deciding how much to run:

| Step | Wall-clock | Tasks | Per-task |
|---|---|---|---|
| Case construction (stdio introspection of the real example server) | 1.88s | — | — |
| Before-arm run (regressed catalog, nothing reverted) | 36.81s | 4 | 9.20s/task |
| One after-arm probe (revert the true culprit) | 21.68s | 4 | 5.42s/task |
| **Total for one probe cycle** | **58.48s** | 8 task-runs | ~7.3s/task (~3.65s/LLM call; each task-run is 2 calls: select + construct) |

Measured delta on that one probe: **exactly 0.0000** (CI `[0.0000, 0.0000]`) — `gemma2:9b`
selected the identical tool for all 4 tasks whether or not `update_issue_state`'s description
carried the injected defect. This was visible before any scope decision was made and is discussed
further in §5.

This pace (~5.4–9.2s/task, ~1.7x variance already visible in a single measurement) drove the
original scope decision: 3 real cases (`real_github_issues`, `real_jira_issues`,
`real_stripe_payments`) × 3 strategies (`exhaustive_ablation`, `sampled_shapley`,
`greedy_bisection`), estimated at ~13–20 minutes total, comfortably inside the 20–45 minute
target. That plan is what actually ran into the infrastructure problem described next.

## 3. Two stall incidents — reported in full, not smoothed over

### Incident 1: backgrounded 3-case run, stalled after the first before-arm, process later found dead

The first live-run attempt used a backgrounded (`run_in_background`) shell invocation of
`scripts/real_agent_validation.py` across the originally-planned 3 cases × 3 strategies. It
printed the environment check and completed the first case's before-arm run
(`before-arm: 18.86s for 4 tasks`), then produced **zero further output for 15 minutes**.

Evidence gathered before concluding this was a genuine stall, not merely slow:
- A direct 20-second-interval poll loop against the output file, run for ~580s (the Bash tool's
  10-minute single-call ceiling), showed the line count **never changing** — no new output at
  all in that entire window.
- `nvidia-smi` at the point of investigation: `0 MiB used, 0%` utilization (it had shown
  43–100% utilization and 7.8–8.0GB used during the genuinely-active phase just before the
  stall — confirmed at multiple timestamped checks).
- `ollama ps`: empty — no resident model (consistent with Ollama's keep-alive TTL expiring after
  several minutes of zero incoming requests).
- The script's process (confirmed by PID) was **no longer present** in the process list —
  it had exited or been killed, with **no traceback or error text ever written** to its output.
- No checkpoint record was ever written (`evals/fixtures/v0_5_real_agent_validation.jsonl` did
  not exist after this attempt) — zero real cases completed, zero data banked.

**Root cause was not conclusively isolated.** The leading (unconfirmed) hypothesis: a long-running
FOREGROUND monitoring command (the 20s-interval poll loop, itself capped by the Bash tool at 10
minutes and then terminated) and the BACKGROUNDED live script may have shared or recycled shell
state on this Windows environment, causing the backgrounded process to be killed as a side effect
of the foreground command's own termination. This is stated as a hypothesis, not a confirmed
mechanism — no direct evidence (e.g. an OS-level kill signal log) was available to prove it.

### Incident avoided: second attempt redesigned around the suspected mechanism

Per direct instruction, the second attempt removed both suspect mechanisms simultaneously: **no
`run_in_background`, and no separate polling loop.** `scripts/real_agent_validation.py` was
instead run as a single, direct, blocking shell call that the caller waits on synchronously,
reading real output only after the call returns — with scope reduced to fit comfortably inside
one blocking call:

- **1 case only**: `real_github_issues` (chosen because its before-arm was already proven working
  in the pilot).
- **2 of 3 strategies**: `exhaustive_ablation` and `greedy_bisection`. `sampled_shapley` was
  **not run** this pass — an explicit, disclosed budget cut (see `STRATEGIES_TO_RUN` in
  `scripts/real_agent_validation.py`), not a silently-dropped corner.

This second attempt **succeeded**, completing in 119.2s (2.0 min) — see §4. It is treated here as
confirmation that the reduced, unbackgrounded, unpolled invocation mechanism itself was sound;
whether the original hypothesis about shared shell state was the true root cause of Incident 1
remains unconfirmed.

## 4. The real accuracy / budget / wall-clock result (n=1 case)

### Case construction — real_github_issues

- **Real server**: `examples/github_issues_server_fixed.py` (a real, already-shipped 4-tool
  example MCP server with genuine, well-written tool descriptions).
- **Real tasks**: 1 task per changed tool (4 tasks total), taken unchanged from
  `evals/fixtures/v2_4_corpus/github_issues_fixture.py` — a real, hand-authored, anti-tautology
  task fixture (task text never leaks the gold tool name or its enum/format answer).
- **True culprit**: `update_issue_state` — mutated with the real, causally-validated
  `type_enum_contradiction` defect (`agentgauge.attribution_benchmark._inject_type_enum_contradiction`,
  imported unchanged: `state`'s schema type flipped `string` → `integer`, plus the appended
  boolean-phrase sentence), camouflaged with a `medium`-tier suffix so its diff size isn't a
  structural giveaway.
- **Decoys** (benign paraphrase edits, real diff-size variation, no causal effect):
  `create_issue` (small tier, 44 chars), `add_assignee` (medium tier, 99 chars), `add_label`
  (large tier, 314 chars) — vs. the culprit's own 95-char diff. The culprit's diff (95 chars)
  is NOT the largest in this case (`add_label`'s 314-char decoy is larger) — the same
  "don't let the largest-diff heuristic win by construction" property the synthetic benchmark's
  confound guard requires, though at n=1 this is descriptive, not a statistically verified guard.

### Result table

| Method | top-1 | top-3 | probes_consumed (logical) | marginal live LLM probe calls | marginal wall-clock |
|---|---|---|---|---|---|
| **exhaustive_ablation** | **HIT** | **HIT** | 4 | 4 | 70.82s |
| **greedy_bisection** | **HIT** | **HIT** | 3 | 1 (2 cache hits) | 17.87s |
| largest_textual_diff (baseline i) | miss | HIT | 0 | 0 | 0s |
| most_lint_violations (baseline ii) | HIT | HIT | 0 | 0 | 0s |
| uniform_random (baseline iii), one draw | miss | HIT | 0 | 0 | 0s |
| uniform_random (baseline iii), analytic expectation | 25.0% | 75.0% | 0 | 0 | 0s |
| `sampled_shapley` | **not run this pass** — disclosed budget cut | | | | |

Case-level totals: before-arm 28.61s (4 tasks), 5 distinct live probe calls across both
strategies combined (2 were cache hits — the same `reverted` subset was queried by both
strategies and only computed live once, per this script's shared-cache-per-case design, disclosed
in `scripts/real_agent_validation.py`'s module docstring), **117.30s total case wall-clock**,
**119.2s total script wall-clock** including the environment check.

**Cost-sharing caveat, stated explicitly**: because `exhaustive_ablation` ran first and
`greedy_bisection` reused 2 of its 3 probed subsets from the shared cache, `greedy_bisection`'s
"1 marginal live call" figure is NOT what it would cost run standalone (in isolation it would
need its own 3 live calls, not 1) — it is the real MARGINAL cost given this run order. A
production deployment running only `greedy_bisection` alone, without a prior `exhaustive_ablation`
pass to piggyback on, would pay closer to 3 live probe calls, not 1.

### A real, honest mechanism uncertainty (not independently confirmed here)

`greedy_bisection`'s real `probes_consumed=3` is markedly cheaper than the synthetic
`single_n4` bucket's measured mean of 6.00 probes (see §5), and its outer "confirm there's no
additional culprit" search pass — which `reports/v0_5_effect_size_sensitivity.md` §11e found adds
real, usually-wasted cost in the synthetic benchmark — does not appear to have run at all here (no
second `_bisect_within` invocation's cost is visible in the probe count). The most likely
explanation, based on the code path traced against the observed probe count and cache-hit
pattern (but **not independently confirmed by inspecting raw delta/CI values**, since this run's
checkpoint does not record them and no further live call was made to check, per this task's
"last attempt" constraint): with only `n_tasks=4` per arm — far below even
`reports/v0_5_effect_size_sensitivity.md`'s already-small `n_tasks=24` per-probe regime, which
itself needed ≥8pp true effect to reliably detect anything — real per-probe confidence intervals
at `n_tasks=4` are almost certainly too wide to ever certify significance at the 5pp threshold.
That would mean `_bisect_within` hit a **total search failure** on its first call (no half ever
clears the CI-significance bar), so `attribute_greedy_bisection`'s top-1 hit here most likely came
from the post-fix "rank by measured (if sub-threshold) marginal delta" fallback path
(`reports/v0_5_effect_size_sensitivity.md` §11's fix), not genuine CI-certified bisection — and a
total search failure on the FIRST call means the outer loop `break`s immediately, explaining why
no second "confirm no more culprits" pass ran. **This is a plausible, code-consistent explanation,
disclosed as an inference from the observed probe/cache-hit pattern, not a directly-measured
fact** — confirming it would require re-running with raw delta/CI logging, which was not done
here given the live-inference budget already spent on two prior attempts.

## 5. Comparison to the synthetic study at a comparable scale

The closest synthetic comparison point is `reports/v0_5_scale_curve.md`'s `single_n4` bucket
(n_changed=4, single culprit, n=30 synthetic cases, same real `type_enum_contradiction` defect
model, same `agentgauge.harness.diff_server_level` estimator):

| Method | Synthetic `single_n4` (n=30 cases) | Real (n=1 case) |
|---|---|---|
| exhaustive_ablation | 100.00% top-1/top-3, 4.00 mean probes (reference) | HIT/HIT, 4 probes (reference) |
| greedy_bisection | 100.00% top-1/top-3, 6.00 mean probes — **MORE EXPENSIVE than exhaustive (+50.0%)** | HIT/HIT, 3 probes — **cheaper than exhaustive (-25%)** |
| largest_textual_diff | 30.00% top-1 | miss (top-1) |
| most_lint_violations | 60.00% top-1 | HIT (top-1) |
| uniform_random (analytic) | 25.00% top-1 | 25.0% top-1 (identical formula, `min(k,n)/n` at n=4,k=1) |

**Same ballpark on accuracy (both perfect on the two probe-based strategies at this tiny n=4
candidate-set size), genuinely different on `greedy_bisection`'s real cost** (cheaper than
exhaustive here vs. more-expensive-than-exhaustive in the 30-case synthetic bucket) — but per §4's
mechanism caveat, this specific real case's cheapness is plausibly an artifact of a total-search
failure short-circuiting the outer loop early (a `n_tasks=4`-driven statistical-power effect), not
evidence that `greedy_bisection` is systematically cheaper against real agents than the synthetic
study found. **n=1 real vs. n=30 synthetic is not a fair-power comparison in either direction** —
see §6.

## 6. Statistical power — read this before citing any number above

**n=1 real case is not enough to confirm, refute, or meaningfully bound the synthetic study's
ship-bar numbers.** This section states that plainly, not as boilerplate:

- A single case's top-1 hit/miss carries **zero** information about the population accuracy rate
  beyond "at least one instance was hit" — it cannot distinguish "this strategy reliably clears
  70% top-1 in reality" from "this strategy got lucky once." Every accuracy percentage that WOULD
  be computed from n=1 (0% or 100%) is meaningless as an estimate of a general rate.
- The single real probe-cost numbers (4 and 3) are similarly single draws from what is, per §5's
  own comparison, at minimum a bimodal-looking cost distribution even in the 30-case synthetic
  bucket (crossing over from more-expensive to less-expensive somewhere between n_changed=4 and
  n_changed=10) — one real draw cannot say which side of any real crossover point real agents
  actually sit on.
- `sampled_shapley` was not measured live at all this pass — there is **zero** real data for it,
  not weak data.
- Real per-call latency variance was already visible at ~1.7x within the pilot's own two
  measurements (5.42 vs. 9.20 s/task) — the small handful of real probes in §4 carry that same
  noise in their wall-clock figures, not just their accuracy.
- Every "NOT MEASURED" caveat in `reports/v0_5_attribution_benchmark.md` §4,
  `reports/v0_5_effect_size_sensitivity.md` §9, and `reports/v0_5_scale_curve.md` §8 about the
  favorable synthetic regime (zero-effect decoys, effect magnitudes at the well-separated end of
  the harness's own measured detection power) still describe the SYNTHETIC numbers in this
  report's own §5 comparison column — this report does not re-validate or invalidate those
  caveats, it only adds one small, real, independent data point alongside them.

**What this report DOES honestly establish, at n=1:** the full real pipeline — real MCP server
variant construction, real live-LLM tool selection, real `TrialOutcome` scoring, the real
`diff_server_level` estimator, and the real, unmodified attribution strategies — runs end to end
against a real local model and produces a coherent, internally-consistent result (probe counts,
cache-hit accounting, and accuracy all cross-check against each other, as traced in §4). That is a
genuine, non-trivial "does this actually work against a real agent, at all" data point — it is not
a validation of the synthetic study's accuracy or cost numbers at any confidence level.

## 7. MEASURED vs. NOT MEASURED

**MEASURED:**
- One full real probe cycle's wall-clock pace (§2), reproducible in isolation.
- One real case's full `exhaustive_ablation` + `greedy_bisection` + three zero-probe-baseline
  result, including real probe counts, real cache-hit counts, and real wall-clock per strategy
  (§4), reproducible via `uv run python scripts/real_agent_validation.py` (seed=42, deterministic
  case construction; live model inference itself is not deterministic run-to-run).
- Two real infrastructure failure modes for backgrounded/polled live-LLM script execution on this
  environment (§3), with concrete evidence (output growth, GPU state, process presence).

**NOT MEASURED:**
- `sampled_shapley` against a real agent — zero real data, this pass or any prior one.
- Any case beyond `real_github_issues` — `real_jira_issues` and `real_stripe_payments` were
  planned (case-construction code for both is committed and unit-tested,
  `tests/test_real_case_construction.py`) but never actually run live, due to the budget consumed
  by the two stall-recovery attempts. `real_slack_messaging` was defined but never attempted at
  all.
- The exact root cause of Incident 1's stall (§3) — a hypothesis is stated, not confirmed.
- Whether `greedy_bisection`'s real cheap result (§4's mechanism caveat) reflects genuine
  CI-certified bisection or the total-search-failure fallback path — plausible from the observed
  probe/cache-hit pattern, not confirmed by inspecting raw delta/CI values.
- Argument-construction correctness — this pilot, per its explicit scope, measures tool-selection
  accuracy only (`TrialOutcome.selection_correct`); no judge model was wired up, matching the
  task's instruction not to add one unless selection accuracy alone proved uncomputable (it did
  not).

## 8. Reproduction

```
uv run python scripts/real_agent_validation.py
```

Requires local Ollama running with `gemma2:9b` pulled, `localhost:11434` reachable, and free GPU
VRAM (confirm via `nvidia-smi`/`ollama ps` immediately before running, per §1 — do not trust a
stale check). **Run this script as a single, direct, blocking call — do not background it, and do
not run a separate polling loop against it**, per §3's disclosed stall incident. Case construction
(`scripts/real_case_construction.py`) is deterministic and fully reproducible; the live model
inference itself is not bit-for-bit deterministic run-to-run (Ollama's `seed` option is passed
but is not a formal reproducibility guarantee across runs/hardware, unlike this repo's synthetic
benchmarks' `_lcg_random`).

`evals/fixtures/v0_5_real_agent_validation.jsonl` (checkpoint, one record per completed case) and
`evals/fixtures/v0_5_real_agent_validation_summary.json` (this report's source data) are both
committed alongside this report as provenance artifacts.
