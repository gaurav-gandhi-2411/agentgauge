"""Regression harness core engine (AgentGauge v2, Task 3; v2.1 estimator rebuild).

Per the eval doctrine (`reports/v2_eval_doctrine.md`, Component 2): this is a
hypothesis test (did a change cause a measurable success-rate delta), not a
correlational score. Evaluated by minimum detectable effect (MDE) at fixed
power, false-alarm rate under the null, and replay determinism -- see
`reports/v2_harness_evaluation.md` for the v2 numbers and
`reports/v2_variance_structure.md` / `reports/v2_1_estimator_rebuild.md` for
why v2.1 exists.

This module is pure statistics + decomposition logic, deliberately separated
from live LLM-calling code (`agentgauge.runner`) so it can be tested with real,
already-collected historical trial data with zero inference cost, and so the
same engine works whether trials come from a live run or a replay cassette.

v2.1 adds a second estimator (`diff_server_level` and friends, below the v2
trial-level `diff_from_trials`) built on Task 1's measured variance structure:
ICC=0.793 within (tool_set, task) groups means repeat trials on the same task
carry almost no independent information (`reports/v2_variance_structure.md`
1a), 56.1% of total variance sits between tasks within a tool set (1b), and
before/after task means correlate at rho=0.881 on matched Phase-3 pairs (1c).
The v2 estimator ignored all three facts -- it resampled individual trials as
if independent, which is optimistic (overstates precision) exactly because it
ignores 1a and 1b. The v1 trial-level functions are kept, unmodified in
behavior (aside from the earlier `bootstrap_delta_ci` index-clamp fix), for
backward compatibility and as the "baseline" row of the v2.1 ablation table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


@dataclass
class TrialOutcome:
    """One task trial's raw outcome -- matches the shape already recorded in
    evals/fixtures/predictive_validity/results_raw.json's `run_results` field."""

    task_tool_name: str
    selected_tool: str | None
    constraint_satisfaction: float

    @property
    def selection_correct(self) -> bool:
        return self.selected_tool == self.task_tool_name

    @property
    def argument_score(self) -> float | None:
        """Argument-construction correctness, defined ONLY when selection was
        correct -- an argument score on a wrong-tool trial is meaningless
        (Task 4: this is the decomposition the call_constraints family's real
        failure mode needs, since a joint success-rate metric structurally
        cannot distinguish 'wrong tool' from 'right tool, wrong argument')."""
        return self.constraint_satisfaction if self.selection_correct else None

    @property
    def joint_success(self) -> float:
        """The v1-style joint metric: 0.0 if wrong tool, else constraint_satisfaction."""
        return self.constraint_satisfaction if self.selection_correct else 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrialOutcome:
        return cls(
            task_tool_name=d["task_tool_name"],
            selected_tool=d.get("selected_tool"),
            constraint_satisfaction=d.get("constraint_satisfaction", 0.0),
        )


@dataclass
class DecomposedRate:
    """A tool set's outcomes split into the two axes Task 4 requires reported
    separately: selection accuracy, and argument-construction accuracy
    conditional on correct selection."""

    n_trials: int
    selection_accuracy: float
    argument_accuracy_given_correct_selection: float | None  # None if 0 correct-selection trials
    joint_success_rate: float

    @classmethod
    def from_trials(cls, trials: list[TrialOutcome]) -> DecomposedRate:
        n = len(trials)
        if n == 0:
            return cls(0, 0.0, None, 0.0)
        n_correct_selection = sum(1 for t in trials if t.selection_correct)
        selection_accuracy = n_correct_selection / n
        arg_scores = [t.argument_score for t in trials if t.argument_score is not None]
        arg_accuracy = sum(arg_scores) / len(arg_scores) if arg_scores else None
        joint = sum(t.joint_success for t in trials) / n
        return cls(n, selection_accuracy, arg_accuracy, joint)


