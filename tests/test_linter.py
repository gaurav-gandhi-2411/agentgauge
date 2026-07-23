"""Tests for agentgauge.linter (v2 deterministic schema-consistency + collision linter).

Includes regression tests for the two false-positive bugs found by hand
spot-check during the predictive-validity study (documented in
reports/predictive_validity_study.md's "Schema-consistency checker" section):
  1. type_enum_contradiction firing on the bare word "no" (e.g. "no pagination").
  2. described_not_in_schema firing on return-value field names documented in a
     Returns:/Output: section, mistaken for missing input parameters.
"""

from __future__ import annotations

from agentgauge.linter import (
    Severity,
    check_name_collisions,
    lint_tool,
    lint_tool_set,
)


class TestNegationRegressionBug:
    """Regression test: 'no pagination' must NOT trigger type_enum_contradiction.

    This is the exact false positive found in confusable_server_oracle's
    `enumerate_all` tool during the predictive-validity study.
    """

    def test_no_pagination_does_not_false_positive(self) -> None:
        description = (
            "Returns the complete set of all items in a collection with no "
            "pagination. Use only when you need every item at once."
        )
        schema = {"type": "object", "properties": {"collection": {"type": "string"}}, "required": ["collection"]}
        result = lint_tool("enumerate_all", description, schema)
        contradictions = [v for v in result.all if v.check == "type_enum_contradiction"]
        assert contradictions == []

    def test_genuine_boolean_phrase_still_detected(self) -> None:
        description = "Set to true/false whether the collection should be cached."
        schema = {"type": "object", "properties": {"collection": {"type": "string"}}, "required": []}
        result = lint_tool("cache_tool", description, schema)
        contradictions = [v for v in result.all if v.check == "type_enum_contradiction"]
        assert len(contradictions) == 1
        assert "collection" in contradictions[0].detail

    def test_boolean_word_far_from_param_mention_does_not_fire(self) -> None:
        # "boolean" appears, but nowhere near the only non-boolean-typed param's mention.
        description = (
            "This tool handles boolean logic operations internally. "
            "The session identifier must be provided."
        )
        schema = {"type": "object", "properties": {"session": {"type": "string"}}, "required": ["session"]}
        result = lint_tool("logic_tool", description, schema)
        contradictions = [v for v in result.all if v.check == "type_enum_contradiction"]
        assert contradictions == []


class TestInputOutputSectionRegressionBug:
    """Regression test: return-value field names documented in a Returns:
    section must NOT be flagged as missing input parameters.

    This is the exact false positive found in
    exp1_stickerdaniel_linkedin_mcp_server_mirror's `get_company_profile` tool.
    """

    def test_return_value_fields_not_flagged_as_missing_params(self) -> None:
        description = (
            "Get a specific company's LinkedIn profile.\n\n"
            "Args:\n"
            "    company_name: LinkedIn company name\n\n"
            "Returns:\n"
            "    Dict with url, sections, and optional references.\n"
            "    Includes unknown_sections list when unrecognised names are passed.\n"
            "    May include a company_urn value in references."
        )
        schema = {
            "type": "object",
            "properties": {"company_name": {"type": "string"}, "sections": {"type": "string"}},
            "required": ["company_name"],
        }
        result = lint_tool("get_company_profile", description, schema)
        flagged_tokens = {
            v.detail for v in result.all if v.check == "described_not_in_schema"
        }
        assert not any("unknown_sections" in d for d in flagged_tokens)
        assert not any("company_urn" in d for d in flagged_tokens)

    def test_inline_returns_sentence_not_flagged_as_missing_param(self) -> None:
        # Found on p2a_arm_oracle's retrieve_order: "Returns" as a mid-paragraph
        # verb, no formal "Returns:" section header at all.
        description = (
            "Returns the order with discount and tax calculations applied: "
            "subtotal, discount_amount, tax_amount, and final_total. "
            "Use when you need the computed final price, not raw field values."
        )
        schema = {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}
        result = lint_tool("retrieve_order", description, schema)
        flagged = {v.detail for v in result.all if v.check == "described_not_in_schema"}
        assert not any("discount_amount" in d for d in flagged)
        assert not any("final_total" in d for d in flagged)
        assert not any("tax_amount" in d for d in flagged)

    def test_genuine_input_param_confusion_still_detected_before_returns_section(self) -> None:
        description = (
            "Look up a record by its record_key.\n\n"
            "Returns:\n"
            "    The matching record."
        )
        schema = {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}
        result = lint_tool("lookup", description, schema)
        flagged_tokens = {v.detail for v in result.all if v.check == "described_not_in_schema"}
        assert any("record_key" in d for d in flagged_tokens)


