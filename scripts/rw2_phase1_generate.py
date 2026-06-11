#!/usr/bin/env python3
"""RW2 Phase 1 — generate Guard-B descriptions from AWS IAM mirror docstrings (qwen3:8b).

Uses the Q5 Guard-B path: scoped extraction of each _handle_<tool>() body from
rw2_aws_iam_mirror.py, neighbor surfaces (def + docstring only), and the Guard-B
prompt that forbids comparative neighbor claims.

Persists to: evals/fixtures/rw2_arm_guardb_descriptions.json

GPU EXCLUSIVITY REQUIREMENT:
  - Silence qwen3:30b reactive requester before running.
  - Check ollama ps shows only qwen3 family before and after.
  - Abort if any foreign model loads during generation.

Usage:
    python scripts/rw2_phase1_generate.py [--model qwen3:8b]

After completion:
    ollama stop
    ollama ps  (must be empty)
    python scripts/rw2_phase2_ab.py
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
from evals.fixtures.rw2_aws_iam_catalog import (
    ARM_O_DESCRIPTIONS,
    AWS_IAM_DOCSTRINGS,
    DESTRUCTIVE_TOOLS,
    FAMILIES,
    TOOL_SCHEMAS,
    get_mirror_source,
)

_OUT_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "rw2_arm_guardb_descriptions.json"
)


def _check_foreign_models(expected_family: str) -> list[str]:
    """Check for non-expected model families loaded in Ollama."""
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
    """Build the neighbor surfaces text for a tool using scoped extraction."""
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
    """Run Phase 1: generate Guard-B descriptions for all 29 AWS IAM tools."""
    generator_family = model.split(":")[0].lower()

    foreign_pre = _check_foreign_models(generator_family)
    if foreign_pre:
        print(f"ABORT: Foreign models loaded before generation: {foreign_pre}")
        print("Unload them first (ollama stop), then re-run.")
        sys.exit(1)
    print(f"[PRE-CHECK] GPU watchdog: clean (generator family: {generator_family})")

    generator = OllamaProvider(model, timeout=600.0)

    # Build Tool objects from catalog (AWS_IAM_DOCSTRINGS as current descriptions)
    all_tools = [
        types.Tool(name=name, description=AWS_IAM_DOCSTRINGS[name], inputSchema=TOOL_SCHEMAS[name])
        for names in FAMILIES.values()
        for name in names
    ]

    mirror_source = get_mirror_source()

    print(f"\nGenerating Guard-B descriptions for {len(all_tools)} AWS IAM tools")
    print(f"  model={model}  guard_b=True  source=rw2_aws_iam_mirror.py")
    print(f"  Output → {_OUT_PATH.name}\n")

    guardb_descriptions: dict[str, str] = {}
    for i, tool in enumerate(all_tools):
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

        is_destructive = tool.name in DESTRUCTIVE_TOOLS
        oracle_desc = ARM_O_DESCRIPTIONS.get(tool.name, "")
        flag = " [DESTRUCTIVE]" if is_destructive else ""
        print(f"  [{i + 1:02d}/{len(all_tools)}] {tool.name}{flag}")
        print(f"    Arm A (AWS IAM): {AWS_IAM_DOCSTRINGS[tool.name][:80]}")
        print(f"    Guard-B:        {desc[:120]}")
        if is_destructive:
            # Verify IRREVERSIBLE / permanently / destroyed signals survived the guard
            oracle_signals = [
                w
                for w in ["IRREVERSIBLE", "permanently", "destroyed", "irrecoverably"]
                if w in oracle_desc
            ]
            gen_signals = [
                w
                for w in [
                    "IRREVERSIBLE",
                    "permanently",
                    "destroyed",
                    "irrecoverably",
                    "irreversible",
                    "permanent",
                ]
                if w.lower() in desc.lower()
            ]
            print(f"    Safety signals: oracle={oracle_signals}  generated={gen_signals}")
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
    print(f"  Total: {len(guardb_descriptions)} tools")

    # Phase 1 summary: highlight destructive tools for manual safety review
    print("\n[DESTRUCTIVE-TOOL SAFETY PRE-SCREEN]")
    print("Verify each destructive tool's Guard-B description does NOT omit the key risk signal:")
    print("  delete_user_policy  → should retain IRREVERSIBLE / permanently deleted / destroyed")
    print("  delete_role_policy  → should retain IRREVERSIBLE / permanently deleted / destroyed")
    print("  delete_user         → should retain IRREVERSIBLE / permanently removes")
    print("  delete_group        → should retain IRREVERSIBLE / permanently removes")
    print("  delete_access_key   → should retain IRREVERSIBLE / permanently revokes")
    print()
    for tool in sorted(DESTRUCTIVE_TOOLS):
        desc = guardb_descriptions.get(tool, "")
        print(f"  {tool}:")
        print(f"    {desc}")
        print()

    print(
        "Phase 1 complete.\n"
        "Next steps:\n"
        "  1. Manually review destructive-tool descriptions above.\n"
        "  2. ollama stop\n"
        "  3. ollama ps  (must be empty)\n"
        "  4. python scripts/rw2_phase2_ab.py"
    )


def main() -> None:
    """Entry point for RW2 Phase 1 generation."""
    parser = argparse.ArgumentParser(
        description="RW2 Phase 1: generate Guard-B descriptions from AWS IAM mirror docstrings"
    )
    parser.add_argument(
        "--model", default="qwen3:8b", help="Generator model (must be qwen3 family)"
    )
    args = parser.parse_args()
    asyncio.run(generate(args.model))


if __name__ == "__main__":
    main()
