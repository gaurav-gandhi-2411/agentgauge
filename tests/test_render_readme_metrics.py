from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "render_readme_metrics", _ROOT / "scripts" / "render_readme_metrics.py"
)
assert _SPEC is not None and _SPEC.loader is not None
rrm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rrm)


def _metric(point: float, lo: float | None = None, hi: float | None = None) -> dict[str, Any]:
    return {
        "point": point,
        "ci_lo": point if lo is None else lo,
        "ci_hi": point if hi is None else hi,
        "n_valid_replicates": 10,
    }


def _metrics(icc: float, zero: float) -> dict[str, Any]:
    return {
        "zero_var_share_pct": _metric(zero),
        "icc": _metric(icc, icc - 0.05, icc + 0.05),
        "pct_between_task": _metric(60.0),
        "pct_between_trial": _metric(15.0),
        "baseline": _metric(0.7),
        "sigma_task": _metric(0.3),
        "resid_sd": _metric(0.2),
    }


def _rate(k: int, n: int) -> dict[str, Any]:
    return {
        "k": k,
        "N": n,
        "rate_pct": 100 * k / n,
        "wilson_lo_pct": 0.1,
        "wilson_hi_pct": 9.9,
    }


def _stratum(fa: int, ab: int, n: int) -> dict[str, Any]:
    return {"false_alarm": _rate(fa, n), "abstention": _rate(ab, n)}


def _cell(label: str, n_tasks: int, mde: float) -> dict[str, Any]:
    return {"label": label, "n_tasks": n_tasks, "sims": 2000, "mde": mde}


def synthetic_results() -> dict[str, Any]:
    """A tiny, fully fake results.json with the same shape recalibration_analyze.py writes."""
    return {
        "tool_sets_used": ["toy_a", "toy_b"],
        "tool_sets_dropped_partial_or_incomplete": [],
        "n_new_rows_used": 123,
        "inputs": {
            "rows": {"path": "rows.ndjson", "sha256": "ab" * 32},
            "old": {"path": "old.json", "sha256": "cd" * 32},
        },
        "old_full": {"tool_sets": ["a"] * 4, "metrics": _metrics(0.80, 90.0)},
        "old_restricted": {"metrics": _metrics(0.75, 85.0)},
        "new_gold": {"metrics": _metrics(0.40, 30.0)},
        "diff_new_minus_old": {"icc": _metric(-0.35, -0.4, -0.3)},
        "null": {
            "caveat": "synthetic caveat text",
            "old_full": {"by_stratum": {"<10 tasks": _stratum(7, 262, 700)}},
            "old_restricted": {"by_stratum": {"<10 tasks": _stratum(1, 20, 100)}},
            "new": {"by_stratum": {"<10 tasks": _stratum(2, 30, 100)}},
        },
        "mde": {
            "sims": 2000,
            "cells": [
                _cell("OLD constants (control)", 100, 0.0848),
                _cell("OLD constants (control)", 253, 0.0537),
                _cell(rrm.GOLD_LABEL, 100, 0.1234),
                _cell(rrm.GOLD_LABEL, 253, 0.0777),
                _cell(rrm.TRUE_LABEL, 100, 0.1111),
                _cell(rrm.TRUE_LABEL, 253, 0.0666),
                _cell("NEW gold, resid_sd at its 97.5% bootstrap quantile (x)", 100, 0.1500),
            ],
        },
    }


@pytest.fixture()
def readme(tmp_path: Path) -> Path:
    path = tmp_path / "README.md"
    path.write_text(f"intro\n\n{rrm.BEGIN}\nstale\n{rrm.END}\n\noutro\n", encoding="utf-8")
    return path


def _write(tmp_path: Path, data: Any) -> Path:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_pending_block_has_exact_line_and_no_digits_of_old_values() -> None:
    block = rrm.render_block(None, "abc1234")
    assert rrm.PENDING_LINE in block.splitlines()
    for old_value in ("0.0848", "0.0537", "0.793", "21.6", "1.57", "90.3"):
        assert old_value not in block


def test_block_with_results_has_tables_sources_and_sha() -> None:
    block = rrm.render_block(synthetic_results(), "abc1234", "evals/x/results.json")
    assert rrm.PENDING_LINE not in block
    assert "`evals/x/results.json`" in block
    assert "`toy_a`" in block and "123" in block
    assert "0.400 [0.350, 0.450]" in block  # new ICC with CI
    assert "0.0848" in block and "0.1234" in block  # old vs new MDE at 100
    assert "7/700" in block  # old null false alarms with k/N
    assert "abababababab" in block  # input hash prefix
    assert "Rendered at commit: `abc1234`" in block
    # new MDE 0.1234 > 0.10 so the ship target must not be reported as met
    assert "**not met**" in block
    # fewer tool sets than the original (2 < 4): the verdict is flagged provisional
    assert "PROVISIONAL" in block


def test_ship_target_met_when_new_mde_below_target() -> None:
    data = synthetic_results()
    data["tool_sets_used"] = ["a"] * 4
    for cell in data["mde"]["cells"]:
        if cell["label"] == rrm.GOLD_LABEL and cell["n_tasks"] == 100:
            cell["mde"] = 0.0900
    block = rrm.render_block(data, "abc1234")
    assert "**met**" in block and "PROVISIONAL" not in block


def test_low_simulation_count_is_flagged_as_preview() -> None:
    data = synthetic_results()
    data["mde"]["sims"] = 20
    assert "low-simulation preview" in rrm.render_block(data, "abc1234")


