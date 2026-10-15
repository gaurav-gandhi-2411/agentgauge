"""First-run experience: bundled demo, clean errors, --mock refusal, init --out, workflow, help.

The LLM is always mocked here: no Ollama, no network, no paid calls. The only subprocesses are
the bundled stdio demo servers themselves (same precedent as test_scan_echo_server_subprocess).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
import yaml
from mcp.types import Tool
from typer.testing import CliRunner

import agentgauge.cli as cli
from agentgauge.audit import run_audit
from agentgauge.cli import app
from agentgauge.client import MCPClient, ServerInfo, ToolCallResult
from agentgauge.constraints import BlindTask
from agentgauge.demo import after_server, before_server
from agentgauge.harness import TrialOutcome, Verdict
from agentgauge.providers import OllamaProvider, ProviderUnreachableError

DEMO = Path(cli.__file__).parent / "demo"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(s: str) -> str:
    return _ANSI.sub("", s)


def _flat(s: str) -> str:
    """Collapse Rich's soft-wrapping so substrings can be asserted across line breaks."""
    return " ".join(_plain(s).split())


# ----------------------------------------------------------------------------- item 1: demo


class TestDemoAssets:
    def test_demo_command_replays_bundled_run_and_exits_zero(self) -> None:
        result = CliRunner().invoke(app, ["demo"])
        out = _flat(result.output)
        assert result.exit_code == 0, result.output
        assert "replaying 24 recorded gemma2:9b trials per arm" in out
        assert "INSUFFICIENT_SENSITIVITY" in out
        assert "What happened:" in out and "Why this verdict:" in out
        assert "replay mode -- no live cost to report" in out
        assert "Traceback" not in result.output

    def test_bundled_replay_is_what_the_demo_reports(self) -> None:
        before = [
            TrialOutcome.from_dict(d) for d in json.loads((DEMO / "replay_before.json").read_text())
        ]
        after = [
            TrialOutcome.from_dict(d) for d in json.loads((DEMO / "replay_after.json").read_text())
        ]
        tasks = json.loads((DEMO / "tasks.json").read_text())
        assert len(before) == len(after) == len(tasks) == 24
        # replay rows are in task order, so the recording is tied to this exact tasks file
        assert [t.task_tool_name for t in before] == [t["tool_name"] for t in tasks]
        assert [t.task_tool_name for t in after] == [t["tool_name"] for t in tasks]

    def test_explanation_follows_the_actual_verdict(self) -> None:
        from agentgauge.harness import diff_from_trials

        good = [TrialOutcome("t", "t", 1.0)] * 60 + [TrialOutcome("t", "u", 0.0)] * 60
        bad = [TrialOutcome("t", "u", 0.0)] * 120
        improved = diff_from_trials(bad, good, threshold=0.2)
        assert improved.verdict == Verdict.IMPROVEMENT
        assert "improvement" in cli._demo_explanation(improved, 120)[1]
        regressed = diff_from_trials(good, bad, threshold=0.2)
        assert regressed.verdict == Verdict.REGRESSION
        assert "worse" in cli._demo_explanation(regressed, 120)[1]
        same = diff_from_trials(good, good, threshold=0.2)
        assert same.verdict == Verdict.NO_CHANGE
        assert "does not clear" in cli._demo_explanation(same, 120)[1]

    def test_extract_copies_files_and_replay_diff_works_on_them(self, tmp_path: Path) -> None:
        dest = tmp_path / "nested" / "demo_files"
        result = CliRunner().invoke(app, ["demo", "--extract", str(dest)])
        assert result.exit_code == 0, result.output
        for name in cli._DEMO_FILES:
            assert (dest / name).is_file(), name
        # explicit-path replay (no positional server args) still works on the extracted files
        replay = CliRunner().invoke(
            app,
            [
                "diff",
                "--replay-before",
                str(dest / "replay_before.json"),
                "--replay-after",
                str(dest / "replay_after.json"),
            ],
        )
        assert replay.exit_code == 0, replay.output
        assert "INSUFFICIENT_SENSITIVITY" in replay.output

    def test_extract_never_overwrites(self, tmp_path: Path) -> None:
        (tmp_path / "tasks.json").write_text("mine", encoding="utf-8")
        result = CliRunner().invoke(app, ["demo", "--extract", str(tmp_path)])
        assert result.exit_code == 2
        assert "refusing to overwrite" in result.output and "tasks.json" in result.output
        assert (tmp_path / "tasks.json").read_text(encoding="utf-8") == "mine"

    def test_extract_into_a_file_path_is_a_clean_error(self, tmp_path: Path) -> None:
        target = tmp_path / "afile"
        target.write_text("x", encoding="utf-8")
        result = CliRunner().invoke(app, ["demo", "--extract", str(target)])
        assert result.exit_code == 2
        assert "cannot create directory" in result.output
        assert "Traceback" not in result.output

    def test_demo_tasks_pass_the_audit_against_both_servers(self) -> None:
        """Real stdio subprocesses: the bundled tasks must pass the same gate users hit."""
        tasks = cli._load_tasks_file(DEMO / "tasks.json")
        before = asyncio.run(cli._introspect_tools(str(DEMO / "before_server.py")))
        after = asyncio.run(cli._introspect_tools(str(DEMO / "after_server.py")))
        report = run_audit(tasks, before_tools=before, after_tools=after)
        assert report.passed, [f.detail for f in report.blocking]
        assert not report.warnings, [f.detail for f in report.warnings]
        # no tool-name leakage, every task has a constraint
        assert all(t.constraints for t in tasks)

    def test_servers_share_names_and_params_and_differ_in_descriptions(self) -> None:
        b = {t["name"]: t for t in before_server.TOOLS}
        a = {t["name"]: t for t in after_server.TOOLS}
        assert list(b) == list(a) and len(b) == 6
        for name in b:
            assert list(b[name]["inputSchema"]["properties"]) == list(
                a[name]["inputSchema"]["properties"]
            )
            assert b[name]["description"] != a[name]["description"]

    @pytest.mark.parametrize("server", [before_server, after_server])
    def test_server_handlers(self, server) -> None:  # type: ignore[no-untyped-def]
        tools = asyncio.run(server.list_tools())
        assert len(tools) == 6
        out = asyncio.run(server.call_tool("ticket_close", {"ticket_id": "1"}))
        assert "ticket_close" in out[0].text
        with pytest.raises(ValueError, match="Unknown tool"):
            asyncio.run(server.call_tool("nope", {}))


