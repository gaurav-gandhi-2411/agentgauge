"""scripts/provider_compat_study.py: pure functions only, synthetic data, no private files."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "provider_compat_study", _ROOT / "scripts" / "provider_compat_study.py"
)
assert _spec and _spec.loader
study = importlib.util.module_from_spec(_spec)
sys.modules["provider_compat_study"] = study
_spec.loader.exec_module(study)


def test_wilson_known_values() -> None:
    lo, hi = study.wilson_ci(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)


def test_wilson_boundaries_and_undefined() -> None:
    lo, hi = study.wilson_ci(0, 5)
    assert lo == 0.0 and hi == pytest.approx(0.4345, abs=1e-3)
    lo, hi = study.wilson_ci(5, 5)
    assert hi == 1.0 and lo == pytest.approx(0.5655, abs=1e-3)
    assert study.wilson_ci(0, 0) is None


def test_wilson_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError):
        study.wilson_ci(3, 2)


def test_confusion_counts() -> None:
    pred = [True, True, False, False, True]
    actual = [True, False, True, False, True]
    assert study.confusion_counts(pred, actual) == {"tp": 2, "fp": 1, "fn": 1, "tn": 1}
    with pytest.raises(ValueError):
        study.confusion_counts([True], [True, False])


def test_metrics_precision_undefined_when_nothing_flagged() -> None:
    m = study.classification_metrics({"tp": 0, "fp": 0, "fn": 2, "tn": 3})
    assert m["precision"]["value"] is None and m["precision"]["ci95"] is None
    assert m["recall"]["value"] == 0.0
    assert m["specificity"]["value"] == 1.0


def test_stratum_edges() -> None:
    assert [study.stratum_of(n) for n in (1, 2, 3, 5, 6, 15, 16, 40, 41)] == [
        study.BELOW_S, study.BELOW_S, "S", "S", "M", "M", "L", "L", "XL",
    ]  # fmt: skip


def test_predicates_and_lint_on_synthetic_catalog() -> None:
    tools = [
        {"name": "ok_tool", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "bad name!", "input_schema": {"type": "object", "maxItems": 3}},
    ]
    p = study.lint_catalog(tools)
    assert p["provider_compat_tool_name"] and p["provider_compat_schema_size"]
    assert p["any_violation"] and p["any_finding"] and not p["provider_compat_tool_count"]
    with pytest.raises(ValueError):
        study.lint_catalog([{"inputSchema": {}}])


def test_prevalence_table_groups() -> None:
    hit = study.predicates_from_fired(["provider_compat_schema_size"])
    miss = study.predicates_from_fired([])
    t = study.prevalence_table([("S", hit), ("S", miss), ("XL", hit)])
    assert t["ALL"]["n"] == 3
    assert t["ALL"]["provider_compat_schema_size"]["k"] == 2
    assert t["S"]["any_finding"]["k"] == 1 and t["XL"]["any_violation"]["k"] == 0
    assert study.BELOW_S not in t


def test_vertex_labels_fail_closed_on_unknown_status() -> None:
    rows = [
        {"server_id": "x", "labeller": "flash", "status": "ok"},
        {"server_id": "x", "labeller": "pro", "status": "HTTP_400"},
        {"server_id": "y", "labeller": "flash", "status": "ok"},
    ]
    labels, meta = study.vertex_labels(rows)
    assert labels == {"x": True, "y": False} and meta["n_calls"] == 3
    with pytest.raises(ValueError):
        study.vertex_labels([{"server_id": "z", "labeller": "flash", "status": "timeout"}])


def test_launch_gate_sentence_not_met_and_met() -> None:
    weak = study._ratio(1, 1)
    low = study._ratio(5, 18)
    s = study.launch_gate_sentence(weak, low)
    assert "NOT met" in s and "1/1" in s and "0.207" in s and "0.278" in s
    strong = study._ratio(100, 100)
    assert "**met**" in study.launch_gate_sentence(strong, strong)
    undefined = study._ratio(0, 0)
    assert "NOT met" in study.launch_gate_sentence(undefined, undefined)
    assert "undefined" in study.launch_gate_sentence(undefined, undefined)


def test_sha256_lf_ignores_crlf(tmp_path: Path) -> None:
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_bytes(b"x = 1\r\ny = 2\r\n")
    b.write_bytes(b"x = 1\ny = 2\n")
    assert study.sha256_lf(a) == study.sha256_lf(b) == study.sha256_file(b)
