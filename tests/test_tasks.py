from __future__ import annotations

from mcp.types import Tool

from agentgauge.tasks import Task, _sample_value, generate_tasks


def _make_tool(name: str, description: str, schema: dict) -> Tool:
    return Tool(name=name, description=description, inputSchema=schema)


ECHO_TOOL = _make_tool(
    "echo",
    "Echo a message back",
    {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Text to echo"},
            "count": {"type": "integer", "description": "Number of times"},
        },
        "required": ["message"],
    },
)

NO_DESC_TOOL = _make_tool("ping", "", {"type": "object", "properties": {}})


def test_generate_tasks_one_per_tool() -> None:
    tasks = generate_tasks([ECHO_TOOL, NO_DESC_TOOL])
    assert len(tasks) == 2
    assert all(isinstance(t, Task) for t in tasks)


def test_generate_tasks_tool_name() -> None:
    tasks = generate_tasks([ECHO_TOOL])
    assert tasks[0].tool_name == "echo"


def test_generate_tasks_description_nonempty() -> None:
    tasks = generate_tasks([ECHO_TOOL, NO_DESC_TOOL])
    for task in tasks:
        assert task.description


def test_generate_tasks_sample_args_from_schema() -> None:
    tasks = generate_tasks([ECHO_TOOL])
    assert "message" in tasks[0].sample_args
    assert tasks[0].sample_args["message"] == "example"
    assert "count" in tasks[0].sample_args
    assert tasks[0].sample_args["count"] == 0


def test_generate_tasks_empty() -> None:
    assert generate_tasks([]) == []


def test_generate_tasks_no_desc_tool_description_contains_name() -> None:
    tasks = generate_tasks([NO_DESC_TOOL])
    assert "ping" in tasks[0].description


def test_sample_value_enum() -> None:
    assert _sample_value({"enum": ["a", "b"]}) == "a"


def test_sample_value_string() -> None:
    assert _sample_value({"type": "string"}) == "example"


def test_sample_value_integer_with_minimum() -> None:
    assert _sample_value({"type": "integer", "minimum": 5}) == 5


def test_sample_value_integer_no_minimum() -> None:
    assert _sample_value({"type": "integer"}) == 0


def test_sample_value_boolean() -> None:
    assert _sample_value({"type": "boolean"}) is True


def test_sample_value_array() -> None:
    assert _sample_value({"type": "array"}) == []


def test_sample_value_object() -> None:
    assert _sample_value({"type": "object"}) == {}


def test_sample_value_unknown_type() -> None:
    assert _sample_value({"type": "null"}) is None
