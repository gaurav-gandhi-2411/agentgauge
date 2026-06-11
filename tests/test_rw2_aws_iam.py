from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.types import Tool

from evals.fixtures.rw2_aws_iam_catalog import (
    ALL_TOOLS,
    ARM_A_DESCRIPTIONS,
    ARM_O_DESCRIPTIONS,
    AWS_IAM_DOCSTRINGS,
    CONTESTED_TOOLS,
    DESTRUCTIVE_CONFUSABLE_PAIRS,
    DESTRUCTIVE_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    MIRROR_DOCSTRING_SIGNALS,
    TASKS,
    THOROUGH_TOOL_CONTROL_SET,
    TOOL_SCHEMAS,
    get_mirror_source,
)

# ── Fixture size and structure ─────────────────────────────────────────────────


def test_rw2_tool_count() -> None:
    assert len(ALL_TOOLS) == 29, f"Expected 29 tools, got {len(ALL_TOOLS)}"


def test_rw2_families_defined() -> None:
    expected = {
        "attach_detach_family",
        "list_policies_family",
        "destructive_pair",
        "user_ops",
        "role_ops",
        "inline_user_policy",
        "inline_role_policy",
        "group_ops",
        "simulate_ops",
        "access_key_ops",
    }
    assert set(FAMILIES.keys()) == expected


def test_rw2_family_sizes() -> None:
    """Check that each family has the expected number of tools."""
    expected_sizes = {
        "attach_detach_family": 4,
        "list_policies_family": 6,
        "destructive_pair": 2,
        "user_ops": 3,
        "role_ops": 2,
        "inline_user_policy": 2,
        "inline_role_policy": 2,
        "group_ops": 5,
        "simulate_ops": 1,
        "access_key_ops": 2,
    }
    for family, expected in expected_sizes.items():
        actual = len(FAMILIES[family])
        assert actual == expected, f"Family {family!r}: expected {expected}, got {actual}"


def test_rw2_family_map_covers_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in FAMILY_MAP, f"'{tool}' missing from FAMILY_MAP"


def test_rw2_family_map_is_consistent() -> None:
    for tool, family in FAMILY_MAP.items():
        assert tool in FAMILIES[family], (
            f"FAMILY_MAP[{tool!r}]={family!r} inconsistent with FAMILIES"
        )


# ── Schema completeness ────────────────────────────────────────────────────────


def test_rw2_all_tools_have_schemas() -> None:
    for tool in ALL_TOOLS:
        assert tool in TOOL_SCHEMAS, f"'{tool}' missing from TOOL_SCHEMAS"
        schema = TOOL_SCHEMAS[tool]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_rw2_all_schemas_have_type_object() -> None:
    for tool, schema in TOOL_SCHEMAS.items():
        assert schema.get("type") == "object", f"'{tool}' schema does not have type=object"


def test_rw2_attach_detach_family_share_policy_arn() -> None:
    """All attach/detach family tools require policy_arn in their schema."""
    for tool in FAMILIES["attach_detach_family"]:
        required = set(TOOL_SCHEMAS[tool]["required"])
        assert "policy_arn" in required, f"{tool}: expected policy_arn in required, got {required}"


def test_rw2_delete_policy_pair_share_policy_name() -> None:
    """Both destructive-pair tools require policy_name."""
    for tool in FAMILIES["destructive_pair"]:
        required = set(TOOL_SCHEMAS[tool]["required"])
        assert "policy_name" in required, (
            f"{tool}: expected policy_name in required, got {required}"
        )


# ── Descriptions ──────────────────────────────────────────────────────────────


def test_rw2_aws_iam_docstrings_cover_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in AWS_IAM_DOCSTRINGS, f"'{tool}' missing from AWS_IAM_DOCSTRINGS"
        assert len(AWS_IAM_DOCSTRINGS[tool]) > 0, f"'{tool}' has empty AWS IAM docstring"


def test_rw2_arm_a_equals_aws_iam_docstrings() -> None:
    """KEY: Arm A uses the verbatim AWS IAM docstrings — independence assertion."""
    assert ARM_A_DESCRIPTIONS == AWS_IAM_DOCSTRINGS, (
        "ARM_A_DESCRIPTIONS must be identical to AWS_IAM_DOCSTRINGS (verbatim source)"
    )


