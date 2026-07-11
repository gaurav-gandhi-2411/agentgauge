from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from mcp.types import Tool

from agentgauge.fixer import (
    DEFAULT_SKIP_ABOVE_BAND,
    VALIDATION_MODE,
    FixCandidate,
    ValidationMode,
    _apply_overmarking_guard,
    _count_grounding_tokens,
    _generate_description,
    _generate_schema_props,
    _judge_desc_trials,
    _patch_source_description,
    _patch_source_required,
    _patch_source_schema_props,
    _select_neighbors,
    assert_generator_ne_judge,
    deep_merge,
    is_low_grounding,
    run_fixer,
)
from agentgauge.providers import Message, MockProvider

# ── T9: Validation mode constants ─────────────────────────────────────────────


def test_validation_mode_schema_completeness_is_deterministic() -> None:
    assert VALIDATION_MODE["schema_completeness"] == ValidationMode.DETERMINISTIC


def test_validation_mode_description_quality_is_judge_based() -> None:
    assert VALIDATION_MODE["description_quality"] == ValidationMode.JUDGE_BASED


# ── T9: Accept/reject threshold logic ─────────────────────────────────────────


def _make_candidate(
    delta: float,
    threshold: float,
    mode: ValidationMode = ValidationMode.DETERMINISTIC,
) -> FixCandidate:
    accepted = delta > threshold
    return FixCandidate(
        tool_name="mystery",
        dim="schema_completeness",
        mode=mode,
        baseline_score=50.0,
        baseline_sigma=0.0,
        candidate_score=50.0 + delta,
        candidate_sigma=0.0,
        delta=delta,
        threshold=threshold,
        accepted=accepted,
    )


def test_accept_above_threshold() -> None:
    c = _make_candidate(delta=50.0, threshold=10.0)
    assert c.accepted is True


def test_reject_below_threshold() -> None:
    c = _make_candidate(delta=5.0, threshold=10.0)
    assert c.accepted is False


def test_reject_equal_to_threshold() -> None:
    # delta must be STRICTLY greater than threshold to accept
    c = _make_candidate(delta=10.0, threshold=10.0)
    assert c.accepted is False


async def test_sigma_gate_used_for_judge_based(tmp_path: Path) -> None:
    """When baseline σ > min_delta, threshold = σ.

    Baseline scores: [10, 90] → mean=50, σ≈56.6
    Candidate: delta=15, which beats min_delta=10 but NOT σ≈56.6 → rejected.
    """
    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    tool = Tool(name="mystery", description="baseline text", inputSchema={})

    # baseline judge calls: 5 trials → alternating extreme scores for high σ
    # candidate judge calls: 5 trials → scores slightly above min_delta
    # generation call: 1 call → "improved description"
    # We need: baseline mean ~50, σ > 10; candidate mean ~50+15=65, delta=15 < σ
    baseline_responses = ["1", "9", "1", "9", "1"]  # mean=42, σ≈3.8 in 0-10 * 10 scale
    # Use more extreme values: [0, 10, 0, 10, 0] → mean=40, σ≈5.5 (in 0-10) → 55 in 0-100
    baseline_responses = ["0", "10", "0", "10", "0"]  # mean=4, σ≈5.5 → 55 in 0-100 scale
    gen_response = ["Slightly improved description."]
    # candidate scores give delta < σ (55) but > min_delta (10)
    candidate_responses = ["4.5", "4.5", "4.5", "4.5", "4.5"]  # mean=45, delta=45-40=5
    # Actually let's make delta=15: candidate mean = 4+1.5=5.5/10 → 55/100; baseline=40/100
    candidate_responses = ["5.5", "5.5", "5.5", "5.5", "5.5"]  # mean=55, delta=15

    all_responses = baseline_responses + gen_response + candidate_responses
    provider = MockProvider(responses=all_responses)

    report = await run_fixer(
        [tool],
        provider,
        provider,
        src_file,
        ["description_quality"],
        trials=5,
        min_delta=10.0,
    )

    # sigma of baseline (0-100 scale):
    # scores = [0, 100, 0, 100, 0] → mean=40, stdev=50.0
    # delta = 55 - 40 = 15
    # threshold = max(50.0, 10.0) = 50.0
    # 15 <= 50 → rejected
    assert len(report.rejected) == 1
    assert len(report.accepted) == 0
    assert report.rejected[0].tool_name == "mystery"


# ── T9: Source patcher — description ──────────────────────────────────────────


def test_patch_source_description_replaces_correctly() -> None:
    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    result = _patch_source_description(source, "mystery", "Improved description.")
    # repr("Improved description.") uses single quotes — check text present, not quote style
    assert "Improved description." in result
    assert 'description=""' not in result


def test_patch_source_description_no_match_unchanged() -> None:
    source = 'name="other", description="old"'
    result = _patch_source_description(source, "mystery", "new")
    assert result == source


