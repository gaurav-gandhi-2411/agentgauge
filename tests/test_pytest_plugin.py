"""The agentgauge pytest plugin, driven end to end through `pytester`.

One case per row of the verdict-mapping table. No model and no network: replays are the bundled
demo files and small synthetic ones; the only subprocesses are the bundled stdio demo servers
(introspection only, to hash their tool schemas for the staleness check).
"""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Any

import pytest

import agentgauge.pytest_plugin as plugin
from agentgauge.harness import TrialOutcome
from agentgauge.replay import save_replay

pytest_plugins = ["pytester"]

DEMO = Path(plugin.__file__).parent / "demo"
BEFORE_SERVER = str(DEMO / "before_server.py")
# Load by module name and block the entry-point name, so these tests behave the same whether or
# not the package metadata (and so the pytest11 autoload) is installed in this environment.
PLUGIN_ARGS = ("-p", "no:agentgauge", "-p", "agentgauge.pytest_plugin", "-rs")


def _arm(n: int, k: int, tools: int = 4) -> list[dict[str, Any]]:
    """n trials, the first k fully successful."""
    return [
        {
            "task_tool_name": f"t{i % tools}",
            "selected_tool": f"t{i % tools}" if i < k else "other",
            "constraint_satisfaction": 1.0 if i < k else 0.0,
        }
        for i in range(n)
    ]


def _write(path: Path, trials: list[dict[str, Any]]) -> str:
    path.write_text(json.dumps(trials), encoding="utf-8")
    return str(path)


def _body(before: str, after: str, extra: str = "", call_kwargs: str = "") -> str:
    return f"""
from agentgauge.pytest_plugin import assert_no_regression

def test_gate(agentgauge_diff):
    result = agentgauge_diff(replay_before={before!r}, replay_after={after!r}{call_kwargs})
    {extra}
    assert_no_regression(result)
"""


def _run(pytester: pytest.Pytester, source: str, *args: str) -> pytest.RunResult:
    pytester.makepyfile(test_gate=source)
    return pytester.runpytest(*PLUGIN_ARGS, *args)


@pytest.fixture
def pairs(tmp_path: Path) -> dict[str, tuple[str, str]]:
    """Synthetic (before, after) replay paths keyed by the verdict they produce."""
    spec = {
        "regression": (_arm(1000, 900), _arm(1000, 500)),
        "improvement": (_arm(1000, 500), _arm(1000, 900)),
        "no_change": (_arm(1000, 600), _arm(1000, 600)),
        "insufficient_sensitivity": (_arm(20, 10), _arm(20, 14)),
        "ceiling": (_arm(200, 200), _arm(200, 200)),
        "floor": (_arm(200, 0), _arm(200, 0)),
    }
    return {
        name: (_write(tmp_path / f"{name}_b.json", b), _write(tmp_path / f"{name}_a.json", a))
        for name, (b, a) in spec.items()
    }


