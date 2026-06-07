#!/usr/bin/env python3
"""Phase 1 — Q2b catalog-aware Arm F descriptions for T18 60-tool catalog.

Runs catalog-aware _generate_description for each tool (qwen3:8b generator),
showing each tool alongside its K lexically-similar neighbors. Persists output
to evals/fixtures/t18_arm_f_q2b_descriptions.json.

Usage:
    python scripts/generate_arm_f_descriptions_q2b.py [--model qwen3:8b] [--out PATH] [--k 6]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp.types as types

from agentgauge.fixer import _NEIGHBOR_K, _generate_description, _select_neighbors
from agentgauge.providers import OllamaProvider
from evals.fixtures.t18_catalog import FAMILIES

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
_DEFAULT_OUT = Path(__file__).parent.parent / "evals" / "fixtures" / "t18_arm_f_q2b_descriptions.json"


async def generate(model: str, out_path: Path, k: int) -> None:
    generator = OllamaProvider(model)
    all_tool_names = [name for names in FAMILIES.values() for name in names]

    # Build full catalog as Tool objects (no family labels used)
    catalog = [
        types.Tool(name=name, description="", inputSchema=_SCHEMA)
        for name in all_tool_names
    ]

    print(f"Generating Q2b catalog-aware descriptions for {len(all_tool_names)} tools using {model}...")
    print(f"Neighbor K={k}")
    descriptions: dict[str, str] = {}

    for i, tool in enumerate(catalog):
        neighbors = _select_neighbors(tool, catalog, k=k)
        neighbor_names = [n.name for n in neighbors]
        desc = await _generate_description(tool, generator, neighbors=neighbors)
        descriptions[tool.name] = desc
        print(f"  [{i + 1:02d}/{len(catalog)}] {tool.name} (neighbors: {neighbor_names})")
        print(f"    => {desc[:100]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(descriptions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(descriptions)} Q2b descriptions to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Q2b catalog-aware Arm F descriptions (Phase 1)")
    parser.add_argument("--model", default="qwen3:8b", help="Generator model (must be qwen3 family)")
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument("--k", type=int, default=_NEIGHBOR_K, help="Neighbors per tool")
    args = parser.parse_args()
    asyncio.run(generate(args.model, Path(args.out), args.k))


if __name__ == "__main__":
    main()
