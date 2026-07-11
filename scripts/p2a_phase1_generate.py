#!/usr/bin/env python3
"""P2-A Phase 1 — generate Guard-B descriptions for contested tools (qwen3:8b).

Uses the Guard-B path: scoped extraction of each _handle_<tool>() body from
p2a_internal_proxy_mirror.py, neighbor surfaces (def + docstring only), and the Guard-B
prompt that forbids comparative neighbor claims.

Only CONTESTED_TOOLS receive generated descriptions. THOROUGH_TOOLS are copied verbatim
from ARM_A_DESCRIPTIONS (their thin one-liners are already adequate — they are the
do-no-harm control arm, not the treatment group).

Persists to: evals/fixtures/p2a_arm_guardb_descriptions.json

GPU EXCLUSIVITY REQUIREMENT:
  - Silence qwen3:30b reactive requester before running.
  - Check ollama ps shows only qwen3 family before and after.
  - Abort if any foreign model loads during generation.

Usage:
    python scripts/p2a_phase1_generate.py [--model qwen3:8b]

After completion:
    ollama stop
    ollama ps  (must be empty)
    python scripts/p2a_phase2_ab.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import mcp.types as types

from agentgauge.fixer import (
    _NEIGHBOR_K,
    _extract_function_surface,
    _extract_scoped_function,
    _generate_description,
    _select_neighbors,
)
from agentgauge.providers import OllamaProvider
from evals.fixtures.p2a_internal_proxy_catalog import (
    ARM_A_DESCRIPTIONS,
    CONTESTED_TOOLS,
    FAMILIES,
    TOOL_SCHEMAS,
)

_MIRROR_PATH = Path(__file__).parent.parent / "examples" / "p2a_internal_proxy_mirror.py"

_OUT_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "p2a_arm_guardb_descriptions.json"
)


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
        print("Unload them first (ollama stop), then re-run.")
        sys.exit(1)
    print(f"[PRE-CHECK] GPU watchdog: clean (generator family: {generator_family})")

    generator = OllamaProvider(model, timeout=600.0)

    # Build Tool objects from catalog — use ARM_A_DESCRIPTIONS as the current descriptions.
    # Only contested tools will receive Guard-B rewrites; thorough tools are pass-through.
    all_tools = [
        types.Tool(name=name, description=ARM_A_DESCRIPTIONS[name], inputSchema=TOOL_SCHEMAS[name])
        for names in FAMILIES.values()
        for name in names
    ]

    contested_tools = [t for t in all_tools if t.name in CONTESTED_TOOLS]
    thorough_tools = [t for t in all_tools if t.name not in CONTESTED_TOOLS]

    mirror_source = _MIRROR_PATH.read_text(encoding="utf-8")

    print(f"\nGenerating Guard-B descriptions for {len(contested_tools)} contested tools")
    print(f"  (skipping {len(thorough_tools)} thorough tools — copying ARM_A as-is)")
    print(f"  model={model}  guard_b=True  source=p2a_internal_proxy_mirror.py")
    print(f"  Output → {_OUT_PATH.name}\n")

    guardb_descriptions: dict[str, str] = {}

    # Pass-through thorough tools: copy ARM_A unchanged
    for tool in thorough_tools:
        guardb_descriptions[tool.name] = ARM_A_DESCRIPTIONS[tool.name]

    # Generate Guard-B for contested tools only
    for i, tool in enumerate(contested_tools):
        scoped_src = _extract_scoped_function(mirror_source, tool.name)
        ns_text = _build_neighbor_surfaces_text(tool.name, mirror_source, all_tools)

        desc = await _generate_description(
            tool,
            generator,
            scoped_source=scoped_src,
            neighbor_surfaces_text=ns_text,
            guard_b=True,
        )
        guardb_descriptions[tool.name] = desc

        print(f"  [{i + 1:02d}/{len(contested_tools)}] {tool.name}")
        print(f"    Arm A (thin):  {ARM_A_DESCRIPTIONS[tool.name]}")
        print(f"    Guard-B:       {desc[:120]}")
        print()

    foreign_post = _check_foreign_models(generator_family)
    if foreign_post:
        print(f"\nWARN: Foreign models appeared during generation: {foreign_post}")
        print("Phase 1 results may be contaminated — check GPU logs.")

    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text(
        json.dumps(guardb_descriptions, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Saved Guard-B descriptions: {_OUT_PATH}")
    print(f"  Contested (generated): {len(contested_tools)}")
    print(f"  Thorough  (ARM_A copy): {len(thorough_tools)}")
    print(f"  Total:                 {len(guardb_descriptions)}")

    print(
        "\nPhase 1 complete.\n"
        "Next steps:\n"
        "  1. Review contested-tool descriptions above.\n"
        "  2. ollama stop\n"
        "  3. ollama ps  (must be empty)\n"
        "  4. python scripts/p2a_phase2_ab.py"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P2-A Phase 1: generate Guard-B descriptions for contested tools from mirror"
    )
    parser.add_argument(
        "--model", default="qwen3:8b", help="Generator model (must be qwen3 family)"
    )
    args = parser.parse_args()
    asyncio.run(generate(args.model))


if __name__ == "__main__":
    main()
