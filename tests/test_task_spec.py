"""Tests for agentgauge.task_spec (opt-in `lint --tasks`): no LLM, no network."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import Tool
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.client import ServerInfo
from agentgauge.constraints import BlindTask
from agentgauge.linter import Severity
from agentgauge.task_spec import (
    ALL_FINDING_CHECKS,
    CHECK_DESC_DUP,
    CHECK_FREE_TEXT,
    CHECK_NAME_DUP,
    CHECK_UNKNOWN_TOOL,
    CHECK_UNSTATED,
    CHECK_WRAPPER,
    check_task_file,
    check_task_specification,
    stated_value_spans,
)


def tool(name: str, props: dict[str, Any], required: list[str], desc: str = "") -> Any:
    return SimpleNamespace(
        name=name,
        description=desc,
        inputSchema={"type": "object", "properties": props, "required": required},
    )


def checks(task: BlindTask, tools: list[Any]) -> set[str]:
    return {v.check for v in check_task_specification(task, tools)}


class TestStatedValueSpans:
    def test_quoted_digit_url_and_capitalised_runs(self) -> None:
        spans = stated_value_spans(
            "Find 'red shoes' in New York for order 4417 at https://x.io/a, ask bob@x.io"
        )
        low = {s.lower() for s in spans}
        assert {"red shoes", "new york", "4417", "https://x.io/a", "bob@x.io"} <= low

    def test_sentence_initial_capital_is_not_a_value(self) -> None:
        assert stated_value_spans("Create an issue. Please hurry.") == []

    def test_contained_span_counted_once(self) -> None:
        assert len(stated_value_spans("Open 'order 4417'")) == 1


class TestCleanTask:
    def test_fully_specified_task_has_no_findings(self) -> None:
        t = tool("get_order", {"order_id": {"type": "string"}}, ["order_id"])
        task = BlindTask("get_order", "Show me order 'A-4417'.")
        assert check_task_specification(task, [t]) == []


class TestUnstatedRequiredArg:
    def test_fires_when_no_value_is_stated(self) -> None:
        t = tool("search", {"query": {"type": "string"}}, ["query"])
        assert CHECK_UNSTATED in checks(BlindTask("search", "Look something up for me."), [t])

    def test_boundary_one_value_for_one_param_passes(self) -> None:
        t = tool("search", {"query": {"type": "integer"}}, ["query"])
        assert CHECK_UNSTATED not in checks(BlindTask("search", "Look up item 12."), [t])

    def test_boundary_two_params_one_value_fires(self) -> None:
        props = {"a": {"type": "integer"}, "b": {"type": "integer"}}
        t = tool("add", props, ["a", "b"])
        assert CHECK_UNSTATED in checks(BlindTask("add", "Add up 12 and more."), [t])

    def test_enum_satisfied_only_by_an_enum_value(self) -> None:
        t = tool("sort", {"order": {"enum": ["asc", "desc"]}}, ["order"])
        assert CHECK_UNSTATED in checks(BlindTask("sort", "Sort the list."), [t])
        assert CHECK_UNSTATED not in checks(BlindTask("sort", "Sort the list in desc order."), [t])

    def test_boolean_and_optional_params_are_ignored(self) -> None:
        t = tool("x", {"flag": {"type": "boolean"}, "n": {"type": "integer"}}, ["flag"])
        assert checks(BlindTask("x", "Do it."), [t]) == set()


class TestFreeTextRequiredArg:
    def test_fires_without_quoted_value(self) -> None:
        t = tool("note", {"text": {"type": "string"}}, ["text"])
        assert CHECK_FREE_TEXT in checks(BlindTask("note", "Save a note saying Hello."), [t])

    def test_quoted_value_silences_it(self) -> None:
        t = tool("note", {"text": {"type": "string"}}, ["text"])
        assert CHECK_FREE_TEXT not in checks(BlindTask("note", 'Save a note: "hello there".'), [t])

    def test_constrained_strings_are_not_free_text(self) -> None:
        for schema in ({"type": "string", "format": "date"}, {"type": "string", "pattern": "^a"}):
            t = tool("d", {"v": schema}, ["v"])
            assert CHECK_FREE_TEXT not in checks(BlindTask("d", "Do it."), [t])


class TestWrapperObjectArg:
    items = {
        "type": "object",
        "properties": {"title": {"type": "string"}, "due_date": {"type": "string"}},
        "required": ["title", "due_date"],
    }

    def test_array_of_objects_with_unnamed_inner_field_fires(self) -> None:
        t = tool("add", {"todos": {"type": "array", "items": self.items}}, ["todos"])
        assert CHECK_WRAPPER in checks(BlindTask("add", "Add a todo called 'Pay rent'."), [t])

    def test_inner_fields_named_in_text_pass(self) -> None:
        t = tool("add", {"todos": {"type": "array", "items": self.items}}, ["todos"])
        task = BlindTask("add", "Add a todo with title 'Pay rent' and due date 2026-01-02.")
        assert CHECK_WRAPPER not in checks(task, [t])

    def test_opaque_object_fires(self) -> None:
        t = tool("cfg", {"config": {"type": "object"}}, ["config"])
        assert CHECK_WRAPPER in checks(BlindTask("cfg", "Configure it with 'fast'."), [t])


class TestNearDuplicates:
    def test_name_duplicate(self) -> None:
        tools = [tool("get_user", {}, []), tool("get_users", {}, []), tool("delete_file", {}, [])]
        assert CHECK_NAME_DUP in checks(BlindTask("get_user", "Fetch the person."), tools)
        assert CHECK_NAME_DUP not in checks(BlindTask("delete_file", "Remove it."), tools)

    def test_description_overlap_threshold_boundary(self) -> None:
        # 4 shared of 8 distinct content tokens = 0.5 -> fires; 3 of 9 -> does not.
        a = tool("a1", {}, [], "alpha bravo charlie delta echo foxtrot")
        b = tool("b2", {}, [], "alpha bravo charlie delta golf hotel")
        c = tool("c3", {}, [], "alpha bravo charlie india juliet kilo lima")
        assert CHECK_DESC_DUP in checks(BlindTask("a1", "x"), [a, b])
        assert CHECK_DESC_DUP not in checks(BlindTask("a1", "x"), [a, c])

    def test_short_descriptions_never_match(self) -> None:
        a, b = tool("a1", {}, [], "read file"), tool("b2", {}, [], "read file")
        assert CHECK_DESC_DUP not in checks(BlindTask("a1", "x"), [a, b])


class TestSeverityAndRobustness:
    def test_all_findings_are_advisory(self) -> None:
        t = tool("search", {"query": {"type": "string"}}, ["query"], "alpha bravo charlie delta")
        for v in check_task_specification(BlindTask("search", "Look it up."), [t]):
            assert v.severity == Severity.ADVISORY
            assert v.check in ALL_FINDING_CHECKS

    def test_unknown_target_tool_is_info_not_a_finding(self) -> None:
        out = check_task_specification(BlindTask("missing", "x"), [tool("a", {}, [])])
        assert [(v.check, v.severity) for v in out] == [(CHECK_UNKNOWN_TOOL, Severity.INFO)]

    def test_odd_schemas_do_not_raise(self) -> None:
        odd = SimpleNamespace(name="t", description=None, inputSchema=None)
        weird = tool(
            "w", {"p": {"anyOf": [{"type": "object"}, {"type": "null"}]}, "q": 3}, ["p", "q", "z"]
        )
        check_task_specification(BlindTask("t", "x"), [odd])
        check_task_specification(BlindTask("w", "x"), [weird])

    def test_report_counts_tasks_flagged(self) -> None:
        t = tool("search", {"query": {"type": "string"}}, ["query"])
        rep = check_task_file(
            [BlindTask("search", "Look it up."), BlindTask("search", "Find 'cats'.")], [t]
        )
        assert (rep.n_tasks, rep.n_tasks_flagged) == (2, 1)
        assert rep.by_task[0][0] == 0


class TestCli:
    def _invoke(self, tmp_path: Path, args: list[str], tool_name: str = "lookup") -> Any:
        info = ServerInfo(
            tools=[
                Tool(
                    name=tool_name,
                    description="Look up a thing",
                    inputSchema={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                )
            ],
            resources=[],
            prompts=[],
        )
        client = MagicMock()
        client.introspect = AsyncMock(return_value=info)
        tasks = tmp_path / "t.json"
        tasks.write_text(
            json.dumps([{"tool_name": tool_name, "description": "[bold red]Look[/] it up"}]),
            encoding="utf-8",
        )
        with (
            patch(
                "agentgauge.cli.connect_stdio",
                new=AsyncMock(return_value=(client, (MagicMock(),) * 4)),
            ),
            patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        ):
            return CliRunner().invoke(app, ["lint", "srv.py", *args, "--tasks", str(tasks)])

    def test_json_output_is_opt_in_and_never_fails_the_run(self, tmp_path: Path) -> None:
        res = self._invoke(tmp_path, ["--json"])
        assert res.exit_code == 0, res.output
        spec = json.loads(res.output)["task_specification"]
        assert spec["n_tasks"] == 1 and spec["findings"]

    def test_hostile_markup_in_tool_name_is_printed_literally(self, tmp_path: Path) -> None:
        res = self._invoke(tmp_path, [], tool_name="[red]evil[/red]")
        assert res.exit_code == 0, res.output
        assert "[red]evil[/red]" in res.output

    def test_default_lint_has_no_task_specification_key(self) -> None:
        info = ServerInfo(tools=[], resources=[], prompts=[])
        client = MagicMock()
        client.introspect = AsyncMock(return_value=info)
        with (
            patch(
                "agentgauge.cli.connect_stdio",
                new=AsyncMock(return_value=(client, (MagicMock(),) * 4)),
            ),
            patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        ):
            res = CliRunner().invoke(app, ["lint", "srv.py", "--json"])
        assert "task_specification" not in json.loads(res.output)
