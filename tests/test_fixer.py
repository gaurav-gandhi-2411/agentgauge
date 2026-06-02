from __future__ import annotations

from pathlib import Path

import pytest
from mcp.types import Tool

from agentgauge.fixer import (
    VALIDATION_MODE,
    FixCandidate,
    ValidationMode,
    _generate_description,
    _generate_schema_props,
    _judge_desc_trials,
    _patch_source_description,
    _patch_source_schema_props,
    assert_generator_ne_judge,
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
        '{"x": {"type": "number", "description": "First value"}, '
        '"y": {"type": "number", "description": "Second value"}}'
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
    json_resp = '{"x": {"type": "number", "description": "Input value"}}'
    provider = MockProvider(responses=[json_resp])
    result = await _generate_schema_props(tool, provider)
    assert result == {"x": {"type": "number", "description": "Input value"}}


async def test_generate_schema_props_strips_markdown_fence() -> None:
    tool = Tool(name="mystery", description="", inputSchema={"properties": {"x": {}}})
    fenced = '```json\n{"x": {"type": "string", "description": "A value"}}\n```'
    provider = MockProvider(responses=[fenced])
    result = await _generate_schema_props(tool, provider)
    assert result == {"x": {"type": "string", "description": "A value"}}


async def test_generate_schema_props_returns_empty_on_invalid_json() -> None:
    tool = Tool(name="mystery", description="", inputSchema={"properties": {"x": {}}})
    provider = MockProvider(responses=["not valid json"])
    result = await _generate_schema_props(tool, provider)
    assert result == {}


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
