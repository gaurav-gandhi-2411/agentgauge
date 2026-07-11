from __future__ import annotations

from pathlib import Path

from evals.fixtures.q6_catalog import (
    ALREADY_PASSING_TASK_INDICES,
    ALREADY_PASSING_TOOLS,
    ARM_A_DESCRIPTIONS,
    ARM_O_DESCRIPTIONS,
    COLLISION_PAIR_DOCS,
    COLLISION_PRONE_PAIRS,
    COLLISION_PRONE_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    INDEPENDENCE_TOKENS,
    Q3_CONTROL_TASKS,
    Q3_FAMILIES,
    Q3_STRUCTURAL_CONTESTED_TASKS,
    Q6_ALREADY_PASSING_TASKS,
    STRUCTURAL_CONTESTED_TASK_INDICES,
    TASKS,
    get_doc_source,
)

# ── Fixture size and structure ─────────────────────────────────────────────────


def test_q6_total_tool_count() -> None:
    all_tools = [name for names in FAMILIES.values() for name in names]
    assert len(all_tools) == 23, f"Expected 23 tools, got {len(all_tools)}"


def test_q6_q3_families_present() -> None:
    for family in ["store_family", "delete_family", "control_search", "control_sched"]:
        assert family in FAMILIES, f"Q3 family '{family}' missing from Q6 catalog"


def test_q6_q3_tools_count() -> None:
    q3_tools = [name for family in Q3_FAMILIES.values() for name in family]
    assert len(q3_tools) == 12


def test_q6_already_passing_tools_count() -> None:
    assert len(ALREADY_PASSING_TOOLS) >= 8, (
        f"Spec requires >= 8 already-passing tools; got {len(ALREADY_PASSING_TOOLS)}"
    )


def test_q6_collision_prone_pairs_count() -> None:
    assert len(COLLISION_PRONE_PAIRS) >= 3, (
        f"Spec requires >= 3 collision-prone pairs; got {len(COLLISION_PRONE_PAIRS)}"
    )


def test_q6_arm_a_all_empty() -> None:
    for tools in FAMILIES.values():
        for name in tools:
            assert ARM_A_DESCRIPTIONS[name] == "", f"Arm A description for '{name}' should be empty"


def test_q6_arm_o_all_present_and_nonempty() -> None:
    for tools in FAMILIES.values():
        for name in tools:
            assert name in ARM_O_DESCRIPTIONS, f"'{name}' missing from ARM_O_DESCRIPTIONS"
            assert len(ARM_O_DESCRIPTIONS[name]) > 0, f"Oracle description for '{name}' is empty"


# ── Task structure ─────────────────────────────────────────────────────────────


def test_q6_total_task_count() -> None:
    # 6 structural contested + 2 control + 11 already-passing = 19
    # (or more if additional tasks added)
    assert len(TASKS) >= 19, f"Expected >= 19 tasks, got {len(TASKS)}"


def test_q6_structural_contested_tasks_count() -> None:
    assert len(Q3_STRUCTURAL_CONTESTED_TASKS) == 6


def test_q6_control_tasks_count() -> None:
    assert len(Q3_CONTROL_TASKS) == 2


def test_q6_already_passing_task_count() -> None:
    assert len(Q6_ALREADY_PASSING_TASKS) == 11


def test_q6_tasks_gold_tools_in_catalog() -> None:
    all_tools = {name for names in FAMILIES.values() for name in names}
    for task in TASKS:
        assert task.tool_name in all_tools, f"Task gold tool '{task.tool_name}' not in Q6 catalog"


def test_q6_tasks_anti_tautology() -> None:
    """Task descriptions must not literally contain the gold tool name."""
    for task in TASKS:
        assert task.tool_name not in task.description, (
            f"Task description for '{task.tool_name}' contains the tool name — tautology risk"
        )


def test_q6_already_passing_task_indices_consistent() -> None:
    """ALREADY_PASSING_TASK_INDICES must index into Q6_ALREADY_PASSING_TASKS region."""
    for idx in ALREADY_PASSING_TASK_INDICES:
        assert 0 <= idx < len(TASKS), f"ALREADY_PASSING_TASK_INDICES contains out-of-range {idx}"
        assert TASKS[idx].tool_name in ALREADY_PASSING_TOOLS, (
            f"Task at index {idx} gold tool '{TASKS[idx].tool_name}' not in ALREADY_PASSING_TOOLS"
        )