class TestVerdictMapping:
    def test_regression_fails(self, pytester: pytest.Pytester, pairs: Any) -> None:
        r = _run(pytester, _body(*pairs["regression"]))
        r.assert_outcomes(failed=1)
        r.stdout.fnmatch_lines(["*agentgauge regression*"])

    @pytest.mark.parametrize("verdict", ["improvement", "no_change"])
    def test_improvement_and_no_change_pass(
        self, pytester: pytest.Pytester, pairs: Any, verdict: str
    ) -> None:
        extra = f"assert result.verdict == {verdict!r}"
        _run(pytester, _body(*pairs[verdict], extra=extra)).assert_outcomes(passed=1)

    def test_insufficient_sensitivity_skips_with_mde_message_on_demo_replays(
        self, pytester: pytest.Pytester
    ) -> None:
        src = _body(str(DEMO / "replay_before.json"), str(DEMO / "replay_after.json"))
        r = _run(pytester, src)
        r.assert_outcomes(skipped=1)
        r.stdout.fnmatch_lines(["*SKIPPED*insufficient_sensitivity*not have enough trials*"])
        r.stdout.fnmatch_lines(["agentgauge: 1 inconclusive verdict(s) skipped, not passed*"])

    def test_insufficient_sensitivity_fails_when_inconclusive_is_fail(
        self, pytester: pytest.Pytester
    ) -> None:
        src = _body(str(DEMO / "replay_before.json"), str(DEMO / "replay_after.json"))
        r = _run(pytester, src, "--agentgauge-inconclusive=fail")
        r.assert_outcomes(failed=1)
        r.stdout.fnmatch_lines(["*--agentgauge-inconclusive=fail*"])

    @pytest.mark.parametrize("verdict", ["ceiling", "floor"])
    def test_ceiling_and_floor_skip_with_reason(
        self, pytester: pytest.Pytester, pairs: Any, verdict: str
    ) -> None:
        r = _run(pytester, _body(*pairs[verdict]))
        r.assert_outcomes(skipped=1)
        r.stdout.fnmatch_lines([f"*SKIPPED*agentgauge {verdict}*cannot discriminate*"])

    @pytest.mark.parametrize("verdict", ["ceiling", "floor"])
    def test_ceiling_and_floor_fail_when_inconclusive_is_fail(
        self, pytester: pytest.Pytester, pairs: Any, verdict: str
    ) -> None:
        r = _run(pytester, _body(*pairs[verdict]), "--agentgauge-inconclusive=fail")
        r.assert_outcomes(failed=1)

    def test_per_call_override_beats_the_option(
        self, pytester: pytest.Pytester, pairs: Any
    ) -> None:
        src = _body(*pairs["ceiling"]).replace(
            "assert_no_regression(result)", "assert_no_regression(result, inconclusive='fail')"
        )
        _run(pytester, src).assert_outcomes(failed=1)

    def test_result_exposes_verdict_ci_and_decomposed_rates(
        self, pytester: pytest.Pytester, pairs: Any
    ) -> None:
        extra = (
            "assert result.verdict == 'improvement' and result.delta > 0.3\n"
            "    assert result.ci_lo <= result.delta <= result.ci_hi and result.message\n"
            "    assert result.before.joint_success_rate < result.after.joint_success_rate"
        )
        _run(pytester, _body(*pairs["improvement"], extra=extra)).assert_outcomes(passed=1)


class TestBrokenMeasurementNeverSkips:
    def test_blocking_audit_finding_fails(self, pytester: pytest.Pytester, tmp_path: Path) -> None:
        # Every trial scores a fixed non-extreme 0.5: the "constant scoring function" defect.
        const = [
            {
                "task_tool_name": f"t{i % 4}",
                "selected_tool": f"t{i % 4}",
                "constraint_satisfaction": 0.5,
            }
            for i in range(20)
        ]
        p = _write(tmp_path / "const.json", const)
        r = _run(pytester, _body(p, p))
        r.assert_outcomes(failed=1)
        r.stdout.fnmatch_lines(["*audit blocked the measurement*degenerate_metrics*"])

    def test_missing_replay_file_fails(self, pytester: pytest.Pytester, tmp_path: Path) -> None:
        r = _run(pytester, _body(str(tmp_path / "nope.json"), str(tmp_path / "nope2.json")))
        r.assert_outcomes(failed=1)
        r.stdout.fnmatch_lines(["*replay file not found*"])

    def test_unreachable_server_fails(
        self, pytester: pytest.Pytester, pairs: Any, tmp_path: Path
    ) -> None:
        # v1 replays so the staleness check actually needs the server.
        b, a = pairs["improvement"]
        v1 = []
        for src, name in ((b, "b"), (a, "a")):
            out = tmp_path / f"v1_{name}.json"
            trials = [TrialOutcome.from_dict(d) for d in json.loads(Path(src).read_text())]
            save_replay(out, trials, model="m", seed=42, trials_per_task=1, target="s.py",
                        tools_sha="0" * 64, tasks_sha=None)  # fmt: skip
            v1.append(str(out))
        kw = f", before_server={str(tmp_path / 'missing.py')!r}, after_server={BEFORE_SERVER!r}"
        r = _run(pytester, _body(*v1, call_kwargs=kw))
        r.assert_outcomes(failed=1)
        r.stdout.fnmatch_lines(["*cannot introspect before server*"])

    def test_stale_replay_fails_and_fresh_replay_passes(
        self, pytester: pytest.Pytester, pairs: Any, tmp_path: Path
    ) -> None:
        b, a = pairs["improvement"]
        live_sha = plugin.server_tools_sha(BEFORE_SERVER)

        def v1(src: str, name: str, sha: str) -> str:
            out = tmp_path / f"v1_{name}.json"
            trials = [TrialOutcome.from_dict(d) for d in json.loads(Path(src).read_text())]
            save_replay(out, trials, model="m", seed=42, trials_per_task=1, target="s.py",
                        tools_sha=sha, tasks_sha=None)  # fmt: skip
            return str(out)

        kw = f", before_server={BEFORE_SERVER!r}, after_server={BEFORE_SERVER!r}"
        stale = _body(v1(b, "b_stale", "0" * 64), v1(a, "a_fresh", live_sha), call_kwargs=kw)
        r = _run(pytester, stale)
        r.assert_outcomes(failed=1)
        r.stdout.fnmatch_lines(["*before replay is stale*tool schema changed*"])
        fresh = _body(v1(b, "b_ok", live_sha), v1(a, "a_ok", live_sha), call_kwargs=kw)
        _run(pytester, fresh).assert_outcomes(passed=1)

    def test_legacy_replay_with_server_is_noted_not_failed(
        self, pytester: pytest.Pytester, pairs: Any
    ) -> None:
        b, a = pairs["improvement"]
        kw = f", before_server={BEFORE_SERVER!r}, after_server={BEFORE_SERVER!r}"
        extra = "assert any('legacy' in n for n in result.notes)"
        _run(pytester, _body(b, a, extra=extra, call_kwargs=kw)).assert_outcomes(passed=1)

    def test_one_server_without_the_other_fails(
        self, pytester: pytest.Pytester, pairs: Any
    ) -> None:
        kw = f", before_server={BEFORE_SERVER!r}"
        r = _run(pytester, _body(*pairs["improvement"], call_kwargs=kw))
        r.assert_outcomes(failed=1)


