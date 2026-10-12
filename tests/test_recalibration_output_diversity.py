from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "recalibration_output_diversity", ROOT / "scripts" / "recalibration_output_diversity.py"
)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _row(tool_set: str, gold: str, desc: str, tool: str, args: dict, score: float) -> dict:
    return {
        "tool_set": tool_set,
        "task_tool_name": gold,
        "task_description": desc,
        "selected_tool": tool,
        "constructed_args": args,
        "constraint_satisfaction": score,
    }


def test_splits_zero_variance_groups_by_whether_the_calls_differ(tmp_path: Path) -> None:
    rows = [
        # group A: identical call every trial, score 1.0
        *[_row("s", "a", "task a", "a", {"x": 1}, 1.0) for _ in range(3)],
        # group B: different args, same score -> zero-variance but NOT identical calls
        _row("s", "b", "task b", "b", {"x": 1}, 1.0),
        _row("s", "b", "task b", "b", {"x": 2}, 1.0),
        # group C: scores differ -> not zero-variance
        _row("s", "c", "task c", "c", {"x": 1}, 1.0),
        _row("s", "c", "task c", "c", {"x": 2}, 0.0),
        # group D: wrong tool picked differently, always scoring 0.0
        _row("s", "d", "task d", "d", {}, 0.0),
        _row("s", "d", "task d", "other", {}, 0.0),
    ]
    p = tmp_path / "rows.ndjson"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    gold = mod.analyse(p)["gold_groups(tool_set,task_tool_name)"]
    assert gold["groups"] == 4
    assert gold["zero_variance_groups"] == 3
    assert gold["zero_variance_all_trials_identical_call"] == 1
    assert gold["zero_variance_differing_calls_same_score"] == 2
    assert gold["of_which_selected_tool_differs"] == 1
    assert gold["of_which_same_tool_only_args_differ"] == 1
    assert gold["zero_variance_all_score_0.0"] == 1
    assert gold["zero_variance_all_score_1.0"] == 2


def test_committed_diversity_fixture_matches_committed_rows() -> None:
    assert mod.main.__module__ == "recalibration_output_diversity"
    rows = ROOT / "evals/fixtures/recalibration_seedfix/rows.ndjson"
    out = ROOT / "evals/fixtures/recalibration_seedfix/output_diversity.json"
    expected = json.dumps(mod.analyse(rows), indent=2, sort_keys=True) + "\n"
    assert out.read_text(encoding="utf-8") == expected
