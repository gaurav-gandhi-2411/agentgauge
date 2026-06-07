from __future__ import annotations

import pytest
from mcp.types import Tool

from agentgauge.fixer import (
    _DESC_GENERATOR_SOURCE_AWARE_PROMPT,
    _generate_description,
)
from agentgauge.providers import Message, MockProvider
from evals.fixtures.q3_catalog import (
    ARM_A_DESCRIPTIONS,
    ARM_O_DESCRIPTIONS,
    CONTROL_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    INDEPENDENCE_TOKENS,
    TASKS,
    get_body_source,
    get_doc_source,
)


class RecordingMockProvider(MockProvider):
    """MockProvider that records every call's message list for prompt-content assertions."""

    def __init__(self, responses: list[str] | None = None) -> None:
        super().__init__(responses)
        self.calls: list[list[Message]] = []

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        self.calls.append(list(messages))
        return await super().chat(messages, seed=seed)


# ── Fixture structure ──────────────────────────────────────────────────────────


def test_q3_catalog_has_four_families() -> None:
    assert len(FAMILIES) == 4


def test_q3_catalog_tool_count() -> None:
    all_tools = [name for names in FAMILIES.values() for name in names]
    assert len(all_tools) == 12


def test_q3_arm_a_all_empty() -> None:
    for tools in FAMILIES.values():
        for name in tools:
            assert ARM_A_DESCRIPTIONS[name] == ""


def test_q3_arm_o_all_present_and_nonempty() -> None:
    for tools in FAMILIES.values():
        for name in tools:
            assert name in ARM_O_DESCRIPTIONS
            assert len(ARM_O_DESCRIPTIONS[name]) > 0


def test_q3_tasks_gold_tools_in_catalog() -> None:
    all_tools = {name for names in FAMILIES.values() for name in names}
    for task in TASKS:
        assert task.tool_name in all_tools, f"Task gold tool {task.tool_name!r} not in catalog"


def test_q3_tasks_anti_tautology_no_tool_names_in_description() -> None:
    """Task descriptions must not literally contain the gold tool name."""
    for task in TASKS:
        assert task.tool_name not in task.description, (
            f"Task description for {task.tool_name!r} contains the tool name — tautology risk"
        )


def test_q3_family_map_covers_all_tools() -> None:
    all_tools = {name for names in FAMILIES.values() for name in names}
    assert set(FAMILY_MAP.keys()) == all_tools


def test_q3_control_tools_set() -> None:
    assert frozenset({"find_entries", "lookup_data", "book_slot", "plan_event"}) == CONTROL_TOOLS


# ── Independence rule assertions ───────────────────────────────────────────────


def test_q3_independence_tokens_in_doc_source() -> None:
    """Each contested tool's independence token must appear in the DOC source.

    This is the independence rule check: the distinguishing fact is in the CODE,
    not derived from the oracle description.
    """
    doc_source = get_doc_source()
    for tool_name, token in INDEPENDENCE_TOKENS.items():
        assert token in doc_source, (
            f"Independence token {token!r} for tool {tool_name!r} "
            "not found in DOC source (q3_real_server.py). "
            "The distinguishing fact must be in the code, not just in the oracle description."
        )


def test_q3_independence_tokens_in_body_source() -> None:
    """Each contested tool's independence token must survive docstring stripping."""
    body_source = get_body_source()
    for tool_name, token in INDEPENDENCE_TOKENS.items():
        assert token in body_source, (
            f"Independence token {token!r} for tool {tool_name!r} "
            "not found in BODY source (docstrings stripped). "
            "The distinguishing fact must be in the implementation body, not only in docstrings."
        )


def test_q3_doc_source_has_docstrings() -> None:
    """DOC source must contain triple-quoted docstrings."""
    doc_source = get_doc_source()
    assert '"""' in doc_source, "DOC source must contain triple-quoted docstrings"


def test_q3_body_source_strips_docstrings() -> None:
    """BODY source must not contain triple-quoted docstrings (only the header comment survives)."""
    import ast

    body_source = get_body_source()
    try:
        tree = ast.parse(body_source)
    except SyntaxError as e:
        pytest.fail(f"BODY source is not valid Python after docstring stripping: {e}")

    # No function should have a string-literal docstring
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            pytest.fail(
                f"Function {node.name!r} still has a docstring in BODY source — stripping failed."
            )


def test_q3_control_tools_not_in_independence_tokens() -> None:
    """Control tools must NOT have independence tokens (they're genuinely equivalent)."""
    for name in CONTROL_TOOLS:
        assert name not in INDEPENDENCE_TOKENS, (
            f"Control tool {name!r} should not have an independence token — "
            "its implementation is truly equivalent to its pair."
        )


def test_q3_control_tools_have_equal_oracle_descriptions() -> None:
    """Each control pair must have the same oracle description (both tools are equivalent)."""
    pairs = [("find_entries", "lookup_data"), ("book_slot", "plan_event")]
    for a, b in pairs:
        assert ARM_O_DESCRIPTIONS[a] == ARM_O_DESCRIPTIONS[b], (
            f"Oracle descriptions for control pair ({a}, {b}) differ — "
            "they should be equal since the implementations are equivalent."
        )


def test_q3_gold_mapping_intact_for_contested_tasks() -> None:
    """Contested tool names must match the INDEPENDENCE_TOKENS keys."""
    contested_tools_in_tasks = {t.tool_name for t in TASKS if t.tool_name not in CONTROL_TOOLS}
    assert contested_tools_in_tasks == set(INDEPENDENCE_TOKENS.keys()), (
        "Mismatch between contested task gold tools and INDEPENDENCE_TOKENS keys. "
        "Check q3_catalog.py TASKS list and INDEPENDENCE_TOKENS dict."
    )


