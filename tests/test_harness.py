"""Tests for agentgauge.harness (v2 regression harness core engine)."""

from __future__ import annotations

from agentgauge.harness import (
    DecomposedRate,
    TrialOutcome,
    Verdict,
    bootstrap_delta_ci,
    diff_from_trials,
    simulate_minimum_detectable_effect,
)


class TestTrialOutcomeDecomposition:
    """Task 4: selection-correctness must be measured separately from
    argument-correctness -- the call_constraints family's real failure mode
    (100% argument-construction, 0% tool-selection) is invisible otherwise."""

    def test_correct_selection_full_argument_score(self) -> None:
        t = TrialOutcome(task_tool_name="get_a", selected_tool="get_a", constraint_satisfaction=1.0)
        assert t.selection_correct is True
        assert t.argument_score == 1.0
        assert t.joint_success == 1.0

    def test_wrong_selection_argument_score_is_none_not_zero(self) -> None:
        # A wrong-tool trial's constraint_satisfaction in the raw data is
        # stored as 0.0 by convention (see predictive_validity_study.py), but
        # argument_score must be None (undefined), not 0.0 -- conflating
        # "wrong tool" with "right tool, bad argument" is exactly the v1
        # blind spot this decomposition exists to fix.
        t = TrialOutcome(task_tool_name="get_a", selected_tool="get_b", constraint_satisfaction=0.0)
        assert t.selection_correct is False
        assert t.argument_score is None
        assert t.joint_success == 0.0

    def test_correct_selection_partial_argument_score(self) -> None:
        t = TrialOutcome(task_tool_name="set_x", selected_tool="set_x", constraint_satisfaction=0.5)
        assert t.selection_correct is True
        assert t.argument_score == 0.5


class TestDecomposedRate:
    def test_call_constraints_style_pattern(self) -> None:
        """Reproduces the exact call_constraints_server pattern found in the
        predictive-validity study: 0% wrong-tool-selection, but real
        argument-construction degradation -- a v1 joint metric shows this as
        "flat success", hiding the real defect entirely."""
        trials = [
            TrialOutcome("ping", "ping", 1.0),
            TrialOutcome("ping", "ping", 0.5),
            TrialOutcome("ping", "ping", 0.0),
            TrialOutcome("ping", "ping", 1.0),
        ]
        rate = DecomposedRate.from_trials(trials)
        assert rate.selection_accuracy == 1.0  # always selected correctly
        assert rate.argument_accuracy_given_correct_selection == 0.625  # (1+0.5+0+1)/4
        assert rate.joint_success_rate == 0.625

    def test_all_wrong_selection_argument_accuracy_is_none(self) -> None:
        trials = [TrialOutcome("a", "b", 0.0), TrialOutcome("a", "b", 0.0)]
        rate = DecomposedRate.from_trials(trials)
        assert rate.selection_accuracy == 0.0
        assert rate.argument_accuracy_given_correct_selection is None

    def test_empty_trials(self) -> None:
        rate = DecomposedRate.from_trials([])
        assert rate.n_trials == 0
        assert rate.joint_success_rate == 0.0


class TestBootstrapDeltaCI:
    def test_identical_arms_ci_straddles_zero(self) -> None:
        arm = [1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0]
        delta, lo, hi = bootstrap_delta_ci(arm, arm, seed=42)
        assert delta == 0.0
        assert lo <= 0.0 <= hi

    def test_clear_positive_effect_detected(self) -> None:
        before = [0.0] * 20
        after = [1.0] * 20
        delta, lo, hi = bootstrap_delta_ci(before, after, seed=42)
        assert delta == 1.0
        assert lo > 0.0  # CI should clearly exclude zero

    def test_deterministic_given_same_seed(self) -> None:
        before = [1.0, 0.5, 0.0, 1.0, 0.5]
        after = [0.5, 0.0, 0.0, 0.5, 1.0]
        result1 = bootstrap_delta_ci(before, after, seed=42)
        result2 = bootstrap_delta_ci(before, after, seed=42)
        assert result1 == result2

    def test_no_index_error_across_many_seeds_and_sizes(self) -> None:
        """Regression test for a real crash found during Task 7's adversarial
        pass: the LCG's next_float() can return exactly 1.0 (state saturates
        at 0x7FFFFFFF), so `int(rng() * n)` can equal `n` -- one past the end
        of the resample list. Runs enough (seed, n_resamples) combinations to
        reliably hit the saturated state at least once; a fixed build must not
        raise IndexError for any of them."""
        before = [0.2, 0.4, 0.6, 0.8, 1.0]
        after = [0.1, 0.3, 0.5, 0.7, 0.9]
        for seed in range(200):
            bootstrap_delta_ci(before, after, n_resamples=50, seed=seed)