def test_rw2_arm_a_thin_on_contested() -> None:
    """attach_detach_family tools should have short (1-sentence) Arm A descriptions."""
    for tool in FAMILIES["attach_detach_family"]:
        desc = ARM_A_DESCRIPTIONS[tool]
        # Thin docstrings: "Attach/Detach a managed policy to/from an IAM user/group."
        assert len(desc) < 100, (
            f"attach_detach_family tool '{tool}' description unexpectedly long ({len(desc)} chars): "
            f"{desc!r}"
        )


def test_rw2_arm_o_covers_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in ARM_O_DESCRIPTIONS, f"'{tool}' missing from ARM_O_DESCRIPTIONS"
        assert len(ARM_O_DESCRIPTIONS[tool]) > 20, f"Oracle description for '{tool}' too short"


def test_rw2_arm_o_longer_than_arm_a() -> None:
    """Oracle descriptions should be substantially more informative than AWS IAM docstrings."""
    for tool in ALL_TOOLS:
        a_len = len(ARM_A_DESCRIPTIONS[tool])
        o_len = len(ARM_O_DESCRIPTIONS[tool])
        assert o_len > a_len, f"Oracle for '{tool}' shorter than Arm A: {o_len} vs {a_len}"


# ── Contested and thorough sets ────────────────────────────────────────────────


def test_rw2_contested_tools_count() -> None:
    # 4 (attach_detach) + 6 (list_policies) + 2 (destructive_pair) = 12
    assert len(CONTESTED_TOOLS) == 12, f"Expected 12 contested tools, got {len(CONTESTED_TOOLS)}"


def test_rw2_attach_detach_family_in_contested() -> None:
    """All 4 attach/detach family tools must be in CONTESTED_TOOLS."""
    for tool in FAMILIES["attach_detach_family"]:
        assert tool in CONTESTED_TOOLS, f"'{tool}' missing from CONTESTED_TOOLS"


def test_rw2_list_policies_family_in_contested() -> None:
    """All 6 list_policies family tools must be in CONTESTED_TOOLS."""
    for tool in FAMILIES["list_policies_family"]:
        assert tool in CONTESTED_TOOLS, f"'{tool}' missing from CONTESTED_TOOLS"


def test_rw2_destructive_pair_in_contested() -> None:
    """Both delete_*_policy tools must be in CONTESTED_TOOLS."""
    for tool in FAMILIES["destructive_pair"]:
        assert tool in CONTESTED_TOOLS, f"'{tool}' missing from CONTESTED_TOOLS"


def test_rw2_thorough_set_count() -> None:
    assert len(THOROUGH_TOOL_CONTROL_SET) == 14, (
        f"Expected 14 thorough tools, got {len(THOROUGH_TOOL_CONTROL_SET)}"
    )


def test_rw2_contested_and_thorough_disjoint() -> None:
    """CONTESTED_TOOLS and THOROUGH_TOOL_CONTROL_SET must not overlap."""
    overlap = CONTESTED_TOOLS & THOROUGH_TOOL_CONTROL_SET
    assert len(overlap) == 0, f"CONTESTED_TOOLS and THOROUGH_TOOL_CONTROL_SET overlap: {overlap}"


def test_rw2_all_thorough_tools_in_catalog() -> None:
    for tool in THOROUGH_TOOL_CONTROL_SET:
        assert tool in ALL_TOOLS, f"Thorough tool '{tool}' not in catalog"


# ── Destructive tools and confusable pairs ─────────────────────────────────────


def test_rw2_destructive_tools_count() -> None:
    assert len(DESTRUCTIVE_TOOLS) >= 4, (
        f"Expected >= 4 destructive tools, got {len(DESTRUCTIVE_TOOLS)}"
    )


def test_rw2_delete_user_policy_is_destructive() -> None:
    assert "delete_user_policy" in DESTRUCTIVE_TOOLS


def test_rw2_delete_role_policy_is_destructive() -> None:
    assert "delete_role_policy" in DESTRUCTIVE_TOOLS


def test_rw2_delete_user_is_destructive() -> None:
    assert "delete_user" in DESTRUCTIVE_TOOLS


def test_rw2_read_tools_not_destructive() -> None:
    """Read-only and list tools must not be in DESTRUCTIVE_TOOLS."""
    safe_tools = {
        "get_user",
        "get_user_policy",
        "get_role_policy",
        "get_group",
        "get_managed_policy_document",
        "list_users",
        "list_groups",
        "list_roles",
        "list_policies",
        "list_user_policies",
        "list_role_policies",
        "simulate_principal_policy",
    }
    for tool in safe_tools:
        assert tool not in DESTRUCTIVE_TOOLS, f"Safe tool '{tool}' incorrectly in DESTRUCTIVE_TOOLS"


