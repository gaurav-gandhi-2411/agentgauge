"""Generic argument-correctness constraint checking (AgentGauge v2 product code).

Promoted from evals/fixtures/predictive_validity/constraints.py (study-specific,
hand-authored per fixture) into general product code, since the underlying
checking logic was always generic -- only the per-fixture constraint
REGISTRATIONS were study-specific. This module provides the CONSTRUCT: a task
with an optional list of Constraints, checked against whatever arguments an
agent actually constructed for it.

Used by `agentgauge diff`/`agentgauge eval`'s live mode: a user-supplied task
file can optionally include constraints (see BlindTask); without them, a task's
correctness collapses to tool-selection-correctness alone (the same
future-proof default this study's own constraint_satisfaction() used) -- this
limitation is real and stated explicitly, not hidden: an MCP server that
accepts any well-formed call cannot be distinguished from one that validates
arguments unless the task itself carries a ground-truth constraint.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_NUMERIC_TOLERANCE = 1e-6


@dataclass
class Constraint:
    """A single correctness constraint on a constructed call argument.

    kind="enum": value must equal gold_value exactly (case-sensitive).
    kind="format": re.fullmatch(pattern, str(value)) must not be None.
    kind="range": min_val <= int(value) <= max_val.
    kind="contains": str(value).lower() must contain gold_value.lower().
    kind="numeric_equals": abs(float(value) - float(gold_value)) <= tolerance.
    """

    param: str
    kind: str
    gold_value: str | None = None
    pattern: str | None = None
    min_val: int | None = None
    max_val: int | None = None
    tolerance: float | None = None


@dataclass
class BlindTask:
    """One anti-tautology task: the gold tool name must never appear in
    `description` (this is a naming/authoring convention this module cannot
    enforce automatically -- see agentgauge init's generated template for
    guidance)."""

    tool_name: str
    description: str
    constraints: list[Constraint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BlindTask:
        constraints = [Constraint(**c) for c in d.get("constraints", [])]
        return cls(tool_name=d["tool_name"], description=d["description"], constraints=constraints)


def _check_constraint(value: Any, c: Constraint) -> bool:
    if value is None:
        return False
    if c.kind == "enum":
        return bool(value == c.gold_value)
    if c.kind == "format":
        return c.pattern is not None and re.fullmatch(c.pattern, str(value)) is not None
    if c.kind == "range":
        try:
            v_int = int(value)
        except (TypeError, ValueError):
            return False
        return c.min_val is not None and c.max_val is not None and c.min_val <= v_int <= c.max_val
    if c.kind == "contains":
        return c.gold_value is not None and c.gold_value.lower() in str(value).lower()
    if c.kind == "numeric_equals":
        try:
            v_float = float(value)
            gold_float = float(c.gold_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        tolerance = c.tolerance if c.tolerance is not None else _DEFAULT_NUMERIC_TOLERANCE
        return abs(v_float - gold_float) <= tolerance
    raise ValueError(f"Unknown constraint kind: {c.kind!r}")


def constraint_satisfaction(
    constructed_args: dict[str, Any], constraints: list[Constraint] | None
) -> float:
    """Fraction of `constraints` satisfied by `constructed_args`, in [0.0, 1.0].

    Returns 1.0 if `constraints` is None or empty: a task with no registered
    constraint is counted as fully correct on arguments (there is nothing to
    check) -- this is a real limitation for unconstrained tasks against a
    server that accepts any well-formed call, stated in this module's
    docstring, not hidden.
    """
    if not constraints:
        return 1.0
    satisfied = sum(1 for c in constraints if _check_constraint(constructed_args.get(c.param), c))
    return satisfied / len(constraints)
