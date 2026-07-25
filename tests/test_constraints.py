"""Tests for agentgauge.constraints (v2 generic constraint-checking, promoted
from the study's evals/fixtures/predictive_validity/constraints.py)."""

from __future__ import annotations

from agentgauge.constraints import BlindTask, Constraint, constraint_satisfaction


class TestConstraintSatisfaction:
    def test_no_constraints_defaults_to_full_credit(self) -> None:
        assert constraint_satisfaction({"a": "anything"}, None) == 1.0
        assert constraint_satisfaction({}, []) == 1.0

    def test_enum_constraint_exact_match(self) -> None:
        c = Constraint(param="mode", kind="enum", gold_value="hard")
        assert constraint_satisfaction({"mode": "hard"}, [c]) == 1.0
        assert constraint_satisfaction({"mode": "soft"}, [c]) == 0.0

    def test_format_constraint(self) -> None:
        c = Constraint(param="id", kind="format", pattern=r"[A-Z]{3}\d{4}")
        assert constraint_satisfaction({"id": "ABC1234"}, [c]) == 1.0
        assert constraint_satisfaction({"id": "abc1234"}, [c]) == 0.0

    def test_range_constraint(self) -> None:
        c = Constraint(param="priority", kind="range", min_val=0, max_val=5)
        assert constraint_satisfaction({"priority": 3}, [c]) == 1.0
        assert constraint_satisfaction({"priority": 10}, [c]) == 0.0

    def test_contains_constraint_case_insensitive(self) -> None:
        c = Constraint(param="query", kind="contains", gold_value="docker")
        assert constraint_satisfaction({"query": "search for Docker images"}, [c]) == 1.0
        assert constraint_satisfaction({"query": "search for kubernetes"}, [c]) == 0.0

    def test_numeric_equals_with_tolerance(self) -> None:
        c = Constraint(param="value", kind="numeric_equals", gold_value="3.14", tolerance=0.01)
        assert constraint_satisfaction({"value": 3.145}, [c]) == 1.0
        assert constraint_satisfaction({"value": 3.5}, [c]) == 0.0

    def test_partial_credit_across_multiple_constraints(self) -> None:
        constraints = [
            Constraint(param="a", kind="enum", gold_value="x"),
            Constraint(param="b", kind="enum", gold_value="y"),
        ]
        assert constraint_satisfaction({"a": "x", "b": "wrong"}, constraints) == 0.5

    def test_missing_arg_fails_constraint(self) -> None:
        c = Constraint(param="required_field", kind="enum", gold_value="x")
        assert constraint_satisfaction({}, [c]) == 0.0


class TestBlindTaskFromDict:
    def test_parses_task_with_constraints(self) -> None:
        d = {
            "tool_name": "set_mode",
            "description": "Switch to the recoverable deletion mode.",
            "constraints": [{"param": "mode", "kind": "enum", "gold_value": "soft"}],
        }
        task = BlindTask.from_dict(d)
        assert task.tool_name == "set_mode"
        assert len(task.constraints) == 1
        assert task.constraints[0].kind == "enum"

    def test_parses_task_without_constraints(self) -> None:
        d = {"tool_name": "ping", "description": "Check connectivity."}
        task = BlindTask.from_dict(d)
        assert task.constraints == []
