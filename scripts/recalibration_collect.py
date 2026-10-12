#!/usr/bin/env python3
"""Re-collect the predictive-validity ground-truth trials with per-trial varied seeds.

Why this exists: the original corpus (evals/fixtures/predictive_validity/results_raw.json)
was collected before ``run_tasks`` derived a distinct seed per (task, trial). Every repeat
trial therefore used seed 42 against Ollama's default sampler and returned the same
completion, so 650 of 720 (tool_set, task) groups had exactly zero variance. This driver
re-runs ONLY the gemma2:9b ground-truth loop -- no judge, no score_all -- with
``run_tasks(..., base_seed=42)`` and writes one NDJSON row per trial to a NEW path
(never the committed corpus).

Local Ollama only (http://localhost:11434). No network, no paid APIs.

Order: the 5 Phase-3 before/after pairs first (needed for the paired-correlation rho), then
the remaining tool sets by ascending catalog size (cheapest first), so a wall-clock cap
(--max-hours) always leaves the largest fully-measured subset.

Resume: one checkpoint per (tool_set, task); rerunning skips tasks already in --out.

Usage:
    .venv/Scripts/python.exe scripts/recalibration_collect.py --out <dir> [--max-hours 7.5]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.client import cleanup_connection, connect_stdio
from agentgauge.providers import OllamaProvider
from agentgauge.runner import run_tasks, trial_seed
from evals.fixtures.predictive_validity.blind_tasks import BLIND_TASKS
from evals.fixtures.predictive_validity.constraints import TASK_CONSTRAINTS, constraint_satisfaction
from evals.fixtures.predictive_validity.manifest import (
    AGENT_MODEL,
    MANIFEST,
    ToolSetEntry,
    resolve_server_path,
)

OLD_CORPUS = Path(__file__).parent.parent / "evals/fixtures/predictive_validity/results_raw.json"
GROUND_TRUTH_TRIALS = 5  # same as the original corpus (predictive_validity_study.py)
BASE_SEED = 42
PROVIDER_TIMEOUT = 300.0  # same as the original study; slow-but-live calls must not hard-fail

# Same 5 pairs as scripts/v2_variance_structure.py PHASE3_PAIRS (duplicated, not imported:
# that module has import-time side effects and cwd-relative paths).
PHASE3_PAIRS = [
    ("grounded_server", "grounded_server_fixed"),
    ("confusable_server", "confusable_server_fixed"),
    ("mediocre_server", "mediocre_server_fixed"),
    ("call_constraints_server", "call_constraints_server_fixed"),
    ("call_constraints_v2_server", "call_constraints_v2_server_fixed"),
]


def _ordered_entries() -> list[ToolSetEntry]:
    """Phase-3 pairs first, then ascending catalog size. Only entries the old corpus
    measured successfully (so old and new cover the same tool sets)."""
    old = json.loads(OLD_CORPUS.read_text(encoding="utf-8"))
    ok = {r["name"]: r.get("tool_count", 0) for r in old if r.get("error") is None}
    by_name = {e.name: e for e in MANIFEST if e.name in ok}
    first = [by_name[n] for pair in PHASE3_PAIRS for n in pair if n in by_name]
    seen = {e.name for e in first}
    rest = sorted((e for e in by_name.values() if e.name not in seen), key=lambda e: ok[e.name])
    return first + rest


def _done_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            keys.add((row["tool_set"], row["task_description"]))
    return keys


async def _run_entry(entry: ToolSetEntry, out: Path, deadline: float, done: set) -> bool:
    """Run every task of one tool set. Returns False if the wall-clock cap was hit."""
    client, ctx = await connect_stdio(sys.executable, [str(resolve_server_path(entry))])
    try:
        info = await client.introspect()
        keep = set(entry.tool_name_filter) if entry.tool_name_filter is not None else None

        class _Filtered:
            async def introspect(self):  # noqa: ANN202 -- duck-typed MCPClient subset
                from agentgauge.client import ServerInfo

                return ServerInfo(
                    tools=[t for t in info.tools if keep is None or t.name in keep],
                    resources=info.resources,
                    prompts=info.prompts,
                )

            async def call_tool(self, name, arguments):  # noqa: ANN001, ANN202
                return await client.call_tool(name, arguments)

        provider = OllamaProvider(AGENT_MODEL, timeout=PROVIDER_TIMEOUT)
        for task in BLIND_TASKS[entry.name]:
            if (entry.name, task.description) in done:
                continue
            if time.time() > deadline:
                return False
            t0 = time.perf_counter()
            results = await run_tasks(
                [task],
                _Filtered(),  # type: ignore[arg-type]
                provider,
                trials=GROUND_TRUTH_TRIALS,
                base_seed=BASE_SEED,
            )
            elapsed = time.perf_counter() - t0
            rows = []
            for i, r in enumerate(results):
                if r.selected_tool != r.task.tool_name:
                    score = 0.0
                else:
                    constraints = TASK_CONSTRAINTS.get(entry.name, {}).get(
                        (r.task.tool_name, r.task.description)
                    )
                    score = constraint_satisfaction(r.constructed_args, constraints)
                rows.append(
                    {
                        "tool_set": entry.name,
                        "tier": entry.tier,
                        "task_tool_name": r.task.tool_name,
                        "task_description": r.task.description,
                        "trial_index": i,
                        "seed": trial_seed(BASE_SEED, r.task, i),
                        "selected_tool": r.selected_tool,
                        "constructed_args": r.constructed_args,
                        "success": r.success,
                        "error": r.error,
                        "parse_failed": r.parse_failed,
                        "constraint_satisfaction": score,
                        "task_block_seconds": round(elapsed, 2),
                        "ts": datetime.now(UTC).isoformat(),
                    }
                )
            with out.open("a", encoding="utf-8") as f:  # one flush per task = the checkpoint
                for row in rows:
                    f.write(json.dumps(row, sort_keys=True) + "\n")
            print(
                f"{entry.name} | {task.tool_name} | {len(rows)} trials | {elapsed:.1f}s "
                f"({elapsed / max(len(rows), 1):.1f}s/trial)",
                flush=True,
            )
        return True
    finally:
        await cleanup_connection(ctx)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True, help="output dir (created)")
    ap.add_argument("--max-hours", type=float, default=7.5)
    ap.add_argument("--only", nargs="*", help="restrict to these tool_set names (smoke test)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "rows.ndjson"
    deadline = time.time() + args.max_hours * 3600
    done = _done_keys(out)
    completed: list[str] = []
    skipped: list[str] = []
    cap_hit = False
    for entry in _ordered_entries():
        if args.only and entry.name not in args.only:
            continue
        if cap_hit:
            skipped.append(entry.name)
            continue
        ok = await _run_entry(entry, out, deadline, done)
        (completed if ok else skipped).append(entry.name)
        cap_hit = not ok
    (args.out / "run_status.json").write_text(
        json.dumps(
            {
                "finished_utc": datetime.now(UTC).isoformat(),
                "max_hours": args.max_hours,
                "completed_tool_sets": completed,
                "not_run_or_partial_tool_sets": skipped,
                "cap_hit": cap_hit,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
