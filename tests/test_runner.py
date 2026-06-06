from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from mcp.types import Tool

from agentgauge.client import MCPClient
from agentgauge.providers import Message, MockProvider
from agentgauge.runner import RunResult, _build_tool_listing, run_tasks
from agentgauge.tasks import Task


def _make_mock_client(tool_name: str = "echo", *, description: str = "Echo a message") -> MCPClient:
    session = MagicMock()

    tools_resp = MagicMock()
    tools_resp.tools = [
        Tool(
            name=tool_name,
            description=description,
            inputSchema={
                "type": "object",
                "properties": {"message": {"type": "string", "description": "Text"}},
                "required": ["message"],
            },
        )
    ]
    resources_resp = MagicMock()
    resources_resp.resources = []
    prompts_resp = MagicMock()
    prompts_resp.prompts = []

    session.list_tools = AsyncMock(return_value=tools_resp)
    session.list_resources = AsyncMock(return_value=resources_resp)
    session.list_prompts = AsyncMock(return_value=prompts_resp)

    call_resp = MagicMock()
    call_resp.content = [MagicMock(type="text", text="hello")]
    session.call_tool = AsyncMock(return_value=call_resp)

    return MCPClient(session)


# ── _build_tool_listing ────────────────────────────────────────────────────────


def test_build_tool_listing_includes_name_and_description() -> None:
    tools = [Tool(name="echo", description="Echo a message back.", inputSchema={})]
    listing = _build_tool_listing(tools)
    assert "echo" in listing
    assert "Echo a message back." in listing


def test_build_tool_listing_includes_param_types() -> None:
    tools = [
        Tool(
            name="add",
            description="Add two numbers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
            },
        )
    ]
    listing = _build_tool_listing(tools)
    assert "a:integer" in listing
    assert "b:integer" in listing


def test_build_tool_listing_no_description_fallback() -> None:
    tools = [Tool(name="foo", description=None, inputSchema={})]
    listing = _build_tool_listing(tools)
    assert "foo" in listing
    assert "(no description)" in listing


def test_build_tool_listing_no_params_fallback() -> None:
    tools = [Tool(name="bar", description="Do something.", inputSchema={})]
    listing = _build_tool_listing(tools)
    assert "(no params)" in listing


def test_build_tool_listing_differs_when_descriptions_differ() -> None:
    """Manipulation check: arm A and arm B must see different selection prompts.

    Run #2 was VOID because runner.py showed names only — arms A and B had identical
    prompts (b=0/c=0). This test asserts the listing now differs when descriptions differ.
    """
    tool_a = Tool(
        name="get_a",
        description="Get.",
        inputSchema={"type": "object", "properties": {"sid": {}}},
    )
    tool_b = Tool(
        name="get_a",
        description="Fetch a specific record by session ID and record ID.",
        inputSchema={"type": "object", "properties": {"sid": {}}},
    )
    listing_a = _build_tool_listing([tool_a])
    listing_b = _build_tool_listing([tool_b])

    assert listing_a != listing_b, "Selection listings must differ when descriptions differ"
    assert "Get." in listing_a
    assert "Fetch a specific record" in listing_b


def test_build_tool_listing_multiple_tools() -> None:
    tools = [
        Tool(name="t1", description="Do A.", inputSchema={}),
        Tool(name="t2", description="Do B.", inputSchema={}),
    ]
    listing = _build_tool_listing(tools)
    assert "t1" in listing
    assert "Do A." in listing
    assert "t2" in listing
    assert "Do B." in listing


# ── selection prompt manipulation check via run_tasks ─────────────────────────


async def test_selection_prompt_includes_tool_description() -> None:
    """Selection prompt must include the tool description (not just its name).

    This is the fix for run #2 void: the agent must see descriptions so arm A and arm B
    present different inputs when descriptions differ.
    """
    captured: list[str] = []

    class CapturingProvider:
        model_name = "capturing"
        _responses = ["echo", "{}"]
        _idx = 0

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.append(messages[0].content)
            resp = self._responses[self._idx % len(self._responses)]
            self._idx += 1
            return resp

    client = _make_mock_client("echo", description="Echo a message back to the caller.")
    provider = CapturingProvider()
    tasks = [Task(tool_name="echo", description="Send a test message", sample_args={})]

    await run_tasks(tasks, client, provider)

    selection_prompt = captured[0]
    assert "Echo a message back to the caller." in selection_prompt, (
        "Tool description must appear in selection prompt (manipulation check)"
    )
    assert "echo" in selection_prompt


