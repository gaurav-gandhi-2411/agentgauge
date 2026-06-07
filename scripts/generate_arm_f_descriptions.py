#!/usr/bin/env python3
"""Phase 1 — generate Arm F descriptions for T18 60-tool catalog.

Runs the fixer's _generate_description for each tool (qwen3:8b generator).
Persists output to evals/fixtures/t18_arm_f_descriptions.json.

Usage:
    python scripts/generate_arm_f_descriptions.py [--model qwen3:8b] [--out PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp.types as types

from agentgauge.fixer import _generate_description
from agentgauge.providers import OllamaProvider
from evals.fixtures.t18_catalog import FAMILIES

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


async def generate(model: str, out_path: Path) -> None:
    generator = OllamaProvider(model)
    all_tool_names = [name for names in FAMILIES.values() for name in names]
    print(f"Generating descriptions for {len(all_tool_names)} tools using {model}...")
    descriptions: dict[str, str] = {}
    for i, name in enumerate(all_tool_names):
        tool = types.Tool(name=name, description="", inputSchema=_SCHEMA)
        desc = await _generate_description(tool, generator)
        descriptions[name] = desc
        print(f"  [{i + 1:02d}/{len(all_tool_names)}] {name}: {desc[:80]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(descriptions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(descriptions)} descriptions to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Arm F descriptions (Phase 1)")
    parser.add_argument(
        "--model", default="qwen3:8b", help="Generator model (must be qwen3 family)"
    )
    parser.add_argument(
        "--out",
        default=str(
            Path(__file__).parent.parent / "evals" / "fixtures" / "t18_arm_f_descriptions.json"
        ),
    )
    args = parser.parse_args()
    asyncio.run(generate(args.model, Path(args.out)))


if __name__ == "__main__":
    main()
