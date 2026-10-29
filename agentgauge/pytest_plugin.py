"""pytest plugin: gate a test suite on an AgentGauge before/after verdict, with no model.

Auto-loaded through the ``pytest11`` entry point, so it is imported by *every* pytest session in
an environment that has agentgauge installed. Nothing heavy is imported at module level (the
statistics, MCP client and audit modules load inside functions) so an unrelated suite pays almost
nothing and cannot be broken by this module. Disable with ``-p no:agentgauge``.

Usage::

    def test_no_regression(agentgauge_diff):
        result = agentgauge_diff(
            replay_before="tests/agentgauge/replay_before.json",
            replay_after="tests/agentgauge/replay_after.json",
        )
        assert_no_regression(result)

Verdict -> outcome (inconclusive is never a silent pass):

=====================================  ==========================================================
regression                             fail
improvement, no_change                 pass
insufficient_sensitivity               skip with the MDE message (fail with
                                       ``--agentgauge-inconclusive=fail``)
ceiling, floor                         skip with a reason (same option applies)
blocking audit finding, stale replay,  fail, raised by the ``agentgauge_diff`` fixture itself:
unreadable replay, unreachable server  a broken measurement never shows up as a skip
=====================================  ==========================================================

Replays are the cassettes: the fixture only reads recorded trials, so CI needs no model, keys or
network. There is no mock path, so a mock verdict cannot be produced. Live runs (a model) are not
implemented: ``--agentgauge-live`` is accepted so a suite can opt in later, but today it fails
with an instruction to record replays with ``agentgauge diff --save-before/--save-after``.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from agentgauge.harness import DecomposedRate, DiffResult

INCONCLUSIVE_CHOICES = ("skip", "fail")
_SKIPPED_KEY = pytest.StashKey[list[str]]()
_UNCHECKED_KEY = pytest.StashKey[list[str]]()  # node ids whose replay freshness went unchecked


@dataclass
class AgentGaugeResult:
    """What `agentgauge_diff` returns: the diff result plus the context needed to map it."""

    diff: DiffResult
    inconclusive: str = "skip"  # "skip" | "fail", from --agentgauge-inconclusive
    notes: list[str] = field(default_factory=list)  # non-fatal findings (audit warnings, legacy)
    config: Any = field(default=None, repr=False)  # pytest Config, used to count skipped verdicts

    @property
    def verdict(self) -> str:
        return str(self.diff.verdict.value)

    @property
    def delta(self) -> float:
        return self.diff.delta

    @property
    def ci_lo(self) -> float:
        return self.diff.ci_lo

    @property
    def ci_hi(self) -> float:
        return self.diff.ci_hi

    @property
    def message(self) -> str:
        return self.diff.message

    @property
    def before(self) -> DecomposedRate:
        return self.diff.before_decomposed

    @property
    def after(self) -> DecomposedRate:
        return self.diff.after_decomposed


# ── hooks ────────────────────────────────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("agentgauge")
    group.addoption(
        "--agentgauge-inconclusive",
        choices=INCONCLUSIVE_CHOICES,
        default="skip",
        help="Outcome for an inconclusive agentgauge verdict "
        "(insufficient_sensitivity, ceiling, floor): skip (default) or fail.",
    )
    group.addoption(
        "--agentgauge-live",
        action="store_true",
        default=False,
        help="Allow agentgauge_diff to use a live model. Off by default: without it a live "
        "request is skipped and no model is ever called.",
    )
    group.addoption(
        "--agentgauge-require-fresh",
        action="store_true",
        default=False,
        help="Fail a test whose v1 replay freshness was not checked (before_server=/"
        "after_server= not given). Off by default: the verdict itself needs no server.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "agentgauge: test gates on an agentgauge before/after verdict "
        "(select with -m agentgauge, deselect with -m 'not agentgauge')",
    )
    config.stash[_SKIPPED_KEY] = []
    config.stash[_UNCHECKED_KEY] = []


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    skipped = config.stash.get(_SKIPPED_KEY, [])
    if skipped:
        terminalreporter.write_line(
            f"agentgauge: {len(skipped)} inconclusive verdict(s) skipped, not passed "
            f"({', '.join(skipped)}); see skip reasons with -rs, or use "
            "--agentgauge-inconclusive=fail."
        )
    unchecked = config.stash.get(_UNCHECKED_KEY, [])
    if unchecked:
        terminalreporter.write_line(
            f"agentgauge: {len(unchecked)} result(s) with replay freshness not checked "
            "(pass before_server/after_server, or use --agentgauge-require-fresh to fail)."
        )


# ── result mapping ───────────────────────────────────────────────────────────


def assert_no_regression(result: AgentGaugeResult, *, inconclusive: str | None = None) -> None:
    """Apply the verdict -> outcome table: raise on regression, skip/fail when inconclusive.

    `inconclusive` overrides the `--agentgauge-inconclusive` option for this call.
    """
    mode = inconclusive or result.inconclusive
    if mode not in INCONCLUSIVE_CHOICES:
        raise ValueError(f"inconclusive must be one of {INCONCLUSIVE_CHOICES}, got {mode!r}")
    verdict = result.verdict
    if verdict == "regression":
        pytest.fail(f"agentgauge regression: {result.message}", pytrace=False)
    if verdict in ("improvement", "no_change"):
        return
    if verdict == "insufficient_sensitivity":
        reason = f"agentgauge {verdict}: {result.message}"
    elif verdict in ("ceiling", "floor"):
        reason = f"agentgauge {verdict}: the task set cannot discriminate. {result.message}"
    else:  # a verdict added later must not become a silent pass
        pytest.fail(f"agentgauge: unknown verdict {verdict!r}: {result.message}", pytrace=False)
    if mode == "fail":
        pytest.fail(f"{reason} (--agentgauge-inconclusive=fail)", pytrace=False)
    if result.config is not None:
        result.config.stash.setdefault(_SKIPPED_KEY, []).append(verdict)
    pytest.skip(reason)


# ── fixture ──────────────────────────────────────────────────────────────────


async def _tools_sha_async(target: str) -> str:
    from agentgauge.client import cleanup_connection, connect_http, connect_stdio
    from agentgauge.replay import tools_sha256

    if target.startswith(("http://", "https://")):
        client, ctx = await connect_http(target)
    else:
        if not Path(target).is_file():
            raise FileNotFoundError(f"server script not found: {target}")
        client, ctx = await connect_stdio(sys.executable, [target])
    try:
        info = await client.introspect()
        return tools_sha256(list(info.tools))
    finally:
        await cleanup_connection(ctx)


def server_tools_sha(target: str) -> str:
    """Hash a server's tool list (connect, introspect, disconnect: no model involved).

    Runs in a worker thread so it also works when the calling test already has an event loop.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _tools_sha_async(target)).result()