# ------------------------------------------------------------ item 2: clean errors, no traceback


def _no_spawn() -> tuple[AsyncMock, object]:
    spawn = AsyncMock(side_effect=AssertionError("a server subprocess was spawned"))
    return spawn, patch("agentgauge.cli.connect_stdio", new=spawn)


class TestMissingServerPath:
    @pytest.mark.parametrize(
        "argv",
        [
            ["diff", "nope_before.py", "nope_after.py", "--tasks", str(DEMO / "tasks.json")],
            ["eval", "nope.py"],
            ["lint", "nope.py"],
            ["scan", "nope.py", "--mock"],
        ],
    )
    def test_one_line_error_exit_2_no_spawn(self, argv: list[str]) -> None:
        spawn, ctx = _no_spawn()
        with ctx:
            result = CliRunner().invoke(app, argv)
        assert result.exit_code == 2, result.output
        assert re.search(r"Error: server script not found: nope\w*\.py", result.output)
        assert "Traceback" not in result.output
        assert "McpError" not in result.output
        spawn.assert_not_called()

    def test_directory_is_not_a_server(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(app, ["lint", str(tmp_path)])
        assert result.exit_code == 2
        assert "server path is not a file" in result.output

    def test_unreadable_script(self, tmp_path: Path) -> None:
        script = tmp_path / "s.py"
        script.write_text("x", encoding="utf-8")
        with patch("agentgauge.cli.os.access", return_value=False):
            result = CliRunner().invoke(app, ["lint", str(script)])
        assert result.exit_code == 2
        assert "server script is not readable" in result.output

    def test_missing_tasks_and_replay_files_are_clean(self, tmp_path: Path) -> None:
        r1 = CliRunner().invoke(
            app,
            [
                "diff",
                str(DEMO / "before_server.py"),
                str(DEMO / "after_server.py"),
                "--tasks",
                "x.json",
            ],
        )
        assert r1.exit_code == 2 and "tasks file not found: x.json" in r1.output
        r2 = CliRunner().invoke(
            app, ["diff", "--replay-before", "a.json", "--replay-after", "b.json"]
        )
        assert r2.exit_code == 2 and "replay file not found: a.json" in r2.output
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        r3 = CliRunner().invoke(
            app, ["diff", "--replay-before", str(bad), "--replay-after", str(bad)]
        )
        assert r3.exit_code == 2 and "cannot read replay file" in r3.output
        r4 = CliRunner().invoke(
            app,
            [
                "diff",
                str(DEMO / "before_server.py"),
                str(DEMO / "after_server.py"),
                "--tasks",
                str(bad),
            ],
        )
        assert r4.exit_code == 2 and "cannot read tasks file" in r4.output

    def test_live_diff_needs_both_server_paths(self) -> None:
        result = CliRunner().invoke(app, ["diff", "--tasks", str(DEMO / "tasks.json")])
        assert result.exit_code == 2
        assert "needs both <before> and <after>" in _flat(result.output)

    def test_url_targets_skip_the_path_check(self) -> None:
        # An http(s) target must reach the connect step, not be rejected as a missing file.
        connect = AsyncMock(side_effect=RuntimeError("reached connect_http"))
        with (
            patch("agentgauge.cli.connect_http", new=connect),
            pytest.raises(RuntimeError, match="reached connect_http"),
        ):
            asyncio.run(cli._connect("http://localhost:9/sse"))
        connect.assert_awaited_once()


class TestOllamaUnreachable:
    _ARGV = [
        "diff",
        str(DEMO / "before_server.py"),
        str(DEMO / "after_server.py"),
        "--tasks",
        str(DEMO / "tasks.json"),
    ]

    def test_preflight_failure_is_one_line_with_hints_and_spawns_nothing(self) -> None:
        spawn, ctx = _no_spawn()
        boom = AsyncMock(
            side_effect=ProviderUnreachableError("Cannot reach Ollama at http://localhost:11434.")
        )
        with ctx, patch.object(OllamaProvider, "ensure_reachable", new=boom):
            result = CliRunner().invoke(app, self._ARGV)
        out = _flat(result.output)
        assert result.exit_code == 2, result.output
        assert "Error: Cannot reach Ollama at http://localhost:11434." in out
        assert "agentgauge demo" in out and "--replay-before" in out and "--mock" in out
        assert "Traceback" not in result.output and "ConnectError" not in result.output
        spawn.assert_not_called()  # failed before any server was started

    def test_eval_live_path_is_also_preflighted(self) -> None:
        boom = AsyncMock(side_effect=ProviderUnreachableError("Cannot reach Ollama at x."))
        with patch.object(OllamaProvider, "ensure_reachable", new=boom):
            result = CliRunner().invoke(
                app,
                ["eval", str(DEMO / "before_server.py"), "--tasks", str(DEMO / "tasks.json")],
            )
        assert result.exit_code == 2 and "Cannot reach Ollama" in result.output

    def test_raw_connect_error_from_other_adapters_is_mapped(self) -> None:
        async def raising() -> None:
            raise httpx.ConnectError("refused")

        with pytest.raises(cli.typer.Exit) as exc:
            cli._run(raising())
        assert exc.value.exit_code == 2

    @respx.mock
    def test_ensure_reachable_ok(self) -> None:
        respx.get(f"{OllamaProvider.BASE_URL}/api/version").mock(
            return_value=httpx.Response(200, json={"version": "0.0.0"})
        )
        asyncio.run(OllamaProvider("m").ensure_reachable())

    @respx.mock
    @pytest.mark.parametrize(
        "effect",
        [httpx.ConnectError("refused"), httpx.ConnectTimeout("slow"), httpx.Response(500)],
    )
    def test_ensure_reachable_maps_failures(self, effect: object) -> None:
        route = respx.get(f"{OllamaProvider.BASE_URL}/api/version")
        if isinstance(effect, httpx.Response):
            route.mock(return_value=effect)
        else:
            route.mock(side_effect=effect)
        with pytest.raises(
            ProviderUnreachableError, match="Cannot reach Ollama at http://localhost"
        ):
            asyncio.run(OllamaProvider("m").ensure_reachable())

    @respx.mock
    def test_chat_connect_error_becomes_provider_unreachable(self) -> None:
        respx.post(f"{OllamaProvider.BASE_URL}/api/chat").mock(
            side_effect=httpx.ConnectError("refused")
        )
        from agentgauge.providers import Message

        with pytest.raises(ProviderUnreachableError):
            asyncio.run(OllamaProvider("m").chat([Message(role="user", content="hi")]))

    def test_preflight_skips_providers_without_a_probe(self) -> None:
        from agentgauge.providers import MockProvider

        asyncio.run(cli._preflight_provider(MockProvider()))  # must not raise


# ----------------------------------------------------------------- item 3: --mock refusal


def _client_with_tool(name: str) -> MCPClient:
    tool = Tool(
        name=name,
        description="d",
        inputSchema={"type": "object", "properties": {"p": {"type": "string"}}},
    )
    client = MCPClient(MagicMock())
    client.introspect = AsyncMock(return_value=ServerInfo(tools=[tool], resources=[], prompts=[]))
    client.call_tool = AsyncMock(return_value=ToolCallResult(success=True, content=[], error=None))
    return client


class TestMockRefusal:
    @staticmethod
    def _run(argv: list[str], tool: str, tmp_path: Path, tasks: list[dict]) -> tuple:  # type: ignore[type-arg]
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps(tasks), encoding="utf-8")
        client = _client_with_tool(tool)
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        with (
            patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(client, fake_ctx))),
            patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        ):
            result = CliRunner().invoke(app, [*argv, "--tasks", str(tasks_file), "--mock"])
        return result, client

    def test_placeholder_scaffold_with_mock_no_longer_prints_no_change(
        self, tmp_path: Path
    ) -> None:
        init = CliRunner().invoke(app, ["init", "--out", str(tmp_path)])
        assert init.exit_code == 0
        scaffold = json.loads((tmp_path / "agentgauge_tasks.json").read_text(encoding="utf-8"))
        script = str(DEMO / "before_server.py")
        client = _client_with_tool("echo")
        fake_ctx = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        with (
            patch("agentgauge.cli.connect_stdio", new=AsyncMock(return_value=(client, fake_ctx))),
            patch("agentgauge.cli.cleanup_connection", new=AsyncMock()),
        ):
            result = CliRunner().invoke(
                app,
                [
                    "diff",
                    script,
                    script,
                    "--tasks",
                    str(tmp_path / "agentgauge_tasks.json"),
                    "--mock",
                ],
            )
        assert len(scaffold) == 1  # the 1-task placeholder this regression is about
        assert result.exit_code == 2, result.output
        assert "--mock cannot produce a verdict" in _flat(result.output)
        assert "NO_CHANGE" not in result.output
        client.call_tool.assert_not_called()

    def test_valid_multi_task_file_is_refused_not_audit_blocked(self, tmp_path: Path) -> None:
        tasks = [
            {"tool_name": "echo", "description": f"say thing number {i}", "constraints": []}
            for i in range(3)
        ]
        argv = ["diff", str(DEMO / "before_server.py"), str(DEMO / "after_server.py")]
        result, client = self._run(argv, "echo", tmp_path, tasks)
        out = _flat(result.output)
        assert result.exit_code == 2
        assert "--mock cannot produce a verdict" in out
        assert "3 task(s) x 1 trial(s)" in out
        assert (
            "degenerate_metrics" in out
        )  # explains WHY (the audit gate), not just that it refuses
        client.call_tool.assert_not_called()

    def test_eval_mock_is_refused_too(self, tmp_path: Path) -> None:
        tasks = [{"tool_name": "echo", "description": "say it", "constraints": []}]
        result, client = self._run(
            ["eval", str(DEMO / "before_server.py")], "echo", tmp_path, tasks
        )
        assert result.exit_code == 2
        assert "--mock cannot produce a verdict" in _flat(result.output)
        assert "joint success rate" not in result.output
        client.call_tool.assert_not_called()

    def test_json_mode_refusal_is_machine_readable(self, tmp_path: Path) -> None:
        tasks = [{"tool_name": "echo", "description": "say it", "constraints": []}]
        script = str(DEMO / "before_server.py")
        result, _ = self._run(["diff", script, script, "--json"], "echo", tmp_path, tasks)
        payload = json.loads(result.output)
        assert result.exit_code == 2 and payload["mock_refused"] is True

    def test_schema_audit_still_runs_first_under_mock(self, tmp_path: Path) -> None:
        """--mock stays useful as a free dry-run of the tasks file against the schemas."""
        tasks = [
            {
                "tool_name": "echo",
                "description": "say it",
                "constraints": [{"param": "missing", "kind": "contains", "gold_value": "x"}],
            }
        ]
        script = str(DEMO / "before_server.py")
        result, _ = self._run(["diff", script, script], "echo", tmp_path, tasks)
        assert result.exit_code == 2
        assert "scoring_reference_consistency" in result.output
        assert "--mock cannot produce a verdict" not in result.output


