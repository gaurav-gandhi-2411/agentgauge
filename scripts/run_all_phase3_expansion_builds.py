#!/usr/bin/env python3
"""Driver: runs build_fixed_fixtures_v2's build_one for every fixture needed to
expand Phase 3 to >=20 pairs, sequentially, against the remote agentgauge-agent
proxy. See PLAN in chat transcript for the source list and rationale.

8 new sources at default dims (description_quality + schema_completeness):
  rw1_github_mirror, p2a_internal_proxy_mirror, q3_real_server, q6_real_server,
  echo_server, exp1_datalayer_jupyter_mcp_server_mirror,
  exp1_stickerdaniel_linkedin_mcp_server_mirror, exp1_dataojitori_nocturne_memory_mirror

3 dims-ablation variants (description_quality ONLY -- never touches schema) on
the 3 cheapest of the above, to test whether restricting the fixer's target
dimension avoids introducing schema-consistency violations:
  echo_server, q3_real_server, exp1_dataojitori_nocturne_memory_mirror

Ordered cheapest-tool-count-first so a killed/interrupted run banks as much as
possible before hitting the most expensive entries.

Usage:
    uv run python scripts/run_all_phase3_expansion_builds.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from agentgauge.providers import OllamaProvider

OllamaProvider.BASE_URL = "http://localhost:11435"

from build_fixed_fixtures_v2 import build_one  # noqa: E402

# (entry_name, out_suffix, dims) -- ordered cheapest tool-count first.
JOBS: list[tuple[str, str, list[str]]] = [
    ("echo_server", "fixed", ["description_quality", "schema_completeness"]),
    ("echo_server", "fixed_dqonly", ["description_quality"]),
    ("exp1_dataojitori_nocturne_memory_mirror", "fixed", ["description_quality", "schema_completeness"]),
    ("exp1_dataojitori_nocturne_memory_mirror", "fixed_dqonly", ["description_quality"]),
    ("q3_real_server", "fixed", ["description_quality", "schema_completeness"]),
    ("q3_real_server", "fixed_dqonly", ["description_quality"]),
    ("exp1_stickerdaniel_linkedin_mcp_server_mirror", "fixed", ["description_quality", "schema_completeness"]),
    ("exp1_datalayer_jupyter_mcp_server_mirror", "fixed", ["description_quality", "schema_completeness"]),
    ("rw1_github_mirror", "fixed", ["description_quality", "schema_completeness"]),
    ("q6_real_server", "fixed", ["description_quality", "schema_completeness"]),
    ("p2a_internal_proxy_mirror", "fixed", ["description_quality", "schema_completeness"]),
]


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


async def main() -> None:
    results = {}
    for i, (name, suffix, dims) in enumerate(JOBS, start=1):
        key = f"{name}_{suffix}"
        out_path = EXAMPLES_DIR / f"{name}_{suffix}.py"
        if out_path.exists():
            print(f"\n[{i}/{len(JOBS)}] {key} ... SKIPPING (already written, resume)", flush=True)
            results[key] = "SKIPPED (already written)"
            continue
        print(f"\n[{i}/{len(JOBS)}] {key} ...", flush=True)
        try:
            wrote = await build_one(name, suffix, dims)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc!r}")
            results[key] = f"FAILED: {exc!r}"
            continue
        results[key] = "WROTE" if wrote else "NO CHANGES ACCEPTED"
        print(f"  -> {results[key]}")

    print(f"\n{'=' * 72}\nSummary\n{'=' * 72}")
    for k, v in results.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
