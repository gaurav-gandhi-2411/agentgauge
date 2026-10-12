"""Task 8: check_constraint_coverage -- selection-only / partial / full, and the output label."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from agentgauge import cli
from agentgauge.audit import (
    FULL,
    PARTIAL,
    SELECTION_ONLY,
    check_constraint_coverage,
    classify_task_coverage,
    run_audit,
    summarize_constraint_coverage,
)
from agentgauge.cli import app
from agentgauge.constraints import BlindTask, Constraint
from agentgauge.harness import TrialOutcome

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _flat(s: str) -> str:
    return " ".join(_ANSI.sub("", s).split())


def _tool(name: str, required: list[str]) -> SimpleNamespace:
    props = {p: {"type": "string"} for p in required}
    return SimpleNamespace(
        name=name, inputSchema={"type": "object", "properties": props, "required": required}
    )


def _enum(param: str, value: str) -> Constraint:
    return Constraint(param=param, kind="enum", gold_value=value)


class TestClassification:
    def test_no_constraints_is_selection_only(self) -> None:
        t = BlindTask("open_ticket", "Open a ticket about the login failure")
        assert classify_task_coverage(t, ["title"]).klass == SELECTION_ONLY

    def test_required_param_without_constraint_is_partial(self) -> None:
        t = BlindTask("open_ticket", "Open a ticket", [_enum("priority", "high")])
        c = classify_task_coverage(t, ["title", "priority"])
        assert c.klass == PARTIAL
        assert c.unconstrained == ["required param 'title'"]

    def test_unchecked_stated_value_is_partial(self) -> None:
        t = BlindTask("set_mode", "Put sensor S03 into fast mode", [_enum("mode", "fast")])
        c = classify_task_coverage(t, ["mode"])  # S03 is stated but nothing checks it
        assert c.klass == PARTIAL
        assert c.unconstrained == ["stated value 'S03'"]

    def test_every_required_param_and_stated_value_covered_is_full(self) -> None:
        t = BlindTask(
            "set_mode",
            "Put sensor S03 into fast mode",
            [
                _enum("mode", "fast"),
                Constraint(param="sensor_id", kind="contains", gold_value="S03"),
            ],
        )
        assert classify_task_coverage(t, ["mode", "sensor_id"]).klass == FULL

    def test_quoted_value_and_range_and_numeric_constraints_count_as_checks(self) -> None:
        t = BlindTask(
            "retry",
            "Retry job 'nightly-sync' 5 times",
            [
                Constraint(param="job", kind="contains", gold_value="nightly-sync"),
                Constraint(param="times", kind="range", min_val=5, max_val=5),
            ],
        )
        assert classify_task_coverage(t, ["job", "times"]).klass == FULL

    def test_without_schema_only_constraints_and_text_are_available(self) -> None:
        t = BlindTask("x", "Do the thing", [_enum("a", "1")])
        assert classify_task_coverage(t, []).klass == FULL


class TestSummaryAndWarning:
    def _tasks(self, n_selection_only: int, n_full: int) -> list[BlindTask]:
        return [BlindTask("zz_tool", f"plain task {i}") for i in range(n_selection_only)] + [
            BlindTask("zz_tool", f"other task {i}", [_enum("p", "v")]) for i in range(n_full)
        ]

    def test_counts_cover_all_three_classes(self) -> None:
        tasks = [
            BlindTask("zz_tool", "no checks here"),
            BlindTask("zz_tool", "some checks", [_enum("p", "v")]),
            BlindTask("zz_tool", "all checks", [_enum("p", "v"), _enum("q", "w")]),
        ]
        s = summarize_constraint_coverage(tasks, [_tool("zz_tool", ["p", "q"])])
        assert (s.count(SELECTION_ONLY), s.count(PARTIAL), s.count(FULL)) == (1, 1, 1)
        assert s.line() == ("constraint coverage over 3 tasks: 1 selection-only, 1 partial, 1 full")

    def test_more_than_half_selection_only_warns_but_never_blocks(self) -> None:
        findings = check_constraint_coverage(self._tasks(3, 2))
        assert [f.severity for f in findings] == ["warn"]
        assert "selection-only verdict" in findings[0].detail
        report = run_audit(self._tasks(3, 2))
        assert report.passed and any(f.check == "constraint_coverage" for f in report.warnings)

    def test_exactly_half_selection_only_does_not_warn(self) -> None:
        assert check_constraint_coverage(self._tasks(2, 2)) == []

    def test_label_flag_follows_the_threshold(self) -> None:
        assert summarize_constraint_coverage(self._tasks(3, 2)).verdict_is_selection_only
        assert not summarize_constraint_coverage(self._tasks(2, 2)).verdict_is_selection_only
        assert not summarize_constraint_coverage([]).verdict_is_selection_only


class TestOutputLabel:
    def _print(self, coverage_tasks: list[BlindTask]) -> str:
        from io import StringIO

        from rich.console import Console

        from agentgauge.harness import diff_from_trials

        trials = [TrialOutcome("t", "t", 1.0)] * 6 + [TrialOutcome("t", "u", 0.0)] * 6
        buf = StringIO()
        console = Console(file=buf, width=200, force_terminal=False)
        cli._print_diff_text(
            diff_from_trials(trials, trials),
            None,
            None,
            console,
            coverage=summarize_constraint_coverage(coverage_tasks),
        )
        return _flat(buf.getvalue())

    def test_selection_only_verdict_is_labelled(self) -> None:
        out = self._print([BlindTask("zz_tool", f"task {i}") for i in range(4)])
        assert "constraint coverage over 4 tasks: 4 selection-only, 0 partial, 0 full" in out
        assert "(selection-only):" in out

    def test_constrained_run_has_counts_but_no_label(self) -> None:
        out = self._print([BlindTask("zz_tool", f"task {i}", [_enum("p", "v")]) for i in range(4)])
        assert "0 selection-only" in out
        assert "(selection-only)" not in out


class TestInitScaffold:
    def test_scaffold_demonstrates_full_coverage(self, tmp_path: Path) -> None:
        assert CliRunner().invoke(app, ["init", "--out", str(tmp_path)]).exit_code == 0
        raw = json.loads((tmp_path / "agentgauge_tasks.json").read_text(encoding="utf-8"))
        tasks = [BlindTask.from_dict(d) for d in raw]
        tool = _tool(tasks[0].tool_name, ["project", "title", "priority"])
        assert summarize_constraint_coverage(tasks, [tool]).count(FULL) == len(tasks) == 1
        assert "selection-only" in raw[0]["note"]


class TestCommittedCorpusCounts:
    """evals/fixtures/constraint_coverage_corpora.json is produced by
    scripts/constraint_coverage_corpora.py (which introspects every fixture server, so the full
    `--check` is run by hand); the cheap parts are re-derived here."""

    FIXTURE = Path(__file__).parent.parent / "evals/fixtures/constraint_coverage_corpora.json"

    def test_class_counts_add_up_for_every_corpus_and_group(self) -> None:
        corpora = json.loads(self.FIXTURE.read_text(encoding="utf-8"))["corpora"]
        # "bundled_demo" is present only where agentgauge/demo exists (see tests/test_demo_coverage.py)
        assert set(corpora) - {"bundled_demo"} == {
            "argument_degradation_253",
            "predictive_validity_44_tool_sets",
        }
        for c in corpora.values():
            assert c["selection_only"] + c["partial"] + c["full"] == c["n_tasks"]
            groups = c.get("by_group", {})
            assert sum(g["n_tasks"] for g in groups.values()) in (0, c["n_tasks"])
        assert corpora["argument_degradation_253"]["n_tasks"] == 253
