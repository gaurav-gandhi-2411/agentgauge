from __future__ import annotations

import pytest

from agentgauge.exp1_classifier import (
    ContestedTask,
    FamilyResult,
    TrialOutcome,
    compute_family_result,
    compute_server_result,
)
from agentgauge.exp1_mirror import ServerMirror
from agentgauge.frozen_protocol import (
    ABSTAINED_OR_HEDGED,
    PARSE_FAILED,
    SELECTED_CORRECT,
    SELECTED_WRONG,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

SERVER_ID = "test-server"
FAMILY_ID = "read-write-family"
TOOL_NAMES = ["read_file", "write_file"]


def _task(task_id: str) -> ContestedTask:
    return ContestedTask(
        task_id=task_id,
        family_id=FAMILY_ID,
        task_text=f"Perform operation {task_id}",
        gold_tool="read_file",
    )


def _outcome(task_id: str, trial: int, outcome: str) -> TrialOutcome:
    selected = "read_file" if outcome == SELECTED_CORRECT else "write_file"
    return TrialOutcome(task_id=task_id, trial=trial, outcome=outcome, selected_tool=selected)


def _contested_tasks() -> list[ContestedTask]:
    return [_task("t1"), _task("t2"), _task("t3")]


def _all_correct_outcomes(tasks: list[ContestedTask], n_trials: int = 5) -> list[TrialOutcome]:
    outcomes: list[TrialOutcome] = []
    for t in tasks:
        for trial in range(n_trials):
            outcomes.append(_outcome(t.task_id, trial, SELECTED_CORRECT))
    return outcomes


def _all_wrong_outcomes(tasks: list[ContestedTask], n_trials: int = 5) -> list[TrialOutcome]:
    outcomes: list[TrialOutcome] = []
    for t in tasks:
        for trial in range(n_trials):
            outcomes.append(_outcome(t.task_id, trial, SELECTED_WRONG))
    return outcomes


def _make_mirror() -> ServerMirror:
    return ServerMirror(
        server_id=SERVER_ID,
        source_repo="owner/test-server",
        language="python",
        stars=100,
        stratum="mid",
    )


# ── IN-REGIME classification ─────────────────────────────────────────────────


def test_in_regime_arm_a_fails_arm_b_recovers() -> None:
    """Arm A fails all tasks, Arm B recovers all — should be IN-REGIME."""
    tasks = _contested_tasks()
    arm_a = _all_wrong_outcomes(tasks)  # all wrong → arm_a_accuracy = 0.0
    arm_b = _all_correct_outcomes(tasks)  # all correct → arm_b_accuracy = 1.0

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, arm_b, tasks)

    assert result.in_regime is True
    assert result.headroom_gated is True
    assert result.aborted is False
    assert result.arm_a_accuracy == 0.0
    assert result.arm_b_accuracy == 1.0
    assert result.effect_pp == pytest.approx(100.0)
    assert result.n_contested == 3


def test_in_regime_partial_recovery() -> None:
    """Arm A fails t1, Arm B recovers t1 only — still IN-REGIME."""
    tasks = _contested_tasks()
    # Arm A: t1 fails (SELECTED_WRONG), t2 and t3 also fail to ensure headroom
    arm_a = []
    for t in tasks:
        # all fail on first 4 trials to keep accuracy < 0.85
        for trial in range(5):
            arm_a.append(_outcome(t.task_id, trial, SELECTED_WRONG))

    # Arm B: t1 correct, t2 and t3 wrong
    arm_b = []
    for t in tasks:
        for trial in range(5):
            outcome = SELECTED_CORRECT if t.task_id == "t1" else SELECTED_WRONG
            arm_b.append(_outcome(t.task_id, trial, outcome))

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, arm_b, tasks)

    assert result.in_regime is True
    assert result.arm_a_accuracy == pytest.approx(0.0)


# ── OUT-OF-REGIME: no headroom ────────────────────────────────────────────────


def test_out_of_regime_no_headroom_arm_a_perfect() -> None:
    """Arm A accuracy = 1.0 (>= 0.85) → aborted, no headroom."""
    tasks = _contested_tasks()
    arm_a = _all_correct_outcomes(tasks)
    arm_b: list[TrialOutcome] = []

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, arm_b, tasks)

    assert result.in_regime is False
    assert result.headroom_gated is False
    assert result.aborted is True
    assert "No headroom" in result.abort_reason
    assert result.arm_a_accuracy == pytest.approx(1.0)
    # Arm B was never run — abort_reason should explain
    assert "0.85" in result.abort_reason or "85%" in result.abort_reason


