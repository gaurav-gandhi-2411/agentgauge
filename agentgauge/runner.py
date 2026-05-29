from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mcp.types import Tool

from agentgauge.client import MCPClient
from agentgauge.providers import Message, Provider
from agentgauge.tasks import Task


@dataclass
class RunResult:
    task: Task
    success: bool
    selected_tool: str | None = None
    constructed_args: dict[str, Any] | None = None
    error: str | None = None


def _build_selection_prompt(task: Task, tools: list[Tool]) -> str:
    tool_lines = "\n".join(f"- {t.name}: {t.description or '(no description)'}" for t in tools)
    return (
        f"{task.description}\n\n"
        f"Available tools:\n{tool_lines}\n\n"
        'Respond with ONLY valid JSON: {"tool_name": "<name>", "arguments": {<key: value>}}'
    )


def _parse_selection_response(response: str) -> tuple[str | None, dict[str, Any] | None]:
    """Extract tool_name and arguments from an LLM JSON response."""
    start = response.find("{")
    end = response.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, None
    try:
        data = json.loads(response[start : end + 1])
    except json.JSONDecodeError:
        return None, None
    tool_name = data.get("tool_name")
    arguments = data.get("arguments", {})
    if isinstance(tool_name, str) and isinstance(arguments, dict):
        return tool_name, arguments
    return None, None


async def run_tasks(
    tasks: list[Task],
    client: MCPClient,
    provider: Provider,
    tools: list[Tool],
    *,
    trials: int = 1,
) -> list[RunResult]:
    """Ask the provider to select and call the right tool for each task description."""
    results: list[RunResult] = []
    for task in tasks:
        prompt = _build_selection_prompt(task, tools)
        selected_tool: str | None = None
        constructed_args: dict[str, Any] | None = None

        for _ in range(trials):
            response = await provider.chat([Message(role="user", content=prompt)])
            tool_name, arguments = _parse_selection_response(response)
            if tool_name is not None:
                selected_tool = tool_name
                constructed_args = arguments
                break

        if selected_tool is None:
            results.append(
                RunResult(
                    task=task,
                    success=False,
                    error="Provider did not return a valid tool selection",
                )
            )
            continue

        call_result = await client.call_tool(selected_tool, constructed_args or {})
        results.append(
            RunResult(
                task=task,
                success=call_result.success,
                selected_tool=selected_tool,
                constructed_args=constructed_args,
                error=call_result.error,
            )
        )
    return results
