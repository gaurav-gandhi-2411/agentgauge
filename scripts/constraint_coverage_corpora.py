"""Task 8: run `check_constraint_coverage` over every committed task corpus.

Corpora (no model is called; servers are only introspected for their tool schemas):
  - bundled_demo            agentgauge/demo/tasks.json (24 tasks) against the demo tool schemas
                              (included only when agentgauge/demo exists)
  - argument_degradation_253  the 12 fixtures of scripts/v2_5_argument_degradation_live.py
                              (62 call_constraints* + 191 v2.4/v2.5 corpus tasks = 253)
  - predictive_validity     evals/fixtures/predictive_validity BLIND_TASKS over the 44 tool sets
                              (overlaps the call_constraints tasks of the 253 corpus)

Writes evals/fixtures/constraint_coverage_corpora.json (deterministic) and, with --check,
verifies the committed file equals a fresh run.

Run: python scripts/constraint_coverage_corpora.py [--check]
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agentgauge.audit import (  # noqa: E402
    FULL,
    CoverageSummary,
    summarize_constraint_coverage,
)
from agentgauge.client import cleanup_connection, connect_stdio  # noqa: E402
from agentgauge.constraints import BlindTask, Constraint  # noqa: E402

OUT = ROOT / "evals/fixtures/constraint_coverage_corpora.json"


def _load_module(name: str, path: Path) -> Any:  # noqa: ANN401
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _introspect(server_rel: str) -> list[Any]:
    client, ctx = await connect_stdio(sys.executable, [str(ROOT / server_rel)])
    try:
        return list((await client.introspect()).tools)
    finally:
        await cleanup_connection(ctx)


def _summ(summary: CoverageSummary) -> dict[str, Any]:
    reasons: Counter[str] = Counter()
    for t in summary.tasks:
        for r in t.unconstrained:
            reasons[
                "required param unconstrained"
                if r.startswith("required")
                else "stated value unchecked"
            ] += 1
    d = summary.as_dict()
    d["share_full"] = round(summary.count(FULL) / summary.n, 4) if summary.n else None
    d["partial_reasons"] = dict(sorted(reasons.items()))
    return d


def _merge(parts: list[CoverageSummary]) -> CoverageSummary:
    return CoverageSummary([t for p in parts for t in p.tasks])


def demo_corpus() -> tuple[CoverageSummary, dict[str, Any]]:
    from agentgauge.demo import before_server

    tasks = [
        BlindTask.from_dict(d)
        for d in json.loads((ROOT / "agentgauge/demo/tasks.json").read_text(encoding="utf-8"))
    ]
    tools = [
        SimpleNamespace(name=t["name"], inputSchema=t["inputSchema"]) for t in before_server.TOOLS
    ]
    s = summarize_constraint_coverage(tasks, tools)
    return s, {}


def arg_degradation_corpus() -> tuple[CoverageSummary, dict[str, Any]]:
    mod = _load_module("v2_5_adl", ROOT / "scripts/v2_5_argument_degradation_live.py")
    parts: list[CoverageSummary] = []
    by_fixture: dict[str, Any] = {}
    for name, _bad, fixed, tasks_module, attr in mod.FIXTURES:
        tasks = mod._load_fixture_tasks(tasks_module, attr)
        tools = asyncio.run(_introspect(fixed))
        s = summarize_constraint_coverage(tasks, tools)
        parts.append(s)
        by_fixture[name] = _summ(s)
    return _merge(parts), by_fixture


def predictive_validity_corpus() -> tuple[CoverageSummary, dict[str, Any]]:
    from evals.fixtures.predictive_validity.blind_tasks import BLIND_TASKS
    from evals.fixtures.predictive_validity.constraints import TASK_CONSTRAINTS
    from evals.fixtures.predictive_validity.manifest import MANIFEST

    parts: list[CoverageSummary] = []
    by_set: dict[str, Any] = {}
    cache: dict[str, list[Any]] = {}
    for entry in MANIFEST:
        if entry.server_path not in cache:
            cache[entry.server_path] = asyncio.run(_introspect(entry.server_path))
        keep = set(entry.tool_name_filter) if entry.tool_name_filter is not None else None
        tools = [t for t in cache[entry.server_path] if keep is None or t.name in keep]
        tasks = []
        for t in BLIND_TASKS[entry.name]:
            raw = TASK_CONSTRAINTS.get(entry.name, {}).get((t.tool_name, t.description)) or []
            cons = [
                c
                if isinstance(c, Constraint)
                else Constraint(**{k: getattr(c, k, None) for k in Constraint.__dataclass_fields__})
                for c in raw
            ]
            tasks.append(BlindTask(t.tool_name, t.description, cons))
        s = summarize_constraint_coverage(tasks, tools)
        parts.append(s)
        by_set[entry.name] = _summ(s)
    return _merge(parts), by_set


def build() -> dict[str, Any]:
    out: dict[str, Any] = {
        "note": (
            "Task classes (agentgauge.audit): selection-only = no argument constraint; "
            "partial = some constraint but a required parameter or a value stated in the task "
            "text is unchecked; full = every required parameter constrained and every stated "
            "value covered. The 'stated value' detection is a heuristic (quoted strings and "
            "tokens containing a digit). The predictive_validity corpus overlaps the "
            "call_constraints fixtures of argument_degradation_253."
        ),
        "corpora": {},
    }
    corpora = [
        ("argument_degradation_253", arg_degradation_corpus),
        ("predictive_validity_44_tool_sets", predictive_validity_corpus),
    ]
    if (ROOT / "agentgauge/demo/tasks.json").exists():  # the demo lands in a later PR
        corpora.insert(0, ("bundled_demo", demo_corpus))
    for key, fn in corpora:
        summary, detail = fn()
        entry = _summ(summary)
        if detail:
            entry["by_group"] = detail
        out["corpora"][key] = entry
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(build(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("constraint_coverage_corpora.json is stale")
            return 1
        print("up to date")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    for k, v in json.loads(text)["corpora"].items():
        print(k, {x: v[x] for x in ("n_tasks", "selection_only", "partial", "full", "share_full")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