def test_malformed_results_raise() -> None:
    data = synthetic_results()
    del data["mde"]
    with pytest.raises(rrm.RenderError, match="mde"):
        rrm.render_block(data, "abc1234")


def test_write_then_check_roundtrip(readme: Path, tmp_path: Path) -> None:
    results = _write(tmp_path, synthetic_results())
    argv = ["--readme", str(readme), "--results", str(results), "--sha", "abc1234"]
    assert rrm.main(argv + ["--check"]) == 1  # README holds the stale placeholder
    assert rrm.main(argv) == 0
    text = readme.read_text(encoding="utf-8")
    assert "intro" in text and "outro" in text and "stale" not in text
    assert rrm.main(argv + ["--check"]) == 0
    # a different commit SHA alone must not make the block stale
    assert (
        rrm.main(
            ["--readme", str(readme), "--results", str(results), "--sha", "zzzzzzz", "--check"]
        )
        == 0
    )


def test_check_fails_when_block_edited_by_hand(readme: Path, tmp_path: Path) -> None:
    results = _write(tmp_path, synthetic_results())
    argv = ["--readme", str(readme), "--results", str(results), "--sha", "abc1234"]
    assert rrm.main(argv) == 0
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("0.1234", "0.0001"), encoding="utf-8"
    )
    assert rrm.main(argv + ["--check"]) == 1


def test_check_fails_when_results_appear_after_pending_render(readme: Path, tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    argv = ["--readme", str(readme), "--sha", "abc1234"]
    assert rrm.main([*argv, "--results", str(missing)]) == 0
    assert rrm.main([*argv, "--results", str(missing), "--check"]) == 0
    results = _write(tmp_path, synthetic_results())
    assert rrm.main([*argv, "--results", str(results), "--check"]) == 1


def test_missing_or_duplicate_markers_are_an_error(tmp_path: Path) -> None:
    results = _write(tmp_path, synthetic_results())
    no_markers = tmp_path / "a.md"
    no_markers.write_text("nothing here\n", encoding="utf-8")
    assert rrm.main(["--readme", str(no_markers), "--results", str(results)]) == 2
    twice = tmp_path / "b.md"
    twice.write_text(f"{rrm.BEGIN}\n{rrm.END}\n{rrm.BEGIN}\n{rrm.END}\n", encoding="utf-8")
    assert rrm.main(["--readme", str(twice), "--results", str(results), "--check"]) == 2


def test_unreadable_results_fail_closed_not_pending(readme: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert rrm.main(["--readme", str(readme), "--results", str(bad), "--check"]) == 2
    incomplete = _write(tmp_path, {"tool_sets_used": []})
    assert rrm.main(["--readme", str(readme), "--results", str(incomplete), "--check"]) == 2


def test_real_readme_has_markers_and_is_in_sync() -> None:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.count(rrm.BEGIN) == 1 and readme.count(rrm.END) == 1
    assert readme.index(rrm.BEGIN) < readme.index(rrm.END)
    # Fails if results.json exists but the README block was not regenerated (drift gate),
    # or if the README block was hand-edited while results are still pending.
    assert rrm.main(["--check"]) == 0


def test_real_readme_pending_state_shows_no_recalibrated_number() -> None:
    results = _ROOT / rrm.DEFAULT_RESULTS
    if results.exists():
        pytest.skip("results.json present: the block is covered by the sync test")
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    block = readme[readme.index(rrm.BEGIN) : readme.index(rrm.END)]
    assert rrm.PENDING_LINE in block
    assert not re.search(r"\d\.\d{3,}", block)


def test_render_does_not_mutate_input() -> None:
    data = synthetic_results()
    before = copy.deepcopy(data)
    rrm.render_block(data, "abc1234")
    assert data == before


def _extras() -> dict[str, Any]:
    return {
        "output_diversity": {
            "gold_groups(tool_set,task_tool_name)": {
                "zero_variance_groups": 10,
                "zero_variance_all_trials_identical_call": 4,
                "zero_variance_differing_calls_same_score": 6,
                "of_which_same_tool_only_args_differ": 5,
                "of_which_selected_tool_differs": 1,
            }
        },
        "zero_variance_audit": {
            "part1_selected_tool_differs": {"n_groups": 1, "n_all_pass_with_non_gold_tool": 0},
            "part3_arguments_differ": {
                "n_all_pass": 5,
                "n_all_fail": 0,
                "all_pass_tasks_with_differing_args": 5,
                "of_which_task_has_NO_registered_constraint": 2,
                "of_which_constrained_but_differing_params_all_unconstrained": 2,
                "of_which_a_differing_param_is_constrained": 1,
            },
        },
    }


def test_diagnosis_states_the_old_attribution_was_wrong_with_numbers_from_results() -> None:
    block = rrm.render_block(synthetic_results(), "abc1234", extras=_extras())
    assert "Correction to an earlier diagnosis" in block
    assert "diagnosis was mostly wrong" in block
    # numbers come from the fixtures passed in, not from literals in the renderer
    assert "4 issued the identical tool call" in block
    assert "6 issued different calls that scored the same" in block
    assert "2 have no registered constraint at all" in block
    assert "only 1 vary in an argument the scorer checks" in block
    assert "more distinct tasks, not more trials per task" in block


def test_diagnosis_degrades_gracefully_without_the_audit_fixtures() -> None:
    block = rrm.render_block(synthetic_results(), "abc1234")
    assert "diagnosis was mostly wrong" in block
    assert "output_diversity.json" not in block
