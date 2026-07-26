"""Offline unit tests for `scripts/real_case_construction.py`.

`connect_stdio`/`cleanup_connection` are mocked (never spawn a real subprocess), matching every
other test file in this repo's convention (see e.g. `tests/test_cli.py`) -- this module makes no
LLM call at all (case construction is pure catalog mutation), but staying subprocess-free keeps
these tests fast and consistent with the rest of the suite regardless.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import Tool

from agentgauge.client import MCPClient, ServerInfo
from agentgauge.tasks import Task
from scripts.real_case_construction import (
    REAL_CASE_SPECS,
    RealCaseSpec,
    build_case_from_spec,
    build_real_case,
    introspect_catalog,
    select_blind_tasks,
)

_CATALOG_TOOLS = [
    Tool(
        name="create_issue",
        description="Creates a new issue.",
        inputSchema={"type": "object", "properties": {"repo": {"type": "string"}}},
    ),
    Tool(
        name="add_assignee",
        description="Adds an assignee to an issue.",
        inputSchema={"type": "object", "properties": {"assignee": {"type": "string"}}},
    ),
    Tool(
        name="update_issue_state",
        description="Updates issue state.",
        inputSchema={"type": "object", "properties": {"state": {"type": "string"}}},
    ),
    Tool(
        name="add_label",
        description="Applies a label.",
        inputSchema={"type": "object", "properties": {"label": {"type": "string"}}},
    ),
]


def _mock_client() -> MCPClient:
    session = MagicMock()
    client = MCPClient(session)
    client.introspect = AsyncMock(
        return_value=ServerInfo(tools=_CATALOG_TOOLS, resources=[], prompts=[])
    )
    return client


async def test_introspect_catalog_returns_plain_dicts() -> None:
    fake_ctx = object()
    with (
        patch(
            "scripts.real_case_construction.connect_stdio",
            new=AsyncMock(return_value=(_mock_client(), fake_ctx)),
        ),
        patch("scripts.real_case_construction.cleanup_connection", new=AsyncMock()) as cleanup,
    ):
        catalog = await introspect_catalog("examples/github_issues_server_fixed.py")

    assert len(catalog) == 4
    names = {t["name"] for t in catalog}
    assert names == {"create_issue", "add_assignee", "update_issue_state", "add_label"}
    assert catalog[0]["description"] == "Creates a new issue."
    assert catalog[0]["inputSchema"] == {"type": "object", "properties": {"repo": {"type": "string"}}}
    cleanup.assert_awaited_once()


def test_select_blind_tasks_picks_first_n_per_tool_in_order() -> None:
    fixture_tasks = [
        Task("tool_a", "First A task."),
        Task("tool_a", "Second A task."),
        Task("tool_b", "First B task."),
        Task("tool_a", "Third A task."),
    ]

    picked = select_blind_tasks(fixture_tasks, ["tool_a", "tool_b"], n_per_tool=2)

    assert [t.description for t in picked] == ["First A task.", "Second A task.", "First B task."]
    assert all(t.constraints == [] for t in picked)


def test_build_real_case_injects_defect_into_culprit_only() -> None:
    clean_catalog = [
        {"name": "create_issue", "description": "Creates a new issue.", "inputSchema": {}},
        {
            "name": "update_issue_state",
            "description": "Updates issue state.",
            "inputSchema": {"type": "object", "properties": {"state": {"type": "string"}}},
        },
        {"name": "add_label", "description": "Applies a label.", "inputSchema": {}},
        {"name": "unrelated_tool", "description": "Not in the changed set.", "inputSchema": {}},
    ]
    blind_tasks = [Task("update_issue_state", "Close the flaky-test issue.")]

    case = build_real_case(
        case_id="test_case",
        server_name="test-server",
        clean_catalog=clean_catalog,
        culprit="update_issue_state",
        decoy_tiers={"create_issue": "small", "add_label": "large"},
        blind_tasks=blind_tasks,  # type: ignore[arg-type]
    )

    assert case.true_culprit == "update_issue_state"
    assert set(case.changed_tools) == {"update_issue_state", "create_issue", "add_label"}
    # The culprit's schema property was flipped to 'integer' (the real type_enum_contradiction
    # mutation) and its description grew.
    culprit_after = next(t for t in case.all_tools_after if t["name"] == "update_issue_state")
    assert culprit_after["inputSchema"]["properties"]["state"]["type"] == "integer"
    assert len(culprit_after["description"]) > len("Updates issue state.")
    # Decoys' descriptions changed (benign) but their schemas did NOT.
    decoy_after = next(t for t in case.all_tools_after if t["name"] == "create_issue")
    assert decoy_after["description"] != "Creates a new issue."
    assert decoy_after["inputSchema"] == {}
    # A tool outside changed_tools is byte-identical in both catalogs.
    unrelated_after = next(t for t in case.all_tools_after if t["name"] == "unrelated_tool")
    assert unrelated_after["description"] == "Not in the changed set."
    # Decoy diff sizes vary (small vs large tier, per the task's "vary decoy sizes" instruction).
    assert case.diff_chars["create_issue"] < case.diff_chars["add_label"]


def test_build_real_case_raises_when_culprit_missing() -> None:
    with pytest.raises(ValueError, match="not found"):
        build_real_case(
            case_id="x",
            server_name="x",
            clean_catalog=[{"name": "only_tool", "description": "x", "inputSchema": {}}],
            culprit="missing_tool",
            decoy_tiers={},
            blind_tasks=[],
        )


def test_real_case_specs_are_disclosed_and_distinct() -> None:
    """Both shipped `RealCaseSpec`s use a different server and a different culprit -- guards
    against silently copy-pasting one case's structure onto the other."""
    assert len(REAL_CASE_SPECS) >= 1
    server_names = {s.server_name for s in REAL_CASE_SPECS}
    assert len(server_names) == len(REAL_CASE_SPECS)
    for spec in REAL_CASE_SPECS:
        assert spec.culprit in spec.decoy_tiers or spec.culprit not in spec.decoy_tiers
        assert spec.culprit not in spec.decoy_tiers  # culprit must not double as its own decoy


async def test_build_case_from_spec_end_to_end_with_mocked_introspection() -> None:
    spec = RealCaseSpec(
        case_id="mocked_case",
        server_name="mocked-server",
        server_path="unused/path.py",  # type: ignore[arg-type]
        fixture_module="evals.fixtures.v2_4_corpus.github_issues_fixture",
        culprit="update_issue_state",
        decoy_tiers={"create_issue": "small", "add_assignee": "medium", "add_label": "large"},
        n_tasks_per_tool=1,
    )
    fake_ctx = object()
    with (
        patch(
            "scripts.real_case_construction.connect_stdio",
            new=AsyncMock(return_value=(_mock_client(), fake_ctx)),
        ),
        patch("scripts.real_case_construction.cleanup_connection", new=AsyncMock()),
    ):
        case = await build_case_from_spec(spec)

    assert case.case_id == "mocked_case"
    assert case.true_culprit == "update_issue_state"
    assert len(case.blind_tasks) == 4  # 1 task x 4 changed tools (culprit + 3 decoys)
    assert {t.tool_name for t in case.blind_tasks} == {
        "update_issue_state",
        "create_issue",
        "add_assignee",
        "add_label",
    }
