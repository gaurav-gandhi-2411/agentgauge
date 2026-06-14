"""CI tests for the P2-A internal-proxy catalog.

Verifies catalog integrity, description constraints, schema structure,
and the independence rule (MIRROR_DOCSTRING_SIGNALS must appear in the
mirror server's handler docstrings).
"""

from __future__ import annotations

from pathlib import Path

from evals.fixtures.p2a_internal_proxy_catalog import (
    ALL_TOOLS,
    ARM_A_DESCRIPTIONS,
    ARM_O_DESCRIPTIONS,
    CONTESTED_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    MIRROR_DOCSTRING_SIGNALS,
    TASKS,
    THOROUGH_TOOLS,
    TOOL_SCHEMAS,
)

_MIRROR_PATH = Path(__file__).parent.parent / "examples" / "p2a_internal_proxy_mirror.py"


# ── Catalog size ───────────────────────────────────────────────────────────────


def test_p2a_all_tools_count() -> None:
    assert len(ALL_TOOLS) == 48, f"Expected 48 tools, got {len(ALL_TOOLS)}"


def test_p2a_contested_tools_count() -> None:
    assert len(CONTESTED_TOOLS) == 31, f"Expected 31 contested tools, got {len(CONTESTED_TOOLS)}"


def test_p2a_thorough_tools_count() -> None:
    assert len(THOROUGH_TOOLS) == 17, f"Expected 17 thorough tools, got {len(THOROUGH_TOOLS)}"


# ── Contested / thorough partition ─────────────────────────────────────────────


def test_p2a_contested_thorough_disjoint() -> None:
    overlap = CONTESTED_TOOLS & THOROUGH_TOOLS
    assert overlap == set(), f"CONTESTED_TOOLS ∩ THOROUGH_TOOLS must be empty, got: {overlap}"


def test_p2a_contested_thorough_cover_all() -> None:
    union = CONTESTED_TOOLS | THOROUGH_TOOLS
    assert union == set(ALL_TOOLS), (
        f"CONTESTED_TOOLS ∪ THOROUGH_TOOLS must equal ALL_TOOLS. "
        f"Missing: {set(ALL_TOOLS) - union}  Extra: {union - set(ALL_TOOLS)}"
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────


def test_p2a_task_count() -> None:
    assert len(TASKS) == 48, f"Expected 48 tasks, got {len(TASKS)}"


def test_p2a_task_tool_names_match_all_tools() -> None:
    task_tools = {t.tool_name for t in TASKS}
    assert task_tools == set(ALL_TOOLS), (
        f"Task tool_names must match ALL_TOOLS exactly. "
        f"Missing: {set(ALL_TOOLS) - task_tools}  Extra: {task_tools - set(ALL_TOOLS)}"
    )


def test_p2a_one_task_per_tool() -> None:
    tool_names = [t.tool_name for t in TASKS]
    assert len(tool_names) == len(set(tool_names)), "Duplicate tool_name in TASKS"


# ── Arm A descriptions ─────────────────────────────────────────────────────────


def test_p2a_arm_a_covers_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in ARM_A_DESCRIPTIONS, f"ARM_A_DESCRIPTIONS missing '{tool}'"


def test_p2a_arm_a_single_sentence() -> None:
    """Each Arm A value must be one sentence: no newlines, ends with a period."""
    for tool, desc in ARM_A_DESCRIPTIONS.items():
        assert "\n" not in desc, (
            f"ARM_A_DESCRIPTIONS['{tool}'] contains a newline: {desc!r}"
        )
        assert desc.endswith("."), (
            f"ARM_A_DESCRIPTIONS['{tool}'] does not end with '.': {desc!r}"
        )


def test_p2a_arm_a_at_most_7_words() -> None:
    """Thin descriptions constraint: each Arm A value has at most 7 words."""
    for tool, desc in ARM_A_DESCRIPTIONS.items():
        word_count = len(desc.split())
        assert word_count <= 7, (
            f"ARM_A_DESCRIPTIONS['{tool}'] has {word_count} words (max 7): {desc!r}"
        )


# ── Arm O descriptions ─────────────────────────────────────────────────────────


def test_p2a_arm_o_covers_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in ARM_O_DESCRIPTIONS, f"ARM_O_DESCRIPTIONS missing '{tool}'"


def test_p2a_arm_o_nonempty() -> None:
    for tool in ALL_TOOLS:
        assert len(ARM_O_DESCRIPTIONS[tool]) > 0, f"ARM_O_DESCRIPTIONS['{tool}'] is empty"


# ── Tool schemas ───────────────────────────────────────────────────────────────


def test_p2a_tool_schemas_covers_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in TOOL_SCHEMAS, f"TOOL_SCHEMAS missing '{tool}'"


def test_p2a_tool_schemas_are_object_type() -> None:
    for tool in ALL_TOOLS:
        schema = TOOL_SCHEMAS[tool]
        assert isinstance(schema, dict), f"TOOL_SCHEMAS['{tool}'] is not a dict"
        assert schema.get("type") == "object", (
            f"TOOL_SCHEMAS['{tool}']['type'] must be 'object', got {schema.get('type')!r}"
        )


# ── Mirror docstring signals (independence rule) ───────────────────────────────


def test_p2a_mirror_server_exists() -> None:
    assert _MIRROR_PATH.exists(), f"Mirror server not found at {_MIRROR_PATH}"


def test_p2a_mirror_docstring_signals_present() -> None:
    """Independence rule: each signal phrase must appear in the corresponding
    handler's docstring within 500 chars of the def _handle_{tool_name} line.

    Whitespace (including newlines and leading indent) is collapsed before
    matching, because Python docstrings may wrap long lines.

    This CI assertion enforces that ARM_O_DESCRIPTIONS are derived from the mirror
    handler docstrings, not invented independently.
    """
    source = _MIRROR_PATH.read_text(encoding="utf-8")
    for tool, signal in MIRROR_DOCSTRING_SIGNALS.items():
        handler_marker = f"def _handle_{tool}("
        idx = source.find(handler_marker)
        assert idx >= 0, (
            f"Handler _handle_{tool}() not found in mirror server {_MIRROR_PATH.name}"
        )
        raw_snippet = source[idx : idx + 500]
        # Collapse all runs of whitespace (including newline + indent) to a single space
        # so signals survive docstring line-wrapping.
        snippet = " ".join(raw_snippet.split())
        assert signal in snippet, (
            f"Independence signal {signal!r} not found within 500 chars of "
            f"_handle_{tool}() in {_MIRROR_PATH.name}. "
            f"Collapsed handler text: {snippet[:300]!r}"
        )


# ── FAMILY_MAP consistency ─────────────────────────────────────────────────────


def test_p2a_family_map_covers_all_tools() -> None:
    for tool in ALL_TOOLS:
        assert tool in FAMILY_MAP, f"'{tool}' missing from FAMILY_MAP"


def test_p2a_family_map_consistent_with_families() -> None:
    for tool, family in FAMILY_MAP.items():
        assert tool in FAMILIES[family], (
            f"FAMILY_MAP['{tool}']={family!r} is inconsistent with FAMILIES"
        )
