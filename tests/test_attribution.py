"""Tests for `agentgauge.attribution` (v0.5, Wave 1, Component 1.2).

Per this repo's standing rule, the LLM is always mocked in tests -- every probe callback below is
a pure, deterministic Python function with no network/inference dependency whatsoever.
"""

from __future__ import annotations

from agentgauge.attribution import (
    AttributionCandidate,
    AttributionResult,
    ProbeFn,
    ProbeResult,
    _bisect_within,
    _sampled_shapley_budget,
    attribute_exhaustive,
    attribute_greedy_bisection,
    attribute_sampled_shapley,
    baseline_largest_textual_diff,
    baseline_most_lint_violations,
    baseline_uniform_random,
    expected_topk_accuracy,
    top_k_hit,
)


def _fixed_effect_probe(effects: dict[str, float], noise: float = 0.0) -> ProbeFn:
    """A synthetic probe: reverting a subset S recovers sum(effects[t] for t in S), i.e. each
    tool's individual effect contributes additively and independently -- the simplest possible
    ground truth, sufficient to test ranking/budget behavior without needing the real harness."""

    def probe(reverted: frozenset[str]) -> ProbeResult:
        delta = sum(effects.get(t, 0.0) for t in reverted)
        return ProbeResult(delta=delta, ci_lo=delta - noise, ci_hi=delta + noise)

    return probe


def _cand(name: str, effect: float) -> AttributionCandidate:
    return AttributionCandidate(tool_name=name, attributed_effect_pp=effect)


class TestTopKHit:
    def test_hit_when_in_top_k(self) -> None:
        result = AttributionResult(
            "s",
            ranked=[
                _cand("a", 10.0),
                _cand("b", 5.0),
                _cand("c", 1.0),
            ],
        )
        assert top_k_hit(result, "a", 1)
        assert top_k_hit(result, "b", 2)
        assert not top_k_hit(result, "c", 2)
        assert top_k_hit(result, "c", 3)


class TestAttributeExhaustive:
    def test_ranks_true_culprit_first(self) -> None:
        changed = ["a", "b", "c"]
        probe = _fixed_effect_probe({"b": 0.20})
        result = attribute_exhaustive(changed, probe)
        assert result.ranked[0].tool_name == "b"
        assert result.probes_consumed == 3

    def test_probe_budget_equals_n_changed(self) -> None:
        changed = [f"t{i}" for i in range(7)]
        probe = _fixed_effect_probe({"t3": 0.15})
        result = attribute_exhaustive(changed, probe)
        assert result.probes_consumed == 7

    def test_empty_changed_set(self) -> None:
        result = attribute_exhaustive([], _fixed_effect_probe({}))
        assert result.ranked == []
        assert result.probes_consumed == 0


class TestSampledShapleyBudget:
    def test_strictly_sub_exhaustive_for_n_ge_2(self) -> None:
        for n in range(2, 20):
            assert _sampled_shapley_budget(n) < n

    def test_degenerate_n_le_1(self) -> None:
        assert _sampled_shapley_budget(0) == 0
        assert _sampled_shapley_budget(1) == 1


class TestAttributeSampledShapley:
    def test_ranks_true_culprit_first_with_sub_exhaustive_budget(self) -> None:
        changed = [f"t{i}" for i in range(6)]
        probe = _fixed_effect_probe({"t4": 0.25})
        result = attribute_sampled_shapley(changed, probe, seed=42)
        assert result.ranked[0].tool_name == "t4"
        assert result.probes_consumed < len(changed)

    def test_deterministic_given_same_seed(self) -> None:
        changed = [f"t{i}" for i in range(5)]
        probe = _fixed_effect_probe({"t2": 0.2})
        r1 = attribute_sampled_shapley(changed, probe, seed=42)
        r2 = attribute_sampled_shapley(changed, probe, seed=42)
        assert [c.tool_name for c in r1.ranked] == [c.tool_name for c in r2.ranked]
        assert r1.probes_consumed == r2.probes_consumed

    def test_empty_changed_set(self) -> None:
        result = attribute_sampled_shapley([], _fixed_effect_probe({}))
        assert result.ranked == []
        assert result.probes_consumed == 0


