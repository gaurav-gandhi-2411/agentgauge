"""Tests for scripts/recalibration_analyze.py (no network, no model, tiny simulations)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "recalibration_analyze", REPO / "scripts" / "recalibration_analyze.py"
)
assert _spec is not None and _spec.loader is not None
ra = importlib.util.module_from_spec(_spec)
sys.modules["recalibration_analyze"] = ra
_spec.loader.exec_module(ra)

OLD_FIXTURE = REPO / "evals" / "fixtures" / "predictive_validity" / "results_raw.json"


def test_zero_variance_share_hand_built() -> None:
    groups = {"a": [1.0, 1.0, 1.0], "b": [0.0, 1.0, 0.0], "c": [0.0, 0.0]}
    agg = ra.tool_set_agg(groups)
    m = ra.metrics_from_aggs([agg], [agg])
    assert agg["n_zero"] == 2 and agg["n_multi"] == 3
    assert m["zero_var_share_pct"] == pytest.approx(100 * 2 / 3)
    assert ra.vvs.task1a_icc({"s": groups})["pct_groups_zero_within_group_variance"] == (
        pytest.approx(100 * 2 / 3)
    )


def test_icc_hand_computed_balanced() -> None:
    # g1=[1,3], g2=[5,7]: grand mean 4, SSB=16 (MSB=16), SSW=4 (MSW=2), n0=2
    # ICC = (16 - 2) / (16 + (2-1)*2) = 14/18
    groups = {"s": {"g1": [1.0, 3.0], "g2": [5.0, 7.0]}}
    expected = 14 / 18
    assert ra.vvs.task1a_icc(groups)["icc"] == pytest.approx(expected)
    agg = ra.tool_set_agg(groups["s"])
    assert ra.metrics_from_aggs([agg], [agg])["icc"] == pytest.approx(expected)


def test_wilson_known_values() -> None:
    lo, hi = ra.wilson_interval(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)
    lo, hi = ra.wilson_interval(5, 10)
    assert (lo, hi) == (pytest.approx(0.2366, abs=1e-4), pytest.approx(0.7634, abs=1e-4))


def test_seed_base_depends_only_on_name() -> None:
    assert ra.seed_base("x") == ra.seed_base("x") != ra.seed_base("y")


def _write_synthetic(tmp: Path) -> tuple[Path, Path]:
    rows = []
    old = []
    for ts in ("set_a", "set_b"):
        old_runs = []
        for gold in ("t1", "t2", "t3"):
            for d in range(2):
                for i in range(3):
                    ok = (i + d + len(ts) + len(gold)) % 3 != 0
                    rows.append(
                        {
                            "tool_set": ts,
                            "tier": "x",
                            "task_tool_name": gold,
                            "task_description": f"{gold} task {d}",
                            "trial_index": i,
                            "seed": i,
                            "selected_tool": gold if ok else "other",
                            "constructed_args": {},
                            "success": ok,
                            "error": None,
                            "parse_failed": False,
                            "constraint_satisfaction": 1.0 if ok else 0.0,
                            "task_block_seconds": 1.0,
                            "ts": "t",
                        }
                    )
                    old_runs.append(
                        {
                            "task_tool_name": gold,
                            "selected_tool": gold,
                            "constraint_satisfaction": 1.0,
                        }
                    )
        old.append({"name": ts, "run_results": old_runs})
    rows_p, old_p = tmp / "rows.ndjson", tmp / "old.json"
    rows_p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    old_p.write_text(json.dumps(old), encoding="utf-8")
    return rows_p, old_p


def test_end_to_end_synthetic_skip_mde(tmp_path: Path) -> None:
    rows_p, old_p = _write_synthetic(tmp_path)
    out = tmp_path / "out"
    rc = ra.main(
        [
            "--rows", str(rows_p), "--old", str(old_p), "--out", str(out),
            "--skip-mde", "--workers", "1", "--fa-repeats", "2", "--boot", "30",
        ]
    )  # fmt: skip
    assert rc == 3  # synthetic "old" is not the real corpus -> control must report FAIL
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert res["tool_sets_used"] == ["set_a", "set_b"]
    assert res["new_gold"]["n_trials"] == 36
    assert res["new_true"]["n_groups"] == 12  # true-task groups: 2 sets x 3 gold x 2 descriptions
    assert res["new_gold"]["n_groups"] == 6
    assert res["old_restricted"]["point"]["zero_var_share_pct"] == 100.0
    assert res["new_gold"]["rho"]["computable"] is False
    assert res["null"]["new"]["overall"]["n_comparisons"] == 4
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest["inputs"]["rows"]["sha256"]) == 64
    assert "Tool sets used" in (out / "results.md").read_text(encoding="utf-8")


def test_old_corpus_control_reproduces_published_numbers() -> None:
    cs = ra.groups_from_old(OLD_FIXTURE, "cs")
    jt = ra.groups_from_old(OLD_FIXTURE, "joint")
    full = ra.analyse_corpus(cs, jt, n_boot=20)
    assert full["n_groups_zero_within_group_variance"] == 650
    assert full["n_groups_with_multiple_trials"] == 720
    # The published ICC is a float built from sum() calls; the last digits differ across Python
    # versions (CI saw 0.7932642721759026): Python 3.11's float sum() is naive left-to-right,
    # 3.12's is compensated. Not an OS effect. Compare to 1e-9, not bit-for-bit.
    assert full["icc_detail"]["icc"] == pytest.approx(0.7932642721759006, rel=1e-9)
    assert round(full["variance_decomposition"]["pct_between_task_within_toolset"], 2) == 56.06
    assert full["suff_stat_vs_exact_max_abs_drift"] < 1e-6
    assert ra.build_control(full, full)["pass"] is True


def test_mde_cells_tiny_sims() -> None:
    fake = {
        "point": {"baseline": 0.7, "sigma_task": 0.3, "resid_sd": 0.1, "rho": None},
        "metrics": {
            "resid_sd": {"ci_lo": 0.05, "ci_hi": 0.2},
            "sigma_task": {"ci_lo": 0.25, "ci_hi": 0.35},
        },
    }
    cells, notes = ra.build_mde_cells(fake, fake, sims=2)
    assert "not computable" in notes["rho"]
    assert {c["rho"] for c in cells} == {ra.CALIBRATED_RHO}
    assert len(cells) == 2 * (3 + 4)
    small = {**cells[0], "n_tasks": 8}
    out = ra._mde_job(small)
    assert 0.0 < out["mde"] <= 1.0