# ---------------------------------------------------------------------------- item 4: init --out


class TestInitOut:
    def test_creates_nested_nonexistent_directory(self, tmp_path: Path) -> None:
        out = tmp_path / "a" / "b" / "c"
        result = CliRunner().invoke(app, ["init", "--out", str(out)])
        assert result.exit_code == 0, result.output
        assert (out / "agentgauge_tasks.json").is_file()
        assert (out / ".github" / "workflows" / "agentgauge.yml").is_file()

    def test_existing_files_are_not_overwritten(self, tmp_path: Path) -> None:
        (tmp_path / "agentgauge_tasks.json").write_text("[]", encoding="utf-8")
        result = CliRunner().invoke(app, ["init", "--out", str(tmp_path)])
        assert result.exit_code == 0
        assert "already exists" in result.output
        assert (tmp_path / "agentgauge_tasks.json").read_text(encoding="utf-8") == "[]"

    def test_out_that_is_a_file_is_a_clean_error(self, tmp_path: Path) -> None:
        target = tmp_path / "iamafile"
        target.write_text("x", encoding="utf-8")
        result = CliRunner().invoke(app, ["init", "--out", str(target)])
        assert result.exit_code == 2
        assert "Error: cannot create output directory" in _flat(result.output)
        assert "Traceback" not in result.output

    def test_unwritable_scaffold_is_a_clean_error(self, tmp_path: Path) -> None:
        with patch.object(Path, "write_text", side_effect=PermissionError(13, "denied")):
            result = CliRunner().invoke(app, ["init", "--out", str(tmp_path / "o")])
        assert result.exit_code == 2
        assert "cannot write scaffold files" in _flat(result.output)


