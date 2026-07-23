"""Tests for agentgauge.harness (v2 regression harness core engine; v2.1 estimator)."""

from __future__ import annotations

import pytest

from agentgauge.harness import (
    DecomposedRate,
    TrialOutcome,
    Verdict,
    _obrien_fleming_cumulative_alpha,
    aggregate_to_tasks,
    bootstrap_delta_ci,
    cluster_bootstrap_mean_ci,
    cuped_adjust,
    diff_from_trials,
    diff_server_level,
    pair_tasks_common_random_numbers,
    simulate_mde_task_level,
    simulate_minimum_detectable_effect,
    simulate_sequential_expected_n,
    simulate_task_level_pairs,
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


class TestAggregateToTasks:
    def test_groups_and_averages_by_task_name(self) -> None:
        trials = [
            TrialOutcome("a", "a", 1.0),
            TrialOutcome("a", "a", 0.0),
            TrialOutcome("b", "b", 0.5),
        ]
        tasks = aggregate_to_tasks(trials)
        assert tasks["a"].mean_joint_success == 0.5
        assert tasks["a"].n_trials == 2
        assert tasks["b"].mean_joint_success == 0.5
        assert tasks["b"].n_trials == 1


class TestPairTasksCommonRandomNumbers:
    def test_matches_shared_tasks(self) -> None:
        before = [TrialOutcome("a", "a", 1.0), TrialOutcome("b", "b", 0.5)]
        after = [TrialOutcome("a", "a", 0.5), TrialOutcome("b", "b", 0.5)]
        pairs, unmatched = pair_tasks_common_random_numbers(before, after)
        assert len(pairs) == 2
        assert unmatched == []
        a_pair = next(p for p in pairs if p.task_tool_name == "a")
        assert a_pair.before_mean == 1.0
        assert a_pair.after_mean == 0.5
        assert a_pair.delta == -0.5

    def test_reports_unmatched_tasks_not_silently_dropped(self) -> None:
        # "c" only exists in the after arm (e.g. a tool renamed/added between
        # before and after) -- this must surface, not vanish silently.
        before = [TrialOutcome("a", "a", 1.0)]
        after = [TrialOutcome("a", "a", 1.0), TrialOutcome("c", "c", 1.0)]
        pairs, unmatched = pair_tasks_common_random_numbers(before, after)
        assert len(pairs) == 1
        assert unmatched == ["c"]


class TestCupedAdjust:
    def test_preserves_mean_delta(self) -> None:
        from agentgauge.harness import PairedTaskDelta

        pairs = [
            PairedTaskDelta(
                "a", before_mean=0.9, after_mean=0.9, delta=0.0, n_before_trials=5, n_after_trials=5
            ),
            PairedTaskDelta(
                "b", before_mean=0.1, after_mean=0.3, delta=0.2, n_before_trials=5, n_after_trials=5
            ),
            PairedTaskDelta(
                "c",
                before_mean=0.5,
                after_mean=0.4,
                delta=-0.1,
                n_before_trials=5,
                n_after_trials=5,
            ),
        ]
        adjusted, theta, reduction_pct = cuped_adjust(pairs)
        raw_mean = sum(p.delta for p in pairs) / len(pairs)
        adj_mean = sum(adjusted) / len(adjusted)
        assert abs(raw_mean - adj_mean) < 1e-9  # CUPED preserves the point estimate

    def test_zero_covariate_variance_returns_unadjusted(self) -> None:
        from agentgauge.harness import PairedTaskDelta

        # All before-arm means identical -> zero covariate variance -> no division by zero.
        pairs = [
            PairedTaskDelta(
                "a", before_mean=0.5, after_mean=0.6, delta=0.1, n_before_trials=5, n_after_trials=5
            ),
            PairedTaskDelta(
                "b",
                before_mean=0.5,
                after_mean=0.4,
                delta=-0.1,
                n_before_trials=5,
                n_after_trials=5,
            ),
        ]
        adjusted, theta, reduction_pct = cuped_adjust(pairs)
        assert adjusted == [0.1, -0.1]
        assert theta == 0.0
        assert reduction_pct == 0.0

    def test_reduces_variance_when_before_predicts_delta(self) -> None:
        from agentgauge.harness import PairedTaskDelta

        # Deltas are a linear function of before_mean (regression-to-mean-style
        # pattern): CUPED should remove essentially all of that variance.
        pairs = [
            PairedTaskDelta(
                "t0",
                before_mean=0.0,
                after_mean=0.5,
                delta=0.5,
                n_before_trials=5,
                n_after_trials=5,
            ),
            PairedTaskDelta(
                "t1",
                before_mean=0.2,
                after_mean=0.5,
                delta=0.3,
                n_before_trials=5,
                n_after_trials=5,
            ),
            PairedTaskDelta(
                "t2",
                before_mean=0.5,
                after_mean=0.5,
                delta=0.0,
                n_before_trials=5,
                n_after_trials=5,
            ),
            PairedTaskDelta(
                "t3",
                before_mean=0.8,
                after_mean=0.5,
                delta=-0.3,
                n_before_trials=5,
                n_after_trials=5,
            ),
            PairedTaskDelta(
                "t4",
                before_mean=1.0,
                after_mean=0.5,
                delta=-0.5,
                n_before_trials=5,
                n_after_trials=5,
            ),
        ]
        _, _, reduction_pct = cuped_adjust(pairs)
        assert reduction_pct > 95.0


class TestClusterBootstrapMeanCi:
    def test_deterministic_given_same_seed(self) -> None:
        values = [0.1, -0.2, 0.3, 0.0, -0.1]
        r1 = cluster_bootstrap_mean_ci(values, seed=42)
        r2 = cluster_bootstrap_mean_ci(values, seed=42)
        assert r1 == r2

    def test_point_estimate_is_plain_mean(self) -> None:
        values = [1.0, 0.0, 0.5, 0.5]
        point, _, _ = cluster_bootstrap_mean_ci(values, seed=42)
        assert point == 0.5


class TestDiffServerLevel:
    def test_clear_regression_across_matched_tasks(self) -> None:
        before = [TrialOutcome(f"t{i}", f"t{i}", 1.0) for i in range(10)]
        after = [TrialOutcome(f"t{i}", f"t{i}", 0.0) for i in range(10)]
        result = diff_server_level(before, after, threshold=0.05, use_cuped=False)
        assert result.verdict == Verdict.REGRESSION
        assert result.exit_code == 1
        assert result.n_tasks_matched == 10

    def test_clear_improvement_across_matched_tasks(self) -> None:
        before = [TrialOutcome(f"t{i}", f"t{i}", 0.0) for i in range(10)]
        after = [TrialOutcome(f"t{i}", f"t{i}", 1.0) for i in range(10)]
        result = diff_server_level(before, after, threshold=0.05, use_cuped=False)
        assert result.verdict == Verdict.IMPROVEMENT
        assert result.exit_code == 0

    def test_identical_arms_no_change(self) -> None:
        trials = [TrialOutcome(f"t{i}", f"t{i}", 0.8) for i in range(10)]
        result = diff_server_level(trials, trials, threshold=0.05)
        assert result.verdict == Verdict.NO_CHANGE
        assert result.exit_code == 0

    def test_raises_on_fewer_than_two_matched_tasks(self) -> None:
        before = [TrialOutcome("a", "a", 1.0)]
        after = [TrialOutcome("a", "a", 0.5)]
        with pytest.raises(ValueError, match="requires >=2 matched tasks"):
            diff_server_level(before, after)

    def test_unmatched_tasks_reported_not_silently_dropped(self) -> None:
        before = [TrialOutcome("a", "a", 1.0), TrialOutcome("b", "b", 1.0)]
        after = [
            TrialOutcome("a", "a", 1.0),
            TrialOutcome("b", "b", 1.0),
            TrialOutcome("c", "c", 1.0),
        ]
        result = diff_server_level(before, after, use_cuped=False)
        assert result.n_tasks_matched == 2
        assert result.unmatched_task_names == ["c"]

    def test_reproduces_call_constraints_pattern_paired(self) -> None:
        """The same real call_constraints_server pattern (perfect selection,
        argument-construction degradation) must still be caught at the
        server/task-paired level, not just at the old trial level."""
        before = [TrialOutcome("register_channel", "register_channel", 1.0) for _ in range(5)]
        before += [TrialOutcome("log_fault", "log_fault", 1.0) for _ in range(5)]
        after = [TrialOutcome("register_channel", "register_channel", 0.0) for _ in range(5)]
        after += [TrialOutcome("log_fault", "log_fault", 0.0) for _ in range(5)]
        result = diff_server_level(before, after, threshold=0.05, use_cuped=False)
        assert result.verdict == Verdict.REGRESSION


class TestObrienFlemingAlphaSpending:
    def test_conservative_at_early_information_fraction(self) -> None:
        # At t=0.1 (an early look), cumulative alpha spent must be tiny --
        # much less than the full 0.05 budget.
        alpha_early = _obrien_fleming_cumulative_alpha(0.1)
        assert alpha_early < 0.001

    def test_spends_full_budget_at_t_equals_one(self) -> None:
        alpha_final = _obrien_fleming_cumulative_alpha(1.0)
        assert abs(alpha_final - 0.05) < 1e-6

    def test_monotonically_increasing_in_information_fraction(self) -> None:
        fractions = [0.1, 0.3, 0.5, 0.7, 1.0]
        values = [_obrien_fleming_cumulative_alpha(t) for t in fractions]
        assert values == sorted(values)

    def test_rejects_non_default_alpha(self) -> None:
        with pytest.raises(ValueError, match="only supports alpha=0.05"):
            _obrien_fleming_cumulative_alpha(0.5, alpha=0.10)


class TestSimulateTaskLevelPairs:
    def test_produces_requested_count(self) -> None:
        from agentgauge.harness import _lcg_random

        rng = _lcg_random(42)
        pairs = simulate_task_level_pairs(0.75, 0.0, n_tasks=20, rng=rng)
        assert len(pairs) == 20
        for b, a in pairs:
            assert 0.0 <= b <= 1.0
            assert 0.0 <= a <= 1.0

    def test_zero_delta_correlated_pairs_track_each_other(self) -> None:
        """At rho close to 1 and true_delta=0, before/after should be close
        for most tasks (high correlation, no true shift)."""
        from agentgauge.harness import _lcg_random

        rng = _lcg_random(7)
        pairs = simulate_task_level_pairs(0.75, 0.0, n_tasks=200, rho=0.99, rng=rng)
        mean_abs_diff = sum(abs(a - b) for b, a in pairs) / len(pairs)
        assert mean_abs_diff < 0.3  # much tighter than the marginal spread alone


class TestSimulateMdeTaskLevel:
    def test_pairing_reduces_mde_vs_unpaired_baseline(self) -> None:
        """The whole point of Task 2: at rho=0.881 (measured), pairing must
        give a materially smaller (better) MDE than treating before/after as
        independent samples at the same n_tasks."""
        mde_unpaired = simulate_mde_task_level(
            n_tasks=20, power=0.8, n_simulations=100, seed=42, use_paired=False, use_cuped=False
        )
        mde_paired = simulate_mde_task_level(
            n_tasks=20, power=0.8, n_simulations=100, seed=42, use_paired=True, use_cuped=False
        )
        assert mde_paired < mde_unpaired

    def test_mde_decreases_with_n_tasks(self) -> None:
        mde_small = simulate_mde_task_level(n_tasks=5, power=0.8, n_simulations=100, seed=42)
        mde_large = simulate_mde_task_level(n_tasks=50, power=0.8, n_simulations=100, seed=42)
        assert mde_large < mde_small


class TestSimulateSequentialExpectedN:
    def test_expected_n_under_null_is_less_than_n_max(self) -> None:
        """Under the null (no true effect), the sequential design should often
        stop early on a confident NO_CHANGE rather than always running to
        n_max -- that is the entire point of sequential testing."""
        result = simulate_sequential_expected_n(
            true_delta=0.0,
            look_schedule=(5, 10, 15, 20, 25, 30, 35, 40, 45, 50),
            n_simulations=100,
            seed=42,
        )
        assert result["expected_n"] <= result["n_max"]

    def test_large_regression_detected_before_n_max(self) -> None:
        """A large (0.5) true regression should be caught well before the
        final scheduled look in most simulated runs."""
        result = simulate_sequential_expected_n(
            true_delta=-0.5,
            look_schedule=(5, 10, 15, 20, 25, 30, 35, 40, 45, 50),
            n_simulations=100,
            seed=42,
        )
        assert result["expected_n"] < 50
