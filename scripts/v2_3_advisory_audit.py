"""Task 1 (v2.3) — audit the -80pp ADVISORY (param_renamed) causal effect
before any re-tiering. Local Ollama only (no GCP), per the v2.3 brief.

1a is answered by static inspection (no inference) -- see the injector
output itself: `inject_param_renamed` never touches the description, only
the schema property key, so the description stays fluent, unchanged prose
in every case. Not covered here.

1c: decompose each AFTER-variant failure into wrong-tool-selection,
refusal/parse-failure, call-error, or argument-construction-failure, using
the full RunResult (selected_tool, success, error, parse_failed) that the
original measurement's scoring step (`_score` in
scripts/v2_2_causal_chain_multimodel.py) collapsed into a single scalar.

Reuses the exact same 6 (tool_set, target_tool) instances the original
ADVISORY measurement used, on gemma2:9b and llama3.1:8b (both already
pulled locally; qwen2.5:7b is not in the local Ollama library and is not
re-pulled here -- disclosed gap, not required to answer a mechanism
question that should not be model-specific).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.client import cleanup_connection, connect_stdio  # noqa: E402
from agentgauge.providers import OllamaProvider  # noqa: E402
from agentgauge.runner import run_tasks  # noqa: E402
from evals.fixtures.predictive_validity.blind_tasks import BLIND_TASKS  # noqa: E402
from evals.fixtures.predictive_validity.constraints import (  # noqa: E402
    TASK_CONSTRAINTS,
    constraint_satisfaction,
)
from evals.fixtures.predictive_validity.manifest import MANIFEST  # noqa: E402

MODELS = ["gemma2:9b", "llama3.1:8b", "qwen2.5:7b"]
INSTANCES = [
    ("confusable_server_oracle", "query_records"),
    ("call_constraints_server_oracle", "set_acquisition_mode"),
    ("call_constraints_v2_server_oracle", "register_channel"),
    ("t18_oracle_server", "retrieve_row"),
    ("rw1_arm_oracle", "search_repositories"),
    ("p2a_arm_oracle", "list_orders"),
]
OUT_PATH = Path("evals/fixtures/v2_3_advisory_audit.json")


def _server_path_to_module(server_path: str) -> str:
    return server_path.removesuffix(".py").replace("/", ".")


async def _run_variant(module_path: str, mutation: tuple[str, str] | None, tasks: list, model: str):
    if mutation is None:
        args = [module_path.replace(".", "/") + ".py"]
    else:
        defect_type, target_tool = mutation
        args = ["scripts/_mutated_stdio_server.py", module_path, defect_type, target_tool]

    provider = OllamaProvider(model)
    client, ctx = await connect_stdio(sys.executable, args)
    try:
        return await run_tasks(tasks, client, provider, trials=1)
    finally:
        await cleanup_connection(ctx)


def _classify(r, target_tool: str, constraints_by_key: dict) -> dict:
    if r.parse_failed:
        category = "refusal_or_unparseable"
    elif r.selected_tool != target_tool:
        category = "wrong_tool_selection"
    elif not r.success:
        category = "call_error"
    else:
        key = (r.task.tool_name, r.task.description)
        constraints = constraints_by_key.get(key)
        score = constraint_satisfaction(r.constructed_args, constraints)
        category = "success" if score >= 1.0 else "argument_construction_failure"
    return {
        "task": r.task.description,
        "selected_tool": r.selected_tool,
        "success": r.success,
        "error": r.error,
        "parse_failed": r.parse_failed,
        "constructed_args": r.constructed_args,
        "category": category,
    }


def _load_state() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict) -> None:
    OUT_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def main() -> None:
    by_name = {e.name: e for e in MANIFEST}
    state = _load_state()

    for model in MODELS:
        state.setdefault(model, {})
        for ts_name, target_tool in INSTANCES:
            key = f"{ts_name}::{target_tool}"
            if key in state[model]:
                print(f"[skip, checkpointed] {model} {key}", flush=True)
                continue
            print(f"Measuring {model} {key}...", flush=True)
            server_path = by_name[ts_name].server_path
            module_path = _server_path_to_module(server_path)
            all_tasks = BLIND_TASKS[ts_name]
            constraints_by_key = TASK_CONSTRAINTS[ts_name]
            target_tasks = [t for t in all_tasks if t.tool_name == target_tool]

            after_results = await _run_variant(
                module_path, ("param_renamed", target_tool), target_tasks, model
            )
            classified = [_classify(r, target_tool, constraints_by_key) for r in after_results]
            state[model][key] = classified
            _save_state(state)
            print(f"    {json.dumps([c['category'] for c in classified])}", flush=True)

    print("\n=== Failure-mode breakdown (AFTER/mutated variant, param_renamed) ===", flush=True)
    for model in MODELS:
        counts: dict[str, int] = {}
        total = 0
        for classified in state[model].values():
            for c in classified:
                counts[c["category"]] = counts.get(c["category"], 0) + 1
                total += 1
        print(f"{model}: n={total}", flush=True)
        for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"    {cat}: {n} ({100 * n / total:.1f}%)", flush=True)

    _save_state(state)
    print(f"\nWrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    import traceback

    try:
        asyncio.run(main())
    except BaseException:
        print("FATAL:", flush=True)
        traceback.print_exc()
        raise
