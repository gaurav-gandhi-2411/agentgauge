"""Task 4b (v2.2): complete the cross-model argument-degradation replication
left inconclusive in v2.1 (`reports/v2_1_cross_model_validation.md`).

v2.1's cross-model check used a REDUCED 16-task subset of
`CALL_CONSTRAINTS_SERVER_TASKS` (2 tasks/tool, 32 available) to fit inside a
single Cloud Run session before the ephemeral-disk/proxy infrastructure was
fixed -- the argument-accuracy pattern was diluted by that reduction (half
the tools are unconstrained and always score 1.0) and came out inconclusive.

This script uses the FULL 32-task set, trials_per_task=1 (Task 1's optimal
allocation), across gemma2:9b / llama3.1:8b / qwen2.5:7b, routed through the
now-baked-image `agentgauge-agent` service (models already present, no pull
step needed -- see reports/v2_2_optimal_allocation.md and the Task 3/4 infra
commit for the image-baking work).

Checkpointed per (model, variant) combo, same pattern as v2.1's script.
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
)
from evals.fixtures.predictive_validity.constraints import (  # noqa: E402
    TASK_CONSTRAINTS,
    constraint_satisfaction,
)

CLOUD_RUN_URL = "https://agentgauge-agent-6txxpjhu2a-uc.a.run.app"
_IDENTITY_TOKEN = os.environ["AGENTGAUGE_AGENT_IDENTITY_TOKEN"]

MODELS = ["gemma2:9b", "llama3.1:8b", "qwen2.5:7b"]
VARIANTS = {
    "before": "examples/call_constraints_server.py",
    "after": "examples/call_constraints_server_fixed.py",
}
OUT_PATH = Path("evals/fixtures/v2_2_cross_model_full.json")


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


async def _run_one(server_path: str, model: str) -> list[TrialOutcome]:
    provider = AuthenticatedOllamaProvider(model)
    client, ctx = await connect_stdio(sys.executable, [server_path])
    try:
        constraints_by_key = TASK_CONSTRAINTS["call_constraints_server"]
        run_results = await run_tasks(
            list(CALL_CONSTRAINTS_SERVER_TASKS), client, provider, trials=1
        )
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


def _load_checkpoint() -> dict[str, dict[str, dict]]:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {}


async def main() -> None:
    results = _load_checkpoint()
    print(f"Full task set: {len(CALL_CONSTRAINTS_SERVER_TASKS)} tasks", flush=True)
    for model in MODELS:
        results.setdefault(model, {})
        for variant_name, server_path in VARIANTS.items():
            if variant_name in results[model]:
                print(
                    f"Skipping model={model} variant={variant_name} (already checkpointed)",
                    flush=True,
                )
                continue
            print(f"Running model={model} variant={variant_name} ({server_path})...", flush=True)
            outcomes = await _run_one(server_path, model)
            rate = DecomposedRate.from_trials(outcomes)
            results[model][variant_name] = {
                "n_trials": rate.n_trials,
                "selection_accuracy": rate.selection_accuracy,
                "argument_accuracy_given_correct_selection": rate.argument_accuracy_given_correct_selection,
                "joint_success_rate": rate.joint_success_rate,
            }
            print(f"  {json.dumps(results[model][variant_name])}", flush=True)
            OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(
        "\n=== Summary: selection accuracy (before -> after) vs argument accuracy (before -> after) ===",
        flush=True,
    )
    for model in MODELS:
        b, a = results[model]["before"], results[model]["after"]
        print(
            f"{model:15s}  selection: {b['selection_accuracy']:.3f} -> {a['selection_accuracy']:.3f}  "
            f"argument: {b['argument_accuracy_given_correct_selection']} -> "
            f"{a['argument_accuracy_given_correct_selection']}",
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
