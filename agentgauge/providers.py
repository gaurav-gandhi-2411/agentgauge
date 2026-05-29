from __future__ import annotations

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

    def __init__(self, model: str = "llama3.2") -> None:
        self._model = model

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
        async with httpx.AsyncClient(timeout=60.0) as client:
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
