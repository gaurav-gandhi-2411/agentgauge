"""Tests for agentgauge.provider_compat (Gemini/Vertex function-calling schema lint).

All schemas are hand-written synthetic fixtures; no third-party catalog text, no network.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agentgauge.linter import Severity, lint_tool_set
from agentgauge.provider_compat import (
    MAX_FUNCTION_NAME_LEN,
    MAX_SCHEMA_DEPTH,
    RECOMMENDED_MAX_TOOLS,
    check_function_name,
    check_refs,
    check_schema_depth,
    lint_provider_compat,
    measure_catalog,
    schema_depth,
)


def _tool(name: str = "get_item", schema: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description="Fetch an item by id.",
        inputSchema=schema or {"type": "object", "properties": {"id": {"type": "string"}}},
    )


def _nested(levels: int) -> dict[str, Any]:
    """Schema whose depth (root = 1) is exactly `levels`."""
    schema: dict[str, Any] = {"type": "string"}
    for _ in range(levels - 1):
        schema = {"type": "object", "properties": {"x": schema}}
    return schema


class TestToolName:
    def test_length_boundary(self) -> None:
        assert check_function_name("a" * MAX_FUNCTION_NAME_LEN) == []
        found = check_function_name("a" * (MAX_FUNCTION_NAME_LEN + 1))
        assert [v.check for v in found] == ["provider_compat_tool_name"]
        assert found[0].severity == Severity.ADVISORY
        assert "65 characters" in found[0].detail

    def test_character_set(self) -> None:
        for ok in ("_private", "get-item.v2", "A1_b"):
            assert check_function_name(ok) == []
        for bad in ("1abc", "has space", "slash/name", "-lead"):
            found = check_function_name(bad)
            assert len(found) == 1, bad
            assert "character set" in found[0].detail

    def test_message_names_provider_and_url(self) -> None:
        detail = check_function_name("bad name")[0].detail
        assert "Gemini/Vertex function calling" in detail
        assert "https://docs.cloud.google.com/vertex-ai/" in detail


class TestDepth:
    def test_depth_measurement(self) -> None:
        assert schema_depth({"type": "string"}) == 1
        assert schema_depth(_nested(5)) == 5

    def test_boundary_32_vs_33(self) -> None:
        assert check_schema_depth("t", _nested(MAX_SCHEMA_DEPTH)) == []
        found = check_schema_depth("t", _nested(MAX_SCHEMA_DEPTH + 1))
        assert [v.check for v in found] == ["provider_compat_schema_depth"]
        assert found[0].severity == Severity.ADVISORY
        assert "33 levels" in found[0].detail

    def test_depth_follows_items_and_anyof(self) -> None:
        schema = {"type": "array", "items": {"anyOf": [{"type": "string"}, _nested(3)]}}
        assert schema_depth(schema) == 1 + 1 + 3

    def test_enum_values_are_not_walked(self) -> None:
        schema = {"type": "string", "enum": [{"properties": {"a": {}}}]}
        assert schema_depth(schema) == 1


class TestRefs:
    def test_direct_defs_child_is_clean(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"$ref": "#/$defs/Name"}, "b": {"$ref": "#/definitions/Name"}},
            "$defs": {"Name": {"type": "string"}},
        }
        assert check_refs("t", schema) == []

    def test_external_and_non_defs_refs_flagged(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "a": {"$ref": "https://example.test/schema.json"},
                "b": {"$ref": "#/properties/a"},
                "c": {"$ref": "#/$defs/Name/properties/x"},
            },
        }
        found = check_refs("t", schema)
        assert len(found) == 3
        assert {v.check for v in found} == {"provider_compat_ref"}
        assert all(v.severity == Severity.ADVISORY for v in found)
        # Wording must not claim the docs prove rejection of $ref itself.
        assert all("may need rewriting" in v.detail for v in found)


class TestCatalogSize:
    def test_clean_schema_has_no_findings(self) -> None:
        assert lint_provider_compat([_tool()]) == []

    def test_validation_keywords_yield_info_with_measured_figures(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
                "n": {"type": "integer", "minimum": 0, "maximum": 9},
            },
        }
        found = lint_provider_compat([_tool(schema=schema)])
        assert [v.check for v in found] == ["provider_compat_schema_size"]
        v = found[0]
        assert v.severity == Severity.INFO
        assert "3 validation-only keywords" in v.detail
        assert "maxItems=1, maximum=1, minimum=1" in v.detail
        assert "no threshold is published" in v.detail
        assert "https://ai.google.dev/gemini-api/docs/function-calling" in v.detail

    def test_property_named_like_a_keyword_is_not_counted(self) -> None:
        schema = {
            "type": "object",
            "properties": {"pattern": {"type": "string"}, "format": {"type": "string"}},
        }
        n_props, counts = measure_catalog([_tool(schema=schema)])
        assert (n_props, counts) == (2, {})


class TestToolCount:
    def test_boundary_20_vs_21(self) -> None:
        at_limit = [_tool(f"tool_{i}") for i in range(RECOMMENDED_MAX_TOOLS)]
        assert lint_provider_compat(at_limit) == []
        found = lint_provider_compat([*at_limit, _tool("tool_extra")])
        assert [v.check for v in found] == ["provider_compat_tool_count"]
        assert found[0].severity == Severity.INFO
        assert "21 tools" in found[0].detail


class TestIntegration:
    def test_default_lint_report_is_unchanged(self) -> None:
        report = lint_tool_set([_tool("bad name")])
        assert report.provider_compat_violations == []
        assert not any(v.check.startswith("provider_compat") for v in report.advisory + report.info)

    def test_opt_in_findings_are_non_gating(self) -> None:
        tools = [_tool("bad name", {"type": "object", "properties": {"n": {"maximum": 3}}})]
        report = lint_tool_set(tools)
        before = (report.n_blocking, report.flagged)
        report.provider_compat_violations = lint_provider_compat(tools)
        assert report.n_advisory >= 1 and report.n_info >= 1
        assert (report.n_blocking, report.flagged) == before == (0, False)

    def test_deterministic(self) -> None:
        tools = [
            _tool("bad name", _nested(33)),
            _tool("ok", {"type": "object", "properties": {"n": {"minimum": 1}}}),
        ]
        first = lint_provider_compat(tools)
        assert first and first == lint_provider_compat(tools)