def test_out_of_regime_headroom_exactly_at_ceiling() -> None:
    """Arm A accuracy = 0.85 exactly → NO headroom (ceiling is STRICT less-than)."""
    tasks = [
        _task("t1"),
        _task("t2"),
        _task("t3"),
        _task("t4"),
        _task("t5"),
        _task("t6"),
        _task("t7"),
        _task("t8"),
        _task("t9"),
        _task("t10"),
        _task("t11"),
        _task("t12"),
        _task("t13"),
        _task("t14"),
        _task("t15"),
        _task("t16"),
        _task("t17"),
        _task("t18"),
        _task("t19"),
        _task("t20"),
    ]

    # 17/20 tasks correct per trial = 0.85 exactly
    arm_a: list[TrialOutcome] = []
    for i, t in enumerate(tasks):
        outcome = SELECTED_CORRECT if i < 17 else SELECTED_WRONG
        arm_a.append(_outcome(t.task_id, 0, outcome))

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, [], tasks)

    assert result.headroom_gated is False
    assert result.aborted is True


def test_out_of_regime_headroom_high_accuracy() -> None:
    """Arm A accuracy = 0.90 → no headroom gate."""
    tasks = [_task(f"t{i}") for i in range(10)]
    arm_a: list[TrialOutcome] = []
    for i, t in enumerate(tasks):
        outcome = SELECTED_CORRECT if i < 9 else SELECTED_WRONG  # 9/10 = 0.90
        arm_a.append(_outcome(t.task_id, 0, outcome))

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, [], tasks)

    assert result.headroom_gated is False
    assert result.aborted is True
    assert result.in_regime is False


# ── OUT-OF-REGIME: headroom but no recovery ───────────────────────────────────


def test_out_of_regime_headroom_but_no_recovery() -> None:
    """Arm A fails tasks but Arm B also fails → OUT-OF-REGIME."""
    tasks = _contested_tasks()
    arm_a = _all_wrong_outcomes(tasks)
    arm_b = _all_wrong_outcomes(tasks)

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, arm_b, tasks)

    assert result.in_regime is False
    assert result.headroom_gated is True
    assert result.aborted is False
    assert result.arm_a_accuracy == 0.0
    assert result.arm_b_accuracy == 0.0
    assert result.effect_pp == pytest.approx(0.0)


def test_out_of_regime_headroom_b_improves_but_no_full_recovery() -> None:
    """Arm B improves but never reaches 1.0 on any failed task → OUT-OF-REGIME."""
    tasks = [_task("t1"), _task("t2")]
    # t1: arm_a = 0 correct/5 trials, arm_b = 4 correct/5 trials (0.8 < 1.0)
    arm_a: list[TrialOutcome] = []
    arm_b: list[TrialOutcome] = []
    for trial in range(5):
        arm_a.append(_outcome("t1", trial, SELECTED_WRONG))
        arm_a.append(_outcome("t2", trial, SELECTED_WRONG))
        b_outcome = SELECTED_CORRECT if trial < 4 else SELECTED_WRONG
        arm_b.append(_outcome("t1", trial, b_outcome))
        arm_b.append(_outcome("t2", trial, b_outcome))

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, arm_b, tasks)

    # t1 arm_b accuracy = 4/5 = 0.8 < 1.0 → NOT recovered
    assert result.in_regime is False
    assert result.headroom_gated is True


# ── parse failures ────────────────────────────────────────────────────────────


def test_parse_failed_outcomes_are_excluded_from_accuracy() -> None:
    """PARSE-FAILED trials are not aggregated into accuracy."""
    tasks = [_task("t1")]
    arm_a = [
        TrialOutcome(task_id="t1", trial=0, outcome=PARSE_FAILED, selected_tool=None),
        TrialOutcome(task_id="t1", trial=1, outcome=SELECTED_CORRECT, selected_tool="read_file"),
    ]
    arm_b: list[TrialOutcome] = []

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, arm_b, tasks)

    # 1 parse failed + 1 correct → parse-success accuracy = 1.0 → NO headroom
    assert result.parse_failed_a == 1
    assert result.arm_a_accuracy == pytest.approx(1.0)
    assert result.aborted is True  # 1.0 >= 0.85 → no headroom