# ------------------------------------------------------------------- item 5: workflow structure


class TestScaffoldedWorkflow:
    @staticmethod
    def _load(tmp_path: Path) -> tuple[str, dict]:  # type: ignore[type-arg]
        CliRunner().invoke(app, ["init", "--out", str(tmp_path)])
        text = (tmp_path / ".github" / "workflows" / "agentgauge.yml").read_text(encoding="utf-8")
        return text, yaml.safe_load(text)

    def test_states_mode_and_how_to_switch_at_the_top(self, tmp_path: Path) -> None:
        text, _ = self._load(tmp_path)
        header = text.split("name: agentgauge")[0]
        assert header.startswith("#")
        assert "LINT-ONLY BY DEFAULT" in header
        assert "AGENTGAUGE_LIVE_DIFF = true" in header

    def test_structure_lint_active_live_diff_opt_in(self, tmp_path: Path) -> None:
        _, doc = self._load(tmp_path)
        triggers = doc.get("on", doc.get(True))  # YAML 1.1 parses the bare key `on` as True
        assert list(triggers) == ["pull_request"]
        assert doc["permissions"] == {"contents": "read"}
        assert set(doc["jobs"]) == {"lint", "live-diff"}
        lint, live = doc["jobs"]["lint"], doc["jobs"]["live-diff"]
        assert "if" not in lint
        assert live["if"] == "${{ vars.AGENTGAUGE_LIVE_DIFF == 'true' }}"
        assert lint["runs-on"] == live["runs-on"] == "ubuntu-latest"
        assert live["timeout-minutes"] == 90

    def test_lint_job_needs_no_ollama_and_live_job_installs_it(self, tmp_path: Path) -> None:
        _, doc = self._load(tmp_path)
        lint_blob = json.dumps(doc["jobs"]["lint"]).lower()
        live_blob = json.dumps(doc["jobs"]["live-diff"])
        assert "ollama" not in lint_blob and "--tasks" not in lint_blob
        assert "ollama.com/install.sh" in live_blob and "ollama pull" in live_blob
        assert "agentgauge diff" in live_blob

    def test_every_step_is_runnable_and_commands_exist(self, tmp_path: Path) -> None:
        _, doc = self._load(tmp_path)
        known = {c.name or c.callback.__name__ for c in cli.app.registered_commands}
        for job in doc["jobs"].values():
            for step in job["steps"]:
                assert ("uses" in step) != ("run" in step), step
                for m in re.finditer(r"agentgauge (\w+)", step.get("run", "")):
                    assert m.group(1) in known | {"harness"}, m.group(0)
        # shell steps that pipe into tee must use bash (pipefail) or the exit code is lost
        for job in doc["jobs"].values():
            for step in job["steps"]:
                if "| tee" in step.get("run", ""):
                    assert step.get("shell") == "bash", step