def _make_diff(request: pytest.FixtureRequest) -> Callable[..., AgentGaugeResult]:
    config = request.config

    def agentgauge_diff(
        *,
        replay_before: str | Path | None = None,
        replay_after: str | Path | None = None,
        before_server: str | None = None,
        after_server: str | None = None,
        tasks: str | Path | None = None,
        threshold: float = 0.05,
        live: bool = False,
    ) -> AgentGaugeResult:
        """Diff two recorded replays. See the module docstring for the outcome mapping.

        Pass `before_server`/`after_server` (and `tasks`, if the replays were recorded with a tasks
        file) to fail when a v1 replay no longer matches the server's tool schemas.
        """
        from agentgauge.audit import run_audit
        from agentgauge.harness import diff_from_trials
        from agentgauge.replay import (
            ReplayError,
            file_sha256,
            load_replay,
            staleness_problems,
        )

        if live:
            if not config.getoption("--agentgauge-live"):
                pytest.skip(
                    "agentgauge live run requested but --agentgauge-live is not set "
                    "(no model is ever called by default); pass replay_before= and replay_after="
                )
            pytest.fail(
                "agentgauge: live runs are not implemented in this release. Record replays "
                "with `agentgauge diff --save-before/--save-after` and pass "
                "replay_before=/replay_after=.",
                pytrace=False,
            )
        # A misconfigured test is a broken measurement, not a request to go live: never skip.
        missing = [
            name
            for name, value in (("replay_before", replay_before), ("replay_after", replay_after))
            if value is None
        ]
        if missing:
            pytest.fail(
                f"agentgauge: missing argument(s): {', '.join(missing)}=. Pass both replay_before= "
                "and replay_after= (or live=True to request a live run).",
                pytrace=False,
            )
        assert replay_before is not None and replay_after is not None  # narrowed for mypy
        try:
            before = load_replay(Path(replay_before))
            after = load_replay(Path(replay_after))
        except ReplayError as exc:
            pytest.fail(f"agentgauge: {exc}", pytrace=False)

        notes: list[str] = []
        if (before_server is None) != (after_server is None):
            pytest.fail(
                "agentgauge: give both before_server= and after_server=, or neither.",
                pytrace=False,
            )
        if before_server is not None and after_server is not None:
            try:
                tasks_sha = file_sha256(Path(tasks)) if tasks is not None else None
            except ReplayError as exc:
                pytest.fail(f"agentgauge: {exc}", pytrace=False)
            for label, rf, target in (
                ("before", before, before_server),
                ("after", after, after_server),
            ):
                if rf.provenance is None:
                    notes.append(f"{label} replay is legacy (no provenance): staleness unchecked")
                    continue
                try:
                    live_sha = server_tools_sha(target)
                except Exception as exc:  # broken server = broken measurement, not a skip
                    pytest.fail(
                        f"agentgauge: cannot introspect {label} server {target}: {exc!r}",
                        pytrace=False,
                    )
                problems = staleness_problems(rf, live_tools_sha=live_sha, live_tasks_sha=tasks_sha)
                if problems:
                    pytest.fail(
                        f"agentgauge: {label} replay is stale: {'; '.join(problems)}. "
                        f"Re-record it with `agentgauge diff --save-{label}`.",
                        pytrace=False,
                    )

        else:
            unchecked = [
                label
                for label, rf in (("before", before), ("after", after))
                if rf.provenance is not None
            ]
            if unchecked:
                if config.getoption("--agentgauge-require-fresh"):
                    pytest.fail(
                        f"agentgauge: {' and '.join(unchecked)} replay freshness not checked "
                        "and --agentgauge-require-fresh is set: pass before_server= and "
                        "after_server=.",
                        pytrace=False,
                    )
                notes.append("replay freshness not checked: pass before_server/after_server")
                config.stash.setdefault(_UNCHECKED_KEY, []).append(request.node.nodeid)

        report = run_audit([], before_trials=before.trials, after_trials=after.trials)
        if report.blocking:
            details = "; ".join(f"({f.check}) {f.detail}" for f in report.blocking)
            pytest.fail(f"agentgauge: audit blocked the measurement: {details}", pytrace=False)
        notes.extend(f"audit warning ({f.check}): {f.detail}" for f in report.warnings)

        diff = diff_from_trials(before.trials, after.trials, threshold=threshold)
        return AgentGaugeResult(
            diff=diff,
            inconclusive=config.getoption("--agentgauge-inconclusive"),
            notes=notes,
            config=config,
        )

    return agentgauge_diff


@pytest.fixture
def agentgauge_diff(request: pytest.FixtureRequest) -> Callable[..., AgentGaugeResult]:
    """Factory: diff two replay files into an `AgentGaugeResult` (never calls a model)."""
    return _make_diff(request)
