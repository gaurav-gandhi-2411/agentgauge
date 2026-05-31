from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool

from agentgauge.client import MCPClient, ToolCallResult
from agentgauge.scorer import _robustness_probes, score_robustness

ECHO_TOOL = Tool(
    name="echo",
    description="Echo a message",
    inputSchema={
        "type": "object",
        "properties": {"message": {"type": "string", "description": "Text to echo"}},
        "required": ["message"],
    },
)

NO_REQUIRED_TOOL = Tool(
    name="ping",
    description="Ping the server",
    inputSchema={"type": "object", "properties": {}},
)

MULTI_PARAM_TOOL = Tool(
    name="add",
    description="Add two numbers",
    inputSchema={
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "First number"},
            "b": {"type": "integer", "description": "Second number"},
        },
        "required": ["a", "b"],
    },
)


# ── Mock client factories ────────────────────────────────────────────────────


def _graceful_client() -> MCPClient:
    """call_tool always returns success=False — graceful rejection of bad input."""
    session = MagicMock()
    client = MCPClient(session)
    client.call_tool = AsyncMock(  # type: ignore[method-assign]
        return_value=ToolCallResult(success=False, content=[], error="validation error")
    )
    return client


def _crash_client() -> MCPClient:
    """call_tool always raises — simulates a server with unhandled error paths."""
    session = MagicMock()
    client = MCPClient(session)
    client.call_tool = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("server crashed")
    )
    return client


def _silent_accept_client() -> MCPClient:
    """call_tool always returns success=True — server accepts malformed input silently."""
    session = MagicMock()
    client = MCPClient(session)
    client.call_tool = AsyncMock(  # type: ignore[method-assign]
        return_value=ToolCallResult(success=True, content=[], error=None)
    )
    return client


def _mixed_crash_graceful_client() -> MCPClient:
    """call_tool alternates: odd calls are graceful rejections, even calls crash."""
    session = MagicMock()
    client = MCPClient(session)
    call_count = 0

    async def _alternating(*args: object, **kwargs: object) -> ToolCallResult:
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 0:
            raise RuntimeError("crash")
        return ToolCallResult(success=False, content=[], error="validation error")

    client.call_tool = _alternating  # type: ignore[method-assign]
    return client


def _mixed_silent_graceful_client() -> MCPClient:
    """call_tool alternates: odd calls are graceful rejections, even calls silent-accept."""
    session = MagicMock()
    client = MCPClient(session)
    call_count = 0

    async def _alternating(*args: object, **kwargs: object) -> ToolCallResult:
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 0:
            return ToolCallResult(success=True, content=[], error=None)
        return ToolCallResult(success=False, content=[], error="validation error")

    client.call_tool = _alternating  # type: ignore[method-assign]
    return client


# ── _robustness_probes ───────────────────────────────────────────────────────


def test_robustness_probes_required_tool_yields_three() -> None:
    probes = _robustness_probes(ECHO_TOOL)
    assert len(probes) >= 3


def test_robustness_probes_includes_null_value() -> None:
    labels = [p.label for p in _robustness_probes(ECHO_TOOL)]
    assert any("null" in lbl for lbl in labels)


def test_robustness_probes_includes_extra_fields() -> None:
    labels = [p.label for p in _robustness_probes(ECHO_TOOL)]
    assert any("extra" in lbl for lbl in labels)


def test_robustness_probes_includes_wrong_type_for_required_param() -> None:
    labels = [p.label for p in _robustness_probes(ECHO_TOOL)]
    assert any("wrong_type" in lbl for lbl in labels)


def test_robustness_probes_wrong_type_uses_non_string_for_string_param() -> None:
    probes = _robustness_probes(ECHO_TOOL)
    wt = next(p for p in probes if "wrong_type" in p.label)
    assert not isinstance(wt.args.get("message"), str)


def test_robustness_probes_no_required_still_yields_three() -> None:
    probes = _robustness_probes(NO_REQUIRED_TOOL)
    assert len(probes) >= 3


def test_robustness_probes_null_value_passes_none() -> None:
    probes = _robustness_probes(ECHO_TOOL)
    null_probe = next(p for p in probes if p.label == "null_value")
    assert None in null_probe.args.values()


def test_robustness_probes_extra_fields_injects_unknown_key() -> None:
    probes = _robustness_probes(ECHO_TOOL)
    extra_probe = next(p for p in probes if p.label == "extra_fields")
    assert "__unknown_field__" in extra_probe.args


# ── score_robustness — boundary cases ───────────────────────────────────────


async def test_score_robustness_no_tools() -> None:
    result = await score_robustness([], _graceful_client())
    assert result.score == 0.0
    assert result.name == "robustness"
    assert result.details.get("reason") == "no tools"


async def test_score_robustness_all_graceful_scores_100() -> None:
    """Server that properly rejects bad input → 100/100."""
    result = await score_robustness([ECHO_TOOL], _graceful_client())
    assert result.score == 100.0
    assert result.fix_hints == []


async def test_score_robustness_all_crashes_scores_0() -> None:
    """Server with unhandled error paths → 0/100."""
    result = await score_robustness([ECHO_TOOL], _crash_client())
    assert result.score == 0.0


