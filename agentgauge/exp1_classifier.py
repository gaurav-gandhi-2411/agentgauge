from __future__ import annotations

from dataclasses import dataclass, field

from agentgauge.exp1_mirror import ServerMirror
from agentgauge.frozen_protocol import (
    HEADROOM_CEILING,
    PARSE_FAILED,
    SELECTED_CORRECT,
)

# Re-export for convenience — callers can import from here
__all__ = [
    "ContestedTask",
    "TrialOutcome",
    "FamilyResult",
    "ServerResult",
    "compute_family_result",
    "compute_server_result",
]


@dataclass
class ContestedTask:
    task_id: str
    family_id: str
    task_text: str  # anti-tautological task description
    gold_tool: str  # the correct tool name


@dataclass
class TrialOutcome:
    task_id: str
    trial: int
    outcome: str  # SELECTED-CORRECT, SELECTED-WRONG, ABSTAINED-OR-HEDGED, PARSE-FAILED
    selected_tool: str | None


@dataclass
class FamilyResult:
    server_id: str
    family_id: str
    tool_names: list[str]
    n_contested: int
    parse_failed_a: int
    parse_failed_b: int
    arm_a_accuracy: float  # on parse-success contested tasks
    arm_b_accuracy: float  # 0.0 if aborted (no headroom)
    effect_pp: float
    headroom_gated: bool  # True = gate passed (Arm A < HEADROOM_CEILING)
    in_regime: bool  # True = Arm A fails >=1 task AND Arm B recovers it
    aborted: bool = False
    abort_reason: str = ""
    arm_a_outcomes: list[TrialOutcome] = field(default_factory=list)
    arm_b_outcomes: list[TrialOutcome] = field(default_factory=list)


@dataclass
class ServerResult:
    server_id: str
    source_repo: str
    stratum: str
    n_families: int
    n_in_regime: int
    n_out_regime: int
    n_aborted: int
    in_regime: bool  # True if any family is in-regime
    families: list[FamilyResult] = field(default_factory=list)
    is_validation_anchor: bool = False
    anchor_known_result: str = ""  # "IN-REGIME" or "OUT-OF-REGIME" if anchor


def compute_family_result(
    server_id: str,
    family_id: str,
    tool_names: list[str],
    arm_a_outcomes: list[TrialOutcome],
    arm_b_outcomes: list[TrialOutcome],
    contested_tasks: list[ContestedTask],
) -> FamilyResult:
    """Compute regime classification for one confusable family.

    arm_a_outcomes and arm_b_outcomes: all trial outcomes for this family.
    If arm_b_outcomes is empty, assumes Arm A showed no headroom (aborted).
    """
    n_contested = len(contested_tasks)
    task_ids = {t.task_id for t in contested_tasks}

    def _filter_family(outcomes: list[TrialOutcome]) -> list[TrialOutcome]:
        return [o for o in outcomes if o.task_id in task_ids]

    a_outcomes = _filter_family(arm_a_outcomes)
    b_outcomes = _filter_family(arm_b_outcomes)

    parse_failed_a = sum(1 for o in a_outcomes if o.outcome == PARSE_FAILED)
    parse_failed_b = sum(1 for o in b_outcomes if o.outcome == PARSE_FAILED)

    a_parse_success = [o for o in a_outcomes if o.outcome != PARSE_FAILED]
    b_parse_success = [o for o in b_outcomes if o.outcome != PARSE_FAILED]

    def _task_accuracy(
        outcomes: list[TrialOutcome], tasks: list[ContestedTask]
    ) -> dict[str, float]:
        """Task-level accuracy (task is the unit; trials are repeated measures)."""
        by_task: dict[str, list[str]] = {}
        for o in outcomes:
            if o.outcome != PARSE_FAILED:
                by_task.setdefault(o.task_id, []).append(o.outcome)
        result: dict[str, float] = {}
        for t in tasks:
            trials = by_task.get(t.task_id, [])
            if trials:
                result[t.task_id] = sum(1 for o in trials if o == SELECTED_CORRECT) / len(trials)
            else:
                result[t.task_id] = 0.0
        return result

    a_task_acc = _task_accuracy(a_parse_success, contested_tasks)
    b_task_acc = _task_accuracy(b_parse_success, contested_tasks)

    arm_a_accuracy = sum(a_task_acc.values()) / len(a_task_acc) if a_task_acc else 0.0
    headroom_gated = arm_a_accuracy < HEADROOM_CEILING

    if not headroom_gated:
        return FamilyResult(
            server_id=server_id,
            family_id=family_id,
            tool_names=tool_names,
            n_contested=n_contested,
            parse_failed_a=parse_failed_a,
            parse_failed_b=0,
            arm_a_accuracy=arm_a_accuracy,
            arm_b_accuracy=0.0,
            effect_pp=0.0,
            headroom_gated=False,
            in_regime=False,
            aborted=True,
            abort_reason=(
                f"No headroom: Arm A accuracy={arm_a_accuracy:.1%} >= {HEADROOM_CEILING:.0%}"
            ),
            arm_a_outcomes=a_outcomes,
        )

    arm_b_accuracy = sum(b_task_acc.values()) / len(b_task_acc) if b_task_acc else 0.0
    effect_pp = (arm_b_accuracy - arm_a_accuracy) * 100

    # IN-REGIME: Arm A fails >=1 contested task AND Arm B recovers it
    a_failures = {tid for tid, acc in a_task_acc.items() if acc < 1.0}
    b_recovered = {tid for tid in a_failures if b_task_acc.get(tid, 0.0) >= 1.0}
    in_regime = len(a_failures) >= 1 and len(b_recovered) >= 1

    return FamilyResult(
        server_id=server_id,
        family_id=family_id,
        tool_names=tool_names,
        n_contested=n_contested,
        parse_failed_a=parse_failed_a,
        parse_failed_b=parse_failed_b,
        arm_a_accuracy=arm_a_accuracy,
        arm_b_accuracy=arm_b_accuracy,
        effect_pp=effect_pp,
        headroom_gated=True,
        in_regime=in_regime,
        arm_a_outcomes=a_outcomes,
        arm_b_outcomes=b_outcomes,
    )


def compute_server_result(
    mirror: ServerMirror,
    family_results: list[FamilyResult],
    is_validation_anchor: bool = False,
    anchor_known_result: str = "",
) -> ServerResult:
    """Aggregate per-family results into a server-level regime verdict."""
    n_in = sum(1 for f in family_results if f.in_regime and not f.aborted)
    n_out = sum(1 for f in family_results if not f.in_regime and not f.aborted)
    n_aborted = sum(1 for f in family_results if f.aborted)
    return ServerResult(
        server_id=mirror.server_id,
        source_repo=mirror.source_repo,
        stratum=mirror.stratum,
        n_families=len(family_results),
        n_in_regime=n_in,
        n_out_regime=n_out,
        n_aborted=n_aborted,
        in_regime=n_in >= 1,
        families=family_results,
        is_validation_anchor=is_validation_anchor,
        anchor_known_result=anchor_known_result,
    )
