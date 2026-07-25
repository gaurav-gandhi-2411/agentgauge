"""Task 2 (v2.2): re-measure false-alarm rate stratified by cluster count,
after switching to a t(G-1)-critical-value CI for G<30 matched tasks
(agentgauge.harness.diff_server_level, _FEW_CLUSTERS_THRESHOLD=30). A
Rademacher wild bootstrap was tried first and measured (via this exact
script) to give a NARROWER, not wider, CI at this repo's actual small-G
counts (4-8) -- see reports/v2_2_few_clusters_correction.md.

Same null-hypothesis methodology as the v2.1 measurement
(scripts/v2_1_false_alarm_new_estimator.py): for each real historical tool
set, bootstrap-resample each task's own trial pool into two independent
samples ("running this exact tool set twice"), run diff_server_level, and
tally REGRESSION/IMPROVEMENT verdicts as false alarms. Reports the false-
alarm rate separately for <10-task, 10-29-task, and >=30-task strata (the
first split is what v2.1 already measured as 1.71% vs 0.07%; the new
30-cluster boundary is where the estimator itself switches bootstrap method).

Zero live inference. Deterministic (seed derived from tool-set index and
repeat index).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from agentgauge.harness import TrialOutcome, Verdict, _lcg_random, diff_server_level

RESULTS_PATH = Path("evals/fixtures/predictive_validity/results_raw.json")
OUT_PATH = Path("evals/fixtures/v2_2_few_clusters_correction.json")

N_REPEATS_PER_TOOLSET = 50


def _load_task_trial_pools() -> dict[str, dict[str, list[TrialOutcome]]]:
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict[str, list[TrialOutcome]]] = {}
    for rec in data:
        results = rec.get("run_results")
        if not results:
            continue
        groups: dict[str, list[TrialOutcome]] = defaultdict(list)
        for t in results:
            groups[t["task_tool_name"]].append(TrialOutcome.from_dict(t))
        out[rec["name"]] = {name: trials for name, trials in groups.items() if len(trials) >= 2}
    return out


def _stratum(n_tasks: int) -> str:
    if n_tasks < 10:
        return "<10 tasks"
    if n_tasks < 30:
        return "10-29 tasks"
    return ">=30 tasks"


def main() -> None:
    pools = _load_task_trial_pools()
    eligible = {name: tasks for name, tasks in pools.items() if len(tasks) >= 2}
    print(f"Tool sets: {len(eligible)}")

    by_stratum: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "false_alarms": 0, "insufficient": 0, "no_change": 0}
    )
    false_alarms = []

    for ts_idx, (ts_name, task_pools) in enumerate(sorted(eligible.items())):
        n_tasks = len(task_pools)
        stratum = _stratum(n_tasks)
        for rep in range(N_REPEATS_PER_TOOLSET):
            seed = (ts_idx * 100000) + rep
            rng = _lcg_random(seed)
            before_trials: list[TrialOutcome] = []
            after_trials: list[TrialOutcome] = []
            for trials in task_pools.values():
                n = len(trials)
                before_trials += [trials[min(int(rng() * n), n - 1)] for _ in range(n)]
                after_trials += [trials[min(int(rng() * n), n - 1)] for _ in range(n)]

            result = diff_server_level(
                before_trials, after_trials, threshold=0.05, use_cuped=True, seed=seed
            )
            by_stratum[stratum]["total"] += 1
            if result.verdict in (Verdict.REGRESSION, Verdict.IMPROVEMENT):
                by_stratum[stratum]["false_alarms"] += 1
                false_alarms.append(
                    {
                        "tool_set": ts_name,
                        "n_tasks": n_tasks,
                        "seed": seed,
                        "verdict": result.verdict.value,
                        "delta": result.delta,
                        "used_few_clusters_correction": result.used_few_clusters_correction,
                    }
                )
            elif result.verdict == Verdict.INSUFFICIENT_SENSITIVITY:
                by_stratum[stratum]["insufficient"] += 1
            else:
                by_stratum[stratum]["no_change"] += 1

    print(f"\n{'Stratum':>15} {'n comparisons':>14} {'false alarms':>13} {'FA rate':>10}")
    summary = {}
    for stratum, counts in sorted(by_stratum.items()):
        rate = 100.0 * counts["false_alarms"] / counts["total"] if counts["total"] else 0.0
        summary[stratum] = {**counts, "false_alarm_rate_pct": rate}
        print(f"{stratum:>15} {counts['total']:>14} {counts['false_alarms']:>13} {rate:>9.2f}%")

    all_pass = all(s["false_alarm_rate_pct"] < 5.0 for s in summary.values())
    print(f"\nAll strata < 5% target: {all_pass}")

    out = {
        "n_repeats_per_toolset": N_REPEATS_PER_TOOLSET,
        "by_stratum": summary,
        "false_alarms": false_alarms,
        "all_strata_under_5pct": all_pass,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