class TestAttributeGreedyBisection:
    def test_ranks_true_culprit_first_with_sub_exhaustive_budget(self) -> None:
        # n=16, not n=8: the outer loop always spends a second (failing) `_bisect_within` search
        # over the remainder to check for additional culprits (see docstring), and with the
        # probes_consumed accounting fix below, that second search's real cost is now honestly
        # counted too. At small n (e.g. n=8) "find one + fail to find a second" can cost as much
        # as exhaustive ablation itself -- n=16 is large enough to stay genuinely sub-exhaustive.
        changed = [f"t{i}" for i in range(16)]
        probe = _fixed_effect_probe({"t5": 0.20})
        result = attribute_greedy_bisection(changed, probe, threshold=0.05)
        assert result.ranked[0].tool_name == "t5"
        assert result.probes_consumed < len(changed)

    def test_probe_budget_scales_logarithmically(self) -> None:
        import math

        for n in (4, 8, 16, 32):
            changed = [f"t{i}" for i in range(n)]
            probe = _fixed_effect_probe({f"t{n // 2}": 0.20})
            result = attribute_greedy_bisection(changed, probe)
            # ceil(log2 n) splits + 1 confirmation probe TO FIND the one real culprit, plus a
            # second (failing) search of the same rough cost over the remainder to check for
            # additional culprits -- both real, both now honestly counted (probes_consumed fix
            # below), so the budget is ~2x a single search's cost, with slack for parity effects.
            assert result.probes_consumed <= 2 * math.ceil(math.log2(n)) + 3

    def test_no_culprit_found_returns_all_at_zero(self) -> None:
        changed = ["a", "b", "c"]
        probe = _fixed_effect_probe({})  # no tool has any effect
        result = attribute_greedy_bisection(changed, probe)
        assert {c.tool_name for c in result.ranked} == set(changed)
        assert all(c.attributed_effect_pp == 0.0 for c in result.ranked)

    def test_probes_consumed_counts_every_real_probe_call_on_total_failure(self) -> None:
        """Regression test for the bug reported in reports/v0_5_effect_size_sensitivity.md sec 5:
        `_bisect_within` used to silently drop `probes_used` on every return-None path, so
        `attribute_greedy_bisection.probes_consumed` under-reported (often to exactly 0) whenever
        the search failed to isolate a culprit. A counting wrapper around the probe callback
        proves the invariant now holds unconditionally: probes_consumed == real probe() calls
        made, even on total search failure."""
        changed = [f"t{i}" for i in range(7)]
        base_probe = _fixed_effect_probe({})  # no tool has any effect -> guaranteed total failure
        call_count = 0

        def counting_probe(reverted: frozenset[str]) -> ProbeResult:
            nonlocal call_count
            call_count += 1
            return base_probe(reverted)

        result = attribute_greedy_bisection(changed, counting_probe, threshold=0.05)
        assert call_count > 0  # sanity: probes really were made, so a naive `== 0` would be wrong
        assert result.probes_consumed == call_count

    def test_probes_consumed_counts_every_real_probe_call_across_multiple_culprits(self) -> None:
        """Same invariant, but exercising the outer `while remaining:` loop across more than one
        `_bisect_within` call: one culprit is found (consuming its own probes), then the search
        continues on the remainder and fails outright (consuming further probes that must still be
        credited) -- probe-cost accounting must stay correct across outer-loop iterations too, not
        just within a single `_bisect_within` call."""
        changed = [f"t{i}" for i in range(6)]
        # t1 has a real, clearly-significant effect; every other tool has none, so once t1 is
        # found and reverted, bisection over the remainder is a guaranteed total failure.
        base_probe = _fixed_effect_probe({"t1": 0.30})
        call_count = 0

        def counting_probe(reverted: frozenset[str]) -> ProbeResult:
            nonlocal call_count
            call_count += 1
            return base_probe(reverted)

        result = attribute_greedy_bisection(changed, counting_probe, threshold=0.05)
        assert result.ranked[0].tool_name == "t1"
        assert result.probes_consumed == call_count

    def test_total_failure_ranking_reflects_measured_deltas_not_list_position(self) -> None:
        """Regression test for the bug's second half: on total search failure, tools probed along
        the way have real (if sub-threshold) measured marginal deltas -- the ranking must reflect
        those, not degenerate to `changed_tools`' input order (the pre-fix behavior, since every
        tool tied at a blanket 0.0). Effects are chosen so every marginal delta bisection actually
        measures is sub-threshold (forcing total failure) but NOT equal, and so that the
        higher-measured tools sit LATER in the input list than the positional-order fallback would
        predict -- if the ranking merely reproduced list order, this test would fail."""
        threshold = 0.05
        effects = {"t0": 0.01, "t1": 0.01, "t2": 0.04, "t3": 0.03}
        probe = _fixed_effect_probe(effects)

        changed_forward = ["t0", "t1", "t2", "t3"]
        result_fwd = attribute_greedy_bisection(changed_forward, probe, threshold=threshold)
        assert result_fwd.probes_consumed > 0
        # Real measured deltas: t2 (0.04) and t3 (0.03) are each isolated individually and must
        # outrank the pair {t0, t1} (grouped delta 0.02) -- the opposite of raw list position.
        ranked_names_fwd = [c.tool_name for c in result_fwd.ranked]
        assert ranked_names_fwd[0] == "t2"
        assert ranked_names_fwd[1] == "t3"

        # Reverse the input list order. If ranking were driven by list position (the pre-fix bug),
        # reversing the input would exactly reverse the output. It does not: t2/t3 still rank
        # ahead of t0/t1 because that ordering is driven by genuinely-measured deltas, which don't
        # depend on which order the caller happened to list the tools in.
        changed_reversed = list(reversed(changed_forward))
        result_rev = attribute_greedy_bisection(changed_reversed, probe, threshold=threshold)
        ranked_names_rev = [c.tool_name for c in result_rev.ranked]
        assert ranked_names_rev[0] == "t2"
        assert ranked_names_rev[1] == "t3"
        assert ranked_names_rev != list(reversed(ranked_names_fwd))

    def test_bisect_within_empty_tools_returns_none_culprit_with_zero_probes(self) -> None:
        """Defensive branch: `_bisect_within` (private helper) guards against being called with
        an empty candidate list directly, even though `attribute_greedy_bisection`'s own outer
        loop never does this (it only calls in when `remaining` is non-empty). The return shape
        is always a 4-tuple now (never bare `None`) -- see the probe-accounting fix below."""
        culprit, culprit_probe, probes_used, elim_scores = _bisect_within(
            [], _fixed_effect_probe({}), frozenset(), 0.0, 0.05
        )
        assert culprit is None
        assert culprit_probe is None
        assert probes_used == 0
        assert elim_scores == {}

    def test_finds_multiple_independent_culprits(self) -> None:
        """Doctrine requires handling >1 independent culprit: once one is isolated and removed,
        bisection re-runs on the remainder if a residual regression signal remains."""
        changed = [f"t{i}" for i in range(6)]
        probe = _fixed_effect_probe({"t1": 0.15, "t4": 0.15})
        result = attribute_greedy_bisection(changed, probe)
        top_two = {c.tool_name for c in result.ranked[:2]}
        assert top_two == {"t1", "t4"}