# ── Source-fed generator prompt ────────────────────────────────────────────────


def test_q3_source_aware_prompt_contains_no_fabrication_guard() -> None:
    """The source-aware prompt must include the no-fabrication instruction."""
    assert "NO FABRICATION" in _DESC_GENERATOR_SOURCE_AWARE_PROMPT
    assert "Only state a difference" in _DESC_GENERATOR_SOURCE_AWARE_PROMPT


def test_q3_source_aware_prompt_references_source_code() -> None:
    """The prompt must tell the generator to use the source code as evidence."""
    assert "{source}" in _DESC_GENERATOR_SOURCE_AWARE_PROMPT
    assert "source code" in _DESC_GENERATOR_SOURCE_AWARE_PROMPT.lower()


def test_q3_source_aware_prompt_format_assembles() -> None:
    """The source-aware prompt must format without KeyError."""
    tool = Tool(name="store_item", description="", inputSchema={"type": "object"})
    source_snippet = "def _handle_store_item(query): _ttl_store[query] = {'value': query}"
    prompt = _DESC_GENERATOR_SOURCE_AWARE_PROMPT.format(
        name=tool.name,
        current=tool.description or "(none)",
        schema=tool.inputSchema,
        source=source_snippet,
    )
    assert "store_item" in prompt
    assert source_snippet in prompt
    assert "NO FABRICATION" in prompt


# ── MockProvider tests for source-fed path ─────────────────────────────────────


@pytest.mark.asyncio
async def test_q3_generate_description_source_param_calls_generator() -> None:
    """With source=<text>, _generate_description must invoke the generator and return its output."""
    tool = Tool(name="store_item", description="", inputSchema={"type": "object"})
    source = "async def _handle_store_item(q): _ttl_store[q] = True"
    provider = RecordingMockProvider(["Stores the query value in the in-memory TTL cache."])
    result = await _generate_description(tool, provider, source=source)
    assert result == "Stores the query value in the in-memory TTL cache."
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_q3_generate_description_source_takes_priority_over_neighbors() -> None:
    """source= takes priority over neighbors= — catalog-aware prompt must not be used."""
    tool = Tool(name="persist_row", description="", inputSchema={"type": "object"})
    neighbor = Tool(name="save_record", description="", inputSchema={"type": "object"})
    source = "if query in _db: raise ValueError(...)"
    provider = RecordingMockProvider(["Inserts a new row; raises if key exists."])
    await _generate_description(tool, provider, source=source, neighbors=[neighbor])
    # Verify source-aware prompt was used (contains the source snippet)
    prompt_sent = provider.calls[0][0].content
    assert source in prompt_sent
    assert "NO FABRICATION" in prompt_sent
    # Should NOT contain the "neighbors" key from the catalog-aware prompt
    assert "Confusable neighbors" not in prompt_sent


@pytest.mark.asyncio
async def test_q3_generate_description_no_source_falls_back_to_catalog_aware() -> None:
    """Without source=, providing neighbors= uses the catalog-aware prompt."""
    tool = Tool(name="save_record", description="", inputSchema={"type": "object"})
    neighbor = Tool(name="persist_row", description="", inputSchema={"type": "object"})
    provider = RecordingMockProvider(["Saves a record."])
    await _generate_description(tool, provider, neighbors=[neighbor])
    prompt_sent = provider.calls[0][0].content
    assert "Confusable neighbors" in prompt_sent
    assert "{source}" not in prompt_sent  # source-aware template not used


@pytest.mark.asyncio
async def test_q3_generate_description_source_response_stripped() -> None:
    """Generator response must be stripped of surrounding whitespace."""
    tool = Tool(name="write_entry", description="", inputSchema={"type": "object"})
    source = "async def _handle_write_entry(q): _audit_log.append({'entry': q})"
    provider = RecordingMockProvider(["  Appends to the audit log.  \n"])
    result = await _generate_description(tool, provider, source=source)
    assert result == "Appends to the audit log."


@pytest.mark.asyncio
async def test_q3_generate_description_empty_source_uses_fallback_prompt() -> None:
    """Empty string source= should NOT use the source-aware prompt (falsy check)."""
    tool = Tool(name="delete_record", description="", inputSchema={"type": "object"})
    provider = RecordingMockProvider(["Deletes a record."])
    await _generate_description(tool, provider, source="")
    prompt_sent = provider.calls[0][0].content
    # Empty string is falsy → falls back to per-tool prompt
    assert "{source}" not in prompt_sent
    assert "Source code" not in prompt_sent


# ── Server files and fixture file presence ─────────────────────────────────────


def test_q3_real_server_file_exists() -> None:
    from pathlib import Path

    server_path = Path(__file__).parent.parent / "examples" / "q3_real_server.py"
    assert server_path.exists(), "examples/q3_real_server.py must exist"


def test_q3_arm_servers_exist() -> None:
    from pathlib import Path

    base = Path(__file__).parent.parent / "examples"
    for arm in ["q3_arm_a.py", "q3_arm_f_doc.py", "q3_arm_f_body.py", "q3_arm_o.py"]:
        assert (base / arm).exists(), f"examples/{arm} must exist"


def test_q3_doc_source_is_real_server_source() -> None:
    """get_doc_source() must read the actual q3_real_server.py file."""
    from pathlib import Path

    expected = (Path(__file__).parent.parent / "examples" / "q3_real_server.py").read_text(
        encoding="utf-8"
    )
    assert get_doc_source() == expected
