"""CLI side of replay files: --save-before/--save-after/--save, staleness check, flag conflicts.

The LLM is always mocked: the live collection step (`_collect_trials`) is replaced by a stub that
returns the bundled demo trials, and the provider is a stub. The only subprocesses are the bundled
stdio demo servers (introspection only -- no model is involved in hashing their tool schemas).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

import agentgauge.cli as cli
from agentgauge.cli import TrialCollectionStats, app
from agentgauge.harness import TrialOutcome
from agentgauge.providers import MockProvider

DEMO = Path(cli.__file__).parent / "demo"
BEFORE, AFTER, TASKS = (
    str(DEMO / n) for n in ("before_server.py", "after_server.py", "tasks.json")
)
STATS = TrialCollectionStats("stub:model-x", 0.1, None, None, None)


def _demo_trials(arm: str) -> list[TrialOutcome]:
    raw = json.loads((DEMO / f"replay_{arm}.json").read_text(encoding="utf-8"))
    return [TrialOutcome.from_dict(d) for d in raw]


def _fake_collect(target: str, *a: object, **k: object) -> tuple[list[TrialOutcome], object]:
    return _demo_trials("before" if target == BEFORE else "after"), STATS


def _live(*args: str) -> object:
    """Run a LIVE command with the model backend and trial collection stubbed out."""
    with (
        patch("agentgauge.cli._collect_trials", new=AsyncMock(side_effect=_fake_collect)),
        patch("agentgauge.cli._resolve_provider", return_value=(MockProvider(), "stub")),
    ):
        return CliRunner().invoke(app, list(args))


@pytest.fixture(scope="module")
def recorded(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One v1 before/after pair recorded through the real `diff --save-*` path."""
    d = tmp_path_factory.mktemp("rec")
    r = _live(
        "diff", BEFORE, AFTER, "--tasks", TASKS,
        "--save-before", str(d / "b.json"), "--save-after", str(d / "a.json"),
    )  # fmt: skip
    assert r.exit_code == 0, r.output  # type: ignore[attr-defined]
    return {"b": d / "b.json", "a": d / "a.json", "dir": d}


def _verdict(output: str) -> str:
    return "INSUFFICIENT_SENSITIVITY" if "INSUFFICIENT_SENSITIVITY" in output else output[-200:]


class TestSave:
    def test_diff_save_writes_v1_with_provenance(self, recorded: dict[str, Path]) -> None:
        raw = json.loads(recorded["b"].read_text(encoding="utf-8"))
        assert raw["format"] == "agentgauge-replay" and raw["format_version"] == 1
        assert raw["model"] == "stub:model-x" and raw["seed"] == 42 and raw["trials_per_task"] == 1
        assert raw["server"]["target"] == BEFORE and len(raw["server"]["tools_sha256"]) == 64
        assert len(raw["tasks_sha256"]) == 64 and len(raw["trials"]) == 24
        other = json.loads(recorded["a"].read_text(encoding="utf-8"))
        assert other["server"]["tools_sha256"] != raw["server"]["tools_sha256"]

    def test_round_trip_gives_identical_verdict_and_numbers(
        self, recorded: dict[str, Path]
    ) -> None:
        live = _live("diff", BEFORE, AFTER, "--tasks", TASKS, "--json")
        replayed = CliRunner().invoke(
            app,
            ["diff", "--replay-before", str(recorded["b"]), "--replay-after", str(recorded["a"]),
             "--json"],
        )  # fmt: skip
        assert live.exit_code == replayed.exit_code == 0  # type: ignore[attr-defined]
        a, b = json.loads(live.output), json.loads(replayed.output)  # type: ignore[attr-defined]
        for key in ("verdict", "delta", "ci_lo", "ci_hi", "before", "after"):
            assert a[key] == b[key]
        # and it is the bundled demo's recorded result
        assert b["before"]["joint_success_rate"] == pytest.approx(0.667, abs=1e-3)

    def test_replay_only_prints_recorded_model_and_seed(self, recorded: dict[str, Path]) -> None:
        r = CliRunner().invoke(
            app,
            ["diff", "--replay-before", str(recorded["b"]), "--replay-after", str(recorded["a"])],
        )
        assert r.exit_code == 0 and "stub:model-x" in r.output and "seed=42" in r.output

    def test_eval_save_then_replay(self, tmp_path: Path) -> None:
        out = tmp_path / "e.json"
        r = _live("eval", BEFORE, "--tasks", TASKS, "--save", str(out))
        assert r.exit_code == 0 and out.is_file(), r.output  # type: ignore[attr-defined]
        back = CliRunner().invoke(app, ["eval", BEFORE, "--replay", str(out), "--tasks", TASKS])
        assert back.exit_code == 0, back.output

    def test_unwritable_destination_is_a_clean_error(self, tmp_path: Path) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x")
        r = _live("diff", BEFORE, AFTER, "--tasks", TASKS, "--save-before", str(blocker / "b.json"))
        assert r.exit_code == 2 and "cannot write replay file" in r.output  # type: ignore[attr-defined]
        assert "Traceback" not in r.output  # type: ignore[attr-defined]


