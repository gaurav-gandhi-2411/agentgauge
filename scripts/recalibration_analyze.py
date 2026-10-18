"""Task 2 analysis pipeline: AgentGauge seed-fix re-calibration (old vs new corpus).

The OLD corpus (evals/fixtures/predictive_validity/results_raw.json) was collected with one
fixed seed for every repeat trial, so repeat trials were (nearly) identical: 650/720
zero-variance groups, ICC=0.7932642721759006.  The NEW corpus is NDJSON, one row per trial,
collected with per-trial varied seeds.  This script compares the two like-for-like:

* variance structure (zero-variance share, ICC, nested variance shares) -- the formulas are
  IMPORTED from scripts/v2_variance_structure.py (not re-derived);
* the four MDE calibration constants (baseline, sigma_task, resid_sd, rho);
* cluster-bootstrap (over TOOL SETS) confidence intervals;
* MDE at 100x1 and 253x1 via agentgauge.harness.simulate_mde_task_level;
* null false-alarm / abstention rate per cluster stratum (logic copied from
  scripts/v2_1_false_alarm_new_estimator.py and v2_2_few_clusters_correction.py).

Zero inference: reads files only.  Pure stdlib (numpy is not a dependency of this repo).
Deterministic: seed 42 for the bootstrap; per-tool-set false-alarm seeds come from a hash of
the tool-set NAME so they do not shift when other tool sets are added or removed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _import_vvs() -> Any:
    """Import scripts/v2_variance_structure.py by path (scripts/ is not a package)."""
    path = Path(__file__).resolve().parent / "v2_variance_structure.py"
    spec = importlib.util.spec_from_file_location("v2_variance_structure", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["v2_variance_structure"] = mod
    spec.loader.exec_module(mod)
    return mod


vvs = _import_vvs()

from agentgauge.harness import (  # noqa: E402  (after sys.path setup)
    CALIBRATED_BASELINE_RATE,
    CALIBRATED_RESID_SD,
    CALIBRATED_RHO,
    CALIBRATED_SIGMA_TASK,
    TrialOutcome,
    Verdict,
    _lcg_random,
    diff_server_level,
    simulate_mde_task_level,
)

SEED = 42
Z95 = 1.959964  # standard normal 97.5th percentile
OLD_CONTROL = {"icc": 0.7932642721759006, "n_zero": 650, "n_multi": 720, "pct_task": 56.06}
MAX_WORKERS = 4  # CPU is shared with a long collection job
STRATA = ("<10 tasks", "10-29 tasks", ">=30 tasks")
PHASE3_SETS = sorted({n for pair in vvs.PHASE3_PAIRS for n in pair})

# ---------------------------------------------------------------------------------------
# Small stats helpers
# ---------------------------------------------------------------------------------------


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion k/n (returns fractions in [0,1])."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def quantile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation quantile of an already sorted list."""
    if not sorted_vals:
        return float("nan")
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------


def load_new_rows(path: Path) -> list[dict[str, Any]]:
    """Read the NDJSON rows; dedupe on (tool_set, task_description, trial_index), last wins."""
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: malformed JSON row: {exc}") from exc
            rows[(row["tool_set"], row["task_description"], int(row["trial_index"]))] = row
    return list(rows.values())


def load_completed(rows: list[dict[str, Any]], status_path: Path | None) -> tuple[list[str], dict]:
    """Tool sets to analyse: run_status.json `completed_tool_sets` if present, else all in rows."""
    present = sorted({r["tool_set"] for r in rows})
    info: dict[str, Any] = {"status_file": None, "rows_tool_sets": present}
    if status_path is not None and status_path.exists():
        st = json.loads(status_path.read_text(encoding="utf-8"))
        completed = sorted(st.get("completed_tool_sets", []))
        info.update(
            status_file=str(status_path),
            not_run_or_partial=st.get("not_run_or_partial_tool_sets", []),
            cap_hit=st.get("cap_hit"),
            completed_declared=completed,
        )
        missing = [c for c in completed if c not in present]
        if missing:
            raise ValueError(f"completed tool sets with no rows: {missing}")
        return completed, info
    info["note"] = "no run_status.json found; treating every tool set present in rows as complete"
    return present, info


def groups_from_rows(
    rows: list[dict[str, Any]], tool_sets: list[str], by: str, value: str
) -> dict[str, dict[str, list[float]]]:
    """{tool_set: {group_key: [values]}} from new rows.

    by: 'gold' -> group key = task_tool_name (like-for-like with the old analysis);
        'true' -> group key = task_description (the real task).
    value: 'cs' -> constraint_satisfaction (rows with null are skipped, as in
        v2_variance_structure._load_groups); 'joint' -> cs if the right tool was selected else 0.
    """
    keep = set(tool_sets)
    out: dict[str, dict[str, list[float]]] = {t: defaultdict(list) for t in tool_sets}
    for r in sorted(rows, key=lambda x: (x["tool_set"], x["task_description"], x["trial_index"])):
        ts = r["tool_set"]
        if ts not in keep:
            continue
        key = r["task_tool_name"] if by == "gold" else r["task_description"]
        cs = r.get("constraint_satisfaction")
        if value == "cs":
            if cs is not None:
                out[ts][key].append(float(cs))
        else:
            ok = r.get("selected_tool") == r["task_tool_name"]
            out[ts][key].append(float(cs) if (ok and cs is not None) else 0.0)
    return {t: dict(g) for t, g in out.items() if g}


def old_records(old_path: Path) -> list[dict[str, Any]]:
    """Old corpus records that have run_results."""
    data = json.loads(old_path.read_text(encoding="utf-8"))
    return [r for r in data if r.get("run_results")]


