from __future__ import annotations

# Frozen evaluation protocol — constants and result type.
# Reference: docs/research/frozen_protocol.md
# Must not be modified after any experiment produces results under this protocol.
from dataclasses import dataclass, field
from typing import Literal

# ── Frozen configuration ──────────────────────────────────────────────────────

JUDGE_MODEL: str = "llama3.1:8b"  # pinned; calibrated 2026-05-31
JUDGE_SEED: int = 42
GENERATOR_MODEL: str = "qwen3:8b"  # ONE family; must always differ from judge
DEFAULT_AGENT_MODEL: str = "gemma2:9b"  # agent is the variable only in EXP-2

TRIALS_PER_ARM: int = 5
SIGN_TEST_ALPHA: float = 0.05
HEADROOM_CEILING: float = 0.85  # Arm A accuracy must be < this to proceed to A/B
MIN_CONTESTED_TASKS: int = 6  # below this, the sign test is underpowered

# Max |run1_correct − run2_correct| (in trials) for a task to be considered stable.
STABILITY_MAX_DELTA_TRIALS: int = 1

# ── Classifier ────────────────────────────────────────────────────────────────

Outcome = Literal["SELECTED-CORRECT", "SELECTED-WRONG", "ABSTAINED-OR-HEDGED"]

SELECTED_CORRECT: Outcome = "SELECTED-CORRECT"
SELECTED_WRONG: Outcome = "SELECTED-WRONG"
ABSTAINED_OR_HEDGED: Outcome = "ABSTAINED-OR-HEDGED"

# Reported separately from the three outcomes — never aggregated with them.
PARSE_FAILED: str = "PARSE-FAILED"

CLASSIFIER_OUTCOMES: tuple[Outcome, ...] = (
    SELECTED_CORRECT,
    SELECTED_WRONG,
    ABSTAINED_OR_HEDGED,
)


# ── Result type ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EffectResult:
    """
    Standardized result report per the frozen protocol.

    Every experiment must produce one of these; ad-hoc table formats are not
    acceptable for cross-experiment comparisons.
    """

    experiment_id: str
    agent_model: str
    fixture_hash: str  # SHA-256[:12] of the fixture file at run time

    # Contested task counts
    n_contested: int  # pre-registered contested task count
    n_stable: int  # after stability screen (n_contested if no flippers)

    # Parse-failure counts (absolute, not %)
    parse_failed_a: int
    parse_failed_b: int

    # Accuracy on parse-success stable contested tasks
    arm_a_accuracy: float  # fraction in [0, 1]
    arm_b_accuracy: float

    effect_pp: float  # (arm_b_accuracy − arm_a_accuracy) × 100

    # Sign test inputs
    n_plus: int  # tasks where B > A
    n_minus: int  # tasks where A > B
    n_ties: int  # tasks where B == A
    sign_test_p: float

    # Stable-set analysis (same as above when no flippers were excluded)
    stable_set_n_plus: int
    stable_set_n_minus: int
    stable_set_p: float

    # Protocol gates
    headroom_gated: bool  # True = headroom gate passed (Arm A < HEADROOM_CEILING)
    aborted: bool = False  # True = experiment aborted (e.g., no headroom)
    abort_reason: str = ""

    # Optional extra context
    notes: list[str] = field(default_factory=list)


def validate_effect_result(r: EffectResult) -> list[str]:
    """
    Check that an EffectResult satisfies the frozen-protocol invariants.

    Returns a list of error strings; an empty list means PASS.
    """
    errors: list[str] = []

    if r.n_contested < MIN_CONTESTED_TASKS:
        errors.append(
            f"n_contested={r.n_contested} is below the minimum {MIN_CONTESTED_TASKS}; "
            "sign test is underpowered"
        )

    if not r.aborted and not r.headroom_gated:
        errors.append(
            "headroom_gated=False but aborted=False; "
            "a result without headroom must be marked aborted"
        )

    expected_effect = (r.arm_b_accuracy - r.arm_a_accuracy) * 100
    if abs(r.effect_pp - expected_effect) > 0.05:
        errors.append(
            f"effect_pp={r.effect_pp:.2f} does not match "
            f"(arm_b - arm_a) * 100 = {expected_effect:.2f}"
        )

    if r.n_plus + r.n_minus + r.n_ties != r.n_stable:
        errors.append(
            f"n_plus({r.n_plus}) + n_minus({r.n_minus}) + n_ties({r.n_ties}) "
            f"= {r.n_plus + r.n_minus + r.n_ties} != n_stable({r.n_stable})"
        )

    if r.arm_a_accuracy < 0.0 or r.arm_a_accuracy > 1.0:
        errors.append(f"arm_a_accuracy={r.arm_a_accuracy} is not in [0, 1]")

    if r.arm_b_accuracy < 0.0 or r.arm_b_accuracy > 1.0:
        errors.append(f"arm_b_accuracy={r.arm_b_accuracy} is not in [0, 1]")

    return errors
