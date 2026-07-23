#!/usr/bin/env python3
"""Run the deterministic schema-consistency checks ((a),(b),(c),(e)) across every
tool in every manifest entry, plus a per-entry aggregate violation count keyed
by manifest name (for cross-referencing against results_raw.json's
task_success_rate in later analysis).

No LLM calls -- pure structural/lexical checks against live-introspected tools.
Still spawns MCP stdio subprocesses (one per manifest entry), so this is not a
zero-cost-in-time operation, but it is zero-cost in tokens/GPU.

Usage:
    uv run python scripts/run_schema_consistency.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from agentgauge.client import cleanup_connection, connect_stdio
from evals.fixtures.predictive_validity.manifest import MANIFEST, resolve_server_path
from schema_consistency_checker import check_deterministic

OUT_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "predictive_validity" / "schema_consistency_results.json"


async def _check_entry(entry_name: str) -> dict:
    entry = next(e for e in MANIFEST if e.name == entry_name)
    server_path = resolve_server_path(entry)
    client, ctx = await connect_stdio(sys.executable, [str(server_path)])
    try:
        info = await client.introspect()
        tools = info.tools
        if entry.tool_name_filter is not None:
            keep = set(entry.tool_name_filter)
            tools = [t for t in tools if t.name in keep]

        per_tool = []
        total_violations = 0
        total_required_missing_prop = 0
        total_required_not_mentioned = 0
        total_desc_not_in_schema = 0
        total_type_enum = 0
        for t in tools:
            r = check_deterministic(t.name, t.description or "", t.inputSchema or {})
            per_tool.append(
                {
                    "tool_name": t.name,
                    "n_violations": r.n_violations,
                    "described_not_in_schema": r.described_not_in_schema,
                    "required_not_mentioned": r.required_not_mentioned,
                    "type_enum_contradictions": r.type_enum_contradictions,
                    "required_references_missing_property": r.required_references_missing_property,
                }
            )
            total_violations += r.n_violations
            total_required_missing_prop += len(r.required_references_missing_property)
            total_required_not_mentioned += len(r.required_not_mentioned)
            total_desc_not_in_schema += len(r.described_not_in_schema)
            total_type_enum += len(r.type_enum_contradictions)

        return {
            "name": entry_name,
            "n_tools": len(tools),
            "total_violations": total_violations,
            "total_required_missing_prop": total_required_missing_prop,
            "total_required_not_mentioned": total_required_not_mentioned,
            "total_desc_not_in_schema": total_desc_not_in_schema,
            "total_type_enum": total_type_enum,
            "violations_per_tool": total_violations / len(tools) if tools else 0.0,
            "per_tool": per_tool,
        }
    finally:
        await cleanup_connection(ctx)


async def main() -> None:
    names = [e.name for e in MANIFEST]
    print(f"Checking {len(names)} manifest entries (deterministic checks only, no LLM calls)...")
    results = []
    for i, name in enumerate(names, start=1):
        r = await _check_entry(name)
        results.append(r)
        print(
            f"[{i}/{len(names)}] {name:45s} tools={r['n_tools']:3d} "
            f"violations={r['total_violations']:3d} (per-tool={r['violations_per_tool']:.2f})"
        )
    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWritten: {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
