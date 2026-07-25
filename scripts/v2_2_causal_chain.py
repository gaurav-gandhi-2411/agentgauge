"""Task 3 (v2.2): end-to-end causal chain -- does a BLOCKING violation
actually cause agent task failure? Live inference, checkpointed.

Prior sessions measured: the linter catches injected defects (recall), and
the harness detects success-rate deltas (MDE). Neither measured that a
BLOCKING violation CAUSES a measurable drop in real agent task success --
this script does, directly, using the exact injector functions already used
(and measured) for the linter's own recall evaluation
(scripts/v2_defect_injector.py's INJECTORS), now run against LIVE, runnable
mutated servers (scripts/_mutated_stdio_server.py) instead of static dicts.

Design: for each of several real, clean (0 BLOCKING violations) tool sets
with existing hand-authored anti-tautology tasks and constraint definitions
(evals/fixtures/predictive_validity/blind_tasks.py + constraints.py), inject
one BLOCKING-class defect (contradictory_required_claim or type_flipped or
enum_dropped) into one eligible tool, then run the live agent against BOTH
the clean and the defect-injected variant on that tool's own tasks
(trials_per_task=1, per Task 1's ICC-informed finding). Pool the resulting
per-task deltas across all (tool_set, defect_type) instances -- each task is
one cluster in the pooled t(G-1)-adjusted CI, mirroring
agentgauge.harness.diff_server_level's own estimator.

Task 3d repeats the same design for ONE ADVISORY-class defect
(param_renamed, which maps to the ADVISORY check described_not_in_schema) --
the only ADVISORY check with a ready-made injector; name_collision and
param_possibly_renamed are not schema/description mutations in the existing
injector framework and are out of scope for this specific measurement
(disclosed, not silently assumed covered).

Routes through the `agentgauge-agent` Cloud Run service (direct HTTPS + IAM
bearer token, same pattern as v2.1's cross-model validation -- the local
proxy is a documented-unreliable intermediary).
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
AGENT_MODEL = "gemma2:9b"
OUT_PATH = Path("evals/fixtures/v2_2_causal_chain.json")

# 6 diverse, clean, well-covered tool sets (all "oracle"/best-description
# variants of different families -- not all near-duplicates of each other).
TOOL_SETS = [
    "confusable_server_oracle",
    "call_constraints_server_oracle",
    "call_constraints_v2_server_oracle",
    "t18_oracle_server",
    "rw1_arm_oracle",
    "p2a_arm_oracle",
]
BLOCKING_DEFECT_TYPES = ["contradictory_required_claim", "type_flipped", "enum_dropped"]
ADVISORY_DEFECT_TYPES = ["param_renamed"]  # the only ADVISORY check with a ready-made injector
MAX_TARGETS_PER_TOOLSET_PER_DEFECT = 1  # keep the live-inference workload bounded


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
    """Pick up to MAX_TARGETS_PER_TOOLSET_PER_DEFECT eligible (tool_set,
    defect_type, target_tool) instances per (tool_set, defect_type) pair,
    restricted to TOOL_SETS, using the same eligibility functions the
    linter's own defect-injection evaluation already uses."""
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


async def _run_variant(module_path: str, mutation: tuple[str, str] | None, tasks: list) -> list:
    """mutation=None -> run the CLEAN server unmodified. mutation=(defect_type,
    target_tool) -> run scripts/_mutated_stdio_server.py with that injection.
    Returns raw RunResult objects; the caller scores them against the
    tool set's own constraint definitions (`_score`)."""
    if mutation is None:
        args = [module_path.replace(".", "/") + ".py"]
    else:
        defect_type, target_tool = mutation
        args = ["scripts/_mutated_stdio_server.py", module_path, defect_type, target_tool]

    provider = AuthenticatedOllamaProvider(AGENT_MODEL)
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
    return {"blocking_instances": [], "advisory_instances": []}


