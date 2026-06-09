from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.types import Tool

from evals.fixtures.rw1_github_catalog import (
    ALL_TOOLS,
    ARM_A_DESCRIPTIONS,
    ARM_O_DESCRIPTIONS,
    DESTRUCTIVE_CONFUSABLE_PAIRS,
    DESTRUCTIVE_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    GITHUB_DOCSTRINGS,
    GITHUB_HAND_FIXED_FAMILIES,
    MIRROR_DOCSTRING_SIGNALS,
    TASKS,
    TOOL_SCHEMAS,
    get_mirror_source,
)

# ── Fixture size and structure ─────────────────────────────────────────────────


def test_rw1_tool_count() -> None:
    assert len(ALL_TOOLS) == 21, f"Expected 21 tools, got {len(ALL_TOOLS)}"


def test_rw1_families_defined() -> None:
    expected = {
        "pr_read_family",
        "search_family",
        "file_ops_family",
        "list_family",
        "repo_ops_family",
    }
    assert set(FAMILIES.keys()) == expected


def test_rw1_pr_read_family_size() -> None:
    assert len(FAMILIES["pr_read_family"]) == 6


def test_rw1_search_family_size() -> None:
    assert len(FAMILIES["search_family"]) == 4


def test_rw1_file_ops_family_size() -> None:
    assert len(FAMILIES["file_ops_family"]) == 3


def test_rw1_list_family_size() -> None:
    assert len(FAMILIES["list_family"]) == 4


def test_rw1_repo_ops_family_size() -> None:
    assert len(FAMILIES["repo_ops_family"]) == 4


def test_rw1_family_map_covers_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in FAMILY_MAP, f"'{tool}' missing from FAMILY_MAP"


def test_rw1_family_map_is_consistent() -> None:
    for tool, family in FAMILY_MAP.items():
        assert tool in FAMILIES[family], (
            f"FAMILY_MAP[{tool!r}]={family!r} inconsistent with FAMILIES"
        )


# ── Schema completeness ────────────────────────────────────────────────────────


def test_rw1_all_tools_have_schemas() -> None:
    for tool in ALL_TOOLS:
        assert tool in TOOL_SCHEMAS, f"'{tool}' missing from TOOL_SCHEMAS"
        schema = TOOL_SCHEMAS[tool]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_rw1_all_schemas_have_required() -> None:
    for tool, schema in TOOL_SCHEMAS.items():
        assert "required" in schema, f"'{tool}' schema missing 'required' field"
        assert len(schema["required"]) >= 1, f"'{tool}' has empty required list"


def test_rw1_pr_family_share_owner_repo_pullnumber() -> None:
    """All pr_read_family tools (inc. merge) must require owner, repo, pullNumber."""
    for tool in FAMILIES["pr_read_family"]:
        required = set(TOOL_SCHEMAS[tool]["required"])
        assert {"owner", "repo", "pullNumber"} <= required, (
            f"{tool}: expected owner/repo/pullNumber in required, got {required}"
        )


def test_rw1_search_family_share_query_schema() -> None:
    """All search_family tools must have an identical top-level required=[query]."""
    for tool in FAMILIES["search_family"]:
        required = TOOL_SCHEMAS[tool]["required"]
        assert required == ["query"], f"{tool}: expected required=['query'], got {required}"
        props = TOOL_SCHEMAS[tool]["properties"]
        assert "query" in props


def test_rw1_file_ops_family_share_owner_repo() -> None:
    for tool in FAMILIES["file_ops_family"]:
        required = set(TOOL_SCHEMAS[tool]["required"])
        assert {"owner", "repo"} <= required, f"{tool}: missing owner/repo in required"


def test_rw1_repo_ops_family_all_have_schemas() -> None:
    for tool in FAMILIES["repo_ops_family"]:
        assert TOOL_SCHEMAS[tool]["type"] == "object"


# ── Descriptions ──────────────────────────────────────────────────────────────


def test_rw1_github_docstrings_cover_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in GITHUB_DOCSTRINGS
        assert len(GITHUB_DOCSTRINGS[tool]) > 0, f"'{tool}' has empty GitHub docstring"


