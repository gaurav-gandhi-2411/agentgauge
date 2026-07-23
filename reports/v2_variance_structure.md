# AgentGauge v2.1 — variance structure (Task 1)

Zero inference. Computed from `evals/fixtures/predictive_validity/results_raw.json` (5,535 trial
records across 720 (tool_set, task) groups, 45 historical runs). Script:
`scripts/v2_variance_structure.py`, output: `evals/fixtures/v2_variance_structure.json`.
**Independently re-derived from raw data by a separate verifier (fresh script, not a re-run of
this one) — all three numbers below CONFIRMED.**

These numbers gate the Task 2 redesign, per the task brief. They are reported before any estimator
code changes.

## 1a. Intraclass correlation (ICC) of trial outcomes within (tool_set, task)

| Quantity | Value |
|---|---|
| Total trials (N) | 5,535 |
| (tool_set, task) groups (k) | 720 |
| Mean trials per group | 7.69 |
| ICC(1), one-way random-effects, unbalanced-ANOVA formula | **0.793** |
| Nominal n | 5,535 |
| **Effective sample size** (`n / (1 + (m̄-1)·ICC)`) | **878** |
| Groups with exactly zero within-group variance (all repeated trials byte-identical) | **650 / 720 (90.3%)** |

**Reading:** repeated trials on the same (tool_set, task) pair carry almost no independent
information — 90.3% of groups show *zero* measurable variance across their ~8 nominal repeats, and
the ICC-adjusted effective sample size is **878, not 5,535** (a 15.9% efficiency ratio). The
existing v2 MDE table (`reports/v2_harness_evaluation.md` §3b) treats each recorded "trial" as an
independent Bernoulli draw. **This confirms the task brief's premise directly: that MDE table is
optimistic, not conservative** — the true information content of "n=50 trials/arm" as historically
collected is closer to n≈8 independent draws' worth, if those 50 trials are 50 repeats of the same
handful of tasks rather than 50 distinct tasks.

## 1b. Nested variance decomposition

Exact sum-of-squares identity (holds for any nesting, balanced or not):
`SS_total = SS_between_toolset + SS_between_task_within_toolset + SS_between_trial_within_task`.

| Component | % of total variance |
|---|---|
| Between tool set | 25.9% |
| **Between task, within tool set** | **56.1%** |
| Between trial, within task (residual/noise) | 18.0% |

**Reading:** the majority of total outcome variance (56.1%) lives at the **task level** — which
specific task/tool is being tested — not at the tool-set level (26%, irrelevant to a single-server
before/after comparison anyway) or at pure trial-to-trial noise (18%, confirmed small, consistent
with 1a's near-zero within-group variance finding). **This tells us where to spend compute:**
running more distinct tasks per server buys far more statistical power than running more repeated
trials of the same task (18% of variance vs. 56%). It also tells us exactly what a paired design
(matching before/after on the same task) can remove: up to the 56.1% task-level share, if the
before/after correlation is high enough (see 1c).

## 1c. Before/after correlation on matched Phase-3 tasks

5 matched fixer pairs (bad/mediocre server → its LLM-rewritten `_fixed` counterpart, identical
task sets), 40 matched (before, after) task-mean pairs pooled:

| Pair | n matched tasks | Spearman rho |
|---|---|---|
| grounded_server → _fixed | 5 | 0.783 |
| confusable_server → _fixed | 16 | 0.868 |
| mediocre_server → _fixed | 5 | 0.632 |
| call_constraints_server → _fixed | 8 | 1.000 |
| call_constraints_v2_server → _fixed | 6 | 0.970 |
| **Pooled (n=40)** | — | **0.869** |
| **Pooled Pearson r (n=40)** | — | **0.881** |

**Reading:** ρ≈0.88 is high. Tasks that are hard before a description fix tend to still be hard
after (and easy tasks stay easy) — a large, stable per-task difficulty effect. Using the paired-
variance identity `Var(diff) = Var(before) + Var(after) - 2ρ·sd(before)·sd(after)`, at ρ=0.88 and
roughly equal arm variances, pairing removes on the order of **~76% of the variance** an unpaired
two-sample comparison would carry at the same n — before any other variance-reduction technique is
applied. This is the single largest lever available and is available at **zero extra inference
cost** (replay determinism is already 100%, so identical before/after task+seed pairs already exist
in the historical data).

## Decision this data drives

All three numbers point the same direction and are mutually consistent: trial-level repetition is
nearly worthless (1a, 18% of variance in 1b), task-level differences dominate (56% in 1b), and
task-level effects are highly stable across a description-quality intervention (1c, ρ=0.88). The
Task 2 redesign is therefore built in this priority order:
1. **Pair on task with common random numbers** (2a) — removes the 56.1% task-level variance share,
   justified directly by 1c's ρ=0.88.
2. **Report at the server level, tasks as the cluster** (2b) — matches 1b's finding that
   between-task variance, not between-trial noise, is what a cluster-robust estimator must account
   for; treating trials as the unit (as the old estimator did) ignores exactly the 82% of variance
   that isn't pure trial noise.
3. **CUPED / covariate adjustment** (2c) — a second-order refinement on top of pairing, using the
   before-arm value as the covariate; expected to buy comparatively less than 2a since 1c already
   shows pairing captures most of the removable task-level signal.
4. **Sequential testing** (2d) — justified by 1a: since repeat trials add little information once a
   handful have been run, a fixed n=50 that keeps sampling past the point of a clear verdict is
   wasted compute; early stopping should reduce expected sample size without a power cost.
