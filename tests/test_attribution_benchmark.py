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
    baseline_most_lint_violations,
    top_k_hit,
)
from agentgauge.attribution_benchmark import (
    CAUSAL_EFFECT_MAX_PP,
    CAUSAL_EFFECT_MIN_PP,
    confound_guard_report,
    generate_benchmark,
    make_probe_fn,
)
from agentgauge.linter import LintReport, lint_tool_set

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

    def test_culprit_diff_size_distribution_not_correlated_with_role(self) -> None:
        """Measurement artifact #9 (found this pass, see module docstring in
        `agentgauge.attribution_benchmark`): the two edge-condition checks above both pass even
        when there is a real, systematic DISTRIBUTIONAL correlation between diff size and
        culprit-vs-decoy role -- the original generator's culprit diff sat at mean fractional
        rank ~=0.66-0.73 (measured on n=50 and n=300 samples, both well outside this band) purely
        because its fixed-size defect sentence was smaller than 2 of the 3 decoy tiers by
        construction. Under a role-independent generating process the expected mean fractional
        rank is exactly 0.5; +/-0.15 is a band wide enough to absorb ordinary sampling noise at
        this sample size (post-fix measured values: ~0.55-0.61) while still decisively rejecting
        the pre-fix ~0.66-0.73 regime -- not fitted to make this specific run's number pass."""
        assert 0.35 <= self._GUARD.mean_culprit_fractional_rank <= 0.65, (
            f"mean culprit fractional rank {self._GUARD.mean_culprit_fractional_rank:.4f} is "
            "outside the [0.35, 0.65] band around the 0.5 null -- diff size still correlates "
            "with culprit-vs-decoy role (the artifact #9 class)"
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


class TestBaselineMostLintViolationsRawCountOffsetOnBenchmark:
    """Task 3c recheck (v0.5 Wave 1, `reports/v0_5_attribution_benchmark.md`): does
    `baseline_most_lint_violations`'s raw-COUNT ranking get inflated or deflated by benchmark
    construction? Measured on the real corpus (n=50, seed=42, the corrected post-artifact-#9
    generator): the true culprit's mandatory defect sentence (`_inject_type_enum_contradiction`)
    always mentions the flipped parameter's name -- when that parameter was previously a required,
    undocumented property, adding the sentence simultaneously (a) triggers the BLOCKING
    `type_enum_contradiction` violation (+1) and (b) satisfies the INFO `required_not_mentioned`
    check that had been firing before the mutation (-1), netting a RAW COUNT delta of exactly 0 in
    a large fraction of cases -- even though the culprit ALWAYS gains a genuine BLOCKING violation
    that no decoy (a pure prose append, no schema change) can ever gain. This is a real,
    root-caused property of raw-count ranking's severity-blindness, not a benchmark artifact that
    should be patched away by redefining the baseline (per the task's explicit instruction not to
    fit the metric to the result) -- these tests lock in the mechanism so it stays honestly
    documented, not silently swapped away."""

    def test_decoys_never_trigger_the_blocking_check(self) -> None:
        """Decoys are pure prose appends with zero schema change -- they must never accidentally
        gain the BLOCKING `type_enum_contradiction` violation the true culprit always gains. If
        this ever became false, `most_lint_violations` could be beaten by construction via a
        genuine competing blocking signal, not merely a raw-count tie."""
        cases = generate_benchmark(n_cases=N_TEST_CASES, seed=SEED)
        for case in cases:
            report = lint_tool_set(case.tools_after_like())
            blocking_tools = {v.tool_name for v in report.blocking}
            decoys = {t for t in case.changed_tools if t != case.true_culprit}
            assert not (blocking_tools & decoys), (
                f"a decoy in {case.case_id} triggered a BLOCKING lint violation -- decoys must "
                "carry zero causal AND zero blocking-severity signal by construction"
            )

    def test_culprit_raw_count_delta_is_frequently_zero_despite_a_real_blocking_gain(self) -> None:
        """The offset mechanism this class documents: the culprit's raw lint-violation-count
        DELTA (after minus before) is 0 in a substantial share of cases, because an incidental
        INFO-severity fix (the parameter becomes newly mentioned) cancels the new BLOCKING
        violation on a pure count basis -- while the culprit's blocking-violation COUNT alone
        (not the before/after delta) is always AT LEAST 1 (asserted below), proving the signal is
        real and simply invisible to a severity-blind raw count. Asserting ">=1", not "==1": one
        real corpus tool (execute_cell, found while writing this test) has NO terminal punctuation
        in its original description, so `_check_type_enum_contradiction`'s sentence-splitter
        merges the whole original description with the appended defect sentence into one
        "sentence" -- if that tool has ANOTHER string-typed property whose name also appears in
        the merged text, it can ALSO fire, giving 2 blocking violations instead of 1. This is a
        genuine, pre-existing linter behavior (unrelated to the diff-size fix in this file), not
        something this task's scope covers fixing -- noted here rather than silently
        over-constraining the assertion to hide it."""
        cases = generate_benchmark(n_cases=N_TEST_CASES, seed=SEED)
        n_zero_delta = 0
        for case in cases:
            after_report = lint_tool_set(case.tools_after_like())
            before_report = lint_tool_set(case.tools_before_like())
            culprit_blocking_after = [
                v for v in after_report.blocking if v.tool_name == case.true_culprit
            ]
            assert len(culprit_blocking_after) >= 1, (
                "the true culprit must always carry at least one BLOCKING "
                "type_enum_contradiction violation after mutation"
            )
            assert all(v.check == "type_enum_contradiction" for v in culprit_blocking_after)

            def _count(report: LintReport, tool: str) -> int:
                return sum(
                    1
                    for v in report.blocking + report.advisory + report.info
                    if v.tool_name == tool
                )

            delta = _count(after_report, case.true_culprit) - _count(
                before_report, case.true_culprit
            )
            if delta == 0:
                n_zero_delta += 1
        # A nonzero rate is the whole point of this test: it demonstrates the offset mechanism is
        # real on the real corpus, not a hypothetical. Not asserting an exact count (n=24 is a
        # smaller sample than the report's n=50) -- only that the mechanism fires at all.
        assert n_zero_delta > 0, (
            "expected at least one case where the culprit's raw lint-count delta nets to 0 "
            "despite a real blocking-severity gain -- if this no longer reproduces, the "
            "documented offset mechanism (required_not_mentioned canceling type_enum_contradiction "
            "on a raw-count basis) may no longer apply and this test's docstring needs revisiting"
        )

    def test_severity_aware_ranking_would_be_strictly_better_than_raw_count(self) -> None:
        """A trivial severity-aware ranking (does the tool carry >=1 BLOCKING violation at all,
        ignoring count) always identifies the true culprit uniquely, since the culprit always
        gains exactly one BLOCKING violation and decoys never gain any (locked by the test above)
        -- while the raw-count baseline (`baseline_most_lint_violations`) measurably misses on a
        real fraction of these same cases due to the tie/offset mechanism. This is the concrete,
        measured evidence for the finding: blocking-severity-blind raw counting is a genuinely
        weaker signal than a severity-aware ranking would be -- not a claim to "fix" the shipped
        baseline against (per the task's explicit instruction), just an honestly reported gap."""
        cases = generate_benchmark(n_cases=N_TEST_CASES, seed=SEED)
        severity_aware_hits = 0
        raw_count_hits = 0
        for case in cases:
            after_report = lint_tool_set(case.tools_after_like())
            blocking_tools = {v.tool_name for v in after_report.blocking}
            if blocking_tools == {case.true_culprit}:
                severity_aware_hits += 1

            result = baseline_most_lint_violations(
                case.changed_tools, case.tools_before_like(), case.tools_after_like()
            )
            if top_k_hit(result, case.true_culprit, 1):
                raw_count_hits += 1

        assert severity_aware_hits == len(cases), (
            "a trivial severity-aware check (unique BLOCKING-carrying tool) should identify the "
            "true culprit in every case -- if not, the ground-truth defect-injection guarantee "
            "itself has broken, which is a bigger problem than this test's own scope"
        )
        assert raw_count_hits < severity_aware_hits, (
            "expected the raw-count baseline to strictly underperform a trivial severity-aware "
            "ranking on this corpus -- if it no longer does, the finding in "
            "reports/v0_5_attribution_benchmark.md needs re-checking, not silently dropped"
        )
