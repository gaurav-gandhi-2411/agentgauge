from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# scripts/ is not on the default sys.path — same pattern as test_ty2_fixture.py /
# test_exp1_generate_mirror_server.py for importing a top-level script module.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from predictive_validity_analysis import (  # noqa: E402 -- import after sys.path fixup
    CORRELATION_FIELDS,
    _bootstrap_spearman_ci,
    _effect_size_label,
    build_correlation_table,
    find_axis_flagged_cases,
)

# ── Fabricated results_raw.json-shaped dataset ──────────────────────────────────
#
# 8 synthetic tool-set records, hand-picked so that:
#   - description_quality, discoverability, schema_completeness, selection_accuracy,
#     call_correctness, error_legibility, overall_score, and baseline_single_prompt
#     all rise roughly monotonically with task_success_rate (a real predictive-signal
#     relationship the correlation table must recover with a positive rho).
#   - robustness is held EXACTLY CONSTANT (80.0) across all 8 records — a deliberately
#     degenerate axis to verify the near-zero-variance exclusion path.
#   - docs_manifest is held constant (20.0) too, mirroring the real floor value for
#     stdio-connected servers (see CLAUDE.md) — it must never appear in a computed
#     correlation because it is excluded by construction, not just degeneracy.
#   - "confusable_verbose" deliberately breaks the pattern: task_success_rate is LOW
#     (0.15, a real failure) despite reasonably well-written individual descriptions
#     (description_quality=68) and the longest description text of any record
#     (baseline_desc_length=420, rescales to 100.0) and a high single-prompt holistic
#     rating (baseline_single_prompt=72) — but AgentGauge's discoverability axis
#     correctly scores it low (18) because its tool names collide. This is the
#     baseline-misses-it / axis-catches-it case find_axis_flagged_cases must surface.


def _record(
    name: str,
    tier: str,
    task_success_rate: float,
    *,
    description_quality: float,
    discoverability: float,
    schema_completeness: float,
    selection_accuracy: float,
    call_correctness: float,
    error_legibility: float,
    overall_score: float,
    baseline_desc_length: float,
    baseline_single_prompt: float,
) -> dict[str, Any]:
    return {
        "name": name,
        "tier": tier,
        "task_success_rate": task_success_rate,
        "dimension_scores": {
            "description_quality": description_quality,
            "discoverability": discoverability,
            "schema_completeness": schema_completeness,
            "selection_accuracy": selection_accuracy,
            "call_correctness": call_correctness,
            "error_legibility": error_legibility,
            "robustness": 80.0,  # deliberately constant across every record
            "docs_manifest": 20.0,  # deliberately constant — mirrors the real stdio floor
        },
        "overall_score": overall_score,
        "baseline_desc_length": baseline_desc_length,
        "baseline_single_prompt": baseline_single_prompt,
    }


