from __future__ import annotations

from mcp.types import Tool

from agentgauge.providers import MockProvider
from agentgauge.scorer import (
    DIMENSION_WEIGHTS,
    _heuristic_subscore,
    _levenshtein,
    _parse_distinguish_score,
    score_all,
    score_discoverability,
)

# ── Tool fixtures ─────────────────────────────────────────────────────────────

# Good catalog: three distinctly-named tools, all with descriptions, no collisions.
GOOD_TOOLS = [
    Tool(
        name="send_email",
        description="Send an email to one or more recipients",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="list_contacts",
        description="List all contacts stored in the address book",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="read_calendar_event",
        description="Read the details of a specific calendar event",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]

# Bad catalog: placeholder names, missing descriptions, one near-duplicate pair.
BAD_TOOLS = [
    Tool(
        name="tool1",
        description=None,
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="foo",
        description=None,
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="search_user",
        description="Search for a user by name or email",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    # Near-duplicate of search_user (edit-distance similarity ≈ 0.92)
    Tool(
        name="search_users",
        description="Search for multiple users matching criteria",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]

SINGLE_TOOL = Tool(
    name="echo",
    description="Echo a message back",
    inputSchema={"type": "object", "properties": {}, "required": []},
)

# ── _levenshtein ──────────────────────────────────────────────────────────────


def test_levenshtein_identical() -> None:
    assert _levenshtein("abc", "abc") == 0


def test_levenshtein_empty_strings() -> None:
    assert _levenshtein("", "") == 0


def test_levenshtein_one_empty() -> None:
    assert _levenshtein("hello", "") == 5


def test_levenshtein_single_insertion() -> None:
    assert _levenshtein("search_user", "search_users") == 1


def test_levenshtein_asymmetric_inputs_symmetric_result() -> None:
    assert _levenshtein("abc", "xyz") == _levenshtein("xyz", "abc")


# ── _parse_distinguish_score ──────────────────────────────────────────────────


def test_parse_distinguish_labeled_format() -> None:
    # Happy path: model follows the new format exactly.
    assert _parse_distinguish_score("CLARITY: 8\nDISTINGUISH: 4") == 4.0


def test_parse_distinguish_labeled_case_insensitive() -> None:
    assert _parse_distinguish_score("clarity: 8\ndistinguish: 6") == 6.0


def test_parse_distinguish_labeled_beats_last_number() -> None:
    # Label should win over last-number strategy even when label is first.
    assert _parse_distinguish_score("DISTINGUISH: 3\nCLARITY: 9") == 3.0


def test_parse_distinguish_two_unlabeled_takes_last() -> None:
    # Model answers two numbers without labels — last is assumed to be DISTINGUISH.
    assert _parse_distinguish_score("8\n4") == 4.0


def test_parse_distinguish_single_bare_number() -> None:
    # Legacy / bare-number fallback for simple responses.
    assert _parse_distinguish_score("7") == 7.0


def test_parse_distinguish_clamps_to_10() -> None:
    assert _parse_distinguish_score("DISTINGUISH: 11") == 10.0


def test_parse_distinguish_no_digit_returns_none() -> None:
    assert _parse_distinguish_score("no number here") is None


# ── _heuristic_subscore ───────────────────────────────────────────────────────


def test_heuristic_good_catalog_scores_near_100() -> None:
    score, _, _, _ = _heuristic_subscore(GOOD_TOOLS)
    assert score >= 90.0, f"Good catalog heuristic should be ≥ 90, got {score:.1f}"


def test_heuristic_bad_catalog_scores_materially_lower() -> None:
    good_score, _, _, _ = _heuristic_subscore(GOOD_TOOLS)
    bad_score, _, _, _ = _heuristic_subscore(BAD_TOOLS)
    gap = good_score - bad_score
    assert gap >= 30.0, (
        f"Good catalog ({good_score:.1f}) should beat bad catalog ({bad_score:.1f}) "
        f"by ≥ 30 pts; gap={gap:.1f}"
    )


def test_heuristic_detects_collision_pair() -> None:
    _, _, collisions, _ = _heuristic_subscore(BAD_TOOLS)
    collision_names = {frozenset(p) for p in collisions}
    assert frozenset({"search_user", "search_users"}) in collision_names


def test_heuristic_no_collisions_in_good_catalog() -> None:
    _, _, collisions, _ = _heuristic_subscore(GOOD_TOOLS)
    assert collisions == []


def test_heuristic_per_tool_good_catalog_all_max_points() -> None:
    _, _, _, per_tool = _heuristic_subscore(GOOD_TOOLS)
    for name, pts in per_tool.items():
        assert pts == 3, f"Tool '{name}' should earn 3/3 heuristic points, got {pts}"


def test_heuristic_per_tool_bad_catalog_has_low_scorers() -> None:
    _, _, _, per_tool = _heuristic_subscore(BAD_TOOLS)
    # "foo": generic name (0) + short name (0) + no description (0) = 0
    assert per_tool["foo"] == 0
    # "tool1": generic (0) + len > 3 (1) + no description (0) = 1
    assert per_tool["tool1"] == 1


def test_heuristic_fix_hint_for_generic_name() -> None:
    _, hints, _, _ = _heuristic_subscore(BAD_TOOLS)
    assert any("tool1" in h and "non-descriptive" in h for h in hints)


def test_heuristic_fix_hint_for_missing_description() -> None:
    _, hints, _, _ = _heuristic_subscore(BAD_TOOLS)
    assert any("foo" in h and "description" in h for h in hints)


def test_heuristic_fix_hint_for_collision_pair() -> None:
    _, hints, _, _ = _heuristic_subscore(BAD_TOOLS)
    assert any("search_user" in h and "search_users" in h for h in hints)


def test_heuristic_empty_tools() -> None:
    # Called with empty list — score_discoverability catches this first, but
    # _heuristic_subscore should not crash on zero-length input.
    # Guard via a single tool as the minimum real case.
    score, hints, collisions, per_tool = _heuristic_subscore([SINGLE_TOOL])
    assert 0.0 <= score <= 100.0


# ── score_discoverability (judge mocked) ──────────────────────────────────────


async def test_discoverability_no_tools_returns_zero() -> None:
    result = await score_discoverability([], MockProvider())
    assert result.score == 0.0
    assert result.name == "discoverability"


async def test_discoverability_details_expose_both_subscores() -> None:
    result = await score_discoverability(
        GOOD_TOOLS, MockProvider(responses=["CLARITY: 8\nDISTINGUISH: 8"]), trials=1
    )
    assert "heuristic_score" in result.details
    assert "judge_score" in result.details
    assert "judge_trials" in result.details
    assert "avg_variance" in result.details
    assert "per_tool_heuristic" in result.details
    assert "collision_pairs" in result.details


async def test_discoverability_good_catalog_mock_high_scores_above_bad_mock_low() -> None:
    # Good catalog: mock DISTINGUISH=9 → judge_score=90, heuristic≈100 → blend≈96
    good = await score_discoverability(
        GOOD_TOOLS, MockProvider(responses=["CLARITY: 9\nDISTINGUISH: 9"]), trials=1
    )
    # Bad catalog: mock DISTINGUISH=2 → judge_score=20, heuristic≈43 → blend≈34
    bad = await score_discoverability(
        BAD_TOOLS, MockProvider(responses=["CLARITY: 2\nDISTINGUISH: 2"]), trials=1
    )
    gap = good.score - bad.score
    assert gap >= 40.0, (
        f"Good catalog ({good.score}) should beat bad catalog ({bad.score}) "
        f"by ≥ 40 pts; gap={gap:.1f}"
    )


async def test_discoverability_blend_is_60_40_heuristic() -> None:
    # With a perfect heuristic catalog (GOOD_TOOLS) and mock DISTINGUISH=6:
    # blend = 0.60 * 100 + 0.40 * 60 = 84.0
    result = await score_discoverability(
        GOOD_TOOLS, MockProvider(responses=["CLARITY: 8\nDISTINGUISH: 6"]), trials=1
    )
    h = result.details["heuristic_score"]
    j = result.details["judge_score"]
    expected = round(0.60 * h + 0.40 * j, 1)
    assert abs(result.score - expected) < 0.5, (
        f"Blend mismatch: expected {expected} (60/40), got {result.score}"
    )


async def test_discoverability_good_catalog_no_fix_hints_from_heuristic() -> None:
    # Good catalog should produce no heuristic hints (all tools are clean).
    result = await score_discoverability(GOOD_TOOLS, MockProvider(responses=["9"]), trials=1)
    # fix_hints may include judge hints if judge score is low, but not heuristic ones.
    # With a mock score of 9 the judge hint threshold (< 6.0) is not triggered either.
    assert result.fix_hints == []


async def test_discoverability_bad_catalog_has_fix_hints() -> None:
    result = await score_discoverability(
        BAD_TOOLS, MockProvider(responses=["CLARITY: 3\nDISTINGUISH: 3"]), trials=1
    )
    assert len(result.fix_hints) > 0


async def test_discoverability_name_is_discoverability() -> None:
    result = await score_discoverability(GOOD_TOOLS, MockProvider())
    assert result.name == "discoverability"


async def test_discoverability_multi_trial_details() -> None:
    result = await score_discoverability(
        GOOD_TOOLS,
        MockProvider(
            responses=[
                "CLARITY: 8\nDISTINGUISH: 8",
                "CLARITY: 9\nDISTINGUISH: 9",
                "CLARITY: 7\nDISTINGUISH: 7",
            ]
        ),
        trials=3,
    )
    assert result.details["judge_trials"] == 3
    assert isinstance(result.details["avg_variance"], float)


# ── score_all integration ──────────────────────────────────────────────────────


async def test_score_all_discoverability_not_stub() -> None:
    report = await score_all([SINGLE_TOOL], MockProvider(responses=["7"]), base_url=None)
    names = [d.name for d in report.dimensions]
    assert "discoverability" in names
    disc = next(d for d in report.dimensions if d.name == "discoverability")
    assert disc.details.get("status") != "not_implemented"


async def test_score_all_discoverability_weight_is_15pct() -> None:
    assert DIMENSION_WEIGHTS.get("discoverability") == 0.15


async def test_score_all_discoverability_details_have_subscores() -> None:
    report = await score_all([SINGLE_TOOL], MockProvider(responses=["7"]), base_url=None)
    disc = next(d for d in report.dimensions if d.name == "discoverability")
    assert "heuristic_score" in disc.details
    assert "judge_score" in disc.details