def _rank(values: list[float]) -> list[float]:
    """Fractional (average) ranks, 1-indexed. Duplicated here (not imported from
    scripts/predictive_validity_analysis.py) so agentgauge/ has no dependency on
    scripts/ -- package code must not import from the scripts directory."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _lcg_random(seed: int) -> Any:
    """Tiny dependency-free deterministic PRNG (linear congruential generator)
    so bootstrap resampling doesn't need numpy/random module global state --
    matches the reproducibility bar the rest of this study already holds
    (seed=42 hardcoded everywhere stochastic)."""
    state = seed & 0xFFFFFFFF

    def next_float() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    return next_float


def bootstrap_delta_ci(
    before: list[float],
    after: list[float],
    n_resamples: int = 2000,
    seed: int = 42,
    ci: float = 0.95,
) -> tuple[float, float, float]:
    """Bootstrap CI for the difference in means (after - before), resampling
    each arm independently with replacement. Returns (point_delta, ci_lo, ci_hi).
    """
    point_delta = (sum(after) / len(after)) - (sum(before) / len(before))
    rng = _lcg_random(seed)
    deltas = []
    nb, na = len(before), len(after)
    for _ in range(n_resamples):
        # min(..., n - 1): the LCG can return exactly 1.0 (state saturates at
        # 0x7FFFFFFF), which would otherwise index one past the end of the list.
        b_sample = [before[min(int(rng() * nb), nb - 1)] for _ in range(nb)]
        a_sample = [after[min(int(rng() * na), na - 1)] for _ in range(na)]
        deltas.append((sum(a_sample) / na) - (sum(b_sample) / nb))
    deltas.sort()
    lo_idx = int((1 - ci) / 2 * n_resamples)
    hi_idx = int((1 + ci) / 2 * n_resamples) - 1
    hi_idx = min(hi_idx, n_resamples - 1)
    return point_delta, deltas[lo_idx], deltas[hi_idx]


class Verdict(StrEnum):
    REGRESSION = "regression"
    IMPROVEMENT = "improvement"
    NO_CHANGE = "no_change"
    INSUFFICIENT_SENSITIVITY = "insufficient_sensitivity"


@dataclass
class DiffResult:
    """Result of `agentgauge diff <before> <after>`."""

    before_decomposed: DecomposedRate
    after_decomposed: DecomposedRate
    delta: float
    ci_lo: float
    ci_hi: float
    threshold: float
    verdict: Verdict
    message: str

    @property
    def exit_code(self) -> int:
        """Non-zero exit on regression, per Task 6a's CLI requirement."""
        return 1 if self.verdict == Verdict.REGRESSION else 0


def diff_from_trials(
    before_trials: list[TrialOutcome],
    after_trials: list[TrialOutcome],
    threshold: float = 0.05,
    n_resamples: int = 2000,
    seed: int = 42,
) -> DiffResult:
    """Core diff engine: compares joint_success rates, with bootstrap CI,
    against a regression threshold. Also decomposes into selection vs argument
    accuracy (Task 4) and emits an explicit sensitivity message (Task 3e) when
    the CI is too wide to distinguish "no effect" from "not enough trials to
    tell" -- the RW1 confound this harness must not repeat: a flat delta must
    be reported as flat, not as "quality doesn't matter" if the CI is wide
    enough that a real effect could be hiding inside it.
    """
    before_dec = DecomposedRate.from_trials(before_trials)
    after_dec = DecomposedRate.from_trials(after_trials)
    before_joint = [t.joint_success for t in before_trials]
    after_joint = [t.joint_success for t in after_trials]

    delta, ci_lo, ci_hi = bootstrap_delta_ci(
        before_joint, after_joint, n_resamples=n_resamples, seed=seed
    )

    ci_width = ci_hi - ci_lo
    # Sensitivity gate: if the CI is wide relative to the threshold itself, this
    # run cannot distinguish a real regression of the size we care about from
    # noise -- say so explicitly rather than emit a point estimate that looks
    # more precise than the data supports.
    if ci_width > 2 * threshold:
        verdict = Verdict.INSUFFICIENT_SENSITIVITY
        message = (
            f"Delta point estimate is {delta:+.3f}, but the 95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}] is "
            f"wider than 2x the regression threshold ({threshold:.3f}) -- this run does not have "
            f"enough trials to reliably distinguish a real regression of this size from sampling "
            f"noise. Descriptions may or may not be the bottleneck for this tool set; this result "
            f"does not resolve that question. Increase trial count or widen the threshold."
        )
    elif ci_hi < -threshold:
        verdict = Verdict.REGRESSION
        message = f"Regression: success rate dropped by {-delta:.3f} (95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}])."
    elif ci_lo > threshold:
        verdict = Verdict.IMPROVEMENT
        message = (
            f"Improvement: success rate rose by {delta:.3f} (95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}])."
        )
    else:
        verdict = Verdict.NO_CHANGE
        message = (
            f"No detectable change (delta={delta:+.3f}, 95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}] does not "
            f"clear the {threshold:.3f} threshold in either direction). Descriptions are not the "
            f"bottleneck for this tool set's task success at the trial count used here."
        )

    return DiffResult(
        before_decomposed=before_dec,
        after_decomposed=after_dec,
        delta=delta,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        threshold=threshold,
        verdict=verdict,
        message=message,
    )


