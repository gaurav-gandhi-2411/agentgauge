"""Replay file format v1: round-trip, legacy compatibility, version guard, atomic write.

No model, no network, no subprocess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp.types import Tool

from agentgauge import replay
from agentgauge.harness import TrialOutcome, diff_from_trials
from agentgauge.replay import ReplayError, load_replay, save_replay, tools_sha256

DEMO = Path(replay.__file__).parent / "demo"


def _trials(n: int = 6) -> list[TrialOutcome]:
    return [
        TrialOutcome(f"tool_{i % 3}", f"tool_{i % 3}" if i % 4 else "other", 1.0 if i % 2 else 0.5)
        for i in range(n)
    ]


def _save(path: Path, trials: list[TrialOutcome], **kw: object) -> None:
    args: dict[str, object] = {
        "model": "ollama:gemma2:9b",
        "seed": 42,
        "trials_per_task": 1,
        "target": "srv.py",
        "tools_sha": "a" * 64,
        "tasks_sha": "b" * 64,
        "created_utc": "2026-10-23T00:00:00Z",
    }
    args.update(kw)
    save_replay(path, trials, **args)  # type: ignore[arg-type]


class TestRoundTrip:
    def test_save_then_load_preserves_trials_and_verdict(self, tmp_path: Path) -> None:
        before, after = _trials(24), list(reversed(_trials(24)))
        _save(tmp_path / "b.json", before)
        _save(tmp_path / "a.json", after)
        lb, la = load_replay(tmp_path / "b.json"), load_replay(tmp_path / "a.json")
        assert lb.trials == before and la.trials == after
        direct = diff_from_trials(before, after, threshold=0.05)
        replayed = diff_from_trials(lb.trials, la.trials, threshold=0.05)
        assert replayed.verdict == direct.verdict
        assert (replayed.delta, replayed.ci_lo, replayed.ci_hi) == (
            direct.delta,
            direct.ci_lo,
            direct.ci_hi,
        )

    def test_provenance_fields_are_written(self, tmp_path: Path) -> None:
        _save(tmp_path / "x.json", _trials())
        raw = json.loads((tmp_path / "x.json").read_text(encoding="utf-8"))
        assert raw["format"] == "agentgauge-replay" and raw["format_version"] == 1
        assert raw["server"] == {"target": "srv.py", "tools_sha256": "a" * 64}
        assert raw["tasks_sha256"] == "b" * 64 and raw["seed"] == 42
        assert {"agentgauge_version", "model", "trials_per_task", "created_utc"} <= raw.keys()
        loaded = load_replay(tmp_path / "x.json")
        assert loaded.tools_sha256 == "a" * 64 and "seed=42" in (loaded.describe() or "")

    def test_creates_missing_parent_directory(self, tmp_path: Path) -> None:
        _save(tmp_path / "deep" / "dir" / "x.json", _trials())
        assert (tmp_path / "deep" / "dir" / "x.json").is_file()


class TestLegacyAndGuards:
    @pytest.mark.parametrize("name", ["replay_before.json", "replay_after.json"])
    def test_bundled_legacy_list_still_loads(self, name: str) -> None:
        loaded = load_replay(DEMO / name)
        assert len(loaded.trials) == 24
        assert loaded.provenance is None and loaded.tools_sha256 is None
        assert loaded.describe() is None

    def test_unknown_format_version_is_a_clear_error(self, tmp_path: Path) -> None:
        p = tmp_path / "x.json"
        _save(p, _trials())
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["format_version"] = 2
        p.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(ReplayError, match=r"unsupported replay format_version 2"):
            load_replay(p)

    def test_foreign_object_and_malformed_trials_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "x.json"
        p.write_text(json.dumps({"hello": 1}), encoding="utf-8")
        with pytest.raises(ReplayError, match="not an agentgauge replay file"):
            load_replay(p)
        p.write_text(json.dumps([{"selected_tool": "t"}]), encoding="utf-8")
        with pytest.raises(ReplayError, match="malformed trial record"):
            load_replay(p)
        with pytest.raises(ReplayError, match="replay file not found"):
            load_replay(tmp_path / "nope.json")


class TestAtomicWrite:
    def test_failed_write_leaves_no_partial_and_keeps_old_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dest = tmp_path / "x.json"
        _save(dest, _trials(3))
        old = dest.read_bytes()

        def boom(src: object, dst: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(replay.os, "replace", boom)
        with pytest.raises(ReplayError, match="cannot write replay file"):
            _save(dest, _trials(9))
        assert dest.read_bytes() == old
        assert sorted(p.name for p in tmp_path.iterdir()) == ["x.json"]

    def test_failure_before_replace_leaves_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(fd: int) -> None:
            raise OSError("io error")

        monkeypatch.setattr(replay.os, "fsync", boom)
        with pytest.raises(ReplayError):
            _save(tmp_path / "x.json", _trials())
        assert list(tmp_path.iterdir()) == []


class TestToolsHash:
    def _tool(self, name: str, desc: str, props: dict[str, object]) -> Tool:
        return Tool(
            name=name, description=desc, inputSchema={"type": "object", "properties": props}
        )

    def test_order_and_key_order_independent_but_content_sensitive(self) -> None:
        a = self._tool("a", "does a", {"x": {"type": "string"}, "y": {"type": "integer"}})
        b = self._tool("b", "does b", {})
        a_reordered = self._tool("a", "does a", {"y": {"type": "integer"}, "x": {"type": "string"}})
        assert tools_sha256([a, b]) == tools_sha256([b, a_reordered])
        edited = self._tool(
            "a", "does a better", {"x": {"type": "string"}, "y": {"type": "integer"}}
        )
        assert tools_sha256([a, b]) != tools_sha256([edited, b])
        renamed = self._tool("a", "does a", {"x2": {"type": "string"}, "y": {"type": "integer"}})
        assert tools_sha256([a, b]) != tools_sha256([renamed, b])


def test_staleness_problems(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    _save(p, _trials(), tools_sha="a" * 64, tasks_sha="t" * 64)
    rf = load_replay(p)
    fresh = replay.staleness_problems(rf, live_tools_sha="a" * 64, live_tasks_sha="t" * 64)
    assert fresh == []
    assert replay.staleness_problems(rf, live_tools_sha="a" * 64, live_tasks_sha=None) == []
    both = replay.staleness_problems(rf, live_tools_sha="b" * 64, live_tasks_sha="x" * 64)
    assert len(both) == 2 and "tool schema changed" in both[0] and "tasks file" in both[1]
    legacy = load_replay(DEMO / "replay_before.json")
    assert replay.staleness_problems(legacy, live_tools_sha="b" * 64, live_tasks_sha=None) == []
