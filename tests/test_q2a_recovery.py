from __future__ import annotations

import json
from pathlib import Path

from agentgauge.q2a_harness import (
    _sign_test,
    compute_recovery_fraction,
    identify_contested_indices,
    load_arm_f_descriptions,
    parse_failed_count,
    parse_success_accuracy,
)
from agentgauge.runner import RunResult
from agentgauge.tasks import Task

# ── Helpers ────────────────────────────────────────────────────────────────────


def _r(task: Task, selected: str | None) -> RunResult:
    return RunResult(task=task, selected_tool=selected, constructed_args={}, success=False)


# ── load_arm_f_descriptions ────────────────────────────────────────────────────


def test_load_arm_f_descriptions_from_file(tmp_path: Path) -> None:
    f = tmp_path / "arm_f.json"
    f.write_text(json.dumps({"get_record": "Fetch by PK.", "fetch_record": "Call REST."}))
    d = load_arm_f_descriptions(f)
    assert d["get_record"] == "Fetch by PK."
    assert d["fetch_record"] == "Call REST."


def test_load_arm_f_descriptions_missing(tmp_path: Path) -> None:
    assert load_arm_f_descriptions(tmp_path / "nope.json") == {}


def test_load_arm_f_descriptions_empty_dict(tmp_path: Path) -> None:
    f = tmp_path / "arm_f.json"
    f.write_text("{}")
    assert load_arm_f_descriptions(f) == {}


# ── compute_recovery_fraction ─────────────────────────────────────────────────


def test_recovery_half() -> None:
    assert abs(compute_recovery_fraction(0.5, 0.0, 1.0) - 0.5) < 1e-9  # type: ignore[operator]


def test_recovery_full() -> None:
    assert abs(compute_recovery_fraction(1.0, 0.0, 1.0) - 1.0) < 1e-9  # type: ignore[operator]


def test_recovery_zero() -> None:
    assert abs(compute_recovery_fraction(0.0, 0.0, 1.0) - 0.0) < 1e-9  # type: ignore[operator]


def test_recovery_zero_headroom() -> None:
    assert compute_recovery_fraction(0.5, 0.5, 0.5) is None


def test_recovery_nonzero_floor() -> None:
    # A=0.3, F=0.65, O=1.0  ->  (0.65-0.30)/(1.0-0.30) = 0.5
    frac = compute_recovery_fraction(0.65, 0.30, 1.0)
    assert frac is not None
    assert abs(frac - 0.5) < 1e-6


# ── identify_contested_indices ────────────────────────────────────────────────


def test_contested_basic() -> None:
    tasks = [Task("t1", "a"), Task("t2", "b"), Task("t3", "c")]
    valid = {"t1", "t2", "t3"}
    # task 0: always wrong (contested); task 1: always right; task 2: always wrong
    results = [
        _r(tasks[0], "t2"),
        _r(tasks[0], "t3"),  # task 0: 2 wrong
        _r(tasks[1], "t2"),
        _r(tasks[1], "t2"),  # task 1: 2 right
        _r(tasks[2], "t1"),
        _r(tasks[2], "t1"),  # task 2: 2 wrong
    ]
    assert identify_contested_indices(results, tasks, 2, valid) == [0, 2]


def test_contested_all_parse_failed_excluded() -> None:
    tasks = [Task("t1", "a")]
    results = [_r(tasks[0], None), _r(tasks[0], None)]
    assert identify_contested_indices(results, tasks, 2, {"t1"}) == []


def test_contested_ceiling_not_included() -> None:
    tasks = [Task("t1", "a")]
    results = [_r(tasks[0], "t1"), _r(tasks[0], "t1"), _r(tasks[0], "t1")]
    assert identify_contested_indices(results, tasks, 3, {"t1"}) == []


# ── parse_success_accuracy ────────────────────────────────────────────────────


def test_parse_success_accuracy_basic() -> None:
    tasks = [Task("t1", "a"), Task("t2", "b")]
    valid = {"t1", "t2"}
    results = [
        _r(tasks[0], "t1"),
        _r(tasks[0], "t2"),  # 1/2 correct
        _r(tasks[1], "t2"),
        _r(tasks[1], "t2"),  # 2/2 correct
    ]
    assert abs(parse_success_accuracy(results, tasks, 2, valid, [0, 1]) - 0.75) < 1e-9


def test_parse_success_accuracy_excludes_parse_failed() -> None:
    tasks = [Task("t1", "a")]
    valid = {"t1"}
    results = [_r(tasks[0], None), _r(tasks[0], "t1")]  # 1 parse-failed, 1 correct
    assert abs(parse_success_accuracy(results, tasks, 2, valid, [0]) - 1.0) < 1e-9