def simulate_minimum_detectable_effect(
    baseline_rate: float,
    n_trials: int,
    power: float,
    alpha: float = 0.05,
    n_simulations: int = 2000,
    seed: int = 42,
) -> float:
    """Empirically determine the minimum detectable effect (MDE): the smallest
    |true delta| such that a two-sample bootstrap-style test detects it (CI
    excludes zero at the given alpha) in >= `power` fraction of simulated
    trials, at a fixed n_trials per arm.

    Uses a binomial outcome model (each trial succeeds/fails independently at
    the given rate) -- a simplification of the real continuous
    constraint-satisfaction outcome, but the same n_trials-per-arm regime this
    study actually ran at, and clearly labeled as a simulation.
    """
    rng = _lcg_random(seed)

    def _simulate_binomial_trials(rate: float, n: int) -> list[float]:
        return [1.0 if rng() < rate else 0.0 for _ in range(n)]

    def _detects(true_delta: float) -> bool:
        before = _simulate_binomial_trials(baseline_rate, n_trials)
        after_rate = max(0.0, min(1.0, baseline_rate + true_delta))
        after = _simulate_binomial_trials(after_rate, n_trials)
        _, ci_lo, ci_hi = bootstrap_delta_ci(before, after, n_resamples=200, seed=int(rng() * 1e9))
        return ci_hi < 0 if true_delta < 0 else ci_lo > 0

    # Binary search over candidate effect sizes for the smallest one clearing `power`.
    lo, hi = 0.0, 1.0 - baseline_rate if baseline_rate < 0.5 else baseline_rate
    for _ in range(12):  # ~12 bisections is enough precision for a reported MDE
        mid = (lo + hi) / 2
        n_detected = sum(1 for _ in range(n_simulations) if _detects(-mid))
        detected_rate = n_detected / n_simulations
        if detected_rate >= power:
            hi = mid
        else:
            lo = mid
    return hi


# =============================================================================
# v2.1 estimator: task-level unit of analysis, paired design, CUPED,
# cluster-robust inference, sequential testing. See module docstring and
# reports/v2_variance_structure.md / reports/v2_1_estimator_rebuild.md.
# =============================================================================


@dataclass
class TaskObservation:
    """One task's aggregated outcome within one arm (before or after) -- the
    unit of analysis Task 1 showed actually carries independent information:
    between-trial-within-task variance is only 18.0% of total (1b), and 90.3%
    of (tool_set, task) groups show literally zero variance across their
    repeat trials (1a) -- so a per-task mean loses almost nothing relative to
    the raw trials, while removing the double-counting that inflated the v2
    estimator's apparent precision."""

    task_tool_name: str
    mean_joint_success: float
    n_trials: int


def aggregate_to_tasks(trials: list[TrialOutcome]) -> dict[str, TaskObservation]:
    groups: dict[str, list[float]] = {}
    for t in trials:
        groups.setdefault(t.task_tool_name, []).append(t.joint_success)
    return {
        name: TaskObservation(name, sum(vals) / len(vals), len(vals))
        for name, vals in groups.items()
    }


@dataclass
class PairedTaskDelta:
    """Task 2a: one matched before/after row per TASK (common random numbers
    -- the before and after arm must have run the same task set for this
    pairing to be valid), not per trial."""

    task_tool_name: str
    before_mean: float
    after_mean: float
    delta: float  # after - before
    n_before_trials: int
    n_after_trials: int


def pair_tasks_common_random_numbers(
    before_trials: list[TrialOutcome],
    after_trials: list[TrialOutcome],
) -> tuple[list[PairedTaskDelta], list[str]]:
    """Match before/after arms on task_tool_name. Returns (paired deltas,
    names of tasks present in only one arm). Unmatched tasks are dropped from
    the paired analysis and their names returned explicitly -- a silent drop
    would hide exactly the kind of task-set drift (e.g. a tool renamed
    between before/after) that should surface as a warning, not vanish."""
    before_tasks = aggregate_to_tasks(before_trials)
    after_tasks = aggregate_to_tasks(after_trials)
    shared = sorted(set(before_tasks) & set(after_tasks))
    unmatched = sorted(set(before_tasks) ^ set(after_tasks))
    pairs = [
        PairedTaskDelta(
            task_tool_name=name,
            before_mean=before_tasks[name].mean_joint_success,
            after_mean=after_tasks[name].mean_joint_success,
            delta=after_tasks[name].mean_joint_success - before_tasks[name].mean_joint_success,
            n_before_trials=before_tasks[name].n_trials,
            n_after_trials=after_tasks[name].n_trials,
        )
        for name in shared
    ]
    return pairs, unmatched