def groups_from_old(
    old_path: Path, value: str, tool_sets: list[str] | None = None
) -> dict[str, dict[str, list[float]]]:
    """Old corpus groups keyed (tool_set, task_tool_name). 'cs' reuses vvs._load_groups."""
    if value == "cs":
        vvs.RESULTS_PATH = old_path
        groups = vvs._load_groups()
    else:
        groups = {}
        for rec in old_records(old_path):
            g: dict[str, list[float]] = defaultdict(list)
            for t in rec["run_results"]:
                cs = t.get("constraint_satisfaction")
                ok = t.get("selected_tool") == t["task_tool_name"]
                g[t["task_tool_name"]].append(float(cs) if (ok and cs is not None) else 0.0)
            groups[rec["name"]] = dict(g)
    if tool_sets is not None:
        keep = set(tool_sets)
        groups = {k: v for k, v in groups.items() if k in keep}
    return groups


# ---------------------------------------------------------------------------------------
# Sufficient statistics (additive per tool set) -> fast cluster bootstrap
# ---------------------------------------------------------------------------------------


def tool_set_agg(groups: dict[str, list[float]]) -> dict[str, float]:
    """Additive sufficient statistics of one tool set's groups."""
    a = dict.fromkeys(
        ("N", "k", "S", "Q", "sg2n", "sn2", "n_multi", "n_zero", "gsum", "gsq", "var_sum"), 0.0
    )
    a["var_cnt"] = 0.0
    for vals in groups.values():
        n = len(vals)
        if n < 1:
            continue
        s = sum(vals)
        q = sum(x * x for x in vals)
        m = s / n
        a["N"] += n
        a["k"] += 1
        a["S"] += s
        a["Q"] += q
        a["sg2n"] += s * s / n
        a["sn2"] += n * n
        a["gsum"] += m
        a["gsq"] += m * m
        if n >= 2:
            a["n_multi"] += 1
            if len({round(x, 6) for x in vals}) == 1:
                a["n_zero"] += 1
            a["var_sum"] += (q - s * s / n) / n  # population variance of the group
            a["var_cnt"] += 1
    a["ss_task"] = a["sg2n"] - (a["S"] ** 2 / a["N"] if a["N"] else 0.0)
    return a


def _tot(aggs: list[dict[str, float]], key: str) -> float:
    return sum(a[key] for a in aggs)


def metrics_from_aggs(
    cs_aggs: list[dict[str, float]], joint_aggs: list[dict[str, float]]
) -> dict[str, float | None]:
    """All scalar metrics from per-tool-set aggregates (cs for ICC/shares, joint for constants)."""
    out: dict[str, float | None] = dict.fromkeys(
        (
            "zero_var_share_pct",
            "icc",
            "pct_between_toolset",
            "pct_between_task",
            "pct_between_trial",
            "baseline",
            "sigma_task",
            "resid_sd",
        )
    )
    N, k = _tot(cs_aggs, "N"), _tot(cs_aggs, "k")
    n_multi = _tot(cs_aggs, "n_multi")
    if n_multi > 0:
        out["zero_var_share_pct"] = 100.0 * _tot(cs_aggs, "n_zero") / n_multi
    if N > 0 and k >= 2:
        gm = _tot(cs_aggs, "S") / N
        Q, sg2n = _tot(cs_aggs, "Q"), _tot(cs_aggs, "sg2n")
        ss_between = sg2n - N * gm * gm
        ss_within = Q - sg2n
        eps = 1e-9 * max(1.0, Q)
        if ss_within < eps:
            ss_within = 0.0
        df_b, df_w = k - 1, N - k
        msb = ss_between / df_b
        msw = ss_within / df_w if df_w > 0 else 0.0
        n0 = (N - _tot(cs_aggs, "sn2") / N) / df_b
        # msw == 0 -> ICC at its ceiling (1.0), as in v2_variance_structure.task1a_icc
        icc = (1.0 if msb > 0 else 0.0) if msw == 0.0 else (msb - msw) / (msb + (n0 - 1) * msw)
        out["icc"] = max(0.0, min(1.0, icc))
        ss_total = Q - N * gm * gm
        if ss_total > eps:
            ss_ts = sum(a["N"] * (a["S"] / a["N"] - gm) ** 2 for a in cs_aggs if a["N"])
            ss_task = _tot(cs_aggs, "ss_task")
            ss_trial = max(0.0, Q - sg2n)
            out["pct_between_toolset"] = 100.0 * ss_ts / ss_total
            out["pct_between_task"] = 100.0 * ss_task / ss_total
            out["pct_between_trial"] = 100.0 * ss_trial / ss_total
    Nj, kj = _tot(joint_aggs, "N"), _tot(joint_aggs, "k")
    if Nj > 0 and kj > 0:
        out["baseline"] = _tot(joint_aggs, "S") / Nj
        mean_m = _tot(joint_aggs, "gsum") / kj
        out["sigma_task"] = math.sqrt(max(0.0, _tot(joint_aggs, "gsq") / kj - mean_m**2))
        vc = _tot(joint_aggs, "var_cnt")
        if vc > 0:
            out["resid_sd"] = math.sqrt(max(0.0, _tot(joint_aggs, "var_sum") / vc))
    return out


def pair_agg(
    before: dict[str, list[float]], after: dict[str, list[float]]
) -> dict[str, float] | None:
    """Additive stats of matched group means for one before/after Phase-3 pair."""
    shared = sorted(set(before) & set(after))
    if not shared:
        return None
    a = dict.fromkeys(("n", "Sx", "Sy", "Sxx", "Syy", "Sxy"), 0.0)
    for t in shared:
        x, y = vvs._mean(before[t]), vvs._mean(after[t])
        a["n"] += 1
        a["Sx"] += x
        a["Sy"] += y
        a["Sxx"] += x * x
        a["Syy"] += y * y
        a["Sxy"] += x * y
    return a


