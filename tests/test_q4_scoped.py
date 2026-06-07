from __future__ import annotations

import asyncio

import pytest
from mcp.types import Tool

from agentgauge.fixer import (
    _DESC_GENERATOR_SCOPED_SOURCE_PROMPT,
    _extract_function_surface,
    _extract_scoped_function,
    _generate_description,
)
from agentgauge.providers import Message, MockProvider

# ── Minimal two-function inline source used for all scoped extractor tests ─────
# Two functions: target (_handle_find_entries) and neighbor (_handle_lookup_data).
# _handle_lookup_data body contains `_search_store` and a body-only return statement.
# The test asserts these body symbols are absent from the extracted find_entries surface.

_TWO_FUNC_SOURCE = '''\
async def _handle_find_entries(query: str) -> str:
    """Return all entries whose key contains the query string."""
    matches = [v for k, v in _search_store.items() if query in k]
    return f"find_entries('{query}'): {len(matches)} result(s)"


async def _handle_lookup_data(query: str) -> str:
    """Return all entries whose key contains the query string."""
    matches = [v for k, v in _search_store.items() if query in k]
    return f"lookup_data('{query}'): {len(matches)} result(s)"
'''

# Three-function source with distinct backing stores to test foreign-symbol exclusion.
# _handle_persist_row uses _db; _handle_find_entries uses _search_store only.
_THREE_FUNC_SOURCE = '''\
async def _handle_persist_row(query: str) -> str:
    """Insert a new row. Raises if key exists."""
    if query in _db:
        raise ValueError(f"Row exists")
    _db[query] = query
    return f"Inserted '{query}' into _db"


async def _handle_save_record(query: str) -> str:
    """Upsert a record."""
    existed = query in _db
    _db[query] = query
    return f"{'updated' if existed else 'created'}"


async def _handle_find_entries(query: str) -> str:
    """Return all entries whose key contains the query string."""
    matches = [v for k, v in _search_store.items() if query in k]
    return f"find_entries: {len(matches)} result(s)"
'''


# ── Q4: Scoped extractor ───────────────────────────────────────────────────────


def test_extract_scoped_function_returns_target_def() -> None:
    """Scoped extractor returns the target function's def line."""
    result = _extract_scoped_function(_TWO_FUNC_SOURCE, "find_entries")
    assert "def _handle_find_entries" in result


def test_extract_scoped_function_excludes_other_function_def() -> None:
    """Scoped extractor does NOT include the other function's def line."""
    result = _extract_scoped_function(_TWO_FUNC_SOURCE, "find_entries")
    assert "_handle_lookup_data" not in result


def test_extract_scoped_function_excludes_foreign_symbols() -> None:
    """Key guarantee: _db (belonging to persist_row/save_record) absent from find_entries extract."""
    result = _extract_scoped_function(_THREE_FUNC_SOURCE, "find_entries")
    assert "_db" not in result, (
        "SCOPING FAILURE: _db (a symbol from other tools) appeared in find_entries extraction"
    )
    assert "_search_store" in result


def test_extract_scoped_function_includes_body() -> None:
    """Scoped extractor includes the function body (not just the def line)."""
    result = _extract_scoped_function(_TWO_FUNC_SOURCE, "find_entries")
    assert "_search_store" in result
    assert "find_entries" in result


def test_extract_scoped_function_returns_empty_when_not_found() -> None:
    """Returns empty string when the handler name is not in the source."""
    result = _extract_scoped_function(_TWO_FUNC_SOURCE, "nonexistent_tool")
    assert result == ""


# ── Q4: Neighbor surface extractor ────────────────────────────────────────────


def test_extract_function_surface_includes_def_line() -> None:
    """Surface always includes the def line."""
    surface = _extract_function_surface(_TWO_FUNC_SOURCE, "lookup_data")
    assert "def _handle_lookup_data" in surface


def test_extract_function_surface_includes_docstring() -> None:
    """Surface includes the triple-quoted docstring."""
    surface = _extract_function_surface(_TWO_FUNC_SOURCE, "lookup_data")
    assert '"""Return all entries' in surface


def test_extract_function_surface_excludes_body_lines() -> None:
    """KEY MECHANICAL GUARANTEE: body lines must NOT appear in the surface.

    Specifically, the return statement and body logic of _handle_lookup_data must
    be absent — this ensures no neighbor body can appear in the assembled prompt,
    making cross-tool body-misattribution impossible by construction.
    """
    surface = _extract_function_surface(_TWO_FUNC_SOURCE, "lookup_data")
    # Body lines that must NOT appear
    assert "matches = " not in surface, (
        "NEIGHBOR-BODY GUARD FAILED: body line 'matches = ' found in surface"
    )
    assert 'return f"lookup_data' not in surface, (
        "NEIGHBOR-BODY GUARD FAILED: return statement found in surface"
    )


def test_extract_function_surface_returns_empty_when_not_found() -> None:
    surface = _extract_function_surface(_TWO_FUNC_SOURCE, "nonexistent_tool")
    assert surface == ""


# ── Q4: Scoped prompt composition ─────────────────────────────────────────────


