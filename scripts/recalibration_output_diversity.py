#!/usr/bin/env python3
"""Output diversity inside zero-variance groups of the seed-fix re-calibration corpus.

A group is "zero-variance" when every trial has the same ``constraint_satisfaction``. That does
not mean the agent produced the same call: different (tool, args) can score identically. This
splits the zero-variance groups into (a) all trials issued the identical tool call and (b)
differing calls that nevertheless score the same. Committed rows only; no inference.

Usage: python scripts/recalibration_output_diversity.py [--rows P] [--out P] [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
ROWS = ROOT / "evals/fixtures/recalibration_seedfix/rows.ndjson"
OUT = ROOT / "evals/fixtures/recalibration_seedfix/output_diversity.json"


def _call(row: dict) -> str:
    return json.dumps([row["selected_tool"], row["constructed_args"]], sort_keys=True)


def analyse(rows_path: Path) -> dict:
    rows = [
        json.loads(ln) for ln in rows_path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    result: dict = {"n_rows": len(rows)}
    for label, key_fn in (
        ("gold_groups(tool_set,task_tool_name)", lambda r: (r["tool_set"], r["task_tool_name"])),
        (
            "true_task_groups(tool_set,task_description)",
            lambda r: (r["tool_set"], r["task_description"]),
        ),
    ):
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in rows:
            groups[key_fn(r)].append(r)
        zero = {
            k: v for k, v in groups.items() if len({x["constraint_satisfaction"] for x in v}) == 1
        }
        identical = {k for k, v in zero.items() if len({_call(x) for x in v}) == 1}
        differing = set(zero) - identical
        # Within the "differing" ones: do the calls differ in the selected tool or only in args?
        tool_differs = {k for k in differing if len({x["selected_tool"] for x in zero[k]}) > 1}
        all_fail = {k for k, v in zero.items() if v[0]["constraint_satisfaction"] == 0.0}
        all_pass = {k for k, v in zero.items() if v[0]["constraint_satisfaction"] == 1.0}
        distinct_calls = [len({_call(x) for x in v}) for v in groups.values()]
        result[label] = {
            "groups": len(groups),
            "zero_variance_groups": len(zero),
            "zero_variance_all_trials_identical_call": len(identical),
            "zero_variance_differing_calls_same_score": len(differing),
            "of_which_selected_tool_differs": len(tool_differs),
            "of_which_same_tool_only_args_differ": len(differing) - len(tool_differs),
            "zero_variance_all_score_1.0": len(all_pass),
            "zero_variance_all_score_0.0": len(all_fail),
            "zero_variance_other_constant_score": len(zero) - len(all_pass) - len(all_fail),
            "all_groups_with_ge2_distinct_calls": sum(1 for d in distinct_calls if d >= 2),
        }
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=Path, default=ROWS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true", help="exit 1 if --out is stale")
    args = ap.parse_args()
    text = json.dumps(analyse(args.rows), indent=2, sort_keys=True) + "\n"
    if args.check:
        return 0 if args.out.exists() and args.out.read_text(encoding="utf-8") == text else 1
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
