"""Unit tests for action/summarize.py (the GitHub Action's summary + pass/fail logic).

No LLM, no network, no agentgauge CLI: the diff JSON is hand-written.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "action_summarize", ROOT / "action" / "summarize.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["action_summarize"] = mod  # dataclasses needs the module registered
    spec.loader.exec_module(mod)
    return mod


S = _load()


def _diff(verdict: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "verdict": verdict,
        "delta": -0.2,
        "ci_lo": -0.3,
        "ci_hi": -0.1,
        "threshold": 0.05,
        "message": "the message",
        "before": {"joint_success_rate": 0.9},
        "after": {"joint_success_rate": 0.7},
    }
    base.update(kw)
    return base


def _v1(path: Path, n: int = 12) -> Path:
    path.write_text(
        json.dumps(
            {
                "format": "agentgauge-replay",
                "format_version": 1,
                "agentgauge_version": "9.9.9",
                "model": "m-test",
                "seed": 42,
                "created_utc": "2026-01-01T00:00:00Z",
                "trials": [{"task_tool_name": "t"}] * n,
            }
        ),
        encoding="utf-8",
    )
    return path


# --- fail-on parsing ------------------------------------------------------------------------


def test_fail_on_default_is_regression_only() -> None:
    assert S.parse_fail_on("") == frozenset({"regression"})
    assert S.parse_fail_on("  ") == frozenset({"regression"})


def test_fail_on_list_none_and_unknown() -> None:
    assert S.parse_fail_on("regression, insufficient_sensitivity") == frozenset(
        {"regression", "insufficient_sensitivity"}
    )
    assert S.parse_fail_on("none") == frozenset()
    with pytest.raises(S.ActionInputError, match="bogus"):
        S.parse_fail_on("regression,bogus")


# --- verdict -> pass/fail --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verdict", "code", "fail_on", "failed"),
    [
        ("regression", 1, "regression", True),
        ("regression", 1, "none", False),  # fail-on can relax even the CLI's own exit 1
        ("improvement", 0, "regression", False),
        ("no_change", 0, "regression", False),
        ("insufficient_sensitivity", 0, "regression", False),  # must NOT fail by default
        ("insufficient_sensitivity", 0, "regression,insufficient_sensitivity", True),
        ("ceiling", 0, "ceiling,floor", True),
        ("floor", 0, "regression", False),
        ("no_change", 0, "no_change", True),
    ],
)
def test_decide_verdict_mapping(verdict: str, code: int, fail_on: str, failed: bool) -> None:
    d = S.decide(code, _diff(verdict), None, S.parse_fail_on(fail_on))
    assert d.failed is failed
    assert d.verdict == verdict


@pytest.mark.parametrize("fail_on", ["none", "regression", "regression,improvement"])
def test_exit_2_always_fails(fail_on: str) -> None:
    d = S.decide(2, None, "no JSON", S.parse_fail_on(fail_on))
    assert d.failed
    assert "exited 2" in d.reason


def test_audit_failed_payload_fails_with_blocking_detail() -> None:
    data = {"audit_failed": True, "blocking": ["task leaks the tool name"]}
    d = S.decide(2, data, None, S.parse_fail_on("none"))
    assert d.failed
    assert "task leaks the tool name" in d.reason


def test_unexpected_exit_code_and_inconsistent_exit_1_fail() -> None:
    assert S.decide(137, _diff("no_change"), None, frozenset()).failed
    # exit 1 means regression; any other verdict with exit 1 is a contract break, not a pass.
    assert S.decide(1, _diff("no_change"), None, frozenset()).failed
    assert S.decide(0, _diff("mystery_verdict"), None, frozenset()).failed


# --- malformed input -------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   \n", "not json", "{truncated", "[1, 2]"])
def test_malformed_json_is_a_clear_failure(text: str) -> None:
    with pytest.raises(ValueError, match="agentgauge"):
        S.parse_diff_json(text)
    d = S.decide(0, None, "agentgauge printed no JSON output", S.parse_fail_on(""))
    assert d.failed
    assert "no JSON" in d.reason


def test_main_malformed_json_exits_1_and_still_writes_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summ, outp = tmp_path / "summary.md", tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    monkeypatch.setenv("GITHUB_OUTPUT", str(outp))
    bad = tmp_path / "diff.json"
    bad.write_text("{oops", encoding="utf-8")
    rc = S.main(["--diff-json", str(bad), "--exit-code", "0"])
    assert rc == 1
    assert "::error" in capsys.readouterr().out
    assert "FAIL" in summ.read_text(encoding="utf-8")
    assert "exit-code=0" in outp.read_text(encoding="utf-8")


# --- summary content + outputs ---------------------------------------------------------------


def test_summary_content_with_provenance_and_warnings(tmp_path: Path) -> None:
    before, after = _v1(tmp_path / "b.json", 12), _v1(tmp_path / "a.json", 8)
    d = S.decide(1, _diff("regression"), None, S.parse_fail_on(""))
    md = S.render_summary(
        d,
        _diff("regression"),
        S.read_replay_info(before),
        S.read_replay_info(after),
        "Warning: replay-after is stale: tool schema changed. Continuing (--allow-stale-replay).\n",
        1,
    )
    assert "## agentgauge diff: FAIL" in md
    assert "| Verdict | `regression` |" in md
    assert "-0.200" in md
    assert "[-0.300, -0.100]" in md
    assert "| Trials (before / after) | 12 / 8 |" in md
    assert "model `m-test`, seed 42, agentgauge 9.9.9, recorded 2026-01-01T00:00:00Z" in md
    assert "### Warnings" in md
    assert "replay-after is stale" in md


def test_summary_legacy_replay_has_no_provenance(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps([{"task_tool_name": "t"}] * 5), encoding="utf-8")
    info = S.read_replay_info(legacy)
    assert info == {"n": 5, "provenance": None}
    d = S.decide(0, _diff("no_change"), None, S.parse_fail_on(""))
    md = S.render_summary(d, _diff("no_change"), info, S.read_replay_info(None), "", 0)
    assert "PASS" in md
    assert "no provenance (legacy file)" in md
    assert "| Trials (before / after) | 5 / n/a |" in md


def test_summary_null_ci_renders_na() -> None:
    data = _diff("insufficient_sensitivity", delta=0.5, ci_lo=None, ci_hi=None)
    d = S.decide(0, data, None, S.parse_fail_on(""))
    md = S.render_summary(d, data, S.read_replay_info(None), S.read_replay_info(None), "", 0)
    assert "| 95% CI | [n/a, n/a] |" in md
    assert S.output_values(data, 0)["ci-low"] == ""


def test_summary_failure_includes_cli_error_line() -> None:
    d = S.decide(2, None, "agentgauge printed no JSON output", S.parse_fail_on(""))
    md = S.render_summary(
        d, None, S.read_replay_info(None), S.read_replay_info(None),
        "Error: replay-after is stale: tool schema changed.\n", 2,
    )  # fmt: skip
    assert "### agentgauge said" in md
    assert "Error: replay-after is stale" in md


def test_output_values() -> None:
    out = S.output_values(_diff("regression"), 1)
    assert out == {
        "verdict": "regression",
        "delta": "-0.2",
        "ci-low": "-0.3",
        "ci-high": "-0.1",
        "exit-code": "1",
    }


def test_main_passes_on_insufficient_sensitivity_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    f = tmp_path / "diff.json"
    f.write_text(json.dumps(_diff("insufficient_sensitivity")), encoding="utf-8")
    assert S.main(["--diff-json", str(f), "--exit-code", "0"]) == 0
    assert (
        S.main(["--diff-json", str(f), "--exit-code", "0", "--fail-on", "insufficient_sensitivity"])
        == 1
    )


def test_main_bad_fail_on_fails(tmp_path: Path) -> None:
    f = tmp_path / "diff.json"
    f.write_text(json.dumps(_diff("no_change")), encoding="utf-8")
    assert S.main(["--diff-json", str(f), "--exit-code", "0", "--fail-on", "typo"]) == 1
