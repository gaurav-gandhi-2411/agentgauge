"""One-time recorder for the bundled `agentgauge demo` replay files.

Runs the repo's own live collection path (`agentgauge.cli._collect_trials`: `run_tasks` ->
OllamaProvider -> constraint scoring) over the bundled before/after demo servers with
`--trials 1 --seed 42`, and writes the trial outcomes with `agentgauge.replay.save_replay` (v1 file,
with provenance; the files currently bundled predate it and are legacy bare lists). Not run in CI.

    python scripts/record_demo_replays.py [--model gemma2:9b] [--max-calls 120]

Sequential, bounded: 2 prompts per (task, trial) per arm -> 4 * n_tasks model calls. Aborts before
sending anything if that would exceed --max-calls. No tuning, no seed search: one pass, one seed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from agentgauge.cli import _collect_trials, _introspect_tools, _load_tasks_file
from agentgauge.providers import OllamaProvider
from agentgauge.replay import file_sha256, save_replay, tools_sha256

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
        server = str(DEMO_DIR / f"{arm}_server.py")
        path = out_dir / f"replay_{arm}.json"
        save_replay(
            path,
            outcomes,
            model=stats.provider_label,
            seed=SEED,
            trials_per_task=1,
            target=server,
            tools_sha=tools_sha256(await _introspect_tools(server)),
            tasks_sha=file_sha256(DEMO_DIR / "tasks.json"),
        )
        print(f"{arm}: {len(outcomes)} trials, {stats.duration_s:.1f}s -> {path}")  # noqa: T201


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma2:9b")
    ap.add_argument("--max-calls", type=int, default=120)
    ap.add_argument("--out-dir", type=Path, default=DEMO_DIR)
    args = ap.parse_args()
    asyncio.run(_record(args.model, args.max_calls, args.out_dir))


if __name__ == "__main__":
    main()
