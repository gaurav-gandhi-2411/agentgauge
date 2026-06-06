#!/usr/bin/env python3
"""T18 oracle A/B: does a large confusable catalog (60 tools, 10 families) create headroom
for discriminating descriptions to improve selection_accuracy?

Arm A = empty descriptions (vague server, agent relies on names alone).
Arm B = oracle discriminating descriptions (each distinguishes within-family tools).

Usage:
    python scripts/run_t18_oracle_ab.py [--agent-model gemma2:9b] [--trials 5] [--stability-trials 3]

Steps (pre-checks reported first, before any interpretation):
1. Assert agent != judge != generator (family check)
2. MANIPULATION CHECK: assert Arm A and Arm B tool listings differ.
3. STABILITY PRE-SCREEN:
   a. Run Arm A twice (stability_run_1, stability_run_2) with --stability-trials each
   b. For each task, count successes in each stability run
   c. Drop any task where |successes_run1 - successes_run2| > 1
   d. Report dropped count and names
4. HEADROOM CHECK:
   a. Compute Arm A accuracy on surviving tasks (from stability_run_1 results)
   b. If accuracy < 40%: ABORT — too hard (below gate)
   c. If accuracy > 70%: ABORT — saturated (above gate)
5. N CHECK: if N_surviving < 30, STOP.
6. Run Arm A and Arm B (oracle) with --trials on the surviving task set.
7. Print parse_failed diagnostic first.
8. Print task-clustered table (Family | Task (truncated 50) | A% | B% | delta%).
9. Sign test on task-level deltas.
10. Three-way verdict: POSITIVE / NULL / ABORT.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path

# ── sign test (no scipy required) ─────────────────────────────────────────────


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


# ── stability screen ───────────────────────────────────────────────────────────


def stability_screen(
    task_successes_run1: list[int],
    task_successes_run2: list[int],
    trials: int,  # noqa: ARG001 — kept for signature symmetry with CI test
) -> list[bool]:
    """Return keep-mask. Task is kept if |successes_run1 - successes_run2| <= 1."""
    return [
        abs(s1 - s2) <= 1 for s1, s2 in zip(task_successes_run1, task_successes_run2, strict=True)
    ]


# ── task-level accuracy helper ─────────────────────────────────────────────────


def task_level_accuracy(run_results: list, tasks: list, trials: int) -> list[float]:
    """Compute per-task selection accuracy from run_results.

    run_results is a flat list of RunResult with tasks × trials entries.
    Returns a list of floats in [0, 1] (fraction of trials correct per task).
    """
    accs: list[float] = []
    for i, task in enumerate(tasks):
        task_results = run_results[i * trials : (i + 1) * trials]
        correct = sum(1 for r in task_results if r.selected_tool == task.tool_name)
        accs.append(correct / trials if trials > 0 else 0.0)
    return accs


async def run(agent_model: str, trials: int, stability_trials: int) -> None:
    import agentgauge.ab_harness as ab
    from agentgauge.client import cleanup_connection, connect_stdio
    from agentgauge.providers import OllamaProvider
    from agentgauge.runner import _build_tool_listing, run_tasks

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from evals.fixtures.t18_catalog import FAMILY_MAP, TASKS

    ab.assert_agent_ne_judge_ne_generator(agent_model)

    fixture_a = Path(__file__).parent.parent / "examples" / "t18_vague_server.py"
    fixture_b = Path(__file__).parent.parent / "examples" / "t18_oracle_server.py"
    python = sys.executable

    print("=" * 80)
    print("T18 Oracle A/B — Discoverability at Scale (60-tool confusable catalog)")
    print(f"Agent: {agent_model}  |  Trials: {trials}  |  Stability trials: {stability_trials}")
    print(f"Tasks (pre-registered): {len(TASKS)}  |  Tools: 60  |  Families: 10")
    print("=" * 80)

    print("\n[STEP 1] Connecting to Arm A...")
    client_a, ctx_a = await connect_stdio(python, [str(fixture_a)])

    try:
        # MANIPULATION CHECK
        info_a = await client_a.introspect()
        client_b_check, ctx_b_check = await connect_stdio(python, [str(fixture_b)])
        try:
            info_b = await client_b_check.introspect()
            listing_a = _build_tool_listing(info_a.tools)
            listing_b = _build_tool_listing(info_b.tools)
            manip_ok = listing_a != listing_b
            print(
                f"[PRE-CHECK] Manipulation check: "
                f"{'PASS — Arm A and B prompts differ' if manip_ok else 'FAIL — prompts identical!'}"
            )
            if not manip_ok:
                print("ABORT: manipulation check failed — arm B descriptions identical to arm A.")
                return
        finally:
            await cleanup_connection(ctx_b_check)

        # STABILITY PRE-SCREEN
        print(
            f"\n[STEP 2] Stability pre-screen: running Arm A twice "
            f"({stability_trials} trials each)..."
        )
        agent_stab1 = OllamaProvider(agent_model)
        agent_stab2 = OllamaProvider(agent_model)

        stab_results_1 = await run_tasks(TASKS, client_a, agent_stab1, trials=stability_trials)
        stab_results_2 = await run_tasks(TASKS, client_a, agent_stab2, trials=stability_trials)

        successes_1 = []
        successes_2 = []
        for i, task in enumerate(TASKS):
            r1 = stab_results_1[i * stability_trials : (i + 1) * stability_trials]
            r2 = stab_results_2[i * stability_trials : (i + 1) * stability_trials]
            successes_1.append(sum(1 for r in r1 if r.selected_tool == task.tool_name))
            successes_2.append(sum(1 for r in r2 if r.selected_tool == task.tool_name))

        keep_mask = stability_screen(successes_1, successes_2, stability_trials)
        dropped_count = sum(1 for k in keep_mask if not k)
        dropped_tasks = [TASKS[i] for i, k in enumerate(keep_mask) if not k]
        surviving_tasks = [TASKS[i] for i, k in enumerate(keep_mask) if k]

        print(f"[PRE-CHECK] Stability: {dropped_count} tasks dropped out of {len(TASKS)}")
        if dropped_tasks:
            for t in dropped_tasks:
                idx = TASKS.index(t)
                print(
                    f"  DROPPED: [{FAMILY_MAP[t.tool_name]}] {t.tool_name!r}: "
                    f"{t.description[:60]!r}"
                )
                print(
                    f"           stability_run1={successes_1[idx]}/{stability_trials}, "
                    f"stability_run2={successes_2[idx]}/{stability_trials}"
                )

        n_surviving = len(surviving_tasks)
        print(f"[PRE-CHECK] Surviving tasks: {n_surviving}")

        # HEADROOM CHECK (use run 1 of stability for arm A baseline estimate)
        stab1_surviving_accs = []
        for i, task in enumerate(TASKS):
            if not keep_mask[i]:
                continue
            r1 = stab_results_1[i * stability_trials : (i + 1) * stability_trials]
            acc = sum(1 for r in r1 if r.selected_tool == task.tool_name) / stability_trials
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
            print(
                f"\nABORT: Arm A below 40% ({arm_a_baseline:.1f}%) — "
                "tasks are too hard / catalog too dense."
            )
            print("       This is a fixture-quality failure. No A/B comparison made.")
            return
        if arm_a_baseline > 70.0:
            print(
                f"\nABORT: Arm A above 70% ({arm_a_baseline:.1f}%) — "
                "catalog is already navigable by name alone (saturated)."
            )
            print("       Not enough headroom for a meaningful effect.")
            return
        print(f"            -> PASS ({arm_a_baseline:.1f}% in 40-70% range)")

        # N CHECK
        if n_surviving < 30:
            print(f"\nSTOP: Only {n_surviving} surviving tasks (need >= 30).")
            print("      Too many tasks dropped in stability screen — fixture-quality failure.")
            return
        print(f"[PRE-CHECK] N check: {n_surviving} >= 30 -> PASS")

        # MAIN A/B RUN
        print(f"\n[STEP 3] Running main A/B: {n_surviving} surviving tasks × {trials} trials...")
        client_b, ctx_b = await connect_stdio(python, [str(fixture_b)])
        try:
            agent_a = OllamaProvider(agent_model)
            agent_b = OllamaProvider(agent_model)

            results_a = await run_tasks(surviving_tasks, client_a, agent_a, trials=trials)
            results_b = await run_tasks(surviving_tasks, client_b, agent_b, trials=trials)
        finally:
            await cleanup_connection(ctx_b)

        # PARSE-FAILED DIAGNOSTIC (reported first per spec)
        parse_failed_a = sum(
            1 for r in results_a if r.selected_tool not in {t.tool_name for t in surviving_tasks}
        )
        parse_failed_b = sum(
            1 for r in results_b if r.selected_tool not in {t.tool_name for t in surviving_tasks}
        )
        total_trials_a = len(results_a)
        total_trials_b = len(results_b)
        print(
            f"\n[DIAGNOSTIC] parse_failed: "
            f"Arm A = {parse_failed_a}/{total_trials_a} "
            f"({100 * parse_failed_a / total_trials_a if total_trials_a else 0:.1f}%)  |  "
            f"Arm B = {parse_failed_b}/{total_trials_b} "
            f"({100 * parse_failed_b / total_trials_b if total_trials_b else 0:.1f}%)"
        )

        # TASK-LEVEL ACCURACIES
        task_accs_a = task_level_accuracy(results_a, surviving_tasks, trials)
        task_accs_b = task_level_accuracy(results_b, surviving_tasks, trials)
        task_deltas = [b - a for a, b in zip(task_accs_a, task_accs_b, strict=True)]

        # AGGREGATE ACCURACY
        agg_a = sum(task_accs_a) / len(task_accs_a) * 100
        agg_b = sum(task_accs_b) / len(task_accs_b) * 100

        # SIGN TEST
        n_plus, n_minus, p_val = _sign_test(task_deltas)
        n_ties = len(task_deltas) - n_plus - n_minus

        # PRINT TASK-CLUSTERED TABLE
        print("\n" + "=" * 100)
        print("T18 TASK-CLUSTERED RESULT TABLE")
        print(f"{'Family':<16} {'Task description (truncated)':<52} {'A%':>5} {'B%':>5} {'Δ%':>6}")
        print("-" * 100)
        for i, task in enumerate(surviving_tasks):
            family = FAMILY_MAP[task.tool_name]
            a_pct = task_accs_a[i] * 100
            b_pct = task_accs_b[i] * 100
            delta = task_deltas[i] * 100
            task_desc = (
                task.description[:50] + ".." if len(task.description) > 52 else task.description
            )
            print(f"{family:<16} {task_desc:<52} {a_pct:>4.0f}% {b_pct:>4.0f}% {delta:>+5.0f}%")
        print("-" * 100)
        print(f"{'AGGREGATE':<16} {'':52} {agg_a:>4.1f}% {agg_b:>4.1f}% {agg_b - agg_a:>+5.1f}%")
        print("=" * 100)

        print(
            f"\n[SIGN TEST] n_plus={n_plus} (B>A)  n_minus={n_minus} (B<A)  "
            f"ties={n_ties}  p={p_val:.4f}"
        )
        sig = "p<0.05 (significant)" if p_val < 0.05 else "p>=0.05 (not significant)"
        print(f"            {sig}")

        print("\n[PRE-REGISTERED VERDICT]")
        if agg_b > agg_a and p_val < 0.05:
            print(
                "POSITIVE: Oracle descriptions improve selection in the 60-tool confusable catalog."
            )
            print("  -> Discriminating descriptions have real behavioral headroom at scale.")
            print("  -> Q2 (fixer realization at catalog scale) is the next experiment.")
        elif agg_b > agg_a:
            print("DIRECTIONAL (oracle > A but not significant):")
            print(f"  Delta={agg_b - agg_a:+.1f}%  p={p_val:.4f}  n={n_surviving}")
            print("  Insufficient power for a claim. Report as directional, not positive.")
        else:
            print("NULL: Oracle descriptions do NOT improve selection even in the large catalog.")
            print(
                "  -> gemma2:9b ignores descriptions when facing dense within-family distractors."
            )
            print(
                "  -> selection_accuracy remains behaviorally description-insensitive "
                "at catalog scale."
            )
            print("  -> Record construct-validity finding in STATUS.md.")

    finally:
        await cleanup_connection(ctx_a)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="T18 oracle A/B experiment — discoverability at scale"
    )
    parser.add_argument(
        "--agent-model",
        default="gemma2:9b",
        help="Agent model (must be != llama3.1 and != qwen3)",
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