def test_rw2_destructive_confusable_pairs_count() -> None:
    assert len(DESTRUCTIVE_CONFUSABLE_PAIRS) == 3, (
        f"Expected 3 destructive confusable pairs, got {len(DESTRUCTIVE_CONFUSABLE_PAIRS)}"
    )


def test_rw2_destructive_confusable_pairs_structure() -> None:
    """Each pair must be (safe_tool, destructive_tool)."""
    for safe, destructive in DESTRUCTIVE_CONFUSABLE_PAIRS:
        assert safe in ALL_TOOLS, f"safe tool '{safe}' not in catalog"
        assert destructive in ALL_TOOLS, f"destructive tool '{destructive}' not in catalog"
        assert safe not in DESTRUCTIVE_TOOLS, f"'{safe}' should be safe but is in DESTRUCTIVE_TOOLS"
        assert destructive in DESTRUCTIVE_TOOLS, f"'{destructive}' should be destructive"


def test_rw2_get_user_policy_vs_delete_pair_exists() -> None:
    assert ("get_user_policy", "delete_user_policy") in DESTRUCTIVE_CONFUSABLE_PAIRS


def test_rw2_get_role_policy_vs_delete_pair_exists() -> None:
    assert ("get_role_policy", "delete_role_policy") in DESTRUCTIVE_CONFUSABLE_PAIRS


# ── Tasks ──────────────────────────────────────────────────────────────────────


def test_rw2_task_count() -> None:
    assert len(TASKS) == 29, f"Expected 29 tasks, got {len(TASKS)}"


def test_rw2_gold_mapping_complete() -> None:
    for task in TASKS:
        assert task.tool_name in ALL_TOOLS, f"Task gold tool '{task.tool_name}' not in catalog"


def test_rw2_one_task_per_tool() -> None:
    gold_tools = [t.tool_name for t in TASKS]
    assert len(gold_tools) == len(set(gold_tools)), "Duplicate gold tool in TASKS"
    assert set(gold_tools) == set(ALL_TOOLS), "TASKS does not cover all 29 tools exactly once"


def test_rw2_tasks_antitautological() -> None:
    """No task description should contain its gold tool name."""
    for task in TASKS:
        assert task.tool_name not in task.description, (
            f"Task for '{task.tool_name}' contains the tool name in its description"
        )


def test_rw2_tasks_have_descriptions() -> None:
    for task in TASKS:
        assert len(task.description) > 20, f"Task for '{task.tool_name}' description too short"


def test_rw2_contested_tasks_specify_principal() -> None:
    """Tasks for attach_detach_family must mention 'user' or 'group' in the description."""
    for task in TASKS:
        if task.tool_name in FAMILIES["attach_detach_family"]:
            desc_lower = task.description.lower()
            assert "user" in desc_lower or "group" in desc_lower, (
                f"Task for '{task.tool_name}' does not specify 'user' or 'group': "
                f"{task.description!r}"
            )


# ── Mirror server source ───────────────────────────────────────────────────────


def test_rw2_mirror_server_path_exists() -> None:
    path = Path(__file__).parent.parent / "examples" / "rw2_aws_iam_mirror.py"
    assert path.exists(), f"Mirror server not found at {path}"


def test_rw2_mirror_source_readable() -> None:
    source = get_mirror_source()
    assert len(source) > 500
    assert "rw2-aws-iam-mirror" in source


def test_rw2_mirror_has_handler_for_each_tool() -> None:
    source = get_mirror_source()
    for tool in ALL_TOOLS:
        assert f"async def _handle_{tool}(" in source, (
            f"Mirror server missing async def _handle_{tool}()"
        )


def test_rw2_mirror_docstring_signals_present() -> None:
    """Each independence signal must appear in the corresponding handler's docstring."""
    source = get_mirror_source()
    for tool, signal in MIRROR_DOCSTRING_SIGNALS.items():
        handler_marker = f"_handle_{tool}("
        idx = source.find(handler_marker)
        assert idx >= 0, f"Handler _handle_{tool}() not found in mirror source"
        # Get the next 800 chars (enough for any docstring)
        snippet = source[idx : idx + 800]
        assert signal in snippet, (
            f"Independence signal {signal!r} not found in _handle_{tool}() docstring. "
            f"First 400 chars of handler: {snippet[:400]!r}"
        )


