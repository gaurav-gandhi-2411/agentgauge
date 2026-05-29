from __future__ import annotations

from mcp.types import Tool

from agentgauge.providers import MockProvider
from agentgauge.scorer import (
    DimensionScore,
    score_all,
    score_description_quality,
    score_schema_completeness,
)


def _make_tool(name: str, description: str, schema: dict) -> Tool:
    return Tool(name=name, description=description, inputSchema=schema)


GOOD_TOOL = _make_tool(
    "echo",
    "Echo a message back",
    {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Text to echo"},
        },
        "required": ["message"],
    },
)

BAD_TOOL = _make_tool(
    "mystery",
    "",
    {"type": "object", "properties": {"x": {}, "y": {}}},
)


def test_schema_completeness_good_tool() -> None:
    result = score_schema_completeness([GOOD_TOOL])
    assert isinstance(result, DimensionScore)
    assert result.score > 80.0


def test_schema_completeness_bad_tool() -> None:
    result = score_schema_completeness([BAD_TOOL])
    assert result.score < 40.0
    assert len(result.fix_hints) > 0


def test_schema_completeness_no_tools() -> None:
    result = score_schema_completeness([])
    assert result.score == 0.0


async def test_description_quality_with_mock_provider() -> None:
    provider = MockProvider(responses=["8"])
    result = await score_description_quality([GOOD_TOOL], provider)
    assert isinstance(result, DimensionScore)
    assert result.score == 80.0  # 8/10 * 100


async def test_description_quality_no_tools() -> None:
    provider = MockProvider()
    result = await score_description_quality([], provider)
    assert result.score == 0.0


async def test_score_all_returns_report() -> None:
    provider = MockProvider(responses=["7"])
    report = await score_all([GOOD_TOOL, BAD_TOOL], provider)
    assert report.tool_count == 2
    assert 0 <= report.overall <= 100
    assert len(report.dimensions) == 8