def pearson_from_pairs(aggs: list[dict[str, float]]) -> float | None:
    """Pooled Pearson r (population moments, as v2_variance_structure 1c) from pair aggregates."""
    n = _tot(aggs, "n")
    if n < 2:
        return None
    mx, my = _tot(aggs, "Sx") / n, _tot(aggs, "Sy") / n
    vx = _tot(aggs, "Sxx") / n - mx * mx
    vy = _tot(aggs, "Syy") / n - my * my
    if vx <= 1e-15 or vy <= 1e-15:
        return None
    return (_tot(aggs, "Sxy") / n - mx * my) / math.sqrt(vx * vy)


def pair_aggs_for(groups_cs: dict[str, dict[str, list[float]]]) -> list[dict[str, float]] | None:
    """Pair aggregates for the 5 Phase-3 pairs, or None if any set/pair is missing."""
    aggs = []
    for b, a in vvs.PHASE3_PAIRS:
        if b not in groups_cs or a not in groups_cs:
            return None
        pa = pair_agg(groups_cs[b], groups_cs[a])
        if pa is None:
            return None
        aggs.append(pa)
    return aggs


def cluster_bootstrap(
    cs_aggs: dict[str, dict[str, float]],
    joint_aggs: dict[str, dict[str, float]],
    pair_aggs: list[dict[str, float]] | None,
    names: list[str],
    draws: list[list[int]],
    rho_draws: list[list[int]],
) -> list[dict[str, float | None]]:
    """Per-replicate metrics. Each replicate resamples TOOL SETS with replacement."""
    reps = []
    for idx in draws:
        cs = [cs_aggs[names[i]] for i in idx]
        jt = [joint_aggs[names[i]] for i in idx]
        reps.append(metrics_from_aggs(cs, jt))
    if pair_aggs is not None:
        for rep, pidx in zip(reps, rho_draws, strict=True):
            rep["rho"] = pearson_from_pairs([pair_aggs[i] for i in pidx])
    else:
        for rep in reps:
            rep["rho"] = None
    return reps


def make_draws(m: int, n_boot: int, seed: int) -> list[list[int]]:
    """n_boot resamples of range(m) with replacement (random.Random(seed), deterministic)."""
    rng = random.Random(seed)
    return [[rng.randrange(m) for _ in range(m)] for _ in range(n_boot)]


def summarise_reps(
    point: dict[str, float | None], reps: list[dict[str, float | None]]
) -> dict[str, dict[str, Any]]:
    """Percentile 95% CI per metric (None replicates dropped and counted)."""
    out = {}
    for key, pt in point.items():
        vals = sorted(v[key] for v in reps if v.get(key) is not None)  # type: ignore[type-var]
        out[key] = {
            "point": pt,
            "ci_lo": quantile(vals, 0.025) if vals else None,
            "ci_hi": quantile(vals, 0.975) if vals else None,
            "n_valid_replicates": len(vals),
        }
    return out


def diff_reps(
    new_reps: list[dict[str, float | None]],
    old_reps: list[dict[str, float | None]],
    new_pt: dict[str, float | None],
    old_pt: dict[str, float | None],
) -> dict[str, dict[str, Any]]:
    """Paired (same tool-set resamples) new-minus-old differences with percentile CIs."""
    out = {}
    for key in new_pt:
        if new_pt[key] is None or old_pt.get(key) is None:
            continue
        ds = sorted(
            n[key] - o[key]  # type: ignore[operator]
            for n, o in zip(new_reps, old_reps, strict=True)
            if n.get(key) is not None and o.get(key) is not None
        )
        out[key] = {
            "point": new_pt[key] - old_pt[key],  # type: ignore[operator]
            "ci_lo": quantile(ds, 0.025) if ds else None,
            "ci_hi": quantile(ds, 0.975) if ds else None,
            "n_valid_replicates": len(ds),
        }
    return out


# ---------------------------------------------------------------------------------------
# One corpus -> point estimates (via imported vvs code) + bootstrap
# ---------------------------------------------------------------------------------------


def analyse_corpus(
    cs_groups: dict[str, dict[str, list[float]]],
    joint_groups: dict[str, dict[str, list[float]]],
    n_boot: int,
    draws: list[list[int]] | None = None,
    names: list[str] | None = None,
) -> dict[str, Any]:
    """Point estimates (exact vvs formulas), bootstrap replicates and CIs for one corpus."""
    names = names if names is not None else sorted(cs_groups)
    icc = vvs.task1a_icc({n: cs_groups[n] for n in names})
    try:
        dec = vvs.task1b_variance_decomposition({n: cs_groups[n] for n in names})
    except ZeroDivisionError:
        # Every trial identical (SS_total == 0): the decomposition is undefined, not an error.
        dec = {
            "pct_between_toolset": None,
            "pct_between_task_within_toolset": None,
            "pct_between_trial_within_task": None,
            "note": "SS_total == 0 (all outcomes identical): variance shares undefined",
        }
    cs_aggs = {n: tool_set_agg(cs_groups[n]) for n in names}
    joint_aggs = {n: tool_set_agg(joint_groups[n]) for n in names}
    pt = metrics_from_aggs([cs_aggs[n] for n in names], [joint_aggs[n] for n in names])
    # exact (imported-formula) values override the sufficient-stat ones for the point estimate;
    # the two agree to ~1e-9 (checked below) -- the sufficient-stat path exists only for speed.
    exact = {
        "zero_var_share_pct": icc["pct_groups_zero_within_group_variance"],
        "icc": icc["icc"],
        "pct_between_toolset": dec["pct_between_toolset"],
        "pct_between_task": dec["pct_between_task_within_toolset"],
        "pct_between_trial": dec["pct_between_trial_within_task"],
    }
    drift = max(abs((pt[k] or 0.0) - v) for k, v in exact.items() if v is not None)
    pt.update(exact)
    pair_aggs = pair_aggs_for({n: cs_groups[n] for n in names})
    rho_info: dict[str, Any]
    if pair_aggs is None:
        pt["rho"] = None
        rho_info = {"computable": False, "note": "not computable on this subset"}
    else:
        corr = vvs.task1c_before_after_correlation({n: cs_groups[n] for n in names})
        pt["rho"] = corr["pooled_pearson_r"]
        rho_info = {
            "computable": True,
            "n_matched_tasks_pooled": corr["n_matched_tasks_pooled"],
            "pooled_spearman_rho": corr["pooled_spearman_rho"],
            "per_pair": corr["per_pair"],
            "bootstrap_unit": "the 5 Phase-3 before/after pairs (only 5 clusters: CI is crude)",
        }
    if draws is None:
        draws = make_draws(len(names), n_boot, SEED)
    rho_draws = make_draws(len(vvs.PHASE3_PAIRS), len(draws), SEED + 1) if pair_aggs else []
    reps = cluster_bootstrap(cs_aggs, joint_aggs, pair_aggs, names, draws, rho_draws)
    return {
        "tool_sets": names,
        "n_trials": icc["n_trials_total"],
        "n_groups": icc["n_groups"],
        "n_groups_with_multiple_trials": icc["n_groups_with_multiple_trials"],
        "n_groups_zero_within_group_variance": icc["n_groups_zero_within_group_variance"],
        "icc_detail": icc,
        "variance_decomposition": dec,
        "rho": rho_info,
        "metrics": summarise_reps(pt, reps),
        "point": pt,
        "_reps": reps,
        "suff_stat_vs_exact_max_abs_drift": drift,
    }