def test_scoped_prompt_contains_no_fabrication_guard() -> None:
    """The scoped prompt template always contains the NO FABRICATION instruction."""
    assert "NO FABRICATION" in _DESC_GENERATOR_SCOPED_SOURCE_PROMPT
    assert "DO NOT" in _DESC_GENERATOR_SCOPED_SOURCE_PROMPT


def test_scoped_prompt_contains_scope_declaration() -> None:
    """The scoped prompt explicitly says the source is only this tool's function."""
    assert "ONLY this tool" in _DESC_GENERATOR_SCOPED_SOURCE_PROMPT


def test_scoped_prompt_contains_neighbor_surface_note() -> None:
    """The scoped prompt states neighbors are shown without bodies."""
    assert "bodies not shown" in _DESC_GENERATOR_SCOPED_SOURCE_PROMPT or \
           "no bodies" in _DESC_GENERATOR_SCOPED_SOURCE_PROMPT


async def test_generate_description_scoped_uses_scoped_prompt() -> None:
    """When scoped_source is provided, prompt contains scoped content and no-fabrication guard."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "Searches the store for entries matching query."

    tool = Tool(name="find_entries", description="", inputSchema={"type": "object"})
    scoped_src = 'async def _handle_find_entries(query: str) -> str:\n    """Doc."""\n    return "x"'
    ns_text = 'async def _handle_lookup_data(query: str) -> str:\n    """Doc."""'

    await _generate_description(
        tool,
        CapturingProvider(),
        scoped_source=scoped_src,
        neighbor_surfaces_text=ns_text,
    )

    assert captured, "No prompt captured"
    prompt = captured[0]
    assert "NO FABRICATION" in prompt
    assert "ONLY this tool" in prompt
    assert scoped_src in prompt
    assert ns_text in prompt


async def test_generate_description_scoped_and_neighbors_compose() -> None:
    """Scoped source and neighbor surfaces appear together in one prompt."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "A plain description."

    tool = Tool(name="find_entries", description="", inputSchema={})
    await _generate_description(
        tool,
        CapturingProvider(),
        scoped_source="async def _handle_find_entries(q): ...",
        neighbor_surfaces_text="async def _handle_lookup_data(q): ...",
    )

    prompt = captured[0]
    # Both must appear in the same prompt — composition test
    assert "_handle_find_entries" in prompt
    assert "_handle_lookup_data" in prompt


async def test_generate_description_scoped_no_neighbor_surfaces() -> None:
    """scoped_source without neighbor_surfaces_text still uses scoped prompt."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "A description."

    tool = Tool(name="store_item", description="", inputSchema={})
    await _generate_description(
        tool,
        CapturingProvider(),
        scoped_source="async def _handle_store_item(q): ...",
    )

    prompt = captured[0]
    assert "ONLY this tool" in prompt
    assert "_handle_store_item" in prompt


async def test_generate_description_scoped_overrides_source() -> None:
    """scoped_source takes priority over source (whole-file)."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "OK."

    tool = Tool(name="mystery", description="", inputSchema={})
    await _generate_description(
        tool,
        CapturingProvider(),
        scoped_source="async def _handle_mystery(q): ...",
        source="full_file_contents_here",
    )

    prompt = captured[0]
    # Scoped path used — not whole-file path
    assert "ONLY this tool" in prompt
    assert "full_file_contents_here" not in prompt


async def test_generate_description_uses_mock_provider() -> None:
    """MockProvider works with the scoped path — no network calls in CI."""
    tool = Tool(name="find_entries", description="", inputSchema={})
    provider = MockProvider(responses=["Return entries matching the query string."])
    result = await _generate_description(
        tool,
        provider,
        scoped_source="async def _handle_find_entries(q: str) -> str:\n    ...",
        neighbor_surfaces_text="async def _handle_lookup_data(q: str) -> str:\n    ...",
    )
    assert result == "Return entries matching the query string."


# ── Q4: No-misattribution mechanical guarantee (the key safety property) ──────


def test_neighbor_body_absent_from_assembled_prompt_guarantee() -> None:
    """MECHANICAL GUARANTEE: when using _extract_function_surface for neighbors,
    their body lines cannot appear in the assembled neighbor_surfaces_text.

    This test asserts the end-to-end property: for the find_entries/lookup_data
    equivalent pair, assembling lookup_data as a surface excludes its body lines,
    so they cannot misattribute into find_entries's description.
    """
    # _handle_lookup_data body: "matches = [v for k, v in _search_store.items()..."
    # This must NOT appear in the surface used in the Q4 prompt.
    surface = _extract_function_surface(_TWO_FUNC_SOURCE, "lookup_data")
    # Assemble as neighbor_surfaces_text would be
    neighbor_surfaces_text = f"Neighbor: lookup_data\n{surface}"

    # Key assertion: no body line from lookup_data appears in the assembled text
    assert "matches = " not in neighbor_surfaces_text
    assert "return f" not in neighbor_surfaces_text
    # But def and docstring ARE present
    assert "def _handle_lookup_data" in neighbor_surfaces_text