def test_q6_structural_contested_task_indices_consistent() -> None:
    """STRUCTURAL_CONTESTED_TASK_INDICES must index into Q3_STRUCTURAL_CONTESTED_TASKS region."""
    contested_tools = {t.tool_name for t in Q3_STRUCTURAL_CONTESTED_TASKS}
    for idx in STRUCTURAL_CONTESTED_TASK_INDICES:
        assert 0 <= idx < len(TASKS)
        assert TASKS[idx].tool_name in contested_tools


def test_q6_already_passing_tasks_cover_all_collision_pairs() -> None:
    """Each tool in a collision-prone pair must have at least one already-passing task."""
    ap_task_tools = {TASKS[i].tool_name for i in ALREADY_PASSING_TASK_INDICES}
    for tool_a, tool_b in COLLISION_PRONE_PAIRS:
        assert tool_a in ap_task_tools, (
            f"No already-passing task for collision-prone tool '{tool_a}'"
        )
        assert tool_b in ap_task_tools, (
            f"No already-passing task for collision-prone tool '{tool_b}'"
        )


# ── Collision-prone pair documentation ────────────────────────────────────────


def test_q6_collision_prone_pairs_all_documented() -> None:
    """Every collision-prone pair must have an entry in COLLISION_PAIR_DOCS."""
    documented_pairs = {(doc["tool_a"], doc["tool_b"]) for doc in COLLISION_PAIR_DOCS}
    for tool_a, tool_b in COLLISION_PRONE_PAIRS:
        assert (tool_a, tool_b) in documented_pairs, (
            f"Collision-prone pair ({tool_a}, {tool_b}) not documented in COLLISION_PAIR_DOCS"
        )


def test_q6_collision_pair_docs_have_required_fields() -> None:
    required_fields = {
        "pair",
        "tool_a",
        "tool_b",
        "names_disambiguate",
        "descriptions_might_not",
        "independence_token_a",
        "independence_token_b",
    }
    for doc in COLLISION_PAIR_DOCS:
        missing = required_fields - set(doc.keys())
        assert not missing, f"COLLISION_PAIR_DOC missing fields: {missing} (pair={doc.get('pair')})"


def test_q6_collision_pair_docs_have_nonempty_rationale() -> None:
    for doc in COLLISION_PAIR_DOCS:
        assert len(doc["names_disambiguate"]) > 20, (
            f"Pair {doc['pair']}: 'names_disambiguate' is too short — must explain why names suffice"
        )
        assert len(doc["descriptions_might_not"]) > 30, (
            f"Pair {doc['pair']}: 'descriptions_might_not' is too short — must explain the collision risk"
        )


def test_q6_collision_prone_tools_in_catalog() -> None:
    all_tools = {name for names in FAMILIES.values() for name in names}
    for name in COLLISION_PRONE_TOOLS:
        assert name in all_tools, f"Collision-prone tool '{name}' not in catalog"


def test_q6_collision_prone_tools_in_already_passing() -> None:
    for name in COLLISION_PRONE_TOOLS:
        assert name in ALREADY_PASSING_TOOLS, (
            f"Collision-prone tool '{name}' not in ALREADY_PASSING_TOOLS"
        )


# ── Independence token assertions ──────────────────────────────────────────────


def test_q6_independence_tokens_in_source() -> None:
    """Each contested/already-passing tool's independence token must appear in q6_real_server.py."""
    source = get_doc_source()
    for tool_name, token in INDEPENDENCE_TOKENS.items():
        assert token in source, (
            f"Independence token {token!r} for tool '{tool_name}' "
            "not found in q6_real_server.py. "
            "The distinguishing fact must be in the code, not just in the oracle description."
        )


def test_q6_collision_pair_independence_tokens_in_source() -> None:
    """Collision-prone pair independence tokens must appear in source."""
    source = get_doc_source()
    for doc in COLLISION_PAIR_DOCS:
        for key in ["independence_token_a", "independence_token_b"]:
            token = doc[key]
            assert token in source, (
                f"Collision pair {doc['pair']}: independence token {token!r} not in q6_real_server.py"
            )