async def test_selection_prompts_differ_between_vague_and_informative_descriptions() -> None:
    """Arm A (vague) and arm B (informative) must produce different selection prompts.

    Concretely tests that the run #2 void condition no longer holds: when two clients
    serve the same tool names with different descriptions, run_tasks sends different
    prompts to the agent.
    """
    prompts_a: list[str] = []
    prompts_b: list[str] = []

    class CaptureA:
        model_name = "capture-a"
        _responses = ["get_a", "{}"]
        _idx = 0

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            prompts_a.append(messages[0].content)
            resp = self._responses[self._idx % len(self._responses)]
            self._idx += 1
            return resp

    class CaptureB:
        model_name = "capture-b"
        _responses = ["get_a", "{}"]
        _idx = 0

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            prompts_b.append(messages[0].content)
            resp = self._responses[self._idx % len(self._responses)]
            self._idx += 1
            return resp

    client_a = _make_mock_client("get_a", description="Get.")
    client_b = _make_mock_client(
        "get_a", description="Fetch a specific record by session and record ID."
    )
    tasks = [
        Task(tool_name="get_a", description="Retrieve record r-001 from session 1", sample_args={})
    ]

    await run_tasks(tasks, client_a, CaptureA())
    await run_tasks(tasks, client_b, CaptureB())

    assert prompts_a[0] != prompts_b[0], (
        "Selection prompts must differ when tool descriptions differ "
        "(run #2 was VOID because this assertion would have failed)"
    )
    assert "Get." in prompts_a[0]
    assert "Fetch a specific record" in prompts_b[0]


# ── run_tasks core behavior ───────────────────────────────────────────────────


async def test_run_tasks_returns_run_results() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", '{"message": "example"}'])
    tasks = [
        Task(
            tool_name="echo",
            description="Call echo: Echo a message",
            sample_args={"message": "example"},
        )
    ]

    results = await run_tasks(tasks, client, provider)

    assert len(results) == 1
    assert isinstance(results[0], RunResult)
    assert results[0].selected_tool == "echo"
    assert results[0].success is True


async def test_run_tasks_multiple_trials() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", "{}"])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider, trials=2)
    assert len(results) == 2


async def test_run_tasks_invalid_json_args_uses_empty_dict() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", "not valid json"])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].constructed_args == {}
    assert results[0].parse_failed is True


async def test_run_tasks_fenced_json_parsed_correctly() -> None:
    client = _make_mock_client("echo")
    fenced = '```json\n{"message": "hello"}\n```'
    provider = MockProvider(responses=["echo", fenced])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].constructed_args == {"message": "hello"}
    assert results[0].parse_failed is False


async def test_run_tasks_json_with_preamble_parsed_correctly() -> None:
    client = _make_mock_client("echo")
    preamble = 'Sure, here are the args: {"message": "world"}'
    provider = MockProvider(responses=["echo", preamble])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].constructed_args == {"message": "world"}
    assert results[0].parse_failed is False


async def test_run_tasks_bare_json_not_flagged() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", '{"message": "bare"}'])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].constructed_args == {"message": "bare"}
    assert results[0].parse_failed is False


async def test_run_tasks_tool_call_failure() -> None:
    client = _make_mock_client("echo")
    client._session.call_tool = AsyncMock(side_effect=RuntimeError("bad call"))
    provider = MockProvider(responses=["echo", "{}"])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].success is False
    assert results[0].error is not None


async def test_run_tasks_empty_tasks() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", "{}"])

    results = await run_tasks([], client, provider)
    assert results == []


async def test_run_tasks_selected_tool_recorded() -> None:
    client = _make_mock_client("echo")
    provider = MockProvider(responses=["echo", '{"message": "hi"}'])
    tasks = [Task(tool_name="echo", description="Call echo", sample_args={})]

    results = await run_tasks(tasks, client, provider)
    assert results[0].selected_tool == "echo"
    assert results[0].constructed_args == {"message": "hi"}
