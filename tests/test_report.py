from __future__ import annotations

import json

from agentgauge.report import render_html, render_json
from agentgauge.scorer import DimensionScore, ScoredReport


def _sample_report() -> ScoredReport:
    return ScoredReport(
        overall=72.5,
        tool_count=2,
        dimensions=[
            DimensionScore(name="schema_completeness", score=80.0, details={}, fix_hints=[]),
            DimensionScore(
                name="description_quality",
                score=65.0,
                details={},
                fix_hints=["Improve tool X"],
            ),
        ],
    )


def test_render_json_parses() -> None:
    report = _sample_report()
    text = render_json(report)
    data = json.loads(text)
    assert data["overall"] == 72.5
    assert data["tool_count"] == 2
    assert len(data["dimensions"]) == 2


def test_render_html_contains_score() -> None:
    report = _sample_report()
    html = render_html(report)
    assert "72.5" in html
    assert "<html" in html.lower()
