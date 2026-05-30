from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool

from agentgauge.client import MCPClient, ToolCallResult
from agentgauge.providers import MockProvider
from agentgauge.scorer import (
    _error_probes,
    _extract_error_text,
    score_error_legibility,
)

# ── Tool fixtures ────────────────────────────────────────────────────────────

ECHO_TOOL = Tool(
    name="echo",
    description="Echo a message back",
    inputSchema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Text to echo"},
        },
        "required": ["message"],
    },
)

NO_REQUIRED_TOOL = Tool(
    name="ping",
    description="Ping the server",
    inputSchema={"type": "object", "properties": {}},
)

# ── Error text fixtures ──────────────────────────────────────────────────────

# A clear, specific error — names the field and what's expected.
GOOD_ERROR = (
    "Invalid argument: required field 'message' was not provided. "
    "Please supply a non-empty string value for the 'message' parameter."
)

# An opaque error — no field name, no guidance.
BAD_ERROR = "Error 500"


# ── Mock client factory ──────────────────────────────────────────────────────


def _make_error_client(error_text: str, tool: Tool = ECHO_TOOL) -> MCPClient:
    """Return a mock MCPClient whose every tool call fails with error_text.

    Uses RuntimeError so the exception path in MCPClient.call_tool populates
    ToolCallResult.error with the message.
    """
    session = MagicMock()
    session.call_tool = AsyncMock(side_effect=RuntimeError(error_text))
    tools_resp = MagicMock()
    tools_resp.tools = [tool]
    resources_resp = MagicMock()
    resources_resp.resources = []
    prompts_resp = MagicMock()
    prompts_resp.prompts = []
    session.list_tools = AsyncMock(return_value=tools_resp)
    session.list_resources = AsyncMock(return_value=resources_resp)
    session.list_prompts = AsyncMock(return_value=prompts_resp)
    return MCPClient(session)


# ── _error_probes unit tests ─────────────────────────────────────────────────


def test_error_probes_required_tool_yields_two_cases() -> None:
    probes = _error_probes(ECHO_TOOL)
    assert len(probes) == 2
    labels = [p.label for p in probes]
    assert "missing_required" in labels
    assert any("wrong_type" in lbl for lbl in labels)


def test_error_probes_missing_required_uses_empty_args() -> None:
    probes = _error_probes(ECHO_TOOL)
    empty_probe = next(p for p in probes if p.label == "missing_required")
    assert empty_probe.args == {}


def test_error_probes_wrong_type_injects_non_string_for_string_param() -> None:
    probes = _error_probes(ECHO_TOOL)
    wrong_probe = next(p for p in probes if "wrong_type" in p.label)
    assert not isinstance(wrong_probe.args.get("message"), str)


def test_error_probes_no_required_yields_unknown_param() -> None:
    probes = _error_probes(NO_REQUIRED_TOOL)
    assert len(probes) == 1
    assert probes[0].label == "unknown_param"
    assert "__bad_field__" in probes[0].args


# ── _extract_error_text unit tests ───────────────────────────────────────────


def test_extract_error_text_from_error_field() -> None:
    result = ToolCallResult(success=False, content=[], error="field 'x' is required")
    assert _extract_error_text(result) == "field 'x' is required"


def test_extract_error_text_from_content_text() -> None:
    item = MagicMock()
    item.text = "bad type on param y"
    result = ToolCallResult(success=True, content=[item])
    assert _extract_error_text(result) == "bad type on param y"


def test_extract_error_text_fallback_when_no_message() -> None:
    result = ToolCallResult(success=True, content=[])
    assert _extract_error_text(result) == "(no error message returned)"


def test_extract_error_text_prefers_error_field_over_content() -> None:
    item = MagicMock()
    item.text = "content text"
    result = ToolCallResult(success=False, content=[item], error="error field text")
    assert _extract_error_text(result) == "error field text"


# ── score_error_legibility ────────────────────────────────────────────────────


async def test_score_error_legibility_no_tools() -> None:
    client = _make_error_client(BAD_ERROR)
    provider = MockProvider(responses=["5"])
    result = await score_error_legibility([], client, provider)
    assert result.score == 0.0
    assert result.name == "error_legibility"


async def test_score_error_legibility_good_error_scores_high() -> None:
    """A clear, actionable error message should score ≥ 70/100 when judge returns 8."""
    client = _make_error_client(GOOD_ERROR)
    provider = MockProvider(responses=["8"])
    result = await score_error_legibility([ECHO_TOOL], client, provider, trials=3)
    assert result.name == "error_legibility"
    assert result.score >= 70.0


async def test_score_error_legibility_bad_error_scores_low() -> None:
    """An opaque error message should score ≤ 30/100 when judge returns 2."""
    client = _make_error_client(BAD_ERROR)
    provider = MockProvider(responses=["2"])
    result = await score_error_legibility([ECHO_TOOL], client, provider, trials=3)
    assert result.score <= 30.0


async def test_good_error_beats_bad_error_by_large_margin() -> None:
    """Core correctness test: clear errors must outscore opaque ones by ≥ 40 points.

    This test FAILS if:
    - the judge wiring silently stubs out (both scores would be 0)
    - the aggregation collapses variance (both would equal the same value)
    - the score formula is inverted

    Judge returns "8" for GOOD_ERROR and "2" for BAD_ERROR → expected gap ≈ 60 points.
    Asserting ≥ 40 leaves room for formula changes while still catching regressions.
    """
    good_client = _make_error_client(GOOD_ERROR)
    bad_client = _make_error_client(BAD_ERROR)

    good_score = await score_error_legibility(
        [ECHO_TOOL], good_client, MockProvider(responses=["8"]), trials=3
    )
    bad_score = await score_error_legibility(
        [ECHO_TOOL], bad_client, MockProvider(responses=["2"]), trials=3
    )

    gap = good_score.score - bad_score.score
    assert gap >= 40.0, (
        f"good error ({good_score.score}) should outscore bad error ({bad_score.score}) "
        f"by ≥ 40 pts, but gap was {gap:.1f}"
    )