def test_rw1_arm_a_equals_github_docstrings() -> None:
    """Arm A uses the real GitHub docstrings, not empty strings."""
    assert ARM_A_DESCRIPTIONS == GITHUB_DOCSTRINGS


def test_rw1_arm_a_all_nonempty() -> None:
    """Arm A is NOT empty — this is the external-validity test."""
    for tool in ALL_TOOLS:
        assert ARM_A_DESCRIPTIONS[tool] != "", (
            f"Arm A description for '{tool}' should not be empty — "
            "Arm A uses real GitHub docstrings"
        )


def test_rw1_arm_o_covers_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in ARM_O_DESCRIPTIONS, f"'{tool}' missing from ARM_O_DESCRIPTIONS"
        assert len(ARM_O_DESCRIPTIONS[tool]) > 20, f"Oracle description for '{tool}' too short"


def test_rw1_arm_o_longer_than_arm_a() -> None:
    """Oracle descriptions should be substantially more informative than GitHub docstrings."""
    for tool in ALL_TOOLS:
        a_len = len(ARM_A_DESCRIPTIONS[tool])
        o_len = len(ARM_O_DESCRIPTIONS[tool])
        assert o_len > a_len, f"Oracle for '{tool}' shorter than Arm A: {o_len} vs {a_len}"


# ── Destructive tools and confusable pairs ────────────────────────────────────


def test_rw1_destructive_tools_count() -> None:
    assert len(DESTRUCTIVE_TOOLS) >= 4, (
        f"Expected >= 4 destructive tools, got {len(DESTRUCTIVE_TOOLS)}"
    )


def test_rw1_destructive_tools_are_in_catalog() -> None:
    for tool in DESTRUCTIVE_TOOLS:
        assert tool in ALL_TOOLS, f"Destructive tool '{tool}' not in catalog"


def test_rw1_merge_pull_request_is_destructive() -> None:
    assert "merge_pull_request" in DESTRUCTIVE_TOOLS


def test_rw1_create_or_update_file_is_destructive() -> None:
    assert "create_or_update_file" in DESTRUCTIVE_TOOLS


def test_rw1_push_files_is_destructive() -> None:
    assert "push_files" in DESTRUCTIVE_TOOLS


def test_rw1_create_repository_is_destructive() -> None:
    assert "create_repository" in DESTRUCTIVE_TOOLS


def test_rw1_fork_repository_is_destructive() -> None:
    assert "fork_repository" in DESTRUCTIVE_TOOLS


def test_rw1_read_tools_not_destructive() -> None:
    safe_tools = {
        "get_pull_request",
        "get_pull_request_diff",
        "get_pull_request_files",
        "get_pull_request_reviews",
        "get_pull_request_comments",
        "get_file_contents",
        "get_repository",
        "list_repositories",
        "list_pull_requests",
        "list_issues",
        "list_commits",
        "list_branches",
        "search_repositories",
        "search_code",
        "search_issues",
        "search_users",
    }
    for tool in safe_tools:
        assert tool not in DESTRUCTIVE_TOOLS, f"Safe tool '{tool}' incorrectly in DESTRUCTIVE_TOOLS"


def test_rw1_destructive_confusable_pairs_count() -> None:
    assert len(DESTRUCTIVE_CONFUSABLE_PAIRS) >= 4


def test_rw1_destructive_confusable_pairs_structure() -> None:
    """Each pair must be (safe_tool, destructive_tool)."""
    for safe, destructive in DESTRUCTIVE_CONFUSABLE_PAIRS:
        assert safe in ALL_TOOLS, f"safe tool '{safe}' not in catalog"
        assert destructive in ALL_TOOLS, f"destructive tool '{destructive}' not in catalog"
        assert safe not in DESTRUCTIVE_TOOLS, f"'{safe}' should be safe but is in DESTRUCTIVE_TOOLS"
        assert destructive in DESTRUCTIVE_TOOLS, f"'{destructive}' should be destructive"


def test_rw1_get_vs_merge_pair_exists() -> None:
    assert ("get_pull_request", "merge_pull_request") in DESTRUCTIVE_CONFUSABLE_PAIRS


