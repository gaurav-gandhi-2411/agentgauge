"""Tool-set-clustered confidence intervals for the type_enum_contradiction causal effect.

The README/paper previously quoted a pooled "-13.3 to -28.9pp" figure for the BLOCKING tier.
That pool mixes three injected defect types (``type_flipped``, ``enum_dropped`` and
``contradictory_required_claim``). Only the first two are the ``type_enum_contradiction`` lint
rule, and ``contradictory_required_claim`` is a measured null, so the pooled number understates the
rule's effect. This script recomputes the type_enum-only effect (n = 30 tasks per model) from the
committed per-task deltas, with:

* a cluster bootstrap over the 6 tool sets (the independent unit: tasks within one injected tool
  set share the same defect, tools and catalog),
* an unclustered task-level bootstrap for contrast (what the earlier reports effectively did),
* a t(G-1) interval from the linearised cluster-robust SE of the ratio estimator (G = 6 clusters;
  percentile bootstrap undercovers with so few clusters, so this is the more conservative one).

Inputs are the two committed fixtures (their sha256 is recorded in the output). Pure Python; no
network, no model calls. Seed 42, B = 10000.

Usage: ``python scripts/type_enum_clustered_ci.py [--check]``; ``--check`` recomputes and exits 1
if the committed output file differs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUTS = (
    "evals/fixtures/v2_2_causal_chain_multimodel.json",
    "evals/fixtures/v2_4_blocking_remeasurement.json",
)
OUTPUT = "evals/fixtures/type_enum_contradiction_clustered.json"
TYPE_ENUM_DEFECTS = ("type_flipped", "enum_dropped")
SEED = 42
B = 10_000
# Two-sided 95% t quantiles for the cluster counts that can occur here (df = G - 1).
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365}


def sha256_of(path: Path) -> str:
    """Return the hex sha256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clusters_for(data: dict, model: str, defects: tuple[str, ...]) -> dict[str, list[float]]:
    """Group per-task deltas of the chosen defect types by tool set (the cluster)."""
    out: dict[str, list[float]] = {}
    for inst in data[model]["blocking_instances"]:
        if inst["defect_type"] in defects:
            out.setdefault(inst["tool_set"], []).extend(t["delta"] for t in inst["task_deltas"])
    return out


def percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation percentile of an already sorted list (q in [0, 1])."""
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def cluster_bootstrap(clusters: dict[str, list[float]], b: int, seed: int) -> list[float]:
    """Resample whole clusters with replacement; return sorted pooled-mean replicates."""
    sums = [sum(v) for v in clusters.values()]
    counts = [len(v) for v in clusters.values()]
    g = len(sums)
    rng = random.Random(seed)
    reps = []
    for _ in range(b):
        idx = [rng.randrange(g) for _ in range(g)]
        reps.append(sum(sums[i] for i in idx) / sum(counts[i] for i in idx))
    return sorted(reps)


def task_bootstrap(deltas: list[float], b: int, seed: int) -> list[float]:
    """Resample individual tasks with replacement (ignores clustering); sorted means."""
    rng = random.Random(seed)
    n = len(deltas)
    return sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(b))


def t_cluster_ci(clusters: dict[str, list[float]]) -> tuple[float, float]:
    """t(G-1) interval from the linearised cluster-robust SE of the pooled mean."""
    sums = [sum(v) for v in clusters.values()]
    counts = [len(v) for v in clusters.values()]
    g, n = len(sums), sum(counts)
    mean = sum(sums) / n
    resid2 = sum((s - mean * c) ** 2 for s, c in zip(sums, counts, strict=True))
    se = ((g / (g - 1)) * resid2) ** 0.5 / n
    half = T975[g - 1] * se
    return mean - half, mean + half


def summarise(data: dict, model: str, defects: tuple[str, ...]) -> dict:
    """All statistics for one model and one set of defect types."""
    clusters = clusters_for(data, model, defects)
    deltas = [d for v in clusters.values() for d in v]
    mean = sum(deltas) / len(deltas)
    cl = cluster_bootstrap(clusters, B, SEED)
    tk = task_bootstrap(deltas, B, SEED)
    t_lo, t_hi = t_cluster_ci(clusters)
    return {
        "n_tasks": len(deltas),
        "n_tool_sets": len(clusters),
        "tasks_per_tool_set": {k: len(v) for k, v in clusters.items()},
        "mean_delta_pp": round(mean * 100, 2),
        "cluster_bootstrap_ci_pp": [
            round(percentile(cl, 0.025) * 100, 1),
            round(percentile(cl, 0.975) * 100, 1),
        ],
        "cluster_t_ci_pp": [round(t_lo * 100, 1), round(t_hi * 100, 1)],
        "unclustered_task_bootstrap_ci_pp": [
            round(percentile(tk, 0.025) * 100, 1),
            round(percentile(tk, 0.975) * 100, 1),
        ],
    }


def build() -> dict:
    """Compute the full output document from the committed fixtures."""
    docs = {p: json.loads((ROOT / p).read_text(encoding="utf-8")) for p in INPUTS}
    primary = docs[INPUTS[0]]

    # The v2.4 re-measurement is meant to be an independent rebuild; record whether its per-task
    # deltas are identical to the v2.2 file rather than assume it (compared on the delta values
    # only: the two files differ in other per-task fields).
    def deltas(doc: dict, m: str) -> list[list[float]]:
        return [[t["delta"] for t in i["task_deltas"]] for i in doc[m]["blocking_instances"]]

    identical = all(deltas(docs[INPUTS[0]], m) == deltas(docs[INPUTS[1]], m) for m in primary)
    models = list(primary)
    return {
        "description": "type_enum_contradiction-only (type_flipped + enum_dropped) causal effect "
        "on joint task success, per model, with tool-set-clustered CIs.",
        "method": {
            "seed": SEED,
            "bootstrap_replicates": B,
            "cluster_unit": "tool set (6 clusters)",
            "statistic": "pooled mean of per-task joint-success deltas (after-defect minus clean)",
            "percentile_ci": "linear-interpolation 2.5/97.5 percentiles",
            "cluster_t_ci": "pooled mean +/- t(0.975, G-1) * linearised cluster-robust SE",
            "caveat": "6 clusters is few: percentile bootstrap undercovers; prefer cluster_t_ci. "
            "Defects are synthetic injections into hand-built mock servers.",
        },
        "inputs": {p: {"sha256": sha256_of(ROOT / p)} for p in INPUTS},
        "v2_4_remeasurement_delta_values_identical_to_v2_2": identical,
        "type_enum_only": {m: summarise(primary, m, TYPE_ENUM_DEFECTS) for m in models},
        "all_blocking_pooled_for_comparison": {
            m: summarise(primary, m, TYPE_ENUM_DEFECTS + ("contradictory_required_claim",))
            for m in models
        },
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed output differs")
    args = ap.parse_args(argv)
    text = json.dumps(build(), indent=2, sort_keys=False) + "\n"
    out = ROOT / OUTPUT
    if args.check:
        ok = out.exists() and out.read_text(encoding="utf-8") == text
        print("up to date" if ok else f"STALE: re-run scripts/type_enum_clustered_ci.py ({OUTPUT})")
        return 0 if ok else 1
    out.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
