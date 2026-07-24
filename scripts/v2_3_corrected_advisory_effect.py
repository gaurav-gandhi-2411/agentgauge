"""Task 1 (v2.3) — corrected ADVISORY (param_renamed) causal effect.

The original measurement (`evals/fixtures/v2_2_causal_chain_multimodel.json`,
advisory_instances) scored the AFTER (mutated) variant with
`constraint_satisfaction`, which looks up the constraint's PRE-rename
parameter name against the agent's constructed_args -- but a schema-valid
call to the mutated tool must use the RENAMED key. This scored a large
fraction of genuinely-correct agent responses as total failures. Confirmed
by direct inspection (`reports/v2_3_task1_advisory_audit.md`) and an
independent verifier pass (~77% of the "argument construction failure"
category was this artifact, not a real agent mistake).

This script re-scores the exact same before/after pairs using
`constraint_satisfaction_renamed` (rename-aware) for the AFTER variant, using:
  - "before" joint_success: unchanged, taken directly from
    evals/fixtures/v2_2_causal_chain_multimodel.json (the clean/unmutated run
    is unaffected by this bug -- nothing was renamed there).
  - "after" joint_success: recomputed from evals/fixtures/v2_3_advisory_audit.json's
    raw per-task RunResult fields (selected_tool, success, parse_failed,
    constructed_args), which the original scoring collapsed into a single
    scalar and did not retain.

Zero new inference -- pure re-scoring of already-collected data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.harness import t_adjusted_cluster_bootstrap_mean_ci  # noqa: E402
from evals.fixtures.predictive_validity.blind_tasks import BLIND_TASKS  # noqa: E402
from evals.fixtures.predictive_validity.constraints import (  # noqa: E402
    TASK_CONSTRAINTS,
    constraint_satisfaction_renamed,
)

ORIG_PATH = Path("evals/fixtures/v2_2_causal_chain_multimodel.json")
AUDIT_PATH = Path("evals/fixtures/v2_3_advisory_audit.json")
OUT_PATH = Path("evals/fixtures/v2_3_corrected_advisory_effect.json")

# (tool_set, target_tool) -> (old_param_name, new_param_name), as produced by
# inject_param_renamed for these specific instances (deterministic given the
# eligibility function's iteration order -- verified against the injector's
# own "Injected: ..." log line for every instance in this set).
RENAMES: dict[str, tuple[str, str]] = {
    "confusable_server_oracle::query_records": ("field", "field_v2"),
    "call_constraints_server_oracle::set_acquisition_mode": ("mode", "mode_v2"),
    "call_constraints_v2_server_oracle::register_channel": ("channel_ref", "channel_ref_v2"),
    "t18_oracle_server::retrieve_row": ("query", "query_v2"),
    "rw1_arm_oracle::search_repositories": ("query", "query_v2"),
    "p2a_arm_oracle::list_orders": ("status", "status_v2"),
}


def _corrected_after_joint_success(
    audit_entry: dict, target_tool: str, constraints: list | None
) -> float:
    if audit_entry["parse_failed"]:
        return 0.0
    if audit_entry["selected_tool"] != target_tool:
        return 0.0
    if not audit_entry["success"]:
        return 0.0
    old_name, new_name = RENAMES[audit_entry["_instance_key"]]
    return constraint_satisfaction_renamed(
        audit_entry["constructed_args"], constraints, {old_name: new_name}
    )


def main() -> None:
    with ORIG_PATH.open(encoding="utf-8") as f:
        orig = json.load(f)
    with AUDIT_PATH.open(encoding="utf-8") as f:
        audit = json.load(f)

    models = [m for m in audit if m in orig]
    result: dict[str, dict] = {}
    print(f"Re-scoring param_renamed effect for models: {models}", flush=True)

    for model in models:
        deltas_original = []
        deltas_corrected = []
        per_task_detail = []
        for inst in orig[model]["advisory_instances"]:
            ts, tool = inst["tool_set"], inst["target_tool"]
            instance_key = f"{ts}::{tool}"
            constraints_by_key = TASK_CONSTRAINTS[ts]
            all_tasks = [t for t in BLIND_TASKS[ts] if t.tool_name == tool]
            audit_entries = audit[model][instance_key]
            for i, td in enumerate(inst["task_deltas"]):
                before = td["before_joint_success"]
                ae = dict(audit_entries[i])
                ae["_instance_key"] = instance_key
                task_obj = all_tasks[i] if i < len(all_tasks) else None
                constraints = (
                    constraints_by_key.get((tool, ae["task"])) if task_obj is not None else None
                )
                after_corrected = _corrected_after_joint_success(ae, tool, constraints)
                deltas_original.append(td["delta"])
                deltas_corrected.append(after_corrected - before)
                per_task_detail.append(
                    {
                        "tool_set": ts,
                        "tool": tool,
                        "before": before,
                        "after_original": td["after_joint_success"],
                        "after_corrected": after_corrected,
                        "category": ae["category"],
                    }
                )

        point_o, lo_o, hi_o = t_adjusted_cluster_bootstrap_mean_ci(deltas_original, seed=42)
        point_c, lo_c, hi_c = t_adjusted_cluster_bootstrap_mean_ci(deltas_corrected, seed=42)
        result[model] = {
            "n": len(deltas_original),
            "original": {"mean_delta": point_o, "ci_lo": lo_o, "ci_hi": hi_o},
            "corrected": {"mean_delta": point_c, "ci_lo": lo_c, "ci_hi": hi_c},
            "per_task_detail": per_task_detail,
        }
        print(
            f"{model}: ORIGINAL mean={point_o:+.4f} CI=[{lo_o:+.4f},{hi_o:+.4f}]  "
            f"CORRECTED mean={point_c:+.4f} CI=[{lo_c:+.4f},{hi_c:+.4f}]  n={len(deltas_original)}",
            flush=True,
        )

    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