def test_rw1_get_file_vs_create_pair_exists() -> None:
    assert ("get_file_contents", "create_or_update_file") in DESTRUCTIVE_CONFUSABLE_PAIRS


def test_rw1_destructive_pairs_share_required_params() -> None:
    """Each (safe, destructive) pair must share at least 2 required params."""
    for safe, destructive in DESTRUCTIVE_CONFUSABLE_PAIRS:
        safe_req = set(TOOL_SCHEMAS[safe]["required"])
        dest_req = set(TOOL_SCHEMAS[destructive]["required"])
        overlap = safe_req & dest_req
        assert len(overlap) >= 1, (
            f"Pair ({safe!r}, {destructive!r}) shares no required params: {safe_req} vs {dest_req}"
        )


# ── Ground truth (GitHub hand-fixed families) ─────────────────────────────────


def test_rw1_github_hand_fixed_families_defined() -> None:
    assert len(GITHUB_HAND_FIXED_FAMILIES) >= 2


def test_rw1_projects_consolidation_documented() -> None:
    assert "projects" in GITHUB_HAND_FIXED_FAMILIES
    assert (
        "6" in GITHUB_HAND_FIXED_FAMILIES["projects"]
        or "consolidat" in GITHUB_HAND_FIXED_FAMILIES["projects"].lower()
    )


def test_rw1_pr_read_family_documented() -> None:
    assert "pr_read_variants" in GITHUB_HAND_FIXED_FAMILIES


# ── Tasks ─────────────────────────────────────────────────────────────────────


def test_rw1_task_count() -> None:
    assert len(TASKS) == 21, f"Expected 21 tasks, got {len(TASKS)}"


def test_rw1_gold_mapping_complete() -> None:
    for task in TASKS:
        assert task.tool_name in ALL_TOOLS, f"Task gold tool '{task.tool_name}' not in catalog"


def test_rw1_one_task_per_tool() -> None:
    gold_tools = [t.tool_name for t in TASKS]
    assert len(gold_tools) == len(set(gold_tools)), "Duplicate gold tool in TASKS"
    assert set(gold_tools) == set(ALL_TOOLS), "TASKS does not cover all 21 tools exactly once"


def test_rw1_tasks_antitautological() -> None:
    """No task description should contain its gold tool name."""
    for task in TASKS:
        assert task.tool_name not in task.description, (
            f"Task for '{task.tool_name}' contains the tool name in its description"
        )


def test_rw1_tasks_have_descriptions() -> None:
    for task in TASKS:
        assert len(task.description) > 20, f"Task for '{task.tool_name}' description too short"


# ── Mirror server source ───────────────────────────────────────────────────────


def test_rw1_mirror_server_path_exists() -> None:
    path = Path(__file__).parent.parent / "examples" / "rw1_github_mirror.py"
    assert path.exists(), f"Mirror server not found at {path}"


def test_rw1_mirror_source_readable() -> None:
    source = get_mirror_source()
    assert len(source) > 500
    assert "rw1-github-mirror" in source


def test_rw1_mirror_has_handler_for_each_tool() -> None:
    source = get_mirror_source()
    for tool in ALL_TOOLS:
        assert f"def _handle_{tool}(" in source or f"async def _handle_{tool}(" in source, (
            f"Mirror server missing _handle_{tool}()"
        )


def test_rw1_mirror_docstring_signals_present() -> None:
    """Each independence signal must appear in the corresponding handler's docstring."""
    source = get_mirror_source()
    for tool, signal in MIRROR_DOCSTRING_SIGNALS.items():
        # Find the handler and check the signal appears somewhere in its body
        handler_marker = f"_handle_{tool}("
        idx = source.find(handler_marker)
        assert idx >= 0, f"Handler _handle_{tool}() not found in mirror source"
        # Get the next 800 chars (enough for any docstring)
        snippet = source[idx : idx + 800]
        assert signal in snippet, (
            f"Independence signal {signal!r} not found in _handle_{tool}() docstring. "
            f"First 400 chars of handler: {snippet[:400]!r}"
        )


# ── Arm servers ───────────────────────────────────────────────────────────────


