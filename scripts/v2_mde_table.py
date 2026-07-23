#!/usr/bin/env python3
"""Compute the real minimum-detectable-effect (MDE) table for Task 3b.

Baseline rate (0.75) is the actual mean task_success_rate across the 44 valid
records in evals/fixtures/predictive_validity/results_raw.json, not an
assumption -- see the printed derivation. Also computes at 0.5 (a
higher-variance scenario, since binomial variance peaks at p=0.5) so the
report shows how much the MDE depends on the baseline rate itself.

Pure simulation, zero inference cost. Takes a few minutes for n_simulations=1000
at 4 trial counts x 2 power levels x 2 baseline rates = 16 MDE estimates, each
doing a 12-step bisection x 1000 simulations x 200 inner bootstrap resamples.

Usage:
    uv run python scripts/v2_mde_table.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.harness import simulate_minimum_detectable_effect

OUT_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "v2_mde_table.json"


def derive_baseline_rate() -> float:
    path = Path(__file__).parent.parent / "evals" / "fixtures" / "predictive_validity" / "results_raw.json"
    with path.open(encoding="utf-8") as f:
        data = [r for r in json.load(f) if r.get("error") is None]
    rates = [r["task_success_rate"] for r in data]
    mean_rate = sum(rates) / len(rates)
    print(f"Derived baseline rate from {len(rates)} real records: mean task_success_rate = {mean_rate:.4f}")
    return mean_rate


def main() -> None:
    real_baseline = derive_baseline_rate()
    baseline_rates = {"real_study_mean (0.75)": round(real_baseline, 2), "worst_case_variance (0.50)": 0.5}
    n_trials_options = [5, 10, 20, 50]
    power_options = [0.80, 0.95]

    results = []
    for baseline_label, baseline_rate in baseline_rates.items():
        for n_trials in n_trials_options:
            for power in power_options:
                print(f"Computing MDE: baseline={baseline_label} n_trials={n_trials} power={power} ...", flush=True)
                mde = simulate_minimum_detectable_effect(
                    baseline_rate=baseline_rate,
                    n_trials=n_trials,
                    power=power,
                    n_simulations=1000,
                    seed=42,
                )
                results.append(
                    {
                        "baseline_label": baseline_label,
                        "baseline_rate": baseline_rate,
                        "n_trials": n_trials,
                        "power": power,
                        "mde": round(mde, 4),
                    }
                )
                print(f"  -> MDE = {mde:.4f}")

    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWritten: {OUT_PATH}")

    print(f"\n{'baseline':30s} {'n_trials':>9} {'power':>7} {'MDE':>8}")
    for r in results:
        print(f"{r['baseline_label']:30s} {r['n_trials']:9d} {r['power']:7.2f} {r['mde']:8.4f}")


if __name__ == "__main__":
    main()