def _save_state(state: dict) -> None:
    OUT_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def _measure_instance(inst: dict) -> dict:
    ts_name = inst["tool_set"]
    module_path = inst["module_path"]
    all_tasks = BLIND_TASKS[ts_name]
    constraints_by_key = TASK_CONSTRAINTS[ts_name]
    target_tasks = [t for t in all_tasks if t.tool_name == inst["target_tool"]]
    if not target_tasks:
        return {**inst, "error": "no tasks for target tool", "task_deltas": []}

    before_results = await _run_variant(module_path, None, target_tasks)
    after_results = await _run_variant(
        module_path, (inst["defect_type"], inst["target_tool"]), target_tasks
    )
    before_outcomes = _score(before_results, constraints_by_key)
    after_outcomes = _score(after_results, constraints_by_key)

    task_deltas = []
    for b, a in zip(before_outcomes, after_outcomes, strict=False):
        task_deltas.append(
            {
                "task_description": None,  # not needed downstream; kept minimal
                "before_joint_success": b.joint_success,
                "after_joint_success": a.joint_success,
                "delta": a.joint_success - b.joint_success,
            }
        )
    return {**inst, "task_deltas": task_deltas}


async def main() -> None:
    state = _load_state()

    print("=== 3a/3b. BLOCKING-class defect instances ===")
    blocking_instances = _select_instances(BLOCKING_DEFECT_TYPES)
    print(
        f"Selected {len(blocking_instances)} instances: {[(i['tool_set'], i['defect_type'], i['target_tool']) for i in blocking_instances]}"
    )
    done_keys = {
        (r["tool_set"], r["defect_type"], r["target_tool"]) for r in state["blocking_instances"]
    }
    for inst in blocking_instances:
        key = (inst["tool_set"], inst["defect_type"], inst["target_tool"])
        if key in done_keys:
            print(f"  [skip, checkpointed] {key}")
            continue
        print(f"  Measuring {key}...")
        result = await _measure_instance(inst)
        state["blocking_instances"].append(result)
        _save_state(state)
        print(f"    {json.dumps(result['task_deltas'])}")

    print("\n=== 3d. ADVISORY-class defect instances (param_renamed) ===")
    advisory_instances = _select_instances(ADVISORY_DEFECT_TYPES)
    print(f"Selected {len(advisory_instances)} instances")
    done_keys_adv = {
        (r["tool_set"], r["defect_type"], r["target_tool"]) for r in state["advisory_instances"]
    }
    for inst in advisory_instances:
        key = (inst["tool_set"], inst["defect_type"], inst["target_tool"])
        if key in done_keys_adv:
            print(f"  [skip, checkpointed] {key}")
            continue
        print(f"  Measuring {key}...")
        result = await _measure_instance(inst)
        state["advisory_instances"].append(result)
        _save_state(state)
        print(f"    {json.dumps(result['task_deltas'])}")

    print("\n=== Pooled effect sizes ===")
    for label, instances in [
        ("BLOCKING", state["blocking_instances"]),
        ("ADVISORY", state["advisory_instances"]),
    ]:
        all_deltas = [d["delta"] for inst in instances for d in inst["task_deltas"]]
        if len(all_deltas) < 2:
            print(f"{label}: insufficient data ({len(all_deltas)} tasks)")
            continue
        point, ci_lo, ci_hi = t_adjusted_cluster_bootstrap_mean_ci(all_deltas, seed=42)
        n_tool_sets = len({inst["tool_set"] for inst in instances})
        print(
            f"{label}: mean delta={point:+.4f} (95% CI [{ci_lo:+.4f}, {ci_hi:+.4f}]), "
            f"N={n_tool_sets} tool sets, M={len(all_deltas)} tasks"
        )
        state[f"{label.lower()}_pooled"] = {
            "mean_delta": point,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "n_tool_sets": n_tool_sets,
            "m_tasks": len(all_deltas),
        }

    _save_state(state)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    import traceback

    try:
        asyncio.run(main())
    except BaseException:
        print("FATAL:", flush=True)
        traceback.print_exc()
        raise
