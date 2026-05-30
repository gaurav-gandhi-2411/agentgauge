from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp.types import Tool


@dataclass
class Task:
    tool_name: str
    description: str
    sample_args: dict[str, Any] = field(default_factory=dict)


def _sample_value(param_schema: dict[str, Any]) -> Any:
    """Return a representative sample value for a single parameter schema."""
    if param_schema.get("enum"):
        return param_schema["enum"][0]
    type_ = param_schema.get("type", "string")
    if type_ == "string":
        return "example"
    if type_ in ("integer", "number"):
        minimum = param_schema.get("minimum")
        return int(minimum) if minimum is not None else 0
    if type_ == "boolean":
        return True
    if type_ == "array":
        return []
    if type_ == "object":
        return {}
    return None


def generate_tasks(tools: list[Tool]) -> list[Task]:
    """Generate one Task per tool with a synthesized description and sample args from the schema."""
    tasks: list[Task] = []
    for tool in tools:
        schema = tool.inputSchema or {}
        properties: dict[str, Any] = schema.get("properties", {})
        sample_args = {name: _sample_value(prop) for name, prop in properties.items()}
        description = (
            f"Call '{tool.name}': {tool.description}"
            if tool.description
            else f"Call the '{tool.name}' tool."
        )
        tasks.append(Task(tool_name=tool.name, description=description, sample_args=sample_args))
    return tasks
