from __future__ import annotations

from mcp.types import Tool

from agentgauge.tasks import Task, generate_tasks


def _make_tool(name: str, description: str, schema: dict) -> Tool:
    return Tool(name=name, description=description, inputSchema=schema)


ECHO_TOOL = _make_tool(
    "echo",
    "Echo a message back",
    {
        "type": "object",
        "properties": {"message": {"type": "string", "description": "Text to echo"}},
        "required": ["message"],
    },
)

ADD_TOOL = _make_tool(
    "add",
    "Add two numbers together",
    {
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "First number"},
            "b": {"type": "integer", "description": "Second number"},
        },
        "required": ["a", "b"],
    },
)

NO_SCHEMA_TOOL = _make_tool("ping", "Ping the server", {"type": "object", "properties": {}})


def test_generate_tasks_one_per_tool() -> None:
    tasks = generate_tasks([ECHO_TOOL, ADD_TOOL])
    assert len(tasks) == 2


def test_generate_tasks_empty() -> None:
    assert generate_tasks([]) == []


def test_generate_tasks_tool_name() -> None:
    tasks = generate_tasks([ECHO_TOOL])
    assert tasks[0].tool_name == "echo"


def test_generate_tasks_description_mentions_tool() -> None:
    tasks = generate_tasks([ECHO_TOOL])
    assert "echo" in tasks[0].description.lower()


def test_generate_tasks_sample_args_string_param() -> None:
    tasks = generate_tasks([ECHO_TOOL])
    assert isinstance(tasks[0].sample_args, dict)
    assert "message" in tasks[0].sample_args
    assert isinstance(tasks[0].sample_args["message"], str)


def test_generate_tasks_sample_args_integer_param() -> None:
    tasks = generate_tasks([ADD_TOOL])
    assert tasks[0].sample_args["a"] == 1
    assert tasks[0].sample_args["b"] == 1


def test_generate_tasks_uses_required_params() -> None:
    tasks = generate_tasks([ECHO_TOOL])
    assert "message" in tasks[0].sample_args


def test_generate_tasks_no_schema_properties() -> None:
    tasks = generate_tasks([NO_SCHEMA_TOOL])
    assert tasks[0].sample_args == {}


def test_task_is_dataclass() -> None:
    task = Task(tool_name="foo", description="bar", sample_args={"x": 1})
    assert task.tool_name == "foo"
    assert task.sample_args == {"x": 1}


def test_task_default_sample_args() -> None:
    task = Task(tool_name="foo", description="bar")
    assert task.sample_args == {}