FABRICATED_RECORDS: list[dict[str, Any]] = [
    _record(
        "tiny_no_desc",
        "bad",
        0.05,
        description_quality=5,
        discoverability=10,
        schema_completeness=10,
        selection_accuracy=8,
        call_correctness=10,
        error_legibility=15,
        overall_score=12,
        baseline_desc_length=10,
        baseline_single_prompt=8,
    ),
    _record(
        "mediocre_a",
        "mediocre",
        0.25,
        description_quality=30,
        discoverability=35,
        schema_completeness=40,
        selection_accuracy=28,
        call_correctness=32,
        error_legibility=40,
        overall_score=33,
        baseline_desc_length=90,
        baseline_single_prompt=35,
    ),
    _record(
        "mediocre_b",
        "mediocre",
        0.35,
        description_quality=45,
        discoverability=48,
        schema_completeness=50,
        selection_accuracy=40,
        call_correctness=45,
        error_legibility=50,
        overall_score=46,
        baseline_desc_length=140,
        baseline_single_prompt=48,
    ),
    _record(
        "confusable_verbose",
        "bad-discoverability",
        0.15,
        description_quality=68,
        discoverability=18,
        schema_completeness=55,
        selection_accuracy=15,
        call_correctness=40,
        error_legibility=50,
        overall_score=45,
        baseline_desc_length=420,
        baseline_single_prompt=72,
    ),
    _record(
        "good_a",
        "good",
        0.65,
        description_quality=72,
        discoverability=75,
        schema_completeness=78,
        selection_accuracy=68,
        call_correctness=70,
        error_legibility=72,
        overall_score=74,
        baseline_desc_length=250,
        baseline_single_prompt=76,
    ),
    _record(
        "good_b",
        "good",
        0.80,
        description_quality=85,
        discoverability=88,
        schema_completeness=90,
        selection_accuracy=82,
        call_correctness=84,
        error_legibility=86,
        overall_score=86,
        baseline_desc_length=310,
        baseline_single_prompt=88,
    ),
    _record(
        "excellent_a",
        "good",
        0.90,
        description_quality=93,
        discoverability=95,
        schema_completeness=95,
        selection_accuracy=92,
        call_correctness=93,
        error_legibility=94,
        overall_score=94,
        baseline_desc_length=360,
        baseline_single_prompt=95,
    ),
    _record(
        "excellent_b",
        "good",
        0.97,
        description_quality=98,
        discoverability=97,
        schema_completeness=98,
        selection_accuracy=96,
        call_correctness=97,
        error_legibility=97,
        overall_score=98,
        baseline_desc_length=390,
        baseline_single_prompt=97,
    ),
]


# ── (a) correlation table shape, keys, n, and sign ──────────────────────────────


def test_correlation_table_has_expected_keys() -> None:
    table = build_correlation_table(FABRICATED_RECORDS)
    # Every CORRELATION_FIELDS entry plus the always-present docs_manifest stub.
    assert set(table.keys()) == set(CORRELATION_FIELDS) | {"docs_manifest"}


def test_correlation_table_n_matches_record_count() -> None:
    table = build_correlation_table(FABRICATED_RECORDS)
    for field in CORRELATION_FIELDS:
        assert table[field]["n"] == len(FABRICATED_RECORDS)


def test_correlation_table_sign_for_monotonic_relationship() -> None:
    """description_quality and discoverability rise with task_success_rate by design."""
    table = build_correlation_table(FABRICATED_RECORDS)
    assert table["description_quality"]["status"] == "ok"
    assert table["description_quality"]["rho"] is not None
    assert table["description_quality"]["rho"] > 0.9

    assert table["discoverability"]["status"] == "ok"
    # Discoverability was constructed as a strictly monotonic function of
    # task_success_rate in the fixture -> perfect rank correlation.
    assert table["discoverability"]["rho"] == 1.0
    assert table["discoverability"]["p_value"] == 0.0


# ── (b) degenerate / constant axis exclusion ─────────────────────────────────────


def test_degenerate_axis_is_excluded_not_silently_reported() -> None:
    table = build_correlation_table(FABRICATED_RECORDS)
    assert table["robustness"]["status"] == "degenerate — excluded"
    assert table["robustness"]["rho"] is None
    assert table["robustness"]["p_value"] is None


def test_docs_manifest_excluded_by_construction_not_computed() -> None:
    table = build_correlation_table(FABRICATED_RECORDS)
    assert table["docs_manifest"]["status"] == "excluded_by_construction"
    assert table["docs_manifest"]["rho"] is None
    assert "docs_manifest" not in CORRELATION_FIELDS


def test_non_degenerate_field_is_not_flagged_degenerate() -> None:
    """Sanity check the detector isn't over-firing on real (non-constant) fields.

    "robustness" is excluded from this loop deliberately — it is the one field
    constructed to BE degenerate (see test_degenerate_axis_is_excluded_...).
    """
    table = build_correlation_table(FABRICATED_RECORDS)
    for field in CORRELATION_FIELDS:
        if field == "robustness":
            continue
        assert table[field]["status"] != "degenerate — excluded", field


# ── (c) example-finder heuristic ─────────────────────────────────────────────────


