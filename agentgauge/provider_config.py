"""Config-driven provider selection (spec-agentgauge-v0.5.md S4.1: "no code change to
switch providers").

A `ProviderConfig` (pydantic, validated at the boundary per project convention) is
loaded from a YAML file and dispatched to the right `agentgauge.providers` adapter via
`create_provider()`. See `configs/provider.*.yaml` for one worked example per adapter.

**Why a hand-rolled flat-YAML parser instead of PyYAML:** this project's standing rule
is "do not install new dependencies without asking." `ProviderConfig`'s schema is a
single, flat mapping of scalar values (str/int/float/None/bool) -- no lists, no nesting
-- so a small bounded parser for exactly that subset avoids the new dependency while
still satisfying "YAML for runtime config, never pyproject.toml." `_parse_flat_yaml`
below is deliberately NOT a general YAML parser (it will raise on anything with nesting
or block sequences); if a future config needs real nesting, that is the trigger to
add PyYAML properly rather than growing this parser. The public API
(`load_provider_config(path) -> ProviderConfig`) is unaffected either way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

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


def _strip_trailing_comment(value_part: str) -> str:
    """Strip a `# comment` suffix from an unquoted scalar value, or return a quoted
    value's contents verbatim (a '#' inside quotes is not a comment)."""
    if value_part.startswith(("'", '"')):
        quote_char = value_part[0]
        end = value_part.find(quote_char, 1)
        if end == -1:
            return value_part.strip()
        return value_part[: end + 1]
    idx = value_part.find("#")
    while idx != -1:
        if idx == 0 or value_part[idx - 1].isspace():
            return value_part[:idx].strip()
        idx = value_part.find("#", idx + 1)
    return value_part.strip()


def _parse_scalar(text: str) -> Any:
    """Parse one YAML-scalar-subset token: quoted string, null, bool, int, float,
    special float tags (`.inf`/`-.inf`/`.nan`), or a bare (unquoted) string."""
    if text == "" or text in ("null", "~", "Null", "NULL"):
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    lowered = text.lower()
    if lowered in (".inf", "inf", "+.inf"):
        return float("inf")
    if lowered in ("-.inf", "-inf"):
        return float("-inf")
    if lowered in (".nan", "nan"):
        return float("nan")
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _parse_flat_yaml(text: str) -> dict[str, Any]:
    """Parse the bounded flat-mapping YAML subset `ProviderConfig` needs: one
    `key: value` pair per non-blank, non-comment line, no nesting, no lists.

    Raises `ValueError` (with the offending line number) on anything outside that
    subset -- fails loudly rather than silently misinterpreting a nested structure.
    """
    result: dict[str, Any] = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") or stripped == "-":
            raise ValueError(
                f"provider config line {lineno}: block sequences ('- item') are not "
                "supported by this project's minimal flat-YAML parser (see "
                "provider_config.py module docstring)."
            )
        if ":" not in raw_line:
            raise ValueError(
                f"provider config line {lineno}: expected 'key: value', got {raw_line!r}"
            )
        key, _, rest = raw_line.partition(":")
        key = key.strip()
        if not key:
            raise ValueError(f"provider config line {lineno}: empty key in {raw_line!r}")
        value_part = _strip_trailing_comment(rest.strip())
        result[key] = _parse_scalar(value_part)
    return result


def load_provider_config(path: str | Path) -> ProviderConfig:
    """Load and validate a `ProviderConfig` from a YAML file (see `configs/` for
    one worked example per adapter kind)."""
    raw = _parse_flat_yaml(Path(path).read_text(encoding="utf-8"))
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
