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
    selected_tool: str | None
    constructed_args: dict[str, Any]
    success: bool
    error: str | None = None


def _build_tool_listing(tools: list[Tool]) -> str:
    """Format tools as a one-line-per-tool listing for the selection prompt.

    Shows name, description, and parameter names/types so the agent can distinguish
    tools by description — not just by name. This ensures arm A and arm B present
    different selection prompts when their descriptions differ (manipulation check).

    Format: '<name> — <description> | <param>:<type>, ...'
    """
    lines = []
    for tool in tools:
        desc = (tool.description or "(no description)").split("\n")[0]
        props = (tool.inputSchema or {}).get("properties", {})
        param_parts = []
        for pname, pschema in props.items():
            ptype = pschema.get("type", "")
            param_parts.append(f"{pname}:{ptype}" if ptype else pname)
        param_str = ", ".join(param_parts) if param_parts else "(no params)"
        lines.append(f"{tool.name} — {desc} | {param_str}")
    return "\n".join(lines)


async def run_tasks(
    tasks: list[Task],
    client: MCPClient,
    provider: Provider,
    *,
    trials: int = 1,
) -> list[RunResult]:
    """Ask the provider to select the right tool and construct arguments for each task.

    For each task, two prompts are sent:
    1. Select the tool name from the available tools (with descriptions + param types).
    2. Construct a JSON argument object for that tool.
    The tool is then called and the result recorded.
    """
    info = await client.introspect()
    tool_listing = _build_tool_listing(info.tools)
    tool_schema_map = {t.name: t.inputSchema for t in info.tools}

    results: list[RunResult] = []
    for task in tasks:
        for _ in range(trials):
            selection_resp = await provider.chat(
                [
                    Message(
                        role="user",
                        content=(
                            f"Available tools:\n{tool_listing}\n\n"
                            f"Task: {task.description}\n"
                            "Reply with ONLY the tool name to call, nothing else."
                        ),
                    )
                ]
            )
            selected_tool = selection_resp.strip().split()[0] if selection_resp.strip() else None

            schema = tool_schema_map.get(selected_tool or task.tool_name, {})
            args_resp = await provider.chat(
                [
                    Message(
                        role="user",
                        content=(
                            f"Tool: {selected_tool or task.tool_name}\n"
                            f"Schema: {schema}\n"
                            f"Task: {task.description}\n"
                            "Reply with ONLY a JSON object of arguments, nothing else."
                        ),
                    )
                ]
            )
            try:
                constructed_args: dict[str, Any] = json.loads(args_resp.strip())
            except (json.JSONDecodeError, ValueError):
                constructed_args = {}

            call_result = await client.call_tool(selected_tool or task.tool_name, constructed_args)
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