def test_parse_success_accuracy_empty_indices() -> None:
    tasks = [Task("t1", "a")]
    results = [_r(tasks[0], "t1")]
    assert parse_success_accuracy(results, tasks, 1, {"t1"}, []) == 0.0


def test_parse_success_accuracy_all_failed() -> None:
    tasks = [Task("t1", "a")]
    results = [_r(tasks[0], None), _r(tasks[0], None)]
    assert parse_success_accuracy(results, tasks, 2, {"t1"}, [0]) == 0.0


# ── parse_failed_count ────────────────────────────────────────────────────────


def test_parse_failed_count_mixed() -> None:
    tasks = [Task("t1", "a")]
    results = [_r(tasks[0], None), _r(tasks[0], "t1"), _r(tasks[0], "unknown")]
    assert parse_failed_count(results, {"t1", "t2"}) == 2


def test_parse_failed_count_zero() -> None:
    tasks = [Task("t1", "a")]
    assert parse_failed_count([_r(tasks[0], "t1")], {"t1"}) == 0


# ── _sign_test ────────────────────────────────────────────────────────────────


def test_sign_test_all_positive() -> None:
    n_plus, n_minus, p = _sign_test([0.5, 0.3, 1.0, 0.2])
    assert n_plus == 4
    assert n_minus == 0
    assert abs(p - 0.125) < 1e-4  # 2*(0.5^4) = 0.125


def test_sign_test_mixed() -> None:
    n_plus, n_minus, _ = _sign_test([0.5, -0.3, 0.0, 0.2])
    assert n_plus == 2
    assert n_minus == 1  # 0.0 is a tie, excluded


def test_sign_test_empty() -> None:
    _, _, p = _sign_test([])
    assert p == 1.0


def test_sign_test_all_ties() -> None:
    n_plus, n_minus, p = _sign_test([0.0, 0.0])
    assert n_plus == 0 and n_minus == 0 and p == 1.0


# ── Integration: three-arm wiring with Arm F from file ────────────────────────


def test_three_arm_wiring_recovery(tmp_path: Path) -> None:
    arm_f_file = tmp_path / "arm_f.json"
    arm_f_file.write_text(json.dumps({"tool_a": "Specific desc for tool_a."}))
    arm_f = load_arm_f_descriptions(arm_f_file)
    assert arm_f["tool_a"] == "Specific desc for tool_a."

    tasks = [Task("tool_a", "task 1"), Task("tool_b", "task 2")]
    valid = {"tool_a", "tool_b"}
    trials = 2

    results_a = [
        _r(tasks[0], "tool_b"),
        _r(tasks[0], "tool_b"),  # task 0 always wrong (contested)
        _r(tasks[1], "tool_b"),
        _r(tasks[1], "tool_b"),  # task 1 always right
    ]
    results_f = [
        _r(tasks[0], "tool_a"),
        _r(tasks[0], "tool_b"),  # task 0: 1/2 correct
        _r(tasks[1], "tool_b"),
        _r(tasks[1], "tool_b"),
    ]
    results_o = [
        _r(tasks[0], "tool_a"),
        _r(tasks[0], "tool_a"),  # task 0: 2/2 correct
        _r(tasks[1], "tool_b"),
        _r(tasks[1], "tool_b"),
    ]

    contested = identify_contested_indices(results_a, tasks, trials, valid)
    assert contested == [0]

    acc_a = parse_success_accuracy(results_a, tasks, trials, valid, contested)
    acc_f = parse_success_accuracy(results_f, tasks, trials, valid, contested)
    acc_o = parse_success_accuracy(results_o, tasks, trials, valid, contested)

    assert acc_a == 0.0
    assert acc_f == 0.5
    assert acc_o == 1.0

    frac = compute_recovery_fraction(acc_f, acc_a, acc_o)
    assert frac is not None
    assert abs(frac - 0.5) < 1e-9


def test_three_arm_descriptions_differ() -> None:
    from evals.fixtures.t18_catalog import ARM_A_DESCRIPTIONS, ARM_B_DESCRIPTIONS

    assert ARM_A_DESCRIPTIONS != ARM_B_DESCRIPTIONS
    for name, desc in ARM_A_DESCRIPTIONS.items():
        assert desc == "", f"{name} should be empty in Arm A"
    for name, desc in ARM_B_DESCRIPTIONS.items():
        assert desc != "", f"{name} should be non-empty in Arm O"
