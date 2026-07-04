from __future__ import annotations

import json
from pathlib import Path

from agentgauge.frozen_protocol import JUDGE_SEED
from agentgauge.localizer import (
    PairGradedLocalizationResult,
    PairLocalizationResult,
    build_graded_localizer_prompt,
    build_localizer_prompt,
    localize_matrix,
    localize_matrix_graded,
    localize_pair,
    localize_pair_graded,
    parse_graded_score,
    parse_vote,
)
from agentgauge.providers import Message

REPO_ROOT = Path(__file__).parent.parent
GROUND_TRUTH_PATH = REPO_ROOT / "evals" / "fixtures" / "exp3_ground_truth.json"


class _SeedSpyProvider:
    """Test double that records every seed it is called with.

    MockProvider ignores the seed argument entirely, so it cannot verify the
    per-trial seed convention -- this spy captures (seed, prompt) per call and
    returns responses round-robin from a preset list.
    """

    model_name = "seed-spy"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.seen_seeds: list[int] = []
        self.seen_prompts: list[str] = []
        self._idx = 0

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        self.seen_seeds.append(seed)
        self.seen_prompts.append(messages[0].content)
        response = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        return response


# ── Prompt construction ────────────────────────────────────────────────────────


def test_prompt_includes_both_names_and_descriptions_verbatim() -> None:
    """Prompt must contain both tool names and both descriptions verbatim."""
    prompt = build_localizer_prompt(
        "delete_sitemap", "Delete a sitemap.", "manage_sitemaps", "All-in-one sitemap manager."
    )
    assert "delete_sitemap" in prompt
    assert "Delete a sitemap." in prompt
    assert "manage_sitemaps" in prompt
    assert "All-in-one sitemap manager." in prompt
    assert "CONFUSABLE: YES" in prompt
    assert "CONFUSABLE: NO" in prompt


# ── Seed convention ─────────────────────────────────────────────────────────────


async def test_localize_pair_uses_judge_seed_plus_trial_index() -> None:
    """Trial i must request seed=JUDGE_SEED+i -- not a fixed seed across trials."""
    spy = _SeedSpyProvider(["CONFUSABLE: NO", "CONFUSABLE: NO", "CONFUSABLE: NO"])
    await localize_pair("tool_a", "desc a", "tool_b", "desc b", spy)
    assert spy.seen_seeds == [JUDGE_SEED, JUDGE_SEED + 1, JUDGE_SEED + 2]


async def test_localize_pair_prompt_reused_across_trials() -> None:
    """The same prompt is sent for every trial of a given pair."""
    spy = _SeedSpyProvider(["CONFUSABLE: YES"] * 3)
    await localize_pair("tool_a", "desc a", "tool_b", "desc b", spy)
    assert len(set(spy.seen_prompts)) == 1


# ── Parsing ──────────────────────────────────────────────────────────────────────


def test_parse_vote_labeled_yes() -> None:
    assert parse_vote("CONFUSABLE: YES") == "YES"


def test_parse_vote_labeled_no() -> None:
    assert parse_vote("CONFUSABLE: NO") == "NO"


def test_parse_vote_labeled_case_insensitive() -> None:
    assert parse_vote("confusable: yes") == "YES"
    assert parse_vote("Confusable:No") == "NO"


def test_parse_vote_missing_label_bare_yes_fallback() -> None:
    """No CONFUSABLE label present, but a bare YES token is found."""
    assert parse_vote("I think the answer is YES, they could be confused.") == "YES"


def test_parse_vote_missing_label_bare_no_fallback() -> None:
    assert parse_vote("No, these tools are clearly distinct.") == "NO"


def test_parse_vote_garbage_response_is_parse_failed() -> None:
    """A response with neither a label nor a bare YES/NO token is PARSE-FAILED."""
    assert parse_vote("These tools serve different purposes entirely.") == "PARSE-FAILED"


def test_parse_vote_empty_response_is_parse_failed() -> None:
    assert parse_vote("") == "PARSE-FAILED"


# ── Majority vote aggregation ────────────────────────────────────────────────────


async def test_majority_vote_two_of_three_yes_is_confusable() -> None:
    spy = _SeedSpyProvider(["CONFUSABLE: YES", "CONFUSABLE: YES", "CONFUSABLE: NO"])
    result = await localize_pair("a", "desc a", "b", "desc b", spy)
    assert result.verdict == "CONFUSABLE"
    assert result.votes == ["YES", "YES", "NO"]
    assert result.parse_failed_count == 0


