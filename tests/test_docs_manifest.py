from __future__ import annotations

import httpx
import respx
from mcp.types import Tool

from agentgauge.client import fetch_llms_txt
from agentgauge.providers import MockProvider
from agentgauge.scorer import DOCS_MANIFEST_FLOOR, score_all, score_docs_manifest

# ── Tool fixture ──────────────────────────────────────────────────────────────

ECHO_TOOL = Tool(
    name="echo",
    description="Echo a message back",
    inputSchema={
        "type": "object",
        "properties": {"message": {"type": "string", "description": "Text to echo"}},
        "required": ["message"],
    },
)

# ── llms.txt content fixtures ─────────────────────────────────────────────────

GOOD_DOC = """\
# My MCP Server

This server provides tools for data manipulation by AI agents.

## Tools

### echo
Echoes any text back to the caller unchanged.
Parameters:
  - message (string, required): The text to echo.
Use when: you want to verify server connectivity or test round-trip latency.
"""

POOR_DOC = "# Tools\n- echo\n"

# ── fetch_llms_txt ────────────────────────────────────────────────────────────


async def test_fetch_llms_txt_none_base_url_returns_none() -> None:
    result = await fetch_llms_txt(None)
    assert result is None


async def test_fetch_llms_txt_404_returns_none() -> None:
    with respx.mock:
        respx.get("http://example.com/llms.txt").mock(return_value=httpx.Response(404))
        result = await fetch_llms_txt("http://example.com")
    assert result is None


async def test_fetch_llms_txt_200_returns_text() -> None:
    with respx.mock:
        respx.get("http://example.com/llms.txt").mock(
            return_value=httpx.Response(200, text=GOOD_DOC)
        )
        result = await fetch_llms_txt("http://example.com")
    assert result == GOOD_DOC


async def test_fetch_llms_txt_trailing_slash_stripped() -> None:
    with respx.mock:
        respx.get("http://example.com/llms.txt").mock(return_value=httpx.Response(200, text="ok"))
        result = await fetch_llms_txt("http://example.com/")
    assert result == "ok"


async def test_fetch_llms_txt_connection_error_returns_none() -> None:
    with respx.mock:
        respx.get("http://example.com/llms.txt").mock(side_effect=httpx.ConnectError("refused"))
        result = await fetch_llms_txt("http://example.com")
    assert result is None


async def test_fetch_llms_txt_follows_301_redirect() -> None:
    """Regression: the pre-fix code (no follow_redirects) returned None on a 301.

    Without follow_redirects=True, sites like docs.anthropic.com silently floor at 20.0
    even though 160k+ chars of real content are available at the redirected URL.
    This test fails against the old code and passes with the fix.
    """
    redirected_body = "# Redirected Server\n\nTools: echo, add\n"
    with respx.mock:
        respx.get("http://example.com/llms.txt").mock(
            return_value=httpx.Response(
                301, headers={"location": "http://cdn.example.com/llms.txt"}
            )
        )
        respx.get("http://cdn.example.com/llms.txt").mock(
            return_value=httpx.Response(200, text=redirected_body)
        )
        result = await fetch_llms_txt("http://example.com")
    assert result == redirected_body


# ── score_docs_manifest — absent path ─────────────────────────────────────────


async def test_absent_returns_floor_score() -> None:
    result = await score_docs_manifest([ECHO_TOOL], None, MockProvider())
    assert result.score == DOCS_MANIFEST_FLOOR
    assert result.score == 20.0


async def test_absent_name_is_docs_manifest() -> None:
    result = await score_docs_manifest([ECHO_TOOL], None, MockProvider())
    assert result.name == "docs_manifest"


async def test_absent_fix_hint_mentions_llms_txt() -> None:
    result = await score_docs_manifest([ECHO_TOOL], None, MockProvider())
    assert len(result.fix_hints) > 0
    assert any("llms.txt" in hint for hint in result.fix_hints)