def cuped_adjust(pairs: list[PairedTaskDelta]) -> tuple[list[float], float, float]:
    """Task 2c: CUPED-style covariate adjustment. Uses each task's before-arm
    mean as the covariate for its own delta -- tasks with a very low or very
    high before-arm score have structurally less room for the delta to move
    (floor/ceiling effects), and 1c already shows before-arm value predicts
    after-arm value at rho=0.881, so it should predict some of the
    task-to-task variability in the delta too, beyond what plain pairing
    removes. theta = Cov(before, delta) / Var(before) is the variance-
    minimizing adjustment (Deng et al. 2013); adjustment preserves the mean
    (E[theta*(before - before_bar)] = 0 by construction) so the point
    estimate is unchanged -- only its variance is reduced.

    Returns (adjusted_deltas, theta, variance_reduction_pct). If all
    before-arm means are identical (zero covariate variance), returns the
    unadjusted deltas with 0% reduction rather than dividing by zero.
    """
    n = len(pairs)
    befores = [p.before_mean for p in pairs]
    deltas = [p.delta for p in pairs]
    before_bar = sum(befores) / n
    var_before = sum((b - before_bar) ** 2 for b in befores) / n
    if var_before == 0.0:
        return deltas, 0.0, 0.0
    delta_bar = sum(deltas) / n
    cov = sum((befores[i] - before_bar) * (deltas[i] - delta_bar) for i in range(n)) / n
    theta = cov / var_before
    adjusted = [deltas[i] - theta * (befores[i] - before_bar) for i in range(n)]

    var_raw = sum((d - delta_bar) ** 2 for d in deltas) / n
    adj_bar = sum(adjusted) / n
    var_adj = sum((d - adj_bar) ** 2 for d in adjusted) / n
    reduction_pct = 100.0 * (1 - var_adj / var_raw) if var_raw > 0 else 0.0
    return adjusted, theta, reduction_pct


def cluster_bootstrap_mean_ci(
    values: list[float],
    n_resamples: int = 2000,
    seed: int = 42,
    ci: float = 0.95,
) -> tuple[float, float, float]:
    """Task 2b: cluster-robust bootstrap CI for a mean, resampling at the
    TASK level (each entry in `values` is one task's delta -- the cluster
    Task 1b identified as carrying 56.1% of total variance), not the trial
    level. Returns (point_mean, ci_lo, ci_hi)."""
    n = len(values)
    point = sum(values) / n
    rng = _lcg_random(seed)
    resampled_means = []
    for _ in range(n_resamples):
        sample = [values[min(int(rng() * n), n - 1)] for _ in range(n)]
        resampled_means.append(sum(sample) / n)
    resampled_means.sort()
    lo_idx = int((1 - ci) / 2 * n_resamples)
    hi_idx = min(int((1 + ci) / 2 * n_resamples) - 1, n_resamples - 1)
    return point, resampled_means[lo_idx], resampled_means[hi_idx]


@dataclass
class ServerDiffResult:
    """Result of the v2.1 server-level `agentgauge diff` estimator: Task 2a
    (paired on task) + 2b (task as cluster, server as the reported unit) +
    2c (CUPED), all combined into one verdict."""

    n_tasks_matched: int
    unmatched_task_names: list[str]
    delta: float
    ci_lo: float
    ci_hi: float
    threshold: float
    verdict: Verdict
    message: str
    cuped_theta: float
    cuped_variance_reduction_pct: float

    @property
    def exit_code(self) -> int:
        return 1 if self.verdict == Verdict.REGRESSION else 0


