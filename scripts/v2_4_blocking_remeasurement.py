"""Task 1b (v2.4): re-measure the surviving BLOCKING causal-chain claim
(-13.3 to -28.9pp, `type_enum_contradiction`) after the artifact #7 audit.

Task 1a established that `type_flipped`/`enum_dropped`/`contradictory_required_claim`
never rename a schema property key, so the specific scoring bug that
invalidated the ADVISORY measurement structurally cannot apply here --
`constraint_satisfaction`'s existing (non-rename-aware) scoring is correct
for these three defect types. This script re-runs the exact same instance
selection as `scripts/v2_2_causal_chain_multimodel.py` (BLOCKING types only)
as an independent live replication, not because a bug was found in this
path, but because the task brief asks to re-verify the one surviving causal
claim before trusting it further.

Routes through `agentgauge-agent` Cloud Run (rebuilt after the prior
teardown; local GPU had contention from a resident qwen3:8b -- user
approved GCP use for this specific measurement).
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
from agentgauge.harness import TrialOutcome, t_adjusted_cluster_bootstrap_mean_ci  # noqa: E402
from agentgauge.providers import Message, OllamaProvider  # noqa: E402
from agentgauge.runner import run_tasks  # noqa: E402
from evals.fixtures.predictive_validity.blind_tasks import BLIND_TASKS  # noqa: E402
from evals.fixtures.predictive_validity.constraints import (  # noqa: E402
    TASK_CONSTRAINTS,
    constraint_satisfaction,
)
from evals.fixtures.predictive_validity.manifest import MANIFEST  # noqa: E402
from scripts.v2_defect_injector import INJECTORS, _load_clean_corpus  # noqa: E402

CLOUD_RUN_URL = "https://agentgauge-agent-6txxpjhu2a-uc.a.run.app"
_IDENTITY_TOKEN = os.environ["AGENTGAUGE_AGENT_IDENTITY_TOKEN"]
MODELS = ["gemma2:9b", "llama3.1:8b", "qwen2.5:7b"]
OUT_PATH = Path("evals/fixtures/v2_4_blocking_remeasurement.json")

TOOL_SETS = [
    "confusable_server_oracle",
    "call_constraints_server_oracle",
    "call_constraints_v2_server_oracle",
    "t18_oracle_server",
    "rw1_arm_oracle",
    "p2a_arm_oracle",
]
BLOCKING_DEFECT_TYPES = ["contradictory_required_claim", "type_flipped", "enum_dropped"]
MAX_TARGETS_PER_TOOLSET_PER_DEFECT = 1


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


def _server_path_to_module(server_path: str) -> str:
    return server_path.removesuffix(".py").replace("/", ".")


def _select_instances(defect_types: list[str]) -> list[dict]:
    clean_corpus = {e["name"]: e for e in _load_clean_corpus()}
    by_name = {e.name: e for e in MANIFEST}
    instances = []
    for ts_name in TOOL_SETS:
        entry = clean_corpus[ts_name]
        server_path = by_name[ts_name].server_path
        module_path = _server_path_to_module(server_path)
        for defect_type in defect_types:
            injector, eligibility_fn = INJECTORS[defect_type]
            eligible = eligibility_fn(entry["tools"])[:MAX_TARGETS_PER_TOOLSET_PER_DEFECT]
            for target_tool in eligible:
                instances.append(
                    {
                        "tool_set": ts_name,
                        "module_path": module_path,
                        "defect_type": defect_type,
                        "target_tool": target_tool,
                    }
                )
    return instances


async def _run_variant(
    module_path: str, mutation: tuple[str, str] | None, tasks: list, model: str
) -> list:
    if mutation is None:
        args = [module_path.replace(".", "/") + ".py"]
    else:
        defect_type, target_tool = mutation
        args = ["scripts/_mutated_stdio_server.py", module_path, defect_type, target_tool]

    provider = AuthenticatedOllamaProvider(model)
    client, ctx = await connect_stdio(sys.executable, args)
    try:
        return await run_tasks(tasks, client, provider, trials=1)
    finally:
        await cleanup_connection(ctx)


def _score(run_results, constraints_by_key) -> list[TrialOutcome]:
    outcomes = []
    for r in run_results:
        key = (r.task.tool_name, r.task.description)
        constraints = constraints_by_key.get(key)
        score = (
            constraint_satisfaction(r.constructed_args, constraints)
            if r.success and r.selected_tool == r.task.tool_name
            else 0.0
        )
        outcomes.append(TrialOutcome(r.task.tool_name, r.selected_tool, score))
    return outcomes


def _load_state() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {model: {"blocking_instances": []} for model in MODELS}


def _save_state(state: dict) -> None:
    OUT_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def _measure_instance(inst: dict, model: str) -> dict:
    ts_name = inst["tool_set"]
    module_path = inst["module_path"]
    all_tasks = BLIND_TASKS[ts_name]
    constraints_by_key = TASK_CONSTRAINTS[ts_name]
    target_tasks = [t for t in all_tasks if t.tool_name == inst["target_tool"]]
    if not target_tasks:
        return {**inst, "error": "no tasks for target tool", "task_deltas": []}

    before_results = await _run_variant(module_path, None, target_tasks, model)
    after_results = await _run_variant(
        module_path, (inst["defect_type"], inst["target_tool"]), target_tasks, model
    )
    before_outcomes = _score(before_results, constraints_by_key)
    after_outcomes = _score(after_results, constraints_by_key)

    task_deltas = []
    for b, a in zip(before_outcomes, after_outcomes, strict=False):
        task_deltas.append(
            {
                "before_joint_success": b.joint_success,
                "after_joint_success": a.joint_success,
                "delta": a.joint_success - b.joint_success,
            }
        )
    return {**inst, "task_deltas": task_deltas}


def _pooled(instances: list[dict]) -> dict | None:
    all_deltas = [d["delta"] for inst in instances for d in inst["task_deltas"]]
    if len(all_deltas) < 2:
        return None
    point, ci_lo, ci_hi = t_adjusted_cluster_bootstrap_mean_ci(all_deltas, seed=42)
    n_tool_sets = len({inst["tool_set"] for inst in instances})
    return {
        "mean_delta": point,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_tool_sets": n_tool_sets,
        "m_tasks": len(all_deltas),
    }


async def main() -> None:
    state = _load_state()
    for model in MODELS:
        state.setdefault(model, {"blocking_instances": []})
        print(f"\n########## model={model} ##########", flush=True)
        instances = _select_instances(BLOCKING_DEFECT_TYPES)
        done_keys = {
            (r["tool_set"], r["defect_type"], r["target_tool"])
            for r in state[model]["blocking_instances"]
        }
        for inst in instances:
            key = (inst["tool_set"], inst["defect_type"], inst["target_tool"])
            if key in done_keys:
                print(f"  [skip, checkpointed] {key}", flush=True)
                continue
            print(f"  Measuring {key}...", flush=True)
            result = await _measure_instance(inst, model)
            state[model]["blocking_instances"].append(result)
            _save_state(state)
            print(f"    {json.dumps(result['task_deltas'])}", flush=True)

    print("\n=== Pooled BLOCKING effect sizes per model ===", flush=True)
    for model in MODELS:
        pooled = _pooled(state[model]["blocking_instances"])
        if pooled is None:
            print(f"{model}: insufficient data", flush=True)
            continue
        state[model]["blocking_pooled"] = pooled
        print(
            f"{model:15s}: mean delta={pooled['mean_delta']:+.4f} "
            f"(95% CI [{pooled['ci_lo']:+.4f}, {pooled['ci_hi']:+.4f}]), "
            f"N={pooled['n_tool_sets']} tool sets, M={pooled['m_tasks']} tasks",
            flush=True,
        )

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
