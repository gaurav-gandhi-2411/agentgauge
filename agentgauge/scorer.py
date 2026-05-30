from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp.types import Tool

from agentgauge.providers import Message, Provider

if TYPE_CHECKING:
    from agentgauge.client import MCPClient
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
        for _ in range(trials):
            prompt = (
                f"Rate this MCP tool description on a scale of 0-10 for clarity and completeness "
                f"for an AI agent. Reply with ONLY a number.\n\n"
                f"Tool name: {tool.name}\n"
                f"Description: {tool.description or '(none)'}\n"
                f"Input schema: {tool.inputSchema}"
            )
            resp = await provider.chat([Message(role="user", content=prompt)])
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
    else:
        selection = _stub_dimension("selection_accuracy")
        correctness = _stub_dimension("call_correctness")

    dimensions = [
        schema,
        description,
        _stub_dimension("discoverability"),
        selection,
        correctness,
        _stub_dimension("error_legibility"),
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
