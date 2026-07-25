"""Cross-check Task 3b's MDE table against real trial-outcome variance.

Adversarial pass (per the study's standing constraint: "before reporting ANY
positive result, run an adversarial pass specifically hunting for a fifth
[measurement artifact]. Assume it exists.") run before Task 7's product-
readiness report.

`agentgauge.harness.simulate_minimum_detectable_effect` models each trial as a
pure Bernoulli(0/1) draw. But real historical trial outcomes
(evals/fixtures/predictive_validity/results_raw.json) are continuous
partial-credit values -- constraint_satisfaction takes {0.0, 0.5, 0.6667, 1.0},
not just {0.0, 1.0} -- because several tasks have multiple constraints and
partial credit is awarded. A binomial simulation cannot represent that
intermediate-value variance. This script re-derives the same MDE table using
an empirical simulator that draws from the REAL pool of observed outcome
values instead of a synthetic 0/1 draw, and reports whether the discrepancy
moves the headline numbers.

Zero LLM inference. Deterministic (seed=42 throughout).
"""

from __future__ import annotations

import json
from pathlib import Path

from agentgauge.harness import _lcg_random, bootstrap_delta_ci

RESULTS_PATH = Path("evals/fixtures/predictive_validity/results_raw.json")
OUT_PATH = Path("evals/fixtures/v2_mde_continuous_crosscheck.json")


def _load_real_outcome_pool() -> list[float]:
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    pool: list[float] = []
    for rec in data:
        for t in rec.get("run_results", []):
            cs = t.get("constraint_satisfaction")
            if cs is not None:
                pool.append(float(cs))
    return pool


def _success_like_pool(pool: list[float]) -> list[float]:
    """The real, observed distribution of non-zero (partial-or-full-credit)
    outcomes -- {0.5, 0.6667, 1.0} in this dataset -- used as the substrate
    for a "success" draw instead of a flat 1.0."""
    return [v for v in pool if v > 0.0]


def simulate_mde_empirical(
    baseline_rate: float,
    n_trials: int,
    power: float,
    success_pool: list[float],
    n_simulations: int = 1000,
    seed: int = 42,
) -> float:
    """Same binary-search MDE procedure as harness.simulate_minimum_detectable_effect,
    but each "success" draw samples from the real observed non-zero outcome
    distribution instead of a fixed 1.0 -- isolating exactly the one modeling
    assumption in question (outcome shape), nothing else changes.
    """
    rng = _lcg_random(seed)
    n_pool = len(success_pool)

    def _simulate_trials(rate: float, n: int) -> list[float]:
        out = []
        for _ in range(n):
            if rng() < rate:
                out.append(success_pool[min(int(rng() * n_pool), n_pool - 1)])
            else:
                out.append(0.0)
        return out

    def _detects(true_delta: float) -> bool:
        before = _simulate_trials(baseline_rate, n_trials)
        after_rate = max(0.0, min(1.0, baseline_rate + true_delta))
        after = _simulate_trials(after_rate, n_trials)
        _, ci_lo, ci_hi = bootstrap_delta_ci(before, after, n_resamples=200, seed=int(rng() * 1e9))
        return ci_hi < 0 if true_delta < 0 else ci_lo > 0

    lo, hi = 0.0, 1.0 - baseline_rate if baseline_rate < 0.5 else baseline_rate
    for _ in range(12):
        mid = (lo + hi) / 2
        n_detected = sum(1 for _ in range(n_simulations) if _detects(-mid))
        detected_rate = n_detected / n_simulations
        if detected_rate >= power:
            hi = mid
        else:
            lo = mid
    return hi


def main() -> None:
    pool = _load_real_outcome_pool()
    success_pool = _success_like_pool(pool)
    print(f"Real trial pool: n={len(pool)}, distinct values={sorted(set(round(v, 4) for v in pool))}")
    print(f"Non-zero ('success-like') substrate pool: n={len(success_pool)}")

    baseline_rate = sum(pool) / len(pool)
    print(f"Empirical mean (== baseline_rate used in Task 3b): {baseline_rate:.4f}")

    cells = [(n, p) for n in (5, 10, 20, 50) for p in (0.80, 0.95)]
    rows = []
    for n_trials, power in cells:
        mde = simulate_mde_empirical(baseline_rate, n_trials, power, success_pool)
        rows.append(
            {"n_trials": n_trials, "power": power, "baseline_rate": baseline_rate, "mde_empirical": mde}
        )
        print(f"n={n_trials:>2} power={power:.0%} -> MDE(empirical outcome shape) = {mde:.3f}")

    OUT_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