def test_find_axis_flagged_cases_surfaces_the_planted_case() -> None:
    flagged = find_axis_flagged_cases(FABRICATED_RECORDS, axis="discoverability")

    assert 0 < len(flagged) <= 5
    names = {r["name"] for r in FABRICATED_RECORDS}
    assert all(c["name"] in names for c in flagged)

    # "confusable_verbose" is the only record with task_success_rate below the
    # default 0.5 threshold where a baseline (desc length / single-prompt judge)
    # scores it higher than the discoverability axis does.
    assert flagged[0]["name"] == "confusable_verbose"
    assert flagged[0]["gap"] > 0
    assert flagged[0]["axis"] == "discoverability"
    assert flagged[0]["axis_score"] == 18.0


def test_find_axis_flagged_cases_respects_max_results_cap() -> None:
    flagged = find_axis_flagged_cases(FABRICATED_RECORDS, axis="discoverability", max_results=1)
    assert len(flagged) <= 1


def test_find_axis_flagged_cases_empty_when_no_low_success_records() -> None:
    """No record has task_success_rate <= threshold -> no candidates, not an error."""
    flagged = find_axis_flagged_cases(
        FABRICATED_RECORDS, axis="discoverability", low_success_threshold=0.0
    )
    assert flagged == []


def test_find_axis_flagged_cases_only_from_fabricated_set() -> None:
    flagged = find_axis_flagged_cases(FABRICATED_RECORDS, axis="discoverability")
    fabricated_names = {r["name"] for r in FABRICATED_RECORDS}
    for case in flagged:
        assert case["name"] in fabricated_names


# ── (d) bootstrap CI + effect size on build_correlation_table's "ok" entries ────


def test_ok_entries_have_ci_and_effect_size_containing_the_point_estimate() -> None:
    table = build_correlation_table(FABRICATED_RECORDS)
    for field in ("description_quality", "discoverability", "overall_score"):
        result = table[field]
        assert result["status"] == "ok"
        assert result["ci"] is not None
        lo, hi = result["ci"]
        assert lo <= result["rho"] <= hi
        assert result["effect_size"] in {"negligible", "small", "moderate", "large"}
        assert result["ci_skipped"] >= 0


def test_degenerate_and_docs_manifest_entries_have_no_ci() -> None:
    table = build_correlation_table(FABRICATED_RECORDS)
    for field in ("robustness", "docs_manifest"):
        assert table[field]["ci"] is None
        assert table[field]["effect_size"] is None
        assert table[field]["ci_skipped"] == 0


def test_insufficient_n_entry_has_no_ci() -> None:
    table = build_correlation_table(FABRICATED_RECORDS[:2])
    assert table["description_quality"]["status"] == "insufficient_n"
    assert table["description_quality"]["ci"] is None
    assert table["description_quality"]["effect_size"] is None


# ── (e) _effect_size_label ───────────────────────────────────────────────────────


def test_effect_size_label_bands() -> None:
    assert _effect_size_label(None) is None
    assert _effect_size_label(0.0) == "negligible"
    assert _effect_size_label(0.05) == "negligible"
    assert _effect_size_label(-0.05) == "negligible"
    assert _effect_size_label(0.2) == "small"
    assert _effect_size_label(0.4) == "moderate"
    assert _effect_size_label(-0.4) == "moderate"
    assert _effect_size_label(0.9) == "large"
    assert _effect_size_label(-0.9) == "large"


# ── (f) _bootstrap_spearman_ci ────────────────────────────────────────────────────


def test_bootstrap_ci_is_deterministic_for_a_fixed_seed() -> None:
    xs = [float(v) for v in range(1, 21)]
    ys = [
        1.0,
        11.0,
        2.0,
        12.0,
        3.0,
        13.0,
        4.0,
        14.0,
        5.0,
        15.0,
        6.0,
        16.0,
        7.0,
        17.0,
        8.0,
        18.0,
        9.0,
        19.0,
        10.0,
        20.0,
    ]
    ci_a, skipped_a = _bootstrap_spearman_ci(xs, ys, n_resamples=500, seed=42)
    ci_b, skipped_b = _bootstrap_spearman_ci(xs, ys, n_resamples=500, seed=42)
    assert ci_a == ci_b
    assert skipped_a == skipped_b


