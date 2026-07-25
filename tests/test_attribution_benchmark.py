"""Tests for `agentgauge.attribution_benchmark` (v0.5, Wave 1, Component 1.2).

No live LLM calls: every case's "measurement" comes from a deterministic synthetic ground-truth
model run through the real `agentgauge.harness.diff_server_level` estimator on synthetic trial
data -- see `agentgauge/attribution_benchmark.py`'s module docstring. Benchmark sizes here are
smaller than the report script's n_cases=50 (kept fast for the unit test suite), but still large
enough to make the confound-guard's statistical assertions meaningful.
"""

from __future__ import annotations

from agentgauge.attribution import (
    attribute_exhaustive,
    baseline_largest_textual_diff,
    top_k_hit,
)
from agentgauge.attribution_benchmark import (
    CAUSAL_EFFECT_MAX_PP,
    CAUSAL_EFFECT_MIN_PP,
    confound_guard_report,
    generate_benchmark,
    make_probe_fn,
)

N_TEST_CASES = 24
SEED = 42


class TestGenerateBenchmark:
    def test_generates_requested_case_count(self) -> None:
        cases = generate_benchmark(n_cases=N_TEST_CASES, seed=SEED)
        assert len(cases) == N_TEST_CASES

    def test_deterministic_given_seed(self) -> None:
        cases_a = generate_benchmark(n_cases=10, seed=SEED)
        cases_b = generate_benchmark(n_cases=10, seed=SEED)
        assert [c.true_culprit for c in cases_a] == [c.true_culprit for c in cases_b]
        assert [c.changed_tools for c in cases_a] == [c.changed_tools for c in cases_b]

    def test_true_effect_within_measured_causal_range(self) -> None:
        cases = generate_benchmark(n_cases=N_TEST_CASES, seed=SEED)
        for case in cases:
            assert CAUSAL_EFFECT_MIN_PP <= case.true_effect_pp <= CAUSAL_EFFECT_MAX_PP

    def test_true_culprit_is_among_changed_tools(self) -> None:
        cases = generate_benchmark(n_cases=N_TEST_CASES, seed=SEED)
        for case in cases:
            assert case.true_culprit in case.changed_tools

    def test_decoys_have_zero_recorded_causal_effect(self) -> None:
        """The ground-truth model attaches nonzero effect ONLY to the true culprit -- decoys are
        pure textual noise. Confirmed by construction: only one tool per case is mutated with
        `_inject_type_enum_contradiction`; decoys use `_inject_benign_decoy`."""
        cases = generate_benchmark(n_cases=N_TEST_CASES, seed=SEED)
        for case in cases:
            decoys = [t for t in case.changed_tools if t != case.true_culprit]
            for decoy in decoys:
                # A decoy's before/after description differs (it WAS mutated) but the tool's
                # schema (aside from the culprit's) is untouched -- decoys never flip a type.
                before_tool = next(t for t in case.all_tools_before if t["name"] == decoy)
                after_tool = next(t for t in case.all_tools_after if t["name"] == decoy)
                assert before_tool["inputSchema"] == after_tool["inputSchema"]


class TestConfoundGuard:
    """Mandatory benchmark-construction guard, per `reports/v0_5_eval_doctrine.md` Component 1.2:
    the true culprit must not be systematically at a fixed position, and decoy diffs must not be
    systematically smaller than the culprit's own diff -- else baseline (i) or a positional
    shortcut would win by construction rather than by real localization signal. One shared
    40-case sample is generated once (module-scoped-ish via a plain module constant) and reused
    across the three assertions below, rather than regenerated per test -- purely a test-speed
    choice; the underlying `generate_benchmark`/`confound_guard_report` calls are identical."""

    _CASES = generate_benchmark(n_cases=40, seed=SEED)
    _GUARD = confound_guard_report(_CASES)

    def test_culprit_position_is_not_fixed(self) -> None:
        assert self._GUARD.n_positions_observed > 1, (
            "true culprit occupied only one position across 40 cases -- position is not "
            "randomized, which would let a positional shortcut win by construction"
        )

    def test_culprit_is_not_always_the_max_diff_tool(self) -> None:
        assert self._GUARD.frac_cases_culprit_is_max_diff < 1.0, (
            "true culprit was the largest-diff tool in EVERY case -- baseline (i) would win by "
            "construction, not by real signal"
        )

    def test_at_least_some_decoys_exceed_culprit_diff(self) -> None:
        assert self._GUARD.frac_cases_a_decoy_exceeds_culprit_diff > 0.0, (
            "no case had a decoy diff larger than the culprit's -- decoy diffs are "
            "systematically smaller than the true culprit's, violating the mandatory guard"
        )


