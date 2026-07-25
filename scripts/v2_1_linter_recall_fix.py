"""Task 4 (v2.1): re-measure param_renamed recall AND clean-corpus
false-alarm rate after adding the inverse check `param_possibly_renamed`
(agentgauge/linter.py). Reuses the exact same clean-corpus definition and
defect-injection generation logic as the original Task 2 measurement
(scripts/v2_defect_injector.py) so the two runs are directly comparable --
this is a re-measurement of the same corpus under updated code, not a new
corpus that could quietly change the comparison.

Zero LLM calls. Deterministic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.linter import lint_tool_set  # noqa: E402
from scripts.v2_defect_injector import INJECTORS, _load_clean_corpus  # noqa: E402

OUT_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "v2_1_linter_recall_fix.json"

_MAX_TARGETS_PER_DEFECT_TYPE = 3


class _T:
    def __init__(self, d: dict) -> None:
        self.name = d["name"]
        self.description = d["description"]
        self.inputSchema = d["inputSchema"]


def measure_clean_corpus_false_alarms() -> dict:
    clean_corpus = _load_clean_corpus()
    n_tools = 0
    n_flagged_tools = 0
    n_flagged_toolsets = 0
    by_check: dict[str, int] = {}
    for entry in clean_corpus:
        tools = [_T(t) for t in entry["tools"]]
        report = lint_tool_set(tools)
        n_tools += len(tools)
        toolset_flagged = False
        for tr in report.tool_results:
            tr_high = tr.blocking + tr.advisory  # v2.1: BLOCKING+ADVISORY == v2's single HIGH tier
            if tr_high:
                n_flagged_tools += 1
                toolset_flagged = True
            for v in tr_high:
                by_check[v.check] = by_check.get(v.check, 0) + 1
        if report.collision_violations:
            toolset_flagged = True
            by_check["name_collision"] = by_check.get("name_collision", 0) + len(
                report.collision_violations
            )
        if toolset_flagged:
            n_flagged_toolsets += 1

    return {
        "n_tool_sets": len(clean_corpus),
        "n_tools": n_tools,
        "n_flagged_tools": n_flagged_tools,
        "pct_flagged_tools": 100.0 * n_flagged_tools / n_tools,
        "n_flagged_toolsets": n_flagged_toolsets,
        "pct_flagged_toolsets": 100.0 * n_flagged_toolsets / len(clean_corpus),
        "violations_by_check": by_check,
    }


def measure_param_renamed_recall() -> dict:
    clean_corpus = _load_clean_corpus()
    injector, eligibility_fn = INJECTORS["param_renamed"]

    n_total = 0
    n_forward_only = 0  # described_not_in_schema (a) fires
    n_inverse_only = 0  # param_possibly_renamed (g) fires
    n_either = 0  # (a) OR (g) fires -- the headline "fixed" recall
    n_both = 0
    per_case = []

    for entry in clean_corpus:
        eligible = eligibility_fn(entry["tools"])[:_MAX_TARGETS_PER_DEFECT_TYPE]
        for target_name in eligible:
            result = injector(entry["tools"], target_name)
            if result is None:
                continue
            mutated_tools, defect = result
            n_total += 1
            tools = [_T(t) for t in mutated_tools]
            report = lint_tool_set(tools)
            all_violations = report.blocking + report.advisory + report.info
            forward_hit = any(
                v.check == "described_not_in_schema" and target_name in v.tool_name
                for v in all_violations
            )
            inverse_hit = any(
                v.check == "param_possibly_renamed" and target_name in v.tool_name
                for v in all_violations
            )
            if forward_hit:
                n_forward_only += 1
            if inverse_hit:
                n_inverse_only += 1
            if forward_hit or inverse_hit:
                n_either += 1
            if forward_hit and inverse_hit:
                n_both += 1
            # Property-name-shape breakdown (multi-word vs single-word),
            # matching the original v2 measurement's split.
            renamed_prop = defect.detail.split("'")[1]
            shape = "multi_word" if "_" in renamed_prop else "single_word"
            per_case.append(
                {
                    "base_tool_set": entry["name"],
                    "tool_name": target_name,
                    "renamed_prop": renamed_prop,
                    "shape": shape,
                    "forward_hit": forward_hit,
                    "inverse_hit": inverse_hit,
                    "either_hit": forward_hit or inverse_hit,
                }
            )

    by_shape: dict[str, dict] = {}
    for shape in ("multi_word", "single_word"):
        cases = [c for c in per_case if c["shape"] == shape]
        n = len(cases)
        by_shape[shape] = {
            "n": n,
            "recall_forward_only": sum(c["forward_hit"] for c in cases) / n if n else None,
            "recall_inverse_only": sum(c["inverse_hit"] for c in cases) / n if n else None,
            "recall_either": sum(c["either_hit"] for c in cases) / n if n else None,
        }

    return {
        "n_total": n_total,
        "recall_forward_only_pct": 100.0 * n_forward_only / n_total,
        "recall_inverse_only_pct": 100.0 * n_inverse_only / n_total,
        "recall_either_pct": 100.0 * n_either / n_total,
        "n_both_checks_fired": n_both,
        "by_property_shape": by_shape,
        "per_case": per_case,
    }


def main() -> None:
    print("=== Clean-corpus false-alarm rate (with param_possibly_renamed added) ===")
    fa = measure_clean_corpus_false_alarms()
    for k, v in fa.items():
        if k != "violations_by_check":
            print(f"  {k}: {v}")
    print(f"  violations_by_check: {fa['violations_by_check']}")

    print("\n=== param_renamed recall (forward-only vs inverse-only vs either) ===")
    recall = measure_param_renamed_recall()
    print(f"  n_total: {recall['n_total']}")
    print(
        f"  recall_forward_only_pct (check a alone, same as v2): {recall['recall_forward_only_pct']:.1f}%"
    )
    print(f"  recall_inverse_only_pct (check g alone): {recall['recall_inverse_only_pct']:.1f}%")
    print(
        f"  recall_either_pct (a OR g -- the fixed headline number): {recall['recall_either_pct']:.1f}%"
    )
    print(f"  n_both_checks_fired: {recall['n_both_checks_fired']}")
    for shape, stats in recall["by_property_shape"].items():
        print(f"  {shape}: {stats}")

    out = {"clean_corpus_false_alarms": fa, "param_renamed_recall": recall}
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
