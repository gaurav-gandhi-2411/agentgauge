"""Task 3: re-verify false-alarm-under-null on the NEW (v2.1) estimator,
using real historical data (not a synthetic model) -- the same "run this
tool set against itself" methodology as the original v2 false-alarm test
(scripts/v2_false_alarm_and_determinism.py), adapted for the paired/
task-clustered/CUPED estimator.

Method: for each of the real historical tool sets (which each already have
a fixed, consistent set of task_tool_names), and for each of its tasks,
bootstrap-resample that task's own trial pool TWICE independently (a
"before" resample and an "after" resample) -- this simulates "running this
exact tool set's exact task set twice", the definition of the null
hypothesis. The two resamples share the same task_tool_name set by
construction (same tool set), so `diff_server_level`'s pairing requirement
is met naturally and validly -- this is not a workaround, it is what pairing
on a real repeated tool-set run actually looks like.

Zero live inference. Deterministic (seed derived from tool-set index and
repeat index, not global mutable state).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from agentgauge.harness import TrialOutcome, Verdict, _lcg_random, diff_server_level

RESULTS_PATH = Path("evals/fixtures/predictive_validity/results_raw.json")
OUT_PATH = Path("evals/fixtures/v2_1_false_alarm_new_estimator.json")

N_REPEATS_PER_TOOLSET = 50


def _load_task_trial_pools() -> dict[str, dict[str, list[TrialOutcome]]]:
    """{tool_set_name: {task_tool_name: [TrialOutcome, ...]}}"""
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict[str, list[TrialOutcome]]] = {}
    for rec in data:
        results = rec.get("run_results")
        if not results:
            continue
        groups: dict[str, list[TrialOutcome]] = defaultdict(list)
        for t in results:
            groups[t["task_tool_name"]].append(TrialOutcome.from_dict(t))
        # Only tasks with >=2 trials can be meaningfully bootstrap-resampled
        # into two independent samples; tasks with exactly 1 trial are
        # dropped from this specific null test (not from the product) since
        # a 1-trial "resample" is deterministic and contributes no
        # information about false-alarm behavior either way.
        out[rec["name"]] = {name: trials for name, trials in groups.items() if len(trials) >= 2}
    return out


def main() -> None:
    pools = _load_task_trial_pools()
    eligible = {name: tasks for name, tasks in pools.items() if len(tasks) >= 2}
    print(f"Tool sets loaded: {len(pools)}, eligible (>=2 resamplable tasks): {len(eligible)}")

    verdict_counts: dict[str, int] = {}
    total_comparisons = 0
    false_alarms = []

    for ts_idx, (ts_name, task_pools) in enumerate(sorted(eligible.items())):
        for rep in range(N_REPEATS_PER_TOOLSET):
            seed = (ts_idx * 100000) + rep
            rng = _lcg_random(seed)
            before_trials: list[TrialOutcome] = []
            after_trials: list[TrialOutcome] = []
            for trials in task_pools.values():
                n = len(trials)
                before_sample = [trials[min(int(rng() * n), n - 1)] for _ in range(n)]
                after_sample = [trials[min(int(rng() * n), n - 1)] for _ in range(n)]
                before_trials.extend(before_sample)
                after_trials.extend(after_sample)

            result = diff_server_level(
                before_trials, after_trials, threshold=0.05, use_cuped=True, seed=seed
            )
            total_comparisons += 1
            verdict_counts[result.verdict.value] = verdict_counts.get(result.verdict.value, 0) + 1
            if result.verdict in (Verdict.REGRESSION, Verdict.IMPROVEMENT):
                false_alarms.append(
                    {
                        "tool_set": ts_name,
                        "seed": seed,
                        "verdict": result.verdict.value,
                        "delta": result.delta,
                    }
                )

    false_alarm_rate = 100.0 * len(false_alarms) / total_comparisons
    abstention_rate = 100.0 * verdict_counts.get("insufficient_sensitivity", 0) / total_comparisons
    confident_no_change_rate = 100.0 * verdict_counts.get("no_change", 0) / total_comparisons

    print(f"\nTotal null comparisons: {total_comparisons}")
    print(f"Verdict breakdown: {verdict_counts}")
    print(f"False-alarm rate (REGRESSION or IMPROVEMENT under the null): {false_alarm_rate:.4f}%")
    print(f"INSUFFICIENT_SENSITIVITY (abstention) rate: {abstention_rate:.1f}%")
    print(f"Confident NO_CHANGE rate: {confident_no_change_rate:.1f}%")
    print(
        "(v2 trial-level baseline for comparison: 0.0% false-alarm, 71.5% abstention, "
        "28.5% confident no-change)"
    )

    out = {
        "n_tool_sets_eligible": len(eligible),
        "n_repeats_per_toolset": N_REPEATS_PER_TOOLSET,
        "total_comparisons": total_comparisons,
        "verdict_counts": verdict_counts,
        "false_alarm_rate_pct": false_alarm_rate,
        "abstention_rate_pct": abstention_rate,
        "confident_no_change_rate_pct": confident_no_change_rate,
        "false_alarms": false_alarms,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