def test_parse_failed_count_reported() -> None:
    """parse_failed_a and parse_failed_b are counted correctly."""
    tasks = _contested_tasks()
    arm_a: list[TrialOutcome] = []
    arm_b: list[TrialOutcome] = []

    for t in tasks:
        arm_a.append(
            TrialOutcome(task_id=t.task_id, trial=0, outcome=PARSE_FAILED, selected_tool=None)
        )
        arm_a.append(_outcome(t.task_id, 1, SELECTED_WRONG))
        arm_b.append(
            TrialOutcome(task_id=t.task_id, trial=0, outcome=PARSE_FAILED, selected_tool=None)
        )
        arm_b.append(_outcome(t.task_id, 1, SELECTED_CORRECT))

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, arm_b, tasks)

    assert result.parse_failed_a == 3  # one per task
    assert result.parse_failed_b == 3


# ── abstained outcomes ────────────────────────────────────────────────────────


def test_abstained_outcome_counts_as_failure() -> None:
    """ABSTAINED-OR-HEDGED on Arm A should be treated as a failure for in_regime."""
    tasks = [_task("t1"), _task("t2")]
    arm_a = [
        _outcome("t1", 0, ABSTAINED_OR_HEDGED),
        _outcome("t2", 0, ABSTAINED_OR_HEDGED),
    ]
    arm_b = [
        _outcome("t1", 0, SELECTED_CORRECT),
        _outcome("t2", 0, SELECTED_CORRECT),
    ]

    result = compute_family_result(SERVER_ID, FAMILY_ID, TOOL_NAMES, arm_a, arm_b, tasks)

    # ABSTAINED is not SELECTED_CORRECT, so arm_a_accuracy = 0 → headroom
    # Arm B recovers both → IN-REGIME
    assert result.headroom_gated is True
    assert result.in_regime is True


# ── compute_server_result ─────────────────────────────────────────────────────


def _make_family_result(
    in_regime: bool = False,
    aborted: bool = False,
) -> FamilyResult:
    return FamilyResult(
        server_id=SERVER_ID,
        family_id="fam-1",
        tool_names=TOOL_NAMES,
        n_contested=3,
        parse_failed_a=0,
        parse_failed_b=0,
        arm_a_accuracy=0.5,
        arm_b_accuracy=1.0 if in_regime else 0.5,
        effect_pp=50.0 if in_regime else 0.0,
        headroom_gated=not aborted,
        in_regime=in_regime,
        aborted=aborted,
    )


def test_compute_server_result_all_in_regime() -> None:
    mirror = _make_mirror()
    families = [
        _make_family_result(in_regime=True),
        _make_family_result(in_regime=True),
    ]
    result = compute_server_result(mirror, families)

    assert result.server_id == SERVER_ID
    assert result.in_regime is True
    assert result.n_in_regime == 2
    assert result.n_out_regime == 0
    assert result.n_aborted == 0
    assert result.n_families == 2


def test_compute_server_result_none_in_regime() -> None:
    mirror = _make_mirror()
    families = [
        _make_family_result(in_regime=False),
        _make_family_result(in_regime=False),
    ]
    result = compute_server_result(mirror, families)

    assert result.in_regime is False
    assert result.n_in_regime == 0
    assert result.n_out_regime == 2


def test_compute_server_result_mixed() -> None:
    mirror = _make_mirror()
    families = [
        _make_family_result(in_regime=True),
        _make_family_result(in_regime=False),
        _make_family_result(in_regime=False, aborted=True),
    ]
    result = compute_server_result(mirror, families)

    assert result.in_regime is True  # at least one is in-regime
    assert result.n_in_regime == 1
    assert result.n_out_regime == 1
    assert result.n_aborted == 1
    assert result.n_families == 3


def test_compute_server_result_empty_families() -> None:
    mirror = _make_mirror()
    result = compute_server_result(mirror, [])

    assert result.in_regime is False
    assert result.n_families == 0
    assert result.n_in_regime == 0


def test_compute_server_result_validation_anchor_fields() -> None:
    mirror = _make_mirror()
    result = compute_server_result(
        mirror,
        [_make_family_result(in_regime=False)],
        is_validation_anchor=True,
        anchor_known_result="OUT-OF-REGIME",
    )

    assert result.is_validation_anchor is True
    assert result.anchor_known_result == "OUT-OF-REGIME"


def test_compute_server_result_source_repo_and_stratum() -> None:
    mirror = _make_mirror()
    result = compute_server_result(mirror, [])

    assert result.source_repo == mirror.source_repo
    assert result.stratum == mirror.stratum
