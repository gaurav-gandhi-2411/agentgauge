"""Failure attribution / regression localization (AgentGauge v0.5, Wave 1, Component 1.2).

Per `reports/v0_5_eval_doctrine.md` (Component 1.2) and `spec-agentgauge-v0.5.md` sec 4.2: given a
multi-tool, multi-file change already known (via `agentgauge diff`) to have regressed task success,
identify *which* tool description(s) among the changed set caused it. This is a credit-assignment
/ ranking problem over a known-finite candidate set (the changed tools), not a detection task.

This module implements three probe-based localization strategies plus a shared scoring interface.
Every strategy is driven by a caller-supplied `ProbeFn`: a callback that, given a candidate subset
of changed tools to "revert" back to their pre-change description, returns a measured effect size
+ CI for that revert. In production this callback is backed by `agentgauge.harness`'s existing
paired + CUPED + cluster-bootstrap estimator (`diff_server_level`) run against real trial data, so
attribution reuses the harness's already-validated statistics rather than a second estimator
(per the doctrine's explicit instruction: "use the existing paired + CUPED estimator so each probe
is cheap"). In tests, and in the injected-culprit benchmark (`agentgauge/attribution_benchmark.py`),
the same `ProbeFn` interface is backed by a deterministic ground-truth model with zero LLM calls,
per this repo's standing rule that the LLM is always mocked in tests.

Two zero-probe baselines (largest textual diff, most lint-violation deltas) and one zero-probe
floor (uniform random) are also implemented here, per the doctrine's required baselines-to-beat.

NOT in scope for this module: `agentgauge.localizer` is a completely different, already-shipped
feature (EXP-3's pairwise tool-confusability judge) and must not be confused with this one.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agentgauge.harness import _lcg_random
from agentgauge.linter import LintReport, lint_tool_set
from agentgauge.scorer import _levenshtein


@dataclass(frozen=True)
class ProbeResult:
    """One probe's measured effect: reverting a candidate subset of changed tools back to their
    pre-change description, relative to reverting nothing (the current, regressed "after" state).
    `delta`/`ci_lo`/`ci_hi` are fractions (0.05 == 5 percentage points), matching
    `agentgauge.harness.DiffResult`/`ServerDiffResult`'s convention -- a positive delta means
    reverting this subset recovered some of the regression."""

    delta: float
    ci_lo: float
    ci_hi: float


# A probe callback: given the frozenset of changed-tool names to revert, return the measured
# effect of that revert relative to reverting nothing. Backed by `harness.diff_server_level` in
# production use, and by a deterministic ground-truth model in tests/the benchmark.
ProbeFn = Callable[[frozenset[str]], ProbeResult]

# Default significance threshold, matching `harness.diff_from_trials`/`diff_server_level`'s own
# default regression threshold (5 percentage points) -- attribution should use the same bar the
# harness itself uses to call something a real effect, not an independently invented one.
DEFAULT_THRESHOLD = 0.05


@dataclass
class AttributionCandidate:
    """One ranked suspect. `attributed_effect_pp` is a percentage-point effect size for the three
    probe-based strategies (attribute_exhaustive/_sampled_shapley/_greedy_bisection); for the
    zero-probe baselines it is a HEURISTIC RANKING SCORE IN A DIFFERENT UNIT (character edit
    distance for baseline (i), lint-violation-count delta for baseline (ii), an arbitrary
    tie-break score for baseline (iii)) -- reused as the same field name for a uniform ranked-list
    interface across all six methods, not because the units are comparable across methods."""

    tool_name: str
    attributed_effect_pp: float
    ci_lo: float | None = None
    ci_hi: float | None = None


@dataclass
class AttributionResult:
    """Result of one localization strategy/baseline run against one benchmark case (or one real
    `diff` regression). `ranked` is sorted most-suspected first."""

    strategy: str
    ranked: list[AttributionCandidate] = field(default_factory=list)
    probes_consumed: int = 0


def top_k_hit(result: AttributionResult, true_culprit: str, k: int) -> bool:
    """True if `true_culprit` appears among the top `k` ranked suspects."""
    return true_culprit in {c.tool_name for c in result.ranked[:k]}


# =============================================================================
# (a) Exhaustive single-tool ablation -- probe budget == len(changed_tools).
# =============================================================================


def attribute_exhaustive(changed_tools: list[str], probe: ProbeFn) -> AttributionResult:
    """Revert each changed tool individually, one probe per tool, rank by measured recovery
    effect (largest positive delta = most likely culprit). Probe budget = len(changed_tools) --
    this is the doctrine's "exhaustive" reference point every other strategy must beat on budget."""
    candidates = []
    for t in changed_tools:
        r = probe(frozenset({t}))
        candidates.append(
            AttributionCandidate(
                tool_name=t,
                attributed_effect_pp=r.delta * 100.0,
                ci_lo=r.ci_lo * 100.0,
                ci_hi=r.ci_hi * 100.0,
            )
        )
    candidates.sort(key=lambda c: c.attributed_effect_pp, reverse=True)
    return AttributionResult("exhaustive_ablation", candidates, len(changed_tools))


