from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from urllib.parse import quote

import httpx

_log = logging.getLogger(__name__)


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


class OllamaTruncationError(RuntimeError):
    """Raised when Ollama evaluated a prompt that filled (or overflowed) the context window.

    Ollama silently drops the oldest tokens when a prompt does not fit in `num_ctx`; the
    model then answers from a truncated catalog with no error. This makes that loud.
    """


# Prompt-size estimator used to size `options.num_ctx` before the call.
# tokens = _TEMPLATE_OVERHEAD + sum over messages of
#          (_PER_MESSAGE_OVERHEAD + ceil(utf-8 bytes of role+content / _BYTES_PER_TOKEN)).
# Bytes (not characters) so CJK / emoji are over- not under-counted. 3.0 is deliberately
# below the measured bytes/token of the audited corpus on llama3.1:8b (see
# docs/evidence/ollama_numctx_impact_audit.json, "estimator_validation") so the estimate
# is an upper bound on the real count there.
_BYTES_PER_TOKEN: float = 3.0
_PER_MESSAGE_OVERHEAD_TOKENS: int = 8
_TEMPLATE_OVERHEAD_TOKENS: int = 32
NUM_CTX_FLOOR: int = 4096
NUM_CTX_HEADROOM: int = 1024  # room for the completion + estimator error
# A correctly sized num_ctx leaves >= NUM_CTX_HEADROOM tokens spare, so an evaluated prompt
# within this many tokens of num_ctx means the window was filled, i.e. truncation.
TRUNCATION_MARGIN: int = 64


def estimate_prompt_tokens(messages: list[Message]) -> int:
    """Conservative (over-)estimate of the tokens Ollama will evaluate for `messages`."""
    total = _TEMPLATE_OVERHEAD_TOKENS
    for m in messages:
        n_bytes = len(m.role.encode("utf-8")) + len(m.content.encode("utf-8"))
        total += _PER_MESSAGE_OVERHEAD_TOKENS + math.ceil(n_bytes / _BYTES_PER_TOKEN)
    return total


def compute_num_ctx(messages: list[Message]) -> int:
    """`max(4096, estimated_prompt_tokens + 1024)`, rounded up to a power of two.

    Rounding is a deliberate deviation from the bare formula: Ollama reloads the model
    runner whenever `num_ctx` changes between requests, so an exact per-prompt value would
    reload on nearly every call. Power-of-two buckets keep reloads rare and never go below
    the formula.
    """
    needed = max(NUM_CTX_FLOOR, estimate_prompt_tokens(messages) + NUM_CTX_HEADROOM)
    return 1 << (needed - 1).bit_length()


# Lower-bound token estimate (used only for the context-shift signature below). The measured
# maximum bytes/token over 316 corpus prompts on llama3.1:8b was 5.50, so 6.0 gives
# L <= true token count; per-message overhead is kept below the real template cost.
_LOWER_BOUND_BYTES_PER_TOKEN: float = 6.0
_LOWER_BOUND_PER_MESSAGE_TOKENS: int = 4
_SHIFT_BELOW_FRACTION: float = 0.9  # count must be under 0.9 * L to look truncated
_SHIFT_SLACK_FRACTION: float = 0.03  # +-3% of num_ctx // 2 ...
_SHIFT_MIN_SLACK: int = 8  # ... but never less than 8 tokens


def lower_bound_prompt_tokens(messages: list[Message]) -> int:
    """Under-estimate of the tokens Ollama will evaluate for `messages` (L <= true count)."""
    total = 0
    for m in messages:
        n_bytes = len(m.role.encode("utf-8")) + len(m.content.encode("utf-8"))
        total += _LOWER_BOUND_PER_MESSAGE_TOKENS + math.ceil(n_bytes / _LOWER_BOUND_BYTES_PER_TOKEN)
    return total


def check_truncation(
    prompt_eval_count: int | None,
    num_ctx: int,
    model: str,
    lower_bound_tokens: int | None = None,
) -> None:
    """Raise OllamaTruncationError if `prompt_eval_count` shows the prompt was truncated.

    Two signatures, because truncation reporting is version-dependent:

    1. Window filled: `prompt_eval_count >= num_ctx - 64` (the naive expectation). Always
       checked.
    2. Context shift: MEASURED on Ollama 0.40.3 / llama3.1:8b, a truncated prompt reports
       about num_ctx/2 + 2 (context shift keeps half the window), NOT num_ctx -- e.g. the
       5307-token google_workspace selection prompt reported 2050 at num_ctx=4096 (3 runs),
       1502 at 3000, 1026 at 2048, and 5325 (no truncation) at 8192. Checked only when
       `lower_bound_tokens` (L, a guaranteed under-estimate) is given: raise when the count
       is < 0.9*L AND within max(8, 3%) tokens of num_ctx//2, or within 64 of num_ctx.
       Other Ollama versions may behave differently, hence both signatures.

    A count below L that is NOWHERE near num_ctx/2 is NOT treated as truncation: KV-cache
    prefix reuse reports only the newly evaluated tokens, so a cached prefix legitimately
    lowers the count. A missing count (None) is not checkable and passes.
    """
    if prompt_eval_count is None:
        return
    shifted = False
    if lower_bound_tokens is not None and prompt_eval_count < _SHIFT_BELOW_FRACTION * (
        lower_bound_tokens
    ):
        half = num_ctx // 2
        slack = max(_SHIFT_MIN_SLACK, math.ceil(_SHIFT_SLACK_FRACTION * half))
        shifted = abs(prompt_eval_count - half) <= slack
    if shifted or prompt_eval_count >= num_ctx - TRUNCATION_MARGIN:
        raise OllamaTruncationError(
            f"Ollama model '{model}' evaluated {prompt_eval_count} prompt tokens with "
            f"num_ctx={num_ctx}: the prompt did not fit the context window and was "
            "truncated, so the model did not see the whole catalog. Raise num_ctx (the "
            "token estimator may be too low for this text) or shorten the tool catalog."
        )


