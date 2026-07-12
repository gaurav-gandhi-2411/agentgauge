from __future__ import annotations

import pytest

from agentgauge.frozen_protocol import (
    ABSTAINED_OR_HEDGED,
    CLASSIFIER_OUTCOMES,
    DEFAULT_AGENT_MODEL,
    GENERATOR_MODEL,
    HEADROOM_CEILING,
    JUDGE_MODEL,
    JUDGE_SEED,
    MIN_CONTESTED_TASKS,
    PARSE_FAILED,
    SELECTED_CORRECT,
    SELECTED_WRONG,
    TRIALS_PER_ARM,
    EffectResult,
    validate_effect_result,
)

# ── Constant invariants ───────────────────────────────────────────────────────


def test_frozen_constants_match_calibrated_values() -> None:
    """Constants must match the values calibrated on 2026-05-31 (CLAUDE.md)."""
    assert JUDGE_MODEL == "llama3.1:8b"
    assert JUDGE_SEED == 42
    assert GENERATOR_MODEL == "qwen3:8b"
    assert DEFAULT_AGENT_MODEL == "gemma2:9b"
    assert TRIALS_PER_ARM == 5
    assert HEADROOM_CEILING == 0.85
    assert MIN_CONTESTED_TASKS == 6


def test_generator_and_judge_are_different() -> None:
    """Structural independence: generator != judge (always)."""
    assert GENERATOR_MODEL != JUDGE_MODEL


def test_parse_failed_is_not_a_classifier_outcome() -> None:
    """PARSE-FAILED is reported separately and must not be in CLASSIFIER_OUTCOMES."""
    assert PARSE_FAILED not in CLASSIFIER_OUTCOMES
    assert PARSE_FAILED not in {SELECTED_CORRECT, SELECTED_WRONG, ABSTAINED_OR_HEDGED}


def test_classifier_outcomes_are_complete() -> None:
    expected = {"SELECTED-CORRECT", "SELECTED-WRONG", "ABSTAINED-OR-HEDGED"}
    assert set(CLASSIFIER_OUTCOMES) == expected


# ── EffectResult helpers ──────────────────────────────────────────────────────


def _valid_result(**overrides: object) -> EffectResult:
    """Build a minimally valid EffectResult for testing."""
    defaults: dict[str, object] = dict(
        experiment_id="test-exp",
        agent_model="gemma2:9b",
        fixture_hash="abc123def456",
        n_contested=10,
        n_stable=10,
        parse_failed_a=0,
        parse_failed_b=0,
        arm_a_accuracy=0.50,
        arm_b_accuracy=0.90,
        effect_pp=40.0,
        n_plus=8,
        n_minus=0,
        n_ties=2,
        sign_test_p=0.008,
        stable_set_n_plus=8,
        stable_set_n_minus=0,
        stable_set_p=0.008,
        headroom_gated=True,
    )
    defaults.update(overrides)
    return EffectResult(**defaults)  # type: ignore[arg-type]


def test_valid_effect_result_passes_validation() -> None:
    assert validate_effect_result(_valid_result()) == []


def test_validation_catches_low_n_contested() -> None:
    # 3 < MIN_CONTESTED_TASKS (6)
    r = _valid_result(n_contested=3, n_stable=3, n_plus=3, n_minus=0, n_ties=0)
    errors = validate_effect_result(r)
    assert any("minimum" in e for e in errors)


def test_validation_catches_headroom_not_gated_on_non_aborted() -> None:
    r = _valid_result(headroom_gated=False, aborted=False)
    errors = validate_effect_result(r)
    assert any("headroom" in e for e in errors)


def test_aborted_experiment_does_not_require_headroom_gate() -> None:
    r = _valid_result(headroom_gated=False, aborted=True, abort_reason="no headroom")
    errors = validate_effect_result(r)
    # No headroom-gate error expected for an aborted experiment
    assert not any("headroom" in e for e in errors)


def test_validation_catches_effect_pp_mismatch() -> None:
    # arm_b - arm_a = 0.40, but effect_pp = 99.0
    r = _valid_result(arm_a_accuracy=0.50, arm_b_accuracy=0.90, effect_pp=99.0)
    errors = validate_effect_result(r)
    assert any("effect_pp" in e for e in errors)


def test_validation_catches_count_mismatch() -> None:
    # n_plus(5) + n_minus(0) + n_ties(2) = 7 != n_stable(10)
    r = _valid_result(n_plus=5, n_minus=0, n_ties=2, n_stable=10)
    errors = validate_effect_result(r)
    assert any("n_stable" in e or "n_plus" in e for e in errors)


def test_validation_catches_arm_accuracy_out_of_range() -> None:
    r_a = _valid_result(arm_a_accuracy=1.5, effect_pp=60.0, arm_b_accuracy=2.1)
    errors_a = validate_effect_result(r_a)
    assert any("arm_a_accuracy" in e for e in errors_a)


def test_effect_result_is_immutable() -> None:
    """EffectResult is frozen — mutation must raise."""
    r = _valid_result()
    with pytest.raises((AttributeError, TypeError)):
        r.effect_pp = 0.0  # type: ignore[misc]