class TestConflicts:
    @pytest.mark.parametrize(
        "extra",
        [
            ["--mock"],
            ["--replay-before", "x.json", "--replay-after", "y.json"],
            ["--replay-before", "x.json"],
        ],
    )
    def test_diff_save_rejected_with_mock_or_replay(self, tmp_path: Path, extra: list[str]) -> None:
        r = CliRunner().invoke(
            app,
            [
                "diff",
                BEFORE,
                AFTER,
                "--tasks",
                TASKS,
                "--save-before",
                str(tmp_path / "b.json"),
                *extra,
            ],
        )
        assert r.exit_code == 2 and "LIVE run" in r.output
        assert not (tmp_path / "b.json").exists()

    def test_same_file_for_both_arms_rejected(self, tmp_path: Path) -> None:
        p = str(tmp_path / "same.json")
        r = CliRunner().invoke(app, ["diff", BEFORE, AFTER, "--save-before", p, "--save-after", p])
        assert r.exit_code == 2 and "different files" in r.output

    @pytest.mark.parametrize("extra", [["--mock"], ["--replay", "x.json"]])
    def test_eval_save_rejected_with_mock_or_replay(self, tmp_path: Path, extra: list[str]) -> None:
        r = CliRunner().invoke(app, ["eval", BEFORE, "--save", str(tmp_path / "e.json"), *extra])
        assert r.exit_code == 2 and "LIVE run" in r.output


class TestStaleness:
    def _replay(self, rec: dict[str, Path], before: str, after: str, *extra: str) -> object:
        return CliRunner().invoke(
            app,
            ["diff", before, after, "--replay-before", str(rec["b"]), "--replay-after", str(rec["a"]),
             *extra],
        )  # fmt: skip

    def test_fresh_replay_with_servers_passes_silently(self, recorded: dict[str, Path]) -> None:
        r = self._replay(recorded, BEFORE, AFTER, "--tasks", TASKS)
        assert r.exit_code == 0 and "stale" not in r.output  # type: ignore[attr-defined]

    def test_changed_tool_schema_blocks_with_exit_2(self, recorded: dict[str, Path]) -> None:
        # Servers swapped = the live schema no longer matches what was recorded.
        r = self._replay(recorded, AFTER, BEFORE)
        assert r.exit_code == 2  # type: ignore[attr-defined]
        assert "replay-before is stale: tool schema changed" in r.output  # type: ignore[attr-defined]
        assert "--save-before" in r.output and "--allow-stale-replay" in r.output  # type: ignore[attr-defined]
        assert "INSUFFICIENT_SENSITIVITY" not in r.output  # type: ignore[attr-defined]

    def test_allow_stale_replay_warns_and_proceeds(self, recorded: dict[str, Path]) -> None:
        r = self._replay(recorded, AFTER, BEFORE, "--allow-stale-replay")
        assert r.exit_code == 0 and "Continuing (--allow-stale-replay)" in r.output  # type: ignore[attr-defined]
        assert "INSUFFICIENT_SENSITIVITY" in r.output  # type: ignore[attr-defined]

    def test_changed_tasks_file_blocks(self, recorded: dict[str, Path], tmp_path: Path) -> None:
        tasks = tmp_path / "tasks.json"
        shutil.copy(TASKS, tasks)
        tasks.write_text(tasks.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        r = self._replay(recorded, BEFORE, AFTER, "--tasks", str(tasks))
        assert r.exit_code == 2 and "tasks file changed" in r.output  # type: ignore[attr-defined]

    def test_eval_replay_against_changed_server_blocks(self, recorded: dict[str, Path]) -> None:
        # recorded["b"] was captured against BEFORE; evaluating it against AFTER is stale.
        ok = CliRunner().invoke(app, ["eval", BEFORE, "--replay", str(recorded["b"])])
        stale = CliRunner().invoke(app, ["eval", AFTER, "--replay", str(recorded["b"])])
        override = CliRunner().invoke(
            app, ["eval", AFTER, "--replay", str(recorded["b"]), "--allow-stale-replay"]
        )
        assert ok.exit_code == 0 and "stale" not in ok.output
        assert stale.exit_code == 2 and "replay is stale" in stale.output
        assert override.exit_code == 0 and "Continuing" in override.output

    def test_legacy_file_with_servers_warns_but_does_not_block(self) -> None:
        r = CliRunner().invoke(
            app,
            ["diff", BEFORE, AFTER, "--replay-before", str(DEMO / "replay_before.json"),
             "--replay-after", str(DEMO / "replay_after.json")],
        )  # fmt: skip
        assert r.exit_code == 0 and "legacy replay with no provenance" in r.output
        assert "INSUFFICIENT_SENSITIVITY" in r.output

    def test_legacy_replay_only_is_unchanged_and_silent(self) -> None:
        r = CliRunner().invoke(
            app,
            ["diff", "--replay-before", str(DEMO / "replay_before.json"),
             "--replay-after", str(DEMO / "replay_after.json")],
        )  # fmt: skip
        assert r.exit_code == 0 and "legacy" not in r.output and "replay before:" not in r.output

    def test_unknown_format_version_is_a_clean_error(
        self, recorded: dict[str, Path], tmp_path: Path
    ) -> None:
        raw = json.loads(recorded["b"].read_text(encoding="utf-8"))
        raw["format_version"] = 9
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(raw), encoding="utf-8")
        r = CliRunner().invoke(
            app, ["diff", "--replay-before", str(bad), "--replay-after", str(recorded["a"])]
        )
        assert r.exit_code == 2 and "unsupported replay format_version 9" in r.output
        assert "Traceback" not in r.output
