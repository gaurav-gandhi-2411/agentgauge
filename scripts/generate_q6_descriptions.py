#!/usr/bin/env python3
"""Q6 Phase 1 — generate Guard-B descriptions for the full extended catalog (23 tools).

For each tool in the Q6 catalog, uses the scoped extractor + neighbor surfaces (WITH
docstrings) to call _generate_description with guard_b=True. Guard B forbids comparative
neighbor claims and requires only target-grounded positive facts.

The extended catalog (23 tools) includes:
  - 12 Q3 tools (6 structural contested + 6 control/non-contested)
  - 5 non-collision already-passing tools
  - 6 collision-prone already-passing tools (3 pairs)

Collision-prone pairs are the harm vector: distinct names but structurally similar
implementations where Guard-B descriptions risk collapsing to the same phrase.

Persists results to:
  evals/fixtures/q6_arm_f_doc_guarded_descriptions.json

Prerequisites:
  - Silence qwen3:30b reactive requester first (check ollama ps).
  - Watch ollama ps; abort if qwen3:30b loads.
  - Run this FIRST; then run scripts/run_q6_regression.py after ollama stop.

Usage:
    python scripts/generate_q6_descriptions.py [--model qwen3:8b]
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
from evals.fixtures.q6_catalog import (
    ALREADY_PASSING_TOOLS,
    ARM_O_DESCRIPTIONS,
    COLLISION_PAIR_DOCS,
    COLLISION_PRONE_PAIRS,
    FAMILIES,
    Q3_FAMILIES,
    get_doc_source,
)

_OUT_GUARDED = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "q6_arm_f_doc_guarded_descriptions.json"
)

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


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
        f"\nGenerating Q6 Guard-B descriptions "
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

        is_ap = tool.name in ALREADY_PASSING_TOOLS
        is_collision = any(tool.name in pair for pair in COLLISION_PRONE_PAIRS)
        label = "[COLLISION]" if is_collision else "[AP]" if is_ap else "[CONTESTED]"
        print(f"  [{i + 1:02d}/{len(all_tools)}] {tool.name} {label}")
        print(f"    guard_b=True  =>  {desc[:120]}")

    foreign_post = _check_foreign_models(generator_family)
    if foreign_post:
        print(f"\nWARN: Foreign models appeared during generation: {foreign_post}")

    _OUT_GUARDED.parent.mkdir(parents=True, exist_ok=True)
    _OUT_GUARDED.write_text(
        json.dumps(guarded_descriptions, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSaved Q6 Guard-B descriptions: {_OUT_GUARDED}")
    print(f"Total tools generated: {len(guarded_descriptions)}")

    # Phase 1 summary: flag collision-prone pairs for manual no-fabrication review
    print("\n[COLLISION-PAIR REVIEW] Guard-B descriptions for collision-prone pairs:")
    print(
        "KEY QUESTION: do the Guard-B descriptions for each pair collapse to identical phrasing?\n"
        "This is the harm vector — if YES, Phase 2 may show regressions on these tools.\n"
    )
    for tool_a, tool_b in COLLISION_PRONE_PAIRS:
        desc_a = guarded_descriptions.get(tool_a, "")
        desc_b = guarded_descriptions.get(tool_b, "")
        oracle_a = ARM_O_DESCRIPTIONS.get(tool_a, "")
        oracle_b = ARM_O_DESCRIPTIONS.get(tool_b, "")
        print(f"  Pair: {tool_a} / {tool_b}")
        print(f"    Oracle  {tool_a}: {oracle_a}")
        print(f"    Guard-B {tool_a}: {desc_a}")
        print(f"    Oracle  {tool_b}: {oracle_b}")
        print(f"    Guard-B {tool_b}: {desc_b}")
        # Heuristic: do descriptions share a common long prefix?
        common_prefix = 0
        for c1, c2 in zip(desc_a.lower(), desc_b.lower()):
            if c1 == c2:
                common_prefix += 1
            else:
                break
        print(f"    Common prefix chars: {common_prefix} (> 30 suggests collision risk)")
        print()

    # Phase 1 summary: collision-pair doc reference
    print("[COLLISION PAIR DOCUMENTATION] (from q6_catalog.py):")
    for doc in COLLISION_PAIR_DOCS:
        print(f"  {doc['pair']}")
        print(f"    Names disambiguate: {doc['names_disambiguate'][:80]}...")
        print(f"    Desc might not:     {doc['descriptions_might_not'][:80]}...")
        print()

    print(
        "\nPhase 1 complete. Next:\n"
        "  ollama stop && ollama ps (must be empty)\n"
        "  then run: python scripts/run_q6_regression.py\n"
        "\nGPU note: agent gemma2:9b only in Phase 2; watchdog kills on any non-gemma model."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Q6 Phase 1: generate Guard-B descriptions for full extended catalog"
    )
    parser.add_argument(
        "--model", default="qwen3:8b", help="Generator model (must be qwen3 family)"
    )
    args = parser.parse_args()
    asyncio.run(generate(args.model))


if __name__ == "__main__":
    main()