# ---------------------------------------------------------------------------------------
# Null false-alarm / abstention
# ---------------------------------------------------------------------------------------


def seed_base(tool_set: str) -> int:
    """31-bit base seed from a hash of the tool-set NAME (stable under tool-set add/remove)."""
    return int.from_bytes(hashlib.sha256(tool_set.encode("utf-8")).digest()[:4], "big") & 0x7FFFFFFF


def stratum_of(n_tasks: int) -> str:
    """Cluster-count stratum, as scripts/v2_2_few_clusters_correction.py."""
    if n_tasks < 10:
        return STRATA[0]
    if n_tasks < 30:
        return STRATA[1]
    return STRATA[2]


def pools_from_old(old_path: Path) -> dict[str, dict[str, list[tuple[str, str | None, float]]]]:
    """{tool_set: {gold: [(gold, selected, cs)]}} for tasks with >=2 trials, old corpus."""
    out: dict[str, dict[str, list[tuple[str, str | None, float]]]] = {}
    for rec in old_records(old_path):
        g: dict[str, list[tuple[str, str | None, float]]] = defaultdict(list)
        for t in rec["run_results"]:
            g[t["task_tool_name"]].append(
                (t["task_tool_name"], t.get("selected_tool"), t.get("constraint_satisfaction", 0.0))
            )
        out[rec["name"]] = {k: v for k, v in g.items() if len(v) >= 2}
    return out


def pools_from_rows(
    rows: list[dict[str, Any]], tool_sets: list[str]
) -> dict[str, dict[str, list[tuple[str, str | None, float]]]]:
    """Same shape from new rows (null cs treated as 0.0, as TrialOutcome would need a number)."""
    keep = set(tool_sets)
    tmp: dict[str, dict[str, list[tuple[str, str | None, float]]]] = {
        t: defaultdict(list) for t in tool_sets
    }
    for r in sorted(rows, key=lambda x: (x["tool_set"], x["task_description"], x["trial_index"])):
        if r["tool_set"] in keep:
            cs = r.get("constraint_satisfaction")
            tmp[r["tool_set"]][r["task_tool_name"]].append(
                (r["task_tool_name"], r.get("selected_tool"), 0.0 if cs is None else float(cs))
            )
    return {t: {k: v for k, v in g.items() if len(v) >= 2} for t, g in tmp.items()}


def _null_job(args: tuple[str, dict, int]) -> dict[str, Any]:
    """Run the null comparisons for one tool set (logic of v2_1/v2_2 scripts)."""
    name, pool, repeats = args
    tasks = {
        g: [
            TrialOutcome(task_tool_name=a, selected_tool=b, constraint_satisfaction=c)
            for a, b, c in trials
        ]
        for g, trials in pool.items()
    }
    counts = {"total": 0, "false_alarms": 0, "insufficient": 0, "no_change": 0}
    base = seed_base(name)
    for rep in range(repeats):
        seed = (base + rep) & 0xFFFFFFFF
        rng = _lcg_random(seed)
        before: list[TrialOutcome] = []
        after: list[TrialOutcome] = []
        for trials in tasks.values():
            n = len(trials)
            before += [trials[min(int(rng() * n), n - 1)] for _ in range(n)]
            after += [trials[min(int(rng() * n), n - 1)] for _ in range(n)]
        res = diff_server_level(before, after, threshold=0.05, use_cuped=True, seed=seed)
        counts["total"] += 1
        if res.verdict in (Verdict.REGRESSION, Verdict.IMPROVEMENT):
            counts["false_alarms"] += 1
        elif res.verdict == Verdict.INSUFFICIENT_SENSITIVITY:
            counts["insufficient"] += 1
        else:
            counts["no_change"] += 1
    zero_pools = sum(1 for t in pool.values() if len({round(x[2], 6) for x in t}) == 1)
    return {
        "tool_set": name,
        "n_tasks": len(pool),
        "stratum": stratum_of(len(pool)),
        "n_task_pools": len(pool),
        "n_zero_variance_task_pools": zero_pools,
        **counts,
    }


def run_null(
    pools: dict[str, dict[str, list]], repeats: int, workers: int, label: str
) -> list[dict[str, Any]]:
    """Null comparisons for every eligible (>=2 resamplable tasks) tool set, in parallel."""
    eligible = {n: p for n, p in sorted(pools.items()) if len(p) >= 2}
    jobs = [(n, p, repeats) for n, p in eligible.items()]
    results: list[dict[str, Any]] = []
    print(f"[null:{label}] {len(jobs)} eligible tool sets x {repeats} repeats", flush=True)
    if workers > 1 and len(jobs) > 1:
        with Pool(min(workers, MAX_WORKERS)) as pool:
            for i, r in enumerate(pool.imap_unordered(_null_job, jobs), 1):
                results.append(r)
                print(f"[null:{label}] {i}/{len(jobs)} {r['tool_set']}", flush=True)
    else:
        for i, j in enumerate(jobs, 1):
            results.append(_null_job(j))
            print(f"[null:{label}] {i}/{len(jobs)} {j[0]}", flush=True)
    return sorted(results, key=lambda r: r["tool_set"])