class TestMakeProbeFn:
    def test_reverting_true_culprit_shows_significant_recovery(self) -> None:
        cases = generate_benchmark(n_cases=8, seed=SEED)
        for case in cases:
            probe = make_probe_fn(case, seed=SEED)
            result = probe(frozenset({case.true_culprit}))
            assert result.ci_lo > 0.05, (
                f"reverting the true culprit ({case.true_culprit}) should show a CI-significant "
                f"recovery effect at the default 0.05 threshold"
            )

    def test_reverting_only_a_decoy_shows_no_significant_effect(self) -> None:
        cases = generate_benchmark(n_cases=8, seed=SEED)
        for case in cases:
            decoys = [t for t in case.changed_tools if t != case.true_culprit]
            if not decoys:
                continue
            probe = make_probe_fn(case, seed=SEED)
            result = probe(frozenset({decoys[0]}))
            assert result.ci_lo <= 0.05, (
                f"reverting only a decoy ({decoys[0]}) should NOT show a significant recovery "
                f"effect -- decoys have zero causal effect by construction"
            )

    def test_reverting_nothing_shows_no_significant_effect(self) -> None:
        """Reverting the empty set means both arms are drawn from the SAME underlying rate (the
        current regressed state, unchanged) -- independent per-task noise means the point delta
        is not exactly 0.0, but it must never be CI-significant (per the same threshold used to
        call a real effect real elsewhere in this module)."""
        cases = generate_benchmark(n_cases=8, seed=SEED)
        for case in cases:
            probe = make_probe_fn(case, seed=SEED)
            result = probe(frozenset())
            assert result.ci_lo <= 0.05
            assert result.ci_hi >= -0.05


class TestExhaustiveAblationOnBenchmark:
    """End-to-end sanity check: the probe-based exhaustive strategy correctly recovers the known
    true culprit on a real (small) slice of the benchmark, wired through the real harness
    estimator via `make_probe_fn` -- not a hand-computed shortcut."""

    def test_exhaustive_ablation_recovers_true_culprit_top1(self) -> None:
        cases = generate_benchmark(n_cases=10, seed=SEED)
        hits = 0
        for case in cases:
            probe = make_probe_fn(case, seed=SEED)
            result = attribute_exhaustive(case.changed_tools, probe)
            assert result.probes_consumed == len(case.changed_tools)
            if top_k_hit(result, case.true_culprit, 1):
                hits += 1
        # Not asserting 100% (this is a real measurement, not a tautology) -- but the clean
        # synthetic ground-truth signal (decoys=0, culprit=13-29pp) should make this very high.
        assert hits / len(cases) >= 0.8


class TestBaselineLargestTextualDiffOnBenchmark:
    def test_runs_zero_probes_end_to_end(self) -> None:
        cases = generate_benchmark(n_cases=6, seed=SEED)
        for case in cases:
            before_desc = {t: case.before_description(t) for t in case.changed_tools}
            after_desc = {t: case.after_description(t) for t in case.changed_tools}
            result = baseline_largest_textual_diff(case.changed_tools, before_desc, after_desc)
            assert result.probes_consumed == 0
            assert {c.tool_name for c in result.ranked} == set(case.changed_tools)
