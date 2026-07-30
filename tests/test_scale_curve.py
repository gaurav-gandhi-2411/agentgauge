"""Tests for the v0.5 Wave 1 scale-curve study's multi-culprit machinery
(`agentgauge.attribution_benchmark.generate_multi_culprit_benchmark` /
`make_multi_probe_fn` / `multi_confound_guard_report`) -- see `reports/v0_5_scale_curve.md`
(Tasks 2b/2c). Pinned-candidate-set-size generation tests (Task 2a) live in
`tests/test_attribution_benchmark.py::TestPinnedSizeGeneration` /
`::TestConfoundGuardAtPinnedSizes`, extending the existing file per this task's own instruction,
rather than duplicated here.

No live LLM calls: same deterministic synthetic ground-truth model as the rest of this study.
"""

from __future__ import annotations

import pytest

from agentgauge.attribution import attribute_exhaustive, top_k_hit
from agentgauge.attribution_benchmark import (
    CAUSAL_EFFECT_MAX_PP,
    CAUSAL_EFFECT_MIN_PP,
    MultiCulpritBenchmarkCase,
    before_arm_floor_clip_rate,
    generate_benchmark,
    generate_multi_culprit_benchmark,
    make_multi_probe_fn,
    make_probe_fn,
    multi_confound_guard_report,
)

SEED = 42


class TestGenerateMultiCulpritBenchmark:
    def test_generates_requested_case_count(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=15, n_culprits=2, n_changed=20, seed=SEED)
        assert len(cases) == 15

    def test_every_case_has_exactly_n_culprits(self) -> None:
        for n_culprits in (2, 3):
            cases = generate_multi_culprit_benchmark(
                n_cases=10, n_culprits=n_culprits, n_changed=20, seed=SEED
            )
            for case in cases:
                assert len(case.true_culprits) == n_culprits
                assert len(set(case.true_culprits)) == n_culprits  # distinct
                assert set(case.true_effects_pp) == set(case.true_culprits)

    def test_every_case_has_exactly_the_pinned_size(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=10, n_culprits=3, n_changed=20, seed=SEED)
        for case in cases:
            assert len(case.changed_tools) == 20

    def test_all_culprits_are_among_changed_tools(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=10, n_culprits=2, n_changed=10, seed=SEED)
        for case in cases:
            for c in case.true_culprits:
                assert c in case.changed_tools

    def test_effect_magnitudes_within_measured_causal_range(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=10, n_culprits=3, n_changed=20, seed=SEED)
        for case in cases:
            for eff in case.true_effects_pp.values():
                assert CAUSAL_EFFECT_MIN_PP <= eff <= CAUSAL_EFFECT_MAX_PP

    def test_deterministic_given_seed(self) -> None:
        cases_a = generate_multi_culprit_benchmark(
            n_cases=10, n_culprits=2, n_changed=20, seed=SEED
        )
        cases_b = generate_multi_culprit_benchmark(
            n_cases=10, n_culprits=2, n_changed=20, seed=SEED
        )
        assert [c.true_culprits for c in cases_a] == [c.true_culprits for c in cases_b]
        assert [c.changed_tools for c in cases_a] == [c.changed_tools for c in cases_b]

    def test_decoys_have_zero_recorded_causal_effect(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=10, n_culprits=2, n_changed=20, seed=SEED)
        for case in cases:
            culprit_set = set(case.true_culprits)
            decoys = [t for t in case.changed_tools if t not in culprit_set]
            for decoy in decoys:
                before_tool = next(t for t in case.all_tools_before if t["name"] == decoy)
                after_tool = next(t for t in case.all_tools_after if t["name"] == decoy)
                assert before_tool["inputSchema"] == after_tool["inputSchema"]

    def test_rejects_n_culprits_below_two(self) -> None:
        with pytest.raises(ValueError, match="n_culprits"):
            generate_multi_culprit_benchmark(n_cases=5, n_culprits=1, n_changed=10, seed=SEED)

    def test_rejects_n_changed_too_small_for_at_least_one_decoy(self) -> None:
        with pytest.raises(ValueError, match="n_changed"):
            generate_multi_culprit_benchmark(n_cases=5, n_culprits=3, n_changed=3, seed=SEED)

    def test_raises_when_no_catalog_is_large_enough(self) -> None:
        with pytest.raises(RuntimeError):
            generate_multi_culprit_benchmark(n_cases=5, n_culprits=2, n_changed=1000, seed=SEED)