# =============================================================================
# (b) Sampled Shapley -- fixed, sub-exhaustive probe budget.
# =============================================================================


def _sampled_shapley_budget(n_changed: int) -> int:
    """Fixed probe budget for sampled-Shapley attribution: roughly half of `n_changed`, capped
    strictly below `n_changed` itself so the strategy is genuinely sub-exhaustive by construction
    for every n_changed >= 2 (per the doctrine's kill-bar: "must be genuinely sub-exhaustive to be
    worth building"). For n_changed <= 1 there is nothing to sample over."""
    if n_changed <= 1:
        return n_changed
    budget = max(2, math.ceil(n_changed * 0.5))
    return min(budget, n_changed - 1)


def attribute_sampled_shapley(
    changed_tools: list[str], probe: ProbeFn, seed: int = 42
) -> AttributionResult:
    """Approximate each changed tool's Shapley value via random-coalition sampling: draw a fixed,
    sub-exhaustive number of random subsets of `changed_tools` (each tool independently included
    with probability 0.5, via this repo's `_lcg_random` deterministic PRNG -- not `random`/numpy,
    per this repo's determinism convention), probe each DISTINCT sampled subset once (a probe
    cache means a subset sampled more than once, including the empty set, is never re-probed), and
    estimate each tool t's contribution as mean(probe-delta | subsets containing t) minus
    mean(probe-delta | subsets NOT containing t). The empty coalition's delta is defined as
    exactly 0.0 without a probe (reverting nothing changes nothing, by construction) and is always
    included as an anchor in the "not containing t" group so the contrast is well-defined even if
    every sampled subset happens to contain t.

    This is a simplified, single-round contrast estimator (not full permutation-based Shapley
    sampling, which would cost O(n) probes per permutation -- the same order as exhaustive
    ablation and therefore not sub-exhaustive). It is a defensible approximation of the same idea
    ("does this tool's presence in a coalition change the measured effect, on average"), at a
    fixed budget below exhaustive.

    CI is an approximate propagated interval (contribution +/- the mean half-width of the CIs of
    the "containing t" probes), not a fresh bootstrap over the contribution estimator itself --
    computing an exact CI for a Shapley contrast would require re-resampling across coalitions,
    out of scope for this budgeted approximation.
    """
    n = len(changed_tools)
    if n == 0:
        return AttributionResult("sampled_shapley", [], 0)

    budget = _sampled_shapley_budget(n)
    rng = _lcg_random(seed)
    cache: dict[frozenset[str], ProbeResult] = {frozenset(): ProbeResult(0.0, 0.0, 0.0)}
    sampled_subsets: list[frozenset[str]] = []
    probes_consumed = 0
    for _ in range(budget):
        subset = frozenset(t for t in changed_tools if rng() < 0.5)
        sampled_subsets.append(subset)
        if subset not in cache:
            cache[subset] = probe(subset)
            probes_consumed += 1

    candidates = []
    for t in changed_tools:
        with_deltas = [cache[s].delta for s in sampled_subsets if t in s]
        without_deltas = [cache[s].delta for s in sampled_subsets if t not in s]
        without_deltas.append(0.0)  # empty-coalition anchor, always available, free of charge
        mean_with = sum(with_deltas) / len(with_deltas) if with_deltas else 0.0
        mean_without = sum(without_deltas) / len(without_deltas)
        contribution = mean_with - mean_without
        with_widths = [cache[s].ci_hi - cache[s].ci_lo for s in sampled_subsets if t in s]
        half_width = (sum(with_widths) / len(with_widths) / 2.0) if with_widths else 0.0
        candidates.append(
            AttributionCandidate(
                tool_name=t,
                attributed_effect_pp=contribution * 100.0,
                ci_lo=(contribution - half_width) * 100.0,
                ci_hi=(contribution + half_width) * 100.0,
            )
        )
    candidates.sort(key=lambda c: c.attributed_effect_pp, reverse=True)
    return AttributionResult("sampled_shapley", candidates, probes_consumed)


# =============================================================================
# (c) Greedy bisection -- probe budget scales ~O(log n) per culprit found.
# =============================================================================


