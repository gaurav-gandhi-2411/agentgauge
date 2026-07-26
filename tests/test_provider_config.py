"""Tests for agentgauge.provider_config -- config-driven provider selection
(spec-agentgauge-v0.5.md S4.1: "no code change to switch providers").

Covers `load_provider_config`'s YAML parsing (now PyYAML's `yaml.safe_load`, v0.5
Wave 1 Task 5b -- see the module docstring for why the earlier hand-rolled
`_parse_flat_yaml` was removed), `ProviderConfig` validation (including the
ANTHROPIC_API_KEY ban across every credential-env field), and `create_provider`'s
dispatch to each of the six adapters. No network calls anywhere -- adapter
construction only, never `.chat()`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from agentgauge.provider_config import ProviderConfig, create_provider, load_provider_config
from agentgauge.providers import (
    ApiAgentProvider,
    BedrockProvider,
    CustomEndpointProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    VertexProvider,
)

_CONFIGS_DIR = Path(__file__).parent.parent / "configs"


# ── load_provider_config: behavior ported forward from the old hand-rolled parser ──
# (rule 79: test behavior, not implementation -- these assert the same end-to-end
# outcomes the pre-PyYAML `_parse_flat_yaml` tests asserted, now through the real
# `load_provider_config` -> ProviderConfig` path rather than a private parser function.)


def _write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "provider.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_provider_config_basic_mapping(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "provider: ollama\nmodel: llama3.1:8b\ntimeout: 180.0\n")
    config = load_provider_config(path)
    assert config.provider == "ollama"
    assert config.model == "llama3.1:8b"
    assert config.timeout == 180.0


def test_load_provider_config_skips_blank_lines_and_full_line_comments(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "# a comment\nprovider: ollama\n\nmodel: llama3.2\n")
    config = load_provider_config(path)
    assert config.provider == "ollama"
    assert config.model == "llama3.2"


def test_load_provider_config_strips_trailing_unquoted_comment(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "provider: bedrock\nmodel: x\nregion: us-east-1  # AWS region\n")
    config = load_provider_config(path)
    assert config.region == "us-east-1"


def test_load_provider_config_quoted_value_preserves_hash_and_trailing_space(
    tmp_path: Path,
) -> None:
    path = _write_config(
        tmp_path,
        'provider: custom_endpoint\nmodel: x\nauth_header_prefix: "Bearer "\n',
    )
    config = load_provider_config(path)
    assert config.auth_header_prefix == "Bearer "


def test_load_provider_config_quoted_value_with_internal_hash_not_treated_as_comment(
    tmp_path: Path,
) -> None:
    path = _write_config(tmp_path, 'provider: ollama\nmodel: "weird#model-name"\n')
    config = load_provider_config(path)
    assert config.model == "weird#model-name"


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
def test_load_provider_config_scalar_types(raw: str, expected: object, tmp_path: Path) -> None:
    path = _write_config(tmp_path, f"provider: ollama\nmodel: x\ncost_ceiling_usd: {raw}\n")
    config = load_provider_config(path)
    if expected is None:
        assert config.cost_ceiling_usd is None
    else:
        assert config.cost_ceiling_usd == expected


def test_load_provider_config_missing_colon_raises(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "provider: ollama\nthis has no colon\n")
    with pytest.raises(yaml.YAMLError):
        load_provider_config(path)


def test_load_provider_config_empty_file_raises_pydantic_missing_field_error(
    tmp_path: Path,
) -> None:
    """An empty/comment-only file parses to `None` via `yaml.safe_load`, normalized to
    `{}` -- `ProviderConfig.model_validate({})` then raises its own missing-required-
    field error (`provider`/`model`), not a raw `AttributeError` on `None`."""
    path = _write_config(tmp_path, "# just a comment\n")
    with pytest.raises(Exception, match="provider"):
        load_provider_config(path)


# ── Real-YAML capabilities the old hand-rolled parser explicitly could NOT support ──
# (v0.5 Wave 1 Task 5b -- the actual point of the PyYAML swap, not just fewer lines.)


class _ListAcceptingModel(BaseModel):
    """Throwaway test-only model with a list field: `ProviderConfig` itself has no
    list-typed field today (its schema is still flat scalars, per the module
    docstring), so this is the most direct way to demonstrate that the PARSING layer
    (`yaml.safe_load`) now genuinely supports YAML block sequences, independent of
    whether any current `ProviderConfig` field happens to use one yet."""

    tags: list[str]


def test_yaml_safe_load_supports_block_sequences_old_parser_rejected() -> None:
    """The old `_parse_flat_yaml` raised `ValueError: block sequences ('- item') are
    not supported...` on this exact input (see the removed
    `test_parse_flat_yaml_block_sequence_rejected` test, pre-Task-5b). `yaml.safe_load`
    parses it into a real Python list; the loaded dict validates cleanly against a
    model with a `list[str]` field."""
    text = "tags:\n  - fast\n  - cheap\n  - local\n"
    raw = yaml.safe_load(text)
    assert raw == {"tags": ["fast", "cheap", "local"]}
    model = _ListAcceptingModel.model_validate(raw)
    assert model.tags == ["fast", "cheap", "local"]


def test_load_provider_config_quoted_special_characters_round_trip(tmp_path: Path) -> None:
    """Colons, `#`, and leading/trailing whitespace inside a quoted scalar are real
    YAML-special characters the old parser handled only via its own bespoke
    `_strip_trailing_comment`/quote-stripping logic; PyYAML handles the full YAML
    quoting grammar (including escapes) natively."""
    path = _write_config(
        tmp_path,
        "provider: custom_endpoint\n"
        "model: x\n"
        'base_url: "https://example.com:8080/v1#fragment"\n'
        'auth_header_prefix: "  Bearer  "\n',
    )
    config = load_provider_config(path)
    assert config.base_url == "https://example.com:8080/v1#fragment"
    assert config.auth_header_prefix == "  Bearer  "


def test_load_provider_config_multiline_block_scalar_parses() -> None:
    """YAML block scalars (`|` literal, preserving newlines) are a construct the old
    hand-rolled parser had no concept of at all -- it parsed strictly one `key: value`
    pair per line. `model` is reused here purely as a convenient string field to prove
    the multi-line VALUE parses correctly; a real config would not normally put a
    block scalar in `model`."""
    text = "provider: ollama\nmodel: |\n  line one\n  line two\n"
    raw = yaml.safe_load(text)
    assert raw["model"] == "line one\nline two\n"
    config = ProviderConfig.model_validate(raw)
    assert config.model == "line one\nline two\n"


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
