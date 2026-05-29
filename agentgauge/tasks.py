from __future__ import annotations

from dataclasses import dataclass

from mcp.types import Tool


@dataclass
class Task:
    tool_name: str
    description: str
    # TODO: extend with generated inputs and expected outputs
    # See TASKS.md: task-generator item


def generate_tasks(tools: list[Tool]) -> list[Task]:
    """Stub — generates one basic task per tool. Full impl in TASKS.md backlog."""
    return [
        Task(
            tool_name=tool.name,
            description=f"Call the '{tool.name}' tool with valid arguments",
        )
        for tool in tools
    ]
