from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

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


def _parse_tool_selection(response: str) -> tuple[str | None, dict[str, Any] | None]:
    """Extract tool name and args from a provider response containing JSON."""
    text = response.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "tool" in data:
            args = data.get("args")
            return str(data["tool"]), dict(args) if isinstance(args, dict) else {}
    except (json.JSONDecodeError, ValueError):
        pass

    for match in re.finditer(r"\{", text):
        start = match.start()
        depth = 0
        end = start
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            try:
                data = json.loads(text[start:end])
                if isinstance(data, dict) and "tool" in data:
                    args = data.get("args")
                    return str(data["tool"]), dict(args) if isinstance(args, dict) else {}
            except (json.JSONDecodeError, ValueError):
                pass

    return None, None


async def run_tasks(
    tasks: list[Task],
    client: MCPClient,
    provider: Provider,
    *,
    trials: int = 1,
) -> list[RunResult]:
    """Ask provider to select and call the right tool; returns trials × len(tasks) results."""
    results: list[RunResult] = []
    tool_names = [t.tool_name for t in tasks]
    tool_list_json = json.dumps(tool_names)

    for task in tasks:
        prompt = (
            f"You are evaluating an MCP server. Given the task description and list of available "
            f"tools, select the most appropriate tool and construct valid call arguments.\n\n"
            f"Task: {task.description}\n\n"
            f"Available tools: {tool_list_json}\n\n"
            f'Respond with ONLY valid JSON: {{"tool": "<tool_name>", "args": {{...}}}}'
        )

        for _ in range(trials):
            resp = await provider.chat([Message(role="user", content=prompt)])
            selected_tool, constructed_args = _parse_tool_selection(resp)

            if selected_tool is None:
                results.append(
                    RunResult(
                        task=task,
                        selected_tool=None,
                        constructed_args=None,
                        success=False,
                        error="Provider response was not parseable as JSON tool selection",
                    )
                )
                continue

            call_result = await client.call_tool(selected_tool, constructed_args or {})
            results.append(
                RunResult(
                    task=task,
                    selected_tool=selected_tool,
                    constructed_args=constructed_args,
                    success=call_result.success,
                    error=call_result.error,
                )
            )

    return results
