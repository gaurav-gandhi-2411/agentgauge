from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "recalibration_zero_variance_audit", ROOT / "scripts" / "recalibration_zero_variance_audit.py"
)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

ROWS = ROOT / "evals/fixtures/recalibration_seedfix/rows.ndjson"
FIXTURE = ROOT / "evals/fixtures/recalibration_seedfix/zero_variance_audit.json"


def test_committed_fixture_matches_committed_rows() -> None:
    expected = json.dumps(mod.analyse(ROWS), indent=2, sort_keys=True) + "\n"
    assert FIXTURE.read_text(encoding="utf-8") == expected


def test_a_wrong_tool_never_scores_above_zero_in_the_corpus() -> None:
    """The scorer zeroes any trial that selected a non-gold tool, so no zero-variance group with
    differing selected tools can be all-pass. Checked on the data, not assumed."""
    audit = json.loads(FIXTURE.read_text(encoding="utf-8"))
    part1 = audit["part1_selected_tool_differs"]
    assert part1["trials_anywhere_selecting_non_gold_tool_but_scoring_nonzero"] == []
    assert part1["n_all_pass_with_non_gold_tool"] == 0
    assert part1["n_all_pass"] == 0
    assert part1["n_groups"] == part1["n_all_fail"]


def test_unconstrained_task_scores_one_regardless_of_args(tmp_path: Path) -> None:
    """Pins the leniency the audit documents: with no registered constraint, any call passes."""
    rows = [
        {
            "tool_set": "no_such_set",
            "task_tool_name": "t",
            "task_description": "unregistered task",
            "trial_index": i,
            "selected_tool": "t",
            "constructed_args": args,
            "constraint_satisfaction": 1.0,
        }
        for i, args in enumerate([{}, {"x": 1}])
    ]
    p = tmp_path / "rows.ndjson"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    part3 = mod.analyse(p)["part3_arguments_differ"]
    assert part3["n_all_pass"] == 1
    assert part3["of_which_task_has_NO_registered_constraint"] == 1