async def test_majority_vote_two_of_three_no_is_not_confusable() -> None:
    spy = _SeedSpyProvider(["CONFUSABLE: NO", "CONFUSABLE: NO", "CONFUSABLE: YES"])
    result = await localize_pair("a", "desc a", "b", "desc b", spy)
    assert result.verdict == "NOT-CONFUSABLE"
    assert result.votes == ["NO", "NO", "YES"]


async def test_all_parse_failed_is_undetermined_not_forced_no() -> None:
    """3/3 parse-failed must be UNDETERMINED, never silently coerced to NOT-CONFUSABLE."""
    spy = _SeedSpyProvider(["garbage one", "garbage two", "garbage three"])
    result = await localize_pair("a", "desc a", "b", "desc b", spy)
    assert result.verdict == "UNDETERMINED"
    assert result.parse_failed_count == 3
    assert result.votes == ["PARSE-FAILED", "PARSE-FAILED", "PARSE-FAILED"]


async def test_one_parse_failed_still_aggregates_over_remaining_two() -> None:
    """1 parse-failed + 2 YES among the remaining trials => CONFUSABLE."""
    spy = _SeedSpyProvider(["garbage", "CONFUSABLE: YES", "CONFUSABLE: YES"])
    result = await localize_pair("a", "desc a", "b", "desc b", spy)
    assert result.verdict == "CONFUSABLE"
    assert result.parse_failed_count == 1


# ── localize_matrix ──────────────────────────────────────────────────────────────


async def test_localize_matrix_returns_one_result_per_pair_in_order() -> None:
    spy = _SeedSpyProvider(["CONFUSABLE: NO"])
    pairs = [
        ("a1", "desc a1", "b1", "desc b1"),
        ("a2", "desc a2", "b2", "desc b2"),
    ]
    results = await localize_matrix(pairs, spy)
    assert len(results) == 2
    assert all(isinstance(r, PairLocalizationResult) for r in results)
    assert results[0].tool_a == "a1" and results[0].tool_b == "b1"
    assert results[1].tool_a == "a2" and results[1].tool_b == "b2"


# ── Ground-truth fixture integrity (regression guard) ─────────────────────────────


def test_ground_truth_fixture_has_exactly_24_pairs_with_expected_class_balance() -> None:
    """Regression guard: the pre-registered fixture must not be silently edited."""
    data = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    pairs = data["pairs"]
    assert len(pairs) == 24

    n_confused = sum(1 for p in pairs if p["label"] == "CONFUSED")
    n_not_confused = sum(1 for p in pairs if p["label"] == "NOT_CONFUSED")
    assert n_confused == 4
    assert n_not_confused == 20
    assert data["n_confused"] == 4
    assert data["n_not_confused"] == 20


# ── Graded-confidence retry (exp3_pre_registration.md Section 7) ────────────────

# ── Prompt construction ────────────────────────────────────────────────────────


def test_graded_prompt_includes_both_names_and_descriptions_verbatim() -> None:
    """Graded prompt must contain both tool names, descriptions, and the label instruction."""
    prompt = build_graded_localizer_prompt(
        "delete_sitemap", "Delete a sitemap.", "manage_sitemaps", "All-in-one sitemap manager."
    )
    assert "delete_sitemap" in prompt
    assert "Delete a sitemap." in prompt
    assert "manage_sitemaps" in prompt
    assert "All-in-one sitemap manager." in prompt
    assert "CONFUSABILITY: <number 0-10>" in prompt
    assert "0-2" in prompt and "9-10" in prompt


# ── Seed convention ─────────────────────────────────────────────────────────────


async def test_localize_pair_graded_uses_judge_seed_plus_trial_index() -> None:
    """Trial i must request seed=JUDGE_SEED+i -- not a fixed seed across trials."""
    spy = _SeedSpyProvider(["CONFUSABILITY: 0", "CONFUSABILITY: 0", "CONFUSABILITY: 0"])
    await localize_pair_graded("tool_a", "desc a", "tool_b", "desc b", spy)
    assert spy.seen_seeds == [JUDGE_SEED, JUDGE_SEED + 1, JUDGE_SEED + 2]


