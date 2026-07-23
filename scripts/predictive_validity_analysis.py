#!/usr/bin/env python3
"""Predictive-validity analysis: correlate AgentGauge's axis scores with task success.

Pure, network-free functions that operate on the `results_raw.json` shape produced by
scripts/predictive_validity_study.py (a `list[dict]`). File I/O is confined to
`main()` so the core logic is unit-testable on fabricated data — see
tests/test_predictive_validity_analysis.py.

No scipy dependency: this repo does not declare scipy in pyproject.toml (see
scripts/run_frontier_t18.py's "no scipy" sign test for the established precedent).
Spearman's rho and its two-tailed p-value are computed from scratch below: rank ->
Pearson correlation of ranks -> Student's t p-value via the regularized incomplete
beta function (Numerical Recipes 6.4.9), a standard closed-form result, not an
approximation shortcut.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

RESULTS_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "predictive_validity" / "results_raw.json"
)

# Correlate task_success_rate against each of these. docs_manifest is deliberately
# NOT in this list: every fixture in the manifest connects via stdio (no base_url),
# so score_docs_manifest floors at exactly 20.0 for every record — a degenerate,
# zero-variance input by construction (see agentgauge/CLAUDE.md docs_manifest notes).
# build_correlation_table() still emits a "docs_manifest" entry documenting the
# exclusion, so the table's key set is stable and self-explanatory.
CORRELATION_FIELDS: tuple[str, ...] = (
    "description_quality",
    "discoverability",
    "schema_completeness",
    "selection_accuracy",
    "call_correctness",
    "error_legibility",
    "robustness",
    "overall_score",
    "baseline_desc_length",
    "baseline_single_prompt",
)

# Fields whose values live at the top level of a record rather than under
# record["dimension_scores"].
_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    {"overall_score", "task_success_rate", "baseline_desc_length", "baseline_single_prompt"}
)

# A field is treated as degenerate (near-constant) when its population variance falls
# below this. Guards against reporting a spurious/NaN correlation on a constant array.
_VARIANCE_EPS = 1e-9


def _get_field_value(record: dict[str, Any], field: str) -> float | None:
    """Look up a scalar field from one results_raw.json-shaped record.

    Dimension names (e.g. "description_quality") live under
    ``record["dimension_scores"]``; everything else is a top-level key. Returns
    ``None`` when the field is missing or explicitly null (e.g. a baseline whose judge
    response failed to parse).
    """
    if field in _TOP_LEVEL_FIELDS:
        val = record.get(field)
    else:
        val = record.get("dimension_scores", {}).get(field)
    return None if val is None else float(val)


def _variance(values: list[float]) -> float:
    """Population variance of ``values`` (0.0 for n<2)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values) / n


def _is_degenerate(values: list[float]) -> bool:
    """True if ``values`` has near-zero variance (constant / near-constant array)."""
    return len(values) < 2 or _variance(values) < _VARIANCE_EPS


