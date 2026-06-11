from __future__ import annotations

import httpx
import pytest
import respx

from agentgauge.frontier import classify_frontier_outcome
from agentgauge.providers import (
    _INPUT_COST_PER_M,
    _OUTPUT_COST_PER_M,
    ApiAgentProvider,
    CostCeilingError,
    Message,
    OpenAICompatibleProvider,
    Provider,
)

# ── ApiAgentProvider key-guard tests ─────────────────────────────────────────


def test_api_agent_provider_rejects_ambient_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passing api_key_env='ANTHROPIC_API_KEY' must raise — anti-double-billing guard."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        ApiAgentProvider(model="claude-haiku-4-5-20251001", api_key_env="ANTHROPIC_API_KEY")


def test_api_agent_provider_raises_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing env var raises ValueError, not a silent None key."""
    monkeypatch.delenv("FRONTIER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FRONTIER_API_KEY"):
        ApiAgentProvider(model="claude-haiku-4-5-20251001", api_key_env="FRONTIER_API_KEY")


def test_api_agent_provider_reads_correct_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider reads from the passed env var, NOT from ANTHROPIC_API_KEY."""
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-frontier-correct")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-NOT-be-used")
    provider = ApiAgentProvider(model="claude-haiku-4-5-20251001", api_key_env="FRONTIER_API_KEY")
    assert provider._api_key == "sk-frontier-correct"
    assert provider._api_key != "sk-ant-should-NOT-be-used"


def test_api_agent_provider_ignores_ambient_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with ANTHROPIC_API_KEY set, provider uses only the specified env var."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-ambient")
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-frontier-explicit")
    provider = ApiAgentProvider(model="claude-sonnet-4-6", api_key_env="FRONTIER_API_KEY")
    assert provider._api_key == "sk-frontier-explicit"


# ── Protocol conformance ──────────────────────────────────────────────────────


def test_api_agent_provider_conforms_to_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    """ApiAgentProvider satisfies the Provider runtime-checkable protocol."""
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-test")
    provider = ApiAgentProvider("claude-haiku-4-5-20251001", api_key_env="FRONTIER_API_KEY")
    assert isinstance(provider, Provider)
    assert provider.model_name == "claude-haiku-4-5-20251001"


# ── Cost-ceiling abort ────────────────────────────────────────────────────────


async def test_cost_ceiling_abort_fires_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """chat() raises CostCeilingError when ceiling is 0 — no network call made."""
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-test")
    provider = ApiAgentProvider(
        "claude-haiku-4-5-20251001", api_key_env="FRONTIER_API_KEY", cost_ceiling_usd=0.0
    )
    with pytest.raises(CostCeilingError):
        await provider.chat([Message(role="user", content="hello")])


async def test_cost_ceiling_abort_after_tokens_accumulated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CostCeilingError fires after spend exceeds ceiling (post-call check)."""
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-test")
    # Set ceiling to essentially zero cost (1 micro-dollar)
    provider = ApiAgentProvider(
        "claude-haiku-4-5-20251001",
        api_key_env="FRONTIER_API_KEY",
        cost_ceiling_usd=0.000001,
    )
    # Simulate tokens having been accumulated
    provider._tokens_in = 100_000
    provider._tokens_out = 10_000

    with pytest.raises(CostCeilingError):
        await provider.chat([Message(role="user", content="hello")])


# ── Cost tracking ─────────────────────────────────────────────────────────────


@respx.mock
async def test_cost_tracking_after_successful_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tokens from API response are accumulated in _tokens_in / _tokens_out."""
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-test")
    provider = ApiAgentProvider(
        "claude-haiku-4-5-20251001",
        api_key_env="FRONTIER_API_KEY",
        cost_ceiling_usd=100.0,
    )

    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "get_record"}],
                "usage": {"input_tokens": 50, "output_tokens": 10},
            },
        )
    )

    result = await provider.chat([Message(role="user", content="which tool?")])
    assert result == "get_record"
    assert provider.tokens_in == 50
    assert provider.tokens_out == 10
    expected_cost = 50 * 0.80 / 1_000_000 + 10 * 4.0 / 1_000_000
    assert abs(provider.total_cost_usd - expected_cost) < 1e-10


@respx.mock
async def test_rate_limit_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 responses trigger retry with backoff; success on second attempt."""
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-test")
    provider = ApiAgentProvider(
        "claude-haiku-4-5-20251001",
        api_key_env="FRONTIER_API_KEY",
        cost_ceiling_usd=100.0,
        max_retries=3,
    )

    call_count = 0

    def side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"error": "rate limit"})
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "save_record"}],
                "usage": {"input_tokens": 20, "output_tokens": 5},
            },
        )

    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=side_effect)

    # Patch asyncio.sleep to skip real wait
    import unittest.mock as mock

    with mock.patch("agentgauge.providers.asyncio.sleep", return_value=None):
        result = await provider.chat([Message(role="user", content="task")])

    assert result == "save_record"
    assert call_count == 2


# ── classify_frontier_outcome ─────────────────────────────────────────────────

_TOOLS = frozenset({"get_record", "fetch_record", "read_entry", "load_item"})


def test_classify_correct_selection() -> None:
    assert classify_frontier_outcome("get_record", _TOOLS, "get_record") == "SELECTED-CORRECT"


def test_classify_correct_with_trailing_punctuation() -> None:
    """Trailing punctuation stripped before tool lookup."""
    assert classify_frontier_outcome("get_record.", _TOOLS, "get_record") == "SELECTED-CORRECT"
    assert classify_frontier_outcome("get_record,", _TOOLS, "get_record") == "SELECTED-CORRECT"


def test_classify_wrong_selection() -> None:
    assert classify_frontier_outcome("fetch_record", _TOOLS, "get_record") == "SELECTED-WRONG"


def test_classify_hedge_uncertainty() -> None:
    """I'm not sure / unsure / unclear → ABSTAINED-OR-HEDGED (not WRONG)."""
    assert (
        classify_frontier_outcome("I'm not sure which tool to use.", _TOOLS, "get_record")
        == "ABSTAINED-OR-HEDGED"
    )
    assert (
        classify_frontier_outcome(
            "I am not sure between get_record and fetch_record.", _TOOLS, "get_record"
        )
        == "ABSTAINED-OR-HEDGED"
    )