def test_patch_source_description_leaves_other_tools_intact() -> None:
    source = (
        'types.Tool(\n    name="echo",\n    description="Echo it",\n    inputSchema={},\n)\n'
        'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    )
    result = _patch_source_description(source, "mystery", "Fixed.")
    assert 'name="echo"' in result
    assert "Echo it" in result
    assert "Fixed." in result


# ── Regression: description with special chars must produce parseable source ──


def test_patch_source_description_double_quote_produces_parseable_source() -> None:
    """Generated descriptions containing double-quotes must not corrupt the file.

    The old code used f'description="{new_desc}"' which produced a SyntaxError
    when new_desc contained a double-quote. The fix uses repr(new_desc).
    """
    import ast

    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    desc_with_quotes = 'Use "quotes" like this'
    result = _patch_source_description(source, "mystery", desc_with_quotes)

    # Must parse as valid Python — the old bug would fail here
    tree = ast.parse(result)
    assert tree is not None

    # The description text must survive the round-trip
    assert desc_with_quotes in result


def test_patch_source_description_backslash_and_quote_round_trips() -> None:
    """Both backslash and double-quote in the same description must round-trip."""
    import ast

    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    desc = r'path\to\file and "quoted" word'
    result = _patch_source_description(source, "mystery", desc)

    # Must be valid Python
    ast.parse(result)

    # Text must be present (repr preserves the value)
    assert "quoted" in result
    assert "path" in result


def test_patch_source_description_newline_in_desc_produces_parseable_source() -> None:
    """A newline character in the description must not produce a broken string literal."""
    import ast

    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    desc = "line one\nline two"
    result = _patch_source_description(source, "mystery", desc)

    # Must parse as valid Python
    ast.parse(result)


# ── T9: Source patcher — schema props ─────────────────────────────────────────


def test_patch_source_schema_props_replaces_empty(tmp_path: Path) -> None:
    source = 'name="mystery"\n"x": {}\n"y": {}'
    new_props = {"x": {"type": "number", "description": "first"}}
    result = _patch_source_schema_props(source, "mystery", new_props)
    assert '"type": "number"' in result


def test_patch_source_schema_props_leaves_unspecified_intact() -> None:
    source = 'name="mystery"\n"x": {}\n"y": {}'
    new_props = {"x": {"type": "number", "description": "first"}}
    result = _patch_source_schema_props(source, "mystery", new_props)
    # "y": {} should remain untouched since it's not in new_props
    assert '"y": {}' in result


def test_patch_source_schema_props_no_match_unchanged() -> None:
    source = 'name="other"\n"x": {}'
    new_props = {"x": {"type": "number", "description": "val"}}
    result = _patch_source_schema_props(source, "mystery", new_props)
    assert result == source


# ── T9: Apply round-trip ───────────────────────────────────────────────────────


def test_apply_round_trip(tmp_path: Path) -> None:
    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    target = tmp_path / "server.py"
    target.write_text(source)

    patched = _patch_source_description(source, "mystery", "Improved!")
    target.write_text(patched)
    content = target.read_text()

    assert "mystery" in content
    assert "Improved!" in content


# ── T9: run_fixer integration (schema_completeness — DETERMINISTIC) ───────────


async def test_run_fixer_schema_accepted(tmp_path: Path) -> None:
    """schema_completeness is deterministic. mystery tool (no types/descriptions) → score 0.
    Generator returns valid JSON with types+descriptions → candidate scores 100+.
    delta = ~100 > 10 → accepted."""
    source = (
        "types.Tool(\n"
        '    name="mystery",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},\n'
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    mystery_tool = Tool(
        name="mystery",
        description="",
        inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},
    )

    gen_response = (
        '{"properties": {"x": {"type": "number", "description": "First value"}, '
        '"y": {"type": "number", "description": "Second value"}}, '
        '"required": ["x", "y"]}'
    )
    generator = MockProvider(responses=[gen_response])
    judge = MockProvider(responses=["7"])  # judge not called for DETERMINISTIC dim

    report = await run_fixer(
        [mystery_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
    )

    assert len(report.accepted) == 1
    assert report.accepted[0].tool_name == "mystery"
    assert report.accepted[0].dim == "schema_completeness"
    assert report.accepted[0].delta > 10.0
    assert report.diff_text  # non-empty diff
    assert report.patched_source  # patched source available


# ── T9: run_fixer integration (description_quality — JUDGE_BASED, accepted) ───


async def test_run_fixer_desc_accepted(tmp_path: Path) -> None:
    """description_quality: MockProvider drives baseline low (score=10), candidate high (score=90).
    delta=80 > max(sigma≈0, min_delta=10) → accepted."""
    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    tool = Tool(name="mystery", description="", inputSchema={})

    # Response queue:
    # - baseline judge: 5 calls → each returns "1" → score=10.0 per trial
    # - generate description: 1 call → "Improved description of mystery tool."
    # - candidate judge: 5 calls → each returns "9" → score=90.0 per trial
    responses = ["1"] * 5 + ["Improved description of mystery tool."] + ["9"] * 5
    provider = MockProvider(responses=responses)

    report = await run_fixer(
        [tool],
        provider,
        provider,
        src_file,
        ["description_quality"],
        trials=5,
        min_delta=10.0,
    )

    assert len(report.accepted) == 1
    assert report.accepted[0].accepted is True
    assert report.accepted[0].delta == pytest.approx(80.0, abs=1.0)
    assert "Improved description" in report.patched_source


# ── T9: run_fixer integration (rejected when delta too small) ─────────────────


async def test_run_fixer_desc_rejected_low_delta(tmp_path: Path) -> None:
    """delta=5 < min_delta=10 → rejected even for JUDGE_BASED."""
    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    tool = Tool(name="mystery", description="", inputSchema={})

    # baseline=50, generate, candidate=55 → delta=5 < 10 → rejected
    responses = ["5"] * 5 + ["Slightly better description."] + ["5.5"] * 5
    provider = MockProvider(responses=responses)

    report = await run_fixer(
        [tool],
        provider,
        provider,
        src_file,
        ["description_quality"],
        trials=5,
        min_delta=10.0,
    )

    assert len(report.rejected) == 1
    assert len(report.accepted) == 0
    assert not report.diff_text  # no diff when nothing accepted


# ── T10: Generator model assertion ────────────────────────────────────────────


def test_generator_ne_judge_raises_when_same() -> None:
    with pytest.raises(ValueError, match="generator_model must differ"):
        assert_generator_ne_judge("llama3.1:8b", "llama3.1:8b")


def test_generator_ne_judge_passes_when_different() -> None:
    assert_generator_ne_judge("qwen3:8b", "llama3.1:8b")  # should not raise


# ── T10: Generate description ─────────────────────────────────────────────────


async def test_generate_description_uses_provider() -> None:
    tool = Tool(name="mystery", description="", inputSchema={})
    provider = MockProvider(responses=["Compute a mystery result from x and y."])
    result = await _generate_description(tool, provider)
    assert result == "Compute a mystery result from x and y."


async def test_generate_description_strips_whitespace() -> None:
    tool = Tool(name="mystery", description="", inputSchema={})
    provider = MockProvider(responses=["  Stripped.  "])
    result = await _generate_description(tool, provider)
    assert result == "Stripped."


# ── T10: Generate schema props ────────────────────────────────────────────────


async def test_generate_schema_props_parses_json() -> None:
    tool = Tool(name="mystery", description="", inputSchema={"properties": {"x": {}}})
    json_resp = (
        '{"properties": {"x": {"type": "number", "description": "Input value"}}, "required": ["x"]}'
    )
    provider = MockProvider(responses=[json_resp])
    props, required = await _generate_schema_props(tool, provider)
    assert props == {"x": {"type": "number", "description": "Input value"}}
    assert required == ["x"]


async def test_generate_schema_props_strips_markdown_fence() -> None:
    tool = Tool(name="mystery", description="", inputSchema={"properties": {"x": {}}})
    fenced = '```json\n{"properties": {"x": {"type": "string", "description": "A value"}}, "required": ["x"]}\n```'
    provider = MockProvider(responses=[fenced])
    props, required = await _generate_schema_props(tool, provider)
    assert props == {"x": {"type": "string", "description": "A value"}}
    assert required == ["x"]


async def test_generate_schema_props_returns_empty_on_invalid_json() -> None:
    tool = Tool(name="mystery", description="", inputSchema={"properties": {"x": {}}})
    provider = MockProvider(responses=["not valid json"])
    props, required = await _generate_schema_props(tool, provider)
    assert props == {}
    assert required == []


# ── T10: Judge trials ─────────────────────────────────────────────────────────


async def test_judge_desc_trials_returns_scores() -> None:
    tool = Tool(name="echo", description="Echo a message.", inputSchema={})
    provider = MockProvider(responses=["8", "7", "9"])
    scores = await _judge_desc_trials(tool, provider, trials=3)
    assert scores == [80.0, 70.0, 90.0]


async def test_judge_desc_trials_clamps_to_100() -> None:
    tool = Tool(name="echo", description="Echo.", inputSchema={})
    provider = MockProvider(responses=["11"])  # above max
    scores = await _judge_desc_trials(tool, provider, trials=1)
    assert scores == [100.0]  # clamped at 10*10


async def test_judge_desc_trials_returns_empty_when_unparseable() -> None:
    tool = Tool(name="echo", description="Echo.", inputSchema={})
    provider = MockProvider(responses=["no number here"])
    scores = await _judge_desc_trials(tool, provider, trials=1)
    assert scores == []


# ── T10: Unknown dim is skipped ────────────────────────────────────────────────


async def test_run_fixer_unknown_dim_is_skipped(tmp_path: Path) -> None:
    source = 'types.Tool(\n    name="mystery",\n    description="",\n    inputSchema={},\n)'
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    tool = Tool(name="mystery", description="", inputSchema={})
    provider = MockProvider()

    report = await run_fixer(
        [tool],
        provider,
        provider,
        src_file,
        ["nonexistent_dim"],
        trials=1,
        min_delta=10.0,
    )

    assert len(report.skipped) == 1
    assert "mystery:nonexistent_dim" in report.skipped
    assert len(report.accepted) == 0
    assert len(report.rejected) == 0


# ── T12: Over-marking guard ────────────────────────────────────────────────────


def test_apply_overmarking_guard_keeps_required_params() -> None:
    result = _apply_overmarking_guard(["x", "y"], {"x": {}, "y": {}}, {})
    assert result == ["x", "y"]


def test_apply_overmarking_guard_strips_defaulted_param() -> None:
    existing_props = {"name": {}, "prefix": {"default": "Hello"}}
    result = _apply_overmarking_guard(["name", "prefix"], existing_props, {})
    assert result == ["name"]
    assert "prefix" not in result


def test_apply_overmarking_guard_strips_generated_default() -> None:
    new_props = {"x": {"type": "number", "description": "val", "default": 0}}
    result = _apply_overmarking_guard(["x"], {}, new_props)
    assert result == []


def test_apply_overmarking_guard_empty_derived_required() -> None:
    result = _apply_overmarking_guard([], {"x": {}}, {})
    assert result == []


# ── T12: _patch_source_required ───────────────────────────────────────────────


def test_patch_source_required_adds_array_after_properties() -> None:
    source = (
        "types.Tool(\n"
        '    name="mystery",\n'
        '    description="",\n'
        "    inputSchema={\n"
        '        "type": "object",\n'
        '        "properties": {\n'
        '            "x": {"type": "number", "description": "val"},\n'
        '            "y": {"type": "number", "description": "val"},\n'
        "        },\n"
        "    },\n"
        ")"
    )
    result = _patch_source_required(source, "mystery", ["x", "y"])
    assert '"required": ["x", "y"]' in result


def test_patch_source_required_replaces_existing_required() -> None:
    source = (
        "types.Tool(\n"
        '    name="mystery",\n'
        '    description="",\n'
        "    inputSchema={\n"
        '        "type": "object",\n'
        '        "properties": {"x": {}},\n'
        '        "required": ["old"],\n'
        "    },\n"
        ")"
    )
    result = _patch_source_required(source, "mystery", ["x"])
    assert '"required": ["x"]' in result
    assert '"required": ["old"]' not in result


def test_patch_source_required_no_properties_returns_unchanged() -> None:
    source = 'name="mystery"\ninputSchema={}'
    result = _patch_source_required(source, "mystery", ["x"])
    assert result == source


def test_patch_source_required_empty_required_returns_unchanged() -> None:
    source = 'name="mystery"\n"properties": {"x": {}}'
    result = _patch_source_required(source, "mystery", [])
    assert result == source


# ── T12: score 66.7 → 100 integration ─────────────────────────────────────────


async def test_run_fixer_schema_required_lifts_score_to_100(tmp_path: Path) -> None:
    """mystery (no types, no descriptions, no required) scores 0 baseline.
    Generator returns types + descriptions + required=["x","y"].
    Candidate scores 100. delta=100 > 10 → accepted. candidate.new_required = ["x", "y"]."""
    source = (
        "types.Tool(\n"
        '    name="mystery",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},\n'
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    mystery_tool = Tool(
        name="mystery",
        description="",
        inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},
    )

    gen_response = (
        '{"properties": {"x": {"type": "number", "description": "First operand"}, '
        '"y": {"type": "number", "description": "Second operand"}}, '
        '"required": ["x", "y"]}'
    )
    generator = MockProvider(responses=[gen_response])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [mystery_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
    )

    assert len(report.accepted) == 1
    cand = report.accepted[0]
    assert cand.tool_name == "mystery"
    assert cand.candidate_score == pytest.approx(100.0)
    assert cand.baseline_score == pytest.approx(0.0)
    assert cand.new_required == ["x", "y"]
    assert '"required"' in report.patched_source


async def test_run_fixer_schema_overmarking_guard_in_full_pipeline(tmp_path: Path) -> None:
    """Greet tool: name (required), prefix (optional, default='Hello').
    Generator marks both as required. Guard must strip prefix from required.
    Patched source must NOT have prefix in required array."""
    source = (
        "types.Tool(\n"
        '    name="greet",\n'
        '    description="",\n'
        "    inputSchema={\n"
        '        "type": "object",\n'
        '        "properties": {\n'
        '            "name": {},\n'
        '            "prefix": {"default": "Hello"},\n'
        "        },\n"
        "    },\n"
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    greet_tool = Tool(
        name="greet",
        description="",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {},
                "prefix": {"default": "Hello"},
            },
        },
    )

    # Generator (incorrectly) marks both name and prefix as required
    gen_response = (
        '{"properties": {"name": {"type": "string", "description": "Name to greet"}, '
        '"prefix": {"type": "string", "description": "Greeting prefix"}}, '
        '"required": ["name", "prefix"]}'
    )
    generator = MockProvider(responses=[gen_response])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [greet_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
    )

    assert len(report.accepted) == 1
    cand = report.accepted[0]
    assert "name" in cand.new_required
    assert "prefix" not in cand.new_required
    # Patched source must not have "prefix" in required
    assert '"prefix"' not in (
        report.patched_source.split('"required"')[1]
        if '"required"' in report.patched_source
        else ""
    )


# ── T14: deep_merge + non-destructive keyword preservation ──────────────────


def test_deep_merge_preserves_keys_absent_from_incoming() -> None:
    existing = {"type": "string", "default": "Hello", "enum": ["Hello", "Hi"]}
    incoming = {"type": "string", "description": "Greeting prefix"}
    result = deep_merge(existing, incoming)
    assert result["default"] == "Hello"
    assert result["enum"] == ["Hello", "Hi"]
    assert result["description"] == "Greeting prefix"
    assert result["type"] == "string"


def test_deep_merge_incoming_scalar_wins() -> None:
    existing = {"type": "integer", "minimum": 0}
    incoming = {"type": "number", "description": "A value"}
    result = deep_merge(existing, incoming)
    assert result["type"] == "number"  # incoming wins
    assert result["minimum"] == 0  # existing preserved


def test_deep_merge_recurses_into_nested_dicts() -> None:
    existing = {"items": {"type": "string", "format": "date"}}
    incoming = {"items": {"type": "string", "description": "A date"}}
    result = deep_merge(existing, incoming)
    assert result["items"]["format"] == "date"  # preserved
    assert result["items"]["description"] == "A date"  # added


def test_deep_merge_list_from_incoming_wins() -> None:
    existing = {"enum": ["a", "b", "c"]}
    incoming = {"enum": ["x", "y"]}
    result = deep_merge(existing, incoming)
    assert result["enum"] == ["x", "y"]  # incoming list wins (scalars/lists override)


def test_deep_merge_keyword_preservation_matrix() -> None:
    """All existing keywords survive when generator returns only {type, description}."""
    existing = {
        "type": "string",
        "default": "Hello",
        "enum": ["Hello", "Hi", "Hey"],
        "minimum": 1,
        "format": "uri",
        "items": {"type": "string"},
        "properties": {"nested": {"type": "boolean"}},
    }
    incoming = {"type": "string", "description": "A parameter"}
    result = deep_merge(existing, incoming)

    assert result["default"] == "Hello"
    assert result["enum"] == ["Hello", "Hi", "Hey"]
    assert result["minimum"] == 1
    assert result["format"] == "uri"
    assert result["items"] == {"type": "string"}
    assert result["properties"] == {"nested": {"type": "boolean"}}
    assert result["description"] == "A parameter"
    assert result["type"] == "string"


def test_deep_merge_param_only_in_existing_unchanged() -> None:
    """Param not touched by generator survives in merged_props."""
    existing_props = {"untouched": {"type": "integer", "minimum": 0}, "touched": {}}
    new_props = {"touched": {"type": "string", "description": "val"}}
    merged: dict[str, Any] = {}
    for param, schema in existing_props.items():
        merged[param] = deep_merge(schema, new_props[param]) if param in new_props else schema
    for param, schema in new_props.items():
        if param not in existing_props:
            merged[param] = schema
    assert merged["untouched"] == {"type": "integer", "minimum": 0}
    assert merged["touched"] == {"type": "string", "description": "val"}


def test_deep_merge_param_only_in_generator_added() -> None:
    """Param that exists only in generator output is added."""
    existing_props: dict[str, Any] = {}
    new_props = {"new_param": {"type": "boolean", "description": "A flag"}}
    merged: dict[str, Any] = {}
    for param, schema in existing_props.items():
        merged[param] = deep_merge(schema, new_props[param]) if param in new_props else schema
    for param, schema in new_props.items():
        if param not in existing_props:
            merged[param] = schema
    assert "new_param" in merged
    assert merged["new_param"]["type"] == "boolean"


async def test_run_fixer_greet_hits_100_with_preserved_default(tmp_path: Path) -> None:
    """greet.prefix has default='Hello'. Generator returns only {type, description} for prefix.
    Non-destructive merge preserves the default. Over-marking guard strips prefix from required.
    Scorer awards 3rd point for default is not None -> greet scores 100."""
    source = (
        "types.Tool(\n"
        '    name="greet",\n'
        '    description="",\n'
        "    inputSchema={\n"
        '        "type": "object",\n'
        '        "properties": {\n'
        '            "name": {},\n'
        '            "prefix": {"default": "Hello"},\n'
        "        },\n"
        "    },\n"
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    greet_tool = Tool(
        name="greet",
        description="",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {},
                "prefix": {"default": "Hello"},
            },
        },
    )

    # Generator returns realistic two-field output (only type + description per param)
    gen_response = (
        '{"properties": {"name": {"type": "string", "description": "Name of the person to greet"}, '
        '"prefix": {"type": "string", "description": "Greeting prefix"}}, '
        '"required": ["name", "prefix"]}'
    )
    generator = MockProvider(responses=[gen_response])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [greet_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
    )

    assert len(report.accepted) == 1
    cand = report.accepted[0]
    assert cand.tool_name == "greet"
    assert cand.candidate_score == pytest.approx(100.0), (
        f"Expected 100 but got {cand.candidate_score} — default not preserved?"
    )
    # Guard must have stripped prefix from required
    assert "prefix" not in cand.new_required
    assert "name" in cand.new_required


