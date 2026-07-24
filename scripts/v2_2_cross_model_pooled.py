"""Task A2 (v2.2 reorder): scale the cross-model argument-degradation
replication toward Task 1's compute-optimal allocation (100 tasks/arm x 1
trial/task, reports/v2_2_optimal_allocation.md).

`scripts/v2_2_cross_model_full.py` (32 tasks/arm, call_constraints_server
only) is below that optimum and, as measured, reproduced v2.1's inconclusive
result (see evals/fixtures/v2_2_cross_model_full.json: joint success rate
flat before->after for all three models at n=32).

The Task 1 optimum (100 tasks) assumes an unlimited task bank; the real
ceiling here is the number of hand-authored tasks with real gold constraints
that test the SAME phenomenon (argument-construction accuracy under a
constrained-schema before/after pair). Only two such fixtures exist in this
repo -- call_constraints_server (32 tasks) and call_constraints_v2_server (30
tasks, an independently-authored "run 2" fixture, same constraint-mix design:
FORMAT/ENUM/RANGE, confirmed structurally identical in intent by reading both
servers' source). Other "_fixed" pairs (confusable_server, grounded_server,
mediocre_server) test different phenomena (tool-selection disambiguation,
general quality) and are NOT pooled here -- pooling them would conflate a
different causal question, not legitimately raise n.

This script pools BOTH constrained-server pairs -> 62 tasks/arm, the real
achievable ceiling, not the fabricated 100. The achieved MDE at n=62 is
computed and reported alongside the result (Task A3) so "inconclusive" can be
told apart from "no effect."
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402

from agentgauge.client import cleanup_connection, connect_stdio  # noqa: E402
from agentgauge.harness import DecomposedRate, TrialOutcome  # noqa: E402
from agentgauge.providers import Message, OllamaProvider  # noqa: E402
from agentgauge.runner import run_tasks  # noqa: E402
from evals.fixtures.predictive_validity.blind_tasks import (  # noqa: E402
    CALL_CONSTRAINTS_SERVER_TASKS,
    CALL_CONSTRAINTS_V2_SERVER_TASKS,
)
from evals.fixtures.predictive_validity.constraints import (  # noqa: E402
    TASK_CONSTRAINTS,
    constraint_satisfaction,
)

CLOUD_RUN_URL = "https://agentgauge-agent-6txxpjhu2a-uc.a.run.app"
_IDENTITY_TOKEN = os.environ["AGENTGAUGE_AGENT_IDENTITY_TOKEN"]

MODELS = ["gemma2:9b", "llama3.1:8b", "qwen2.5:7b"]
# (constraints_key, tasks, before_server, after_server)
TOOL_SET_PAIRS = [
    (
        "call_constraints_server",
        CALL_CONSTRAINTS_SERVER_TASKS,
        "examples/call_constraints_server.py",
        "examples/call_constraints_server_fixed.py",
    ),
    (
        "call_constraints_v2_server",
        CALL_CONSTRAINTS_V2_SERVER_TASKS,
        "examples/call_constraints_v2_server.py",
        "examples/call_constraints_v2_server_fixed.py",
    ),
]
OUT_PATH = Path("evals/fixtures/v2_2_cross_model_pooled.json")


class AuthenticatedOllamaProvider(OllamaProvider):
    BASE_URL = CLOUD_RUN_URL

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"seed": seed},
        }
        headers = {"Authorization": f"Bearer {_IDENTITY_TOKEN}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self.BASE_URL}/api/chat", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


async def _run_one(server_path: str, model: str, constraints_key: str, tasks: list) -> list[TrialOutcome]:
    provider = AuthenticatedOllamaProvider(model)
    client, ctx = await connect_stdio(sys.executable, [server_path])
    try:
        constraints_by_key = TASK_CONSTRAINTS[constraints_key]
        run_results = await run_tasks(tasks, client, provider, trials=1)
        outcomes = []
        for r in run_results:
            key = (r.task.tool_name, r.task.description)
            constraints = constraints_by_key.get(key)
            score = (
                constraint_satisfaction(r.constructed_args, constraints)
                if r.success and r.selected_tool == r.task.tool_name
                else 0.0
            )
            outcomes.append(
                TrialOutcome(
                    task_tool_name=r.task.tool_name,
                    selected_tool=r.selected_tool,
                    constraint_satisfaction=score,
                )
            )
        return outcomes
    finally:
        await cleanup_connection(ctx)


def _load_checkpoint() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {}


async def main() -> None:
    results = _load_checkpoint()
    total_tasks = sum(len(t) for _, t, _, _ in TOOL_SET_PAIRS)
    print(f"Pooled task set: {total_tasks} tasks across {len(TOOL_SET_PAIRS)} tool sets", flush=True)

    for model in MODELS:
        results.setdefault(model, {})
        for variant_idx, variant_name in enumerate(["before", "after"]):
            if variant_name in results[model]:
                print(f"Skipping model={model} variant={variant_name} (checkpointed)", flush=True)
                continue
            print(f"Running model={model} variant={variant_name}...", flush=True)
            pooled_outcomes: list[TrialOutcome] = []
            for constraints_key, tasks, before_path, after_path in TOOL_SET_PAIRS:
                server_path = before_path if variant_name == "before" else after_path
                outcomes = await _run_one(server_path, model, constraints_key, tasks)
                pooled_outcomes.extend(outcomes)
                print(
                    f"    [{constraints_key}] n={len(outcomes)} "
                    f"joint={sum(o.joint_success for o in outcomes) / len(outcomes):.4f}",
                    flush=True,
                )
            rate = DecomposedRate.from_trials(pooled_outcomes)
            results[model][variant_name] = {
                "n_trials": rate.n_trials,
                "selection_accuracy": rate.selection_accuracy,
                "argument_accuracy_given_correct_selection": rate.argument_accuracy_given_correct_selection,
                "joint_success_rate": rate.joint_success_rate,
            }
            print(f"  pooled: {json.dumps(results[model][variant_name])}", flush=True)
            OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n=== Summary (pooled n=62/arm): joint success rate before -> after ===", flush=True)
    for model in MODELS:
        b, a = results[model]["before"], results[model]["after"]
        delta = a["joint_success_rate"] - b["joint_success_rate"]
        print(
            f"{model:15s}  joint: {b['joint_success_rate']:.4f} -> {a['joint_success_rate']:.4f}  "
            f"(delta={delta:+.4f})",
            flush=True,
        )

    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    import traceback

    try:
        asyncio.run(main())
    except BaseException:
        print("FATAL:", flush=True)
        traceback.print_exc()
        raise
