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


def _structured_client() -> MCPClient:
    """call_tool always returns a structured error (no exception)."""
    session = MagicMock()
    client = MCPClient(session)
    client.call_tool = AsyncMock(  # type: ignore[method-assign]
        return_value=ToolCallResult(success=False, content=[], error="validation error")
    )
    return client


def _crash_client() -> MCPClient:
    """call_tool always raises (simulates server crash)."""
    session = MagicMock()
    client = MCPClient(session)
    client.call_tool = AsyncMock(side_effect=RuntimeError("server crashed"))  # type: ignore[method-assign]
    return client


def _mixed_client() -> MCPClient:
    """call_tool alternates: odd calls return structured error, even calls raise."""
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


# _robustness_probes


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


# score_robustness


async def test_score_robustness_no_tools() -> None:
    result = await score_robustness([], _structured_client())
    assert result.score == 0.0
    assert result.name == "robustness"
    assert result.details.get("reason") == "no tools"


async def test_score_robustness_all_structured_errors_scores_100() -> None:
    result = await score_robustness([ECHO_TOOL], _structured_client())
    assert result.score == 100.0
    assert result.name == "robustness"
    assert result.fix_hints == []


async def test_score_robustness_all_crashes_scores_0() -> None:
    result = await score_robustness([ECHO_TOOL], _crash_client())
    assert result.score == 0.0


async def test_score_robustness_partial_crashes_intermediate_score() -> None:
    result = await score_robustness([ECHO_TOOL], _mixed_client())
    assert 0.0 < result.score < 100.0


async def test_score_robustness_details_total_probes_at_least_3() -> None:
    result = await score_robustness([ECHO_TOOL], _structured_client())
    assert result.details["total_probes"] >= 3


async def test_score_robustness_details_structured_errors_equals_total_when_clean() -> None:
    result = await score_robustness([ECHO_TOOL], _structured_client())
    assert result.details["structured_errors"] == result.details["total_probes"]


async def test_score_robustness_details_per_tool_present() -> None:
    result = await score_robustness([ECHO_TOOL], _structured_client())
    assert "per_tool" in result.details
    assert "echo" in result.details["per_tool"]
    info = result.details["per_tool"]["echo"]
    assert "structured" in info and "total" in info and "score" in info


async def test_score_robustness_fix_hints_on_crash() -> None:
    result = await score_robustness([ECHO_TOOL], _crash_client())
    assert len(result.fix_hints) > 0
    assert any("echo" in hint for hint in result.fix_hints)


async def test_score_robustness_no_fix_hints_when_all_structured() -> None:
    result = await score_robustness([ECHO_TOOL], _structured_client())
    assert result.fix_hints == []


async def test_score_robustness_multiple_tools() -> None:
    result = await score_robustness([ECHO_TOOL, MULTI_PARAM_TOOL], _structured_client())
    assert result.score == 100.0
    assert "echo" in result.details["per_tool"]
    assert "add" in result.details["per_tool"]
    assert result.details["total_probes"] >= 6  # at least 3 per tool
