#!/usr/bin/env python3
"""Ty oracle A/B: does showing the agent an oracle schema (with correct enums) reduce malformed calls?

Usage:
    python scripts/run_ty_oracle_ab.py [--agent-model gemma2:9b] [--trials 5] [--stability-trials 3]

Steps (pre-checks reported first, before any interpretation):
1. Assert agent != judge != generator (family check)
2. Manipulation check: assert Arm A and B tool listings differ
3. STABILITY PRE-SCREEN:
   a. Run Arm A twice (stability_run_1, stability_run_2) with --stability-trials each
   b. For each task, count correct calls in each stability run (via _is_correct_call)
   c. Drop any task where |successes_run1 - successes_run2| > 1
   d. Report dropped count and names
4. HEADROOM CHECK:
   a. Compute Arm A accuracy on surviving tasks (from stability_run_1 results)
   b. If accuracy < 40% or > 70%, STOP with a fixture-quality warning
5. N CHECK: if N_surviving < 30, STOP.
6. Run Arm A and Arm B (oracle) with --trials on the surviving task set.
7. Print task-clustered table (task | arm_A_acc | arm_B_acc | delta).
8. Sign test on task-level deltas.
9. Honest verdict: POSITIVE / NULL / DIRECTIONAL.

Correctness metric: _is_correct_call compares result.constructed_args against
GOLD_CONSTRAINTS — NOT result.success (server always echoes success).
Easy tools (EASY_TOOL_NAMES) are always counted as correct (no constrained params).
"""
from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentgauge.runner import RunResult
    from agentgauge.tasks import Task


# ── Sign test (no scipy required) ─────────────────────────────────────────────


def _sign_test(deltas: list[float]) -> tuple[int, int, float]:
    """Two-tailed sign test. Returns (n_plus, n_minus, p_value).

    Ignores ties (delta == 0). p-value from binomial distribution with p=0.5.
    """
    n_plus = sum(1 for d in deltas if d > 0)
    n_minus = sum(1 for d in deltas if d < 0)
    n = n_plus + n_minus
    if n == 0:
        return 0, 0, 1.0
    k = min(n_plus, n_minus)
    p_one_tail = sum(math.comb(n, i) * (0.5**n) for i in range(k + 1))
    p = min(1.0, 2.0 * p_one_tail)
    return n_plus, n_minus, round(p, 4)


# ── Stability screen ───────────────────────────────────────────────────────────


def stability_screen(
    task_successes_run1: list[int],
    task_successes_run2: list[int],
    trials: int,  # noqa: ARG001 — kept for signature symmetry with CI test
) -> list[bool]:
    """Return keep-mask. Task is kept if |successes_run1 - successes_run2| <= 1."""
    return [
        abs(s1 - s2) <= 1
        for s1, s2 in zip(task_successes_run1, task_successes_run2, strict=True)
    ]


# ── Call-correctness scoring ───────────────────────────────────────────────────


def _is_correct_call(
    result: RunResult,
    task: Task,
    gold_constraints: dict[tuple[str, str], dict[str, str]],
) -> bool:
    """Score a single trial: True if constructed_args satisfy the gold constraint.

    Easy tools (no entry in gold_constraints) are always correct.
    Hard tools: all constrained param values must match the gold exactly.
    """
    gold = gold_constraints.get((task.tool_name, task.description))
    if gold is None:
        # Easy tool — no constrained params, always correct
        return True
    for param, expected_value in gold.items():
        if result.constructed_args.get(param) != expected_value:
            return False
    return True


def task_level_accuracy(
    run_results: list[Any],
    tasks: list[Any],
    trials: int,
    gold_constraints: dict[tuple[str, str], dict[str, str]],
) -> list[float]:
    """Per-task fraction of correct calls using _is_correct_call.

    run_results is a flat list of RunResult with tasks × trials entries.
    Returns a list of floats in [0, 1] (fraction of trials correct per task).
    """
    accs: list[float] = []
    for i, task in enumerate(tasks):
        task_results = run_results[i * trials : (i + 1) * trials]
        correct = sum(
            1 for r in task_results if _is_correct_call(r, task, gold_constraints)
        )
        accs.append(correct / trials if trials > 0 else 0.0)
    return accs


