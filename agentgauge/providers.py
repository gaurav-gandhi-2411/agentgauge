from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from urllib.parse import quote

import httpx


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str


@runtime_checkable
class Provider(Protocol):
    """Model-agnostic LLM provider interface."""

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str: ...

    @property
    def model_name(self) -> str: ...


class OllamaProvider:
    """Calls a local Ollama instance. Default for local dev."""

    BASE_URL = "http://localhost:11434"

    def __init__(self, model: str = "llama3.2", *, timeout: float = 180.0) -> None:
        self._model = model
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"seed": seed},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self.BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


class MockProvider:
    """Deterministic mock for tests — returns preset responses in round-robin."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = responses or ["7"]
        self._idx = 0

    @property
    def model_name(self) -> str:
        return "mock"

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        response = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        return response


class CostCeilingError(RuntimeError):
    """Raised when accumulated API spend reaches the pre-registered ceiling."""


# Anthropic pricing constants (USD per million tokens, 2026-06-12).
# Add new model IDs here when pricing changes; unknown models fall back to sonnet rates.
_INPUT_COST_PER_M: dict[str, float] = {
    "claude-sonnet-4-6": 3.0,
    "claude-haiku-4-5-20251001": 0.80,
    "claude-opus-4-8": 15.0,
}
_OUTPUT_COST_PER_M: dict[str, float] = {
    "claude-sonnet-4-6": 15.0,
    "claude-haiku-4-5-20251001": 4.0,
    "claude-opus-4-8": 75.0,
}
_FALLBACK_INPUT_COST_PER_M: float = 3.0
_FALLBACK_OUTPUT_COST_PER_M: float = 15.0


class ApiAgentProvider:
    """Calls the Anthropic Messages API. Key from an explicitly-passed env var only.

    GG's standing rule: never wire ANTHROPIC_API_KEY (Max-plan double-billing).
    Pass api_key_env='FRONTIER_API_KEY' (or another separately-billed var).
    Tracks token spend and raises CostCeilingError when cost_ceiling_usd is hit.
    """

    _ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
    _ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        model: str,
        api_key_env: str,
        *,
        cost_ceiling_usd: float = 5.0,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        if api_key_env == "ANTHROPIC_API_KEY":
            raise ValueError(
                "api_key_env='ANTHROPIC_API_KEY' is forbidden — use a separately-billed key "
                "env var (e.g. 'FRONTIER_API_KEY') to avoid double-billing on the Max plan."
            )
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ValueError(
                f"API key env var '{api_key_env}' is not set or empty. "
                "Confirm a separately-billed key + spend cap before running."
            )
        self._api_key = api_key
        self._model = model
        self._cost_ceiling_usd = cost_ceiling_usd
        self._timeout = timeout
        self._max_retries = max_retries
        self._tokens_in: int = 0
        self._tokens_out: int = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def tokens_in(self) -> int:
        return self._tokens_in

    @property
    def tokens_out(self) -> int:
        return self._tokens_out

    @property
    def total_cost_usd(self) -> float:
        in_rate = _INPUT_COST_PER_M.get(self._model, _FALLBACK_INPUT_COST_PER_M)
        out_rate = _OUTPUT_COST_PER_M.get(self._model, _FALLBACK_OUTPUT_COST_PER_M)
        return self._tokens_in * in_rate / 1_000_000 + self._tokens_out * out_rate / 1_000_000

    async def chat(
        self,
        messages: list[Message],
        *,
        seed: int = 42,  # noqa: ARG002 — API is non-deterministic; seed accepted but ignored
    ) -> str:
        if self.total_cost_usd >= self._cost_ceiling_usd:
            raise CostCeilingError(
                f"Cost ceiling ${self._cost_ceiling_usd:.4f} reached "
                f"(spent ${self.total_cost_usd:.6f}). Aborting to protect spend cap."
            )

        system_parts = [m.content for m in messages if m.role == "system"]
        user_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        payload: dict = {
            "model": self._model,
            "max_tokens": 256,
            "messages": user_msgs,
        }
        if system_parts:
            payload["system"] = system_parts[-1]

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        self._ANTHROPIC_URL,
                        headers={
                            "x-api-key": self._api_key,
                            "anthropic-version": self._ANTHROPIC_VERSION,
                            "content-type": "application/json",
                        },
                        json=payload,
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep(2**attempt)
                        last_exc = httpx.HTTPStatusError(
                            f"Rate limit on attempt {attempt + 1}",
                            request=resp.request,
                            response=resp,
                        )
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    usage = data.get("usage", {})
                    self._tokens_in += usage.get("input_tokens", 0)
                    self._tokens_out += usage.get("output_tokens", 0)
                    if self.total_cost_usd > self._cost_ceiling_usd:
                        raise CostCeilingError(
                            f"Cost ceiling ${self._cost_ceiling_usd:.4f} exceeded after call "
                            f"(total ${self.total_cost_usd:.6f})."
                        )
                    return data["content"][0]["text"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_exc = exc
                    continue
                raise
        raise last_exc or RuntimeError("All retries exhausted with no response.")


class OpenAICompatibleProvider:
    """Calls any OpenAI-compatible chat-completions endpoint.

    Works for OpenRouter, Together AI, Groq, local vLLM/llama.cpp servers, and
    Ollama's /v1 shim. Key from an explicitly-passed env var (or None for keyless
    local servers). Tracks token spend; raises CostCeilingError when ceiling is hit.

    GG's standing rule: api_key_env must not be 'ANTHROPIC_API_KEY'.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key_env: str | None = None,
        *,
        cost_ceiling_usd: float = float("inf"),
        timeout: float = 180.0,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if api_key_env == "ANTHROPIC_API_KEY":
            raise ValueError(
                "api_key_env='ANTHROPIC_API_KEY' is forbidden — use a non-Anthropic key var "
                "(e.g. 'OPENROUTER_API_KEY') to avoid double-billing on the Max plan."
            )
        api_key: str | None = None
        if api_key_env:
            api_key = os.environ.get(api_key_env)
            if not api_key:
                raise ValueError(f"API key env var '{api_key_env}' is not set or empty.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._cost_ceiling_usd = cost_ceiling_usd
        self._timeout = timeout
        self._max_retries = max_retries
        self._extra_headers = extra_headers or {}
        self._tokens_in: int = 0
        self._tokens_out: int = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def tokens_in(self) -> int:
        return self._tokens_in

    @property
    def tokens_out(self) -> int:
        return self._tokens_out

    @property
    def total_cost_usd(self) -> float:
        return (
            self._tokens_in * _FALLBACK_INPUT_COST_PER_M / 1_000_000
            + self._tokens_out * _FALLBACK_OUTPUT_COST_PER_M / 1_000_000
        )

    async def chat(
        self,
        messages: list[Message],
        *,
        seed: int = 42,  # noqa: ARG002 — most endpoints ignore seed
    ) -> str:
        if self.total_cost_usd >= self._cost_ceiling_usd:
            raise CostCeilingError(
                f"Cost ceiling ${self._cost_ceiling_usd:.4f} reached "
                f"(spent ${self.total_cost_usd:.6f}). Aborting to protect spend cap."
            )

        headers: dict[str, str] = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers)

        payload: dict = {
            "model": self._model,
            "max_tokens": 256,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep(2**attempt)
                        last_exc = httpx.HTTPStatusError(
                            f"Rate limit on attempt {attempt + 1}",
                            request=resp.request,
                            response=resp,
                        )
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    usage = data.get("usage", {})
                    self._tokens_in += usage.get("prompt_tokens", 0)
                    self._tokens_out += usage.get("completion_tokens", 0)
                    if self.total_cost_usd > self._cost_ceiling_usd:
                        raise CostCeilingError(
                            f"Cost ceiling ${self._cost_ceiling_usd:.4f} exceeded after call "
                            f"(total ${self.total_cost_usd:.6f})."
                        )
                    return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_exc = exc
                    continue
                raise
        raise last_exc or RuntimeError("All retries exhausted with no response.")


# ── AWS SigV4 signing (Bedrock) ───────────────────────────────────────────────
#
# Implemented locally rather than depending on boto3/botocore. Rationale (spec-
# agentgauge-v0.5.md S4.1 explicitly leaves this a judgment call): SigV4 for a single
# POST endpoint with no query string is a small, fully-documented algorithm (AWS's own
# spec, unchanged in years); botocore's only advantage here would be its *default
# credential chain* (env vars -> shared config file -> instance metadata), which this
# project's provider conventions explicitly reject in favor of one explicit env var per
# secret (see ApiAgentProvider's api_key_env pattern) -- so the one thing botocore is
# good at is the one thing we don't want. Self-signing keeps this adapter dependency-free
# and fully unit-testable with respx (no real AWS credentials or network needed).


def _sha256_hex(data: bytes) -> str:
    """Hex-encoded SHA-256 digest, used for SigV4's payload hash and canonical-request
    hash steps."""
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    """One HMAC-SHA256 step of the SigV4 key-derivation chain."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sigv4_signing_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    """Derive the SigV4 signing key via the documented 4-step HMAC chain
    (AWS4<secret> -> date -> region -> service -> 'aws4_request')."""
    k_date = _hmac_sha256(f"AWS4{secret_key}".encode(), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


def _sign_bedrock_request(
    *,
    access_key: str,
    secret_key: str,
    region: str,
    host: str,
    canonical_uri: str,
    payload: bytes,
    amz_date: str,
    date_stamp: str,
) -> dict[str, str]:
    """Build SigV4-signed headers for a `POST` to Bedrock Runtime's invoke-model
    endpoint (no query string, one fixed set of signed headers).

    Returns the full header dict (content-type, host, x-amz-content-sha256,
    x-amz-date, authorization) ready to pass to `httpx`.
    """
    service = "bedrock"
    payload_hash = _sha256_hex(payload)
    canonical_headers = (
        f"content-type:application/json\nhost:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    )
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        ["POST", canonical_uri, "", canonical_headers, signed_headers, payload_hash]
    )
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )
    signing_key = _sigv4_signing_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "content-type": "application/json",
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "authorization": authorization,
    }


# Bedrock (Anthropic-on-Bedrock) pricing constants, USD per million tokens. NOT
# independently verified this session (no network access) -- modeled on Bedrock's
# published on-demand rates for the equivalent direct-Anthropic models; confirm against
# https://aws.amazon.com/bedrock/pricing/ before using for a real spend decision.
_BEDROCK_INPUT_COST_PER_M: dict[str, float] = {
    "anthropic.claude-3-5-sonnet-20241022-v2:0": 3.0,
    "anthropic.claude-3-haiku-20240307-v1:0": 0.25,
}
_BEDROCK_OUTPUT_COST_PER_M: dict[str, float] = {
    "anthropic.claude-3-5-sonnet-20241022-v2:0": 15.0,
    "anthropic.claude-3-haiku-20240307-v1:0": 1.25,
}
_BEDROCK_FALLBACK_INPUT_COST_PER_M: float = 3.0
_BEDROCK_FALLBACK_OUTPUT_COST_PER_M: float = 15.0


class BedrockProvider:
    """Calls AWS Bedrock Runtime's `invoke-model` endpoint for an Anthropic-on-Bedrock
    model (e.g. `anthropic.claude-3-5-sonnet-20241022-v2:0`).

    Credentials come from two explicitly-named env vars (never an ambient default
    credential chain -- see the module-level SigV4 docstring above for why boto3/
    botocore are not used here). GG's standing rule applies to every key-env parameter,
    not just Anthropic's: neither env var name may be 'ANTHROPIC_API_KEY'.
    """

    def __init__(
        self,
        model: str,
        *,
        region: str = "us-east-1",
        aws_access_key_id_env: str = "AWS_ACCESS_KEY_ID",
        aws_secret_access_key_env: str = "AWS_SECRET_ACCESS_KEY",
        cost_ceiling_usd: float = 5.0,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        if (
            aws_access_key_id_env == "ANTHROPIC_API_KEY"
            or aws_secret_access_key_env == "ANTHROPIC_API_KEY"
        ):
            raise ValueError(
                "'ANTHROPIC_API_KEY' is forbidden for any credential env var (Max-plan "
                "double-billing) -- use e.g. 'AWS_ACCESS_KEY_ID'/'AWS_SECRET_ACCESS_KEY'."
            )
        access_key = os.environ.get(aws_access_key_id_env)
        secret_key = os.environ.get(aws_secret_access_key_env)
        if not access_key or not secret_key:
            raise ValueError(
                f"AWS credential env vars '{aws_access_key_id_env}'/'{aws_secret_access_key_env}' "
                "are not both set. Confirm a separately-billed IAM principal + spend cap first."
            )
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._model = model
        self._host = f"bedrock-runtime.{region}.amazonaws.com"
        self._path = quote(f"/model/{model}/invoke", safe="/")
        self._url = f"https://{self._host}{self._path}"
        self._cost_ceiling_usd = cost_ceiling_usd
        self._timeout = timeout
        self._max_retries = max_retries
        self._tokens_in: int = 0
        self._tokens_out: int = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def tokens_in(self) -> int:
        return self._tokens_in

    @property
    def tokens_out(self) -> int:
        return self._tokens_out

    @property
    def total_cost_usd(self) -> float:
        in_rate = _BEDROCK_INPUT_COST_PER_M.get(self._model, _BEDROCK_FALLBACK_INPUT_COST_PER_M)
        out_rate = _BEDROCK_OUTPUT_COST_PER_M.get(self._model, _BEDROCK_FALLBACK_OUTPUT_COST_PER_M)
        return self._tokens_in * in_rate / 1_000_000 + self._tokens_out * out_rate / 1_000_000

    async def chat(
        self,
        messages: list[Message],
        *,
        seed: int = 42,  # noqa: ARG002 -- Bedrock/Anthropic is non-deterministic; accepted, ignored
    ) -> str:
        if self.total_cost_usd >= self._cost_ceiling_usd:
            raise CostCeilingError(
                f"Cost ceiling ${self._cost_ceiling_usd:.4f} reached "
                f"(spent ${self.total_cost_usd:.6f}). Aborting to protect spend cap."
            )

        system_parts = [m.content for m in messages if m.role == "system"]
        user_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]

        body: dict = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "messages": user_msgs,
        }
        if system_parts:
            body["system"] = system_parts[-1]
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            now = datetime.now(UTC)
            headers = _sign_bedrock_request(
                access_key=self._access_key,
                secret_key=self._secret_key,
                region=self._region,
                host=self._host,
                canonical_uri=self._path,
                payload=payload,
                amz_date=now.strftime("%Y%m%dT%H%M%SZ"),
                date_stamp=now.strftime("%Y%m%d"),
            )
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(self._url, headers=headers, content=payload)
                    if resp.status_code == 429:
                        await asyncio.sleep(2**attempt)
                        last_exc = httpx.HTTPStatusError(
                            f"Rate limit on attempt {attempt + 1}",
                            request=resp.request,
                            response=resp,
                        )
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    usage = data.get("usage", {})
                    self._tokens_in += usage.get("input_tokens", 0)
                    self._tokens_out += usage.get("output_tokens", 0)
                    if self.total_cost_usd > self._cost_ceiling_usd:
                        raise CostCeilingError(
                            f"Cost ceiling ${self._cost_ceiling_usd:.4f} exceeded after call "
                            f"(total ${self.total_cost_usd:.6f})."
                        )
                    return data["content"][0]["text"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_exc = exc
                    continue
                raise
        raise last_exc or RuntimeError("All retries exhausted with no response.")


# Vertex/Gemini pricing constants, USD per million tokens. NOT independently verified
# this session (no network access) -- modeled on Vertex's published Gemini tiers;
# confirm against https://cloud.google.com/vertex-ai/generative-ai/pricing before using
# for a real spend decision.
_VERTEX_INPUT_COST_PER_M: dict[str, float] = {
    "gemini-1.5-pro": 1.25,
    "gemini-1.5-flash": 0.075,
}
_VERTEX_OUTPUT_COST_PER_M: dict[str, float] = {
    "gemini-1.5-pro": 5.0,
    "gemini-1.5-flash": 0.30,
}
_VERTEX_FALLBACK_INPUT_COST_PER_M: float = 1.25
_VERTEX_FALLBACK_OUTPUT_COST_PER_M: float = 5.0


class VertexProvider:
    """Calls Google Vertex AI's `generateContent` REST endpoint for a Gemini model.

    Scope limitation (deliberate, per spec-agentgauge-v0.5.md S4.1): this adapter takes
    a pre-obtained OAuth2 bearer access token via an explicit env var, not `google-auth`/
    Application Default Credentials. Token refresh and the ADC discovery flow are
    NOT MEASURED and NOT implemented this wave -- only the wire-format call given an
    already-valid token, which is all the cassette determinism proof needs (a mocked
    wire response, never live auth). Obtain a token yourself (e.g. `gcloud auth
    print-access-token`) and export it into the configured env var before using this
    adapter for a real (non-replay) run.
    """

    def __init__(
        self,
        model: str,
        *,
        project_id: str,
        region: str = "us-central1",
        access_token_env: str = "VERTEX_ACCESS_TOKEN",
        cost_ceiling_usd: float = 5.0,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        if access_token_env == "ANTHROPIC_API_KEY":
            raise ValueError(
                "access_token_env='ANTHROPIC_API_KEY' is forbidden -- use a non-Anthropic "
                "env var (e.g. 'VERTEX_ACCESS_TOKEN')."
            )
        access_token = os.environ.get(access_token_env)
        if not access_token:
            raise ValueError(
                f"Access token env var '{access_token_env}' is not set or empty. "
                "Obtain a bearer token (e.g. `gcloud auth print-access-token`) first "
                "-- this adapter does not perform its own OAuth2/ADC flow (scope-limited "
                "this wave; see class docstring)."
            )
        self._access_token = access_token
        self._model = model
        self._project_id = project_id
        self._region = region
        self._url = (
            f"https://{region}-aiplatform.googleapis.com/v1/projects/{project_id}"
            f"/locations/{region}/publishers/google/models/{model}:generateContent"
        )
        self._cost_ceiling_usd = cost_ceiling_usd
        self._timeout = timeout
        self._max_retries = max_retries
        self._tokens_in: int = 0
        self._tokens_out: int = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def tokens_in(self) -> int:
        return self._tokens_in

    @property
    def tokens_out(self) -> int:
        return self._tokens_out

    @property
    def total_cost_usd(self) -> float:
        in_rate = _VERTEX_INPUT_COST_PER_M.get(self._model, _VERTEX_FALLBACK_INPUT_COST_PER_M)
        out_rate = _VERTEX_OUTPUT_COST_PER_M.get(self._model, _VERTEX_FALLBACK_OUTPUT_COST_PER_M)
        return self._tokens_in * in_rate / 1_000_000 + self._tokens_out * out_rate / 1_000_000

    async def chat(
        self,
        messages: list[Message],
        *,
        seed: int = 42,  # noqa: ARG002 -- Gemini's REST API has no request-level seed param
    ) -> str:
        if self.total_cost_usd >= self._cost_ceiling_usd:
            raise CostCeilingError(
                f"Cost ceiling ${self._cost_ceiling_usd:.4f} reached "
                f"(spent ${self.total_cost_usd:.6f}). Aborting to protect spend cap."
            )

        system_parts = [m.content for m in messages if m.role == "system"]
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages
            if m.role != "system"
        ]

        payload: dict = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": system_parts[-1]}]}

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self._access_token}",
        }

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(self._url, headers=headers, json=payload)
                    if resp.status_code == 429:
                        await asyncio.sleep(2**attempt)
                        last_exc = httpx.HTTPStatusError(
                            f"Rate limit on attempt {attempt + 1}",
                            request=resp.request,
                            response=resp,
                        )
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    usage = data.get("usageMetadata", {})
                    self._tokens_in += usage.get("promptTokenCount", 0)
                    self._tokens_out += usage.get("candidatesTokenCount", 0)
                    if self.total_cost_usd > self._cost_ceiling_usd:
                        raise CostCeilingError(
                            f"Cost ceiling ${self._cost_ceiling_usd:.4f} exceeded after call "
                            f"(total ${self.total_cost_usd:.6f})."
                        )
                    candidate = data["candidates"][0]
                    return "".join(part.get("text", "") for part in candidate["content"]["parts"])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_exc = exc
                    continue
                raise
        raise last_exc or RuntimeError("All retries exhausted with no response.")


class CustomEndpointProvider:
    """Generic "internal enterprise serving" adapter: a base URL + a single
    configurable auth header, OpenAI-chat-completions-compatible request/response shape
    by default -- the shape most internal enterprise LLM gateways mimic (spec-
    agentgauge-v0.5.md S4.1: "don't over-engineer a generic JSONPath mapper if a
    sensible default shape covers the real case").

    The auth header's *name* and *value prefix* are configurable (e.g. a bare API-key
    header like `X-API-Key: <value>`, or the default `Authorization: Bearer <value>`),
    but the request/response JSON shape itself is fixed to OpenAI's, matching
    `OpenAICompatibleProvider`. Cost is tracked via the same flat fallback rate
    `OpenAICompatibleProvider` uses for unknown models -- an internal gateway's actual
    per-token price is org-specific and not knowable from the wire response alone.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        *,
        auth_header_name: str = "Authorization",
        auth_header_value_env: str | None = None,
        auth_header_prefix: str = "Bearer ",
        cost_ceiling_usd: float = float("inf"),
        timeout: float = 180.0,
        max_retries: int = 3,
    ) -> None:
        if auth_header_value_env == "ANTHROPIC_API_KEY":
            raise ValueError(
                "auth_header_value_env='ANTHROPIC_API_KEY' is forbidden -- use a non-Anthropic "
                "key var (e.g. 'INTERNAL_GATEWAY_TOKEN')."
            )
        auth_value: str | None = None
        if auth_header_value_env:
            auth_value = os.environ.get(auth_header_value_env)
            if not auth_value:
                raise ValueError(
                    f"Auth header env var '{auth_header_value_env}' is not set or empty."
                )
        self._auth_header_name = auth_header_name
        self._auth_header_value = f"{auth_header_prefix}{auth_value}" if auth_value else None
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._cost_ceiling_usd = cost_ceiling_usd
        self._timeout = timeout
        self._max_retries = max_retries
        self._tokens_in: int = 0
        self._tokens_out: int = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def tokens_in(self) -> int:
        return self._tokens_in

    @property
    def tokens_out(self) -> int:
        return self._tokens_out

    @property
    def total_cost_usd(self) -> float:
        return (
            self._tokens_in * _FALLBACK_INPUT_COST_PER_M / 1_000_000
            + self._tokens_out * _FALLBACK_OUTPUT_COST_PER_M / 1_000_000
        )

    async def chat(
        self,
        messages: list[Message],
        *,
        seed: int = 42,  # noqa: ARG002 -- most internal gateways ignore seed
    ) -> str:
        if self.total_cost_usd >= self._cost_ceiling_usd:
            raise CostCeilingError(
                f"Cost ceiling ${self._cost_ceiling_usd:.4f} reached "
                f"(spent ${self.total_cost_usd:.6f}). Aborting to protect spend cap."
            )

        headers: dict[str, str] = {"content-type": "application/json"}
        if self._auth_header_value:
            headers[self._auth_header_name] = self._auth_header_value

        payload: dict = {
            "model": self._model,
            "max_tokens": 256,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    if resp.status_code == 429:
                        await asyncio.sleep(2**attempt)
                        last_exc = httpx.HTTPStatusError(
                            f"Rate limit on attempt {attempt + 1}",
                            request=resp.request,
                            response=resp,
                        )
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    usage = data.get("usage", {})
                    self._tokens_in += usage.get("prompt_tokens", 0)
                    self._tokens_out += usage.get("completion_tokens", 0)
                    if self.total_cost_usd > self._cost_ceiling_usd:
                        raise CostCeilingError(
                            f"Cost ceiling ${self._cost_ceiling_usd:.4f} exceeded after call "
                            f"(total ${self.total_cost_usd:.6f})."
                        )
                    return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_exc = exc
                    continue
                raise
        raise last_exc or RuntimeError("All retries exhausted with no response.")