async def test_three_tier_scoring_locks_actionability() -> None:
    """Regression test for the two-dimension rubric (diagnosis × actionability).

    Three tiers with distinct mock judge scores that mirror the rubric anchors:
      "1" → opaque ("Error 500")                             0–2 band
      "5" → diagnosis-only ("...is missing.")                5–6 cap
      "9" → what+how ("...is missing — add it and retry.")   9–10 band

    Assertions verify:
    1. Strict ordering: opaque < diagnosis-only < what+how
    2. Diagnosis-only is capped in the middle band (40–65), not the high band
    3. Actionability gap (what+how minus diagnosis-only) ≥ 25 pts — the regression
       lock that fails if the rubric collapses back to measuring clarity alone
    4. Diagnosis gap (diagnosis-only minus opaque) ≥ 20 pts — naming the field
       still matters materially
    """
    OPAQUE = "Error 500"
    DIAG_ONLY = "Required field 'message' (string) is missing."
    WHAT_HOW = "Required field 'message' (string) is missing — add it and retry."

    opaque_score = await score_error_legibility(
        [ECHO_TOOL], _make_error_client(OPAQUE), MockProvider(responses=["1"]), trials=1
    )
    diag_score = await score_error_legibility(
        [ECHO_TOOL], _make_error_client(DIAG_ONLY), MockProvider(responses=["5"]), trials=1
    )
    what_how_score = await score_error_legibility(
        [ECHO_TOOL], _make_error_client(WHAT_HOW), MockProvider(responses=["9"]), trials=1
    )

    # Strict ordering
    assert opaque_score.score < diag_score.score < what_how_score.score, (
        f"Expected opaque ({opaque_score.score}) < diag ({diag_score.score}) "
        f"< what+how ({what_how_score.score})"
    )

    # Band membership
    assert opaque_score.score <= 20, f"opaque should be ≤ 20, got {opaque_score.score}"
    assert 40 <= diag_score.score <= 65, (
        f"diagnosis-only should land in 40–65 (5–6 cap), got {diag_score.score}"
    )
    assert what_how_score.score >= 80, f"what+how should be ≥ 80, got {what_how_score.score}"

    # Actionability gap: what+how must materially outscore diagnosis-only
    actionability_gap = what_how_score.score - diag_score.score
    assert actionability_gap >= 25, (
        f"Actionability gap ({actionability_gap:.1f} pts) < 25 — "
        f"rubric is not separating diagnosis from actionability"
    )

    # Diagnosis gap: naming the field must materially outscore opaque
    diagnosis_gap = diag_score.score - opaque_score.score
    assert diagnosis_gap >= 20, (
        f"Diagnosis gap ({diagnosis_gap:.1f} pts) < 20 — "
        f"rubric is not rewarding field-level specificity"
    )


async def test_variance_reported_in_details() -> None:
    """details must carry 'avg_variance' and 'judge_trials'."""
    client = _make_error_client(GOOD_ERROR)
    # Mixed responses → non-zero variance across 3 trials
    provider = MockProvider(responses=["8", "6", "7"])
    result = await score_error_legibility([ECHO_TOOL], client, provider, trials=3)
    assert "avg_variance" in result.details
    assert "judge_trials" in result.details
    assert result.details["judge_trials"] == 3
    # With responses 8,6,7,8,6,7 (round-robin for 2 probes × 3 trials)
    # each probe mean = 7.0; variance per probe = ((8-7)²+(6-7)²+(7-7)²)/3 = 2/3 ≈ 0.667
    assert result.details["avg_variance"] > 0.0


async def test_per_tool_breakdown_in_details() -> None:
    """details['per_tool'] maps each tool name to its 0-100 score."""
    client = _make_error_client(GOOD_ERROR)
    provider = MockProvider(responses=["7"])
    result = await score_error_legibility([ECHO_TOOL], client, provider)
    assert "per_tool" in result.details
    assert "echo" in result.details["per_tool"]
    assert 0 <= result.details["per_tool"]["echo"] <= 100


async def test_fix_hints_present_for_low_scoring_tool() -> None:
    """A tool with score < 6/10 should appear in fix_hints."""
    client = _make_error_client(BAD_ERROR)
    provider = MockProvider(responses=["3"])
    result = await score_error_legibility([ECHO_TOOL], client, provider)
    assert len(result.fix_hints) > 0
    assert any("echo" in hint for hint in result.fix_hints)


async def test_no_fix_hints_for_high_scoring_tool() -> None:
    """A tool with score ≥ 6/10 should not generate a fix hint."""
    client = _make_error_client(GOOD_ERROR)
    provider = MockProvider(responses=["9"])
    result = await score_error_legibility([ECHO_TOOL], client, provider)
    assert result.fix_hints == []


async def test_score_error_legibility_single_trial() -> None:
    """Runs correctly with trials=1 (the score_all default path)."""
    client = _make_error_client(GOOD_ERROR)
    provider = MockProvider(responses=["8"])
    result = await score_error_legibility([ECHO_TOOL], client, provider, trials=1)
    assert result.score > 0
    assert result.details["judge_trials"] == 1
