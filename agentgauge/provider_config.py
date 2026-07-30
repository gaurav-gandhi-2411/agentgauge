"""Config-driven provider selection (spec-agentgauge-v0.5.md S4.1: "no code change to
switch providers").

A `ProviderConfig` (pydantic, validated at the boundary per project convention) is
loaded from a YAML file and dispatched to the right `agentgauge.providers` adapter via
`create_provider()`. See `configs/provider.*.yaml` for one worked example per adapter.

**PyYAML (v0.5 Wave 1 Task 5b):** `load_provider_config` parses with
`yaml.safe_load` -- never `yaml.load` without a safe loader, since a config file is an
untrusted-input trust boundary. This project's earlier hand-rolled `_parse_flat_yaml`
(a small bounded parser for exactly `ProviderConfig`'s flat-scalar-mapping subset, kept
to avoid a new dependency) has been removed: real nested mappings and YAML block
sequences (lists) are now genuinely supported by the parsing layer, even though
`ProviderConfig`'s pydantic schema itself is still flat scalars today (a list-typed
field is a schema change, not a parser change, and hasn't been needed yet).
`ProviderConfig`'s pydantic validation remains the boundary-validation layer exactly as
before -- `yaml.safe_load` only needs to hand it a `dict`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

from agentgauge.providers import (
    ApiAgentProvider,
    BedrockProvider,
    CustomEndpointProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    Provider,
    VertexProvider,
)

ProviderKind = Literal[
    "ollama", "anthropic", "openai_compatible", "bedrock", "vertex", "custom_endpoint"
]

_FORBIDDEN_KEY_ENV = "ANTHROPIC_API_KEY"
_CREDENTIAL_ENV_FIELDS = (
    "api_key_env",
    "aws_access_key_id_env",
    "aws_secret_access_key_env",
    "access_token_env",
    "auth_header_value_env",
)


class ProviderConfig(BaseModel):
    """Provider selection + adapter-specific fields, one flat schema for all six
    adapters (unused fields for a given `provider` kind are simply ignored by
    `create_provider`). Validated at the YAML-loading boundary per project convention
    (pydantic for anything crossing a boundary)."""

    provider: ProviderKind
    model: str

    # Shared knobs (subset used depends on `provider`).
    timeout: float = 180.0
    max_retries: int = 3
    cost_ceiling_usd: float | None = None

    # Anthropic / OpenAI-compatible / custom-endpoint.
    api_key_env: str | None = None
    base_url: str | None = None

    # Bedrock.
    region: str | None = None
    aws_access_key_id_env: str | None = None
    aws_secret_access_key_env: str | None = None

    # Vertex.
    project_id: str | None = None
    access_token_env: str | None = None

    # Custom endpoint auth header.
    auth_header_name: str | None = None
    auth_header_value_env: str | None = None
    auth_header_prefix: str | None = None

    @model_validator(mode="after")
    def _forbid_anthropic_api_key_everywhere(self) -> ProviderConfig:
        """Defense in depth: the adapters themselves already raise on
        `ANTHROPIC_API_KEY`, but catching it here gives a config-load-time error
        instead of a construction-time one, and covers every credential-env field
        uniformly regardless of which adapter is selected."""
        for field in _CREDENTIAL_ENV_FIELDS:
            if getattr(self, field) == _FORBIDDEN_KEY_ENV:
                raise ValueError(
                    f"provider config field '{field}' must not be '{_FORBIDDEN_KEY_ENV}' "
                    "(Claude Max double-billing rule -- use a separately-billed env var)."
                )
        return self


def load_provider_config(path: str | Path) -> ProviderConfig:
    """Load and validate a `ProviderConfig` from a YAML file (see `configs/` for
    one worked example per adapter kind).

    `yaml.safe_load` (never `yaml.load` without `Loader=SafeLoader`) -- a config file
    is untrusted input at a trust boundary. An empty or comment-only file parses to
    `None`; that is normalized to `{}` so `ProviderConfig.model_validate` sees a dict
    and raises its own (more informative) missing-required-field error rather than a
    raw `AttributeError`."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ProviderConfig.model_validate(raw)


def create_provider(config: ProviderConfig) -> Provider:
    """Dispatch a validated `ProviderConfig` to the matching `agentgauge.providers`
    adapter. Raises `ValueError` if a required adapter-specific field is missing."""
    if config.provider == "ollama":
        return OllamaProvider(config.model, timeout=config.timeout)

    if config.provider == "anthropic":
        if not config.api_key_env:
            raise ValueError("provider: anthropic requires 'api_key_env'.")
        return ApiAgentProvider(
            config.model,
            api_key_env=config.api_key_env,
            cost_ceiling_usd=config.cost_ceiling_usd
            if config.cost_ceiling_usd is not None
            else 5.0,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    if config.provider == "openai_compatible":
        if not config.base_url:
            raise ValueError("provider: openai_compatible requires 'base_url'.")
        return OpenAICompatibleProvider(
            config.model,
            config.base_url,
            config.api_key_env,
            cost_ceiling_usd=(
                config.cost_ceiling_usd if config.cost_ceiling_usd is not None else float("inf")
            ),
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    if config.provider == "bedrock":
        return BedrockProvider(
            config.model,
            region=config.region or "us-east-1",
            aws_access_key_id_env=config.aws_access_key_id_env or "AWS_ACCESS_KEY_ID",
            aws_secret_access_key_env=config.aws_secret_access_key_env or "AWS_SECRET_ACCESS_KEY",
            cost_ceiling_usd=config.cost_ceiling_usd
            if config.cost_ceiling_usd is not None
            else 5.0,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    if config.provider == "vertex":
        if not config.project_id:
            raise ValueError("provider: vertex requires 'project_id'.")
        return VertexProvider(
            config.model,
            project_id=config.project_id,
            region=config.region or "us-central1",
            access_token_env=config.access_token_env or "VERTEX_ACCESS_TOKEN",
            cost_ceiling_usd=config.cost_ceiling_usd
            if config.cost_ceiling_usd is not None
            else 5.0,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    if config.provider == "custom_endpoint":
        if not config.base_url:
            raise ValueError("provider: custom_endpoint requires 'base_url'.")
        return CustomEndpointProvider(
            config.model,
            config.base_url,
            auth_header_name=config.auth_header_name or "Authorization",
            auth_header_value_env=config.auth_header_value_env,
            auth_header_prefix=(
                config.auth_header_prefix if config.auth_header_prefix is not None else "Bearer "
            ),
            cost_ceiling_usd=(
                config.cost_ceiling_usd if config.cost_ceiling_usd is not None else float("inf")
            ),
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    raise ValueError(
        f"Unknown provider kind: {config.provider!r}"
    )  # pragma: no cover -- Literal-guarded