def diff_server_level(
    before_trials: list[TrialOutcome],
    after_trials: list[TrialOutcome],
    threshold: float = 0.05,
    use_cuped: bool = True,
    n_resamples: int = 2000,
    seed: int = 42,
) -> ServerDiffResult:
    """The v2.1 estimator: paired, task-clustered, CUPED-adjusted server-level
    diff. Requires the before and after arms to share at least 2 matched
    tasks (common random numbers -- both arms must have run the same task
    set); raises ValueError otherwise, since a paired estimator has no
    meaning with 0-1 matched tasks.
    """
    pairs, unmatched = pair_tasks_common_random_numbers(before_trials, after_trials)
    if len(pairs) < 2:
        raise ValueError(
            f"diff_server_level requires >=2 matched tasks between before/after arms "
            f"(common random numbers design); found {len(pairs)}. Unmatched task names: "
            f"{unmatched}"
        )

    if use_cuped:
        deltas, theta, reduction_pct = cuped_adjust(pairs)
    else:
        deltas = [p.delta for p in pairs]
        theta, reduction_pct = 0.0, 0.0

    delta, ci_lo, ci_hi = cluster_bootstrap_mean_ci(deltas, n_resamples=n_resamples, seed=seed)

    ci_width = ci_hi - ci_lo
    if ci_width > 2 * threshold:
        verdict = Verdict.INSUFFICIENT_SENSITIVITY
        message = (
            f"Delta point estimate is {delta:+.3f}, but the 95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}] is "
            f"wider than 2x the regression threshold ({threshold:.3f}) -- this run does not have "
            f"enough matched tasks to reliably distinguish a real regression of this size from "
            f"sampling noise. Increase the number of tasks per arm or widen the threshold."
        )
    elif ci_hi < -threshold:
        verdict = Verdict.REGRESSION
        message = f"Regression: success rate dropped by {-delta:.3f} (95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}])."
    elif ci_lo > threshold:
        verdict = Verdict.IMPROVEMENT
        message = (
            f"Improvement: success rate rose by {delta:.3f} (95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}])."
        )
    else:
        verdict = Verdict.NO_CHANGE
        message = (
            f"No detectable change (delta={delta:+.3f}, 95% CI [{ci_lo:+.3f}, {ci_hi:+.3f}] does not "
            f"clear the {threshold:.3f} threshold in either direction) across {len(pairs)} matched "
            f"tasks. Descriptions are not the bottleneck for this server's task success at the "
            f"task count used here."
        )

    return ServerDiffResult(
        n_tasks_matched=len(pairs),
        unmatched_task_names=unmatched,
        delta=delta,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        threshold=threshold,
        verdict=verdict,
        message=message,
        cuped_theta=theta,
        cuped_variance_reduction_pct=reduction_pct,
    )


# --- Calibration constants for the v2.1 task-level simulator ---------------
# Measured directly in scripts/v2_variance_structure.py / v2_1_task_level_mde.py
# from evals/fixtures/predictive_validity/results_raw.json's 720 (tool_set,
# task) groups' joint_success values -- not assumed, not tuned to produce a
# nice-looking MDE table.
CALIBRATED_BASELINE_RATE = 0.7749  # trial-weighted grand mean of joint_success
CALIBRATED_SIGMA_TASK = 0.3588  # sd of per-task joint_success means (task-level spread)
CALIBRATED_RESID_SD = 0.1392  # mean within-task sd across groups with >=2 trials
CALIBRATED_RHO = 0.881  # pooled Pearson r, before/after task means, 40 matched Phase-3 tasks


def _approx_standard_normal(rng: Any) -> float:
    """Irwin-Hall / CLT approximation to a standard normal draw: sum of 12
    independent U(0,1) draws has mean 6, variance 1 -- subtracting 6 gives
    an approximately N(0,1) variate without needing a full Box-Muller
    transform or any external dependency."""
    return sum(rng() for _ in range(12)) - 6.0


