from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

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
