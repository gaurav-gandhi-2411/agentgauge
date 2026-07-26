"""Pilot-scale, fully offline unit test for `scripts/real_probe.py`.

Per this repo's standing rule ("the LLM is always mocked in tests -- never add a test that
calls Ollama or any hosted API"), this test never touches the network or a real model. It uses
a small deterministic test double (`_RevertSensitiveProvider`, NOT
`agentgauge.providers.MockProvider` -- that one is a stateless round-robin responder and cannot
exercise "does reverting a tool's description change selection behavior", which is exactly the
mechanism this real `ProbeFn` measures) that inspects the actual prompt text `run_tasks` sends
and answers deterministically based on whether the queried tool listing currently shows a known
"broken" marker for the gold tool -- letting this test assert a genuine, sign-correct recovery
effect through the FULL real pipeline: in-memory MCP server construction, `run_tasks`, real
`TrialOutcome` scoring, and the real `agentgauge.harness.diff_server_level` estimator.
"""

from __future__ import annotations

from typing import Any

from agentgauge.constraints import BlindTask
from agentgauge.providers import Message
from scripts.real_probe import RealAttributionCase, make_real_probe_fn

_BROKEN_MARKER = "BROKEN_MARKER_XYZ"


class _RevertSensitiveProvider:
    """Deterministic test double satisfying the `agentgauge.providers.Provider` Protocol
    structurally (not by inheritance, per this repo's Protocol convention). Given a task's exact
    description (matched against a supplied gold-tool map) and the CURRENT tool listing text it
    is shown, picks the gold tool UNLESS that tool's listing entry in THIS catalog contains
    `_BROKEN_MARKER` -- in which case it deterministically picks a different, wrong tool. The
    argument-construction prompt (second call per task) always gets an empty JSON object back --
    argument correctness is not what this ProbeFn measures."""

    def __init__(self, gold_by_description: dict[str, str]) -> None:
        self._gold_by_description = gold_by_description

    @property
    def model_name(self) -> str:
        return "fake-revert-sensitive"

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        content = messages[0].content
        if not content.startswith("Available tools:"):
            return "{}"
        listing, rest = content.split("\n\nTask: ", 1)
        description = rest.split("\nReply with ONLY")[0]
        gold = self._gold_by_description[description]
        gold_line = next(line for line in listing.splitlines() if line.startswith(f"{gold} "))
        if _BROKEN_MARKER in gold_line:
            fallback = next(
                line.split(" ")[0]
                for line in listing.splitlines()
                if not line.startswith(f"{gold} ")
            )
            return fallback
        return gold


def _tool(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": {}},
    }


def _build_pilot_case() -> RealAttributionCase:
    """A tiny, fully synthetic (not from a real example server) 2-tool case: `tool_a` is the
    true culprit (its regressed description carries `_BROKEN_MARKER`), `tool_b` is unchanged."""
    all_tools_before = [_tool("tool_a", "Handles A things."), _tool("tool_b", "Handles B things.")]
    all_tools_after = [
        _tool("tool_a", f"Handles A things. {_BROKEN_MARKER}"),
        _tool("tool_b", "Handles B things."),
    ]
    blind_tasks = [
        BlindTask(tool_name="tool_a", description="Please do the A thing."),
        BlindTask(tool_name="tool_b", description="Please do the B thing."),
    ]
    return RealAttributionCase(
        case_id="pilot_case",
        server_name="pilot-test-server",
        all_tools_before=all_tools_before,
        all_tools_after=all_tools_after,
        changed_tools=["tool_a"],
        true_culprit="tool_a",
        blind_tasks=blind_tasks,
    )


def _provider() -> _RevertSensitiveProvider:
    return _RevertSensitiveProvider(
        {
            "Please do the A thing.": "tool_a",
            "Please do the B thing.": "tool_b",
        }
    )


def test_probe_recovers_positive_delta_when_true_culprit_is_reverted() -> None:
    """End-to-end: reverting the true culprit (tool_a) should measure a positive recovery delta
    -- selection accuracy on tool_a's task goes from wrong (broken marker present) to correct
    (marker gone) -- while tool_b's task is answered correctly in both arms."""
    case = _build_pilot_case()
    provider = _provider()
    probe, stats = make_real_probe_fn(case, provider, trials=1, n_resamples=50, seed=42)

    result = probe(frozenset({"tool_a"}))

    assert result.delta > 0.0
    assert result.ci_lo <= result.delta <= result.ci_hi
    assert stats.n_probe_calls == 1
    assert stats.n_cache_hits == 0
    assert stats.before_arm_n_tasks == 2
    assert stats.before_arm_wallclock_s >= 0.0
    assert len(stats.per_probe_wallclock_s) == 1


def test_probe_reverting_nothing_yields_zero_delta() -> None:
    """Reverting the empty set means the 'after' arm is byte-identical to the 'before' arm
    (both are the constant regressed catalog) -- the measured delta must be exactly 0.0."""
    case = _build_pilot_case()
    provider = _provider()
    probe, _stats = make_real_probe_fn(case, provider, trials=1, n_resamples=50, seed=42)

    result = probe(frozenset())

    assert result.delta == 0.0


def test_probe_caches_repeated_identical_reverted_subsets() -> None:
    """Calling `probe()` twice with the SAME `reverted` subset must not re-run live inference --
    `RealProbeStats.n_cache_hits` should record the second call, `n_probe_calls` should not grow,
    and the returned `ProbeResult` must be identical (same cached trials feed the same
    `diff_server_level` call)."""
    case = _build_pilot_case()
    provider = _provider()
    probe, stats = make_real_probe_fn(case, provider, trials=1, n_resamples=50, seed=42)

    first = probe(frozenset({"tool_a"}))
    second = probe(frozenset({"tool_a"}))

    assert stats.n_probe_calls == 1
    assert stats.n_cache_hits == 1
    assert first == second


def test_probe_reverting_unaffected_tool_does_not_recover() -> None:
    """Reverting `tool_b` (never mutated, not the true culprit) changes nothing observable --
    the measured delta should be exactly 0.0, the same as reverting nothing."""
    case = _build_pilot_case()
    provider = _provider()
    probe, _stats = make_real_probe_fn(case, provider, trials=1, n_resamples=50, seed=42)

    result = probe(frozenset({"tool_b"}))

    assert result.delta == 0.0
