#!/usr/bin/env python3
"""Ad-hoc script: run agentgauge.fixer.run_fixer live against a predictive-validity
"before" fixture and persist the patched source as a new "_fixed" example server.

Not part of CI, not committed (per predictive-validity study convention -- see
evals/fixtures/predictive_validity/manifest.py header). Makes real Ollama calls:
generator=qwen3:8b, judge=llama3.1:8b (the repo's pinned convention -- see
scripts/run_ab_experiment.py). Requires local Ollama with both models pulled, and
enough free VRAM/compute for both models to respond within OllamaProvider's 180s
per-call timeout -- see agentgauge/CLAUDE.md "Real-model spot checks" note.

Usage:
    python scripts/build_fixed_fixtures.py <fixture_name> [<fixture_name> ...]

where <fixture_name> is one of:
    grounded_server, confusable_server, mediocre_server,
    call_constraints_server, call_constraints_v2_server

Writes examples/<fixture_name>_fixed.py ONLY if run_fixer accepts at least one
change (report.accepted non-empty). Prints accept/reject/skip/abstain counts and
per-candidate detail for each fixture so the caller can decide whether to add a
manifest entry -- never fabricates a fake "after" state when nothing was accepted.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.client import cleanup_connection, connect_stdio
from agentgauge.fixer import run_fixer
from agentgauge.providers import OllamaProvider

REPO_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"

# Pinned convention for this repo's fixer runs (see agentgauge/CLAUDE.md,
# scripts/run_ab_experiment.py): qwen3 family generates, llama3.1 family judges.
GENERATOR_MODEL = "qwen3:8b"
JUDGE_MODEL = "llama3.1:8b"

_FIXTURES: dict[str, str] = {
    "grounded_server": "grounded_server.py",
    "confusable_server": "confusable_server.py",
    "mediocre_server": "mediocre_server.py",
    "call_constraints_server": "call_constraints_server.py",
    "call_constraints_v2_server": "call_constraints_v2_server.py",
}


async def build_one(name: str) -> bool:
    """Run the fixer against one fixture and, if accepted changes exist, persist it.

    Returns True if an `<name>_fixed.py` file was written, False otherwise.
    """
    if name not in _FIXTURES:
        raise SystemExit(f"Unknown fixture {name!r}. Choose from {sorted(_FIXTURES)}.")
    src_path = EXAMPLES_DIR / _FIXTURES[name]
    out_path = EXAMPLES_DIR / f"{name}_fixed.py"

    python = sys.executable
    print(f"\n{'=' * 72}\nFixture: {name}  ({src_path.name})\n{'=' * 72}")
    print(f"Connecting to {src_path.name} ...")
    client, ctx = await connect_stdio(python, [str(src_path)])
    try:
        info = await client.introspect()
        tool_names = [t.name for t in info.tools]
        print(f"Tools ({len(tool_names)}): {tool_names}")

        generator = OllamaProvider(GENERATOR_MODEL)
        judge = OllamaProvider(JUDGE_MODEL)

        print(f"Running fixer (generator={GENERATOR_MODEL}, judge={JUDGE_MODEL}) ...")
        report = await run_fixer(
            info.tools,
            generator,
            judge,
            src_path,
            dims=["description_quality", "schema_completeness"],
        )

        print(f"\nAccepted: {len(report.accepted)}")
        for c in report.accepted:
            print(
                f"  + {c.tool_name}:{c.dim} baseline={c.baseline_score:.1f} "
                f"candidate={c.candidate_score:.1f} delta={c.delta:+.1f}"
            )
        print(f"Rejected: {len(report.rejected)}")
        for c in report.rejected:
            print(f"  - {c.tool_name}:{c.dim} {c.rejection_reason}")
        print(f"Skipped: {len(report.skipped)}")
        for s in report.skipped:
            print(f"  ? {s}")
        print(f"Abstained: {len(report.abstained)}")
        for a in report.abstained:
            print(f"  ~ {a}")

        if report.accepted and report.patched_source:
            out_path.write_text(report.patched_source, encoding="utf-8")
            print(f"\nWrote patched source to {out_path}")
            return True
        print("\nNo accepted changes -- NOT writing an _fixed.py file (avoid fabricated 'after').")
        return False
    finally:
        await cleanup_connection(ctx)


async def main_async(names: list[str]) -> None:
    results: dict[str, bool] = {}
    for name in names:
        results[name] = await build_one(name)
    print(f"\n{'=' * 72}\nSummary\n{'=' * 72}")
    for name, wrote in results.items():
        print(f"  {name}: {'WROTE _fixed.py' if wrote else 'no changes accepted -- skipped'}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(f"Usage: python {sys.argv[0]} <fixture_name> [<fixture_name> ...]")
    asyncio.run(main_async(sys.argv[1:]))


if __name__ == "__main__":
    main()
