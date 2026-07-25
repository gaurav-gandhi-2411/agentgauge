"""v0.4.0 Task 1: re-measure the argument-degradation effect size (does
description quality fix argument construction?) under the CORRECTED checker
(post-artifact-#7 agentgauge.constraints/agentgauge.audit), at the validated
optimal allocation (1 trial/task, agentgauge diff's own default) on the full
253-task real corpus (62 original call_constraints* tasks + 191 v2.4/v2.5
real-API corpus tasks), across gemma2:9b / llama3.1:8b / qwen2.5:7b.

Superseded methodology note vs. v2.2's Task A (reports/v2_2_task_a_reallocation.md):
that measurement pooled 62 tasks and reported a raw joint-success-rate delta
with NO formal CI. This script goes further -- it also computes a paired,
task-clustered, CUPED-adjusted 95% CI via agentgauge.harness.diff_server_level,
the same estimator agentgauge diff itself uses.

IMPORTANT (found while designing this measurement, NOT fixed here --
disclosed, out of scope per this task's "no new hardening" constraint):
agentgauge.harness.TrialOutcome.task_tool_name is used as the task-CLUSTERING
key by aggregate_to_tasks/pair_tasks_common_random_numbers -- but
agentgauge/cli.py's _collect_trials sets it to the bare tool name
(`r.task.tool_name`), not a task-unique key. Every fixture in this corpus has
multiple tasks per tool (e.g. GitHub's update_issue_state has 6), so the
SHIPPED CLI's own `agentgauge diff`/`eval` would silently collapse same-tool
tasks into one cluster, understating the true number of independent task
clusters (253 tasks -> ~48 tool-level clusters across this corpus). This
script does NOT reproduce that bug: it builds a task-unique clustering key
(f"{fixture}::{tool_name}::{description}") so the CI reported here is valid
for the full 253 independent task clusters, matching what "253 tasks" is
supposed to mean. See reports/v0_4_0_task1_argument_degradation.md for the
disclosure and recommended (not yet applied) product fix.

Resumable: every trial record is appended to a JSONL checkpoint immediately
after scoring. Re-running this script skips any (model, fixture, variant,
task_key) combination already present in the checkpoint file.

Run: uv run python scripts/v2_5_argument_degradation_live.py
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from agentgauge.audit import run_audit
from agentgauge.client import cleanup_connection, connect_stdio
from agentgauge.constraints import BlindTask, Constraint, constraint_satisfaction
from agentgauge.harness import TrialOutcome, diff_server_level
from agentgauge.providers import OllamaProvider
from agentgauge.runner import run_tasks
from agentgauge.tasks import Task

REPO_ROOT = Path(__file__).parent.parent
CHECKPOINT_PATH = REPO_ROOT / "evals" / "fixtures" / "v2_5_argument_degradation_live.jsonl"
SUMMARY_PATH = REPO_ROOT / "evals" / "fixtures" / "v2_5_argument_degradation_summary.json"

MODELS = ["gemma2:9b", "llama3.1:8b", "qwen2.5:7b"]

# (fixture_name, bad_server, fixed_server, tasks_module, constraints_attr)
# constraints_attr: "TASK_CONSTRAINTS" (dict[key, list[Constraint]]) or
# "GOLD_CONSTRAINTS" (dict[key, dict[str, str]] -- older ty_tasks.py format,
# normalized below).
FIXTURES: list[tuple[str, str, str, str, str]] = [
    (
        "call_constraints",
        "examples/call_constraints_server.py",
        "examples/call_constraints_server_fixed.py",
        "evals.fixtures.ty_tasks",
        "GOLD_CONSTRAINTS",
    ),
    (
        "call_constraints_v2",
        "examples/call_constraints_v2_server.py",
        "examples/call_constraints_v2_server_fixed.py",
        "evals.fixtures.ty2_tasks",
        "TASK_CONSTRAINTS",
    ),
    (
        "github_issues",
        "examples/github_issues_server.py",
        "examples/github_issues_server_fixed.py",
        "evals.fixtures.v2_4_corpus.github_issues_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "stripe_payments",
        "examples/stripe_payments_server.py",
        "examples/stripe_payments_server_fixed.py",
        "evals.fixtures.v2_4_corpus.stripe_payments_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "gcal",
        "examples/gcal_server.py",
        "examples/gcal_server_fixed.py",
        "evals.fixtures.v2_4_corpus.gcal_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "jira_issues",
        "examples/jira_issues_server.py",
        "examples/jira_issues_server_fixed.py",
        "evals.fixtures.v2_4_corpus.jira_issues_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "slack_messaging",
        "examples/slack_messaging_server.py",
        "examples/slack_messaging_server_fixed.py",
        "evals.fixtures.v2_4_corpus.slack_messaging_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "docker_containers",
        "examples/docker_containers_server.py",
        "examples/docker_containers_server_fixed.py",
        "evals.fixtures.v2_4_corpus.docker_containers_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "k8s_workloads",
        "examples/k8s_workloads_server.py",
        "examples/k8s_workloads_server_fixed.py",
        "evals.fixtures.v2_4_corpus.k8s_workloads_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "twilio_messaging",
        "examples/twilio_messaging_server.py",
        "examples/twilio_messaging_server_fixed.py",
        "evals.fixtures.v2_4_corpus.twilio_messaging_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "aws_s3",
        "examples/aws_s3_server.py",
        "examples/aws_s3_server_fixed.py",
        "evals.fixtures.v2_4_corpus.aws_s3_fixture",
        "TASK_CONSTRAINTS",
    ),
    (
        "spotify_playlists",
        "examples/spotify_playlists_server.py",
        "examples/spotify_playlists_server_fixed.py",
        "evals.fixtures.v2_4_corpus.spotify_playlists_fixture",
        "TASK_CONSTRAINTS",
    ),
]


def _load_fixture_tasks(module_path: str, constraints_attr: str) -> list[BlindTask]:
    mod = importlib.import_module(module_path)
    tasks: list[Task] = mod.TASKS
    raw_constraints: dict[tuple[str, str], Any] = getattr(mod, constraints_attr)

    blind_tasks = []
    for t in tasks:
        key = (t.tool_name, t.description)
        raw = raw_constraints.get(key)
        if raw is None:
            constraints: list[Constraint] = []
        elif constraints_attr == "GOLD_CONSTRAINTS":
            # dict[str, str] -> list[Constraint(kind="enum")]
            constraints = [Constraint(param=p, kind="enum", gold_value=v) for p, v in raw.items()]
        else:
            constraints = raw
        blind_tasks.append(
            BlindTask(tool_name=t.tool_name, description=t.description, constraints=constraints)
        )
    return blind_tasks


def _load_checkpoint() -> set[tuple[str, str, str, str]]:
    """Returns the set of (model, fixture, variant, task_key) already recorded."""
    done: set[tuple[str, str, str, str]] = set()
    if not CHECKPOINT_PATH.exists():
        return done
    with CHECKPOINT_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            done.add((rec["model"], rec["fixture"], rec["variant"], rec["task_key"]))
    return done


def _append_checkpoint(record: dict[str, Any]) -> None:
    with CHECKPOINT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()


async def _run_variant(
    model: str,
    fixture_name: str,
    variant: str,
    server_path: str,
    blind_tasks: list[BlindTask],
    done: set[tuple[str, str, str, str]],
) -> None:
    remaining = [
        t
        for t in blind_tasks
        if (model, fixture_name, variant, f"{t.tool_name}::{t.description}") not in done
    ]
    if not remaining:
        print(f"  [{model}] {fixture_name}/{variant}: already complete, skipping", flush=True)
        return

    client, ctx = await connect_stdio(sys.executable, [server_path])
    try:
        info = await client.introspect()
        tools = list(info.tools)

        # Schema-only audit gate (the CORRECTED checker, v2.5 Task 1's fix):
        # confirm every constraint's param resolves against THIS connected
        # schema before spending any inference. Should always pass -- every
        # fixture here was validated in v2.5 Task 2 -- but this is the
        # correctness gate this whole task is closing the loop on, so it
        # runs for real, not skipped as a formality.
        report = run_audit(blind_tasks, after_tools=tools)
        if report.blocking:
            details = "; ".join(f.detail for f in report.blocking)
            raise RuntimeError(
                f"agentgauge audit BLOCKED {fixture_name}/{variant} against {model} -- "
                f"refusing to run live inference on an invalid measurement: {details}"
            )

        constraints_by_key = {(t.tool_name, t.description): t.constraints for t in remaining}
        task_objs = [Task(tool_name=t.tool_name, description=t.description) for t in remaining]
        provider = OllamaProvider(model)
        results = await run_tasks(task_objs, client, provider, trials=1)

        for r in results:
            key = (r.task.tool_name, r.task.description)
            constraints = constraints_by_key.get(key)
            score = (
                constraint_satisfaction(r.constructed_args, constraints)
                if r.selected_tool == r.task.tool_name
                else 0.0
            )
            task_key = f"{r.task.tool_name}::{r.task.description}"
            _append_checkpoint(
                {
                    "model": model,
                    "fixture": fixture_name,
                    "variant": variant,
                    "task_key": task_key,
                    "tool_name": r.task.tool_name,
                    "selected_tool": r.selected_tool,
                    "constraint_satisfaction": score,
                }
            )
        print(f"  [{model}] {fixture_name}/{variant}: {len(results)} trials recorded", flush=True)
    finally:
        await cleanup_connection(ctx)


async def main() -> None:
    fixture_tasks: dict[str, list[BlindTask]] = {}
    total_expected = 0
    for name, _bad, _fixed, module_path, constraints_attr in FIXTURES:
        tasks = _load_fixture_tasks(module_path, constraints_attr)
        fixture_tasks[name] = tasks
        total_expected += len(tasks)
    print(
        f"Loaded {len(FIXTURES)} fixtures, {total_expected} tasks each (bad+fixed x 3 models "
        f"= {total_expected * 2 * len(MODELS)} total trials)",
        flush=True,
    )

    for model in MODELS:
        print(f"=== model: {model} ===", flush=True)
        for name, bad_path, fixed_path, _module_path, _attr in FIXTURES:
            done = _load_checkpoint()
            blind_tasks = fixture_tasks[name]
            await _run_variant(model, name, "bad", bad_path, blind_tasks, done)
            done = _load_checkpoint()
            await _run_variant(model, name, "fixed", fixed_path, blind_tasks, done)

    print("All live trials collected. Computing pooled diff_server_level per model...", flush=True)

    done = _load_checkpoint()
    # Rebuild TrialOutcome lists per model/variant from the checkpoint file,
    # using a globally-unique task_tool_name (fixture::tool::description) so
    # pairing/clustering is valid across all 12 fixtures at once (see module
    # docstring -- the shipped CLI's bare-tool-name key would collide, e.g.
    # github_issues and jira_issues both have a `create_issue` tool).
    by_model: dict[str, dict[str, list[TrialOutcome]]] = {
        m: {"bad": [], "fixed": []} for m in MODELS
    }
    with CHECKPOINT_PATH.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line.strip())
            unique_key = f"{rec['fixture']}::{rec['task_key']}"
            # TrialOutcome.selection_correct is `selected_tool == task_tool_name` --
            # task_tool_name here is the unique CLUSTERING key (not the bare tool
            # name), so the real selection-correctness (selected_tool == the
            # actual gold tool_name recorded in the checkpoint) must be evaluated
            # separately and encoded via selected_tool matching unique_key exactly
            # when correct, and a sentinel that can never match otherwise.
            really_correct = rec["selected_tool"] == rec["tool_name"]
            by_model[rec["model"]][rec["variant"]].append(
                TrialOutcome(
                    task_tool_name=unique_key,
                    selected_tool=unique_key if really_correct else "__WRONG_TOOL__",
                    constraint_satisfaction=rec["constraint_satisfaction"],
                )
            )

    summary: dict[str, Any] = {}
    for model in MODELS:
        before = by_model[model]["bad"]
        after = by_model[model]["fixed"]
        before_rate = sum(t.joint_success for t in before) / len(before) if before else None
        after_rate = sum(t.joint_success for t in after) / len(after) if after else None
        result = diff_server_level(before, after)
        summary[model] = {
            "n_before_trials": len(before),
            "n_after_trials": len(after),
            "before_rate": before_rate,
            "after_rate": after_rate,
            "n_tasks_matched": result.n_tasks_matched,
            "unmatched_task_names": result.unmatched_task_names,
            "delta": result.delta,
            "ci_lo": result.ci_lo,
            "ci_hi": result.ci_hi,
            "verdict": result.verdict.value,
            "message": result.message,
            "cuped_theta": result.cuped_theta,
            "cuped_variance_reduction_pct": result.cuped_variance_reduction_pct,
            "used_few_clusters_correction": result.used_few_clusters_correction,
        }
        print(
            f"{model}: before={before_rate:.4f} after={after_rate:.4f} "
            f"delta={result.delta:+.4f} 95% CI [{result.ci_lo:+.4f}, {result.ci_hi:+.4f}] "
            f"verdict={result.verdict.value} (n_tasks_matched={result.n_tasks_matched})",
            flush=True,
        )

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Summary written to {SUMMARY_PATH}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