def _rank(values: list[float]) -> list[float]:
    """Fractional (average) ranks, 1-indexed. Ties share the mean of their rank span."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _pearsonr(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient, clamped to [-1, 1] against float rounding."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    if denom == 0.0:
        return 0.0
    return max(-1.0, min(1.0, cov / denom))


def _betacf(a: float, b: float, x: float) -> float:
    """Continued-fraction evaluation for the incomplete beta function (Lentz's method).

    Numerical Recipes in C, 2nd ed., section 6.4 — standard, dependency-free.
    """
    max_iter = 200
    eps = 3e-12
    fp_min = 1e-300

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fp_min:
        d = fp_min
    d = 1.0 / d
    h = d

    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fp_min:
            d = fp_min
        c = 1.0 + aa / c
        if abs(c) < fp_min:
            c = fp_min
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fp_min:
            d = fp_min
        c = 1.0 + aa / c
        if abs(c) < fp_min:
            c = fp_min
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break

    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _t_two_tailed_p(t: float, df: int) -> float:
    """Two-tailed p-value for Student's t-distribution: P(|T| > |t|) with `df` d.o.f."""
    if df <= 0:
        return 1.0
    x = df / (df + t * t)
    return _betai(df / 2.0, 0.5, x)


def _spearmanr(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Spearman's rank correlation and its two-tailed p-value. No scipy required."""
    n = len(xs)
    rho = _pearsonr(_rank(xs), _rank(ys))
    if n <= 2:
        return rho, 1.0
    if abs(rho) >= 1.0:
        return rho, 0.0
    t = rho * math.sqrt((n - 2) / (1.0 - rho**2))
    p = _t_two_tailed_p(abs(t), n - 2)
    return rho, p


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile of a pre-sorted list (matches numpy's default).

    ``pct`` is 0-100. Assumes ``sorted_values`` is already sorted ascending and
    non-empty.
    """
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (n - 1)
    lo_idx = math.floor(rank)
    hi_idx = math.ceil(rank)
    if lo_idx == hi_idx:
        return sorted_values[int(rank)]
    frac = rank - lo_idx
    return sorted_values[lo_idx] + frac * (sorted_values[hi_idx] - sorted_values[lo_idx])


def _bootstrap_spearman_ci(
    xs: list[float],
    ys: list[float],
    *,
    n_resamples: int = 2000,
    seed: int = 42,
    ci_low_pct: float = 2.5,
    ci_high_pct: float = 97.5,
) -> tuple[tuple[float, float] | None, int]:
    """Percentile bootstrap 95% CI for Spearman rho, resampling the ``(x, y)`` pairs.

    Draws ``n_resamples`` bootstrap samples (each the same size as ``xs``/``ys``,
    drawn with replacement, index-paired so x and y stay matched) using a
    deterministic ``random.Random(seed)`` for reproducibility, recomputes rho on
    each resample with the existing hand-rolled ``_spearmanr``, and returns the
    ``[ci_low_pct, ci_high_pct]`` percentile interval of the resulting rho
    distribution.

    A resample can land on a constant (zero-variance) x or y array purely from
    the luck of the draw — e.g. every one of n indices happens to repeat a tied
    value — in which case rho is undefined. Those resamples are skipped rather
    than fed into ``_spearmanr`` (which would divide by zero). If fewer than 2
    usable resamples remain, ``(None, n_resamples)`` is returned: not enough
    signal to report a percentile interval.

    Returns ``(ci, skipped)`` where ``ci`` is ``(lo, hi)`` rounded to 4 decimals
    or ``None``, and ``skipped`` is the count of degenerate resamples discarded.
    """
    n = len(xs)
    rng = random.Random(seed)
    rhos: list[float] = []
    skipped = 0
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        rx = [xs[i] for i in idx]
        ry = [ys[i] for i in idx]
        if _is_degenerate(rx) or _is_degenerate(ry):
            skipped += 1
            continue
        rho, _ = _spearmanr(rx, ry)
        rhos.append(rho)

    if len(rhos) < 2:
        return None, skipped

    rhos.sort()
    lo = _percentile(rhos, ci_low_pct)
    hi = _percentile(rhos, ci_high_pct)
    return (round(lo, 4), round(hi, 4)), skipped


def _effect_size_label(rho: float | None) -> str | None:
    """Plain-language read of a Spearman rho magnitude (rough, standard convention).

    ``|rho| < 0.1`` -> "negligible", ``0.1-0.3`` -> "small", ``0.3-0.5`` ->
    "moderate", ``> 0.5`` -> "large". Returns ``None`` when ``rho`` is ``None``
    (correlation wasn't computed for this field).
    """
    if rho is None:
        return None
    magnitude = abs(rho)
    if magnitude > 0.5:
        return "large"
    if magnitude > 0.3:
        return "moderate"
    if magnitude > 0.1:
        return "small"
    return "negligible"


def build_correlation_table(
    records: list[dict[str, Any]],
    fields: tuple[str, ...] = CORRELATION_FIELDS,
    *,
    success_field: str = "task_success_rate",
    n_bootstrap: int = 2000,
    bootstrap_seed: int = 42,
) -> dict[str, dict[str, Any]]:
    """Spearman correlation of ``success_field`` against each of ``fields``.

    ``success_field`` defaults to ``"task_success_rate"`` (the continuous
    fractional constraint-satisfaction ground truth). Pass
    ``"task_success_rate_binary"`` to run the same table against the preserved
    binary ground truth on the same records, for an old-vs-new metric
    comparison that isolates metric-shape from trial-count.

    Returns a dict keyed by field name, each value ``{"n", "rho", "p_value",
    "ci", "effect_size", "ci_skipped", "status"}``. ``status`` is one of:
      - "ok": correlation computed normally.
      - "insufficient_n": fewer than 3 paired (field, success_field) values.
      - "degenerate — excluded": field or success_field had near-zero variance
        across the paired records — computing a correlation on a constant array is
        undefined/spurious (scipy would emit a warning and return NaN); this is
        detected generically (any near-zero-variance field), not just for
        docs_manifest by name.

    ``ci`` is a ``[lo, hi]`` 95% percentile bootstrap confidence interval for rho
    (``n_bootstrap`` resamples, seeded with ``bootstrap_seed`` for
    reproducibility — see ``_bootstrap_spearman_ci``), or ``None`` when status is
    not "ok" or too few resamples were usable. ``effect_size`` is a
    plain-language magnitude label from ``_effect_size_label``, or ``None`` when
    ``rho`` is ``None``. ``ci_skipped`` is the count of bootstrap resamples
    discarded for landing on a degenerate (zero-variance) resample; 0 for
    non-"ok" statuses.

    Additionally always includes a ``"docs_manifest"`` entry with status
    "excluded_by_construction" — docs_manifest is never in ``fields`` because every
    manifest fixture connects via stdio, so it floors at a constant 20.0 by design
    (see CLAUDE.md). This keeps the table self-documenting rather than silently
    omitting the dimension.
    """
    table: dict[str, dict[str, Any]] = {}
    task_success = [r.get(success_field) for r in records]

    for field in fields:
        pairs = [
            (x, y)
            for r, y in zip(records, task_success, strict=True)
            if y is not None and (x := _get_field_value(r, field)) is not None
        ]
        n = len(pairs)
        if n < 3:
            table[field] = {
                "n": n,
                "rho": None,
                "p_value": None,
                "ci": None,
                "effect_size": None,
                "ci_skipped": 0,
                "status": "insufficient_n",
            }
            continue

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        if _is_degenerate(xs) or _is_degenerate(ys):
            table[field] = {
                "n": n,
                "rho": None,
                "p_value": None,
                "ci": None,
                "effect_size": None,
                "ci_skipped": 0,
                "status": "degenerate — excluded",
            }
            continue

        rho, p_value = _spearmanr(xs, ys)
        ci, ci_skipped = _bootstrap_spearman_ci(
            xs, ys, n_resamples=n_bootstrap, seed=bootstrap_seed
        )
        table[field] = {
            "n": n,
            "rho": round(rho, 4),
            "p_value": round(p_value, 4),
            "ci": list(ci) if ci is not None else None,
            "effect_size": _effect_size_label(rho),
            "ci_skipped": ci_skipped,
            "status": "ok",
        }

    table["docs_manifest"] = {
        "n": len(records),
        "rho": None,
        "p_value": None,
        "ci": None,
        "effect_size": None,
        "ci_skipped": 0,
        "status": "excluded_by_construction",
    }
    return table


def _minmax_rescale(values: list[float]) -> list[float]:
    """Rescale ``values`` to 0-100 (midpoint 50.0 for a degenerate/constant input)."""
    lo, hi = min(values), max(values)
    if hi - lo < _VARIANCE_EPS:
        return [50.0 for _ in values]
    return [100.0 * (v - lo) / (hi - lo) for v in values]


def find_axis_flagged_cases(
    records: list[dict[str, Any]],
    *,
    axis: str = "discoverability",
    max_results: int = 5,
    low_success_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Surface tool sets where ``axis`` catches a real problem the baselines missed.

    Heuristic (explicit, auditable — not a black-box ranking):
      1. Restrict to records with a CONFIRMED real problem: task_success_rate <=
         ``low_success_threshold``. Without this filter a large baseline-vs-axis gap
         could just mean the axis is miscalibrated relative to the baseline, not that
         it caught something real.
      2. For each such record, rescale baseline_desc_length to 0-100 (min-max across
         all ``records``, since it is a raw character count, not a 0-100 score) and
         take ``baseline_best = max(baseline_desc_length_rescaled,
         baseline_single_prompt)`` — the more charitable of the two baselines.
      3. ``gap = baseline_best - axis_score``. A positive gap means at least one
         baseline rated the tool set better than AgentGauge's ``axis`` did, on a tool
         set that genuinely failed in practice — i.e. the axis flagged a problem a
         baseline-only view would have missed.
      4. Keep only records with ``gap > 0``, sort descending by gap, return the top
         ``min(max_results, 5)``.

    Returns a list of dicts (empty if no record qualifies), each with the fields
    needed to audit the pick: name, tier, task_success_rate, axis, axis_score,
    baseline_desc_length_rescaled, baseline_single_prompt, gap.
    """
    low_success = [
        r
        for r in records
        if r.get("task_success_rate") is not None
        and r["task_success_rate"] <= low_success_threshold
    ]
    if not low_success:
        return []

    desc_lengths = [float(r.get("baseline_desc_length") or 0.0) for r in records]
    rescaled_by_name = dict(
        zip((r["name"] for r in records), _minmax_rescale(desc_lengths), strict=True)
    )

    candidates: list[dict[str, Any]] = []
    for r in low_success:
        axis_score = _get_field_value(r, axis)
        if axis_score is None:
            continue
        single_prompt = r.get("baseline_single_prompt")
        desc_rescaled = rescaled_by_name[r["name"]]
        baseline_candidates = [v for v in (single_prompt, desc_rescaled) if v is not None]
        if not baseline_candidates:
            continue
        baseline_best = max(baseline_candidates)
        gap = baseline_best - axis_score
        if gap > 0:
            candidates.append(
                {
                    "name": r["name"],
                    "tier": r.get("tier"),
                    "task_success_rate": r["task_success_rate"],
                    "axis": axis,
                    "axis_score": axis_score,
                    "baseline_desc_length_rescaled": round(desc_rescaled, 1),
                    "baseline_single_prompt": single_prompt,
                    "gap": round(gap, 1),
                }
            )

    candidates.sort(key=lambda c: c["gap"], reverse=True)
    return candidates[: min(max_results, 5)]


def main() -> None:
    """CLI entry point: load results_raw.json and print the correlation table + flagged cases."""
    parser = argparse.ArgumentParser(description="Analyze predictive_validity_study.py output")
    parser.add_argument("--results", type=Path, default=RESULTS_PATH)
    parser.add_argument("--axis", default="discoverability")
    args = parser.parse_args()

    if not args.results.exists():
        print(
            f"No results file at {args.results} — run scripts/predictive_validity_study.py first."
        )
        return

    all_records: list[dict[str, Any]] = json.loads(args.results.read_text(encoding="utf-8"))
    records = [r for r in all_records if r.get("error") is None]
    if len(records) < len(all_records):
        print(f"Skipping {len(all_records) - len(records)} failed tool-set record(s).")

    table = build_correlation_table(records)
    print(
        f"\nCorrelation table (Spearman rho, continuous task_success_rate vs. field, "
        f"n={len(records)}, 95% CI via {2000}-resample bootstrap seed=42):"
    )
    for field, result in table.items():
        print(
            f"  {field:<24} n={result['n']:<3} rho={result['rho']}  "
            f"p={result['p_value']}  ci={result['ci']}  effect={result['effect_size']}  "
            f"status={result['status']}"
        )
        if result["ci_skipped"] > 5:
            print(f"    (skipped {result['ci_skipped']}/2000 degenerate bootstrap resamples)")

    binary_table = build_correlation_table(records, success_field="task_success_rate_binary")
    print(
        f"\nOld-vs-new comparison — same records, binary task_success_rate_binary "
        f"vs. field (n={len(records)}):"
    )
    for field, result in binary_table.items():
        print(
            f"  {field:<24} n={result['n']:<3} rho={result['rho']}  "
            f"p={result['p_value']}  ci={result['ci']}  effect={result['effect_size']}  "
            f"status={result['status']}"
        )

    flagged = find_axis_flagged_cases(records, axis=args.axis)
    print(f"\nCases where '{args.axis}' flagged a problem the baselines missed:")
    if not flagged:
        print("  (none)")
    for c in flagged:
        print(
            f"  {c['name']} (tier={c['tier']}): axis_score={c['axis_score']}  "
            f"baseline_desc_length_rescaled={c['baseline_desc_length_rescaled']}  "
            f"baseline_single_prompt={c['baseline_single_prompt']}  "
            f"task_success_rate={c['task_success_rate']}  gap={c['gap']}"
        )


if __name__ == "__main__":
    main()
