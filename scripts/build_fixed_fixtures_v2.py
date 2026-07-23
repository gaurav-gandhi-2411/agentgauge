#!/usr/bin/env python3
"""Generalized version of build_fixed_fixtures.py: runs agentgauge.fixer.run_fixer
against ANY manifest entry (not just the original 5 hardcoded fixtures), and
supports a `dims` override per invocation so a description_quality-only variant
(never touching schema_completeness) can be generated as a deliberate ablation --
does restricting the fixer's target dimension avoid introducing schema
violations, a mechanistic test of the schema-hallucination hypothesis, not
arbitrary volume-padding.

Same conventions as build_fixed_fixtures.py: generator=qwen3:8b, judge=llama3.1:8b
(this repo's pinned family-hygiene rule), points OllamaProvider.BASE_URL at the
remote proxy if the --remote flag is passed.

Usage:
    python scripts/build_fixed_fixtures_v2.py <manifest_entry_name> <out_suffix> [--dims description_quality] [--remote]

Example:
    python scripts/build_fixed_fixtures_v2.py rw1_github_mirror fixed --remote
      -> writes examples/rw1_github_mirror_fixed.py (default dims: description_quality + schema_completeness)
    python scripts/build_fixed_fixtures_v2.py echo_server fixed_dqonly --dims description_quality --remote
      -> writes examples/echo_server_fixed_dqonly.py (description_quality ONLY, never touches schema)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

GENERATOR_MODEL = "qwen3:8b"
JUDGE_MODEL = "llama3.1:8b"

REPO_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"


async def build_one(entry_name: str, out_suffix: str, dims: list[str]) -> bool:
    from agentgauge.client import cleanup_connection, connect_stdio
    from agentgauge.fixer import run_fixer
    from agentgauge.providers import OllamaProvider
    from evals.fixtures.predictive_validity.manifest import MANIFEST, resolve_server_path

    entry = next(e for e in MANIFEST if e.name == entry_name)
    src_path = resolve_server_path(entry)
    out_path = EXAMPLES_DIR / f"{entry_name}_{out_suffix}.py"

    python = sys.executable
    print(f"\n{'=' * 72}\nEntry: {entry_name}  ({src_path.name})  dims={dims}\n{'=' * 72}")
    client, ctx = await connect_stdio(python, [str(src_path)])
    try:
        info = await client.introspect()
        tools = info.tools
        if entry.tool_name_filter is not None:
            keep = set(entry.tool_name_filter)
            tools = [t for t in tools if t.name in keep]
        print(f"Tools ({len(tools)}): {[t.name for t in tools]}")

        generator = OllamaProvider(GENERATOR_MODEL, timeout=300.0)
        judge = OllamaProvider(JUDGE_MODEL, timeout=300.0)

        print(f"Running fixer (generator={GENERATOR_MODEL}, judge={JUDGE_MODEL}, dims={dims}) ...")
        report = await run_fixer(tools, generator, judge, src_path, dims=dims)

        print(f"Accepted: {len(report.accepted)}  Rejected: {len(report.rejected)}  "
              f"Skipped: {len(report.skipped)}  Abstained: {len(report.abstained)}")

        if report.accepted and report.patched_source:
            out_path.write_text(report.patched_source, encoding="utf-8")
            print(f"Wrote patched source to {out_path}")
            return True
        print("No accepted changes -- NOT writing an _fixed file.")
        return False
    finally:
        await cleanup_connection(ctx)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("entry_name")
    parser.add_argument("out_suffix")
    parser.add_argument("--dims", nargs="+", default=["description_quality", "schema_completeness"])
    parser.add_argument("--remote", action="store_true", help="Point OllamaProvider at localhost:11435")
    args = parser.parse_args()

    if args.remote:
        from agentgauge.providers import OllamaProvider
        OllamaProvider.BASE_URL = "http://localhost:11435"

    wrote = asyncio.run(build_one(args.entry_name, args.out_suffix, args.dims))
    print(f"\n{args.entry_name}: {'WROTE' if wrote else 'no changes accepted'}")


if __name__ == "__main__":
    main()
