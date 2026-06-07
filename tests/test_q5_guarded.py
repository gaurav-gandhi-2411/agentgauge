from __future__ import annotations

from mcp.types import Tool

from agentgauge.fixer import (
    _DESC_GENERATOR_GUARD_B_PROMPT,
    _contains_comparative_neighbor_claim,
    _generate_description,
)
from agentgauge.providers import Message, MockProvider

# ── Prompt content assertions (deterministic, no model) ───────────────────────


def test_guard_b_prompt_contains_no_fabrication_instruction() -> None:
    """Guard B prompt must contain the NO FABRICATION instruction."""
    assert "NO FABRICATION" in _DESC_GENERATOR_GUARD_B_PROMPT


def test_guard_b_prompt_forbids_comparative_claims() -> None:
    """Guard B prompt must explicitly forbid comparative neighbor claims."""
    assert "must NOT" in _DESC_GENERATOR_GUARD_B_PROMPT or "FORBIDDEN" in _DESC_GENERATOR_GUARD_B_PROMPT


def test_guard_b_prompt_includes_good_example() -> None:
    """Guard B prompt must contain a target-grounded GOOD example."""
    assert "GOOD" in _DESC_GENERATOR_GUARD_B_PROMPT or "target-grounded" in _DESC_GENERATOR_GUARD_B_PROMPT


def test_guard_b_prompt_includes_forbidden_example() -> None:
    """Guard B prompt must contain a FORBIDDEN comparative example."""
    assert "FORBIDDEN" in _DESC_GENERATOR_GUARD_B_PROMPT or "Unlike lookup_data" in _DESC_GENERATOR_GUARD_B_PROMPT


def test_guard_b_prompt_neighbor_surfaces_include_docstrings() -> None:
    """Guard B prompt must indicate that neighbor docstrings are included in surfaces."""
    assert "docstring" in _DESC_GENERATOR_GUARD_B_PROMPT


# ── Post-check function (deterministic, no model) ─────────────────────────────


def test_comparative_claim_detection_unlike_neighbor() -> None:
    """'Unlike <neighbor>, which ...' pattern triggers the detector."""
    result = _contains_comparative_neighbor_claim(
        "Unlike lookup_data, which returns full entries, this tool returns a count.",
        ["lookup_data"],
    )
    assert result is True


def test_comparative_claim_detection_whereas_neighbor() -> None:
    """'Whereas <neighbor> ...' pattern triggers the detector."""
    result = _contains_comparative_neighbor_claim(
        "Whereas book_slot schedules, this archives.",
        ["book_slot"],
    )
    assert result is True


def test_comparative_claim_clean_description_passes() -> None:
    """A plain target-grounded description with no comparative claims passes."""
    result = _contains_comparative_neighbor_claim(
        "Returns a count of matching entries.",
        ["lookup_data"],
    )
    assert result is False


def test_comparative_claim_no_neighbors_passes() -> None:
    """Empty neighbor list always passes."""
    result = _contains_comparative_neighbor_claim("Some description.", [])
    assert result is False


def test_comparative_claim_unrelated_unlike_passes() -> None:
    """'unlike' not followed by a known neighbor name does not trigger."""
    result = _contains_comparative_neighbor_claim(
        "Unlike a database, this uses memory.",
        ["lookup_data"],
    )
    assert result is False


# ── MockProvider path — prompt routing (async, MockProvider) ──────────────────


async def test_generate_description_guard_b_uses_guard_b_prompt() -> None:
    """With guard_b=True and scoped_source, captured prompt contains Guard B FORBIDDEN text."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "Returns a count of matching entries."

    tool = Tool(name="find_entries", description="", inputSchema={"type": "object"})
    scoped_src = (
        'async def _handle_find_entries(query: str) -> str:\n'
        '    """Return all entries whose key contains the query string."""\n'
        '    matches = [v for k, v in _store.items() if query in k]\n'
        '    return str(len(matches))'
    )

    await _generate_description(
        tool,
        CapturingProvider(),
        scoped_source=scoped_src,
        guard_b=True,
    )

    assert captured, "No prompt captured"
    prompt = captured[0]
    assert "FORBIDDEN" in prompt
    assert scoped_src in prompt


async def test_generate_description_guard_b_neighbor_surfaces_in_prompt() -> None:
    """With guard_b=True, neighbor_surfaces_text appears in the captured prompt."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "Returns count."

    tool = Tool(name="find_entries", description="", inputSchema={})
    ns_text = 'async def _handle_lookup_data(query: str) -> str:\n    """Returns full entries."""'

    await _generate_description(
        tool,
        CapturingProvider(),
        scoped_source="async def _handle_find_entries(q): ...",
        neighbor_surfaces_text=ns_text,
        guard_b=True,
    )

    prompt = captured[0]
    assert ns_text in prompt


async def test_generate_description_guard_b_uses_mock_provider() -> None:
    """MockProvider works with guard_b=True — no network calls in CI."""
    tool = Tool(name="find_entries", description="", inputSchema={})
    provider = MockProvider(responses=["Returns a count of matching entries."])
    result = await _generate_description(
        tool,
        provider,
        scoped_source="async def _handle_find_entries(q: str) -> str:\n    ...",
        neighbor_surfaces_text="async def _handle_lookup_data(q: str) -> str:\n    ...",
        guard_b=True,
    )
    assert result == "Returns a count of matching entries."


async def test_generate_description_guard_b_false_uses_scoped_prompt() -> None:
    """With guard_b=False and scoped_source, falls back to Q4 scoped prompt (ONLY this tool)."""
    captured: list[str] = []

    class CapturingProvider:
        model_name = "mock"

        async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
            captured.extend(m.content for m in messages)
            return "OK."

    tool = Tool(name="find_entries", description="", inputSchema={})
    await _generate_description(
        tool,
        CapturingProvider(),
        scoped_source="async def _handle_find_entries(q): ...",
        guard_b=False,
    )

    prompt = captured[0]
    # Q4 scoped prompt distinguisher — absent from Guard B prompt
    assert "bodies not shown" in prompt or "ONLY this tool" in prompt
    # Guard B's FORBIDDEN example must NOT appear
    assert "Unlike lookup_data, which returns full entries" not in prompt
