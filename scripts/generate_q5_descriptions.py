#!/usr/bin/env python3
"""Q5 Phase 1 — generate F-DOC-guarded descriptions using Guard B.

For each tool in the Q3 catalog, uses the scoped extractor + neighbor surfaces (WITH docstrings)
to call _generate_description with guard_b=True. Guard B forbids comparative neighbor claims
("unlike X, which does Y") and requires only target-grounded positive facts.

This is one condition (not two): DOC-scoped + Guard B. The DOC-scoped WITHOUT Guard B (reference
arm) was already generated in Q4 Phase 1.

Persists results to:
  evals/fixtures/q5_arm_f_doc_guarded_descriptions.json

Prerequisites:
  - Silence qwen3:30b reactive requester first.
  - Watch ollama ps; abort if qwen3:30b loads.
  - Run this FIRST; then run scripts/run_q5_four_arm.py after ollama stop.

Usage:
    python scripts/generate_q5_descriptions.py [--model qwen3:8b]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp.types as types

from agentgauge.fixer import (
    _NEIGHBOR_K,
    _extract_function_surface,
    _extract_scoped_function,
    _generate_description,
    _select_neighbors,
)
from agentgauge.providers import OllamaProvider
from evals.fixtures.q3_catalog import (
    ARM_O_DESCRIPTIONS,
    CONTROL_TOOLS,
    FAMILIES,
    INDEPENDENCE_TOKENS,
    get_doc_source,
)

_OUT_GUARDED = (
    Path(__file__).parent.parent
    / "evals"
    / "fixtures"
    / "q5_arm_f_doc_guarded_descriptions.json"
)

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

_AMBIGUOUS_TOOLS: set[str] = set(CONTROL_TOOLS)


def _check_foreign_models(expected_family: str) -> list[str]:
    try:
        result = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().splitlines()
        foreign = []
        for line in lines[1:]:
            parts = line.split()
            if parts and expected_family.lower() not in parts[0].lower():
                foreign.append(parts[0])
        return foreign
    except Exception:
        return []


def _build_neighbor_surfaces_text(
    tool_name: str,
    source: str,
    all_tools: list[types.Tool],
) -> str:
    """Select K neighbors and assemble their surfaces (sig + docstring, body stripped)."""
    target = next(t for t in all_tools if t.name == tool_name)
    neighbors = _select_neighbors(target, all_tools, k=_NEIGHBOR_K)
    surfaces: list[str] = []
    for nbr in neighbors:
        surface = _extract_function_surface(source, nbr.name)
        if surface:
            surfaces.append(f"Neighbor: {nbr.name}\n{surface}")
        else:
            surfaces.append(f"Neighbor: {nbr.name}  (no source found)")
    return "\n\n".join(surfaces)


async def generate(model: str) -> None:
    generator_family = model.split(":")[0].lower()

    foreign_pre = _check_foreign_models(generator_family)
    if foreign_pre:
        print(f"ABORT: Foreign models loaded before generation: {foreign_pre}")
        print("Unload them first (ollama stop, kill PIDs), then re-run.")
        sys.exit(1)
    print(f"[PRE-CHECK] GPU watchdog: clean (generator family: {generator_family})")

    generator = OllamaProvider(model, timeout=600.0)
    all_tools = [
        types.Tool(name=name, description="", inputSchema=_SCHEMA)
        for names in FAMILIES.values()
        for name in names
    ]

    doc_source = get_doc_source()

    print(
        f"\nGenerating Q5-DOC-guarded descriptions "
        f"({len(all_tools)} tools, model={model}, guard_b=True)..."
    )
    guarded_descriptions: dict[str, str] = {}
    for i, tool in enumerate(all_tools):
        scoped_src = _extract_scoped_function(doc_source, tool.name)
        ns_text = _build_neighbor_surfaces_text(tool.name, doc_source, all_tools)
        desc = await _generate_description(
            tool,
            generator,
            scoped_source=scoped_src,
            neighbor_surfaces_text=ns_text,
            guard_b=True,
        )
        guarded_descriptions[tool.name] = desc
        is_control = tool.name in _AMBIGUOUS_TOOLS
        token = INDEPENDENCE_TOKENS.get(tool.name, "(control — no token)")
        print(f"  [{i + 1:02d}/{len(all_tools)}] {tool.name} {'[CONTROL]' if is_control else ''}")
        print(f"    token={token!r}  guard_b=True  =>  {desc[:120]}")

    foreign_post = _check_foreign_models(generator_family)
    if foreign_post:
        print(f"\nWARN: Foreign models appeared during DOC-guarded generation: {foreign_post}")

    _OUT_GUARDED.parent.mkdir(parents=True, exist_ok=True)
    _OUT_GUARDED.write_text(
        json.dumps(guarded_descriptions, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSaved Q5-DOC-guarded: {_OUT_GUARDED}")

    # Phase 1 summary: flag control tools for manual no-fabrication review
    print("\n[NO-FABRICATION PRE-SCREEN] Control tools (manual review required in Phase 2):")
    for name in sorted(_AMBIGUOUS_TOOLS):
        oracle_desc = ARM_O_DESCRIPTIONS.get(name, "")
        guarded_desc = guarded_descriptions.get(name, "")
        print(f"  {name}")
        print(f"    Oracle:          {oracle_desc}")
        print(f"    DOC-guarded:     {guarded_desc}")

    print(
        "\nPhase 1 complete. Next: ollama stop && ollama ps (must be empty) "
        "then run scripts/run_q5_four_arm.py"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Q5 Phase 1: generate DOC-guarded (Guard B) descriptions"
    )
    parser.add_argument(
        "--model", default="qwen3:8b", help="Generator model (must be qwen3 family)"
    )
    args = parser.parse_args()
    asyncio.run(generate(args.model))


if __name__ == "__main__":
    main()
