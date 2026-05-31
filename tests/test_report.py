from __future__ import annotations

import json

from agentgauge.report import render_html, render_json, render_json_stable
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


def test_render_json_stable_schema() -> None:
    report = ScoredReport(
        overall=72.5,
        tool_count=2,
        dimensions=[
            DimensionScore(name="schema_completeness", score=80.0, details={}, fix_hints=[]),
            DimensionScore(name="description_quality", score=65.0, details={}, fix_hints=[]),
            DimensionScore(name="discoverability", score=70.0, details={}, fix_hints=[]),
            DimensionScore(name="selection_accuracy", score=75.0, details={}, fix_hints=[]),
            DimensionScore(name="call_correctness", score=60.0, details={}, fix_hints=[]),
            DimensionScore(name="error_legibility", score=55.0, details={}, fix_hints=[]),
            DimensionScore(name="robustness", score=50.0, details={}, fix_hints=[]),
            DimensionScore(name="docs_manifest", score=45.0, details={}, fix_hints=[]),
        ],
    )
    text = render_json_stable(report)
    data = json.loads(text)

    assert set(data.keys()) == {"schema_version", "overall_score", "dimensions"}
    assert data["schema_version"] == "1.0"
    assert data["overall_score"] == 72.5

    dimension_names = {d["name"] for d in data["dimensions"]}
    expected_names = {
        "schema_completeness",
        "description_quality",
        "discoverability",
        "selection_accuracy",
        "call_correctness",
        "error_legibility",
        "robustness",
        "docs_manifest",
    }
    assert dimension_names == expected_names