# ── Arm servers ────────────────────────────────────────────────────────────────


def test_rw2_arm_a_server_exists() -> None:
    path = Path(__file__).parent.parent / "examples" / "rw2_arm_a.py"
    assert path.exists()


def test_rw2_arm_guardb_server_exists() -> None:
    path = Path(__file__).parent.parent / "examples" / "rw2_arm_guardb.py"
    assert path.exists()


# ── Discoverability heuristic (deterministic, no LLM) ─────────────────────────


def test_rw2_discoverability_heuristic_runs() -> None:
    """Discoverability heuristic sub-score runs on the AWS IAM catalog without error."""
    from agentgauge.scorer import _heuristic_subscore

    tools = [
        Tool(name=name, description=AWS_IAM_DOCSTRINGS[name], inputSchema=TOOL_SCHEMAS[name])
        for name in ALL_TOOLS
    ]
    score, fix_hints, collision_pairs, per_tool = _heuristic_subscore(tools)
    assert 0.0 <= score <= 100.0
    assert isinstance(fix_hints, list)
    assert isinstance(collision_pairs, list)
    assert len(per_tool) == 29


def test_rw2_heuristic_detects_attach_detach_collision() -> None:
    """attach_detach_family tools should trigger name-collision detection.

    The heuristic finds near-duplicate name pairs. attach_user_policy / detach_user_policy
    differ only by 'attach' vs 'detach' — high edit-distance similarity. This is the most
    confusable pair within the family (applying vs removing a policy on the same principal).
    """
    from agentgauge.scorer import _heuristic_subscore

    tools = [
        Tool(name=name, description=AWS_IAM_DOCSTRINGS[name], inputSchema=TOOL_SCHEMAS[name])
        for name in ALL_TOOLS
    ]
    _, _, collision_pairs, _ = _heuristic_subscore(tools)
    # attach_user_policy and detach_user_policy differ only by attach/detach prefix
    flagged_names = {frozenset(p) for p in collision_pairs}
    attach_detach_pair = frozenset({"attach_user_policy", "detach_user_policy"})
    assert attach_detach_pair in flagged_names, (
        f"Expected attach_user_policy/detach_user_policy collision not found. "
        f"Found pairs: {collision_pairs}"
    )


def test_rw2_discoverability_scorer_with_mock() -> None:
    """Full score_discoverability runs with MockProvider without error."""
    from agentgauge.providers import MockProvider
    from agentgauge.scorer import score_discoverability

    tools = [
        Tool(name=name, description=AWS_IAM_DOCSTRINGS[name], inputSchema=TOOL_SCHEMAS[name])
        for name in ALL_TOOLS
    ]
    provider = MockProvider("CLARITY: 5\nDISTINGUISH: 3")
    result = asyncio.run(score_discoverability(tools, provider, trials=1))
    assert result.name == "discoverability"
    assert 0.0 <= result.score <= 100.0


# ── Guard-B fixer path (MockProvider, deterministic) ──────────────────────────


def test_rw2_scoped_extraction_finds_handlers() -> None:
    """_extract_scoped_function can find each tool's handler in the mirror source."""
    from agentgauge.fixer import _extract_scoped_function

    source = get_mirror_source()
    for tool in ALL_TOOLS:
        extracted = _extract_scoped_function(source, tool)
        assert extracted != "", f"_extract_scoped_function returned empty for '{tool}'"
        assert f"_handle_{tool}" in extracted


def test_rw2_scoped_extraction_contains_docstring() -> None:
    """Extracted handlers should contain triple-quoted docstrings."""
    from agentgauge.fixer import _extract_scoped_function

    source = get_mirror_source()
    for tool in ALL_TOOLS:
        extracted = _extract_scoped_function(source, tool)
        assert '"""' in extracted, (
            f"No docstring found in extracted handler for '{tool}': {extracted[:200]!r}"
        )


def test_rw2_surface_extraction_finds_all_handlers() -> None:
    """_extract_function_surface can find the def+docstring for each tool."""
    from agentgauge.fixer import _extract_function_surface

    source = get_mirror_source()
    for tool in ALL_TOOLS:
        surface = _extract_function_surface(source, tool)
        assert surface != "", f"_extract_function_surface returned empty for '{tool}'"
