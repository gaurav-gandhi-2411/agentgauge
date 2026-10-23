"""Replay files: recorded per-trial outcomes that `diff`/`eval` can re-score with no model.

Two on-disk shapes are readable:

* legacy -- a bare JSON list of trial records (the bundled demo replays). No provenance.
* v1 -- a JSON object ``{"format": "agentgauge-replay", "format_version": 1, ...,
  "trials": [...]}`` that records which model/seed/tool schemas/tasks file produced the trials, so
  a CI gate can refuse a replay that no longer matches the server under test.

Pure stdlib + `agentgauge.harness`; importable without pulling in the CLI.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentgauge import __version__
from agentgauge.harness import TrialOutcome

REPLAY_FORMAT = "agentgauge-replay"
REPLAY_FORMAT_VERSION = 1


class ReplayError(Exception):
    """A replay file cannot be read, parsed or written (the CLI turns this into exit 2)."""


@dataclass
class ReplayFile:
    """Loaded replay: the trials plus (v1 only) the provenance block; `provenance is None` = legacy."""

    trials: list[TrialOutcome]
    provenance: dict[str, Any] | None = None

    @property
    def tools_sha256(self) -> str | None:
        server = (self.provenance or {}).get("server")
        return server.get("tools_sha256") if isinstance(server, dict) else None

    @property
    def tasks_sha256(self) -> str | None:
        return (self.provenance or {}).get("tasks_sha256")

    def describe(self) -> str | None:
        """One-line header for a v1 file ('model=... seed=...'); None for a legacy file."""
        if self.provenance is None:
            return None
        p = self.provenance
        return (
            f"model={p.get('model')} seed={p.get('seed')} "
            f"trials/task={p.get('trials_per_task')} recorded={p.get('created_utc')} "
            f"agentgauge={p.get('agentgauge_version')}"
        )


def tools_sha256(tools: Sequence[Any]) -> str:
    """SHA-256 of the canonical JSON of a server's tool list.

    Only what the agent sees is hashed (name, description, inputSchema), sorted by name, with
    sorted keys and no whitespace -- so tool order and JSON formatting never change the hash, but
    any description or schema edit does. Accepts `mcp.types.Tool` objects or equivalent dicts.
    """

    def field(tool: Any, key: str) -> Any:
        return tool.get(key) if isinstance(tool, dict) else getattr(tool, key, None)

    canon = sorted(
        (
            {
                "name": field(t, "name"),
                "description": field(t, "description"),
                "inputSchema": field(t, "inputSchema"),
            }
            for t in tools
        ),
        key=lambda d: str(d["name"]),
    )
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's raw bytes (used for the tasks file)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReplayError(f"cannot read {path}: {exc}") from None


def load_replay(path: Path) -> ReplayFile:
    """Read a legacy (bare list) or v1 replay file. Raises `ReplayError` with an actionable message."""
    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise ReplayError(f"replay file not found: {path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"cannot read replay file {path}: {exc}") from None

    provenance: dict[str, Any] | None = None
    if isinstance(raw, dict):
        if raw.get("format") != REPLAY_FORMAT:
            raise ReplayError(
                f"{path} is not an agentgauge replay file "
                f'(expected "format": "{REPLAY_FORMAT}", got {raw.get("format")!r}).'
            )
        version = raw.get("format_version")
        if version != REPLAY_FORMAT_VERSION:
            raise ReplayError(
                f"unsupported replay format_version {version!r} in {path} (this agentgauge reads "
                f"{REPLAY_FORMAT_VERSION}); upgrade agentgauge or re-record the file."
            )
        provenance = {k: v for k, v in raw.items() if k != "trials"}
        raw = raw.get("trials")
    if not isinstance(raw, list):
        raise ReplayError(f"replay file {path} must hold a list of trial records.")
    try:
        return ReplayFile(trials=[TrialOutcome.from_dict(r) for r in raw], provenance=provenance)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ReplayError(f"malformed trial record in {path}: {exc!r}") from None


def save_replay(
    path: Path,
    trials: Sequence[TrialOutcome],
    *,
    model: str,
    seed: int,
    trials_per_task: int,
    target: str,
    tools_sha: str,
    tasks_sha: str | None,
    created_utc: str | None = None,
) -> None:
    """Write a v1 replay file atomically (temp file in the same directory, then `os.replace`).

    A failure part-way leaves the destination untouched (an old file stays intact, no partial
    file appears) and the temp file is removed.
    """
    payload = {
        "format": REPLAY_FORMAT,
        "format_version": REPLAY_FORMAT_VERSION,
        "agentgauge_version": __version__,
        "model": model,
        "seed": seed,
        "trials_per_task": trials_per_task,
        "created_utc": created_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server": {"target": target, "tools_sha256": tools_sha},
        "tasks_sha256": tasks_sha,
        "trials": [
            {
                "task_tool_name": t.task_tool_name,
                "selected_tool": t.selected_tool,
                "constraint_satisfaction": t.constraint_satisfaction,
            }
            for t in trials
        ],
    }
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(payload, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise ReplayError(f"cannot write replay file {path}: {exc}") from None
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise
