#!/usr/bin/env python3
"""Q3 Phase 1 — generate F-DOC and F-BODY descriptions for each Q3 tool.

Runs _generate_description(tool, generator, source=<source_text>) for each tool
in the Q3 catalog, twice:
  - DOC: source = q3_real_server.py as-is (with docstrings)
  - BODY: source = same file with docstrings stripped

Persists results to:
  evals/fixtures/q3_arm_f_doc_descriptions.json
  evals/fixtures/q3_arm_f_body_descriptions.json

Prerequisites:
  - Silence qwen3:30b reactive requester before running.
  - Watch ollama ps; abort if qwen3:30b loads during generation.
  - Run this FIRST; then run scripts/run_q3_four_arm.py after ollama stop.

Usage:
    python scripts/generate_q3_descriptions.py [--model qwen3:8b]
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

from agentgauge.fixer import _generate_description
from agentgauge.providers import OllamaProvider
from evals.fixtures.q3_catalog import (
    ARM_O_DESCRIPTIONS,
    CONTROL_TOOLS,
    FAMILIES,
    INDEPENDENCE_TOKENS,
    get_body_source,
    get_doc_source,
)

_OUT_DOC = Path(__file__).parent.parent / "evals" / "fixtures" / "q3_arm_f_doc_descriptions.json"
_OUT_BODY = Path(__file__).parent.parent / "evals" / "fixtures" / "q3_arm_f_body_descriptions.json"

_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

# No-fabrication: for control tools, oracle descriptions do NOT distinguish — generator should not invent.
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
    body_source = get_body_source()

    print(f"\nGenerating Q3 F-DOC descriptions ({len(all_tools)} tools, model={model})...")
    doc_descriptions: dict[str, str] = {}
    for i, tool in enumerate(all_tools):
        desc = await _generate_description(tool, generator, source=doc_source)
        doc_descriptions[tool.name] = desc
        is_control = tool.name in _AMBIGUOUS_TOOLS
        token = INDEPENDENCE_TOKENS.get(tool.name, "(control — no token)")
        print(f"  [{i + 1:02d}/{len(all_tools)}] {tool.name} {'[CONTROL]' if is_control else ''}")
        print(f"    token={token!r}  =>  {desc[:120]}")

    foreign_post_doc = _check_foreign_models(generator_family)
    if foreign_post_doc:
        print(f"\nWARN: Foreign models appeared during F-DOC generation: {foreign_post_doc}")
        print("Results may be contaminated. Record this in the PR report.")

    print(f"\nGenerating Q3 F-BODY descriptions ({len(all_tools)} tools, model={model})...")
    body_descriptions: dict[str, str] = {}
    for i, tool in enumerate(all_tools):
        desc = await _generate_description(tool, generator, source=body_source)
        body_descriptions[tool.name] = desc
        is_control = tool.name in _AMBIGUOUS_TOOLS
        token = INDEPENDENCE_TOKENS.get(tool.name, "(control — no token)")
        print(f"  [{i + 1:02d}/{len(all_tools)}] {tool.name} {'[CONTROL]' if is_control else ''}")
        print(f"    token={token!r}  =>  {desc[:120]}")

    foreign_post_body = _check_foreign_models(generator_family)
    if foreign_post_body:
        print(f"\nWARN: Foreign models appeared during F-BODY generation: {foreign_post_body}")

    _OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    _OUT_DOC.write_text(json.dumps(doc_descriptions, indent=2, ensure_ascii=False), encoding="utf-8")
    _OUT_BODY.write_text(json.dumps(body_descriptions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved F-DOC: {_OUT_DOC}")
    print(f"Saved F-BODY: {_OUT_BODY}")

    # Phase 1 summary: flag if F-DOC or F-BODY description for a control tool looks fabricated
    print("\n[NO-FABRICATION PRE-SCREEN] Check generated descriptions for control tools:")
    print("  (Full classification in Section C of the A/B run — manual review required)")
    for name in sorted(_AMBIGUOUS_TOOLS):
        oracle = ARM_O_DESCRIPTIONS.get(name, "")
        doc_desc = doc_descriptions.get(name, "")
        body_desc = body_descriptions.get(name, "")
        print(f"  {name}")
        print(f"    Oracle: {oracle}")
        print(f"    F-DOC:  {doc_desc}")
        print(f"    F-BODY: {body_desc}")

    print(
        "\nPhase 1 complete. Next: ollama stop && ollama ps (must be empty) "
        "then run scripts/run_q3_four_arm.py"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Q3 Phase 1: generate F-DOC and F-BODY descriptions")
    parser.add_argument("--model", default="qwen3:8b", help="Generator model (must be qwen3 family)")
    args = parser.parse_args()
    asyncio.run(generate(args.model))


if __name__ == "__main__":
    main()