async def test_absent_details_status_is_absent() -> None:
    result = await score_docs_manifest([ECHO_TOOL], None, MockProvider())
    assert result.details.get("status") == "absent"


# ── score_docs_manifest — present paths ──────────────────────────────────────


async def test_good_doc_judge_9_scores_above_80() -> None:
    # judge=9 → score = 20 + (9/10)*80 = 92.0
    result = await score_docs_manifest(
        [ECHO_TOOL], GOOD_DOC, MockProvider(responses=["9"]), trials=3
    )
    assert result.score >= 80.0


async def test_poor_doc_judge_2_scores_above_floor_below_good() -> None:
    # judge=2 → score = 20 + (2/10)*80 = 36.0
    result = await score_docs_manifest(
        [ECHO_TOOL], POOR_DOC, MockProvider(responses=["2"]), trials=3
    )
    assert result.score >= DOCS_MANIFEST_FLOOR
    assert result.score < 50.0


async def test_good_doc_beats_poor_doc_by_at_least_40_points() -> None:
    # judge=9 → 92.0; judge=2 → 36.0; gap = 56.0
    good = await score_docs_manifest([ECHO_TOOL], GOOD_DOC, MockProvider(responses=["9"]), trials=1)
    poor = await score_docs_manifest([ECHO_TOOL], POOR_DOC, MockProvider(responses=["2"]), trials=1)
    gap = good.score - poor.score
    assert gap >= 40.0, (
        f"good ({good.score}) should beat poor ({poor.score}) by ≥ 40 pts; gap={gap:.1f}"
    )


async def test_present_doc_details_has_judge_fields() -> None:
    result = await score_docs_manifest(
        [ECHO_TOOL], GOOD_DOC, MockProvider(responses=["8", "7", "9"]), trials=3
    )
    assert "judge_score_mean" in result.details
    assert "judge_trials" in result.details
    assert "avg_variance" in result.details
    assert result.details["judge_trials"] == 3


async def test_present_poor_doc_has_fix_hint() -> None:
    result = await score_docs_manifest(
        [ECHO_TOOL], POOR_DOC, MockProvider(responses=["2"]), trials=1
    )
    assert len(result.fix_hints) > 0


async def test_present_good_doc_no_fix_hint() -> None:
    result = await score_docs_manifest(
        [ECHO_TOOL], GOOD_DOC, MockProvider(responses=["9"]), trials=1
    )
    assert result.fix_hints == []


# ── stdio treated as absent ───────────────────────────────────────────────────


async def test_stdio_no_base_url_scores_floor() -> None:
    # Simulate stdio: caller passes fetched_doc=None because fetch_llms_txt(None) → None
    result = await score_docs_manifest([ECHO_TOOL], None, MockProvider(responses=["9"]))
    assert result.score == DOCS_MANIFEST_FLOOR


# ── score_all integration ─────────────────────────────────────────────────────


async def test_score_all_includes_docs_manifest_not_stub() -> None:
    # base_url=None → fetch returns None → absent → score=20.0 (not a stub)
    report = await score_all([ECHO_TOOL], MockProvider(responses=["7"]), base_url=None)
    names = [d.name for d in report.dimensions]
    assert "docs_manifest" in names
    docs_dim = next(d for d in report.dimensions if d.name == "docs_manifest")
    assert docs_dim.details.get("status") != "not_implemented"


async def test_score_all_docs_manifest_absent_is_floor() -> None:
    report = await score_all([ECHO_TOOL], MockProvider(responses=["7"]), base_url=None)
    docs_dim = next(d for d in report.dimensions if d.name == "docs_manifest")
    assert docs_dim.score == 20.0


async def test_score_all_docs_manifest_weight_is_2pct() -> None:
    from agentgauge.scorer import DIMENSION_WEIGHTS

    assert DIMENSION_WEIGHTS.get("docs_manifest") == 0.02
