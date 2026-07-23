#!/usr/bin/env python3
"""Extract (name, description, inputSchema) for every tool in every manifest
entry, via live MCP introspection -- zero LLM inference, just process spawn +
protocol handshake. Cached to disk so the clean/defect-injection corpus
builders (Task 2c/2d) and the linter evaluation don't need to re-spawn 45
subprocesses every time they're re-run.

Usage:
    uv run python scripts/v2_extract_tool_definitions.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.client import cleanup_connection, connect_stdio
from evals.fixtures.predictive_validity.manifest import MANIFEST, resolve_server_path

OUT_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "v2_tool_definitions.json"


async def extract_one(entry_name: str) -> dict:
    """Extracts the FULL tool catalog, ignoring `tool_name_filter`.

    The predictive-validity study filtered several manifest entries (the T18
    family in particular) down to a 12-tool subset purely to bound ground-truth
    COLLECTION cost -- that filter was never meant to represent the "real" tool
    set a linter would see in production. Linting the filtered subset produces
    a measurement artifact: sibling tool names from the un-filtered families
    (e.g. "write_entry" mentioned in a filtered-out tool's description) look
    like unknown identifiers when they are actually real, legitimate tool names
    in the same live server. Found during v2 clean-corpus measurement on
    t18_q2b_server; fixed by linting the full catalog, not the study's
    cost-bounded subset.
    """
    entry = next(e for e in MANIFEST if e.name == entry_name)
    server_path = resolve_server_path(entry)
    client, ctx = await connect_stdio(sys.executable, [str(server_path)])
    try:
        info = await client.introspect()
        tools = info.tools
        return {
            "name": entry_name,
            "tier": entry.tier,
            "tools": [
                {"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema or {}}
                for t in tools
            ],
        }
    finally:
        await cleanup_connection(ctx)


async def main() -> None:
    names = [e.name for e in MANIFEST]
    print(f"Extracting tool definitions from {len(names)} manifest entries...")
    results = []
    for i, name in enumerate(names, start=1):
        r = await extract_one(name)
        results.append(r)
        print(f"[{i}/{len(names)}] {name:45s} tier={r['tier']:22s} tools={len(r['tools'])}")
    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWritten: {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