async def run(agent_model: str, trials: int, stability_trials: int) -> None:
    import agentgauge.ab_harness as ab
    from agentgauge.client import cleanup_connection, connect_stdio
    from agentgauge.providers import OllamaProvider
    from agentgauge.runner import _build_tool_listing, run_tasks

    # Import pre-registered tasks and gold constraints
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import evals.fixtures.ty_tasks as ty

    gold_constraints = ty.GOLD_CONSTRAINTS
    tasks = ty.TASKS
    hard_tool_names = ty.HARD_TOOL_NAMES

    ab.assert_agent_ne_judge_ne_generator(agent_model)

    fixture_a = Path(__file__).parent.parent / "examples" / "call_constraints_server.py"
    fixture_b = (
        Path(__file__).parent.parent / "examples" / "call_constraints_server_oracle.py"
    )
    python = sys.executable

    print("=" * 72)
    print("Ty Oracle A/B — Call-Correctness Fixture")
    print(f"Agent: {agent_model}  |  Trials: {trials}  |  Stability trials: {stability_trials}")
    print(f"Tasks (pre-registered): {len(tasks)}")
    print("=" * 72)

    print("\n[STEP 1] Connecting to Arm A and Arm B for manipulation check...")
    client_a, ctx_a = await connect_stdio(python, [str(fixture_a)])

    try:
        info_a = await client_a.introspect()
        client_b_check, ctx_b_check = await connect_stdio(python, [str(fixture_b)])
        try:
            info_b = await client_b_check.introspect()
            listing_a = _build_tool_listing(info_a.tools)
            listing_b = _build_tool_listing(info_b.tools)
            manip_ok = listing_a != listing_b
            print(
                "[PRE-CHECK] Manipulation check: "
                + ("PASS — Arm A and B prompts differ" if manip_ok else "FAIL — prompts identical!")
            )
            if not manip_ok:
                print("ABORT: manipulation check failed — arm B schema identical to arm A.")
                return
        finally:
            await cleanup_connection(ctx_b_check)

        # Stability pre-screen
        print(
            f"\n[STEP 2] Stability pre-screen: running Arm A twice "
            f"({stability_trials} trials each)..."
        )
        agent_stab1 = OllamaProvider(agent_model)
        agent_stab2 = OllamaProvider(agent_model)

        stab_results_1 = await run_tasks(tasks, client_a, agent_stab1, trials=stability_trials)
        stab_results_2 = await run_tasks(tasks, client_a, agent_stab2, trials=stability_trials)

        successes_1: list[int] = []
        successes_2: list[int] = []
        for i, task in enumerate(tasks):
            r1 = stab_results_1[i * stability_trials : (i + 1) * stability_trials]
            r2 = stab_results_2[i * stability_trials : (i + 1) * stability_trials]
            successes_1.append(
                sum(1 for r in r1 if _is_correct_call(r, task, gold_constraints))
            )
            successes_2.append(
                sum(1 for r in r2 if _is_correct_call(r, task, gold_constraints))
            )

        keep_mask = stability_screen(successes_1, successes_2, stability_trials)
        dropped_count = sum(1 for k in keep_mask if not k)
        dropped_tasks = [tasks[i] for i, k in enumerate(keep_mask) if not k]
        surviving_tasks = [tasks[i] for i, k in enumerate(keep_mask) if k]

        print(f"[PRE-CHECK] Stability: {dropped_count} tasks dropped out of {len(tasks)}")
        if dropped_tasks:
            for t in dropped_tasks:
                idx = tasks.index(t)
                tool_type = "hard" if t.tool_name in hard_tool_names else "easy"
                print(
                    f"  DROPPED: [{tool_type}] {t.tool_name!r}: {t.description[:60]!r}"
                )
                print(
                    f"           stability_run1={successes_1[idx]}/{stability_trials}, "
                    f"stability_run2={successes_2[idx]}/{stability_trials}"
                )

        n_surviving = len(surviving_tasks)
        print(f"[PRE-CHECK] Surviving tasks: {n_surviving}")

        # Headroom check (use stability run 1 for arm A baseline estimate)
        stab1_surviving_accs: list[float] = []
        for i, task in enumerate(tasks):
            if not keep_mask[i]:
                continue
            r1 = stab_results_1[i * stability_trials : (i + 1) * stability_trials]
            acc = (
                sum(1 for r in r1 if _is_correct_call(r, task, gold_constraints))
                / stability_trials
            )
            stab1_surviving_accs.append(acc)

        arm_a_baseline = (
            (sum(stab1_surviving_accs) / len(stab1_surviving_accs) * 100)
            if stab1_surviving_accs
            else 0.0
        )
        print(
            f"[PRE-CHECK] Arm A baseline (stability run 1, surviving tasks): {arm_a_baseline:.1f}%"
        )
        print("            Target: 40-70% (real headroom). Outside range = fixture-quality issue.")

        if arm_a_baseline < 40.0:
            print("STOP: Arm A below 40% — enum values may be too hard to guess even by luck.")
            print("      This is a fixture-quality failure. Do not proceed to interpretation.")
            return
        if arm_a_baseline > 70.0:
            print("STOP: Arm A above 70% — not enough headroom for a meaningful oracle effect.")
            print("      This is a fixture-quality failure. Do not proceed to interpretation.")
            return
        print(f"            -> PASS ({arm_a_baseline:.1f}% in 40-70% range)")

        if n_surviving < 30:
            print(f"STOP: Only {n_surviving} surviving tasks (need >= 30).")
            print(
                "      This is a fixture-quality failure — too many tasks dropped in stability "
                "screen."
            )
            return
        print(f"[PRE-CHECK] N check: {n_surviving} >= 30 -> PASS")

        # Main A/B run on surviving tasks
        print(
            f"\n[STEP 3] Running main A/B: {n_surviving} surviving tasks × {trials} trials..."
        )
        client_b, ctx_b = await connect_stdio(python, [str(fixture_b)])
        try:
            agent_a = OllamaProvider(agent_model)
            agent_b = OllamaProvider(agent_model)

            results_a = await run_tasks(surviving_tasks, client_a, agent_a, trials=trials)
            results_b = await run_tasks(surviving_tasks, client_b, agent_b, trials=trials)
        finally:
            await cleanup_connection(ctx_b)

        # Task-level accuracies
        task_accs_a = task_level_accuracy(results_a, surviving_tasks, trials, gold_constraints)
        task_accs_b = task_level_accuracy(results_b, surviving_tasks, trials, gold_constraints)
        task_deltas = [b - a for a, b in zip(task_accs_a, task_accs_b, strict=True)]

        # Aggregate accuracy
        agg_a = sum(task_accs_a) / len(task_accs_a) * 100
        agg_b = sum(task_accs_b) / len(task_accs_b) * 100

        # Sign test
        n_plus, n_minus, p_val = _sign_test(task_deltas)
        n_ties = len(task_deltas) - n_plus - n_minus

        # Print task-clustered table
        print("\n" + "=" * 96)
        print("Ty TASK-CLUSTERED RESULT TABLE")
        print(
            f"{'Type':<6} {'Tool':<22} {'Task (truncated)':<40} {'A':>5} {'B':>5} {'Δ':>6}"
        )
        print("-" * 96)
        for i, task in enumerate(surviving_tasks):
            tool_type = "hard" if task.tool_name in hard_tool_names else "easy"
            a_pct = task_accs_a[i] * 100
            b_pct = task_accs_b[i] * 100
            delta = task_deltas[i] * 100
            task_desc = (
                task.description[:38] + ".."
                if len(task.description) > 40
                else task.description
            )
            print(
                f"{tool_type:<6} {task.tool_name:<22} {task_desc:<40} "
                f"{a_pct:>4.0f}% {b_pct:>4.0f}% {delta:>+5.0f}%"
            )
        print("-" * 96)
        print(
            f"{'':6} {'AGGREGATE':<22} {'':40} "
            f"{agg_a:>4.1f}% {agg_b:>4.1f}% {agg_b - agg_a:>+5.1f}%"
        )
        print("=" * 96)

        print(
            f"\n[SIGN TEST] n_plus={n_plus} (B>A)  n_minus={n_minus} (B<A)  "
            f"ties={n_ties}  p={p_val:.4f}"
        )
        sig = "p<0.05 (significant)" if p_val < 0.05 else "p>=0.05 (not significant)"
        print(f"            {sig}")

        print("\n[PRE-REGISTERED VERDICT]")
        if agg_b > agg_a and p_val < 0.05:
            print(
                "POSITIVE: Oracle schema reduces malformed calls — agents given enum+description "
                "info construct valid calls more often."
            )
            print(
                "  -> description_quality / schema_completeness have real behavioral headroom "
                "on CALLS."
            )
            print("  -> Tx-val / a fixer-realization experiment should run on THIS fixture.")
        elif agg_b > agg_a:
            print("DIRECTIONAL (oracle > A but not significant):")
            print(f"  Delta={agg_b - agg_a:+.1f}%  p={p_val:.4f}  n={n_surviving}")
            print("  Insufficient power for a claim. Report as directional, not positive.")
        else:
            print(
                "NULL: gemma builds correct calls without schema even when values are "
                "non-guessable — schema info does not reduce malformed calls."
            )
            print(
                "  -> Combined with the selection finding, both description_quality and "
                "schema_completeness appear behaviorally inert for gemma2:9b on standard "
                "call construction."
            )

    finally:
        await cleanup_connection(ctx_a)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ty oracle A/B — call-correctness experiment")
    parser.add_argument(
        "--agent-model",
        default="gemma2:9b",
        help="Agent model (must differ from llama3.1 judge and qwen3 generator families)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=5,
        help="Trials per arm per task for the main A/B run",
    )
    parser.add_argument(
        "--stability-trials",
        type=int,
        default=3,
        help="Trials per run for the stability pre-screen",
    )
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials, args.stability_trials))


if __name__ == "__main__":
    main()
