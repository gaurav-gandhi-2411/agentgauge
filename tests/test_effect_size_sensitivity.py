"""Tests for the v0.5 Wave 1 effect-size sensitivity study (`reports/v0_5_effect_size_sensitivity.md`).

Covers two things:
  (1) `agentgauge.attribution_benchmark.generate_benchmark`'s new `effect_min_pp`/`effect_max_pp`
      parameters -- the band-parameterized generation this study is built on.
  (2) The confound guard (`agentgauge.attribution_benchmark.confound_guard_report` +
      `agentgauge.audit.check_benchmark_construction_diffsize_bias`) still passing at every
      effect band this study measures, not just the original 13.3-28.9pp range.

No live LLM calls anywhere -- same deterministic synthetic ground-truth model the rest of this
repo's attribution benchmark tests use.

`_EFFECT_BANDS` below is intentionally duplicated (not imported) from
`scripts/effect_size_sensitivity_report.py`'s own band list, per this repo's existing convention
for test/script duplication (see `tests/test_t18_fixture.py`'s header comment) -- tests must not
depend on a script's importability.
"""

from __future__ import annotations

from agentgauge.attribution_benchmark import (
    CAUSAL_EFFECT_MAX_PP,
    CAUSAL_EFFECT_MIN_PP,
    confound_guard_report,
    generate_benchmark,
)
from agentgauge.audit import check_benchmark_construction_diffsize_bias

N_TEST_CASES = 24
SEED = 42

# label, effect_min_pp (more negative / larger magnitude), effect_max_pp (less negative /
# smaller magnitude), seed. Mirrors `scripts/effect_size_sensitivity_report.py::EFFECT_BANDS`
# (kept in sync manually -- see module docstring).
_EFFECT_BANDS: tuple[tuple[str, float, float, int], ...] = (
    ("below_mde_3.0_5.0pp", -5.0, -3.0, 42),
    ("straddle_mde_5.0_8.0pp", -8.0, -5.0, 1042),
    ("moderate_8.0_13.3pp", -13.3, -8.0, 2042),
    ("original_13.3_28.9pp", CAUSAL_EFFECT_MIN_PP, CAUSAL_EFFECT_MAX_PP, 3042),
    ("beyond_28.9_33.0pp", -33.0, -28.9, 4042),
)


class TestEffectBandParameterization:
    def test_default_behavior_unchanged(self) -> None:
        """Omitting effect_min_pp/effect_max_pp must reproduce the exact original formula's
        output range -- this repo's existing 50-case benchmark and its tests must not regress."""
        cases = generate_benchmark(n_cases=N_TEST_CASES, seed=SEED)
        for case in cases:
            assert CAUSAL_EFFECT_MIN_PP <= case.true_effect_pp <= CAUSAL_EFFECT_MAX_PP

    def test_true_effect_stays_within_caller_specified_band(self) -> None:
        for _label, min_pp, max_pp, seed in _EFFECT_BANDS:
            cases = generate_benchmark(
                n_cases=N_TEST_CASES, seed=seed, effect_min_pp=min_pp, effect_max_pp=max_pp
            )
            assert len(cases) == N_TEST_CASES
            for case in cases:
                assert min_pp <= case.true_effect_pp <= max_pp, (
                    f"case {case.case_id} true_effect_pp={case.true_effect_pp:.2f} outside "
                    f"requested band [{min_pp}, {max_pp}]"
                )

    def test_deterministic_given_seed_across_bands(self) -> None:
        for _label, min_pp, max_pp, seed in _EFFECT_BANDS:
            cases_a = generate_benchmark(
                n_cases=10, seed=seed, effect_min_pp=min_pp, effect_max_pp=max_pp
            )
            cases_b = generate_benchmark(
                n_cases=10, seed=seed, effect_min_pp=min_pp, effect_max_pp=max_pp
            )
            assert [c.true_effect_pp for c in cases_a] == [c.true_effect_pp for c in cases_b]
            assert [c.true_culprit for c in cases_a] == [c.true_culprit for c in cases_b]

    def test_effect_band_does_not_change_non_effect_draws_at_same_seed(self) -> None:
        """Structural claim (see `generate_benchmark`'s docstring): the effect-magnitude draw
        consumes exactly one PRNG state transition regardless of the interval it's mapped into, so
        for a FIXED seed, every other drawn field (catalog, culprit, decoy set, positions, diff
        sizes) must be bit-identical across different effect bands. This is the mechanistic reason
        a diff-size confound cannot reappear "because of" the effect-band parameterization itself
        (see `reports/v0_5_effect_size_sensitivity.md` section 1a)."""
        narrow = generate_benchmark(
            n_cases=N_TEST_CASES, seed=SEED, effect_min_pp=-5.0, effect_max_pp=-3.0
        )
        wide = generate_benchmark(
            n_cases=N_TEST_CASES, seed=SEED, effect_min_pp=-33.0, effect_max_pp=-28.9
        )
        assert [c.true_culprit for c in narrow] == [c.true_culprit for c in wide]
        assert [c.changed_tools for c in narrow] == [c.changed_tools for c in wide]
        assert [c.diff_chars for c in narrow] == [c.diff_chars for c in wide]
        # The only field that legitimately differs is the effect magnitude itself.
        assert [c.true_effect_pp for c in narrow] != [c.true_effect_pp for c in wide]


