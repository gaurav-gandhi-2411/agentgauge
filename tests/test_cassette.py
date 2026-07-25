"""Tests for agentgauge.cassette -- the record/replay determinism proof.

Per `reports/v0_5_eval_doctrine.md` Component 1.1, this is the gate that must pass
before any other Wave 1 work (new adapters, cost accounting, attribution) is built:
replaying a cassette must reproduce byte-identical provider output, and feeding that
output through the existing harness's real decision path (`diff_from_trials`) must
reproduce an identical verdict, for every one of the six adapters (Ollama, Anthropic/
ApiAgentProvider, OpenAI-compatible, AWS Bedrock, Google Vertex, generic custom
endpoint). The three new (Bedrock/Vertex/custom-endpoint) adapters are proven against
mocked wire-format responses only, per the doctrine's "Note on live-provider scope":
this measures that the adapter code itself introduces no nondeterminism, not the live
providers' own response variance (out of scope, no paid calls in this repo's tests).

Wire calls are mocked with `respx` (already used this way in `tests/test_frontier.py`);
zero network access, per project rule (LLM is always mocked in tests).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from agentgauge.cassette import (
    Cassette,
    CassetteEntry,
    CassetteMiss,
    CassetteProvider,
    cassette_key,
)
from agentgauge.harness import DecomposedRate, TrialOutcome, diff_from_trials
from agentgauge.providers import (
    ApiAgentProvider,
    BedrockProvider,
    CustomEndpointProvider,
    Message,
    OllamaProvider,
    OpenAICompatibleProvider,
    VertexProvider,
)

# ── fixed fixture set (content is arbitrary; only fixedness/reuse matters) ────

# (gold_tool, prompt) pairs, reused identically across every adapter and every replay.
_FIXTURE_PROMPTS: list[tuple[str, str]] = [
    ("get_record", "Which tool fetches a single record by id?"),
    ("list_records", "Which tool lists all records?"),
    ("delete_record", "Which tool deletes a record by id?"),
    ("create_record", "Which tool creates a new record?"),
    ("update_record", "Which tool updates an existing record?"),
    ("search_records", "Which tool searches records by query?"),
    ("get_record", "Repeat: which tool fetches a single record by id?"),
    ("archive_record", "Which tool archives a record?"),
]

# Canned model responses, one per fixture prompt (by position). Deliberately mixes
# correct and incorrect selections so DecomposedRate/diff_from_trials exercise a
# non-trivial (non-0%, non-100%) decomposition, not just a degenerate all-correct case.
_CANNED_RESPONSES: list[str] = [
    "get_record",
    "list_records",
    "search_records",  # wrong (gold: delete_record)
    "create_record",
    "list_records",  # wrong (gold: update_record)
    "search_records",
    "get_record",
    "wrong_tool",  # wrong (gold: archive_record)
]

_N_REPLAYS = 20


def _trials_from_responses(responses: list[str]) -> list[TrialOutcome]:
    """Build TrialOutcome list from replayed response strings + the fixed fixture's
    gold tools. constraint_satisfaction=1.0 whenever selection is correct (argument
    construction is out of scope for this proof -- only selection varies here)."""
    trials = []
    for (gold_tool, _prompt), response in zip(_FIXTURE_PROMPTS, responses, strict=True):
        selected = response.strip()
        trials.append(
            TrialOutcome(
                task_tool_name=gold_tool,
                selected_tool=selected,
                constraint_satisfaction=1.0 if selected == gold_tool else 0.0,
            )
        )
    return trials


async def _run_fixture_set(provider: CassetteProvider) -> list[str]:
    """Run the fixed fixture set through `provider.chat()` once, in order."""
    return [
        await provider.chat([Message(role="user", content=prompt)], seed=42)
        for _gold_tool, prompt in _FIXTURE_PROMPTS
    ]


# ── cassette_key ──────────────────────────────────────────────────────────────


def test_cassette_key_is_deterministic_for_identical_input() -> None:
    messages = [Message(role="user", content="hello")]
    k1 = cassette_key("ollama", "llama3.2", 42, messages)
    k2 = cassette_key("ollama", "llama3.2", 42, messages)
    assert k1 == k2


def test_cassette_key_matches_documented_formula() -> None:
    """Locks the exact canonical-JSON + sha256[:16] formula documented in the
    module docstring, so a future refactor can't silently change key derivation
    without a failing test."""
    import hashlib
    import json

    messages = [Message(role="user", content="hello")]
    payload = {
        "provider_name": "ollama",
        "model": "llama3.2",
        "seed": 42,
        "messages": [{"role": "user", "content": "hello"}],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    assert cassette_key("ollama", "llama3.2", 42, messages) == expected


@pytest.mark.parametrize(
    ("field", "other"),
    [
        ("provider_name", "anthropic"),
        ("model", "llama3.3"),
        ("seed", 7),
    ],
)
def test_cassette_key_changes_with_each_field(field: str, other: object) -> None:
    messages = [Message(role="user", content="hello")]
    base = cassette_key("ollama", "llama3.2", 42, messages)
    kwargs = {"provider_name": "ollama", "model": "llama3.2", "seed": 42}
    kwargs[field] = other
    changed = cassette_key(**kwargs, messages=messages)
    assert base != changed


def test_cassette_key_changes_with_message_content() -> None:
    k1 = cassette_key("ollama", "llama3.2", 42, [Message(role="user", content="hello")])
    k2 = cassette_key("ollama", "llama3.2", 42, [Message(role="user", content="goodbye")])
    assert k1 != k2


def test_cassette_key_is_16_hex_chars() -> None:
    k = cassette_key("ollama", "llama3.2", 42, [Message(role="user", content="hello")])
    assert len(k) == 16
    int(k, 16)  # raises ValueError if not valid hex


# ── Cassette save/load round trip ─────────────────────────────────────────────


def test_cassette_save_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "cassette.json"
    cassette = Cassette(path)
    cassette.set("key1", CassetteEntry(response="hello", tokens_in=10, tokens_out=5))
    cassette.save()

    reloaded = Cassette.load(path)
    entry = reloaded.get("key1")
    assert entry is not None
    assert entry.response == "hello"
    assert entry.tokens_in == 10
    assert entry.tokens_out == 5


def test_cassette_load_missing_file_returns_empty(tmp_path: Path) -> None:
    cassette = Cassette.load(tmp_path / "does_not_exist.json")
    assert len(cassette) == 0


def test_cassette_get_missing_key_returns_none() -> None:
    cassette = Cassette(Path("unused.json"))
    assert cassette.get("nope") is None


# ── CassetteProvider replay-miss is a hard error ──────────────────────────────


async def test_replay_miss_raises_never_falls_back() -> None:
    empty_cassette = Cassette(Path("unused.json"))
    replay_provider = CassetteProvider(empty_cassette, "ollama", model="llama3.2")
    with pytest.raises(CassetteMiss):
        await replay_provider.chat([Message(role="user", content="unrecorded prompt")], seed=42)


def test_replay_mode_without_model_raises_value_error() -> None:
    empty_cassette = Cassette(Path("unused.json"))
    with pytest.raises(ValueError, match="model"):
        CassetteProvider(empty_cassette, "ollama")


# ── per-adapter determinism proof ─────────────────────────────────────────────


def _mock_ollama() -> None:
    def side_effect(request: httpx.Request) -> httpx.Response:
        import json as _json

        idx = side_effect.call_count  # type: ignore[attr-defined]
        side_effect.call_count += 1  # type: ignore[attr-defined]
        _ = _json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": _CANNED_RESPONSES[idx]}})

    side_effect.call_count = 0  # type: ignore[attr-defined]
    respx.post(f"{OllamaProvider.BASE_URL}/api/chat").mock(side_effect=side_effect)


def _mock_anthropic() -> None:
    def side_effect(request: httpx.Request) -> httpx.Response:
        idx = side_effect.call_count  # type: ignore[attr-defined]
        side_effect.call_count += 1  # type: ignore[attr-defined]
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": _CANNED_RESPONSES[idx]}],
                "usage": {"input_tokens": 20, "output_tokens": 3},
            },
        )

    side_effect.call_count = 0  # type: ignore[attr-defined]
    respx.post("https://api.anthropic.com/v1/messages").mock(side_effect=side_effect)


def _mock_openai_compatible(base_url: str) -> None:
    def side_effect(request: httpx.Request) -> httpx.Response:
        idx = side_effect.call_count  # type: ignore[attr-defined]
        side_effect.call_count += 1  # type: ignore[attr-defined]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": _CANNED_RESPONSES[idx]}}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 4},
            },
        )

    side_effect.call_count = 0  # type: ignore[attr-defined]
    respx.post(f"{base_url}/chat/completions").mock(side_effect=side_effect)


def _mock_bedrock(region: str = "us-east-1") -> None:
    def side_effect(request: httpx.Request) -> httpx.Response:
        idx = side_effect.call_count  # type: ignore[attr-defined]
        side_effect.call_count += 1  # type: ignore[attr-defined]
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": _CANNED_RESPONSES[idx]}],
                "usage": {"input_tokens": 25, "output_tokens": 3},
            },
        )

    side_effect.call_count = 0  # type: ignore[attr-defined]
    respx.post(
        url__regex=rf"https://bedrock-runtime\.{region}\.amazonaws\.com/model/.*/invoke"
    ).mock(side_effect=side_effect)


def _mock_vertex(region: str = "us-central1") -> None:
    def side_effect(request: httpx.Request) -> httpx.Response:
        idx = side_effect.call_count  # type: ignore[attr-defined]
        side_effect.call_count += 1  # type: ignore[attr-defined]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": _CANNED_RESPONSES[idx]}],
                            "role": "model",
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 18, "candidatesTokenCount": 4},
            },
        )

    side_effect.call_count = 0  # type: ignore[attr-defined]
    respx.post(
        url__regex=rf"https://{region}-aiplatform\.googleapis\.com/v1/projects/.*:generateContent"
    ).mock(side_effect=side_effect)


async def _record_then_replay_and_assert_determinism(
    tmp_path: Path,
    provider_name: str,
    real_provider: object,
    model: str,
) -> None:
    """Shared proof body: record once, save+reload from disk, replay N times with
    NO wire mock installed (so any accidental live call would error loudly), and
    assert byte-identical output plus an identical harness verdict on every replay.
    """
    cassette_path = tmp_path / f"{provider_name}.json"
    record_cassette = Cassette(cassette_path)
    record_provider = CassetteProvider(record_cassette, provider_name, provider=real_provider)  # type: ignore[arg-type]

    recorded_responses = await _run_fixture_set(record_provider)
    record_cassette.save()

    # Reload from disk to prove the cassette survives a process boundary, not just
    # in-memory reuse within the same test.
    replay_cassette = Cassette.load(cassette_path)
    replay_provider = CassetteProvider(replay_cassette, provider_name, model=model)

    first_trials = _trials_from_responses(recorded_responses)
    first_decomposed = DecomposedRate.from_trials(first_trials)
    first_diff = diff_from_trials(first_trials, first_trials)

    determinism_hits = 0
    for _ in range(_N_REPLAYS):
        replayed_responses = await _run_fixture_set(replay_provider)
        if replayed_responses == recorded_responses:
            determinism_hits += 1

        trials = _trials_from_responses(replayed_responses)
        decomposed = DecomposedRate.from_trials(trials)
        diff_result = diff_from_trials(trials, trials)

        assert decomposed == first_decomposed
        # Whatever verdict the harness reaches (NO_CHANGE or INSUFFICIENT_SENSITIVITY
        # at n=8 -- either is fine here; only identity across replays is asserted),
        # it must be byte-for-byte identical on every replay.
        assert diff_result.verdict == first_diff.verdict
        assert diff_result.delta == first_diff.delta
        assert diff_result.ci_lo == first_diff.ci_lo
        assert diff_result.ci_hi == first_diff.ci_hi

    determinism_rate = determinism_hits / _N_REPLAYS
    print(f"\n[cassette determinism] {provider_name}: {determinism_rate:.1%} ({determinism_hits}/{_N_REPLAYS})")
    assert determinism_rate == 1.0, (
        f"{provider_name} replay determinism rate was {determinism_rate:.2%}, not 100% "
        f"({determinism_hits}/{_N_REPLAYS} byte-identical replays)"
    )


@respx.mock
async def test_ollama_replay_determinism(tmp_path: Path) -> None:
    _mock_ollama()
    provider = OllamaProvider(model="llama3.1:8b")
    await _record_then_replay_and_assert_determinism(tmp_path, "ollama", provider, "llama3.1:8b")


@respx.mock
async def test_anthropic_replay_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-test")
    _mock_anthropic()
    provider = ApiAgentProvider(
        "claude-haiku-4-5-20251001", api_key_env="FRONTIER_API_KEY", cost_ceiling_usd=100.0
    )
    await _record_then_replay_and_assert_determinism(
        tmp_path, "anthropic", provider, "claude-haiku-4-5-20251001"
    )


@respx.mock
async def test_openai_compatible_replay_determinism(tmp_path: Path) -> None:
    base_url = "https://openrouter.ai/api/v1"
    _mock_openai_compatible(base_url)
    provider = OpenAICompatibleProvider("some-model", base_url=base_url)
    await _record_then_replay_and_assert_determinism(
        tmp_path, "openai_compatible", provider, "some-model"
    )


@respx.mock
async def test_bedrock_replay_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secretfake")
    _mock_bedrock()
    model = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    provider = BedrockProvider(
        model,
        region="us-east-1",
        aws_access_key_id_env="AWS_ACCESS_KEY_ID",
        aws_secret_access_key_env="AWS_SECRET_ACCESS_KEY",
        cost_ceiling_usd=100.0,
    )
    await _record_then_replay_and_assert_determinism(tmp_path, "bedrock", provider, model)


@respx.mock
async def test_vertex_replay_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERTEX_ACCESS_TOKEN", "ya29.test")
    _mock_vertex()
    provider = VertexProvider(
        "gemini-1.5-flash",
        project_id="test-project",
        region="us-central1",
        access_token_env="VERTEX_ACCESS_TOKEN",
        cost_ceiling_usd=100.0,
    )
    await _record_then_replay_and_assert_determinism(
        tmp_path, "vertex", provider, "gemini-1.5-flash"
    )


@respx.mock
async def test_custom_endpoint_replay_determinism(tmp_path: Path) -> None:
    base_url = "https://llm-gateway.internal.example.com/v1"
    _mock_openai_compatible(base_url)
    provider = CustomEndpointProvider("internal-llama-70b", base_url)
    await _record_then_replay_and_assert_determinism(
        tmp_path, "custom_endpoint", provider, "internal-llama-70b"
    )


# ── CassetteProvider.model_name / is_recording ────────────────────────────────


def test_record_mode_model_name_delegates_to_wrapped_provider() -> None:
    cassette = Cassette(Path("unused.json"))
    provider = OllamaProvider(model="llama3.2")
    wrapped = CassetteProvider(cassette, "ollama", provider=provider)
    assert wrapped.model_name == "llama3.2"
    assert wrapped.is_recording is True


def test_replay_mode_model_name_uses_explicit_model() -> None:
    cassette = Cassette(Path("unused.json"))
    wrapped = CassetteProvider(cassette, "ollama", model="llama3.2")
    assert wrapped.model_name == "llama3.2"
    assert wrapped.is_recording is False
