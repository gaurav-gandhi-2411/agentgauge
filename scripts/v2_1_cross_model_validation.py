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
families, or is it model-specific? Live inference required -- calls the `agentgauge-agent`
Cloud Run service DIRECTLY over HTTPS with an IAM identity-token bearer header, not via
`gcloud run services proxy` -- the local proxy tunnel is documented (memory: "Local gcloud
proxy unreliable") and was reconfirmed in this session to die silently (still-running
process, but stops forwarding traffic) well before a 16-task run completes. Direct HTTPS
has no such intermediary to fail.

trials=1, 2 tasks/tool (16 of 32 tasks, one from each tool's two "hard"/constrained
task variants where available) to keep this bounded and reduce the wall-clock window
a Cloud Run cold-start/scale-down could interrupt mid-run -- Task 1 already showed
repeat trials on the same deterministic task carry almost no independent information
(ICC=0.793), so a single trial per task is not a meaningfully weaker design than the
historical 3-trials-per-task collection for this specific question (does the SIGN/
existence of the pattern replicate, not a precise effect-size estimate).

Checkpointed: writes evals/fixtures/v2_1_cross_model_validation.json after EVERY
(model, variant) combo, not just at the end -- a mid-run interruption (this exact
infrastructure had one) loses at most one combo's progress, not the whole run. Skips
combos already present in an existing output file, so a re-run resumes rather than
re-paying for already-collected combos.
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
# Generated in the launching shell (gcloud auth print-identity-token) and passed via
# env var -- the detached-process environment this script often runs under does not
# reliably have `gcloud` on PATH, and re-shelling out to gcloud per script invocation
# is unnecessary when the launcher already has a live gcloud session.
_IDENTITY_TOKEN = os.environ["AGENTGAUGE_AGENT_IDENTITY_TOKEN"]


class AuthenticatedOllamaProvider(OllamaProvider):
    """OllamaProvider variant that calls the Cloud Run service directly over
    HTTPS with an IAM identity-token bearer header, bypassing `gcloud run
    services proxy` entirely -- that local proxy is a documented unreliable
    intermediary on this machine (dies silently mid-run without exiting)."""

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


MODELS = ["gemma2:9b", "llama3.1:8b", "qwen2.5:7b"]
VARIANTS = {
    "before": "examples/call_constraints_server.py",
    "after": "examples/call_constraints_server_fixed.py",
}
OUT_PATH = Path("evals/fixtures/v2_1_cross_model_validation.json")


def _select_task_subset() -> list:
    """First 2 tasks per tool (16 of 32) -- deterministic, not random, so this
    is reproducible without a seed. Keeps at least one task per tool (covers
    selection accuracy across all 8 tools) and 2 tasks for each of the 4
    constrained tools (covers the argument-construction-degradation question
    on the tools where it can actually manifest -- the other 4 tools have no
    constrained params and always score 1.0 by construction)."""
    by_tool: dict[str, list] = {}
    for t in CALL_CONSTRAINTS_SERVER_TASKS:
        by_tool.setdefault(t.tool_name, []).append(t)
    subset = []
    for tasks in by_tool.values():
        subset.extend(tasks[:2])
    return subset


TASK_SUBSET = _select_task_subset()


async def _run_one(server_path: str, model: str) -> list[TrialOutcome]:
    provider = AuthenticatedOllamaProvider(model)
    client, ctx = await connect_stdio(sys.executable, [server_path])
    try:
        constraints_by_key = TASK_CONSTRAINTS["call_constraints_server"]
        run_results = await run_tasks(list(TASK_SUBSET), client, provider, trials=1)
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


async def _ensure_models_pulled() -> None:
    """Pull all MODELS via direct HTTP (Bearer token), in the SAME process
    run as the trials below -- ephemeral disk means models do not persist
    across a cold start, and this Cloud Run service has been observed to
    scale back to zero in the gap between a separate pull step and a later
    run step. Doing both in one uninterrupted script run removes that gap."""
    headers = {"Authorization": f"Bearer {_IDENTITY_TOKEN}"}
    # Generous connect timeout: a cold GPU container start (driver + Ollama +
    # model load) can take minutes, and Cloud Run queues the request rather
    # than rejecting it while the instance comes up.
    timeout = httpx.Timeout(connect=300.0, read=120.0, write=30.0, pool=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{CLOUD_RUN_URL}/api/tags", headers=headers)
        resp.raise_for_status()
        already_present = {m["name"] for m in resp.json().get("models", [])}
        for model in MODELS:
            if model in already_present:
                print(f"Already pulled: {model}", flush=True)
                continue
            print(f"Pulling {model}...", flush=True)
            last_pct = -1
            async with client.stream(
                "POST",
                f"{CLOUD_RUN_URL}/api/pull",
                json={"model": model, "stream": True},
                headers=headers,
            ) as stream:
                stream.raise_for_status()
                async for line in stream.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    status = data.get("status", "")
                    total, done = data.get("total"), data.get("completed")
                    if total and done:
                        pct = int(100 * done / total)
                        if pct != last_pct and pct % 10 == 0:
                            print(f"  {model}: {status} {pct}%", flush=True)
                            last_pct = pct
                    else:
                        print(f"  {model}: {status}", flush=True)


async def main() -> None:
    await _ensure_models_pulled()
    results = _load_checkpoint()
    for model in MODELS:
        results.setdefault(model, {})
        for variant_name, server_path in VARIANTS.items():
            if variant_name in results[model]:
                print(f"Skipping model={model} variant={variant_name} (already checkpointed)")
                continue
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
            OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

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
    import traceback

    try:
        asyncio.run(main())
    except BaseException:
        print("FATAL:", flush=True)
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        raise
