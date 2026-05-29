from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp.types import Tool


@dataclass
class Task:
    tool_name: str
    description: str
    sample_args: dict[str, Any] = field(default_factory=dict)


def _sample_value(schema: dict[str, Any]) -> Any:
    """Generate a representative sample value from a JSON schema property."""
    t = schema.get("type", "")
    if t == "string":
        return str(schema.get("example", schema.get("default", "example")))
    if t in ("integer", "int"):
        return int(schema.get("example", schema.get("default", 42)))
    if t == "number":
        return float(schema.get("example", schema.get("default", 3.14)))
    if t == "boolean":
        return bool(schema.get("default", True))
    if t == "array":
        return list(schema.get("default", []))
    if t == "object":
        return dict(schema.get("default", {}))
    return None


def _synthesize_description(tool: Tool) -> str:
    """Produce a natural-language task description from tool metadata."""
    if tool.description:
        return tool.description.rstrip(".") + "."
    readable = tool.name.replace("_", " ").replace("-", " ")
    return f"Use the {readable} capability."


def generate_tasks(tools: list[Tool]) -> list[Task]:
    """Generate one Task per tool with a natural description and sample arguments."""
    tasks: list[Task] = []
    for tool in tools:
        schema = tool.inputSchema or {}
        properties: dict[str, Any] = schema.get("properties", {})
        sample_args = {name: _sample_value(prop) for name, prop in properties.items()}
        tasks.append(
            Task(
                tool_name=tool.name,
                description=_synthesize_description(tool),
                sample_args=sample_args,
            )
        )
    return tasks