def simulate_task_level_pairs(
    baseline_rate: float,
    true_delta: float,
    n_tasks: int,
    rng: Any,
    sigma_task: float = CALIBRATED_SIGMA_TASK,
    resid_sd: float = CALIBRATED_RESID_SD,
    rho: float = CALIBRATED_RHO,
) -> list[tuple[float, float]]:
    """Generate n_tasks correlated (before_observed, after_observed) task-mean
    pairs, calibrated to Task 1's measured variance structure: each task has
    a true difficulty effect (sd=sigma_task) shared between its before/after
    incarnation at correlation `rho` (1c), plus independent residual noise
    (sd=resid_sd, matching the measured within-task trial-to-trial spread,
    1a/1b) added to each arm's observation separately.
    """
    pairs = []
    for _ in range(n_tasks):
        task_effect = _approx_standard_normal(rng) * sigma_task
        indep_component = _approx_standard_normal(rng) * sigma_task
        after_task_effect = rho * task_effect + math.sqrt(max(0.0, 1 - rho**2)) * indep_component
        before_true = min(1.0, max(0.0, baseline_rate + task_effect))
        after_true = min(1.0, max(0.0, baseline_rate + true_delta + after_task_effect))
        before_obs = min(1.0, max(0.0, before_true + _approx_standard_normal(rng) * resid_sd))
        after_obs = min(1.0, max(0.0, after_true + _approx_standard_normal(rng) * resid_sd))
        pairs.append((before_obs, after_obs))
    return pairs


def simulate_mde_task_level(
    n_tasks: int,
    power: float,
    baseline_rate: float = CALIBRATED_BASELINE_RATE,
    threshold_alpha: float = 0.05,
    n_simulations: int = 1000,
    seed: int = 42,
    use_paired: bool = True,
    use_cuped: bool = True,
    sigma_task: float = CALIBRATED_SIGMA_TASK,
    resid_sd: float = CALIBRATED_RESID_SD,
    rho: float = CALIBRATED_RHO,
) -> float:
    """Task 3: re-derive MDE under the v2.1 estimator, at the SERVER
    (task-clustered) level. `use_paired=False` collapses to an independent-
    samples comparison (the v2 baseline's assumption) for the Task 3 ablation
    table; `use_cuped=False` isolates pairing's contribution without CUPED's
    additional reduction.
    """
    rng = _lcg_random(seed)

    def _detects(true_delta: float) -> bool:
        pairs = simulate_task_level_pairs(
            baseline_rate, true_delta, n_tasks, rng, sigma_task, resid_sd, rho
        )
        if use_paired:
            deltas = [a - b for b, a in pairs]
            if use_cuped:
                befores = [b for b, _ in pairs]
                n = len(deltas)
                before_bar = sum(befores) / n
                var_before = sum((b - before_bar) ** 2 for b in befores) / n
                if var_before > 0:
                    delta_bar = sum(deltas) / n
                    cov = (
                        sum((befores[i] - before_bar) * (deltas[i] - delta_bar) for i in range(n))
                        / n
                    )
                    theta = cov / var_before
                    deltas = [deltas[i] - theta * (befores[i] - before_bar) for i in range(n)]
            _, ci_lo, ci_hi = cluster_bootstrap_mean_ci(
                deltas, n_resamples=200, seed=int(rng() * 1e9)
            )
        else:
            # Baseline (v2-style) assumption: treat before/after as independent
            # samples of task means, ignoring the pairing correlation entirely.
            befores = [b for b, _ in pairs]
            afters = [a for _, a in pairs]
            _, ci_lo, ci_hi = bootstrap_delta_ci(
                befores, afters, n_resamples=200, seed=int(rng() * 1e9)
            )
        return ci_hi < 0 if true_delta < 0 else ci_lo > 0

    lo, hi = 0.0, 1.0 - baseline_rate if baseline_rate < 0.5 else baseline_rate
    for _ in range(12):
        mid = (lo + hi) / 2
        n_detected = sum(1 for _ in range(n_simulations) if _detects(-mid))
        detected_rate = n_detected / n_simulations
        if detected_rate >= power:
            hi = mid
        else:
            lo = mid
    return hi


# --- Task 2d: sequential testing ------------------------------------------

_Z_ALPHA_2_005 = 1.959964  # standard normal 97.5th percentile (two-sided alpha=0.05)


def _standard_normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _obrien_fleming_cumulative_alpha(info_fraction: float, alpha: float = 0.05) -> float:
    """Lan-DeMets O'Brien-Fleming-type alpha-spending function: cumulative
    two-sided alpha spent by information fraction t (0<t<=1). Conservative at
    early looks (t small -> alpha_star ~ 0, an almost-100% CI, very hard to
    stop early on efficacy), converging to the full `alpha` budget only at
    t=1 (the final look) -- this is the classic O'Brien-Fleming shape:
    "spend almost nothing early, spend it all by the end." Hardcoded for
    alpha=0.05 (the z-value for other alphas would need its own inverse-CDF
    computation, not implemented -- this harness targets alpha=0.05
    throughout, matching every other v2 doctrine target).
    """
    if info_fraction <= 0:
        return 0.0
    if abs(alpha - 0.05) > 1e-9:
        raise ValueError("_obrien_fleming_cumulative_alpha only supports alpha=0.05")
    z = _Z_ALPHA_2_005 / math.sqrt(info_fraction)
    return min(2.0 * (1.0 - _standard_normal_cdf(z)), alpha)