def test_classify_clarifying_question() -> None:
    assert (
        classify_frontier_outcome(
            "Could you clarify whether you want a database or API lookup?", _TOOLS, "get_record"
        )
        == "ABSTAINED-OR-HEDGED"
    )


def test_classify_either_or_hedge() -> None:
    assert (
        classify_frontier_outcome(
            "Either get_record or fetch_record could work depending on the context.",
            _TOOLS,
            "get_record",
        )
        == "ABSTAINED-OR-HEDGED"
    )


def test_classify_explicit_inability() -> None:
    assert (
        classify_frontier_outcome(
            "I cannot determine the correct tool without more context.", _TOOLS, "get_record"
        )
        == "ABSTAINED-OR-HEDGED"
    )


def test_classify_multiword_non_tool_response() -> None:
    """A multi-word response that doesn't name a valid tool → ABSTAINED-OR-HEDGED."""
    assert (
        classify_frontier_outcome(
            "This task requires additional information before selecting a tool.",
            _TOOLS,
            "get_record",
        )
        == "ABSTAINED-OR-HEDGED"
    )


def test_classify_short_non_tool_response() -> None:
    """Short opaque non-tool response → ABSTAINED-OR-HEDGED."""
    assert classify_frontier_outcome("unknown_tool", _TOOLS, "get_record") == "ABSTAINED-OR-HEDGED"


def test_classify_empty_response() -> None:
    assert classify_frontier_outcome("", _TOOLS, "get_record") == "ABSTAINED-OR-HEDGED"


# ── Pricing table sanity ──────────────────────────────────────────────────────


def test_pricing_tables_have_matching_keys() -> None:
    """Input and output pricing tables must cover the same model IDs."""
    assert set(_INPUT_COST_PER_M.keys()) == set(_OUTPUT_COST_PER_M.keys())


def test_pricing_positive() -> None:
    """All pricing entries must be positive."""
    for model, cost in _INPUT_COST_PER_M.items():
        assert cost > 0, f"Input cost for {model} is non-positive"
    for model, cost in _OUTPUT_COST_PER_M.items():
        assert cost > 0, f"Output cost for {model} is non-positive"


# ── OpenAICompatibleProvider ──────────────────────────────────────────────────


def test_openai_compat_rejects_anthropic_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """ANTHROPIC_API_KEY is forbidden for OpenAICompatibleProvider too."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        OpenAICompatibleProvider(
            model="llama3",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="ANTHROPIC_API_KEY",
        )


def test_openai_compat_raises_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing env var raises ValueError."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenAICompatibleProvider(
            model="llama3",
            base_url="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
        )


def test_openai_compat_keyless_local_server() -> None:
    """api_key_env=None is allowed for local keyless servers (e.g. vLLM)."""
    provider = OpenAICompatibleProvider(
        model="llama3",
        base_url="http://localhost:8000/v1",
        api_key_env=None,
    )
    assert provider.model_name == "llama3"
    assert isinstance(provider, Provider)


def test_openai_compat_conforms_to_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAICompatibleProvider satisfies the Provider runtime-checkable protocol."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    provider = OpenAICompatibleProvider(
        model="meta-llama/llama-3.3-70b-instruct",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    )
    assert isinstance(provider, Provider)
    assert provider.model_name == "meta-llama/llama-3.3-70b-instruct"


async def test_openai_compat_cost_ceiling_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    """CostCeilingError fires at zero ceiling before any network call."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    provider = OpenAICompatibleProvider(
        model="llama3",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        cost_ceiling_usd=0.0,
    )
    with pytest.raises(CostCeilingError):
        await provider.chat([Message(role="user", content="hello")])


@respx.mock
async def test_openai_compat_successful_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful call returns content and accumulates token counts."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    provider = OpenAICompatibleProvider(
        model="meta-llama/llama-3.3-70b-instruct",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        cost_ceiling_usd=100.0,
    )

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "get_record"}}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 3},
            },
        )
    )

    result = await provider.chat([Message(role="user", content="which tool?")])
    assert result == "get_record"
    assert provider.tokens_in == 80
    assert provider.tokens_out == 3


@respx.mock
async def test_openai_compat_rate_limit_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 retries with backoff; success on second attempt."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    provider = OpenAICompatibleProvider(
        model="llama3",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        cost_ceiling_usd=100.0,
        max_retries=3,
    )
    call_count = 0

    def side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"error": "rate limit"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "fetch_record"}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 2},
            },
        )

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(side_effect=side_effect)

    import unittest.mock as mock

    with mock.patch("agentgauge.providers.asyncio.sleep", return_value=None):
        result = await provider.chat([Message(role="user", content="task")])

    assert result == "fetch_record"
    assert call_count == 2


def test_openai_compat_bearer_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider stores the key from the env var (not ANTHROPIC_API_KEY)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-explicit")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-NOT-be-used")
    provider = OpenAICompatibleProvider(
        model="llama3",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    )
    assert provider._api_key == "sk-or-explicit"
    assert provider._api_key != "sk-ant-should-NOT-be-used"
