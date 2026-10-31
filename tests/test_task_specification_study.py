"""scripts/task_specification_study.py: pure helpers and the aggregate-only leak guard.

Synthetic data only; the private R1 inputs are never touched here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "task_specification_study", _ROOT / "scripts" / "task_specification_study.py"
)
assert _spec and _spec.loader
study = importlib.util.module_from_spec(_spec)
sys.modules["task_specification_study"] = study
_spec.loader.exec_module(study)


def test_wilson_ci_known_value_and_undefined() -> None:
    lo, hi = study.wilson_ci(50, 100)
    assert (round(lo, 3), round(hi, 3)) == (0.404, 0.596)
    assert study.wilson_ci(0, 0) is None
    with pytest.raises(ValueError):
        study.wilson_ci(5, 4)


def test_confusion_and_metrics() -> None:
    c = study.confusion_counts([True, True, False, False], [True, False, True, False])
    assert c == {"tp": 1, "fp": 1, "fn": 1, "tn": 1}
    m = study.classification_metrics(c)
    assert m["precision"]["value"] == 0.5 and m["specificity"]["n"] == 2
    empty = study.classification_metrics({"tp": 0, "fp": 0, "fn": 0, "tn": 3})
    assert empty["precision"]["value"] is None  # flags nothing: undefined, not zero


def test_predicates_union() -> None:
    p = study.predicates_for({"task_spec_near_duplicate_description"})
    assert p[study.NEAR_DUP_EITHER] and p[study.ANY]
    assert not study.predicates_for(set())[study.ANY]


def test_fired_checks_ignores_info_notes() -> None:
    tools = [SimpleNamespace(name="a", description="", inputSchema={})]
    from agentgauge.constraints import BlindTask

    assert study.fired_checks(BlindTask("missing", "x"), tools) == set()


def test_leak_guard_counts_without_returning_values() -> None:
    items = [{"server_id": "acme/widgets", "gold_tool": "get_widget"}]
    cats = {"h": {"server_id": "acme/widgets", "tools": [{"name": "get_widget"}, {"name": "ping"}]}}
    toks = study.leak_tokens(items, cats)
    assert "acme/widgets" in toks and "get_widget" in toks and "ping" not in toks
    assert study.find_leaks("clean aggregate text", toks) == 0
    assert study.find_leaks("calls get_widget twice", toks) == 1
    assert study.find_leaks("get_widgets is a different word", toks) == 0


def test_recall_by_group_counts() -> None:
    rows = [
        ({n: n == study.ANY for n in study.PREDICATES}, "g"),
        ({n: False for n in study.PREDICATES}, "g"),
    ]
    out = study.recall_by_group(rows)
    assert out["g"]["n"] == 2 and out["g"][study.ANY]["k"] == 1
