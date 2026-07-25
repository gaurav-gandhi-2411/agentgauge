"""Task 1 (v2.1 statistical power rebuild): measure the variance structure of
the existing 5,535 trial records BEFORE changing the harness estimator.

Zero inference -- reads evals/fixtures/predictive_validity/results_raw.json
only. Answers three pre-registered questions (per the v2.1 task brief):

1a. ICC of trial outcomes within (tool_set, task). High ICC means repeated
    trials on the same task carry little independent information, so the
    existing MDE table (which treats trials as independent) is OPTIMISTIC.
1b. Nested variance decomposition: between-tool-set / between-task-within-set /
    between-trial-within-task, as a share of total sum of squares. Tells us
    which axis (more tool sets? more tasks? more trials?) actually buys power.
1c. Correlation between before-arm and after-arm mean outcomes on matched
    tasks in the 5 Phase-3 fixer pairs (bad -> *_fixed). This is the rho a
    paired design would exploit.

All computations are dependency-free (no numpy/scipy), matching this repo's
existing deterministic-simulation style (agentgauge/harness.py).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

RESULTS_PATH = Path("evals/fixtures/predictive_validity/results_raw.json")
OUT_PATH = Path("evals/fixtures/v2_variance_structure.json")

PHASE3_PAIRS = [
    ("grounded_server", "grounded_server_fixed"),
    ("confusable_server", "confusable_server_fixed"),
    ("mediocre_server", "mediocre_server_fixed"),
    ("call_constraints_server", "call_constraints_server_fixed"),
    ("call_constraints_v2_server", "call_constraints_v2_server_fixed"),
]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _load_groups() -> dict[str, dict[str, list[float]]]:
    """{tool_set_name: {task_tool_name: [constraint_satisfaction, ...]}}"""
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict[str, list[float]]] = {}
    for rec in data:
        results = rec.get("run_results")
        if not results:
            continue
        groups: dict[str, list[float]] = defaultdict(list)
        for t in results:
            cs = t.get("constraint_satisfaction")
            if cs is not None:
                groups[t["task_tool_name"]].append(float(cs))
        out[rec["name"]] = dict(groups)
    return out


def task1a_icc(groups: dict[str, dict[str, list[float]]]) -> dict:
    """One-way random-effects ICC(1) across (tool_set, task) groups, unbalanced
    ANOVA formula (Shrout & Fleiss 1979 / McGraw & Wong 1996 ICC(1)):

        MSB = between-group mean square
        MSW = within-group (residual) mean square
        n0  = (N - sum(n_i^2)/N) / (k - 1)     [Fisher's adjusted average group size]
        ICC = (MSB - MSW) / (MSB + (n0 - 1) * MSW)

    Groups with a single trial contribute to MSB but not to MSW's df; standard
    unbalanced-ANOVA handling (they still count toward N and k).
    """
    all_groups: list[list[float]] = []
    for task_groups in groups.values():
        for vals in task_groups.values():
            if len(vals) >= 1:
                all_groups.append(vals)

    N = sum(len(g) for g in all_groups)
    k = len(all_groups)
    grand_mean = sum(sum(g) for g in all_groups) / N

    ss_between = sum(len(g) * (_mean(g) - grand_mean) ** 2 for g in all_groups)
    ss_within = sum(sum((x - _mean(g)) ** 2 for x in g) for g in all_groups)

    df_between = k - 1
    df_within = N - k

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within if df_within > 0 else 0.0

    sum_ni2 = sum(len(g) ** 2 for g in all_groups)
    n0 = (N - sum_ni2 / N) / df_between

    if ms_within == 0.0:
        # Zero measurable within-group variance: ICC is at its ceiling (1.0),
        # not undefined -- ms_between > 0 whenever task means differ at all.
        icc = 1.0 if ms_between > 0 else 0.0
    else:
        icc = (ms_between - ms_within) / (ms_between + (n0 - 1) * ms_within)
    icc = max(0.0, min(1.0, icc))

    m_bar = N / k  # average trials per (tool_set, task) group
    n_eff = N / (1 + (m_bar - 1) * icc)

    n_multi = sum(1 for g in all_groups if len(g) >= 2)
    n_zero_var = sum(1 for g in all_groups if len(g) >= 2 and len(set(round(x, 6) for x in g)) == 1)

    return {
        "n_trials_total": N,
        "n_groups": k,
        "mean_trials_per_group": m_bar,
        "ms_between": ms_between,
        "ms_within": ms_within,
        "n0_adjusted_group_size": n0,
        "icc": icc,
        "n_eff": n_eff,
        "n_groups_with_multiple_trials": n_multi,
        "n_groups_zero_within_group_variance": n_zero_var,
        "pct_groups_zero_within_group_variance": 100.0 * n_zero_var / n_multi if n_multi else 0.0,
    }


def task1b_variance_decomposition(groups: dict[str, dict[str, list[float]]]) -> dict:
    """Nested sum-of-squares decomposition: SS_total = SS_toolset + SS_task
    (within toolset) + SS_trial (residual, within task). This identity holds
    exactly for any (balanced or unbalanced) nested design -- no distributional
    assumption beyond the nesting structure itself.
    """
    all_trials: list[float] = []
    for task_groups in groups.values():
        for vals in task_groups.values():
            all_trials.extend(vals)
    grand_mean = _mean(all_trials)
    ss_total = sum((x - grand_mean) ** 2 for x in all_trials)

    ss_toolset = 0.0
    ss_task = 0.0
    ss_trial = 0.0
    for task_groups in groups.values():
        toolset_vals = [x for vals in task_groups.values() for x in vals]
        n_ts = len(toolset_vals)
        mean_ts = _mean(toolset_vals)
        ss_toolset += n_ts * (mean_ts - grand_mean) ** 2
        for vals in task_groups.values():
            n_t = len(vals)
            mean_t = _mean(vals)
            ss_task += n_t * (mean_t - mean_ts) ** 2
            ss_trial += sum((x - mean_t) ** 2 for x in vals)

    return {
        "ss_total": ss_total,
        "ss_between_toolset": ss_toolset,
        "ss_between_task_within_toolset": ss_task,
        "ss_between_trial_within_task": ss_trial,
        "pct_between_toolset": 100.0 * ss_toolset / ss_total,
        "pct_between_task_within_toolset": 100.0 * ss_task / ss_total,
        "pct_between_trial_within_task": 100.0 * ss_trial / ss_total,
        "identity_check_sum_of_parts": ss_toolset + ss_task + ss_trial,
    }


def _spearman(xs: list[float], ys: list[float]) -> tuple[float, int]:
    def rank(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for kk in range(i, j + 1):
                ranks[order[kk]] = avg
            i = j + 1
        return ranks

    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = _mean(rx), _mean(ry)
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    sx = math.sqrt(sum((v - mx) ** 2 for v in rx))
    sy = math.sqrt(sum((v - my) ** 2 for v in ry))
    if sx == 0 or sy == 0:
        return 0.0, n
    return cov / (sx * sy), n


def task1c_before_after_correlation(groups: dict[str, dict[str, list[float]]]) -> dict:
    before_means: list[float] = []
    after_means: list[float] = []
    per_pair = []
    for before_name, after_name in PHASE3_PAIRS:
        before_tasks = groups.get(before_name, {})
        after_tasks = groups.get(after_name, {})
        shared = sorted(set(before_tasks) & set(after_tasks))
        pair_before = [_mean(before_tasks[t]) for t in shared]
        pair_after = [_mean(after_tasks[t]) for t in shared]
        before_means.extend(pair_before)
        after_means.extend(pair_after)
        rho, n = _spearman(pair_before, pair_after) if len(shared) >= 3 else (None, len(shared))
        per_pair.append(
            {
                "before": before_name,
                "after": after_name,
                "n_matched_tasks": len(shared),
                "spearman_rho": rho,
            }
        )

    pooled_rho, pooled_n = _spearman(before_means, after_means)
    # Pearson too, since the paired-design variance-reduction formula this
    # feeds into (Var(diff) = Var(before)+Var(after)-2*rho*sd(before)*sd(after))
    # is a Pearson-correlation identity, not a Spearman one.
    mb, ma = _mean(before_means), _mean(after_means)
    cov = sum((before_means[i] - mb) * (after_means[i] - ma) for i in range(pooled_n))
    sdb = math.sqrt(sum((v - mb) ** 2 for v in before_means) / pooled_n)
    sda = math.sqrt(sum((v - ma) ** 2 for v in after_means) / pooled_n)
    pooled_pearson = cov / (pooled_n * sdb * sda) if sdb > 0 and sda > 0 else 0.0

    return {
        "per_pair": per_pair,
        "n_matched_tasks_pooled": pooled_n,
        "pooled_spearman_rho": pooled_rho,
        "pooled_pearson_r": pooled_pearson,
    }


def main() -> None:
    groups = _load_groups()

    print("=== 1a. ICC of trial outcomes within (tool_set, task) ===")
    icc_result = task1a_icc(groups)
    for k, v in icc_result.items():
        print(f"  {k}: {v}")

    print("\n=== 1b. Nested variance decomposition ===")
    var_result = task1b_variance_decomposition(groups)
    for k, v in var_result.items():
        print(f"  {k}: {v}")

    print("\n=== 1c. Before/after correlation on matched Phase-3 tasks ===")
    corr_result = task1c_before_after_correlation(groups)
    for row in corr_result["per_pair"]:
        print(f"  {row}")
    print(f"  pooled n={corr_result['n_matched_tasks_pooled']}")
    print(f"  pooled Spearman rho = {corr_result['pooled_spearman_rho']:.4f}")
    print(f"  pooled Pearson r    = {corr_result['pooled_pearson_r']:.4f}")

    out = {
        "icc": icc_result,
        "variance_decomposition": var_result,
        "before_after_correlation": corr_result,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
