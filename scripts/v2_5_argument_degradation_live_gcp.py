"""v0.4.0 Task 1: routes scripts/v2_5_argument_degradation_live.py's Ollama calls
to the remote `agentgauge-agent` Cloud Run service instead of local Ollama --
used only because local GPU was contended by an unrelated process (`aetherart`)
for the duration of this measurement, with explicit user sign-off to use GCP.

Deliberately does NOT use `gcloud run services proxy` -- this repo's own memory
records that an unattended local proxy dies within ~2-30 minutes on this machine
(three prior launch mechanisms tried, unsolved), which is fatal for a multi-hour
job. Instead this calls the Cloud Run service's HTTPS URL directly, authenticated
per-request with a `gcloud auth print-identity-token` bearer token (refreshed
every 45 minutes -- tokens last ~1 hour) -- no long-lived local process to die.

MCP servers (the fixtures under test) still run locally via stdio -- only the
LLM provider calls are remote. Only `agentgauge.providers.OllamaProvider` is
monkeypatched (BASE_URL + chat()); no product code is edited.

Prerequisite: `agentgauge-agent` Cloud Run service must already be deployed
(scripts/agentgauge-agent-service.yaml) with gemma2:9b/llama3.1:8b/qwen2.5:7b
baked into its image (scripts/Dockerfile.agentgauge-agent).

Usage:
    python scripts/v2_5_argument_degradation_live_gcp.py
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from agentgauge.providers import Message, OllamaProvider

CLOUD_RUN_URL = "https://agentgauge-agent-6txxpjhu2a-uc.a.run.app"
_TOKEN_REFRESH_INTERVAL_S = 45 * 60  # tokens last ~1hr; refresh well before expiry

# On Windows, `gcloud` is a `.cmd` wrapper -- subprocess.run(["gcloud", ...]) without
# shell=True raises FileNotFoundError (CreateProcess doesn't do PATHEXT resolution
# the way a shell does). shutil.which() resolves the real (.cmd) path once at import
# time, avoiding both the FileNotFoundError and the need for shell=True.
_gcloud_path = shutil.which("gcloud")
if _gcloud_path is None:
    raise RuntimeError("gcloud not found on PATH -- required for identity-token auth")
_GCLOUD_EXE: str = _gcloud_path

_token_cache: dict[str, Any] = {"token": None, "fetched_at": 0.0}


def _get_identity_token() -> str:
    now = time.monotonic()
    if (
        _token_cache["token"] is None
        or (now - _token_cache["fetched_at"]) > _TOKEN_REFRESH_INTERVAL_S
    ):
        result = subprocess.run(
            [_GCLOUD_EXE, "auth", "print-identity-token"],
            capture_output=True,
            text=True,
            check=True,
        )
        _token_cache["token"] = result.stdout.strip()
        _token_cache["fetched_at"] = now
    return _token_cache["token"]


async def _gcp_chat(self: OllamaProvider, messages: list[Message], *, seed: int = 42) -> str:
    payload = {
        "model": self._model,  # noqa: SLF001 -- same-module-family monkeypatch, mirrors OllamaProvider.chat exactly
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "stream": False,
        "options": {"seed": seed},
    }
    token = _get_identity_token()
    async with httpx.AsyncClient(timeout=self._timeout) as client:  # noqa: SLF001
        resp = await client.post(
            f"{self.BASE_URL}/api/chat",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


OllamaProvider.BASE_URL = CLOUD_RUN_URL
OllamaProvider.chat = _gcp_chat  # type: ignore[method-assign]

from v2_5_argument_degradation_live import main  # noqa: E402 -- must patch first

if __name__ == "__main__":
    asyncio.run(main())
