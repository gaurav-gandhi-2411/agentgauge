#!/usr/bin/env python3
"""Task 3c (false-alarm rate under the null) and 3d (replay determinism),
using real historical per-trial data from the predictive-validity study --
zero new inference.

3c method: for each of the 44 valid historical tool sets, its `run_results`
array is a real pool of individual trial outcomes. Two independent bootstrap
resamples of that SAME pool simulate "running this exact tool set twice" --
since both samples are drawn from the identical underlying distribution, ANY
verdict of REGRESSION (or IMPROVEMENT) is by definition a false alarm; there
is no true change between two resamples of the same pool. This measures false-
alarm rate against REAL observed trial-to-trial variance, not an assumed
variance model.

3d method: re-run diff_from_trials on the exact same input data 50 times and
confirm byte-identical output every time -- verifying, not assuming, that the
deterministic core (fixed-seed bootstrap) has no hidden non-determinism.

Usage:
    uv run python scripts/v2_false_alarm_and_determinism.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.harness import TrialOutcome, Verdict, _lcg_random, diff_from_trials

RESULTS_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "predictive_validity" / "results_raw.json"
OUT_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "v2_false_alarm_determinism.json"

N_NULL_TRIALS_PER_TOOLSET = 50  # repeated null comparisons per tool set
THRESHOLD = 0.05


def _load_trial_pools() -> list[tuple[str, list[TrialOutcome]]]:
    with RESULTS_PATH.open(encoding="utf-8") as f:
        data = [r for r in json.load(f) if r.get("error") is None]
    pools = []
    for r in data:
        trials = [TrialOutcome.from_dict(rr) for rr in r["run_results"]]
        if len(trials) >= 4:  # need enough to resample meaningfully
            pools.append((r["name"], trials))
    return pools


def measure_false_alarm_rate() -> dict:
    pools = _load_trial_pools()
    print(f"Loaded {len(pools)} real historical trial pools")

    rng = _lcg_random(seed=123)  # distinct seed from the harness's own internal seed=42
    n_total = 0
    n_false_alarms = 0
    per_toolset_results = []
    for name, trials in pools:
        n = len(trials)
        false_alarms_here = 0
        for _ in range(N_NULL_TRIALS_PER_TOOLSET):
            sample_a = [trials[int(rng() * n)] for _ in range(n)]
            sample_b = [trials[int(rng() * n)] for _ in range(n)]
            result = diff_from_trials(sample_a, sample_b, threshold=THRESHOLD, n_resamples=500, seed=42)
            n_total += 1
            if result.verdict in (Verdict.REGRESSION, Verdict.IMPROVEMENT):
                n_false_alarms += 1
                false_alarms_here += 1
        per_toolset_results.append(
            {"name": name, "n_trials": n, "false_alarms": false_alarms_here, "n_comparisons": N_NULL_TRIALS_PER_TOOLSET}
        )

    rate = n_false_alarms / n_total
    print(f"Total null comparisons: {n_total}")
    print(f"False alarms (REGRESSION or IMPROVEMENT verdict on a true null): {n_false_alarms}")
    print(f"False-alarm rate under the null: {rate:.4%}")
    return {"n_total": n_total, "n_false_alarms": n_false_alarms, "rate": rate, "per_toolset": per_toolset_results}


def measure_determinism() -> dict:
    pools = _load_trial_pools()
    name, trials = pools[0]
    half = len(trials) // 2
    before, after = trials[:half], trials[half:]

    n_runs = 50
    results = []
    for _ in range(n_runs):
        r = diff_from_trials(before, after, threshold=THRESHOLD, n_resamples=500, seed=42)
        results.append((round(r.delta, 10), round(r.ci_lo, 10), round(r.ci_hi, 10), r.verdict.value, r.message))

    all_identical = len(set(results)) == 1
    print(f"\nDeterminism check on '{name}': {n_runs} repeated runs, identical input")
    print(f"All byte-identical: {all_identical}  (unique outputs: {len(set(results))})")
    return {"tool_set": name, "n_runs": n_runs, "all_identical": all_identical, "n_unique_outputs": len(set(results))}


def main() -> None:
    false_alarm_result = measure_false_alarm_rate()
    determinism_result = measure_determinism()
    OUT_PATH.write_text(
        json.dumps({"false_alarm": false_alarm_result, "determinism": determinism_result}, indent=2),
        encoding="utf-8",
    )
    print(f"\nWritten: {OUT_PATH}")


if __name__ == "__main__":
    main()
