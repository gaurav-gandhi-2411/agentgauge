from __future__ import annotations

import difflib
import json
import re
import statistics
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from mcp.types import Tool

from agentgauge.providers import Message, Provider
from agentgauge.scorer import score_schema_completeness


class ValidationMode(Enum):
    DETERMINISTIC = "deterministic"  # schema_completeness — heuristic, no LLM
    JUDGE_BASED = "judge_based"  # description_quality — LLM judge, σ-gated


# Determined by reading scorer.py (do not change without re-reading scorer.py):
# schema_completeness: pure static heuristic → exact delta, single pass
# description_quality: LLM judge → N≥5 trials, paired delta, σ-gated
VALIDATION_MODE: dict[str, ValidationMode] = {
    "schema_completeness": ValidationMode.DETERMINISTIC,
    "description_quality": ValidationMode.JUDGE_BASED,
}

JUDGE_MODEL_DEFAULT = "llama3.1:8b"
DEFAULT_MIN_DELTA = 10.0
DEFAULT_TRIALS = 5


@dataclass
class FixCandidate:
    tool_name: str
    dim: str
    mode: ValidationMode
    baseline_score: float
    baseline_sigma: float
    candidate_score: float
    candidate_sigma: float
    delta: float
    threshold: float
    accepted: bool
    rejection_reason: str = ""
    new_description: str = ""
    new_schema_props: dict[str, Any] = field(default_factory=dict)


@dataclass
class FixReport:
    accepted: list[FixCandidate] = field(default_factory=list)
    rejected: list[FixCandidate] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    diff_text: str = ""
    patched_source: str = ""


# Mirrors scorer.py score_description_quality prompt — do not change independently of scorer.py
_DESC_JUDGE_PROMPT = (
    "Rate this MCP tool description on a scale of 0-10 for clarity and completeness "
    "for an AI agent. Reply with ONLY a number.\n\n"
    "Tool name: {name}\n"
    "Description: {description}\n"
    "Input schema: {schema}"
)

_DESC_GENERATOR_PROMPT = (
    "You are improving an MCP tool's description to help AI agents use it correctly.\n"
    "Write a clear, concise description (1-2 sentences) that:\n"
    "- States what the tool does\n"
    "- Names any key parameters and what they represent\n"
    "- Distinguishes this tool from similar tools if relevant\n\n"
    "Tool name: {name}\n"
    "Current description: {current}\n"
    "Input schema: {schema}\n\n"
    "Write ONLY the new description text. No quotes, no preamble, no markdown."
)

_SCHEMA_GENERATOR_PROMPT = (
    "You are improving MCP tool parameter metadata for AI agent usability.\n"
    "For the tool below, generate improved parameter metadata.\n\n"
    "Tool name: {name}\n"
    "Current properties JSON: {properties}\n\n"
    "Reply with ONLY a valid JSON object mapping each parameter name to its improved metadata.\n"
    'Each parameter must have exactly these two fields: "type" and "description".\n'
    "Use standard JSON Schema types: string, integer, number, boolean, array, object.\n"
    "Example format:\n"
    '{{"x": {{"type": "number", "description": "First input value"}}, '
    '"y": {{"type": "number", "description": "Second input value"}}}}\n\n'
    "Reply with ONLY the JSON object, no markdown fences, no other text."
)


def assert_generator_ne_judge(generator_model: str, judge_model: str) -> None:
    """Raise ValueError if generator_model equals judge_model.

    Using the same model for both generation and judging creates shared blind spots —
    the judge is likely to rate its own outputs highly regardless of actual quality.
    Use a different model family for generation (e.g. qwen3 family vs llama3.1).
    """
    if generator_model == judge_model:
        raise ValueError(
            f"generator_model must differ from judge_model (both are '{generator_model}'). "
            "Using the same model for generation and judging creates shared blind spots — "
            "the judge is likely to rate its own outputs highly. "
            "Consider using a qwen3 family model as generator (e.g. 'qwen3:8b')."
        )


async def _judge_desc_trials(tool: Tool, provider: Provider, trials: int) -> list[float]:
    """Run the description quality judge for `trials` iterations.

    Mirrors scorer.py score_description_quality per-trial logic.
    Returns list of scores on 0-100 scale. Returns [] if no parseable responses.
    """
    scores: list[float] = []
    for trial_idx in range(trials):
        prompt = _DESC_JUDGE_PROMPT.format(
            name=tool.name,
            description=tool.description or "(none)",
            schema=tool.inputSchema,
        )
        resp = await provider.chat([Message(role="user", content=prompt)], seed=42 + trial_idx)
        match = re.search(r"\b(\d+(?:\.\d+)?)\b", resp)
        if match:
            raw_score = float(match.group(1))
            scores.append(min(raw_score, 10.0) * 10)  # 0-10 → 0-100
    return scores