def test_bootstrap_ci_contains_point_estimate_for_perfect_correlation() -> None:
    xs = [float(v) for v in range(1, 21)]
    ys = xs  # perfect monotonic relationship -> rho == 1.0
    ci, skipped = _bootstrap_spearman_ci(xs, ys, n_resamples=500, seed=42)
    assert ci is not None
    lo, hi = ci
    # Every bootstrap resample of a perfectly monotonic pair is itself perfectly
    # monotonic (duplicated indices still pair consistently) -> tight CI at 1.0.
    assert lo == 1.0
    assert hi == 1.0
    assert skipped == 0


def test_bootstrap_ci_width_is_wider_for_noisier_synthetic_data() -> None:
    """Same n and seed; only the y-values' noise level differs.

    A perfectly monotonic (xs, xs) pair collapses to a point-mass rho=1.0
    bootstrap distribution (zero-width CI). A noisier but still positively
    correlated pair (rho ~= 0.57, see module docstring precedent) should
    produce a strictly wider CI -- the resampled rho estimate varies more
    when the underlying relationship is noisier.
    """
    xs = [float(v) for v in range(1, 21)]
    ys_strong = xs
    ys_weak = [
        1.0,
        11.0,
        2.0,
        12.0,
        3.0,
        13.0,
        4.0,
        14.0,
        5.0,
        15.0,
        6.0,
        16.0,
        7.0,
        17.0,
        8.0,
        18.0,
        9.0,
        19.0,
        10.0,
        20.0,
    ]

    ci_strong, _ = _bootstrap_spearman_ci(xs, ys_strong, n_resamples=500, seed=42)
    ci_weak, _ = _bootstrap_spearman_ci(xs, ys_weak, n_resamples=500, seed=42)
    assert ci_strong is not None
    assert ci_weak is not None

    width_strong = ci_strong[1] - ci_strong[0]
    width_weak = ci_weak[1] - ci_weak[0]
    assert width_weak > width_strong
    assert width_strong == 0.0


def test_bootstrap_ci_skips_degenerate_resamples_without_crashing() -> None:
    """Heavily duplicated x-values make degenerate (zero-variance) resamples likely.

    3 of 4 records share x=5.0; a bootstrap resample that only draws from those
    three indices collapses to a constant x array, which is undefined for rho.
    This must be skipped, not raise, and the skip count must be reported.
    """
    xs = [5.0, 5.0, 5.0, 1.0]
    ys = [10.0, 12.0, 11.0, 1.0]
    ci, skipped = _bootstrap_spearman_ci(xs, ys, n_resamples=2000, seed=42)
    assert ci is not None
    assert skipped > 5  # non-trivial fraction of 2000 resamples land on the 3 duplicate x's


def test_bootstrap_ci_returns_none_when_no_resamples_are_usable() -> None:
    """n_resamples=0 -> the resample loop never runs -> fewer than 2 usable rhos."""
    xs = [1.0, 2.0, 3.0]
    ys = [3.0, 1.0, 2.0]
    ci, skipped = _bootstrap_spearman_ci(xs, ys, n_resamples=0, seed=42)
    assert ci is None
    assert skipped == 0


# ── (g) success_field parameter — old (binary) vs. new (continuous) ground truth ──


def test_build_correlation_table_success_field_selects_ground_truth() -> None:
    """success_field picks which ground-truth column drives the correlation.

    Constructed so ``x`` rises with ``task_success_rate`` (continuous, "new") but
    falls with ``task_success_rate_binary`` ("old") -- if success_field were
    ignored, both calls would return the same sign.
    """
    records = [
        {
            "name": f"r{i}",
            "task_success_rate": 0.1 * (i + 1),
            "task_success_rate_binary": 1.0 - 0.2 * i,
            "dimension_scores": {"x": 10.0 * (i + 1)},
            "overall_score": 10.0 * (i + 1),
            "baseline_desc_length": 10.0,
            "baseline_single_prompt": 10.0,
        }
        for i in range(6)
    ]

    table_continuous = build_correlation_table(records, fields=("x",))
    table_binary = build_correlation_table(
        records, fields=("x",), success_field="task_success_rate_binary"
    )

    assert table_continuous["x"]["rho"] == 1.0
    assert table_binary["x"]["rho"] == -1.0
