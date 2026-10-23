"""The bundled demo must pass the repo's own constraint-coverage check (24 of 24 tasks full)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from agentgauge import cli
from agentgauge.audit import FULL, summarize_constraint_coverage
from agentgauge.cli import app
from agentgauge.demo import after_server, before_server

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
DEMO_DIR = Path(cli.__file__).parent / "demo"
FIXTURE = Path(__file__).parent.parent / "evals/fixtures/constraint_coverage_corpora.json"


def _flat(s: str) -> str:
    return " ".join(_ANSI.sub("", s).split())


def _tools(server: object) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(name=t["name"], inputSchema=t["inputSchema"])
        for t in server.TOOLS  # type: ignore[attr-defined]
    ]


class TestDemoCoverage:
    def test_every_demo_task_is_full_against_both_arms_schemas(self) -> None:
        tasks = cli._load_tasks_file(DEMO_DIR / "tasks.json")
        assert len(tasks) == 24
        for server in (before_server, after_server):
            summary = summarize_constraint_coverage(tasks, _tools(server))
            assert summary.count(FULL) == 24, [
                (t.tool_name, t.unconstrained) for t in summary.tasks if t.klass != FULL
            ]

    def test_demo_prints_counts_and_is_not_labelled_selection_only(self) -> None:
        out = _flat(CliRunner().invoke(app, ["demo"]).output)
        assert "constraint coverage over 24 tasks: 0 selection-only, 0 partial, 24 full" in out
        assert "(selection-only)" not in out

    def test_committed_corpus_entry_matches_a_fresh_run(self) -> None:
        corpora = json.loads(FIXTURE.read_text(encoding="utf-8"))["corpora"]
        tasks = cli._load_tasks_file(DEMO_DIR / "tasks.json")
        fresh = summarize_constraint_coverage(tasks, _tools(before_server)).as_dict()
        committed = corpora["bundled_demo"]
        assert {k: committed[k] for k in fresh} == fresh
        assert committed["full"] == committed["n_tasks"] == 24