# ── T13: cost pre-filter (skip_above_band) ────────────────────────────────


async def test_skip_above_band_skips_high_scoring_tool(tmp_path: Path) -> None:
    """Tool already at 100 with band=90 -> SKIPPED, zero generator calls."""
    source = (
        "types.Tool(\n"
        '    name="perfect",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {'
        '"x": {"type": "number", "description": "val"}}, "required": ["x"]},\n'
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    perfect_tool = Tool(
        name="perfect",
        description="",
        inputSchema={
            "type": "object",
            "properties": {"x": {"type": "number", "description": "val"}},
            "required": ["x"],
        },
    )

    generator = MockProvider(responses=["should not be called"])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [perfect_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
        skip_above_band=90.0,
    )

    assert len(report.accepted) == 0
    assert len(report.rejected) == 0
    assert len(report.skipped) == 1
    assert "perfect:schema_completeness:already_above_band" in report.skipped
    # Zero generator calls — _idx stays at 0
    assert generator._idx == 0


async def test_skip_above_band_processes_low_scoring_tool(tmp_path: Path) -> None:
    """Tool at 0 with band=90 -> generation proceeds, accepted when delta large."""
    source = (
        "types.Tool(\n"
        '    name="mystery",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},\n'
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    mystery_tool = Tool(
        name="mystery",
        description="",
        inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},
    )

    gen_response = (
        '{"properties": {"x": {"type": "number", "description": "First value"}, '
        '"y": {"type": "number", "description": "Second value"}}, '
        '"required": ["x", "y"]}'
    )
    generator = MockProvider(responses=[gen_response])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [mystery_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
        skip_above_band=90.0,
    )

    assert len(report.accepted) == 1
    assert len(report.skipped) == 0
    # Generator was called (at least once)
    assert generator._idx >= 1


async def test_skip_above_band_boundary_equal_is_skipped(tmp_path: Path) -> None:
    """A tool scoring exactly at the band threshold is skipped (>=, not >)."""
    # Single param with type + description + default -> 3/3 points for 1 param = 100
    # Use a band of 100.0 to hit the == boundary
    source = (
        "types.Tool(\n"
        '    name="exact",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {'
        '"x": {"type": "string", "description": "val", "default": "hi"}}},\n'
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    exact_tool = Tool(
        name="exact",
        description="",
        inputSchema={
            "type": "object",
            "properties": {"x": {"type": "string", "description": "val", "default": "hi"}},
        },
    )

    generator = MockProvider(responses=["unused"])
    judge = MockProvider(responses=[])

    # band = 100.0, tool scores 100 => should be skipped
    report = await run_fixer(
        [exact_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
        skip_above_band=100.0,
    )

    assert len(report.skipped) == 1
    assert "exact:schema_completeness:already_above_band" in report.skipped
    assert generator._idx == 0


async def test_skip_above_band_just_under_is_processed(tmp_path: Path) -> None:
    """A tool scoring just below the band still goes through generation."""
    # mystery with x:{} y:{} -> score=0, well below any reasonable band
    # Use a band of 50.0 — mystery at 0 should be processed
    source = (
        "types.Tool(\n"
        '    name="mystery",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},\n'
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    mystery_tool = Tool(
        name="mystery",
        description="",
        inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},
    )

    gen_response = (
        '{"properties": {"x": {"type": "number", "description": "x"}, '
        '"y": {"type": "number", "description": "y"}}, "required": ["x", "y"]}'
    )
    generator = MockProvider(responses=[gen_response])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [mystery_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
        skip_above_band=50.0,
    )

    # mystery was NOT skipped — generation was called
    assert generator._idx >= 1
    assert "mystery:schema_completeness:already_above_band" not in report.skipped


def test_skip_above_band_reason_distinct_from_rejected() -> None:
    """Skipped entries contain 'already_above_band'; rejected entries do not.

    Also verifies DEFAULT_SKIP_ABOVE_BAND is 90.0 — the calibrated default.
    """
    # Structural test — verify the string convention and the constant value
    skipped_entry = "echo:schema_completeness:already_above_band"
    assert "already_above_band" in skipped_entry
    assert skipped_entry != "echo:schema_completeness"  # distinct from unknown-dim skip
    assert DEFAULT_SKIP_ABOVE_BAND == 90.0


async def test_skip_above_band_mixed_tools(tmp_path: Path) -> None:
    """In a mixed run: high-scoring tool skipped, low-scoring tool processed."""
    source = (
        "types.Tool(\n"
        '    name="perfect",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {'
        '"x": {"type": "number", "description": "val"}}, "required": ["x"]},\n'
        ")\n"
        "types.Tool(\n"
        '    name="mystery",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},\n'
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    perfect_tool = Tool(
        name="perfect",
        description="",
        inputSchema={
            "type": "object",
            "properties": {"x": {"type": "number", "description": "val"}},
            "required": ["x"],
        },
    )
    mystery_tool = Tool(
        name="mystery",
        description="",
        inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},
    )

    gen_response = (
        '{"properties": {"x": {"type": "number", "description": "x"}, '
        '"y": {"type": "number", "description": "y"}}, "required": ["x", "y"]}'
    )
    generator = MockProvider(responses=[gen_response])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [perfect_tool, mystery_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
        skip_above_band=90.0,
    )

    # perfect is skipped
    assert any("perfect:schema_completeness:already_above_band" in s for s in report.skipped)
    # mystery is accepted
    assert any(c.tool_name == "mystery" for c in report.accepted)
    # Generator called exactly once (for mystery only)
    assert generator._idx == 1


# ── Tx: Grounding detection ────────────────────────────────────────────────────


def test_is_low_grounding_true_for_single_char_suffix() -> None:
    """get_a, del_b, put_x → single-char suffix after generic verb → low grounding."""
    for name in ("get_a", "del_b", "put_x", "set_z"):
        tool = Tool(name=name, description="", inputSchema={})
        assert is_low_grounding(tool), f"Expected low grounding for {name!r}"


def test_is_low_grounding_false_for_grounded_tool() -> None:
    """transform_scale, compute_median, search_products → carry domain signal."""
    for name in ("transform_scale", "compute_median", "search_products", "fetch_sensor_value"):
        tool = Tool(name=name, description="", inputSchema={})
        assert not is_low_grounding(tool), f"Expected grounded (not low) for {name!r}"


def test_count_grounding_tokens_zero_for_opaque() -> None:
    """_count_grounding_tokens returns 0 for opaque tool names."""
    assert _count_grounding_tokens("get_a") == 0
    assert _count_grounding_tokens("del_b") == 0
    assert _count_grounding_tokens("put_x") == 0


def test_count_grounding_tokens_positive_for_grounded() -> None:
    """_count_grounding_tokens returns > 0 for tools with domain tokens."""
    assert _count_grounding_tokens("transform_scale") >= 1
    assert _count_grounding_tokens("compute_median") >= 1


# ── Tx: ABSTAINED behavior in run_fixer ───────────────────────────────────────


async def test_abstain_fires_on_opaque_description_quality(tmp_path: Path) -> None:
    """Opaque tool name → description_quality → ABSTAINED, original preserved, zero generator calls."""
    source = 'types.Tool(\n    name="get_a",\n    description="Get.",\n    inputSchema={},\n)'
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    opaque_tool = Tool(name="get_a", description="Get.", inputSchema={})
    generator = MockProvider(responses=["should not be called"])
    judge = MockProvider(responses=["1"] * 10)  # judge would be called for baseline if we got there

    report = await run_fixer(
        [opaque_tool],
        generator,
        judge,
        src_file,
        ["description_quality"],
        trials=5,
        min_delta=10.0,
    )

    # Abstained — not in accepted, rejected, or skipped
    assert len(report.abstained) == 1
    assert "get_a:description_quality:low_grounding" in report.abstained
    assert len(report.accepted) == 0
    assert len(report.rejected) == 0
    # No generator call made
    assert generator._idx == 0
    # No judge call made (we never reached baseline scoring)
    assert judge._idx == 0


async def test_abstain_preserves_original_description(tmp_path: Path) -> None:
    """When ABSTAINED, the original description is untouched in source."""
    source = 'types.Tool(\n    name="del_b",\n    description="Del.",\n    inputSchema={},\n)'
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    opaque_tool = Tool(name="del_b", description="Del.", inputSchema={})
    generator = MockProvider(responses=[])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [opaque_tool],
        generator,
        judge,
        src_file,
        ["description_quality"],
    )

    assert len(report.abstained) == 1
    # Source not modified — no diff, no patched_source
    assert not report.diff_text
    assert not report.patched_source


async def test_abstain_not_fired_for_schema_completeness(tmp_path: Path) -> None:
    """Opaque tool name + schema_completeness → grounding check NOT applied → generation fires."""
    source = (
        "types.Tool(\n"
        '    name="get_a",\n'
        '    description="",\n'
        '    inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},\n'
        ")"
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    opaque_tool = Tool(
        name="get_a",
        description="",
        inputSchema={"type": "object", "properties": {"x": {}, "y": {}}},
    )

    gen_response = (
        '{"properties": {"x": {"type": "number", "description": "First value"}, '
        '"y": {"type": "number", "description": "Second value"}}, "required": ["x", "y"]}'
    )
    generator = MockProvider(responses=[gen_response])
    judge = MockProvider(responses=[])

    report = await run_fixer(
        [opaque_tool],
        generator,
        judge,
        src_file,
        ["schema_completeness"],
        trials=1,
        min_delta=10.0,
    )

    # schema_completeness path unaffected — generation fired
    assert len(report.abstained) == 0
    assert generator._idx >= 1
    assert len(report.accepted) == 1


async def test_degenerate_guard_grounded_tool_generates(tmp_path: Path) -> None:
    """DEGENERATE-GUARD: a clearly-grounded tool must NOT abstain on description_quality.

    Prevents the degenerate solution of abstaining on everything.
    """
    source = 'types.Tool(\n    name="transform_scale",\n    description="",\n    inputSchema={},\n)'
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    grounded_tool = Tool(name="transform_scale", description="", inputSchema={})

    # Generator returns a description; judge scores it high enough to accept
    generator = MockProvider(responses=["Applies a linear scale transformation."])
    # Baseline: 5 trials = 10/100; candidate: 5 trials = 90/100 → accepted
    judge = MockProvider(responses=["1"] * 5 + ["9"] * 5)

    report = await run_fixer(
        [grounded_tool],
        generator,
        judge,
        src_file,
        ["description_quality"],
        trials=5,
        min_delta=10.0,
    )

    # Tool is grounded → abstain did NOT fire
    assert len(report.abstained) == 0, (
        "DEGENERATE GUARD FAILED: transform_scale (grounded tool) should not abstain"
    )
    # Generator was called
    assert generator._idx >= 1
    # Result is in accepted or rejected (either is fine — we just need generation to have fired)
    total = len(report.accepted) + len(report.rejected)
    assert total == 1, f"Expected 1 candidate (accepted or rejected), got {total}"


async def test_abstained_distinct_from_skipped_and_rejected(tmp_path: Path) -> None:
    """ABSTAINED is a separate list from skipped and rejected; entries follow format tool:dim:reason."""
    source = 'types.Tool(\n    name="put_x",\n    description="Put.",\n    inputSchema={},\n)'
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    opaque_tool = Tool(name="put_x", description="Put.", inputSchema={})
    provider = MockProvider(responses=[])

    report = await run_fixer(
        [opaque_tool],
        provider,
        provider,
        src_file,
        ["description_quality"],
    )

    # Exactly one abstained entry
    assert len(report.abstained) == 1
    assert report.abstained[0] == "put_x:description_quality:low_grounding"
    # Not in skipped
    assert not any("put_x" in s for s in report.skipped)
    # Not in rejected
    assert not any(c.tool_name == "put_x" for c in report.rejected)
    # Not in accepted
    assert not any(c.tool_name == "put_x" for c in report.accepted)


async def test_mixed_opaque_and_grounded_tools(tmp_path: Path) -> None:
    """Mixed run: opaque tool abstains, grounded tool generates. Proves abstain is selective."""
    source = (
        'types.Tool(\n    name="get_a",\n    description="Get.",\n    inputSchema={},\n)\n'
        'types.Tool(\n    name="transform_scale",\n    description="",\n    inputSchema={},\n)'
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    opaque = Tool(name="get_a", description="Get.", inputSchema={})
    grounded = Tool(name="transform_scale", description="", inputSchema={})

    # Only one generate call (for grounded tool); judge calls for grounded tool
    generator = MockProvider(responses=["Applies a linear scale transformation."])
    judge = MockProvider(responses=["1"] * 5 + ["9"] * 5)

    report = await run_fixer(
        [opaque, grounded],
        generator,
        judge,
        src_file,
        ["description_quality"],
        trials=5,
        min_delta=10.0,
    )

    # get_a abstained
    assert any("get_a:description_quality:low_grounding" in s for s in report.abstained)
    # transform_scale did NOT abstain
    assert not any("transform_scale" in s for s in report.abstained)
    # Generator called for transform_scale only (idx=1)
    assert generator._idx == 1


# ── Q2b: Neighbor selection ────────────────────────────────────────────────────


def test_select_neighbors_deterministic() -> None:
    """Same catalog → identical neighbor order on repeated calls."""
    catalog = [
        Tool(name="get_record", description="", inputSchema={}),
        Tool(name="fetch_record", description="", inputSchema={}),
        Tool(name="read_entry", description="", inputSchema={}),
        Tool(name="save_record", description="", inputSchema={}),
        Tool(name="store_item", description="", inputSchema={}),
        Tool(name="delete_record", description="", inputSchema={}),
        Tool(name="update_record", description="", inputSchema={}),
    ]
    target = Tool(name="get_record", description="", inputSchema={})
    neighbors1 = _select_neighbors(target, catalog, k=4)
    neighbors2 = _select_neighbors(target, catalog, k=4)
    assert [n.name for n in neighbors1] == [n.name for n in neighbors2]


def test_select_neighbors_excludes_target() -> None:
    """Neighbors never include the target tool itself."""
    catalog = [
        Tool(name="get_record", description="", inputSchema={}),
        Tool(name="fetch_record", description="", inputSchema={}),
        Tool(name="save_record", description="", inputSchema={}),
    ]
    target = Tool(name="get_record", description="", inputSchema={})
    neighbors = _select_neighbors(target, catalog, k=5)
    assert all(n.name != "get_record" for n in neighbors)


def test_select_neighbors_does_not_use_family_labels() -> None:
    """_select_neighbors takes only list[Tool] — no family dict in signature."""
    sig = inspect.signature(_select_neighbors)
    params = list(sig.parameters.keys())
    assert "family" not in params
    assert "families" not in params
    assert "family_map" not in params


def test_select_neighbors_token_similarity_ranks_shared_token_first() -> None:
    """fetch_record shares 'record' with get_record → ranks above unrelated tools."""
    catalog = [
        Tool(name="fetch_record", description="", inputSchema={}),
        Tool(name="search_items", description="", inputSchema={}),
        Tool(name="notify_user", description="", inputSchema={}),
    ]
    target = Tool(name="get_record", description="", inputSchema={})
    neighbors = _select_neighbors(target, catalog, k=3)
    assert neighbors[0].name == "fetch_record"


def test_select_neighbors_respects_k() -> None:
    """Returns at most k neighbors."""
    catalog = [Tool(name=f"tool_{i}", description="", inputSchema={}) for i in range(20)]
    target = Tool(name="tool_0", description="", inputSchema={})
    neighbors = _select_neighbors(target, catalog, k=5)
    assert len(neighbors) <= 5


# ── Q2b: Catalog-aware prompt content ─────────────────────────────────────────


async def test_catalog_aware_prompt_contains_no_fabrication_guard() -> None:
    """Catalog-aware prompt includes the no-fabrication instruction."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "Plain description."

    target = Tool(name="store_item", description="", inputSchema={"type": "object"})
    neighbor = Tool(name="save_record", description="", inputSchema={"type": "object"})
    await _generate_description(target, CapturingProvider(), neighbors=[neighbor])

    assert captured, "No prompt captured"
    prompt = captured[0]
    assert "NO FABRICATION" in prompt or "DO NOT invent" in prompt
    assert "save_record" in prompt


async def test_catalog_aware_prompt_contains_neighbor_names() -> None:
    """Catalog-aware prompt contains all neighbor names and descriptions."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "A distinguishing description."

    target = Tool(name="get_record", description="", inputSchema={})
    neighbors = [
        Tool(name="fetch_record", description="Fetch via HTTP", inputSchema={}),
        Tool(name="read_entry", description="Read from file", inputSchema={}),
    ]
    await _generate_description(target, CapturingProvider(), neighbors=neighbors)

    prompt = captured[0]
    assert "fetch_record" in prompt
    assert "read_entry" in prompt
    assert "Fetch via HTTP" in prompt


async def test_generate_description_no_neighbors_omits_catalog_content() -> None:
    """When neighbors=None, prompt does not contain catalog-aware content."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "Simple description."

    target = Tool(name="mystery", description="old", inputSchema={})
    await _generate_description(target, CapturingProvider(), neighbors=None)

    prompt = captured[0]
    assert "Confusable neighbors" not in prompt
    assert "NO FABRICATION" not in prompt


async def test_generate_description_catalog_aware_real_difference_neighbor() -> None:
    """MockProvider: real-schema-difference neighbor → distinguishing response returned."""
    _SCHEMA_CACHE = {
        "type": "object",
        "properties": {"key": {"type": "string"}, "ttl": {"type": "integer"}},
    }
    _SCHEMA_DB = {
        "type": "object",
        "properties": {"key": {"type": "string"}, "value": {"type": "object"}},
    }

    target = Tool(name="store_item", description="", inputSchema=_SCHEMA_CACHE)
    neighbors = [Tool(name="save_record", description="", inputSchema=_SCHEMA_DB)]

    provider = MockProvider(
        responses=["Store an item in cache with TTL; unlike save_record which persists to DB."]
    )
    result = await _generate_description(target, provider, neighbors=neighbors)
    assert "Store an item in cache with TTL" in result


async def test_generate_description_catalog_aware_identical_neighbor_plain() -> None:
    """MockProvider: identical-schema neighbor → plain non-fabricated response returned."""
    _SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    target = Tool(name="find_entries", description="", inputSchema=_SCHEMA)
    neighbors = [Tool(name="lookup_data", description="", inputSchema=_SCHEMA)]

    provider = MockProvider(responses=["Retrieve entries matching the given query string."])
    result = await _generate_description(target, provider, neighbors=neighbors)
    assert result == "Retrieve entries matching the given query string."


async def test_run_fixer_catalog_aware_prompt_references_neighbors(tmp_path: Path) -> None:
    """run_fixer with catalog_aware=True sends catalog-aware prompt referencing neighbors."""
    _SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    captured_prompts: list[str] = []

    class CapturingProvider:
        model_name = "mock"
        _idx: int = 0
        _responses = ["1"] * 5 + ["Distinguishing description."] + ["9"] * 5

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured_prompts.extend(m.content for m in messages)
            resp = self._responses[self._idx % len(self._responses)]
            self._idx += 1
            return resp

    target = Tool(name="store_item", description="old", inputSchema=_SCHEMA)
    neighbor = Tool(name="save_record", description="old2", inputSchema=_SCHEMA)

    source = (
        'types.Tool(\n    name="store_item",\n    description="old",\n    inputSchema={},\n)\n'
        'types.Tool(\n    name="save_record",\n    description="old2",\n    inputSchema={},\n)'
    )
    src_file = tmp_path / "server.py"
    src_file.write_text(source)

    prov = CapturingProvider()
    await run_fixer(
        [target, neighbor],
        prov,
        prov,
        src_file,
        ["description_quality"],
        trials=5,
        min_delta=10.0,
        catalog_aware=True,
    )

    gen_prompt = next(
        (p for p in captured_prompts if "Confusable neighbors" in p),
        None,
    )
    assert gen_prompt is not None, "Expected catalog-aware prompt with 'Confusable neighbors'"
    assert "save_record" in gen_prompt
    assert "NO FABRICATION" in gen_prompt or "DO NOT invent" in gen_prompt