def summarise_null(per_set: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-stratum and overall k/N with Wilson 95% intervals."""

    def block(items: list[dict[str, Any]]) -> dict[str, Any]:
        n = sum(i["total"] for i in items)
        out: dict[str, Any] = {
            "n_tool_sets": len(items),
            "n_comparisons": n,
            "n_task_pools": sum(i["n_task_pools"] for i in items),
            "n_zero_variance_task_pools": sum(i["n_zero_variance_task_pools"] for i in items),
            "n_tool_sets_all_pools_zero_variance": sum(
                1 for i in items if i["n_zero_variance_task_pools"] == i["n_task_pools"]
            ),
        }
        for key, field in (
            ("false_alarm", "false_alarms"),
            ("abstention", "insufficient"),
            ("confident_no_change", "no_change"),
        ):
            k = sum(i[field] for i in items)
            lo, hi = wilson_interval(k, n)
            out[key] = {
                "k": k,
                "N": n,
                "rate_pct": 100.0 * k / n if n else None,
                "wilson_lo_pct": 100.0 * lo,
                "wilson_hi_pct": 100.0 * hi,
            }
        return out

    summary = {"overall": block(per_set), "by_stratum": {}}
    for s in STRATA:
        items = [i for i in per_set if i["stratum"] == s]
        if items:
            summary["by_stratum"][s] = block(items)
    return summary


# ---------------------------------------------------------------------------------------
# MDE
# ---------------------------------------------------------------------------------------


def _mde_job(cell: dict[str, Any]) -> dict[str, Any]:
    t0 = time.time()
    val = simulate_mde_task_level(
        n_tasks=cell["n_tasks"],
        power=0.8,
        baseline_rate=cell["baseline"],
        n_simulations=cell["sims"],
        seed=SEED,
        trials_per_task=1,
        sigma_task=cell["sigma_task"],
        resid_sd=cell["resid_sd"],
        rho=cell["rho"],
    )
    return {**cell, "mde": val, "seconds": round(time.time() - t0, 1)}


def build_mde_cells(
    new_gold: dict[str, Any], new_true: dict[str, Any], sims: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Cells: OLD (control), NEW gold, NEW true-task, and resid_sd / sigma_task sensitivity."""
    old_c = {
        "baseline": CALIBRATED_BASELINE_RATE,
        "sigma_task": CALIBRATED_SIGMA_TASK,
        "resid_sd": CALIBRATED_RESID_SD,
        "rho": CALIBRATED_RHO,
    }
    notes: dict[str, Any] = {}
    old_rho = CALIBRATED_RHO
    rho_new = new_gold["point"].get("rho")
    if rho_new is None:
        rho_used = old_rho
        notes["rho"] = (
            f"rho not computable on this subset of tool sets; OLD rho={old_rho} used for all "
            "NEW-constant MDE cells"
        )
    else:
        rho_used = round(rho_new, 3)
        notes["rho"] = f"NEW rho={rho_used} (pooled Pearson on matched Phase-3 tasks)"

    def consts(corpus: dict[str, Any], **override: float) -> dict[str, float] | None:
        p = corpus["point"]
        if p["baseline"] is None or p["sigma_task"] is None or p["resid_sd"] is None:
            return None
        c = {
            "baseline": round(p["baseline"], 4),
            "sigma_task": round(p["sigma_task"], 4),
            "resid_sd": round(p["resid_sd"], 4),
            "rho": rho_used,
        }
        c.update(override)
        return c

    specs: list[tuple[str, dict[str, float] | None]] = [
        ("OLD constants (control; expect 0.0848 @100, 0.0537 @253)", old_c),
        ("NEW constants, gold-tool grouping (point)", consts(new_gold)),
        ("NEW constants, true-task grouping (point)", consts(new_true)),
    ]
    for key, name in (("resid_sd", "resid_sd"), ("sigma_task", "sigma_task")):
        ci = new_gold["metrics"][key]
        for tag, v in (
            ("2.5% bootstrap quantile", ci["ci_lo"]),
            ("97.5% bootstrap quantile", ci["ci_hi"]),
        ):
            if v is not None:
                specs.append(
                    (
                        f"NEW gold constants with {name} at its {tag} (others at point)",
                        consts(new_gold, **{key: round(v, 4)}),
                    )
                )
    cells = []
    for label, c in specs:
        if c is None:
            continue
        for n in (100, 253):
            cells.append({"label": label, "n_tasks": n, "sims": sims, **c})
    return cells, notes


def run_mde(cells: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    """Run MDE cells in parallel (<=4 workers), printing progress as each finishes."""
    # Longest cells first so the pool drains evenly.
    order = sorted(cells, key=lambda c: -c["n_tasks"])
    results = []
    print(f"[mde] {len(order)} cells, {order[0]['sims'] if order else 0} sims each", flush=True)
    with Pool(max(1, min(workers, MAX_WORKERS))) as pool:
        for i, r in enumerate(pool.imap_unordered(_mde_job, order), 1):
            results.append(r)
            print(
                f"[mde] {i}/{len(order)} n={r['n_tasks']} mde={r['mde']:.4f} "
                f"({r['seconds']}s) {r['label']}",
                flush=True,
            )
    results.sort(
        key=lambda r: cells.index(
            next(c for c in cells if c["label"] == r["label"] and c["n_tasks"] == r["n_tasks"])
        )
    )
    return results


# ---------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------


def _fmt(v: float | None, nd: int = 4) -> str:
    return "n/a" if v is None else f"{v:.{nd}f}"


def _ci(m: dict[str, Any], nd: int = 4) -> str:
    if m["point"] is None:
        return "n/a"
    return f"{_fmt(m['point'], nd)} [{_fmt(m['ci_lo'], nd)}, {_fmt(m['ci_hi'], nd)}]"


METRIC_ROWS = (
    ("zero_var_share_pct", "Zero-variance group share (%)", 2),
    ("icc", "ICC(1)", 4),
    ("pct_between_toolset", "Variance share: tool set (%)", 2),
    ("pct_between_task", "Variance share: task within set (%)", 2),
    ("pct_between_trial", "Variance share: trial within task (%)", 2),
    ("baseline", "baseline (joint_success mean)", 4),
    ("sigma_task", "sigma_task (SD of group means)", 4),
    ("resid_sd", "resid_sd", 4),
    ("rho", "rho (Phase-3 pooled Pearson)", 4),
)


def render_md(res: dict[str, Any]) -> str:
    """Markdown report from the results dict."""
    L: list[str] = []
    a = L.append
    a("# AgentGauge seed-fix re-calibration: old vs new corpus\n")
    a(f"Generated by `scripts/recalibration_analyze.py`. Bootstrap seed {SEED}.\n")
    a("## Method\n")
    a(f"- {res['method']['bootstrap']}")
    a(f"- {res['method']['formulas']}")
    a(f"- {res['method']['groupings']}")
    a(f"- {res['method']['null']}")
    a(f"- {res['method']['mde']}\n")
    if len(res["tool_sets_used"]) < 10:
        a(
            f"WARNING: only {len(res['tool_sets_used'])} tool set(s) analysed; a cluster bootstrap "
            "over so few clusters is degenerate/unreliable (CIs can collapse to a point).\n"
        )
    a("## Tool sets used\n")
    a(
        f"Completed tool sets in the new rows ({len(res['tool_sets_used'])}): "
        + ", ".join(f"`{t}`" for t in res["tool_sets_used"])
    )
    st = res["status"]
    if st.get("not_run_or_partial"):
        a(f"\nNot run / partial (excluded): {', '.join(st['not_run_or_partial'])}")
    if res.get("old_missing_tool_sets"):
        a(
            f"\nWARNING: completed tool sets absent from the old corpus: "
            f"{res['old_missing_tool_sets']}"
        )
    a("")
    a("## Control: old corpus, full\n")
    c = res["control"]
    a("| quantity | expected | observed | match |")
    a("|---|---|---|---|")
    for row in c["rows"]:
        a(f"| {row['name']} | {row['expected']} | {row['observed']} | {row['match']} |")
    a(f"\nControl overall: {'PASS' if c['pass'] else 'FAIL'}\n")
    a(
        "Harness constants recomputed from the old corpus (joint_success; rounded to the harness "
        "precision) vs `CALIBRATED_*`:\n"
    )
    a("| constant | harness | recomputed |")
    a("|---|---|---|")
    for k, (h, r) in c["constants"].items():
        a(f"| {k} | {h} | {r} |")
    a("")

    def table(title: str, corpora: list[tuple[str, dict[str, Any]]]) -> None:
        a(f"## {title}\n")
        a("| metric | " + " | ".join(n for n, _ in corpora) + " |")
        a("|---|" + "---|" * len(corpora))
        a("| trials | " + " | ".join(str(d["n_trials"]) for _, d in corpora) + " |")
        a(
            "| groups (multi-trial) | "
            + " | ".join(
                f"{d['n_groups']} ({d['n_groups_with_multiple_trials']})" for _, d in corpora
            )
            + " |"
        )
        a(
            "| zero-variance groups | "
            + " | ".join(
                f"{d['n_groups_zero_within_group_variance']}/{d['n_groups_with_multiple_trials']}"
                for _, d in corpora
            )
            + " |"
        )
        for key, label, nd in METRIC_ROWS:
            a(
                f"| {label} | "
                + " | ".join(
                    _ci(d["metrics"][key], nd) if d["metrics"].get(key) else "n/a"
                    for _, d in corpora
                )
                + " |"
            )
        a("")

    table(
        "Old vs new, like-for-like (gold-tool groups, same tool sets)",
        [("OLD restricted", res["old_restricted"]), ("NEW gold", res["new_gold"])],
    )
    a(
        "Point [2.5%, 97.5%] cluster-bootstrap over tool sets. rho: "
        + (res["new_gold"]["rho"].get("note", "computed") if res["new_gold"]["rho"] else "n/a")
        + " (new); old: "
        + (res["old_restricted"]["rho"].get("note", "computed"))
        + ".\n"
    )
    a("### New minus old (paired bootstrap, same tool-set resamples)\n")
    a("| metric | diff [95% CI] |")
    a("|---|---|")
    for key, label, nd in METRIC_ROWS:
        d = res["diff_new_minus_old"].get(key)
        if d:
            a(f"| {label} | {_ci(d, nd)} |")
    a("")
    table(
        "NEW data, true-task groups (tool_set, task_description) vs gold-tool groups",
        [("NEW true-task", res["new_true"]), ("NEW gold", res["new_gold"])],
    )
    table("Old corpus, full", [("OLD full", res["old_full"])])

    if "mde" in res:
        m = res["mde"]
        a(
            "## MDE (power 0.8, 1 trial per task, seed 42, "
            f"{m['sims']} simulations per bisection step)\n"
        )
        a(f"{m['notes']['rho']}\n")
        a("| constants | baseline | sigma_task | resid_sd | rho | n=100 | n=253 |")
        a("|---|---|---|---|---|---|---|")
        by_label: dict[str, dict[int, dict[str, Any]]] = {}
        for r in m["cells"]:
            by_label.setdefault(r["label"], {})[r["n_tasks"]] = r
        for label, d in by_label.items():
            any_ = next(iter(d.values()))
            a(
                f"| {label} | {any_['baseline']} | {any_['sigma_task']} | {any_['resid_sd']} | "
                f"{any_['rho']} | {_fmt(d.get(100, {}).get('mde'))} | "
                f"{_fmt(d.get(253, {}).get('mde'))} |"
            )
        a(
            "\nThe 'bootstrap quantile' rows are a one-at-a-time sensitivity range (parameter set "
            "to the 2.5%/97.5% cluster-bootstrap quantile of the NEW gold-grouping estimate, "
            "others at point): they are NOT a CI on the MDE itself. MC error at small --mde-sims "
            "is large; 12-step bisection with a 200-resample inner bootstrap.\n"
        )
    else:
        a("## MDE\n\nSkipped (`--skip-mde`).\n")

    if "null" in res:
        a("## Null false-alarm / abstention (Wilson 95% on k/N)\n")
        a(res["null"]["caveat"] + "\n")
        for which in ("old_full", "old_restricted", "new"):
            blk = res["null"][which]
            a(f"### {which}\n")
            a(
                "| stratum | tool sets | comparisons | false alarm k/N (rate, Wilson) | "
                "abstention k/N (rate, Wilson) | confident no-change k/N | zero-var task pools |"
            )
            a("|---|---|---|---|---|---|---|")
            rows = [("ALL", blk["overall"])] + list(blk["by_stratum"].items())
            for name, b in rows:

                def f(x: dict[str, Any]) -> str:
                    return (
                        f"{x['k']}/{x['N']} ({x['rate_pct']:.2f}%, "
                        f"[{x['wilson_lo_pct']:.2f}, {x['wilson_hi_pct']:.2f}])"
                    )

                a(
                    f"| {name} | {b['n_tool_sets']} | {b['n_comparisons']} | {f(b['false_alarm'])} | "
                    f"{f(b['abstention'])} | {b['confident_no_change']['k']}/"
                    f"{b['confident_no_change']['N']} | "
                    f"{b['n_zero_variance_task_pools']}/{b['n_task_pools']} |"
                )
            ov = blk["overall"]
            if ov["n_task_pools"] and ov["n_zero_variance_task_pools"] / ov["n_task_pools"] > 0.5:
                a(
                    f"\nDEGENERATE for a null test: {ov['n_zero_variance_task_pools']}/"
                    f"{ov['n_task_pools']} task pools have zero variance (all trials identical), so "
                    "before/after resamples are identical and the false-alarm rate is trivially 0 "
                    "-- it says nothing about estimator calibration."
                )
            a("")
    a("## Inputs\n")
    for k, v in res["inputs"].items():
        a(f"- {k}: `{v['path']}` sha256 `{v['sha256']}`")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------


def build_control(old_full: dict[str, Any], joint_old_full: dict[str, Any]) -> dict[str, Any]:
    """Compare the full-old-corpus numbers against the published control values."""
    rows = []

    def add(name: str, expected: Any, observed: Any, ok: bool) -> None:
        rows.append({"name": name, "expected": expected, "observed": observed, "match": ok})

    icc = old_full["icc_detail"]
    # Float, so compare to 1e-9: Windows and Linux differ in the last digits (2e-15 seen in CI).
    icc_ok = math.isclose(icc["icc"], OLD_CONTROL["icc"], rel_tol=1e-9)
    add("ICC(1)", OLD_CONTROL["icc"], icc["icc"], icc_ok)
    add(
        "zero-variance groups",
        OLD_CONTROL["n_zero"],
        icc["n_groups_zero_within_group_variance"],
        icc["n_groups_zero_within_group_variance"] == OLD_CONTROL["n_zero"],
    )
    add(
        "multi-trial groups",
        OLD_CONTROL["n_multi"],
        icc["n_groups_with_multiple_trials"],
        icc["n_groups_with_multiple_trials"] == OLD_CONTROL["n_multi"],
    )
    raw_pt = old_full["variance_decomposition"]["pct_between_task_within_toolset"]
    pt = None if raw_pt is None else round(raw_pt, 2)
    add("between-task share (%)", OLD_CONTROL["pct_task"], pt, pt == OLD_CONTROL["pct_task"])
    p = joint_old_full["point"]
    consts = {}
    for key, harness, nd in (
        ("baseline", CALIBRATED_BASELINE_RATE, 4),
        ("sigma_task", CALIBRATED_SIGMA_TASK, 4),
        ("resid_sd", CALIBRATED_RESID_SD, 4),
        ("rho", CALIBRATED_RHO, 3),
    ):
        got = None if p.get(key) is None else round(p[key], nd)
        consts[key] = (harness, got)
        add(f"constant {key}", harness, got, got == harness)
    return {"rows": rows, "constants": consts, "pass": all(r["match"] for r in rows)}


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the pipeline and write outputs. Returns the results dict."""
    rows_path, old_path, out = Path(args.rows), Path(args.old), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    status_path = Path(args.status) if args.status else rows_path.parent / "run_status.json"
    rows = load_new_rows(rows_path)
    tool_sets, status = load_completed(rows, status_path)
    print(f"[load] {len(rows)} new rows; {len(tool_sets)} completed tool sets", flush=True)
    dropped = sorted({r["tool_set"] for r in rows} - set(tool_sets))
    rows_used = [r for r in rows if r["tool_set"] in set(tool_sets)]
    n_null_cs = sum(1 for r in rows_used if r.get("constraint_satisfaction") is None)

    old_cs_full = groups_from_old(old_path, "cs")
    old_jt_full = groups_from_old(old_path, "joint")
    missing = [t for t in tool_sets if t not in old_cs_full]
    common = [t for t in tool_sets if t in old_cs_full]

    n_boot = args.boot
    print("[boot] old full", flush=True)
    old_full = analyse_corpus(old_cs_full, old_jt_full, n_boot)
    # Shared tool-set resamples so new-minus-old differences are paired.
    draws = make_draws(len(common), n_boot, SEED)
    print("[boot] old restricted + new", flush=True)
    old_cs_r = {t: old_cs_full[t] for t in common}
    old_jt_r = {t: old_jt_full[t] for t in common}
    old_restricted = analyse_corpus(old_cs_r, old_jt_r, n_boot, draws, common)
    new_cs_gold = groups_from_rows(rows_used, common, "gold", "cs")
    new_jt_gold = groups_from_rows(rows_used, common, "gold", "joint")
    new_names = [t for t in common if t in new_cs_gold]
    new_gold = analyse_corpus(new_cs_gold, new_jt_gold, n_boot, draws, new_names)
    new_true = analyse_corpus(
        groups_from_rows(rows_used, common, "true", "cs"),
        groups_from_rows(rows_used, common, "true", "joint"),
        n_boot,
        draws,
        new_names,
    )
    diff = diff_reps(
        new_gold["_reps"], old_restricted["_reps"], new_gold["point"], old_restricted["point"]
    )
    control = build_control(old_full, old_full)

    for d in (old_full, old_restricted, new_gold, new_true):
        d.pop("_reps")

    def inp(p: Path) -> dict[str, str]:
        return {"path": str(p), "sha256": sha256_file(p)}

    inputs = {"rows": inp(rows_path), "old": inp(old_path)}
    if status_path.exists():
        inputs["run_status"] = inp(status_path)
    res: dict[str, Any] = {
        "method": {
            "bootstrap": (
                f"Cluster bootstrap over TOOL SETS: B={n_boot}, resample tool sets with "
                f"replacement (random.Random({SEED})), recompute each statistic from "
                "per-tool-set sufficient statistics, percentile 95% CI (linear "
                "interpolation). Old-restricted and NEW share the same resamples so the "
                "new-minus-old difference CI is paired. rho resamples the 5 Phase-3 "
                "pairs (5 clusters; crude)."
            ),
            "formulas": (
                "ICC, nested variance shares, zero-variance share and rho are computed by "
                "the code of scripts/v2_variance_structure.py (imported) on "
                "constraint_satisfaction. Constants use joint_success: baseline = "
                "trial-weighted mean; sigma_task = population SD of group means; "
                "resid_sd = sqrt(mean population variance over groups with n>=2); "
                "rho = pooled Pearson of before/after group means over the 5 PHASE3 pairs."
            ),
            "groupings": (
                "gold = (tool_set, task_tool_name) like the old analysis; true = "
                "(tool_set, task_description), NEW data only (old rows carry no "
                "description)."
            ),
            "null": (
                "Null: per tool set, bootstrap-resample each gold-tool trial pool twice "
                "(before/after), diff_server_level(threshold=0.05, CUPED); seed from a hash "
                "of the tool-set name. Eligible = >=2 gold tools each with >=2 trials."
            ),
            "mde": (
                "simulate_mde_task_level, power 0.8, trials_per_task=1, seed 42; constants "
                "rounded to 4 dp (rho 3 dp) as in harness."
            ),
        },
        "status": status,
        "tool_sets_used": common,
        "tool_sets_dropped_partial_or_incomplete": dropped,
        "old_missing_tool_sets": missing,
        "n_new_rows_used": len(rows_used),
        "n_new_rows_null_constraint_satisfaction": n_null_cs,
        "inputs": inputs,
        "control": control,
        "old_full": old_full,
        "old_restricted": old_restricted,
        "new_gold": new_gold,
        "new_true": new_true,
        "diff_new_minus_old": diff,
    }
    (out / "MANIFEST.json").write_text(
        json.dumps({"inputs": inputs, "script": inp(Path(__file__).resolve())}, indent=2),
        encoding="utf-8",
    )

    if not args.skip_fa:
        old_pools = pools_from_old(old_path)
        new_pools = pools_from_rows(rows_used, common)
        old_per = run_null(old_pools, args.fa_repeats, args.workers, "old")
        new_per = run_null(new_pools, args.fa_repeats, args.workers, "new")
        restricted_per = [r for r in old_per if r["tool_set"] in set(common)]
        res["null"] = {
            "repeats_per_tool_set": args.fa_repeats,
            "caveat": (
                "Repeats within a tool set share one trial pool, so the Wilson intervals "
                "treat correlated comparisons as independent and are optimistic."
            ),
            "old_full": summarise_null(old_per),
            "old_restricted": summarise_null(restricted_per),
            "new": summarise_null(new_per),
            "per_tool_set_old": old_per,
            "per_tool_set_new": new_per,
        }
    (out / "results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (out / "results.md").write_text(render_md(res), encoding="utf-8")

    if not args.skip_mde:
        cells, notes = build_mde_cells(new_gold, new_true, args.mde_sims)
        results = run_mde(cells, args.workers)
        res["mde"] = {"sims": args.mde_sims, "notes": notes, "cells": results}
        (out / "results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        (out / "results.md").write_text(render_md(res), encoding="utf-8")
    print(f"[done] wrote {out / 'results.json'} and results.md")
    print(f"[control] {'PASS' if control['pass'] else 'FAIL'}")
    return res


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--rows", required=True, help="new rows.ndjson")
    p.add_argument("--old", required=True, help="old results_raw.json")
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--status", default=None, help="run_status.json (default: next to rows)")
    p.add_argument("--mde-sims", type=int, default=2000)
    p.add_argument("--workers", type=int, default=4, help=f"capped at {MAX_WORKERS}")
    p.add_argument("--skip-mde", action="store_true")
    p.add_argument("--skip-fa", action="store_true", help="skip the null false-alarm section")
    p.add_argument("--fa-repeats", type=int, default=50)
    p.add_argument("--boot", type=int, default=2000, help="bootstrap replicates (default 2000)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point; non-zero exit if the old-corpus control does not reproduce."""
    res = run(parse_args(argv))
    return 0 if res["control"]["pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
