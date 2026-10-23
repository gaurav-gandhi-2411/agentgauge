"""Turn `agentgauge diff --json` output into a GitHub job summary, step outputs and a pass/fail.

Used by the composite action in the repo-root `action.yml`. Stdlib only on purpose: it runs
after the CLI, must never be the thing that breaks, and reads replay files as plain JSON (just
for the trial count and recorded provenance) rather than importing agentgauge.

Decision rule (see `decide`):

* agentgauge exit 2 (stale replay, blocked audit, usage error), an unparseable diff JSON, or an
  unexpected exit code always FAILS the step -- `fail-on` cannot downgrade those.
* Otherwise the step fails iff the verdict is in `fail-on` (comma-separated verdict names,
  default ``regression``; ``none`` never fails on a verdict).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERDICTS = (
    "regression",
    "improvement",
    "no_change",
    "insufficient_sensitivity",
    "ceiling",
    "floor",
)
DEFAULT_FAIL_ON = ("regression",)


class ActionInputError(Exception):
    """A bad action input (for example an unknown `fail-on` verdict); the step fails with it."""


@dataclass
class Decision:
    """Outcome of `decide`: whether the step fails, the one-line reason, and the verdict if known."""

    failed: bool
    reason: str
    verdict: str = ""


def parse_fail_on(raw: str) -> frozenset[str]:
    """Parse the `fail-on` input. Empty -> default; ``none`` -> no verdict fails the step."""
    items = [p.strip().lower() for p in raw.replace("\n", ",").split(",") if p.strip()]
    if not items:
        return frozenset(DEFAULT_FAIL_ON)
    if items == ["none"]:
        return frozenset()
    unknown = [i for i in items if i not in VERDICTS]
    if unknown:
        raise ActionInputError(
            f"unknown fail-on value(s) {unknown}; use a comma-separated subset of "
            f"{', '.join(VERDICTS)}, or 'none'."
        )
    return frozenset(items)


def parse_diff_json(text: str) -> dict[str, Any]:
    """Parse the CLI's stdout. Raises ValueError with a clear message if it is not a JSON object."""
    if not text.strip():
        raise ValueError("agentgauge printed no JSON output")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"agentgauge output is not valid JSON ({exc.msg} at char {exc.pos})"
        ) from None
    if not isinstance(data, dict):
        raise ValueError("agentgauge JSON output is not an object")
    return data


def decide(
    exit_code: int, data: dict[str, Any] | None, error: str | None, fail_on: frozenset[str]
) -> Decision:
    """Map (CLI exit code, parsed JSON, parse error) to pass/fail. See the module docstring."""
    if data is not None and data.get("audit_failed"):
        blocking = "; ".join(str(b) for b in data.get("blocking", [])) or "see log"
        return Decision(True, f"audit blocked the diff: {blocking}")
    if exit_code == 2:
        return Decision(True, "agentgauge exited 2 (stale replay, blocked audit or usage error)")
    if exit_code not in (0, 1):
        return Decision(True, f"agentgauge exited with unexpected code {exit_code}")
    if data is None:
        return Decision(True, error or "no diff result to read")
    verdict = str(data.get("verdict", ""))
    if verdict not in VERDICTS:
        return Decision(True, f"unrecognised verdict {verdict!r} in agentgauge output")
    if exit_code == 1 and verdict != "regression":
        return Decision(True, f"agentgauge exited 1 with verdict {verdict!r} (unexpected)", verdict)
    if verdict in fail_on:
        listed = ", ".join(sorted(fail_on))
        return Decision(True, f"verdict '{verdict}' is in fail-on ({listed})", verdict)
    return Decision(False, f"verdict '{verdict}' does not fail the step", verdict)


def read_replay_info(path: Path | None) -> dict[str, Any]:
    """Trial count and provenance of a replay file (legacy bare list -> provenance None)."""
    info: dict[str, Any] = {"n": None, "provenance": None}
    if path is None:
        return info
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return info
    if isinstance(raw, dict):
        trials = raw.get("trials")
        info["provenance"] = {k: v for k, v in raw.items() if k != "trials"}
    else:
        trials = raw
    if isinstance(trials, list):
        info["n"] = len(trials)
    return info


def _fmt(value: Any, digits: int = 3, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, int) and not signed:
            return str(value)
        return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"
    return str(value)


def _provenance_cell(info: dict[str, Any]) -> str:
    prov = info["provenance"]
    if prov is None:
        return "no provenance (legacy file)"
    return (
        f"model `{prov.get('model')}`, seed {prov.get('seed')}, "
        f"agentgauge {prov.get('agentgauge_version')}, recorded {prov.get('created_utc')}"
    )


def _warnings(stderr_text: str) -> list[str]:
    return [ln.strip() for ln in stderr_text.splitlines() if ln.strip().startswith("Warning:")]


