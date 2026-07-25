# AgentGauge v2 — regression harness evaluation (Task 3)

Per the eval doctrine (`reports/v2_eval_doctrine.md`, Component 2): the harness's task is a
hypothesis test (did a change cause a measurable success-rate change), evaluated by minimum
detectable effect (MDE) at fixed power, false-alarm rate under the null, and replay determinism —
never a correlation. All numbers below are measured, not assumed.

## 3a. The diff engine

`agentgauge/harness.py`'s `diff_from_trials(before_trials, after_trials, threshold)` is the core
engine behind `agentgauge diff <before> <after>`: bootstrap-CI comparison of joint task-success
rate, decomposed into selection accuracy and argument-construction accuracy (Task 4), with an
explicit sensitivity gate (Task 3e). Pure statistics, zero LLM dependency in the engine itself —
tested with 16 unit tests (`tests/test_harness.py`), all passing, covering clear regressions, clear
improvements, ties, the low-n insufficient-sensitivity case, and the selection/argument
decomposition on a synthetic reproduction of the real `call_constraints` failure pattern.

## 3b. Minimum detectable effect (MDE) — the headline power table

Computed via `simulate_minimum_detectable_effect` (binary-search over true effect size, binomial
outcome model, 1000 simulations per cell), at two baseline rates: **0.75**, the actual mean
`task_success_rate` across the 44 valid historical records in
`evals/fixtures/predictive_validity/results_raw.json` (not assumed — derived and printed at
computation time), and **0.50**, a higher-variance scenario (binomial variance peaks at p=0.5, so
this brackets the realistic range).

| n_trials per arm | Power | MDE @ baseline=0.75 | MDE @ baseline=0.50 |
|---|---|---|---|
| 5 | 80% | **0.711** | 0.500 |
| 5 | 95% | 0.750 | 0.500 |
| 10 | 80% | **0.598** | 0.475 |
| 10 | 95% | 0.692 | 0.500 |
| 20 | 80% | **0.433** | 0.391 |
| 20 | 95% | 0.537 | 0.453 |
| 50 | 80% | **0.273** | 0.269 |
| 50 | 95% | 0.355 | 0.333 |

**The honest, unsoftened shippable claim:** at realistic trial counts (5–50 per arm, the same range
this entire study has run at), the harness needs a **large** true effect to reliably detect it. At
n=50 trials/arm — more than double what most of this study's own historical collection used per
tool set — the MDE at 80% power is still **0.27** (baseline 0.75) to **0.27** (baseline 0.50): a
regression has to cut task success by roughly a quarter before this harness can be expected to catch
it 80% of the time. At n=5 (closer to typical CI-budget trial counts), MDE is **0.71** — the harness
can only reliably detect a regression that destroys nearly all remaining headroom. This is a real
limitation, not a marketing number: **"detects an X-point regression at 95% confidence in N trials"
is honestly "detects roughly a 27-35 point regression in 50 trials, or a 47-75 point regression in
5-10 trials" (ranges span both the 0.75 and 0.50 baseline scenarios), not the tighter claim a reader
might hope for.** Detecting realistic single-digit or
low-double-digit regressions (the kind an actual PR is likely to introduce) requires substantially
more than 50 trials per arm — not measured here, flagged as the natural follow-up question in
`reports/v2_product_readiness.md`.

## 3c. False-alarm rate under the null

**Method:** for each of 44 real historical tool sets, its actual `run_results` trial pool was
bootstrap-resampled into two independent samples (simulating "running this exact tool set twice") —
2200 total null comparisons (44 tool sets × 50 repeated comparisons each), using **real observed
trial-to-trial variance**, not an assumed variance model.

**Result: 0/2200 false alarms (0.0000%)** — clears the doctrine's <5% target decisively.

**The nuance that must be reported alongside the headline number, per the doctrine's honesty
requirement:** breaking down all 2200 verdicts —

| Verdict | Count | % |
|---|---|---|
| `INSUFFICIENT_SENSITIVITY` (correctly abstains) | 1572 | 71.5% |
| `NO_CHANGE` (confidently confirms no effect) | 628 | 28.5% |
| `REGRESSION` or `IMPROVEMENT` (false alarm) | 0 | 0.0% |

**The 0% false-alarm rate is real, but a majority of it is achieved by the harness declining to
commit to any verdict, not by confidently and correctly saying "no change."** This is not a flaw —
abstaining under genuine uncertainty is exactly what the Task 3e sensitivity gate is designed to do,
and it is a direct, mechanistic explanation of *why* the MDE table above shows the numbers it does:
these 44 historical tool sets mostly have trial counts (12-48 total trials across several tasks) at
or below the range where the MDE table shows real detection power is limited, so the harness
correctly recognizes it often cannot resolve the question at this sample size. A false-alarm rate
this low, achieved this honestly, is a genuine asset for CI-gate trust; a reader should understand
it as "this harness rarely lies," not "this harness rarely fails to notice."

## 3d. Replay determinism

**Method:** the same before/after trial split (from `echo_server`'s real historical data) run through
`diff_from_trials` 50 times with identical input and a fixed seed.

**Result: 50/50 runs produced byte-identical output** (delta, CI bounds, verdict, and message string
all identical every time) — **100% determinism**, confirmed empirically rather than assumed from the
fixed-seed design. This validates the deterministic core has no hidden non-determinism (dict
ordering, floating-point accumulation order, etc.) that could make a CI gate flap on identical inputs.

## 3e. Sensitivity reporting (the RW1-confound fix)

Implemented directly in `diff_from_trials`: when the bootstrap CI is wider than 2× the regression
threshold, the verdict is `INSUFFICIENT_SENSITIVITY` with an explicit message stating the run cannot
distinguish a real effect from noise at this trial count — never a bare point estimate presented as
if it were conclusive. On a genuine `NO_CHANGE` verdict (CI resolves and excludes both directions),
the message states plainly: *"Descriptions are not the bottleneck for this tool set's task success at
the trial count used here."* This is the direct fix for the predictive-validity study's RW1 confound
(a family where task success was flat across all quality arms because tool names alone were
sufficient — flat correlation was previously reported as ambiguous, when the real, checkable fact was
"quality isn't the bottleneck here"). Covered by dedicated tests in `tests/test_harness.py`
(`test_insufficient_sensitivity_with_few_trials`, `test_identical_trials_no_change`).

## Summary against the doctrine's pre-declared bar

- False-alarm rate: **passes** decisively (0% vs. <5% target) — with the honest caveat that most of
  that safety margin comes from appropriate abstention, not confident correct nulls, at the trial
  counts this study's historical data actually used.
- Determinism: **passes** (100%, empirically confirmed).
- MDE: **measured, not a marketing number** — real detection power at realistic trial counts (5-50)
  requires large true effects (27-75 percentage points depending on n and power); this is reported
  as a genuine, sobering limitation per the doctrine's "report real numbers even if unimpressive"
  requirement, not softened into a more attractive-sounding claim.
