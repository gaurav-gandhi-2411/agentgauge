"""One-time recorder for the bundled `agentgauge demo` replay files.

Runs the repo's own live collection path (`agentgauge.cli._collect_trials`: `run_tasks` ->
OllamaProvider -> constraint scoring) over the bundled before/after demo servers with
`--trials 1 --seed 42`, and writes the trial outcomes in the exact JSON shape
`agentgauge diff --replay-before/--replay-after` loads. Not run in CI (needs a local Ollama).

    python scripts/record_demo_replays.py [--model gemma2:9b] [--max-calls 120]

Sequential, bounded: 2 prompts per (task, trial) per arm -> 4 * n_tasks model calls. Aborts before
sending anything if that would exceed --max-calls. No tuning, no seed search: one pass, one seed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from agentgauge.cli import _collect_trials, _load_tasks_file
from agentgauge.providers import OllamaProvider

DEMO_DIR = Path(__file__).resolve().parent.parent / "agentgauge" / "demo"
SEED = 42  # repo-wide convention; per-trial seeds are derived from it by runner.trial_seed


async def _record(model: str, max_calls: int, out_dir: Path) -> None:
    tasks = _load_tasks_file(DEMO_DIR / "tasks.json")
    planned_calls = 4 * len(tasks)  # 2 arms x 2 prompts (select + args) x 1 trial
    if planned_calls > max_calls:
        sys.exit(f"refusing: {planned_calls} planned model calls > --max-calls {max_calls}")
    await OllamaProvider(model).ensure_reachable()
    for arm in ("before", "after"):
        outcomes, stats = await _collect_trials(
            str(DEMO_DIR / f"{arm}_server.py"),
            tasks,
            model=model,
            trials=1,
            mock=False,
            seed=SEED,
        )
        payload = [
            {
                "task_tool_name": o.task_tool_name,
                "selected_tool": o.selected_tool,
                "constraint_satisfaction": o.constraint_satisfaction,
            }
            for o in outcomes
        ]
        path = out_dir / f"replay_{arm}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"{arm}: {len(payload)} trials, {stats.duration_s:.1f}s -> {path}")  # noqa: T201


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma2:9b")
    ap.add_argument("--max-calls", type=int, default=120)
    ap.add_argument("--out-dir", type=Path, default=DEMO_DIR)
    args = ap.parse_args()
    asyncio.run(_record(args.model, args.max_calls, args.out_dir))


if __name__ == "__main__":
    main()
