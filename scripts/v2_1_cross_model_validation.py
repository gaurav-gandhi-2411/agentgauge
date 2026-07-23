"""Task 6 (v2.1): cross-model validation of the harness's core finding.

The predictive-validity study's flagship real-world pattern (`call_constraints_server`
family): tool-selection accuracy stays flat/perfect while argument-construction accuracy
degrades under worse descriptions -- previously measured ONLY with gemma2:9b as the acting
agent. This script re-runs the identical task set (evals/fixtures/predictive_validity/
blind_tasks.py's CALL_CONSTRAINTS_SERVER_TASKS, 32 anti-tautology tasks, with the same
constraint definitions already used for the historical gemma2:9b collection) against
`examples/call_constraints_server.py` (before) and `examples/call_constraints_server_fixed.py`
(after), across THREE acting-agent models: gemma2:9b, llama3.1:8b, qwen2.5:7b.

Answers: does the selection-flat/argument-degrades pattern hold across all three model
families, or is it model-specific? Live inference required -- routes through the
`agentgauge-agent` Cloud Run proxy (see reports/v2_1_cross_model_validation.md for the
infrastructure rebuild this required).

trials=1 per task (32 trials/arm/model) to keep this bounded -- Task 1 already showed
repeat trials on the same deterministic task carry almost no independent information
(ICC=0.793), so a single trial per task is not a meaningfully weaker design than the
historical 3-trials-per-task collection for this specific question (does the SIGN/
existence of the pattern replicate, not a precise effect-size estimate).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.client import cleanup_connection, connect_stdio  # noqa: E402
from agentgauge.harness import DecomposedRate, TrialOutcome  # noqa: E402
from agentgauge.providers import OllamaProvider  # noqa: E402
from agentgauge.runner import run_tasks  # noqa: E402
from evals.fixtures.predictive_validity.blind_tasks import (  # noqa: E402
    CALL_CONSTRAINTS_SERVER_TASKS,
)
from evals.fixtures.predictive_validity.constraints import (  # noqa: E402
    TASK_CONSTRAINTS,
    constraint_satisfaction,
)

OllamaProvider.BASE_URL = "http://localhost:11435"  # agentgauge-agent Cloud Run proxy

MODELS = ["gemma2:9b", "llama3.1:8b", "qwen2.5:7b"]
VARIANTS = {
    "before": "examples/call_constraints_server.py",
    "after": "examples/call_constraints_server_fixed.py",
}
OUT_PATH = Path("evals/fixtures/v2_1_cross_model_validation.json")


async def _run_one(server_path: str, model: str) -> list[TrialOutcome]:
    provider = OllamaProvider(model)
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


async def main() -> None:
    results: dict[str, dict[str, dict]] = {}
    for model in MODELS:
        results[model] = {}
        for variant_name, server_path in VARIANTS.items():
            print(f"Running model={model} variant={variant_name} ({server_path})...")
            outcomes = await _run_one(server_path, model)
            rate = DecomposedRate.from_trials(outcomes)
            results[model][variant_name] = {
                "n_trials": rate.n_trials,
                "selection_accuracy": rate.selection_accuracy,
                "argument_accuracy_given_correct_selection": rate.argument_accuracy_given_correct_selection,
                "joint_success_rate": rate.joint_success_rate,
            }
            print(f"  {json.dumps(results[model][variant_name])}")

    print(
        "\n=== Summary: selection accuracy (before -> after) vs argument accuracy (before -> after) ==="
    )
    for model in MODELS:
        b, a = results[model]["before"], results[model]["after"]
        print(
            f"{model:15s}  selection: {b['selection_accuracy']:.3f} -> {a['selection_accuracy']:.3f}  "
            f"argument: {b['argument_accuracy_given_correct_selection']} -> "
            f"{a['argument_accuracy_given_correct_selection']}"
        )

    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
