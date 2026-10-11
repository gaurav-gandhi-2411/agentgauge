"""Task 7: pooled degenerate-metrics audit, CEILING / FLOOR verdicts, replay runs the audit."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from agentgauge.audit import check_degenerate_metrics_pooled, run_audit
from agentgauge.cli import app
from agentgauge.harness import TrialOutcome, Verdict, diff_from_trials

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _flat(s: str) -> str:
    return " ".join(_ANSI.sub("", s).split())


def _trials(n_pass: int, n_fail: int, score: float = 1.0) -> list[TrialOutcome]:
    return [TrialOutcome("t", "t", score)] * n_pass + [TrialOutcome("t", "u", 0.0)] * n_fail


def _write(path: Path, trials: list[TrialOutcome]) -> str:
    rows = [
        {
            "task_tool_name": t.task_tool_name,
            "selected_tool": t.selected_tool,
            "constraint_satisfaction": t.constraint_satisfaction,
        }
        for t in trials
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")
    return str(path)


class TestPooledDegenerate:
    def test_perfect_after_arm_passes(self) -> None:
        report = run_audit([], before_trials=_trials(16, 8), after_trials=_trials(24, 0))
        assert report.passed, [f.detail for f in report.blocking]

    def test_perfect_before_arm_passes(self) -> None:
        assert run_audit([], before_trials=_trials(24, 0), after_trials=_trials(16, 8)).passed

    def test_both_arms_all_pass_does_not_block(self) -> None:
        report = run_audit([], before_trials=_trials(24, 0), after_trials=_trials(24, 0))
        assert report.passed  # CEILING is reported by the diff, not blocked by the audit
        assert any(f.check == "ceiling_floor" for f in report.warnings)

    def test_both_arms_all_fail_does_not_block(self) -> None:
        assert run_audit([], before_trials=_trials(0, 24), after_trials=_trials(0, 24)).passed

    def test_pooled_constant_non_extreme_still_blocks(self) -> None:
        pooled = check_degenerate_metrics_pooled(_trials(10, 0, 0.5), _trials(10, 0, 0.5))
        assert len(pooled) == 1 and pooled[0].severity == "block"

    def test_single_arm_run_still_uses_the_per_arm_check(self) -> None:
        report = run_audit([], before_trials=_trials(10, 0))
        assert [f.check for f in report.blocking] == ["degenerate_metrics"]


class TestCeilingFloorVerdict:
    def test_both_arms_one_is_ceiling(self) -> None:
        r = diff_from_trials(_trials(24, 0), _trials(24, 0))
        assert r.verdict == Verdict.CEILING
        assert r.exit_code == 0
        assert "scored 1.0" in r.message and "no headroom" in r.message

    def test_both_arms_zero_is_floor(self) -> None:
        r = diff_from_trials(_trials(0, 24), _trials(0, 24))
        assert r.verdict == Verdict.FLOOR
        assert r.exit_code == 0
        assert "scored 0.0" in r.message

    def test_one_constant_arm_still_reports_a_delta(self) -> None:
        r = diff_from_trials(_trials(0, 24), _trials(24, 0))
        assert r.verdict == Verdict.IMPROVEMENT
        assert r.delta == 1.0

    def test_values_between_zero_and_one_are_not_ceiling(self) -> None:
        r = diff_from_trials(_trials(24, 0, 0.5), _trials(24, 0, 0.5))
        assert r.verdict == Verdict.NO_CHANGE


class TestReplayRunsTheAudit:
    def test_replay_ceiling_exits_zero_with_no_delta_text(self, tmp_path: Path) -> None:
        b = _write(tmp_path / "b.json", _trials(24, 0))
        a = _write(tmp_path / "a.json", _trials(24, 0))
        result = CliRunner().invoke(
            app, ["diff", "before.py", "after.py", "--replay-before", b, "--replay-after", a]
        )
        out = _flat(result.output)
        assert result.exit_code == 0, result.output
        assert "CEILING" in out and "no delta to estimate" in out
        assert "95% CI" not in out

    def test_replay_floor_json_has_null_delta(self, tmp_path: Path) -> None:
        b = _write(tmp_path / "b.json", _trials(0, 24))
        a = _write(tmp_path / "a.json", _trials(0, 24))
        result = CliRunner().invoke(
            app,
            ["diff", "before.py", "after.py", "--replay-before", b, "--replay-after", a, "--json"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output[result.output.index("{") :])
        assert payload["verdict"] == "floor" and payload["delta"] is None

    def test_replay_with_a_perfect_after_arm_reports_the_delta(self, tmp_path: Path) -> None:
        b = _write(tmp_path / "b.json", _trials(16, 8))
        a = _write(tmp_path / "a.json", _trials(24, 0))
        result = CliRunner().invoke(
            app, ["diff", "before.py", "after.py", "--replay-before", b, "--replay-after", a]
        )
        assert result.exit_code == 0, result.output
        assert "AUDIT BLOCK" not in result.output

    def test_replay_blocks_on_a_constant_non_extreme_scorer(self, tmp_path: Path) -> None:
        """Proves the replay path runs the audit: this input only fails if run_audit executes."""
        b = _write(tmp_path / "b.json", _trials(10, 0, 0.5))
        a = _write(tmp_path / "a.json", _trials(10, 0, 0.5))
        result = CliRunner().invoke(
            app, ["diff", "before.py", "after.py", "--replay-before", b, "--replay-after", a]
        )
        assert result.exit_code == 2
        assert "degenerate_metrics" in result.output