def test_rw1_arm_a_server_exists() -> None:
    path = Path(__file__).parent.parent / "examples" / "rw1_arm_a.py"
    assert path.exists()


def test_rw1_arm_guardb_server_exists() -> None:
    path = Path(__file__).parent.parent / "examples" / "rw1_arm_guardb.py"
    assert path.exists()


def test_rw1_arm_oracle_server_exists() -> None:
    path = Path(__file__).parent.parent / "examples" / "rw1_arm_oracle.py"
    assert path.exists()


# ── Discoverability heuristic (deterministic, no LLM) ─────────────────────────


def test_rw1_discoverability_heuristic_runs() -> None:
    """Discoverability heuristic sub-score runs on the GitHub catalog without error."""
    from agentgauge.scorer import _heuristic_subscore

    tools = [
        Tool(name=name, description=GITHUB_DOCSTRINGS[name], inputSchema=TOOL_SCHEMAS[name])
        for name in ALL_TOOLS
    ]
    score, fix_hints, collision_pairs, per_tool = _heuristic_subscore(tools)
    assert 0.0 <= score <= 100.0
    assert isinstance(fix_hints, list)
    assert isinstance(collision_pairs, list)
    assert len(per_tool) == 21


def test_rw1_heuristic_detects_pr_read_collision() -> None:
    """get_pull_request_diff and get_pull_request_files are close enough to trigger collision."""
    from agentgauge.scorer import _heuristic_subscore

    tools = [
        Tool(name=name, description=GITHUB_DOCSTRINGS[name], inputSchema=TOOL_SCHEMAS[name])
        for name in ALL_TOOLS
    ]
    _, _, collision_pairs, _ = _heuristic_subscore(tools)
    # The diff/files pair has edit-distance similarity > 0.80 — should be flagged
    flagged_names = {frozenset(p) for p in collision_pairs}
    diff_files = frozenset({"get_pull_request_diff", "get_pull_request_files"})
    assert diff_files in flagged_names, (
        f"Expected get_pull_request_diff/get_pull_request_files collision not found. "
        f"Found pairs: {collision_pairs}"
    )


def test_rw1_discoverability_scorer_with_mock() -> None:
    """Full score_discoverability runs with MockProvider without error."""
    from agentgauge.providers import MockProvider
    from agentgauge.scorer import score_discoverability

    tools = [
        Tool(name=name, description=GITHUB_DOCSTRINGS[name], inputSchema=TOOL_SCHEMAS[name])
        for name in ALL_TOOLS
    ]
    provider = MockProvider("CLARITY: 5\nDISTINGUISH: 3")
    result = asyncio.run(score_discoverability(tools, provider, trials=1))
    assert result.name == "discoverability"
    assert 0.0 <= result.score <= 100.0


# ── Guard-B fixer path (MockProvider, deterministic) ──────────────────────────


def test_rw1_scoped_extraction_finds_handlers() -> None:
    """_extract_scoped_function can find each tool's handler in the mirror source."""
    from agentgauge.fixer import _extract_scoped_function

    source = get_mirror_source()
    for tool in ALL_TOOLS:
        extracted = _extract_scoped_function(source, tool)
        assert extracted != "", f"_extract_scoped_function returned empty for '{tool}'"
        assert f"_handle_{tool}" in extracted


def test_rw1_scoped_extraction_contains_docstring() -> None:
    """Extracted handlers should contain triple-quoted docstrings."""
    from agentgauge.fixer import _extract_scoped_function

    source = get_mirror_source()
    for tool in ALL_TOOLS:
        extracted = _extract_scoped_function(source, tool)
        assert '"""' in extracted, (
            f"No docstring found in extracted handler for '{tool}': {extracted[:200]!r}"
        )


def test_rw1_surface_extraction_finds_all_neighbors() -> None:
    """_extract_function_surface can find the def+docstring for each tool."""
    from agentgauge.fixer import _extract_function_surface

    source = get_mirror_source()
    for tool in ALL_TOOLS:
        surface = _extract_function_surface(source, tool)
        assert surface != "", f"_extract_function_surface returned empty for '{tool}'"