# ----------------------------------------------------------------------------- item 6: help


class TestHelpListing:
    def test_legacy_commands_are_labelled_and_attribute_is_hidden(self) -> None:
        result = CliRunner().invoke(app, ["--help"])
        out = _plain(result.output)
        assert result.exit_code == 0
        for name in ("scan", "fix", "ci", "try"):
            line = next(ln for ln in out.splitlines() if re.search(rf"│\s*{name}\s", ln))
            assert "(legacy)" in line, line
        for name in ("diff", "eval", "lint", "init", "demo"):
            line = next(ln for ln in out.splitlines() if re.search(rf"│\s*{name}\s", ln))
            assert "(legacy)" not in line, line
        assert "attribute" not in out

    def test_attribute_still_gated_and_runnable(self) -> None:
        refused = CliRunner().invoke(app, ["attribute"])
        assert refused.exit_code == 1
        assert "--experimental" in _plain(refused.output)
        ok = CliRunner().invoke(app, ["attribute", "--experimental"])
        assert ok.exit_code == 0 and "Experimental mode acknowledged" in _plain(ok.output)


def test_blindtask_loader_roundtrip_for_demo_tasks() -> None:
    tasks = cli._load_tasks_file(DEMO / "tasks.json")
    assert all(isinstance(t, BlindTask) for t in tasks) and len(tasks) == 24


def test_audit_block_message_keeps_the_arm_label_rich_would_treat_as_markup() -> None:
    """`[after]` in an audit detail used to be swallowed as Rich markup, hiding which arm tripped."""
    from io import StringIO

    from rich.console import Console

    from agentgauge.audit import AuditFinding, AuditReport
    from agentgauge.cli import _print_audit_report

    finding = AuditFinding(
        check="degenerate_metrics", severity="block", detail="[after] every one of 24 trials"
    )
    buf = StringIO()
    _print_audit_report(AuditReport(findings=[finding]), Console(file=buf, force_terminal=False))
    assert "[after] every one of 24 trials" in buf.getvalue()