class TestLiveIsOffByDefault:
    SRC = """
def test_live(agentgauge_diff):
    agentgauge_diff(live=True)
"""

    def test_live_request_without_flag_skips_and_calls_no_model(
        self, pytester: pytest.Pytester
    ) -> None:
        r = _run(pytester, self.SRC)
        r.assert_outcomes(skipped=1)
        r.stdout.fnmatch_lines(["*--agentgauge-live is not set*"])

    def test_live_flag_does_not_silently_pass(self, pytester: pytest.Pytester) -> None:
        r = _run(pytester, self.SRC, "--agentgauge-live")
        r.assert_outcomes(failed=1)
        r.stdout.fnmatch_lines(["*live runs are not implemented*"])


class TestPluginHygiene:
    def test_empty_project_collects_cleanly(self, pytester: pytest.Pytester) -> None:
        r = pytester.runpytest(*PLUGIN_ARGS, "--collect-only", "-q")
        assert r.ret == 5  # pytest's "no tests collected", not a plugin error
        assert "error" not in r.stdout.str().lower()

    def test_marker_is_registered_under_strict_markers(self, pytester: pytest.Pytester) -> None:
        pytester.makepyfile(
            test_m="""
import pytest

@pytest.mark.agentgauge
def test_marked():
    pass
"""
        )
        r = pytester.runpytest(*PLUGIN_ARGS, "--strict-markers")
        r.assert_outcomes(passed=1)
        listing = pytester.runpytest(*PLUGIN_ARGS, "--markers")
        listing.stdout.fnmatch_lines(["@pytest.mark.agentgauge: *"])

    def test_options_have_documented_defaults(self, pytester: pytest.Pytester) -> None:
        pytester.makepyfile(
            test_o="""
def test_defaults(pytestconfig):
    assert pytestconfig.getoption("--agentgauge-inconclusive") == "skip"
    assert pytestconfig.getoption("--agentgauge-live") is False
"""
        )
        pytester.runpytest(*PLUGIN_ARGS).assert_outcomes(passed=1)

    def test_invalid_inconclusive_value_is_rejected(self, pytester: pytest.Pytester) -> None:
        r = pytester.runpytest(*PLUGIN_ARGS, "--agentgauge-inconclusive=pass")
        assert r.ret != 0

    def test_importing_the_plugin_pulls_in_no_heavy_modules(self) -> None:
        import subprocess
        import sys

        code = (
            "import sys, agentgauge.pytest_plugin; "
            "bad = [m for m in ('numpy', 'mcp', 'agentgauge.harness', 'agentgauge.client', "
            "'agentgauge.audit') if m in sys.modules]; "
            "print(bad); sys.exit(1 if bad else 0)"
        )
        proc = subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_entry_point_is_declared(self) -> None:
        eps = importlib.metadata.entry_points(group="pytest11")
        mine = [ep for ep in eps if ep.name == "agentgauge"]
        if not mine:
            pytest.skip("package metadata predates the entry point; re-run `uv sync`")
        assert mine[0].value == "agentgauge.pytest_plugin"