class TestBaselineLargestTextualDiff:
    def test_ranks_by_edit_distance(self) -> None:
        changed = ["a", "b"]
        before = {"a": "Fetch a user record by id.", "b": "Fetch a user record by id."}
        after = {
            "a": "Fetch a user record by id.",  # unchanged -> distance 0
            "b": "Retrieve the complete user profile record given an identifier value.",
        }
        result = baseline_largest_textual_diff(changed, before, after)
        assert result.ranked[0].tool_name == "b"
        assert result.probes_consumed == 0

    def test_missing_description_defaults_to_empty_string(self) -> None:
        result = baseline_largest_textual_diff(["a"], {}, {})
        assert result.ranked[0].attributed_effect_pp == 0.0


class TestBaselineMostLintViolations:
    class _T:
        def __init__(self, name: str, description: str, inputSchema: dict) -> None:  # noqa: N803
            self.name = name
            self.description = description
            self.inputSchema = inputSchema

    def test_ranks_tool_with_new_blocking_violation_first(self) -> None:
        before = [
            self._T(
                "set_flag",
                "Set the mode.",
                {"type": "object", "properties": {"mode": {"type": "string"}}},
            ),
            self._T(
                "get_flag",
                "Get the mode.",
                {"type": "object", "properties": {"mode": {"type": "string"}}},
            ),
        ]
        after = [
            self._T(
                "set_flag",
                "Set the mode to true/false as needed.",
                {"type": "object", "properties": {"mode": {"type": "integer"}}},
            ),
            self._T(
                "get_flag",
                "Get the mode.",
                {"type": "object", "properties": {"mode": {"type": "string"}}},
            ),
        ]
        result = baseline_most_lint_violations(["set_flag", "get_flag"], before, after)
        assert result.ranked[0].tool_name == "set_flag"
        assert result.ranked[0].attributed_effect_pp > result.ranked[1].attributed_effect_pp
        assert result.probes_consumed == 0


class TestBaselineUniformRandom:
    def test_zero_probes(self) -> None:
        result = baseline_uniform_random(["a", "b", "c"], seed=42)
        assert result.probes_consumed == 0
        assert {c.tool_name for c in result.ranked} == {"a", "b", "c"}

    def test_deterministic_given_seed(self) -> None:
        r1 = baseline_uniform_random(["a", "b", "c", "d"], seed=42)
        r2 = baseline_uniform_random(["a", "b", "c", "d"], seed=42)
        assert [c.tool_name for c in r1.ranked] == [c.tool_name for c in r2.ranked]


class TestExpectedTopkAccuracy:
    def test_analytic_formula(self) -> None:
        assert expected_topk_accuracy(5, 1) == 0.2
        assert expected_topk_accuracy(5, 3) == 0.6
        assert expected_topk_accuracy(2, 3) == 1.0  # min(3, 2) / 2
        assert expected_topk_accuracy(0, 1) == 0.0

    def test_matches_repeated_draw_average(self) -> None:
        """Cross-check the analytic formula against many repeated random draws -- the doctrine's
        explicit requirement ("don't just run it once, since chance variance at one draw isn't
        the baseline's real accuracy")."""
        n_changed = 6
        changed = [f"t{i}" for i in range(n_changed)]
        true_culprit = "t3"
        n_draws = 2000
        top1_hits = 0
        for seed in range(n_draws):
            result = baseline_uniform_random(changed, seed=seed)
            if top_k_hit(result, true_culprit, 1):
                top1_hits += 1
        empirical_top1 = top1_hits / n_draws
        analytic_top1 = expected_topk_accuracy(n_changed, 1)
        assert abs(empirical_top1 - analytic_top1) < 0.05