class TestConfoundGuardPerBand:
    """The mandatory benchmark-construction confound guard (doctrine Component 1.2), re-run
    independently on each effect band with its own freshly-drawn cases (distinct per-band seed,
    not a reuse of the original 50-case set) -- per the task's explicit instruction not to assume
    the original set's guard pass generalizes to every band. A construction bias could in
    principle reappear only at certain bands if band and tier draws interacted through the shared
    RNG stream -- `TestEffectBandParameterization::
    test_effect_band_does_not_change_non_effect_draws_at_same_seed` already shows this is
    structurally impossible at a FIXED seed; this class is the complementary empirical check with
    genuinely different (per-band) seeds, so it is not a foregone conclusion."""

    _CASES_BY_BAND = {
        label: generate_benchmark(
            n_cases=N_TEST_CASES, seed=seed, effect_min_pp=min_pp, effect_max_pp=max_pp
        )
        for label, min_pp, max_pp, seed in _EFFECT_BANDS
    }
    _REPORTS = {label: confound_guard_report(cases) for label, cases in _CASES_BY_BAND.items()}

    def test_audit_diffsize_bias_check_does_not_fire_in_any_band(self) -> None:
        """`agentgauge.audit.check_benchmark_construction_diffsize_bias` (the standing, reusable
        BLOCK-severity audit for this artifact class -- independent implementation, duck-typed,
        does not import this module) run directly against each band's cases, not just
        `confound_guard_report`'s own statistic."""
        for label, cases in self._CASES_BY_BAND.items():
            findings = check_benchmark_construction_diffsize_bias(cases)
            assert findings == [], (
                f"band {label}: audit check fired: {[f.detail for f in findings]}"
            )

    def test_culprit_position_not_fixed_in_every_band(self) -> None:
        for label, guard in self._REPORTS.items():
            assert guard.n_positions_observed > 1, (
                f"band {label}: true culprit occupied only one position -- positional shortcut "
                "would win by construction"
            )

    def test_culprit_not_always_max_diff_in_every_band(self) -> None:
        for label, guard in self._REPORTS.items():
            assert guard.frac_cases_culprit_is_max_diff < 1.0, (
                f"band {label}: true culprit was the largest-diff tool in EVERY case"
            )

    def test_some_decoy_exceeds_culprit_diff_in_every_band(self) -> None:
        for label, guard in self._REPORTS.items():
            assert guard.frac_cases_a_decoy_exceeds_culprit_diff > 0.0, (
                f"band {label}: no case had a decoy diff larger than the culprit's"
            )

    def test_diffsize_fractional_rank_not_correlated_with_role_in_every_band(self) -> None:
        """Same [0.35, 0.65] band `TestConfoundGuard` uses on the original 50-case set
        (`tests/test_attribution_benchmark.py`), applied independently to each effect band --
        this is the check that would catch a diff-size confound reappearing at a specific band."""
        for label, guard in self._REPORTS.items():
            assert 0.35 <= guard.mean_culprit_fractional_rank <= 0.65, (
                f"band {label}: mean culprit fractional rank "
                f"{guard.mean_culprit_fractional_rank:.4f} is outside the [0.35, 0.65] band -- "
                "diff size correlates with culprit-vs-decoy role at this effect band"
            )