async def test_localize_pair_graded_prompt_reused_across_trials() -> None:
    """The same prompt is sent for every trial of a given pair."""
    spy = _SeedSpyProvider(["CONFUSABILITY: 3"] * 3)
    await localize_pair_graded("tool_a", "desc a", "tool_b", "desc b", spy)
    assert len(set(spy.seen_prompts)) == 1


# ── Parsing ──────────────────────────────────────────────────────────────────────


def test_parse_graded_score_labeled() -> None:
    assert parse_graded_score("CONFUSABILITY: 7") == 7.0


def test_parse_graded_score_labeled_case_insensitive() -> None:
    assert parse_graded_score("confusability: 7") == 7.0
    assert parse_graded_score("Confusability:8") == 8.0


def test_parse_graded_score_bare_number_fallback_no_label() -> None:
    """No CONFUSABILITY label present, but a bare number is found."""
    assert parse_graded_score("I'd say these tools score about 6 on confusability.") == 6.0


def test_parse_graded_score_garbage_with_no_digit_is_parse_failed() -> None:
    """A response with no digit at all is parse-failed (None), never coerced to 0."""
    assert parse_graded_score("These tools serve entirely different purposes.") is None


def test_parse_graded_score_empty_response_is_parse_failed() -> None:
    assert parse_graded_score("") is None


def test_parse_graded_score_out_of_range_clamped_to_ten() -> None:
    """CONFUSABILITY: 15 must not silently exceed 10 -- clamp to 10.0."""
    assert parse_graded_score("CONFUSABILITY: 15") == 10.0


# ── Mean aggregation ─────────────────────────────────────────────────────────────


async def test_mean_aggregation_ignores_parse_failed_not_treated_as_zero() -> None:
    """1 parse-failed + 2 real scores (e.g. 6 and 8) -> mean of just the 2 reals (7.0),
    not (0 + 6 + 8) / 3."""
    spy = _SeedSpyProvider(["garbage", "CONFUSABILITY: 6", "CONFUSABILITY: 8"])
    result = await localize_pair_graded("a", "desc a", "b", "desc b", spy)
    assert result.scores == [None, 6.0, 8.0]
    assert result.mean_score == 7.0
    assert result.parse_failed_count == 1
    assert result.verdict == "CONFUSABLE"


async def test_all_three_parse_failed_is_undetermined_not_forced() -> None:
    """3/3 parse-failed must be UNDETERMINED, never forced to a verdict."""
    spy = _SeedSpyProvider(["garbage one", "garbage two", "garbage three"])
    result = await localize_pair_graded("a", "desc a", "b", "desc b", spy)
    assert result.verdict == "UNDETERMINED"
    assert result.mean_score is None
    assert result.parse_failed_count == 3
    assert result.scores == [None, None, None]


# ── Threshold boundary (pre-registered cut point) ───────────────────────────────


async def test_mean_exactly_five_is_confusable() -> None:
    """Mean exactly 5.0 => CONFUSABLE (>=, not >) -- the pre-registered cut point."""
    spy = _SeedSpyProvider(["CONFUSABILITY: 5", "CONFUSABILITY: 5", "CONFUSABILITY: 5"])
    result = await localize_pair_graded("a", "desc a", "b", "desc b", spy)
    assert result.mean_score == 5.0
    assert result.verdict == "CONFUSABLE"


async def test_mean_four_point_nine_nine_is_not_confusable() -> None:
    """Mean 4.99 => NOT-CONFUSABLE -- just below the pre-registered cut point."""
    spy = _SeedSpyProvider(["CONFUSABILITY: 4.99", "CONFUSABILITY: 4.99", "CONFUSABILITY: 4.99"])
    result = await localize_pair_graded("a", "desc a", "b", "desc b", spy)
    assert result.mean_score == 4.99
    assert result.verdict == "NOT-CONFUSABLE"


# ── localize_matrix_graded ───────────────────────────────────────────────────────


async def test_localize_matrix_graded_returns_one_result_per_pair_in_order() -> None:
    spy = _SeedSpyProvider(["CONFUSABILITY: 2"])
    pairs = [
        ("a1", "desc a1", "b1", "desc b1"),
        ("a2", "desc a2", "b2", "desc b2"),
    ]
    results = await localize_matrix_graded(pairs, spy)
    assert len(results) == 2
    assert all(isinstance(r, PairGradedLocalizationResult) for r in results)
    assert results[0].tool_a == "a1" and results[0].tool_b == "b1"
    assert results[1].tool_a == "a2" and results[1].tool_b == "b2"
