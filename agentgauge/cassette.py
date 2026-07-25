"""Record/replay cassette for `agentgauge.providers.Provider.chat()` calls.

Wave 1's model-adapter abstraction (spec-agentgauge-v0.5.md S4.1) can only ship if it
preserves the product's headline claim: 100% replay determinism (v0.4.0). This module
is the mechanism that makes a provider call replayable byte-for-byte, independent of
which adapter served it.

Design (see `reports/v0_5_eval_doctrine.md` Component 1.1):
- A call is keyed on `(provider_name, model, seed, messages)`, hashed via
  `cassette_key()` -- sha256 over a canonical JSON serialization, never Python's
  salted `hash()` or object identity, so the key is stable across process restarts
  and platforms.
- `Cassette` is a JSON-file-backed key -> recorded-response store.
- `CassetteProvider` implements the `Provider` protocol structurally. In **record**
  mode (constructed with `provider=<real Provider>`) it calls through and stores the
  response. In **replay** mode (constructed with `provider=None`) it looks up the
  key and returns the stored response -- a miss is a hard `CassetteMiss` error, never
  a silent live-call fallback or a default value. A silent fallback would itself be
  the exact nondeterminism-hiding bug this mechanism exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentgauge.providers import Message, Provider


def cassette_key(provider_name: str, model: str, seed: int, messages: list[Message]) -> str:
    """Deterministic cache key for a `(provider_name, model, seed, messages)` call.

    Stability requirements (must hold across Python process restarts and platforms):
    - sha256 over a canonical JSON serialization (`sort_keys=True`, fixed separators,
      `ensure_ascii=True`) -- never Python's built-in `hash()` (salted per-process for
      str/bytes since PEP 456) or `id()`/dict-iteration order, both of which vary
      between runs and would silently break replay.
    - Truncated to the first 16 hex chars (64 bits). Collision risk is negligible at
      cassette-sized fixture sets (low hundreds of distinct keys at most); a short key
      keeps cassette JSON files readable in diffs and code review.
    """
    payload = {
        "provider_name": provider_name,
        "model": model,
        "seed": seed,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]


class CassetteMiss(KeyError):
    """Raised by a replay-mode `CassetteProvider` when no recorded entry matches the
    computed key. This is a hard error by design: replay mode must never fall back
    to a live call or a placeholder response (see module docstring)."""


@dataclass
class CassetteEntry:
    """One recorded `chat()` call. `tokens_in`/`tokens_out` are additive metadata for
    the cost-accounting work (spec S4.1) -- populated when the wrapped provider in
    record mode exposes them, `None` otherwise (e.g. `OllamaProvider` has no cost
    tracking today)."""

    response: str
    tokens_in: int | None = None
    tokens_out: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {"response": self.response, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CassetteEntry:
        """Deserialize from a dict produced by `to_dict()` (or loaded JSON)."""
        return cls(
            response=d["response"],
            tokens_in=d.get("tokens_in"),
            tokens_out=d.get("tokens_out"),
        )


class Cassette:
    """In-memory, JSON-file-backed store of recorded `chat()` responses, keyed by
    `cassette_key()`.

    File format::

        {"entries": {"<16-hex-char key>": {"response": str,
                                            "tokens_in": int | null,
                                            "tokens_out": int | null}, ...}}

    One file per cassette. Callers choose the path (e.g. one cassette per
    fixture-set x adapter combination).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries: dict[str, CassetteEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> CassetteEntry | None:
        """Look up a recorded entry by key, or `None` if absent."""
        return self._entries.get(key)

    def set(self, key: str, entry: CassetteEntry) -> None:
        """Store (or overwrite) a recorded entry under `key`."""
        self._entries[key] = entry

    def save(self) -> None:
        """Write all entries to `self.path` as JSON, creating parent dirs as needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": {k: v.to_dict() for k, v in self._entries.items()}}
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Cassette:
        """Load a cassette from `path`. Returns an empty cassette if the file does
        not exist yet (the common case when starting a fresh recording)."""
        cassette = cls(path)
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            for key, raw_entry in data.get("entries", {}).items():
                cassette._entries[key] = CassetteEntry.from_dict(raw_entry)
        return cassette


class CassetteProvider:
    """Wraps a `Provider` to record or replay `chat()` calls, keyed by
    `(provider_name, model, seed, messages)`.

    Record mode: pass `provider=<real Provider instance>`. Each `chat()` call is
    forwarded to the wrapped provider; the response (and token counts, if the
    wrapped provider exposes `tokens_in`/`tokens_out`) is stored in `cassette` and
    returned unchanged.

    Replay mode: pass `provider=None` and an explicit `model=` (there is no live
    provider to ask for `model_name`). Each `chat()` call computes the same key and
    returns the previously recorded response. A missing key raises `CassetteMiss` --
    replay NEVER falls back to a live call or a default value.
    """

    def __init__(
        self,
        cassette: Cassette,
        provider_name: str,
        *,
        provider: Provider | None = None,
        model: str | None = None,
    ) -> None:
        if provider is None and model is None:
            raise ValueError(
                "Replay-mode CassetteProvider (provider=None) requires an explicit "
                "model= argument -- there is no live provider to ask for model_name."
            )
        self._cassette = cassette
        self._provider_name = provider_name
        self._provider = provider
        self._model = model if model is not None else provider.model_name  # type: ignore[union-attr]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_recording(self) -> bool:
        """True in record mode (a live provider is wrapped), False in replay mode."""
        return self._provider is not None

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        key = cassette_key(self._provider_name, self._model, seed, messages)

        if self._provider is not None:
            response = await self._provider.chat(messages, seed=seed)
            tokens_in = getattr(self._provider, "tokens_in", None)
            tokens_out = getattr(self._provider, "tokens_out", None)
            self._cassette.set(
                key, CassetteEntry(response=response, tokens_in=tokens_in, tokens_out=tokens_out)
            )
            return response

        entry = self._cassette.get(key)
        if entry is None:
            raise CassetteMiss(
                f"No recorded cassette entry for key={key!r} "
                f"(provider_name={self._provider_name!r}, model={self._model!r}, seed={seed}). "
                "Replay mode never falls back to a live call -- record a cassette first."
            )
        return entry.response
