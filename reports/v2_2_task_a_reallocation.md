# AgentGauge v2.2 — Task A: was 4b adequately powered? (reorder addendum)

Addendum to `reports/v2_2_optimal_allocation.md` (Task 1) and the original
`scripts/v2_2_cross_model_full.py` run. Zero new inference for A1/A3 (pure
simulation via `agentgauge/harness.py`); A2 is one live rerun,
`scripts/v2_2_cross_model_pooled.py`, `evals/fixtures/v2_2_cross_model_pooled.json`.

## A1. Was the running 4b (32 tasks) at the Task 1 optimum?

No. Task 1's compute-optimal allocation is **100 tasks/arm × 1 trial/task**
(MDE=0.0848 at 80% power, `reports/v2_2_optimal_allocation.md` 1b/1c). The
32-task run used less than a third of that.

Achieved MDE by task count (80% power, `simulate_mde_task_level`,
`n_simulations=2000`, calibrated params, `trials_per_task=1` throughout):

| n_tasks/arm | MDE (80% power) |
|---|---|
| 32 (original 4b) | **0.1443** |
| 50 | 0.1184 |
| 62 (real ceiling, see A2) | 0.1061 |
| 100 (Task 1 optimum) | 0.0848 |

32 tasks is underpowered by a wide margin — its MDE is 70% worse than the
100-task optimum. The prediction in the task brief ("32 tasks will likely
return the same inconclusive result as last round") held: the original 4b run
showed joint success rate flat at 0.500→0.500 (gemma2:9b), 0.500→0.500
(llama3.1:8b), and a small 0.469→0.4375 drop (qwen2.5:7b) —
all far smaller than what a 32-task design can even resolve.

## A2. Scaling toward the optimum — the real achievable ceiling is 62, not 100

100 tasks assumes an unlimited task bank. It isn't unlimited: the "argument
construction degrades under vague vs. clear schemas" phenomenon under test
has exactly **two** hand-authored fixtures in this repo with real gold
constraints —

- `call_constraints_server` / `call_constraints_server_fixed` — 32 tasks
- `call_constraints_v2_server` / `call_constraints_v2_server_fixed` — 30 tasks

Both read directly (not assumed from filenames): same design — 6 tools, FORMAT
/ENUM/RANGE constraint mix, type-only schemas with no description in the
"bad" variant, full descriptions restored in `_fixed`. Genuinely the same
causal question, independently authored ("Run 2" per the v2 file's own header
comment), safe to pool.

Other `_fixed` pairs that exist in the repo (`confusable_server_fixed`,
`grounded_server_fixed`, `mediocre_server_fixed`) were **not** pooled in —
they test different phenomena (tool-selection disambiguation, general
description-quality tiers, not constrained-argument construction). Pooling
them would inflate n by answering a different question with each task,
which is not a legitimate way to reach 100; it would just be a different,
uncontrolled measurement wearing this one's MDE number.

**Real ceiling: 62 tasks/arm** (`scripts/v2_2_cross_model_pooled.py`,
`evals/fixtures/v2_2_cross_model_pooled.json`) — pooling two real fixtures,
not fabricating tasks. Live result, all 3 models, pooled joint success rate
before → after:

| Model | Before | After | Δ |
|---|---|---|---|
| gemma2:9b | 0.4194 | 0.4355 | **+0.0161** |
| llama3.1:8b | 0.3548 | 0.3548 | **+0.0000** |
| qwen2.5:7b | 0.3226 | 0.3226 | **+0.0000** |

## A3. Achieved MDE at n=62 — and why "flat" here is not "no effect"

**MDE at n=62, trials/task=1: 0.1061 at 80% power (0.1425 at 95% power).**
Still above the 0.10 ship target — 62 real tasks is not enough to reliably
detect a 10-point regression, only something closer to an 11-point one.

All three measured deltas (+1.6pp, 0.0pp, 0.0pp) are far below 10.6pp — an
order of magnitude below the study's own resolving power at this n. **The
honest reading is "inconclusive at n=62," not "no argument-degradation
effect."** A true effect anywhere below ~10.6pp (in either direction) would
be statistically indistinguishable from the null at this sample size. This
is reported plainly per the task brief's requirement not to round an
underpowered null up to a confident "no effect" finding.

**What would resolve it:** authoring ~38 more real gold-constraint tasks
(to reach the Task 1 optimum of 100) on either existing fixture, or a third
comparable fixture. Out of scope for this pass — not attempted, not
approximated with synthetic tasks, disclosed as the actual limitation rather
than papered over.

## CUPED / ICC note

No new finding here beyond Task 1 (`reports/v2_2_optimal_allocation.md` 1d):
`trials_per_task=1` remains correct and does not break CUPED at this or any
tested n_tasks — this is an n_tasks ceiling problem, not a trials-per-task
problem.

## Independent verification

A separate verifier agent re-ran the MDE simulation from source (all four
values matched to reported precision), re-read the pooled JSON fixture
directly against the report's table (exact match, all 6 model×variant
entries), and re-read all four `call_constraints*` example server files plus
`confusable_server`/`confusable_server_fixed` to check the pooling-legitimacy
claim independently rather than take it on assertion. **All three items:
CONFIRMED**, with one cosmetic nuance noted (only the v2 fixture's docstring
literally uses the FORMAT/ENUM/RANGE taxonomy; the original fixture's
docstring calls its hard tools "enum-constrained" without that label — same
design, different wording, not a design mismatch).
