#!/usr/bin/env python3
"""RW1 Part 1 — score-validity check: does the scanner flag what GitHub hand-fixed?

Runs the discoverability scorer on the GitHub MCP mirror catalog (21 tools, real
GitHub docstrings) using the live Ollama judge (llama3.1:8b). Identifies families
the scorer flags as confusable and cross-checks them against GITHUB_HAND_FIXED_FAMILIES
— the ground truth of families GitHub's own engineers consolidated to reduce confusion.

If the scorer flags the same families GitHub hand-fixed, that is external evidence
the score predicts real problems. If not, that is a score-validity gap to report.

Output: per-family heuristic sub-score, judge DISTINGUISH scores, blend, collision
pairs, and an explicit overlap verdict against GITHUB_HAND_FIXED_FAMILIES.

Usage:
    python scripts/rw1_part1_discoverability.py [--judge llama3.1:8b] [--trials 3]

Prerequisites:
    - Ollama running with llama3.1:8b pulled
    - VRAM >= 5 GB free (check ollama ps first; use GCP proxy if contended)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows (cp1252 default can't encode box/arrow chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.types import Tool

from agentgauge.providers import OllamaProvider
from agentgauge.scorer import _heuristic_subscore, _judge_discoverability, score_discoverability
from evals.fixtures.rw1_github_catalog import (
    FAMILIES,
    FAMILY_MAP,
    GITHUB_DOCSTRINGS,
    GITHUB_HAND_FIXED_FAMILIES,
    TOOL_SCHEMAS,
)


def _build_tools(descriptions: dict[str, str]) -> list[Tool]:
    return [
        Tool(name=name, description=descriptions[name], inputSchema=TOOL_SCHEMAS[name])
        for name in descriptions
    ]


async def run(judge_model: str, trials: int) -> None:
    print("=" * 80)
    print("RW1 Part 1 — Score Validity: discoverability scorer vs GitHub hand-fixed families")
    print(f"Judge: {judge_model}  |  Trials: {trials}  |  Tools: 21  |  Families: 5")
    print("=" * 80)

    tools = _build_tools(GITHUB_DOCSTRINGS)

    # ── Heuristic sub-score (deterministic) ───────────────────────────────────
    heuristic_score, h_hints, collision_pairs, per_tool_pts = _heuristic_subscore(tools)

    print("\n[HEURISTIC] Name-based sub-score (deterministic, no LLM)")
    print(f"  Overall heuristic score: {heuristic_score:.1f}/100")
    print(f"  Collision pairs detected (sim >= 0.80): {len(collision_pairs)}")
    for a, b in collision_pairs:
        fam_a = FAMILY_MAP.get(a, "?")
        fam_b = FAMILY_MAP.get(b, "?")
        print(f"    [{fam_a}] {a!r} <-> {b!r}  [{fam_b}]")
    if not collision_pairs:
        print("    (none — all names have edit-distance similarity < 0.80)")

    print("\n  Per-tool heuristic points (0-3 each: non-generic-name + len>3 + has-description):")
    for family, names in FAMILIES.items():
        pts_list = [f"{n}={per_tool_pts[n]}" for n in names]
        print(f"    [{family}]: {', '.join(pts_list)}")

    print("\n  Heuristic fix hints:")
    for hint in h_hints[:10]:
        print(f"    - {hint}")

    # ── Judge sub-score (LLM) ─────────────────────────────────────────────────
    provider = OllamaProvider(judge_model)

    print(f"\n[JUDGE] DISTINGUISH sub-score ({trials} trials, {judge_model})")
    print("  Sending full 21-tool catalog to judge...")

    judge_score, judge_variance, j_hints = await _judge_discoverability(
        tools, provider, trials=trials
    )

    print(f"  DISTINGUISH score (judge): {judge_score:.1f}/100  σ²={judge_variance:.2f}")
    for hint in j_hints:
        print(f"  Hint: {hint}")

    # ── Blended score ─────────────────────────────────────────────────────────
    blend_weight = 0.60
    blended = blend_weight * heuristic_score + (1.0 - blend_weight) * judge_score

    print(f"\n[BLEND] 60% heuristic + 40% judge = {blended:.1f}/100")

    # ── Per-family analysis ───────────────────────────────────────────────────
    print("\n[PER-FAMILY ANALYSIS]")
    print("  Collision pairs per family (from heuristic):")
    family_collision_count: dict[str, int] = {f: 0 for f in FAMILIES}
    for a, b in collision_pairs:
        fa, fb = FAMILY_MAP.get(a, "?"), FAMILY_MAP.get(b, "?")
        if fa == fb:
            family_collision_count[fa] = family_collision_count.get(fa, 0) + 1
        else:
            print(f"    Cross-family pair: {a!r} ({fa}) <-> {b!r} ({fb})")

    for family, count in family_collision_count.items():
        tools_in_fam = FAMILIES[family]
        print(f"    {family}: {count} collision pair(s) among {len(tools_in_fam)} tools")

    # ── Score-validity cross-check against GitHub ground truth ────────────────
    print("\n" + "=" * 80)
    print("SCORE VALIDITY CROSS-CHECK")
    print("=" * 80)
    print(
        "Ground truth: families GitHub's own engineers consolidated or restructured\n"
        "  to reduce confusion (GITHUB_HAND_FIXED_FAMILIES).\n"
        "  If the scorer flags the same families, score validity is CONFIRMED.\n"
        "  If not, that is a score-validity gap.\n"
    )

    print("GitHub hand-fixed families:")
    for key, note in GITHUB_HAND_FIXED_FAMILIES.items():
        print(f"  [{key}]  {note[:120]}")

    print()
    print("Heuristic-flagged collision families (sim >= 0.80 pair within family):")
    heuristic_flagged = {fam for fam, cnt in family_collision_count.items() if cnt > 0}
    if heuristic_flagged:
        for fam in sorted(heuristic_flagged):
            print(f"  {fam}")
    else:
        print("  (none — heuristic did not flag any within-family collisions)")

    print()
    print("Judge-flagged families (DISTINGUISH < 6/10 → full catalog scored):")
    print(
        f"  Judge gave the FULL 21-tool catalog a DISTINGUISH score of {judge_score:.1f}/100.\n"
        "  For per-family judge analysis, run with per-family sub-catalogs (see below)."
    )

    # Per-family judge analysis (optional detail)
    print("\n[PER-FAMILY JUDGE SUBSCORES] Running judge on each family subset...")
    family_scores: dict[str, float] = {}
    for family, names in FAMILIES.items():
        fam_tools = [t for t in tools if t.name in names]
        fam_judge, fam_var, _ = await _judge_discoverability(
            fam_tools, provider, trials=max(1, trials - 1)
        )
        family_scores[family] = fam_judge
        flagged = fam_judge < 60.0
        print(
            f"  {family}: DISTINGUISH={fam_judge:.1f}/100  σ²={fam_var:.2f}  "
            f"{'<-- FLAGGED (< 60)' if flagged else ''}"
        )

    scorer_flagged_families = {fam for fam, sc in family_scores.items() if sc < 60.0}

    # ── Final verdict ─────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)

    gh_family_keys = set(GITHUB_HAND_FIXED_FAMILIES.keys())
    # Map GitHub hand-fixed keys to our family keys where applicable
    gh_mapped: dict[str, str] = {
        "projects": None,  # Projects family not in our 21-tool subset
        "pr_read_variants": "pr_read_family",
        "search_variants": "search_family",
    }

    print("\n  Overlap between scorer-flagged and GitHub-hand-fixed:")
    overlap_count = 0
    for gh_key, our_key in gh_mapped.items():
        if our_key is None:
            print(f"  [{gh_key}]: NOT in our 21-tool subset (projects were consolidated; "
                  f"testing the pre-consolidation surface requires a separate fixture)")
            continue
        score_flags = our_key in scorer_flagged_families
        print(
            f"  [{gh_key}] → [{our_key}]: "
            f"scorer={'FLAGGED' if score_flags else 'not flagged'}  "
            f"| judge={family_scores.get(our_key, 0):.1f}/100"
        )
        if score_flags:
            overlap_count += 1

    tested_families = sum(1 for v in gh_mapped.values() if v is not None)
    print(f"\n  Score-validity overlap: {overlap_count}/{tested_families} GitHub-hand-fixed "
          f"families also flagged by our scorer.")

    if overlap_count == tested_families:
        print(
            "\n  VERDICT: SCORE VALIDITY CONFIRMED — scorer flags the same families "
            "GitHub's own engineers consolidated to reduce confusion."
        )
    elif overlap_count > 0:
        print(
            f"\n  VERDICT: PARTIAL SCORE VALIDITY — {overlap_count}/{tested_families} "
            "families matched. Report which were missed and why."
        )
    else:
        print(
            "\n  VERDICT: SCORE-VALIDITY GAP — scorer did NOT flag the families GitHub "
            "hand-fixed. This is a critical finding: the score may not predict real "
            "confusability on naming patterns like the get_pull_request_* family."
        )

    print("\n  Note: Judge score and overlap are model-dependent. Record judge model with results.")
    print(
        "  Families not flagged by judge but by heuristic (or vice versa) are worth "
        "examining — the blend may obscure gaps in either sub-score."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="RW1 Part 1: discoverability score validity")
    parser.add_argument("--judge", default="llama3.1:8b", help="Judge model (llama family)")
    parser.add_argument("--trials", type=int, default=3, help="Judge trials per sub-catalog")
    args = parser.parse_args()
    asyncio.run(run(args.judge, args.trials))


if __name__ == "__main__":
    main()
