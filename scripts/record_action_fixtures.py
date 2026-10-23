"""Regenerate the tiny replay pair used by the GitHub Action self-test.

    python scripts/record_action_fixtures.py

No model and no network: the trial outcomes are hand-written constants (a "before" server whose
two undocumented tools get mis-selected, an "after" server that fixes them). What is real is the
provenance, written through the public `agentgauge.replay.save_replay`: each file records the
tool-schema hash of the actual server it claims, `examples/echo_server.py` (before) and
`examples/echo_server_fixed.py` (after). The self-test then proves the staleness gate both ways:
the matching servers pass; pointing `after-server` at the unfixed server makes the CLI exit 2.

A second pair, regress_{before,after}.json, is a deterministic REGRESSION: "before" (recorded from
echo_server_fixed.py) succeeds on every trial, "after" (echo_server.py) selects nothing on any
trial. Both arms are constant but at different extremes, so the bootstrap CI is degenerate
([-1, -1]) and the verdict is `regression` without depending on resampling.

Output: tests/fixtures/action/{before,after,regress_before,regress_after}.json (committed). Re-run after editing either
example server, otherwise the self-test's "fresh" job would start failing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from agentgauge.cli import _introspect_tools
from agentgauge.harness import TrialOutcome
from agentgauge.replay import save_replay, tools_sha256

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "tests" / "fixtures" / "action"
SEED = 42
TRIALS_PER_TASK = 4
TOOLS = ("echo", "add", "mystery", "greet")
# A fixed, documented timestamp keeps the committed files byte-stable across regenerations.
CREATED_UTC = "2026-10-23T00:00:00Z"


def _all(*, ok: bool) -> list[TrialOutcome]:
    """Every trial succeeds (`ok`) or selects no tool at all."""
    return [
        TrialOutcome(
            task_tool_name=tool,
            selected_tool=tool if ok else None,
            constraint_satisfaction=1.0 if ok else 0.0,
        )
        for tool in TOOLS
        for _ in range(TRIALS_PER_TASK)
    ]


def _trials(*, fixed: bool) -> list[TrialOutcome]:
    """Hand-written outcomes. Before: the two undocumented tools are never selected correctly."""
    out: list[TrialOutcome] = []
    for tool in TOOLS:
        ok = fixed or tool in ("echo", "add")
        for _ in range(TRIALS_PER_TASK):
            out.append(
                TrialOutcome(
                    task_tool_name=tool,
                    selected_tool=tool if ok else "echo",
                    constraint_satisfaction=1.0 if ok else 0.0,
                )
            )
    return out


async def _record() -> None:
    for arm, server, trials in (
        ("before", "examples/echo_server.py", _trials(fixed=False)),
        ("after", "examples/echo_server_fixed.py", _trials(fixed=True)),
        ("regress_before", "examples/echo_server_fixed.py", _all(ok=True)),
        ("regress_after", "examples/echo_server.py", _all(ok=False)),
    ):
        tools = await _introspect_tools(str(ROOT / server))
        save_replay(
            OUT_DIR / f"{arm}.json",
            trials,
            model="hand-written-fixture",
            seed=SEED,
            trials_per_task=TRIALS_PER_TASK,
            target=server,
            tools_sha=tools_sha256(tools),
            tasks_sha=None,
            created_utc=CREATED_UTC,
        )
        print(f"wrote {OUT_DIR / f'{arm}.json'}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(_record())