def _bisect_within(
    tools: list[str],
    probe: ProbeFn,
    base: frozenset[str],
    base_delta: float,
    threshold: float,
) -> tuple[str | None, ProbeResult | None, int, dict[str, float]]:
    """Binary-search for a single tool with a significant marginal recovery effect within
    `tools`, holding `base` (already-identified culprits, already reverted) fixed.

    Always returns a 4-tuple `(culprit, culprit_probe, probes_used, elim_scores)` -- `probes_used`
    and `elim_scores` are populated on EVERY path (success or failure) since real `probe()` calls
    and real (if not individually significant) marginal-delta measurements happen regardless of
    whether the search ultimately isolates a culprit. On success, `culprit`/`culprit_probe` are the
    isolated tool and its final marginal `ProbeResult`. On failure (no tool in `tools` shows a
    significant marginal effect), `culprit` and `culprit_probe` are both `None`, but `probes_used`
    still reports every real probe spent and `elim_scores` still carries every measured (if
    sub-threshold) marginal delta gathered along the way -- the caller must not discard either.
    `base_delta` is the already-measured probe(base) delta, passed in so it need not be re-probed.
    """
    candidates = list(tools)
    probes_used = 0
    elim_scores: dict[str, float] = {}
    while len(candidates) > 1:
        mid = len(candidates) // 2
        half_a, half_b = candidates[:mid], candidates[mid:]
        r = probe(base | frozenset(half_a))
        probes_used += 1
        marginal_delta = r.delta - base_delta
        marginal_ci_lo = r.ci_lo - base_delta
        if marginal_ci_lo > threshold:
            for t in half_b:
                elim_scores[t] = 0.0
            candidates = half_a
        else:
            for t in half_a:
                elim_scores[t] = marginal_delta
            candidates = half_b
    if not candidates:
        # Defensive only: `attribute_greedy_bisection`'s outer loop never calls this with an
        # empty `tools` list (it only calls in when `remaining` is non-empty), so this path is
        # unreachable via the real caller -- kept as a guard for any future/direct caller.
        return (None, None, probes_used, elim_scores)
    culprit = candidates[0]
    final = probe(base | frozenset({culprit}))
    probes_used += 1
    marginal_delta = final.delta - base_delta
    marginal_ci_lo = final.ci_lo - base_delta
    marginal_ci_hi = final.ci_hi - base_delta
    if marginal_ci_lo <= threshold:
        elim_scores[culprit] = marginal_delta
        return (None, None, probes_used, elim_scores)
    return (
        culprit,
        ProbeResult(marginal_delta, marginal_ci_lo, marginal_ci_hi),
        probes_used,
        elim_scores,
    )


def attribute_greedy_bisection(
    changed_tools: list[str], probe: ProbeFn, threshold: float = DEFAULT_THRESHOLD
) -> AttributionResult:
    """Binary-search-style localization: revert half the changed set, probe, recurse into
    whichever half still shows a significant recovery effect (per `threshold`, the same
    convention `harness.diff_from_trials` uses for calling something a real effect). Once a
    culprit is isolated and removed from consideration, bisection re-runs on the remainder
    (holding the found culprit reverted) if any residual effect signal remains -- handling the
    possibility of multiple independent culprits, though this benchmark's generator only ever
    injects one. Probe budget is ~ceil(log2(n)) + 1 (one confirmation probe) per culprit found,
    strictly less than exhaustive ablation's n probes for n >= 3.

    Tools ruled out along the way are still returned (needed for top-3 scoring), ranked by the
    marginal delta of the half they were eliminated with (higher = more suspicious even though
    not individually isolated), after all isolated culprits.

    Probe-cost accounting invariant: `probes_consumed` on the returned `AttributionResult` is the
    exact sum of every real `probe()` call made by every `_bisect_within` invocation across every
    iteration of the outer loop below -- including invocations that fail to isolate a culprit.
    `_bisect_within` always reports `probes_used` regardless of outcome (see its docstring), and
    every iteration here adds it to `probes_consumed` unconditionally, before branching on whether
    a culprit was found.
    """
    remaining = list(changed_tools)
    reverted_base: frozenset[str] = frozenset()
    base_delta = 0.0
    found: list[AttributionCandidate] = []
    probes_consumed = 0
    elim_scores: dict[str, float] = {}

    while remaining:
        culprit, culprit_probe, probes_used, this_elim = _bisect_within(
            remaining, probe, reverted_base, base_delta, threshold
        )
        probes_consumed += probes_used
        elim_scores.update(this_elim)
        if culprit is None or culprit_probe is None:
            # Total search failure: `_bisect_within` measured a real (if sub-threshold) marginal
            # delta for every tool in `remaining` along the way (each round's eliminated half gets
            # an entry -- see its docstring/loop), so `elim_scores` already covers every tool here.
            # This `setdefault` fallback is defensive only, for a tool that was somehow never
            # probed; tracing `_bisect_within`'s loop shows this cannot actually happen given how
            # the outer loop only ever calls it with a non-empty `remaining`, so this never fires
            # in practice -- kept as a guard rather than assuming the invariant always holds.
            for t in remaining:
                elim_scores.setdefault(t, 0.0)
            break
        found.append(
            AttributionCandidate(
                tool_name=culprit,
                attributed_effect_pp=culprit_probe.delta * 100.0,
                ci_lo=culprit_probe.ci_lo * 100.0,
                ci_hi=culprit_probe.ci_hi * 100.0,
            )
        )
        remaining = [t for t in remaining if t != culprit]
        reverted_base = reverted_base | frozenset({culprit})
        base_delta = culprit_probe.delta + base_delta

    found.sort(key=lambda c: c.attributed_effect_pp, reverse=True)
    found_names = {c.tool_name for c in found}
    rest = [t for t in changed_tools if t not in found_names]
    rest_candidates = [
        AttributionCandidate(tool_name=t, attributed_effect_pp=elim_scores.get(t, 0.0) * 100.0)
        for t in rest
    ]
    rest_candidates.sort(key=lambda c: c.attributed_effect_pp, reverse=True)
    return AttributionResult("greedy_bisection", found + rest_candidates, probes_consumed)


# =============================================================================
# Zero-probe baselines (spec-agentgauge-v0.5.md sec 4.2 / doctrine Component 1.2).
# =============================================================================


def baseline_largest_textual_diff(
    changed_tools: list[str],
    before_descriptions: dict[str, str],
    after_descriptions: dict[str, str],
) -> AttributionResult:
    """(i) Blame the tool with the largest textual diff between its before/after description --
    zero probes. Uses character-level Levenshtein edit distance (`agentgauge.scorer._levenshtein`,
    already implemented and calibrated for this repo's near-duplicate-name checks) as the diff-
    size proxy, rather than a second edit-distance implementation."""
    candidates = [
        AttributionCandidate(
            tool_name=t,
            attributed_effect_pp=float(
                _levenshtein(before_descriptions.get(t, ""), after_descriptions.get(t, ""))
            ),
        )
        for t in changed_tools
    ]
    candidates.sort(key=lambda c: c.attributed_effect_pp, reverse=True)
    return AttributionResult("largest_textual_diff", candidates, 0)


def baseline_most_lint_violations(
    changed_tools: list[str],
    before_tools: list[Any],
    after_tools: list[Any],
) -> AttributionResult:
    """(ii) Blame the tool with the most lint-violation-count delta (after minus before), using
    the existing deterministic (free, zero-LLM) linter -- zero additional-inference probes.
    `before_tools`/`after_tools` must be the FULL catalog (not just the changed subset), since
    `lint_tool_set`'s checks are sibling-aware (name-collision, cross-tool workflow references).
    Pairwise `name_collision` violations (which name two tools jointly, e.g. "toolA/toolB") are
    excluded from the per-tool count -- they cannot be uniquely attributed to one changed tool."""

    def _count_by_tool(report: LintReport) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in report.blocking + report.advisory + report.info:
            if "/" in v.tool_name:  # pairwise collision violation, not attributable to one tool
                continue
            counts[v.tool_name] = counts.get(v.tool_name, 0) + 1
        return counts

    before_counts = _count_by_tool(lint_tool_set(before_tools))
    after_counts = _count_by_tool(lint_tool_set(after_tools))
    candidates = [
        AttributionCandidate(
            tool_name=t,
            attributed_effect_pp=float(after_counts.get(t, 0) - before_counts.get(t, 0)),
        )
        for t in changed_tools
    ]
    candidates.sort(key=lambda c: c.attributed_effect_pp, reverse=True)
    return AttributionResult("most_lint_violations", candidates, 0)


def baseline_uniform_random(changed_tools: list[str], seed: int = 42) -> AttributionResult:
    """(iii) Floor baseline: one deterministic (seed-derived) uniformly random ordering of the
    changed-tool set -- zero probes. Suitable for slotting into the same per-case scoring loop as
    the other five methods. IMPORTANT: per the doctrine, a single draw's incidental hit/miss is
    NOT this baseline's real accuracy -- use `expected_topk_accuracy` below (the analytic
    expectation) for the number that is actually reported and compared against the ship bar.
    """
    rng = _lcg_random(seed)
    order = sorted(changed_tools, key=lambda _: rng())
    n = len(order)
    candidates = [
        AttributionCandidate(tool_name=t, attributed_effect_pp=float(n - i))
        for i, t in enumerate(order)
    ]
    return AttributionResult("uniform_random", candidates, 0)


def expected_topk_accuracy(n_changed: int, k: int) -> float:
    """Analytic expected top-k accuracy of a uniform-random ranking over `n_changed` candidates
    containing exactly one true culprit: min(k, n_changed) / n_changed. This is the number the
    doctrine requires reporting for baseline (iii) -- not any single draw's realized hit/miss,
    since "chance variance at one draw isn't the baseline's real accuracy" (doctrine, baseline
    (iii))."""
    if n_changed <= 0:
        return 0.0
    return min(k, n_changed) / n_changed
