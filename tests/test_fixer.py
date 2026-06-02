from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp.types import Tool

from agentgauge.fixer import (
    VALIDATION_MODE,
    FixCandidate,
    ValidationMode,
    _apply_overmarking_guard,
    _generate_description,
    _generate_schema_props,
    _judge_desc_trials,
    _patch_source_description,
    _patch_source_required,
    _patch_source_schema_props,
    assert_generator_ne_judge,
    deep_merge,
    run_fixer,
)
from agentgauge.providers import MockProvider

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
    assert 'description="Improved description."' in result
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
    assert 'description="Echo it"' in result
    assert 'description="Fixed."' in result


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
