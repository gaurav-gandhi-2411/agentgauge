#!/usr/bin/env python3
"""Empirically verify the EFFECTIVE decoding temperature of the shipped Ollama code path.

The adapter (``OllamaProvider``) sends only ``options.seed``; the gemma2:9b Modelfile sets no
temperature/top_p/top_k. So the effective sampler is Ollama's runtime default -- a claim that
must be measured, not assumed. This script does three things against local Ollama:

1. Logs the exact JSON body ``OllamaProvider`` posts to /api/chat for one real request.
2. Sampler control on an open-ended prompt: 10 distinct seeds through the shipped provider
   (default options) vs the same 10 seeds with ``temperature=0`` set explicitly. If default
   decoding were greedy-equivalent, both would show one distinct response.
3. Task-level check: 5 tasks from groups that were zero-variance in the recalibration corpus and
   5 from groups that were not, each run 10x with distinct seeds via ``run_tasks``; reports
   distinct raw response strings (exact dedupe), distinct tool calls (name + args) and
   pass/fail per trial.

Local Ollama only (http://localhost:11434). Writes JSON to --out.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.client import ServerInfo, cleanup_connection, connect_stdio
from agentgauge.providers import Message, OllamaProvider
from agentgauge.runner import run_tasks, trial_seed
from evals.fixtures.predictive_validity.blind_tasks import BLIND_TASKS
from evals.fixtures.predictive_validity.constraints import TASK_CONSTRAINTS, constraint_satisfaction
from evals.fixtures.predictive_validity.manifest import (
    AGENT_MODEL,
    MANIFEST,
    resolve_server_path,
)

ROWS = Path(__file__).parent.parent / "evals/fixtures/recalibration_seedfix/rows.ndjson"
# Small catalogs only, so the check is quick; both kinds of group exist in them.
CANDIDATE_SETS = [
    "grounded_server",
    "confusable_server",
    "mediocre_server",
    "call_constraints_server",
]
N_PER_KIND = 5
TRIALS = 10
OPEN_ENDED = [Message(role="user", content="Write one sentence about a lighthouse keeper.")]


class _LoggingProvider:
    """Wraps OllamaProvider; records every request body and raw response."""

    def __init__(self) -> None:
        self._inner = OllamaProvider(AGENT_MODEL, timeout=300.0)
        self.calls: list[dict] = []

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        body = {
            "model": self._inner.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"seed": seed},
        }
        resp = await self._inner.chat(messages, seed=seed)
        self.calls.append({"request_body": body, "response": resp, "seed": seed})
        return resp


async def _raw_chat(messages: list[Message], options: dict) -> str:
    payload = {
        "model": AGENT_MODEL,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "stream": False,
        "options": options,
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(f"{OllamaProvider.BASE_URL}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"]


def _pick_tasks() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for line in ROWS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            groups[(r["tool_set"], r["task_description"])].append(r["constraint_satisfaction"])
    zero, varying = [], []
    for key, vals in sorted(groups.items()):
        if key[0] not in CANDIDATE_SETS:
            continue
        (zero if len(set(vals)) == 1 else varying).append(key)
    rng = random.Random(42)
    return rng.sample(zero, N_PER_KIND), rng.sample(varying, N_PER_KIND)


async def _run_group(kind: str, tool_set: str, description: str) -> dict:
    entry = next(e for e in MANIFEST if e.name == tool_set)
    task = next(t for t in BLIND_TASKS[tool_set] if t.description == description)
    client, ctx = await connect_stdio(sys.executable, [str(resolve_server_path(entry))])
    try:
        info = await client.introspect()
        keep = set(entry.tool_name_filter) if entry.tool_name_filter is not None else None

        class _Filtered:
            async def introspect(self) -> ServerInfo:
                return ServerInfo(
                    tools=[t for t in info.tools if keep is None or t.name in keep],
                    resources=info.resources,
                    prompts=info.prompts,
                )

            async def call_tool(self, name, arguments):  # noqa: ANN001, ANN202
                return await client.call_tool(name, arguments)

        provider = _LoggingProvider()
        results = await run_tasks(
            [task],
            _Filtered(),
            provider,
            trials=TRIALS,
            base_seed=42,  # type: ignore[arg-type]
        )
        raw = [c["response"] for c in provider.calls]
        calls, scores = [], []
        for r in results:
            calls.append(json.dumps([r.selected_tool, r.constructed_args], sort_keys=True))
            if r.selected_tool != r.task.tool_name:
                scores.append(0.0)
            else:
                cons = TASK_CONSTRAINTS.get(tool_set, {}).get(
                    (r.task.tool_name, r.task.description)
                )
                scores.append(constraint_satisfaction(r.constructed_args, cons))
        return {
            "kind": kind,
            "tool_set": tool_set,
            "task": description,
            "seeds": [trial_seed(42, task, i) for i in range(TRIALS)],
            "n_raw_responses": len(raw),
            "distinct_raw_responses": len(set(raw)),
            "distinct_tool_calls": len(set(calls)),
            "per_trial_score": scores,
            "pass_per_trial": [s == 1.0 for s in scores],
            "example_raw_responses": sorted(set(raw))[:4],
            "first_request_body": provider.calls[0]["request_body"],
        }
    finally:
        await cleanup_connection(ctx)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    seeds = list(range(100, 100 + TRIALS))
    provider = _LoggingProvider()
    default_resp = [await provider.chat(OPEN_ENDED, seed=s) for s in seeds]
    greedy_resp = [await _raw_chat(OPEN_ENDED, {"seed": s, "temperature": 0}) for s in seeds]
    repeat_resp = [await provider.chat(OPEN_ENDED, seed=100) for _ in range(3)]
    zero_keys, vary_keys = _pick_tasks()
    groups = []
    for kind, keys in (("zero_variance", zero_keys), ("non_zero_variance", vary_keys)):
        for tool_set, desc in keys:
            groups.append(await _run_group(kind, tool_set, desc))
            print(kind, tool_set, groups[-1]["distinct_raw_responses"], flush=True)
    out = {
        "model": AGENT_MODEL,
        "logged_request_body_open_ended": provider.calls[0]["request_body"],
        "sampler_control": {
            "prompt": OPEN_ENDED[0].content,
            "seeds": seeds,
            "default_options_distinct_responses": len(set(default_resp)),
            "temperature_0_distinct_responses": len(set(greedy_resp)),
            "same_seed_3x_distinct_responses": len(set(repeat_resp)),
            "default_examples": default_resp[:3],
            "temperature_0_example": greedy_resp[0],
        },
        "task_groups": groups,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