async def _generate_description(tool: Tool, generator: Provider) -> str:
    """Generate an improved description for `tool` using the generator model."""
    prompt = _DESC_GENERATOR_PROMPT.format(
        name=tool.name,
        current=tool.description or "(none)",
        schema=tool.inputSchema,
    )
    resp = await generator.chat([Message(role="user", content=prompt)], seed=42)
    return resp.strip()


async def _generate_schema_props(tool: Tool, generator: Provider) -> dict[str, Any]:
    """Generate improved parameter metadata for `tool` using the generator model.

    Returns a dict mapping param names to {type, description} dicts.
    Returns {} if the response cannot be parsed as valid JSON.
    """
    schema = tool.inputSchema or {}
    properties = schema.get("properties", {})
    prompt = _SCHEMA_GENERATOR_PROMPT.format(
        name=tool.name,
        properties=json.dumps(properties),
    )
    resp = await generator.chat([Message(role="user", content=prompt)], seed=42)
    # Strip markdown fences if present
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", resp.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip())
    try:
        result = json.loads(cleaned.strip())
        if isinstance(result, dict):
            return result
        return {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _patch_source_description(source: str, tool_name: str, new_desc: str) -> str:
    """Replace the description field for tool_name in source code.

    Finds the tool block by locating name="<tool_name>", then replaces the next
    description= line encountered. Returns source unchanged if no match is found.
    """
    lines = source.splitlines(keepends=True)
    result_lines: list[str] = []
    found_tool = False
    replaced = False

    for line in lines:
        if not found_tool and f'name="{tool_name}"' in line:
            found_tool = True
            result_lines.append(line)
        elif found_tool and not replaced and "description=" in line:
            patched = re.sub(
                r'description="[^"]*"',
                f'description="{new_desc}"',
                line,
                count=1,
            )
            result_lines.append(patched)
            replaced = True
            found_tool = False
        else:
            result_lines.append(line)

    return "".join(result_lines)


def _patch_source_schema_props(source: str, tool_name: str, new_props: dict[str, Any]) -> str:
    """Replace empty property dicts ({}) for given param names in the tool's source block.

    Locates the block starting at name="<tool_name>" and ending at the next types.Tool(
    occurrence (or end of source). Within that block, replaces `"<param>": {}` with
    the improved metadata JSON for each param in new_props.
    """
    # Find start of this tool's block
    name_pattern = f'name="{tool_name}"'
    start_idx = source.find(name_pattern)
    if start_idx == -1:
        return source

    # Find end of block: next types.Tool( occurrence after start, or end of source
    next_tool_match = re.search(r"types\.Tool\s*\(", source[start_idx + len(name_pattern) :])
    if next_tool_match:
        end_idx = start_idx + len(name_pattern) + next_tool_match.start()
    else:
        end_idx = len(source)

    block = source[start_idx:end_idx]

    for prop_name, prop_meta in new_props.items():
        escaped_name = re.escape(prop_name)
        replacement_value = json.dumps(prop_meta)
        block = re.sub(
            rf'"{escaped_name}":\s*\{{}}',
            f'"{prop_name}": {replacement_value}',
            block,
        )

    return source[:start_idx] + block + source[end_idx:]


async def run_fixer(
    tools: list[Tool],
    generator: Provider,
    judge: Provider,
    source_path: Path,
    dims: list[str],
    *,
    trials: int = DEFAULT_TRIALS,
    min_delta: float = DEFAULT_MIN_DELTA,
) -> FixReport:
    """Run the auto-fix loop for the given tools and scoring dimensions.

    For each (tool, dim) pair:
    - Baseline score is measured (heuristic for DETERMINISTIC, judge trials for JUDGE_BASED).
    - A candidate fix is generated using the generator provider.
    - The candidate is scored using the same method as the baseline.
    - The fix is accepted only if delta > threshold (strict greater-than).
      For JUDGE_BASED, threshold = max(sigma_of_baseline, min_delta).

    After all decisions, accepted fixes are applied to the source file and a unified diff
    is generated.
    """
    report = FixReport()

    for tool in tools:
        for dim in dims:
            if dim not in VALIDATION_MODE:
                report.skipped.append(f"{tool.name}:{dim}")
                continue

            mode = VALIDATION_MODE[dim]

            # ── Baseline scoring ──────────────────────────────────────────────
            if mode == ValidationMode.DETERMINISTIC:
                baseline_score = score_schema_completeness([tool]).score
                baseline_scores: list[float] = [baseline_score]
                baseline_sigma = 0.0
            else:
                baseline_scores = await _judge_desc_trials(tool, judge, trials)
                if not baseline_scores:
                    report.skipped.append(f"{tool.name}:{dim}:no_baseline_scores")
                    continue
                baseline_score = statistics.mean(baseline_scores)
                baseline_sigma = (
                    statistics.stdev(baseline_scores) if len(baseline_scores) >= 2 else 0.0
                )

            # ── Generate candidate ────────────────────────────────────────────
            if dim == "description_quality":
                new_desc = await _generate_description(tool, generator)
                candidate_tool = Tool(
                    name=tool.name,
                    description=new_desc,
                    inputSchema=tool.inputSchema,
                )
                new_props: dict[str, Any] = {}
            else:  # schema_completeness
                new_props = await _generate_schema_props(tool, generator)
                # Merge new_props into a copy of existing properties
                existing_schema = dict(tool.inputSchema or {})
                existing_props: dict[str, Any] = dict(existing_schema.get("properties", {}))
                merged_props = {**existing_props, **new_props}
                merged_schema = {**existing_schema, "properties": merged_props}
                candidate_tool = Tool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=merged_schema,
                )
                new_desc = ""

            # ── Candidate scoring ─────────────────────────────────────────────
            if mode == ValidationMode.DETERMINISTIC:
                candidate_score_val = score_schema_completeness([candidate_tool]).score
                candidate_scores: list[float] = [candidate_score_val]
                candidate_sigma = 0.0
            else:
                candidate_scores = await _judge_desc_trials(candidate_tool, judge, trials)
                if not candidate_scores:
                    report.skipped.append(f"{tool.name}:{dim}:no_candidate_scores")
                    continue
                candidate_score_val = statistics.mean(candidate_scores)
                candidate_sigma = (
                    statistics.stdev(candidate_scores) if len(candidate_scores) >= 2 else 0.0
                )

            # ── Accept/reject decision ────────────────────────────────────────
            baseline_mean = statistics.mean(baseline_scores)
            candidate_mean = statistics.mean(candidate_scores)
            delta = candidate_mean - baseline_mean

            if mode == ValidationMode.DETERMINISTIC:
                threshold = min_delta
            else:
                threshold = max(baseline_sigma, min_delta)

            accepted = delta > threshold
            rejection_reason = ""
            if not accepted:
                if delta <= 0:
                    rejection_reason = f"no improvement (delta={delta:+.1f})"
                elif delta <= threshold:
                    rejection_reason = (
                        f"delta={delta:+.1f} does not exceed threshold={threshold:.1f} "
                        f"(sigma={baseline_sigma:.1f}, min_delta={min_delta:.1f})"
                    )

            candidate = FixCandidate(
                tool_name=tool.name,
                dim=dim,
                mode=mode,
                baseline_score=baseline_mean,
                baseline_sigma=baseline_sigma,
                candidate_score=candidate_mean,
                candidate_sigma=candidate_sigma,
                delta=delta,
                threshold=threshold,
                accepted=accepted,
                rejection_reason=rejection_reason,
                new_description=new_desc,
                new_schema_props=new_props,
            )

            if accepted:
                report.accepted.append(candidate)
            else:
                report.rejected.append(candidate)

    # ── Apply accepted fixes to source ────────────────────────────────────────
    source = source_path.read_text(encoding="utf-8")
    patched = source

    for candidate in report.accepted:
        if candidate.dim == "description_quality" and candidate.new_description:
            patched = _patch_source_description(
                patched, candidate.tool_name, candidate.new_description
            )
        elif candidate.dim == "schema_completeness" and candidate.new_schema_props:
            patched = _patch_source_schema_props(
                patched, candidate.tool_name, candidate.new_schema_props
            )

    if report.accepted:
        diff_lines = list(
            difflib.unified_diff(
                source.splitlines(keepends=True),
                patched.splitlines(keepends=True),
                fromfile=str(source_path),
                tofile=str(source_path) + " (auto-fixed)",
            )
        )
        report.diff_text = "".join(diff_lines)
        report.patched_source = patched

    return report
