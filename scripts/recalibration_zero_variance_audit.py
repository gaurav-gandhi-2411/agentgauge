#!/usr/bin/env python3
"""Audit of what "zero-variance" means in the seed-fix re-calibration corpus.

Reads committed rows only (no inference). Two questions about the zero-variance gold groups
(tool_set, gold tool) whose trials issued DIFFERENT calls yet scored identically:

1. Groups where the selected TOOL differs across trials: which tools, how often, what constant
   score. In the collection scorer a trial that selects a non-gold tool scores exactly 0.0
   (``recalibration_collect.py``), so such a group can only be constant if it is all-fail; this
   verifies that against the data instead of assuming it.
2. Groups where only ARGUMENTS differ: all-pass vs all-fail; for all-pass, whether the task has
   any registered constraint at all (``constraint_satisfaction`` returns 1.0 for an empty
   constraint list -- an unfalsifiable pass), and whether the arguments that differ are
   constrained or free. Samples 10 all-pass groups (seed 42) with the differing args beside the
   constraints so a human can judge whether the constraints check what the task requires.

Usage: python scripts/recalibration_zero_variance_audit.py [--out P]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from evals.fixtures.predictive_validity.constraints import (  # noqa: E402
    TASK_CONSTRAINTS,
    constraint_satisfaction,
)

ROWS = ROOT / "evals/fixtures/recalibration_seedfix/rows.ndjson"
OUT = ROOT / "evals/fixtures/recalibration_seedfix/zero_variance_audit.json"


def _call(row: dict) -> str:
    return json.dumps([row["selected_tool"], row["constructed_args"]], sort_keys=True)


def _constraints(row: dict) -> list:
    return (
        TASK_CONSTRAINTS.get(row["tool_set"], {}).get(
            (row["task_tool_name"], row["task_description"])
        )
        or []
    )


def _describe(c) -> dict:  # noqa: ANN001 -- duck-typed Constraint
    d = {"param": c.param, "kind": c.kind}
    for f in ("gold_value", "pattern", "min_val", "max_val", "tolerance"):
        if getattr(c, f, None) is not None:
            d[f] = getattr(c, f)
    return d


def analyse(rows_path: Path) -> dict:
    rows = [json.loads(x) for x in rows_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["tool_set"], r["task_tool_name"])].append(r)
    zero = {
        k: v
        for k, v in sorted(groups.items())
        if len({x["constraint_satisfaction"] for x in v}) == 1
    }
    differing = {k: v for k, v in zero.items() if len({_call(x) for x in v}) > 1}
    tool_differs = {k: v for k, v in differing.items() if len({x["selected_tool"] for x in v}) > 1}
    args_only = {k: v for k, v in differing.items() if k not in tool_differs}

    # --- Part 1: selected tool differs ---------------------------------------------------------
    part1 = []
    for (tool_set, gold), v in tool_differs.items():
        counts = Counter(x["selected_tool"] for x in v)
        part1.append(
            {
                "tool_set": tool_set,
                "gold_tool": gold,
                "task_descriptions": sorted({x["task_description"] for x in v}),
                "selected_tool_counts": dict(counts),
                "n_trials": len(v),
                "constant_score": v[0]["constraint_satisfaction"],
                "all_pass_with_non_gold_tool": v[0]["constraint_satisfaction"] == 1.0
                and any(x["selected_tool"] != gold for x in v),
            }
        )
    # Any trial anywhere that selected a non-gold tool yet scored > 0 (would be a scorer hole).
    wrong_tool_scored = [
        {
            "tool_set": r["tool_set"],
            "task": r["task_description"],
            "score": r["constraint_satisfaction"],
        }
        for r in rows
        if r["selected_tool"] != r["task_tool_name"] and r["constraint_satisfaction"] != 0.0
    ]

    # --- Part 2: arguments differ --------------------------------------------------------------
    all_pass = {k: v for k, v in args_only.items() if v[0]["constraint_satisfaction"] == 1.0}
    all_fail = {k: v for k, v in args_only.items() if v[0]["constraint_satisfaction"] == 0.0}
    other = len(args_only) - len(all_pass) - len(all_fail)

    def per_group(k, v):  # noqa: ANN001, ANN202
        by_task: dict[str, list[dict]] = defaultdict(list)
        for x in v:
            by_task[x["task_description"]].append(x)
        tasks = []
        for desc, tv in by_task.items():
            cons = _constraints(tv[0])
            variants = {}
            for x in tv:
                variants.setdefault(json.dumps(x["constructed_args"], sort_keys=True), []).append(
                    x["trial_index"]
                )
            all_params = {p for x in tv for p in x["constructed_args"]}
            differing_params = sorted(
                p
                for p in all_params
                if len({json.dumps(x["constructed_args"].get(p), sort_keys=True) for x in tv}) > 1
            )
            constrained = {c.param for c in cons}
            tasks.append(
                {
                    "task_description": desc,
                    "n_constraints": len(cons),
                    "constraints": [_describe(c) for c in cons],
                    "distinct_arg_variants": len(variants),
                    "variants": [
                        {
                            "args": json.loads(a),
                            "trials": t,
                            "satisfaction": constraint_satisfaction(json.loads(a), cons or None),
                        }
                        for a, t in variants.items()
                    ],
                    "differing_params": differing_params,
                    "differing_params_constrained": [
                        p for p in differing_params if p in constrained
                    ],
                    "differing_params_unconstrained": [
                        p for p in differing_params if p not in constrained
                    ],
                }
            )
        return {"tool_set": k[0], "gold_tool": k[1], "tasks": tasks}

    detail = [per_group(k, v) for k, v in all_pass.items()]
    flat = [t for g in detail for t in g["tasks"] if t["distinct_arg_variants"] > 1]
    unconstrained_tasks = [t for t in flat if t["n_constraints"] == 0]
    diff_all_unconstrained = [
        t for t in flat if t["n_constraints"] > 0 and not t["differing_params_constrained"]
    ]
    diff_some_constrained = [t for t in flat if t["differing_params_constrained"]]
    rng = random.Random(42)
    sample_pool = [
        (g["tool_set"], g["gold_tool"], t)
        for g in detail
        for t in g["tasks"]
        if t["distinct_arg_variants"] > 1
    ]
    sample = [
        {"tool_set": a, "gold_tool": b, **t}
        for a, b, t in rng.sample(sample_pool, min(10, len(sample_pool)))
    ]
    return {
        "n_zero_variance_gold_groups": len(zero),
        "n_differing_call_groups": len(differing),
        "part1_selected_tool_differs": {
            "n_groups": len(part1),
            "n_all_fail": sum(1 for g in part1 if g["constant_score"] == 0.0),
            "n_all_pass": sum(1 for g in part1 if g["constant_score"] == 1.0),
            "n_all_pass_with_non_gold_tool": sum(
                1 for g in part1 if g["all_pass_with_non_gold_tool"]
            ),
            "trials_anywhere_selecting_non_gold_tool_but_scoring_nonzero": wrong_tool_scored,
            "groups": part1,
        },
        "part3_arguments_differ": {
            "n_groups": len(args_only),
            "n_all_pass": len(all_pass),
            "n_all_fail": len(all_fail),
            "n_other_constant_score": other,
            "all_pass_tasks_with_differing_args": len(flat),
            "of_which_task_has_NO_registered_constraint": len(unconstrained_tasks),
            "of_which_constrained_but_differing_params_all_unconstrained": len(
                diff_all_unconstrained
            ),
            "of_which_a_differing_param_is_constrained": len(diff_some_constrained),
            "sample_of_10_all_pass_tasks": sample,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=Path, default=ROWS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = json.dumps(analyse(a.rows), indent=2, sort_keys=True) + "\n"
    if a.check:
        return 0 if a.out.exists() and a.out.read_text(encoding="utf-8") == text else 1
    a.out.write_text(text, encoding="utf-8")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
