from __future__ import annotations

# EXP-1 validation-anchor check -- confirms agentgauge.exp1_classifier's REAL
# compute_family_result/compute_server_result code reproduces the pre-registered
# OUT-OF-REGIME expectation for github-mcp and aws-iam-mcp.
#
# NOT A FRESH MODEL RUN. TrialOutcome objects below are a faithful re-encoding of
# the ALREADY-PUBLISHED RW1/RW2 aggregate result (exp4_regime_map.md: "Arm A 100%
# (21/21)" for GitHub MCP, "Arm A 100% (29/29, incl. 12 contested)" for AWS IAM) --
# a 100% aggregate can only be produced if every individual trial was also
# SELECTED-CORRECT, so this reconstruction loses no information relative to the
# published finding. This script exercises the real classifier CODE against known
# ground truth; it does not claim new agent/judge inference was spent this session.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.exp1_classifier import (  # noqa: E402
    ContestedTask,
    TrialOutcome,
    compute_family_result,
    compute_server_result,
)
from agentgauge.exp1_mirror import load_mirror  # noqa: E402
from agentgauge.frozen_protocol import SELECTED_CORRECT, TRIALS_PER_ARM  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIRRORS_DIR = REPO_ROOT / "evals" / "fixtures" / "exp1_mirrors"
OUTPUT_PATH = REPO_ROOT / "evals" / "fixtures" / "exp1_anchor_validation.json"

# server_id -> {family_id: [tool_names]} for the families RW1/RW2 actually ran
# contested tasks through (source: evals/fixtures/rw1_github_catalog.py,
# rw2_aws_iam_catalog.py FAMILIES + TASKS).
_RW1_TESTED_FAMILIES = {
    "pr_read_family": [
        "get_pull_request",
        "get_pull_request_diff",
        "get_pull_request_files",
        "get_pull_request_reviews",
        "get_pull_request_comments",
        "merge_pull_request",
    ],
    "search_family": ["search_repositories", "search_code", "search_issues", "search_users"],
    "file_ops_family": ["get_file_contents", "create_or_update_file", "push_files"],
    "list_family": ["list_pull_requests", "list_issues", "list_commits", "list_branches"],
    "repo_ops_family": [
        "get_repository",
        "list_repositories",
        "create_repository",
        "fork_repository",
    ],
}
_RW2_TESTED_FAMILIES = {
    "attach_detach_family": [
        "attach_user_policy",
        "attach_group_policy",
        "detach_user_policy",
        "detach_group_policy",
    ],
    "list_policies_family": [
        "list_policies",
        "list_user_policies",
        "list_role_policies",
        "list_users",
        "list_groups",
        "list_roles",
    ],
    "destructive_pair": ["delete_user_policy", "delete_role_policy"],
}


def _all_correct_outcomes(tool_names: list[str]) -> tuple[list[ContestedTask], list[TrialOutcome]]:
    """A ContestedTask + TrialOutcome set encoding: every task, every trial,
    SELECTED-CORRECT -- the only way to produce a published 100% aggregate."""
    tasks = [
        ContestedTask(task_id=name, family_id="", task_text="", gold_tool=name)
        for name in tool_names
    ]
    outcomes = [
        TrialOutcome(
            task_id=t.task_id, trial=trial, outcome=SELECTED_CORRECT, selected_tool=t.gold_tool
        )
        for t in tasks
        for trial in range(TRIALS_PER_ARM)
    ]
    return tasks, outcomes


def validate_anchor(server_id: str, tested_families: dict[str, list[str]]) -> dict:
    mirror = load_mirror(MIRRORS_DIR / f"{server_id}.json")
    family_results = []
    for family_id, tool_names in tested_families.items():
        tasks, arm_a_outcomes = _all_correct_outcomes(tool_names)
        for t in tasks:
            t.family_id = family_id
        fr = compute_family_result(
            server_id=server_id,
            family_id=family_id,
            tool_names=tool_names,
            arm_a_outcomes=arm_a_outcomes,
            arm_b_outcomes=[],  # never reached -- Arm A shows no headroom
            contested_tasks=tasks,
        )
        family_results.append(fr)

    server_result = compute_server_result(
        mirror=mirror,
        family_results=family_results,
        is_validation_anchor=True,
        anchor_known_result="OUT-OF-REGIME",
    )

    reproduced = (not server_result.in_regime) and server_result.n_aborted == len(family_results)
    return {
        "server_id": server_id,
        "known_result": "OUT-OF-REGIME",
        "reproduced": reproduced,
        "n_families_tested": server_result.n_families,
        "n_in_regime": server_result.n_in_regime,
        "n_out_regime": server_result.n_out_regime,
        "n_aborted_no_headroom": server_result.n_aborted,
        "classifier_verdict": "OUT-OF-REGIME" if not server_result.in_regime else "IN-REGIME",
        "families": [
            {
                "family_id": fr.family_id,
                "n_contested": fr.n_contested,
                "arm_a_accuracy": fr.arm_a_accuracy,
                "headroom_gated": fr.headroom_gated,
                "aborted": fr.aborted,
                "abort_reason": fr.abort_reason,
            }
            for fr in family_results
        ],
    }


def main() -> None:
    github_result = validate_anchor("github-mcp", _RW1_TESTED_FAMILIES)
    aws_result = validate_anchor("aws-iam-mcp", _RW2_TESTED_FAMILIES)

    output = {
        "experiment_id": "EXP-1",
        "purpose": "Validation-anchor check per pre-reg: confirm the classifier reproduces the known OUT-OF-REGIME result.",
        "method_disclosure": (
            "NOT a fresh model run. TrialOutcome data is a faithful re-encoding of the "
            "already-published RW1/RW2 aggregate result (docs/research/exp4_regime_map.md), "
            "run through the real agentgauge.exp1_classifier code to validate the CODE, not to "
            "claim new agent/judge inference was spent this session."
        ),
        "anchors": [github_result, aws_result],
        "all_anchors_reproduced": github_result["reproduced"] and aws_result["reproduced"],
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    for r in (github_result, aws_result):
        status = "PASS" if r["reproduced"] else "FAIL"
        print(
            f"[{status}] {r['server_id']}: known={r['known_result']} "
            f"classifier_verdict={r['classifier_verdict']} "
            f"(n_families={r['n_families_tested']}, n_aborted={r['n_aborted_no_headroom']})"
        )
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