def _error_lines(stderr_text: str) -> list[str]:
    lines = [ln.strip() for ln in stderr_text.splitlines() if ln.strip()]
    return [ln for ln in lines if not ln.startswith("Warning:")]


def render_summary(
    decision: Decision,
    data: dict[str, Any] | None,
    before: dict[str, Any],
    after: dict[str, Any],
    stderr_text: str,
    exit_code: int,
) -> str:
    """Markdown for $GITHUB_STEP_SUMMARY."""
    status = "FAIL" if decision.failed else "PASS"
    out = [f"## agentgauge diff: {status}", ""]
    if data is not None and not data.get("audit_failed") and decision.verdict:
        b, a = data.get("before") or {}, data.get("after") or {}
        lo, hi = _fmt(data.get("ci_lo"), signed=True), _fmt(data.get("ci_hi"), signed=True)
        out += [
            "| | |",
            "|---|---|",
            f"| Verdict | `{decision.verdict}` |",
            f"| Delta (joint success, after - before) | {_fmt(data.get('delta'), signed=True)} |",
            f"| 95% CI | [{lo}, {hi}] |",
            f"| Regression threshold | {_fmt(data.get('threshold'), 2)} |",
            f"| Trials (before / after) | {_fmt(before['n'])} / {_fmt(after['n'])} |",
            f"| Joint success (before / after) | {_fmt(b.get('joint_success_rate'))} / "
            f"{_fmt(a.get('joint_success_rate'))} |",
            f"| Recorded (before) | {_provenance_cell(before)} |",
            f"| Recorded (after) | {_provenance_cell(after)} |",
            "",
            f"> {data.get('message', '')}",
            "",
        ]
    out.append(f"**Result:** {decision.reason}.")
    out.append("")
    warns = _warnings(stderr_text)
    if warns:
        out += ["### Warnings", ""] + [f"- {w}" for w in warns] + [""]
    if decision.failed and (exit_code != 0 or data is None):
        errs = _error_lines(stderr_text)
        if errs:
            out += ["### agentgauge said", "", "```text", *errs[:20], "```", ""]
    return "\n".join(out)


def output_values(data: dict[str, Any] | None, exit_code: int) -> dict[str, str]:
    """Step outputs; missing values are empty strings (outputs are always strings)."""
    d = data or {}

    def s(key: str) -> str:
        v = d.get(key)
        return "" if v is None else str(v)

    return {
        "verdict": s("verdict"),
        "delta": s("delta"),
        "ci-low": s("ci_lo"),
        "ci-high": s("ci_hi"),
        "exit-code": str(exit_code),
    }


def _append(path: str | None, text: str) -> None:
    if path:
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(text)


def _read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    """CLI entry: returns 0 to pass the step, 1 to fail it."""
    ap = argparse.ArgumentParser(description="Summarise `agentgauge diff --json` for GitHub.")
    ap.add_argument("--diff-json", type=Path, required=True)
    ap.add_argument("--stderr", type=Path)
    ap.add_argument("--exit-code", type=int, required=True)
    ap.add_argument("--replay-before", type=Path)
    ap.add_argument("--replay-after", type=Path)
    ap.add_argument("--fail-on", default="")
    ap.add_argument("--summary-file", type=Path, help="also write the summary Markdown here")
    ns = ap.parse_args(argv)

    try:
        fail_on = parse_fail_on(ns.fail_on)
    except ActionInputError as exc:
        print(f"::error title=agentgauge::{exc}")
        return 1

    data: dict[str, Any] | None = None
    error: str | None = None
    try:
        data = parse_diff_json(_read_text(ns.diff_json))
    except ValueError as exc:
        error = str(exc)

    decision = decide(ns.exit_code, data, error, fail_on)
    stderr_text = _read_text(ns.stderr)
    summary = render_summary(
        decision,
        data,
        read_replay_info(ns.replay_before),
        read_replay_info(ns.replay_after),
        stderr_text,
        ns.exit_code,
    )
    _append(os.environ.get("GITHUB_STEP_SUMMARY"), summary + "\n")
    if ns.summary_file is not None:
        ns.summary_file.write_text(summary + "\n", encoding="utf-8", newline="\n")
    _append(
        os.environ.get("GITHUB_OUTPUT"),
        "".join(f"{k}={v}\n" for k, v in output_values(data, ns.exit_code).items()),
    )
    for w in _warnings(stderr_text):
        print(f"::warning title=agentgauge::{w}")
    if decision.failed:
        errs = _error_lines(stderr_text)
        detail = f" -- {errs[0]}" if errs and ns.exit_code != 0 else ""
        print(f"::error title=agentgauge::{decision.reason}{detail}")
        return 1
    print(f"agentgauge: {decision.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
