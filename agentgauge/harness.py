"""Regression harness core engine (AgentGauge v2, Task 3).

Per the eval doctrine (`reports/v2_eval_doctrine.md`, Component 2): this is a
hypothesis test (did a change cause a measurable success-rate delta), not a
correlational score. Evaluated by minimum detectable effect (MDE) at fixed
power, false-alarm rate under the null, and replay determinism -- see
`reports/v2_harness_evaluation.md` for the measured numbers.

This module is pure statistics + decomposition logic, deliberately separated
from live LLM-calling code (`agentgauge.runner`) so it can be tested with real,
already-collected historical trial data with zero inference cost, and so the
same engine works whether trials come from a live run or a replay cassette.
"""

from __future__ import annotations

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