class TestExamplesSectionRegressionBug:
    """Regression test: identifiers inside an Examples: section's illustrative
    string values must not be flagged as missing parameters. Exact false
    positive found on exp1_dataojitori_nocturne_memory_mirror's create_memory
    (example URI 'core://my_user/survival_state')."""

    def test_example_uri_content_not_flagged(self) -> None:
        description = (
            "Creates a new memory under a parent URI.\n\n"
            "Args:\n    parent_uri: The existing node to create this memory under.\n\n"
            "Examples:\n"
            '    create_memory("core://my_user/survival_state", "content", priority=2)\n'
        )
        schema = {"type": "object", "properties": {"parent_uri": {"type": "string"}}, "required": ["parent_uri"]}
        result = lint_tool("create_memory", description, schema)
        flagged = {v.detail for v in result.all if v.check == "described_not_in_schema"}
        assert not any("survival_state" in d for d in flagged)
        assert not any("my_user" in d for d in flagged)


class TestSiblingToolNameRegressionBug:
    """Regression test: a description referencing ANOTHER tool by name (workflow
    guidance, e.g. "use `watch_topic` before calling this") must not be flagged
    as a missing parameter. Exact false positive found on
    exp1_blazickjp_arxiv_mcp_server_mirror's check_alerts/get_abstract/etc.
    """

    def test_sibling_tool_name_not_flagged_as_missing_param(self) -> None:
        description = "Use watch_topic to register topics before calling this."
        schema = {"type": "object", "properties": {}, "required": []}
        result = lint_tool("check_alerts", description, schema, sibling_tool_names=frozenset({"watch_topic"}))
        flagged = {v.detail for v in result.all if v.check == "described_not_in_schema"}
        assert not any("watch_topic" in d for d in flagged)

    def test_lint_tool_set_excludes_sibling_names_automatically(self) -> None:
        class _T:
            def __init__(self, name: str, description: str, inputSchema: dict) -> None:
                self.name = name
                self.description = description
                self.inputSchema = inputSchema

        tools = [
            _T("check_alerts", "Use watch_topic to register topics first.", {"type": "object", "properties": {}}),
            _T("watch_topic", "Register a topic watch.", {"type": "object", "properties": {}}),
        ]
        report = lint_tool_set(tools)
        flagged = {v.detail for v in report.high if v.check == "described_not_in_schema"}
        assert not any("watch_topic" in d for d in flagged)

    def test_genuine_missing_param_still_flagged_when_not_a_sibling_name(self) -> None:
        description = "Look up a record by its record_key."
        schema = {"type": "object", "properties": {}, "required": []}
        result = lint_tool("lookup", description, schema, sibling_tool_names=frozenset({"other_tool"}))
        flagged = {v.detail for v in result.all if v.check == "described_not_in_schema"}
        assert any("record_key" in d for d in flagged)


class TestRequiredReferencesMissingProperty:
    """The one fully-deterministic, schema-internal check -- ping_server's exact defect."""

    def test_required_references_nonexistent_property(self) -> None:
        description = "The ping_server tool checks server connectivity with no required parameters."
        schema = {"type": "object", "properties": {}, "required": ["host"]}
        result = lint_tool("ping_server", description, schema)
        e_violations = [v for v in result.all if v.check == "required_references_missing_property"]
        assert len(e_violations) == 1
        assert e_violations[0].severity == Severity.HIGH

    def test_no_false_positive_when_required_matches_properties(self) -> None:
        description = "Stores a value under a key."
        schema = {
            "type": "object",
            "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
            "required": ["key", "value"],
        }
        result = lint_tool("store", description, schema)
        e_violations = [v for v in result.all if v.check == "required_references_missing_property"]
        assert e_violations == []


class TestRequiredNotMentionedIsInfoSeverityOnly:
    """Demoted check must never appear in the HIGH severity list."""

    def test_required_not_mentioned_is_info_not_high(self) -> None:
        description = "Put."
        schema = {
            "type": "object",
            "properties": {"sid": {"type": "string"}, "key": {"type": "string"}},
            "required": ["sid", "key"],
        }
        result = lint_tool("put_x", description, schema)
        assert result.high == []
        assert len(result.info) == 2
        assert all(v.severity == Severity.INFO for v in result.info)
        assert all(v.check == "required_not_mentioned" for v in result.info)


class TestNameCollisions:
    """Extracted from v1's discoverability heuristic, per v2_axis_triage.md."""

    def test_near_duplicate_names_flagged(self) -> None:
        violations = check_name_collisions(["get_a", "get_b", "delete_record"])
        assert len(violations) == 1
        assert violations[0].check == "name_collision"
        assert violations[0].severity == Severity.HIGH

    def test_distinct_names_not_flagged(self) -> None:
        violations = check_name_collisions(["search_documents", "send_message", "create_record"])
        assert violations == []

    def test_identical_names_flagged(self) -> None:
        violations = check_name_collisions(["fetch_record", "fetch_record"])
        assert len(violations) == 1


class TestCleanToolNoFalsePositives:
    """A well-documented tool with fully consistent schema/description should
    produce zero HIGH-severity violations."""

    def test_fully_consistent_tool_is_clean(self) -> None:
        description = (
            "Attach a managed IAM policy to a user. Requires the user_name and "
            "the policy_arn to attach; set confirmed to true to proceed."
        )
        schema = {
            "type": "object",
            "properties": {
                "user_name": {"type": "string"},
                "policy_arn": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["user_name", "policy_arn", "confirmed"],
        }
        result = lint_tool("attach_user_policy", description, schema)
        assert result.high == []