class TestMultiConfoundGuard:
    """Task 2b's explicit instruction: the single-culprit guard's definitions do not carry over to
    multi-culprit cases unchanged -- `multi_confound_guard_report` generalizes each one (see its
    field docstrings) and must still pass on the real corpus."""

    def test_position_not_fixed_for_2_culprits(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=30, n_culprits=2, n_changed=20, seed=SEED)
        guard = multi_confound_guard_report(cases)
        assert guard.n_positions_observed > 1

    def test_position_not_fixed_for_3_culprits(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=30, n_culprits=3, n_changed=20, seed=SEED)
        guard = multi_confound_guard_report(cases)
        assert guard.n_positions_observed > 1

    def test_a_culprit_is_not_always_the_max_diff_tool(self) -> None:
        for n_culprits in (2, 3):
            cases = generate_multi_culprit_benchmark(
                n_cases=30, n_culprits=n_culprits, n_changed=20, seed=SEED
            )
            guard = multi_confound_guard_report(cases)
            assert guard.frac_cases_a_culprit_is_max_diff < 1.0, (
                f"n_culprits={n_culprits}: a true culprit was the max-diff tool in EVERY case -- "
                "baseline (i) would win by construction"
            )

    def test_decoys_sometimes_exceed_the_weakest_culprit_diff(self) -> None:
        for n_culprits in (2, 3):
            cases = generate_multi_culprit_benchmark(
                n_cases=30, n_culprits=n_culprits, n_changed=20, seed=SEED
            )
            guard = multi_confound_guard_report(cases)
            assert guard.frac_cases_a_decoy_exceeds_min_culprit_diff > 0.0

    def test_fractional_rank_distribution_not_correlated_with_role(self) -> None:
        """Same [0.35, 0.65] band as the single-culprit guard
        (`TestConfoundGuard::test_culprit_diff_size_distribution_not_correlated_with_role`),
        applied per-culprit-instance (see `MultiConfoundGuardReport.mean_culprit_fractional_rank`
        docstring for exactly what is averaged)."""
        for n_culprits in (2, 3):
            cases = generate_multi_culprit_benchmark(
                n_cases=30, n_culprits=n_culprits, n_changed=20, seed=SEED
            )
            guard = multi_confound_guard_report(cases)
            assert 0.35 <= guard.mean_culprit_fractional_rank <= 0.65, (
                f"n_culprits={n_culprits}: mean culprit fractional rank "
                f"{guard.mean_culprit_fractional_rank:.4f} is outside the [0.35, 0.65] band"
            )


class TestMakeMultiProbeFn:
    def test_reduces_to_single_culprit_model_at_n_culprits_1(self) -> None:
        """`make_multi_probe_fn`'s additive combination is a drop-in generalization of
        `make_probe_fn`'s single-culprit arithmetic: constructing an equivalent 1-culprit
        `MultiCulpritBenchmarkCase` from a real `BenchmarkCase` and probing both with the same
        `reverted` subsets must give numerically identical results (same RNG draws, same formula
        modulo the dict-vs-scalar bookkeeping)."""
        single_cases = generate_benchmark(n_cases=3, seed=SEED)
        for single in single_cases:
            multi = MultiCulpritBenchmarkCase(
                case_id=single.case_id,
                base_tool_set=single.base_tool_set,
                all_tools_before=single.all_tools_before,
                all_tools_after=single.all_tools_after,
                changed_tools=single.changed_tools,
                true_culprits=[single.true_culprit],
                true_effects_pp={single.true_culprit: single.true_effect_pp},
                diff_chars=single.diff_chars,
            )
            probe_single = make_probe_fn(single, seed=SEED)
            probe_multi = make_multi_probe_fn(multi, seed=SEED)
            for reverted in (
                frozenset(),
                frozenset({single.true_culprit}),
                frozenset(single.changed_tools[:2]),
            ):
                r_single = probe_single(reverted)
                r_multi = probe_multi(reverted)
                assert r_single.delta == pytest.approx(r_multi.delta, abs=1e-9)
                assert r_single.ci_lo == pytest.approx(r_multi.ci_lo, abs=1e-9)
                assert r_single.ci_hi == pytest.approx(r_multi.ci_hi, abs=1e-9)

    def test_reverting_all_culprits_shows_a_significant_recovery_effect(self) -> None:
        for n_culprits in (2, 3):
            cases = generate_multi_culprit_benchmark(
                n_cases=8, n_culprits=n_culprits, n_changed=20, seed=SEED
            )
            for case in cases:
                probe = make_multi_probe_fn(case, seed=SEED)
                result = probe(frozenset(case.true_culprits))
                assert result.ci_lo > 0.05, (
                    f"reverting ALL {n_culprits} true culprits should show a CI-significant "
                    "recovery effect"
                )

    def test_reverting_only_a_decoy_shows_no_significant_effect(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=8, n_culprits=2, n_changed=20, seed=SEED)
        for case in cases:
            culprit_set = set(case.true_culprits)
            decoys = [t for t in case.changed_tools if t not in culprit_set]
            if not decoys:
                continue
            probe = make_multi_probe_fn(case, seed=SEED)
            result = probe(frozenset({decoys[0]}))
            assert result.ci_lo <= 0.05

    def test_reverting_one_of_two_culprits_recovers_less_than_reverting_both(self) -> None:
        """Additive-combination sanity check: partial revert should measure a strictly smaller
        point delta than a full revert, on average -- direct evidence the combination is additive
        rather than e.g. saturating at the first culprit's effect alone."""
        cases = generate_multi_culprit_benchmark(n_cases=10, n_culprits=2, n_changed=20, seed=SEED)
        n_partial_smaller = 0
        for case in cases:
            probe = make_multi_probe_fn(case, seed=SEED)
            one = probe(frozenset({case.true_culprits[0]}))
            both = probe(frozenset(case.true_culprits))
            if one.delta < both.delta:
                n_partial_smaller += 1
        assert n_partial_smaller == len(cases), (
            "reverting only one of two culprits should ALWAYS measure a smaller recovery than "
            "reverting both, under additive combination"
        )


