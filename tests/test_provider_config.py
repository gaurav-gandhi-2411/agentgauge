"""Tests for agentgauge.provider_config -- config-driven provider selection
(spec-agentgauge-v0.5.md S4.1: "no code change to switch providers").

Covers the bounded flat-YAML parser (`_parse_flat_yaml`), `ProviderConfig`
validation (including the ANTHROPIC_API_KEY ban across every credential-env
field), and `create_provider`'s dispatch to each of the six adapters. No network
calls anywhere -- adapter construction only, never `.chat()`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentgauge.provider_config import (
    ProviderConfig,
    _parse_flat_yaml,
    create_provider,
    load_provider_config,
)
from agentgauge.providers import (
    ApiAgentProvider,
    BedrockProvider,
    CustomEndpointProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    VertexProvider,
)

_CONFIGS_DIR = Path(__file__).parent.parent / "configs"


# ── _parse_flat_yaml ──────────────────────────────────────────────────────────


def test_parse_flat_yaml_basic_mapping() -> None:
    text = "provider: ollama\nmodel: llama3.1:8b\ntimeout: 180.0\n"
    assert _parse_flat_yaml(text) == {
        "provider": "ollama",
        "model": "llama3.1:8b",
        "timeout": 180.0,
    }


def test_parse_flat_yaml_skips_blank_lines_and_full_line_comments() -> None:
    text = "# a comment\nprovider: ollama\n\nmodel: llama3.2\n"
    assert _parse_flat_yaml(text) == {"provider": "ollama", "model": "llama3.2"}


def test_parse_flat_yaml_strips_trailing_unquoted_comment() -> None:
    text = "region: us-east-1  # AWS region\n"
    assert _parse_flat_yaml(text) == {"region": "us-east-1"}


def test_parse_flat_yaml_quoted_value_preserves_hash_and_trailing_space() -> None:
    text = 'auth_header_prefix: "Bearer "\n'
    assert _parse_flat_yaml(text) == {"auth_header_prefix": "Bearer "}


def test_parse_flat_yaml_quoted_value_with_internal_hash_not_treated_as_comment() -> None:
    text = 'model: "weird#model-name"\n'
    assert _parse_flat_yaml(text) == {"model": "weird#model-name"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("null", None),
        ("~", None),
        ("true", True),
        ("false", False),
        ("42", 42),
        ("3.5", 3.5),
        (".inf", float("inf")),
        ("-.inf", float("-inf")),
    ],
)
def test_parse_flat_yaml_scalar_types(raw: str, expected: object) -> None:
    result = _parse_flat_yaml(f"value: {raw}\n")
    if expected is None:
        assert result["value"] is None
    elif isinstance(expected, float) and expected != expected:  # nan
        assert result["value"] != result["value"]
    else:
        assert result["value"] == expected


def test_parse_flat_yaml_missing_colon_raises_with_line_number() -> None:
    with pytest.raises(ValueError, match="line 2"):
        _parse_flat_yaml("provider: ollama\nthis has no colon\n")


def test_parse_flat_yaml_block_sequence_rejected() -> None:
    with pytest.raises(ValueError, match="block sequences"):
        _parse_flat_yaml("items:\n  - one\n  - two\n")


def test_parse_flat_yaml_empty_key_raises() -> None:
    with pytest.raises(ValueError, match="empty key"):
        _parse_flat_yaml(": value\n")


# ── ProviderConfig validation ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "field",
    [
        "api_key_env",
        "aws_access_key_id_env",
        "aws_secret_access_key_env",
        "access_token_env",
        "auth_header_value_env",
    ],
)
def test_provider_config_forbids_anthropic_api_key_in_any_credential_field(field: str) -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        ProviderConfig.model_validate(
            {"provider": "ollama", "model": "x", field: "ANTHROPIC_API_KEY"}
        )


def test_provider_config_rejects_unknown_provider_kind() -> None:
    with pytest.raises(ValueError):
        ProviderConfig.model_validate({"provider": "not_a_real_provider", "model": "x"})


# ── create_provider dispatch ────────────────────────────────────────────────


def test_create_provider_ollama() -> None:
    config = ProviderConfig(provider="ollama", model="llama3.2")
    provider = create_provider(config)
    assert isinstance(provider, OllamaProvider)
    assert provider.model_name == "llama3.2"


def test_create_provider_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTIER_API_KEY", "sk-test")
    config = ProviderConfig(
        provider="anthropic", model="claude-haiku-4-5-20251001", api_key_env="FRONTIER_API_KEY"
    )
    provider = create_provider(config)
    assert isinstance(provider, ApiAgentProvider)


def test_create_provider_anthropic_missing_api_key_env_raises() -> None:
    config = ProviderConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    with pytest.raises(ValueError, match="api_key_env"):
        create_provider(config)


def test_create_provider_openai_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    config = ProviderConfig(
        provider="openai_compatible",
        model="some-model",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    )
    provider = create_provider(config)
    assert isinstance(provider, OpenAICompatibleProvider)


def test_create_provider_openai_compatible_missing_base_url_raises() -> None:
    config = ProviderConfig(provider="openai_compatible", model="some-model")
    with pytest.raises(ValueError, match="base_url"):
        create_provider(config)


def test_create_provider_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secretfake")
    config = ProviderConfig(
        provider="bedrock", model="anthropic.claude-3-5-sonnet-20241022-v2:0", region="us-east-1"
    )
    provider = create_provider(config)
    assert isinstance(provider, BedrockProvider)


def test_create_provider_vertex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERTEX_ACCESS_TOKEN", "ya29.test")
    config = ProviderConfig(provider="vertex", model="gemini-1.5-flash", project_id="my-project")
    provider = create_provider(config)
    assert isinstance(provider, VertexProvider)


def test_create_provider_vertex_missing_project_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERTEX_ACCESS_TOKEN", "ya29.test")
    config = ProviderConfig(provider="vertex", model="gemini-1.5-flash")
    with pytest.raises(ValueError, match="project_id"):
        create_provider(config)


def test_create_provider_custom_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_GATEWAY_TOKEN", "tok-test")
    config = ProviderConfig(
        provider="custom_endpoint",
        model="internal-llama-70b",
        base_url="https://llm-gateway.internal.example.com/v1",
        auth_header_value_env="INTERNAL_GATEWAY_TOKEN",
    )
    provider = create_provider(config)
    assert isinstance(provider, CustomEndpointProvider)


def test_create_provider_custom_endpoint_missing_base_url_raises() -> None:
    config = ProviderConfig(provider="custom_endpoint", model="internal-llama-70b")
    with pytest.raises(ValueError, match="base_url"):
        create_provider(config)


# ── example configs under configs/ round-trip through load + create ─────────


@pytest.mark.parametrize(
    ("filename", "env"),
    [
        ("provider.ollama.yaml", {}),
        ("provider.anthropic.yaml", {"FRONTIER_API_KEY": "sk-test"}),
        (
            "provider.openai_compatible.yaml",
            {"OPENROUTER_API_KEY": "or-test"},
        ),
        (
            "provider.bedrock.yaml",
            {"AWS_ACCESS_KEY_ID": "AKIAFAKE", "AWS_SECRET_ACCESS_KEY": "secretfake"},
        ),
        ("provider.vertex.yaml", {"VERTEX_ACCESS_TOKEN": "ya29.test"}),
        (
            "provider.custom_endpoint.yaml",
            {"INTERNAL_GATEWAY_TOKEN": "tok-test"},
        ),
    ],
)
def test_example_configs_load_and_dispatch(
    filename: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config = load_provider_config(_CONFIGS_DIR / filename)
    provider = create_provider(config)
    assert provider.model_name == config.model
