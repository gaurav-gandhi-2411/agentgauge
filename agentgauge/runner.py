from __future__ import annotations

from dataclasses import dataclass

from agentgauge.client import MCPClient
from agentgauge.providers import Provider
from agentgauge.tasks import Task


@dataclass
class RunResult:
    task: Task
    success: bool
    error: str | None = None
    # TODO: extend with LLM-selected tool name, constructed args, etc.
    # See TASKS.md: agent-runner item


async def run_tasks(
    tasks: list[Task],
    client: MCPClient,
    provider: Provider,
    *,
    trials: int = 1,
) -> list[RunResult]:
    """Stub — full agent runner in TASKS.md backlog."""
    results: list[RunResult] = []
    for task in tasks:
        # TODO: have provider select and call the right tool
        result = await client.call_tool(task.tool_name, {})
        results.append(RunResult(task=task, success=result.success, error=result.error))
    return results