async def test_score_robustness_all_silent_accepts_scores_0() -> None:
    """Server that silently accepts malformed input → 0/100.

    This is the key semantics regression-lock: a server that never raises but
    also never validates MUST score the same as one that crashes, not the same
    as one that properly rejects.
    """
    result = await score_robustness([ECHO_TOOL], _silent_accept_client())
    assert result.score == 0.0


# ── score_robustness — discrimination ────────────────────────────────────────


async def test_graceful_scores_materially_above_silent_accept() -> None:
    """Core regression lock: graceful rejection MUST outscore silent accept by a real margin.

    Both clients receive the same probes. The graceful client explicitly rejects bad input;
    the silent-accept client lets it through without complaint. This test fails if the
    two outcomes are treated equivalently — which was the original bug.
    """
    graceful = await score_robustness([ECHO_TOOL], _graceful_client())
    silent = await score_robustness([ECHO_TOOL], _silent_accept_client())

    gap = graceful.score - silent.score
    assert gap >= 80, (
        f"Graceful ({graceful.score}) should outscore silent-accept ({silent.score}) "
        f"by >= 80 pts, got {gap:.1f}"
    )


async def test_graceful_scores_materially_above_crash() -> None:
    """Graceful rejection must also outscore crashes by a real margin."""
    graceful = await score_robustness([ECHO_TOOL], _graceful_client())
    crashed = await score_robustness([ECHO_TOOL], _crash_client())

    gap = graceful.score - crashed.score
    assert gap >= 80, (
        f"Graceful ({graceful.score}) should outscore crash ({crashed.score}) "
        f"by >= 80 pts, got {gap:.1f}"
    )


async def test_score_robustness_partial_crashes_intermediate_score() -> None:
    result = await score_robustness([ECHO_TOOL], _mixed_crash_graceful_client())
    assert 0.0 < result.score < 100.0


async def test_score_robustness_partial_silent_accepts_intermediate_score() -> None:
    result = await score_robustness([ECHO_TOOL], _mixed_silent_graceful_client())
    assert 0.0 < result.score < 100.0


# ── score_robustness — details ───────────────────────────────────────────────


async def test_score_robustness_details_total_probes_at_least_3() -> None:
    result = await score_robustness([ECHO_TOOL], _graceful_client())
    assert result.details["total_probes"] >= 3


async def test_score_robustness_details_graceful_equals_total_when_clean() -> None:
    result = await score_robustness([ECHO_TOOL], _graceful_client())
    assert result.details["graceful_rejections"] == result.details["total_probes"]
    assert result.details["silent_accepts"] == 0
    assert result.details["crashes"] == 0


async def test_score_robustness_details_silent_accepts_counted() -> None:
    result = await score_robustness([ECHO_TOOL], _silent_accept_client())
    assert result.details["silent_accepts"] == result.details["total_probes"]
    assert result.details["graceful_rejections"] == 0
    assert result.details["crashes"] == 0


async def test_score_robustness_details_crashes_counted() -> None:
    result = await score_robustness([ECHO_TOOL], _crash_client())
    assert result.details["crashes"] == result.details["total_probes"]
    assert result.details["graceful_rejections"] == 0
    assert result.details["silent_accepts"] == 0


async def test_score_robustness_details_per_tool_present() -> None:
    result = await score_robustness([ECHO_TOOL], _graceful_client())
    assert "per_tool" in result.details
    assert "echo" in result.details["per_tool"]
    info = result.details["per_tool"]["echo"]
    assert "graceful_rejections" in info
    assert "crashes" in info
    assert "silent_accepts" in info
    assert "total" in info
    assert "score" in info


# ── score_robustness — fix hints ─────────────────────────────────────────────


async def test_score_robustness_fix_hint_on_crash_names_tool() -> None:
    result = await score_robustness([ECHO_TOOL], _crash_client())
    assert len(result.fix_hints) > 0
    assert any("echo" in hint for hint in result.fix_hints)


async def test_score_robustness_fix_hint_on_silent_accept_names_tool() -> None:
    """Silent accept must produce a distinct, actionable fix hint."""
    result = await score_robustness([ECHO_TOOL], _silent_accept_client())
    assert len(result.fix_hints) > 0
    assert any("echo" in hint for hint in result.fix_hints)
    # The hint must mention silent acceptance, not crash
    combined = " ".join(result.fix_hints)
    assert "silently accepted" in combined or "silent" in combined


async def test_score_robustness_no_fix_hints_when_all_graceful() -> None:
    result = await score_robustness([ECHO_TOOL], _graceful_client())
    assert result.fix_hints == []


# ── score_robustness — multiple tools ────────────────────────────────────────


async def test_score_robustness_multiple_tools() -> None:
    result = await score_robustness([ECHO_TOOL, MULTI_PARAM_TOOL], _graceful_client())
    assert result.score == 100.0
    assert "echo" in result.details["per_tool"]
    assert "add" in result.details["per_tool"]
    assert result.details["total_probes"] >= 6  # at least 3 per tool
