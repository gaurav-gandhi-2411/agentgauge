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
    t = schema.get("type")
    if t == "string":
        return "example"
    if t in ("integer", "number"):
        return 1
    if t == "boolean":
        return True
    if t == "array":
        return []
    if t == "object":
        return {}
    return "sample"


def _derive_sample_args(input_schema: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = input_schema.get("properties", {})
    required: set[str] = set(input_schema.get("required", []))
    selected = {k: v for k, v in props.items() if k in required} or props
    return {name: _sample_value(schema) for name, schema in selected.items()}


def _synthesize_description(tool: Tool) -> str:
    if tool.description:
        desc = tool.description.rstrip(".")
        return f"Use the '{tool.name}' tool to {desc[0].lower() + desc[1:]}"
    return f"Use the '{tool.name}' tool with valid arguments"


def generate_tasks(tools: list[Tool]) -> list[Task]:
    return [
        Task(
            tool_name=tool.name,
            description=_synthesize_description(tool),
            sample_args=_derive_sample_args(tool.inputSchema or {}),
        )
        for tool in tools
    ]
