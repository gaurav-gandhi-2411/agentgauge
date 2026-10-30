"""scripts/provider_compat_posthoc.py: pure functions only, synthetic data, no private files."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "provider_compat_posthoc", _ROOT / "scripts" / "provider_compat_posthoc.py"
)
assert _spec and _spec.loader
posthoc = importlib.util.module_from_spec(_spec)
sys.modules["provider_compat_posthoc"] = posthoc
_spec.loader.exec_module(posthoc)

_WITH_LIMIT = [
    {
        "name": "t",
        "input_schema": {
            "type": "object",
            "properties": {"a": {"type": "array", "items": {"type": "string"}, "maxItems": 4}},
        },
    }
]
_WITHOUT = [{"name": "t", "inputSchema": {"type": "object", "properties": {}}}]


def test_fired_checks_sees_new_check_with_either_schema_key() -> None:
    assert posthoc.NEW_CHECK in posthoc.fired_checks(_WITH_LIMIT)
    assert posthoc.NEW_CHECK not in posthoc.fired_checks(_WITHOUT)


def test_before_predicates_ignore_the_new_check() -> None:
    fired = posthoc.fired_checks(_WITH_LIMIT)
    before = posthoc.predicates(fired, after=False)
    after = posthoc.predicates(fired, after=True)
    assert posthoc.NEW_CHECK not in before
    assert after[posthoc.NEW_CHECK] is True
    # INFO tier: the gate predicate cannot move; any_finding is true either way here because the
    # schema-size note already fires on `maxItems`.
    assert before["any_violation"] is after["any_violation"] is False
    assert before["any_finding"] is after["any_finding"] is True


def test_new_check_alone_moves_any_finding_only_when_nothing_else_fires() -> None:
    fired = {posthoc.NEW_CHECK}
    assert posthoc.predicates(fired, after=False)["any_finding"] is False
    assert posthoc.predicates(fired, after=True)["any_finding"] is True


def test_nameless_tool_fails_closed() -> None:
    with pytest.raises(ValueError):
        posthoc.fired_checks([{"input_schema": {}}])


def test_validation_confusion_for_new_predicate() -> None:
    labels = {"a": True, "b": False, "c": False}
    fired = {
        "a": posthoc.fired_checks(_WITH_LIMIT),
        "b": posthoc.fired_checks(_WITH_LIMIT),
        "c": posthoc.fired_checks(_WITHOUT),
    }
    m = posthoc.validation(labels, fired, after=True)["predicates"][posthoc.NEW_CHECK]
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 0, 1)
    assert posthoc.NEW_CHECK not in posthoc.validation(labels, fired, after=False)["predicates"]


def test_prevalence_groups_and_denominators() -> None:
    rows = [("S", posthoc.fired_checks(_WITH_LIMIT)), ("S", posthoc.fired_checks(_WITHOUT))]
    table = posthoc.prevalence(rows, after=True)
    assert table["ALL"]["n"] == 2 and table["S"]["n"] == 2
    assert table["ALL"][posthoc.NEW_CHECK]["k"] == 1