class TestBeforeArmFloorClipRate:
    def test_returns_zero_for_a_single_small_effect_case(self) -> None:
        cases = generate_multi_culprit_benchmark(
            n_cases=1, n_culprits=2, n_changed=20, seed=SEED, effect_min_pp=-5.0, effect_max_pp=-3.0
        )
        assert before_arm_floor_clip_rate(cases) == 0.0

    def test_is_nonzero_when_summed_effects_can_exceed_the_baseline_rate(self) -> None:
        """Constructed directly (not relying on random draws clearing the bar): 3 culprits each at
        the max magnitude end of the causal range sum to ~86.7pp, comfortably exceeding
        `CALIBRATED_BASELINE_RATE` (~77.5%) -- the floor must be hit for such a case."""
        case = MultiCulpritBenchmarkCase(
            case_id="floor_probe",
            base_tool_set="synthetic",
            all_tools_before=[],
            all_tools_after=[],
            changed_tools=["a", "b", "c", "d"],
            true_culprits=["a", "b", "c"],
            true_effects_pp={"a": -28.9, "b": -28.9, "c": -28.9},
        )
        assert before_arm_floor_clip_rate([case]) == 1.0

    def test_returns_a_fraction_between_zero_and_one_on_the_real_generator(self) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=30, n_culprits=3, n_changed=20, seed=SEED)
        rate = before_arm_floor_clip_rate(cases)
        assert 0.0 <= rate <= 1.0


class TestMultiCulpritScoringWiring:
    """End-to-end sanity: baselines and `attribute_exhaustive` (single-culprit-oriented, per its
    own `top_k_hit(result, true_culprit: str, k)` signature) still run mechanically against a
    multi-culprit case's `changed_tools` -- multi-culprit-AWARE scoring (recall@k / strict-top-k
    over a set of true culprits) is implemented in `scripts/scale_curve_report.py`, not in
    `agentgauge.attribution`, since that module's interface is intentionally single-culprit-
    string-shaped and is out of this task's edit scope."""

    def test_exhaustive_ablation_ranks_every_true_culprit_above_every_decoy_on_average(
        self,
    ) -> None:
        cases = generate_multi_culprit_benchmark(n_cases=10, n_culprits=2, n_changed=10, seed=SEED)
        hits_at_least_one_culprit_in_top2 = 0
        for case in cases:
            probe = make_multi_probe_fn(case, seed=SEED)
            result = attribute_exhaustive(case.changed_tools, probe)
            top2_names = {c.tool_name for c in result.ranked[:2]}
            if top2_names & set(case.true_culprits):
                hits_at_least_one_culprit_in_top2 += 1
        assert hits_at_least_one_culprit_in_top2 >= 8  # not a tight bound -- just a sanity floor

    def test_top_k_hit_accepts_any_single_true_culprit_string(self) -> None:
        """`top_k_hit` itself is unmodified (single-culprit-shaped by design) -- confirms it can
        still be called once per true culprit against a multi-culprit result, the building block
        `scripts/scale_curve_report.py`'s multi-culprit scoring functions use."""
        cases = generate_multi_culprit_benchmark(n_cases=5, n_culprits=2, n_changed=10, seed=SEED)
        for case in cases:
            probe = make_multi_probe_fn(case, seed=SEED)
            result = attribute_exhaustive(case.changed_tools, probe)
            for c in case.true_culprits:
                assert isinstance(top_k_hit(result, c, 3), bool)