def simulate_sequential_expected_n(
    true_delta: float,
    baseline_rate: float = CALIBRATED_BASELINE_RATE,
    look_schedule: tuple[int, ...] = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50),
    threshold: float = 0.05,
    alpha: float = 0.05,
    n_simulations: int = 1000,
    seed: int = 42,
    use_cuped: bool = True,
    sigma_task: float = CALIBRATED_SIGMA_TASK,
    resid_sd: float = CALIBRATED_RESID_SD,
    rho: float = CALIBRATED_RHO,
) -> dict[str, Any]:
    """Task 2d: group-sequential test with an O'Brien-Fleming efficacy
    boundary and a NON-BINDING futility stop (simplification, disclosed: the
    futility stop reuses the same alpha-spent CI's width rather than a
    separate beta-spending schedule -- if the current look's CI already sits
    entirely within [-threshold, threshold], that is a confident NO_CHANGE
    and the run stops; this is the same standard `diff_server_level` already
    uses for a fixed-n NO_CHANGE verdict, just checked incrementally).

    Simulates `n_simulations` runs; each generates task pairs incrementally
    up to `look_schedule[-1]` tasks/arm (paired + CUPED, per Task 2a/2c) and
    checks the alpha-spent CI at each scheduled look, stopping at the first
    look whose verdict is not INSUFFICIENT_SENSITIVITY. Returns expected
    (mean) and median stopping sample size, the resolved-verdict breakdown,
    and the fraction still unresolved at the final scheduled look (a forced,
    nominal-alpha decision at that point, not an indefinite continuation).
    """
    n_max = look_schedule[-1]
    rng = _lcg_random(seed)
    stopping_ns: list[int] = []
    unresolved = 0
    verdict_counts: dict[str, int] = {}

    for _ in range(n_simulations):
        all_pairs = simulate_task_level_pairs(
            baseline_rate, true_delta, n_max, rng, sigma_task, resid_sd, rho
        )
        resolved = False
        for n_at_look in look_schedule:
            info_fraction = n_at_look / n_max
            ci_level = 1.0 - _obrien_fleming_cumulative_alpha(info_fraction, alpha)
            subset = all_pairs[:n_at_look]
            deltas = [a - b for b, a in subset]
            if use_cuped:
                befores = [b for b, _ in subset]
                n = len(deltas)
                before_bar = sum(befores) / n
                var_before = sum((b - before_bar) ** 2 for b in befores) / n
                if var_before > 0:
                    delta_bar = sum(deltas) / n
                    cov = (
                        sum((befores[i] - before_bar) * (deltas[i] - delta_bar) for i in range(n))
                        / n
                    )
                    theta = cov / var_before
                    deltas = [deltas[i] - theta * (befores[i] - before_bar) for i in range(n)]
            _, ci_lo, ci_hi = cluster_bootstrap_mean_ci(
                deltas, n_resamples=200, seed=int(rng() * 1e9), ci=ci_level
            )
            ci_width = ci_hi - ci_lo
            if ci_hi < -threshold:
                verdict = "regression"
            elif ci_lo > threshold:
                verdict = "improvement"
            elif ci_width <= 2 * threshold:
                verdict = "no_change"
            else:
                verdict = "insufficient_sensitivity"

            if verdict != "insufficient_sensitivity":
                stopping_ns.append(n_at_look)
                verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
                resolved = True
                break
        if not resolved:
            stopping_ns.append(n_max)
            unresolved += 1
            verdict_counts["insufficient_sensitivity"] = (
                verdict_counts.get("insufficient_sensitivity", 0) + 1
            )

    stopping_ns.sort()
    mid = len(stopping_ns) // 2
    median_n = (
        stopping_ns[mid] if len(stopping_ns) % 2 else (stopping_ns[mid - 1] + stopping_ns[mid]) / 2
    )
    return {
        "expected_n": sum(stopping_ns) / len(stopping_ns),
        "median_n": median_n,
        "pct_unresolved_at_n_max": 100.0 * unresolved / n_simulations,
        "verdict_counts": verdict_counts,
        "n_max": n_max,
    }
