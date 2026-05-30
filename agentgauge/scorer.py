from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp.types import Tool

from agentgauge.providers import Message, Provider

if TYPE_CHECKING:
    from agentgauge.client import MCPClient, ToolCallResult
    from agentgauge.runner import RunResult


@dataclass
class DimensionScore:
    name: str
    score: float  # 0-100
    details: dict[str, Any] = field(default_factory=dict)
    fix_hints: list[str] = field(default_factory=list)


@dataclass
class ScoredReport:
    overall: float
    dimensions: list[DimensionScore]
    tool_count: int


# Weights must sum to 1.0
DIMENSION_WEIGHTS: dict[str, float] = {
    "schema_completeness": 0.25,
    "description_quality": 0.25,
    "discoverability": 0.15,
    "selection_accuracy": 0.15,
    "call_correctness": 0.10,
    "error_legibility": 0.05,
    "robustness": 0.03,
    "docs_manifest": 0.02,
}


def score_schema_completeness(tools: list[Tool]) -> DimensionScore:
    """Static analysis — no LLM needed."""
    if not tools:
        return DimensionScore(
            name="schema_completeness",
            score=0.0,
            details={"reason": "no tools"},
            fix_hints=["Add tools to your MCP server"],
        )

    total_params = 0
    scored_params = 0
    fix_hints: list[str] = []

    for tool in tools:
        schema = tool.inputSchema or {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        if not properties:
            fix_hints.append(f"Tool '{tool.name}': add parameter definitions to inputSchema")
            continue

        for param_name, param_schema in properties.items():
            total_params += 1
            param_score = 0

            if param_schema.get("description"):
                param_score += 1
            else:
                fix_hints.append(f"Tool '{tool.name}', param '{param_name}': add a description")

            if param_schema.get("type"):
                param_score += 1
            else:
                fix_hints.append(f"Tool '{tool.name}', param '{param_name}': add a type")

            if param_name in required or param_schema.get("default") is not None:
                param_score += 1

            scored_params += param_score

    raw = 0.0 if total_params == 0 else (scored_params / (total_params * 3)) * 100

    return DimensionScore(
        name="schema_completeness",
        score=round(raw, 1),
        details={"total_params": total_params, "scored_params": scored_params},
        fix_hints=fix_hints[:5],  # cap noise
    )


async def score_description_quality(
    tools: list[Tool], provider: Provider, *, trials: int = 1
) -> DimensionScore:
    """LLM-as-judge: ask the provider to rate each tool description 0-10."""
    if not tools:
        return DimensionScore(
            name="description_quality",
            score=0.0,
            details={"reason": "no tools"},
            fix_hints=["Add tools with descriptions to your MCP server"],
        )

    scores_by_tool: dict[str, list[float]] = {}
    fix_hints: list[str] = []

    for tool in tools:
        tool_scores: list[float] = []
        for trial_idx in range(trials):
            prompt = (
                f"Rate this MCP tool description on a scale of 0-10 for clarity and completeness "
                f"for an AI agent. Reply with ONLY a number.\n\n"
                f"Tool name: {tool.name}\n"
                f"Description: {tool.description or '(none)'}\n"
                f"Input schema: {tool.inputSchema}"
            )
            resp = await provider.chat([Message(role="user", content=prompt)], seed=42 + trial_idx)
            match = re.search(r"\b(\d+(?:\.\d+)?)\b", resp)
            if match:
                raw_score = float(match.group(1))
                tool_scores.append(min(raw_score, 10.0))

        if tool_scores:
            avg = sum(tool_scores) / len(tool_scores)
            scores_by_tool[tool.name] = tool_scores
            if avg < 7.0:
                fix_hints.append(
                    f"Tool '{tool.name}' scored {avg:.1f}/10 — improve its description"
                )

    if not scores_by_tool:
        return DimensionScore(
            name="description_quality",
            score=0.0,
            details={},
            fix_hints=["Could not parse LLM scores"],
        )

    all_scores = [s for scores in scores_by_tool.values() for s in scores]
    overall = (sum(all_scores) / len(all_scores)) * 10  # 0-10 -> 0-100

    return DimensionScore(
        name="description_quality",
        score=round(overall, 1),
        details={"per_tool": {k: round(sum(v) / len(v), 2) for k, v in scores_by_tool.items()}},
        fix_hints=fix_hints[:5],
    )


def score_selection_accuracy(run_results: list[RunResult]) -> DimensionScore:
    """Score how often the agent picked the correct tool for each task."""
    if not run_results:
        return DimensionScore(
            name="selection_accuracy",
            score=0.0,
            details={"reason": "no run results"},
            fix_hints=["Run tasks to generate selection accuracy data"],
        )
    correct = sum(1 for r in run_results if r.selected_tool == r.task.tool_name)
    total = len(run_results)
    score = (correct / total) * 100
    return DimensionScore(
        name="selection_accuracy",
        score=round(score, 1),
        details={"correct": correct, "total": total},
        fix_hints=(
            ["Improve tool names and descriptions so agents can identify the right tool"]
            if score < 75
            else []
        ),
    )


def score_call_correctness(run_results: list[RunResult]) -> DimensionScore:
    """Score how often the agent's tool call succeeded (server accepted the arguments)."""
    if not run_results:
        return DimensionScore(
            name="call_correctness",
            score=0.0,
            details={"reason": "no run results"},
            fix_hints=["Run tasks to generate call correctness data"],
        )
    successful = sum(1 for r in run_results if r.success)
    total = len(run_results)
    score = (successful / total) * 100
    return DimensionScore(
        name="call_correctness",
        score=round(score, 1),
        details={"successful": successful, "total": total},
        fix_hints=(
            ["Improve parameter descriptions and examples so agents construct valid arguments"]
            if score < 75
            else []
        ),
    )


@dataclass
class ErrorProbe:
    label: str
    args: dict[str, Any]


def _error_probes(tool: Tool) -> list[ErrorProbe]:
    """Generate 2 bad-input cases for a tool derived from its JSON schema.

    Case 1 (when required params exist): empty args — triggers missing-required errors.
    Case 2 (when required params exist): wrong type on the first required param.
    Fallback (no required params): inject an unknown field.
    """
    schema = tool.inputSchema or {}
    properties: dict[str, Any] = schema.get("properties", {})
    required: list[str] = schema.get("required", [])

    if not required:
        return [ErrorProbe(label="unknown_param", args={"__bad_field__": True})]

    probes: list[ErrorProbe] = [ErrorProbe(label="missing_required", args={})]

    first = required[0]
    prop = properties.get(first, {})
    wrong: dict[str, Any] = {
        "string": 99999,
        "integer": "not_a_number",
        "number": "not_a_number",
        "boolean": [1, 2, 3],
        "array": "not_an_array",
        "object": 42,
    }
    bad_val: Any = wrong.get(prop.get("type", "string"))
    probes.append(ErrorProbe(label=f"wrong_type_{first}", args={first: bad_val}))

    return probes


def _extract_error_text(result: ToolCallResult) -> str:
    """Pull the human-readable error string out of a ToolCallResult."""
    if result.error:
        return result.error
    # Some servers return error content in the content list rather than raising.
    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            return str(text)
    return "(no error message returned)"


async def score_error_legibility(
    tools: list[Tool],
    client: MCPClient,
    provider: Provider,
    *,
    trials: int = 3,
) -> DimensionScore:
    """LLM-judge whether error responses are understandable and actionable to an agent.

    For each tool, injects 2 classes of bad input (missing required param, wrong type).
    Runs the judge `trials` times per case and aggregates mean + variance across all cases.
    """
    if not tools:
        return DimensionScore(
            name="error_legibility",
            score=0.0,
            details={"reason": "no tools"},
            fix_hints=["Add tools to your MCP server"],
        )

    all_case_means: list[float] = []
    all_variances: list[float] = []
    per_tool: dict[str, float] = {}
    fix_hints: list[str] = []

    for tool in tools:
        probes = _error_probes(tool)
        tool_case_means: list[float] = []

        for probe in probes:
            result = await client.call_tool_with_bad_input(tool.name, probe.args)
            error_text = _extract_error_text(result)

            judge_scores: list[float] = []
            for trial_idx in range(trials):
                # Rubric calibration note (llama3.1:8b, 2026-05-31):
                # The 5-6 anchor for "diagnosis-only" is the INTENDED target but
                # is aspirational: llama3.1:8b rates such errors at ~7/10 (~70/100).
                # The dimension guarantees ORDERING (what+how > diag > opaque) and
                # ACTIONABILITY GAP (~20 pts), not absolute band membership.
                # Revisit if the pinned judge model changes. See CLAUDE.md.
                prompt = (
                    f"An AI agent called MCP tool '{tool.name}' with invalid arguments "
                    f"and received the error below. Rate it 0-10 on TWO dimensions:\n"
                    f"(a) DIAGNOSIS — does it name what was wrong (which field, which type)?\n"
                    f"(b) ACTIONABILITY — does it state how to fix it (the corrective step)?\n\n"
                    f"Scoring guide:\n"
                    f"- 9-10: Names what was wrong AND states the corrective action "
                    f"(e.g. \"Required field 'user_id' (string) is missing — add it and retry\")\n"
                    f"- 5-6: Names the failing field/type but gives NO corrective instruction "
                    f"(e.g. \"Required field 'user_id' (string) is missing.\")\n"
                    f"- 3-4: Vague — something failed but not which field or why "
                    f'(e.g. "Invalid input")\n'
                    f"- 0-2: No field-level information — bare status code, empty string, "
                    f'or stack trace. Score "Error 500" as 1, "Internal Server Error" as 1. '
                    f"Any response naming no specific field scores <= 2.\n\n"
                    f"Bad input used: {probe.args}\n"
                    f"Error response: {error_text!r}\n\n"
                    f"Reply with ONLY a number 0-10."
                )
                resp = await provider.chat(
                    [Message(role="user", content=prompt)], seed=42 + trial_idx
                )
                m = re.search(r"\b(\d+(?:\.\d+)?)\b", resp)
                if m:
                    judge_scores.append(min(float(m.group(1)), 10.0))

            if judge_scores:
                case_mean = sum(judge_scores) / len(judge_scores)
                case_var = sum((s - case_mean) ** 2 for s in judge_scores) / len(judge_scores)
                tool_case_means.append(case_mean)
                all_variances.append(case_var)

        if tool_case_means:
            tool_avg = sum(tool_case_means) / len(tool_case_means)
            per_tool[tool.name] = round(tool_avg * 10, 1)  # 0-10 → 0-100
            all_case_means.extend(tool_case_means)
            if tool_avg < 6.0:
                fix_hints.append(
                    f"Tool '{tool.name}' error messages scored {tool_avg:.1f}/10 — "
                    f"return structured errors that name the failing field, expected type, "
                    f"and corrective action (e.g. '— add it and retry')"
                )

    if not all_case_means:
        return DimensionScore(
            name="error_legibility",
            score=0.0,
            details={"reason": "no scores collected", "judge_trials": trials},
            fix_hints=fix_hints,
        )

    overall_mean = sum(all_case_means) / len(all_case_means)
    overall_score = round(overall_mean * 10, 1)  # 0-10 → 0-100
    avg_var = sum(all_variances) / len(all_variances) if all_variances else 0.0

    return DimensionScore(
        name="error_legibility",
        score=overall_score,
        details={
            "per_tool": per_tool,
            "judge_trials": trials,
            "avg_variance": round(avg_var, 4),
        },
        fix_hints=fix_hints[:5],
    )


def _stub_dimension(name: str) -> DimensionScore:
    return DimensionScore(
        name=name,
        score=0.0,
        details={"status": "not_implemented"},
        fix_hints=[f"{name} scoring is not yet implemented — see TASKS.md"],
    )


async def score_all(
    tools: list[Tool],
    provider: Provider,
    *,
    client: MCPClient | None = None,
    trials: int = 1,
) -> ScoredReport:
    from agentgauge.runner import run_tasks
    from agentgauge.tasks import generate_tasks

    schema = score_schema_completeness(tools)
    description = await score_description_quality(tools, provider, trials=trials)

    if client is not None:
        tasks = generate_tasks(tools)
        run_results = await run_tasks(tasks, client, provider, trials=trials)
        selection = score_selection_accuracy(run_results)
        correctness = score_call_correctness(run_results)
        error_leg = await score_error_legibility(tools, client, provider, trials=trials)
    else:
        selection = _stub_dimension("selection_accuracy")
        correctness = _stub_dimension("call_correctness")
        error_leg = _stub_dimension("error_legibility")

    dimensions = [
        schema,
        description,
        _stub_dimension("discoverability"),
        selection,
        correctness,
        error_leg,
        _stub_dimension("robustness"),
        _stub_dimension("docs_manifest"),
    ]

    dim_map = {d.name: d for d in dimensions}
    overall = sum(
        dim_map[name].score * weight
        for name, weight in DIMENSION_WEIGHTS.items()
        if name in dim_map
    )

    return ScoredReport(overall=round(overall, 1), dimensions=dimensions, tool_count=len(tools))