class TestDiffFromTrials:
    def test_clear_regression_detected(self) -> None:
        before = [TrialOutcome("t", "t", 1.0) for _ in range(20)]
        after = [TrialOutcome("t", "t", 0.0) for _ in range(20)]
        result = diff_from_trials(before, after, threshold=0.05)
        assert result.verdict == Verdict.REGRESSION
        assert result.exit_code == 1

    def test_clear_improvement_detected(self) -> None:
        before = [TrialOutcome("t", "t", 0.0) for _ in range(20)]
        after = [TrialOutcome("t", "t", 1.0) for _ in range(20)]
        result = diff_from_trials(before, after, threshold=0.05)
        assert result.verdict == Verdict.IMPROVEMENT
        assert result.exit_code == 0

    def test_identical_trials_no_change(self) -> None:
        trials = [TrialOutcome("t", "t", 0.8) for _ in range(20)]
        result = diff_from_trials(trials, trials, threshold=0.05)
        assert result.verdict == Verdict.NO_CHANGE
        assert result.exit_code == 0

    def test_insufficient_sensitivity_with_few_trials(self) -> None:
        # Small n, noisy outcomes -> CI too wide to resolve a small threshold.
        before = [TrialOutcome("t", "t", 1.0), TrialOutcome("t", "t", 0.0)]
        after = [TrialOutcome("t", "t", 0.0), TrialOutcome("t", "t", 1.0)]
        result = diff_from_trials(before, after, threshold=0.05)
        assert result.verdict == Verdict.INSUFFICIENT_SENSITIVITY
        assert "does not have enough trials" in result.message

    def test_decomposition_reported_separately_in_result(self) -> None:
        """The call_constraints regression pattern: selection stays perfect,
        argument accuracy drops -- both must be visible in the diff result,
        not collapsed into one joint number."""
        before = [TrialOutcome("t", "t", 1.0) for _ in range(10)]
        after = [TrialOutcome("t", "t", 0.3) for _ in range(10)]
        result = diff_from_trials(before, after, threshold=0.05)
        assert result.before_decomposed.selection_accuracy == 1.0
        assert result.after_decomposed.selection_accuracy == 1.0
        assert result.before_decomposed.argument_accuracy_given_correct_selection == 1.0
        assert result.after_decomposed.argument_accuracy_given_correct_selection == 0.3
        assert result.verdict == Verdict.REGRESSION


class TestMinimumDetectableEffect:
    def test_mde_decreases_as_n_increases(self) -> None:
        """Larger sample size should require a smaller true effect to detect
        at the same power -- the basic sanity check on the MDE simulation."""
        mde_small_n = simulate_minimum_detectable_effect(
            baseline_rate=0.7, n_trials=5, power=0.8, n_simulations=30, seed=42
        )
        mde_large_n = simulate_minimum_detectable_effect(
            baseline_rate=0.7, n_trials=50, power=0.8, n_simulations=30, seed=42
        )
        assert mde_large_n < mde_small_n

    def test_mde_is_positive_and_bounded(self) -> None:
        mde = simulate_minimum_detectable_effect(
            baseline_rate=0.5, n_trials=10, power=0.8, n_simulations=30, seed=42
        )
        assert 0.0 < mde <= 1.0