def test_q6_already_passing_tools_have_independence_tokens() -> None:
    """Every already-passing tool must have an independence token."""
    for name in ALREADY_PASSING_TOOLS:
        assert name in INDEPENDENCE_TOKENS, (
            f"Already-passing tool '{name}' missing independence token in INDEPENDENCE_TOKENS"
        )


# ── Distinct names for already-passing tools ───────────────────────────────────


def test_q6_already_passing_tool_names_are_distinct() -> None:
    """Already-passing tools must have unique names."""
    assert len(ALREADY_PASSING_TOOLS) == len(set(ALREADY_PASSING_TOOLS)), (
        "ALREADY_PASSING_TOOLS contains duplicate names"
    )


def test_q6_collision_pairs_have_distinct_names() -> None:
    """Each collision-prone pair must have two distinct tool names."""
    for tool_a, tool_b in COLLISION_PRONE_PAIRS:
        assert tool_a != tool_b, f"Collision-prone pair has identical names: ({tool_a}, {tool_b})"


def test_q6_non_collision_tools_not_in_collision_pairs() -> None:
    """Non-collision already-passing tools must not appear in collision-prone pairs."""
    from evals.fixtures.q6_catalog import Q6_NON_COLLISION

    for name in Q6_NON_COLLISION:
        assert name not in COLLISION_PRONE_TOOLS, (
            f"Non-collision tool '{name}' appears in COLLISION_PRONE_TOOLS"
        )


# ── Gold mapping integrity ─────────────────────────────────────────────────────


def test_q6_family_map_covers_all_tools() -> None:
    all_tools = {name for names in FAMILIES.values() for name in names}
    assert set(FAMILY_MAP.keys()) == all_tools


def test_q6_q3_structural_contested_tools_preserved() -> None:
    """The 6 Q3 structural contested tools must appear in the task list."""
    structural_contested = {
        "store_item",
        "persist_row",
        "write_entry",
        "delete_record",
        "retire_data",
        "remove_entry",
    }
    task_tools = {t.tool_name for t in Q3_STRUCTURAL_CONTESTED_TASKS}
    assert task_tools == structural_contested, (
        f"Q3 structural contested tasks mismatch: {task_tools} != {structural_contested}"
    )


# ── Server file presence ───────────────────────────────────────────────────────


def test_q6_real_server_file_exists() -> None:
    server_path = Path(__file__).parent.parent / "examples" / "q6_real_server.py"
    assert server_path.exists(), "examples/q6_real_server.py must exist"


def test_q6_arm_a_server_file_exists() -> None:
    server_path = Path(__file__).parent.parent / "examples" / "q6_arm_a.py"
    assert server_path.exists(), "examples/q6_arm_a.py must exist"


def test_q6_arm_f_server_file_exists() -> None:
    server_path = Path(__file__).parent.parent / "examples" / "q6_arm_f_doc_guarded.py"
    assert server_path.exists(), "examples/q6_arm_f_doc_guarded.py must exist"


def test_q6_doc_source_is_real_server_source() -> None:
    """get_doc_source() must read the actual q6_real_server.py file."""
    expected = (Path(__file__).parent.parent / "examples" / "q6_real_server.py").read_text(
        encoding="utf-8"
    )
    assert get_doc_source() == expected


# ── Guard-B path unchanged (smoke test — full tests in test_q5_guarded.py) ────


def test_q6_guard_b_prompt_still_contains_forbidden() -> None:
    """Guard B prompt must still contain FORBIDDEN — path unchanged from Q5."""
    from agentgauge.fixer import _DESC_GENERATOR_GUARD_B_PROMPT

    assert "FORBIDDEN" in _DESC_GENERATOR_GUARD_B_PROMPT


def test_q6_guard_b_prompt_still_contains_no_fabrication() -> None:
    """Guard B prompt must still contain NO FABRICATION — path unchanged from Q5."""
    from agentgauge.fixer import _DESC_GENERATOR_GUARD_B_PROMPT

    assert "NO FABRICATION" in _DESC_GENERATOR_GUARD_B_PROMPT
