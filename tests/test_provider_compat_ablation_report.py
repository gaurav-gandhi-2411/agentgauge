"""scripts/provider_compat_ablation_report.py on a synthetic aggregate; no private files."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "provider_compat_ablation_report", _ROOT / "scripts" / "provider_compat_ablation_report.py"
)
assert _spec and _spec.loader
rep = importlib.util.module_from_spec(_spec)
sys.modules["provider_compat_ablation_report"] = rep
_spec.loader.exec_module(rep)

_HEAD = "a" * 40
_INPUT_SHA = "b" * 64


def _unit(label: str, *, c_outcomes: dict[str, str], b_reason: str | None = None) -> dict[str, Any]:
    return {
        "a0": "rejected",
        "a0_reproduced": True,
        "a1": {"enum": "no_flip", "maxItems": "flip"},
        "b": {
            "maxItems": {
                "N": 2,
                "class": "aggregate",
                "class_before_stability": None,
                "idx_forward": 1,
                "idx_reverse": 0,
                "n_forward": 2,
                "n_reverse": 2,
                "reason": b_reason,
                "singles": {"0": "accepted", "1": "accepted"},
            }
        },
        "c": {"construct": "maxItems", "copies_rejected_at": None, "outcomes": c_outcomes},
        "d": {"construct": "maxItems", "double": "rejected", "one": "accepted"},
        "depends_on_resent_call": True,
        "flipping": ["maxItems"],
        "label": label,
        "n_instances": {"enum": 3, "maxItems": 2},
        "n_tools": 2,
        "r_label": "R3",
        "s": {
            "a0_repeat": "rejected",
            "a0_stable": True,
            "boundary": {"lower": "accepted", "reproduced": True, "upper": "rejected"},
        },
    }


def _agg() -> dict[str, Any]:
    return {
        "banner": "POST-HOC: design 3d5d6e6; the rejections were seen before the design.",
        "complete": True,
        "deviation_note": "frozen design specified no retries; 1 call was re-sent once.",
        "n_resent_calls": 1,
        "stopped": None,
        "totals": {"accepted": 5, "calls": 9, "inr": 1.5, "other": 2, "rejected": 2},
        "units": [
            _unit("U1", c_outcomes={"2": "accepted", "3": "accepted", "4": "accepted"}),
            _unit("U2", c_outcomes={"2": "accepted", "3": "accepted", "4": "other"}),
            _unit("U3", c_outcomes={"2": "other"}, b_reason="other outcome during search"),
            _unit("U4", c_outcomes={}),
        ],
    }


def _render(agg: dict[str, Any]) -> tuple[str, str]:
    return rep.render_outputs(agg, input_sha256=_INPUT_SHA, git_head=_HEAD)


def test_outputs_are_deterministic_and_carry_provenance() -> None:
    j1, m1 = _render(_agg())
    j2, m2 = _render(_agg())
    assert (j1, m1) == (j2, m2)
    prov = json.loads(j1)["provenance"]
    assert prov["design_commit"] == "3d5d6e6" and prov["plan_sha256"] == rep.PLAN_SHA256
    assert prov["input_sha256"] == _INPUT_SHA and prov["git_head_at_run"] == _HEAD
    assert list(json.loads(j1)) == sorted(json.loads(j1))


def test_markdown_banner_first_and_verdict_present() -> None:
    _, md = _render(_agg())
    assert md.splitlines()[2].startswith("> **POST-HOC")
    assert "No limit isolated -> no rule change; documentation only." in md
    assert '"frozen design specified no retries; 1 call was re-sent once."' in md


def test_isolation_block_is_not_isolated() -> None:
    j, _ = _render(_agg())
    iso = json.loads(j)["isolation"]
    assert iso["isolated"] is False and iso["criterion_2"]["holds"] is False
    assert iso["criterion_1"]["units"] == ["U1", "U2", "U3", "U4"]


def test_unresolved_calls_and_c_coverage_derived_from_data() -> None:
    agg = _agg()
    assert rep.unresolved_calls(agg) == [
        {"unit": "U2", "phase": "C", "detail": "copy 4: other outcome"},
        {"unit": "U3", "phase": "B", "detail": "maxItems search: other outcome"},
        {"unit": "U3", "phase": "C", "detail": "copy 2: other outcome"},
    ]
    cov = {u["label"]: rep.c_coverage(u) for u in agg["units"]}
    assert cov["U1"] == "complete to 4 copies, all accepted"
    assert cov["U2"] == "tested 2, 3 (4 unresolved)"
    assert cov["U3"] == "untested (copy 2 unresolved)"
    assert cov["U4"] == "untested"


def test_refuses_unknown_key_such_as_a_tool_name() -> None:
    agg = _agg()
    agg["units"][0]["a1"]["my_secret_tool"] = "flip"
    with pytest.raises(ValueError, match="allow-list"):
        _render(agg)
    agg = _agg()
    agg["units"][0]["surprise"] = 1
    with pytest.raises(ValueError, match="allow-list"):
        _render(agg)


def test_refuses_undeclared_hex_string() -> None:
    agg = _agg()
    agg["banner"] = "POST-HOC: deadbeefcafe0123"
    with pytest.raises(ValueError, match="hex"):
        _render(agg)


def test_declared_digests_alone_are_allowed_and_short_hex_is_fine() -> None:
    j, m = _render(_agg())  # 3d5d6e6 (7 chars) and the declared 40/64-char digests appear
    assert _HEAD in m and _INPUT_SHA in j


def test_refuses_unexpected_value_and_bad_label() -> None:
    agg = _agg()
    agg["units"][0]["a0"] = "maybe"
    with pytest.raises(ValueError):
        _render(agg)
    agg = copy.deepcopy(_agg())
    agg["units"][0]["label"] = "some_tool"
    with pytest.raises(ValueError):
        _render(agg)


def test_main_writes_both_files(tmp_path: Path) -> None:
    src = tmp_path / "in.json"
    src.write_text(json.dumps(_agg()), encoding="utf-8")
    out_j, out_m = tmp_path / "o.json", tmp_path / "o.md"
    assert rep.main(["--in", str(src), "--out-json", str(out_j), "--out-md", str(out_m)]) == 0
    assert json.loads(out_j.read_text(encoding="utf-8"))["isolation"]["isolated"] is False
    assert out_m.read_text(encoding="utf-8").startswith("# Provider-compat ablation")


def test_main_writes_nothing_when_refused(tmp_path: Path) -> None:
    bad = _agg()
    bad["units"][0]["a1"]["leaky_name"] = "flip"
    src = tmp_path / "in.json"
    src.write_text(json.dumps(bad), encoding="utf-8")
    out_j, out_m = tmp_path / "o.json", tmp_path / "o.md"
    with pytest.raises(ValueError):
        rep.main(["--in", str(src), "--out-json", str(out_j), "--out-md", str(out_m)])
    assert not out_j.exists() and not out_m.exists()
