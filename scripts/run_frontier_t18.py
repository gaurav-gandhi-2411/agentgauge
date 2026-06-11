#!/usr/bin/env python3
"""FRONTIER-T18: does the T18 description effect survive a frontier agent?

Pre-registered design (spec.md @ claude/frontier-t18 branch start).
The 85% headroom gate, the abstain/hedge handling, the cost ceiling,
and the verdict rule are all committed before any spend.

Usage (requires FRONTIER_API_KEY env var — separately-billed, NOT the Max-plan key):

    FRONTIER_API_KEY=sk-ant-... python scripts/run_frontier_t18.py \\
        --model claude-haiku-4-5-20251001 \\
        --trials 3 \\
        --cost-ceiling 5.0

Steps:
  STEP 1 (cheap, runs first): Arm A headroom gate.
    - Run Arm A (empty descriptions) on all 40 T18 tasks × 1 trial.
    - If SELECTED-CORRECT >= 85% -> NO-HEADROOM finding, STOP.
  STEP 2 (only if headroom): Full A vs B matrix.
    - Arm A and Arm B (oracle) × --trials per task.
    - 3-outcome breakdown per arm, effect (B-A), task-clustered sign test.
    - Total spend reported; must be under --cost-ceiling.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evals.fixtures.t18_catalog import ARM_A_DESCRIPTIONS, ARM_B_DESCRIPTIONS, FAMILIES, TASKS
from agentgauge.frontier import FrontierOutcome, FrontierRunResult, classify_frontier_outcome
from agentgauge.providers import ApiAgentProvider, CostCeilingError, Message

# Pre-registered cost ceiling (USD). The runner aborts if spend would exceed this.
# GG must confirm a separately-billed key + spend cap before running STEP 2.
_DEFAULT_COST_CEILING_USD = 5.0

# Pre-registered headroom gate: if Arm A SELECTED-CORRECT >= this, NO-HEADROOM.
_HEADROOM_GATE = 0.85

# Pre-registered trial count for the full A/B run.
_DEFAULT_TRIALS = 3

# All T18 tool names (60 tools).
_VALID_TOOLS: frozenset[str] = frozenset(
    tool for tools in FAMILIES.values() for tool in tools
)


# ── Sign test (no scipy) ──────────────────────────────────────────────────────


def _sign_test(deltas: list[float]) -> tuple[int, int, float]:
    """Two-tailed sign test. Returns (n_plus, n_minus, p_value). Ignores ties."""
    n_plus = sum(1 for d in deltas if d > 0)
    n_minus = sum(1 for d in deltas if d < 0)
    n = n_plus + n_minus
    if n == 0:
        return 0, 0, 1.0
    k = min(n_plus, n_minus)
    p_one_tail = sum(math.comb(n, i) * (0.5**n) for i in range(k + 1))
    return n_plus, n_minus, round(min(1.0, 2.0 * p_one_tail), 4)


# ── Tool listing builder ──────────────────────────────────────────────────────


def _build_listing(descriptions: dict[str, str]) -> str:
    """Build the tool listing shown to the agent — same format as runner._build_tool_listing.

    All T18 tools share schema {query: string}, so param type is stable across arms.
    """
    lines = []
    for tool_list in FAMILIES.values():
        for name in tool_list:
            desc = descriptions.get(name, "")
            first_line = desc.split("\n")[0] if desc else "(no description)"
            lines.append(f"{name} — {first_line} | query:string")
    return "\n".join(lines)


# ── Core runner (selection-only, no tool call — saves tokens) ─────────────────


async def _run_arm(
    tasks: list,
    listing: str,
    provider: ApiAgentProvider,
    *,
    trials: int,
    arm_label: str,
) -> list[FrontierRunResult]:
    """Run selection-only trials. Returns one FrontierRunResult per task × trial."""
    results: list[FrontierRunResult] = []
    for task in tasks:
        for trial_idx in range(trials):
            try:
                raw = await provider.chat(
                    [
                        Message(
                            role="user",
                            content=(
                                f"Available tools:\n{listing}\n\n"
                                f"Task: {task.description}\n"
                                "Reply with ONLY the tool name to call, nothing else."
                            ),
                        )
                    ]
                )
            except CostCeilingError:
                print(
                    f"\n[ABORT] Cost ceiling reached during {arm_label} "
                    f"(task '{task.tool_name}' trial {trial_idx + 1}). "
                    f"Spent ${provider.total_cost_usd:.4f}."
                )
                raise
            outcome = classify_frontier_outcome(raw, _VALID_TOOLS, task.tool_name)
            results.append(FrontierRunResult(task=task, raw_response=raw, outcome=outcome))
    return results


# ── Outcome summary helpers ───────────────────────────────────────────────────


def _count_outcomes(
    results: list[FrontierRunResult],
) -> dict[FrontierOutcome, int]:
    counts: dict[FrontierOutcome, int] = {
        "SELECTED-CORRECT": 0,
        "SELECTED-WRONG": 0,
        "ABSTAINED-OR-HEDGED": 0,
    }
    for r in results:
        counts[r.outcome] += 1
    return counts


def _task_correct_rate(results: list[FrontierRunResult], tasks: list, trials: int) -> list[float]:
    """Per-task fraction of SELECTED-CORRECT trials."""
    rates = []
    for i, task in enumerate(tasks):
        task_results = results[i * trials : (i + 1) * trials]
        correct = sum(1 for r in task_results if r.outcome == "SELECTED-CORRECT")
        rates.append(correct / trials if trials > 0 else 0.0)
    return rates


# ── Main experiment ───────────────────────────────────────────────────────────


async def run(model: str, trials: int, cost_ceiling_usd: float) -> None:
    # ── Key check ────────────────────────────────────────────────────────────
    if not os.environ.get("FRONTIER_API_KEY"):
        print("=" * 70)
        print("AWAITING KEY + COST CEILING CONFIRMATION")
        print("=" * 70)
        print()
        print("FRONTIER_API_KEY is not set.")
        print("GG's standing rule: never use ANTHROPIC_API_KEY (Max-plan double-billing).")
        print()
        print("To proceed:")
        print("  1. Obtain a separately-billed Anthropic API key with a hard spend cap.")
        print("  2. Confirm the spend cap explicitly (e.g. '$5 ceiling').")
        print("  3. Re-run with:  FRONTIER_API_KEY=<key> python scripts/run_frontier_t18.py")
        print()
        print("BUILD + CI are complete and require no key. This STOP is for the live run only.")
        sys.exit(0)

    provider = ApiAgentProvider(
        model=model,
        api_key_env="FRONTIER_API_KEY",
        cost_ceiling_usd=cost_ceiling_usd,
    )

    listing_a = _build_listing(ARM_A_DESCRIPTIONS)
    listing_b = _build_listing(ARM_B_DESCRIPTIONS)

    print("=" * 80)
    print("FRONTIER-T18: T18 description effect on a frontier agent")
    print(f"Model: {model}  |  Trials (Step 2): {trials}  |  Cost ceiling: ${cost_ceiling_usd:.2f}")
    print(f"Tasks: {len(TASKS)}  |  Headroom gate: {_HEADROOM_GATE * 100:.0f}%")
    print("=" * 80)

    # ── STEP 1: Arm A headroom gate (1 trial, cheap) ──────────────────────────
    print("\n[STEP 1] Arm A headroom gate — 1 trial × 40 tasks (cheap)")
    print(f"         Running on model: {model}")

    try:
        step1_results = await _run_arm(
            TASKS, listing_a, provider, trials=1, arm_label="STEP-1-ArmA"
        )
    except CostCeilingError:
        print(f"[STEP 1] ABORTED: cost ceiling ${cost_ceiling_usd:.2f} hit during headroom gate.")
        print(f"         Total spent: ${provider.total_cost_usd:.4f}")
        print(f"         Tokens in: {provider.tokens_in}  |  Tokens out: {provider.tokens_out}")
        return

    step1_counts = _count_outcomes(step1_results)
    step1_total = len(step1_results)
    step1_correct_rate = step1_counts["SELECTED-CORRECT"] / step1_total if step1_total else 0.0

    print(f"\n[STEP 1] Results ({step1_total} trials):")
    print(f"  SELECTED-CORRECT     : {step1_counts['SELECTED-CORRECT']:3d} / {step1_total}  ({step1_correct_rate * 100:.1f}%)")
    print(f"  SELECTED-WRONG       : {step1_counts['SELECTED-WRONG']:3d} / {step1_total}")
    print(f"  ABSTAINED-OR-HEDGED  : {step1_counts['ABSTAINED-OR-HEDGED']:3d} / {step1_total}")
    print(f"\n  Spend after STEP 1: ${provider.total_cost_usd:.4f}  "
          f"(in: {provider.tokens_in} tok, out: {provider.tokens_out} tok)")
    print(f"  Headroom gate: {_HEADROOM_GATE * 100:.0f}%")

    if step1_correct_rate >= _HEADROOM_GATE:
        print(f"\n[FINDING] NO-HEADROOM (Arm A = {step1_correct_rate * 100:.1f}% >= {_HEADROOM_GATE * 100:.0f}% gate)")
        print()
        print("  The frontier agent resolves the T18 catalog from tool NAMES ALONE.")
        print("  Discriminating descriptions provide no additional signal on this fixture.")
        print()
        print("  Strategic implication: same as COLLAPSE (market shrinks as agents improve).")
        print("  Reached cheaply — do NOT run the full matrix; do NOT manufacture difficulty.")
        print()
        print("  Update STATUS.md: FRONTIER-T18 → NO-HEADROOM finding.")
        print(f"  Total spend: ${provider.total_cost_usd:.4f}")
        return

    print(f"\n  -> HEADROOM CONFIRMED (Arm A = {step1_correct_rate * 100:.1f}% < {_HEADROOM_GATE * 100:.0f}% gate)")
    print("  Proceeding to STEP 2 (full A/B matrix).")

    # ── STEP 2: Full A vs B matrix ────────────────────────────────────────────
    print(f"\n[STEP 2] Full A/B matrix — {trials} trials × 40 tasks × 2 arms")
    print(f"         Projected tokens: ~{trials * len(TASKS) * 2 * 200} (rough estimate)")

    try:
        results_a = await _run_arm(TASKS, listing_a, provider, trials=trials, arm_label="Arm-A")
    except CostCeilingError:
        print(f"[STEP 2] ABORTED during Arm A: cost ceiling hit.")
        print(f"         Total spent: ${provider.total_cost_usd:.4f}")
        return

    try:
        results_b = await _run_arm(TASKS, listing_b, provider, trials=trials, arm_label="Arm-B")
    except CostCeilingError:
        print(f"[STEP 2] ABORTED during Arm B: cost ceiling hit.")
        print(f"         Total spent: ${provider.total_cost_usd:.4f}")
        return

    # Outcome counts
    counts_a = _count_outcomes(results_a)
    counts_b = _count_outcomes(results_b)
    total_a = len(results_a)
    total_b = len(results_b)

    correct_rate_a = counts_a["SELECTED-CORRECT"] / total_a if total_a else 0.0
    correct_rate_b = counts_b["SELECTED-CORRECT"] / total_b if total_b else 0.0
    effect = correct_rate_b - correct_rate_a

    # Task-level accuracies for sign test
    task_accs_a = _task_correct_rate(results_a, TASKS, trials)
    task_accs_b = _task_correct_rate(results_b, TASKS, trials)
    task_deltas = [b - a for a, b in zip(task_accs_a, task_accs_b, strict=True)]
    n_plus, n_minus, p_val = _sign_test(task_deltas)
    n_ties = len(task_deltas) - n_plus - n_minus

    from evals.fixtures.t18_catalog import FAMILY_MAP

    # Task-clustered table
    print("\n" + "=" * 100)
    print("FRONTIER-T18 TASK-CLUSTERED RESULT TABLE")
    print(f"{'Family':<16} {'Task description (truncated)':<52} {'A%':>5} {'B%':>5} {'dlt%':>6}")
    print("-" * 100)
    for i, task in enumerate(TASKS):
        family = FAMILY_MAP[task.tool_name]
        a_pct = task_accs_a[i] * 100
        b_pct = task_accs_b[i] * 100
        delta = task_deltas[i] * 100
        task_desc = task.description[:50] + ".." if len(task.description) > 52 else task.description
        print(f"{family:<16} {task_desc:<52} {a_pct:>4.0f}% {b_pct:>4.0f}% {delta:>+5.0f}%")
    print("-" * 100)
    print(
        f"{'AGGREGATE':<16} {'':52} "
        f"{correct_rate_a * 100:>4.1f}% {correct_rate_b * 100:>4.1f}% "
        f"{effect * 100:>+5.1f}%"
    )
    print("=" * 100)

    # 3-outcome breakdown
    print("\n3-OUTCOME BREAKDOWN (trial level):")
    print(f"{'Outcome':<28} {'Arm A':>12} {'Arm B':>12}")
    print("-" * 54)
    for outcome in ("SELECTED-CORRECT", "SELECTED-WRONG", "ABSTAINED-OR-HEDGED"):
        a_n = counts_a[outcome]
        b_n = counts_b[outcome]
        print(
            f"{outcome:<28} "
            f"{a_n:>5}/{total_a} ({100 * a_n / total_a if total_a else 0:>4.1f}%)  "
            f"{b_n:>5}/{total_b} ({100 * b_n / total_b if total_b else 0:>4.1f}%)"
        )

    # Sign test
    sig = "p<0.05 (significant)" if p_val < 0.05 else "p>=0.05 (not significant)"
    print(f"\n[SIGN TEST] n_plus={n_plus} (B>A)  n_minus={n_minus} (B<A)  ties={n_ties}  p={p_val:.4f}")
    print(f"            {sig}")

    # Spend summary
    print(f"\n[SPEND] Total: ${provider.total_cost_usd:.4f} / ${cost_ceiling_usd:.2f} ceiling")
    print(f"        Tokens in: {provider.tokens_in}  |  Tokens out: {provider.tokens_out}")
    if provider.total_cost_usd > cost_ceiling_usd:
        print("        WARNING: final spend exceeded ceiling (ceiling check fires per-call; "
              "last call may have pushed slightly over).")

    # Pre-registered verdict
    print("\n[PRE-REGISTERED VERDICT]")
    if correct_rate_b > correct_rate_a and p_val < 0.05:
        print("SURVIVES: Oracle descriptions improve selection on the frontier agent.")
        print(f"  Effect: {effect * 100:+.1f}pp (vs gemma2:9b T18 effect: +34.5pp)")
        print("  Description quality matters even for strong agents in the confusable-at-scale")
        print("  regime -> fixer value is DURABLE. Strongest possible commercial result.")
    elif correct_rate_b > correct_rate_a:
        print("DIRECTIONAL (B > A but not significant):")
        print(f"  Effect: {effect * 100:+.1f}pp  p={p_val:.4f}  n={len(TASKS)} tasks")
        print("  Insufficient power for a claim. Report as directional, not SURVIVES.")
    else:
        print("COLLAPSES: Oracle descriptions do NOT improve selection on the frontier agent.")
        print(f"  Effect: {effect * 100:+.1f}pp  p={p_val:.4f}")
        print("  The frontier agent resolves tool selection from names alone even on T18.")
        print("  Fixer value is weak-agent-specific -> market shrinks as agents improve.")

    print(f"\n  (One frontier model = one datapoint. Do not over-generalize.)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FRONTIER-T18 — T18 description effect on a frontier API agent"
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Frontier model ID (e.g. claude-haiku-4-5-20251001, claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=_DEFAULT_TRIALS,
        help=f"Trials per arm per task for STEP 2 (pre-registered: {_DEFAULT_TRIALS})",
    )
    parser.add_argument(
        "--cost-ceiling",
        type=float,
        default=_DEFAULT_COST_CEILING_USD,
        help=f"Hard spend cap in USD (default: ${_DEFAULT_COST_CEILING_USD:.2f})",
    )
    args = parser.parse_args()
    asyncio.run(run(args.model, args.trials, args.cost_ceiling))


if __name__ == "__main__":
    main()