class OllamaProvider:
    """Calls a local Ollama instance. Default for local dev.

    Decoding: sends `options.seed` and `options.num_ctx`; temperature/top_p/top_k are NOT
    set, so the model's Modelfile / Ollama's runtime defaults apply (Ollama's documented
    default temperature is 0.8 -- sampling is on). Seed support: honoured (same seed + same
    prompt + same model build -> same completion). `runner.run_tasks` passes a distinct seed
    per trial.

    Context window: Ollama silently truncates prompts longer than `num_ctx`, so every call
    sets `num_ctx` from `compute_num_ctx` (>= 4096, sized to the prompt) and afterwards
    raises `OllamaTruncationError` if `prompt_eval_count` shows truncation (window filled, or
    the context-shift signature of about num_ctx/2 measured on Ollama 0.40.3).

    Ollama also clamps `num_ctx` to the model's maximum context (gemma2:9b: 8192), so the
    model's `context_length` is read once from `/api/show`: the requested `num_ctx` is
    clamped to it, the call fails up front when the estimated prompt plus headroom cannot
    fit, and the truncation check uses the EFFECTIVE window. If `/api/show` is unavailable
    the previous (unclamped) behaviour applies, with one warning.
    """

    BASE_URL = "http://localhost:11434"

    def __init__(self, model: str = "llama3.2", *, timeout: float = 180.0) -> None:
        self._model = model
        self._timeout = timeout
        self._max_ctx: int | None = None
        self._max_ctx_probed = False

    @property
    def model_name(self) -> str:
        return self._model

    async def _model_max_ctx(self, client: httpx.AsyncClient) -> int | None:
        """Model's maximum context length from `/api/show` (cached; None if unavailable)."""
        if self._max_ctx_probed:
            return self._max_ctx
        self._max_ctx_probed = True
        try:
            resp = await client.post(f"{self.BASE_URL}/api/show", json={"model": self._model})
            resp.raise_for_status()
            info = resp.json().get("model_info") or {}
            values = [
                v
                for k, v in info.items()
                if k.endswith(".context_length") and isinstance(v, int) and v > 0
            ]
            self._max_ctx = values[0] if values else None
        except Exception:  # best-effort probe; must never break the chat call
            self._max_ctx = None
        if self._max_ctx is None:
            _log.warning(
                "Ollama /api/show gave no context_length for %s; num_ctx is not clamped to "
                "the model maximum and truncation is checked against the requested num_ctx.",
                self._model,
            )
        return self._max_ctx

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        num_ctx = compute_num_ctx(messages)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            max_ctx = await self._model_max_ctx(client)
            if max_ctx is not None:
                est = estimate_prompt_tokens(messages)
                if est + NUM_CTX_HEADROOM > max_ctx:
                    raise OllamaTruncationError(
                        f"Ollama model '{self._model}' has a maximum context of {max_ctx} "
                        f"tokens, but this prompt is estimated at {est} tokens plus "
                        f"{NUM_CTX_HEADROOM} tokens of headroom, so it cannot fit and would "
                        "be silently truncated. Shorten the tool catalog or use a model with "
                        "a larger context window."
                    )
                num_ctx = min(num_ctx, max_ctx)
            payload = {
                "model": self._model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "options": {"seed": seed, "num_ctx": num_ctx},
            }
            resp = await client.post(f"{self.BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            body = resp.json()
        check_truncation(
            body.get("prompt_eval_count"),
            num_ctx,
            self._model,
            lower_bound_prompt_tokens(messages),
        )
        return body["message"]["content"]


class MockProvider:
    """Deterministic mock for tests — returns preset responses in round-robin.

    Seed support: accepted and ignored (output depends only on call order).
    """

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

    Decoding: temperature/top_p are NOT sent (API defaults apply). Seed support: none --
    the Messages API has no seed parameter; `seed` is accepted and ignored, so trials are
    independently sampled but not replayable except via a recorded cassette.
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

    Decoding: temperature/top_p are NOT sent (endpoint defaults apply). Seed support: none
    -- `seed` is accepted and ignored (most endpoints do not honour it); replay requires a
    recorded cassette.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key_env: str | None = None,
        *,
        cost_ceiling_usd: float = 5.0,
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

    Decoding: temperature/top_p are NOT sent (model defaults apply). Seed support: none --
    `seed` is accepted and ignored; replay requires a recorded cassette.
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

    Decoding: temperature/top_p are NOT sent (model defaults apply). Seed support: none --
    the REST call sets no seed; `seed` is accepted and ignored; replay requires a cassette.
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

    Decoding: temperature/top_p are NOT sent (gateway defaults apply). Seed support: none
    -- `seed` is accepted and ignored; replay requires a recorded cassette.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        *,
        auth_header_name: str = "Authorization",
        auth_header_value_env: str | None = None,
        auth_header_prefix: str = "Bearer ",
        cost_ceiling_usd: float = 5.0,
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
