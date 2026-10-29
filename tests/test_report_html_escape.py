from __future__ import annotations

from agentgauge.report import render_html
from agentgauge.scorer import DimensionScore, ScoredReport


def test_render_html_escapes_hint_and_dimension_name() -> None:
    """Server-derived fix hints (tool names, descriptions) must not inject markup."""
    dim = DimensionScore(name="<b>dim</b>", score=40.0, fix_hints=["<script>alert(1)</script>"])
    page = render_html(ScoredReport(overall=40.0, dimensions=[dim], tool_count=1))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<b>dim</b>" not in page
    assert "&lt;b&gt;dim&lt;/b&gt;" in page
