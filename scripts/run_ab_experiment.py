#!/usr/bin/env python3
"""Run the T16 paired A/B experiment on the held-out fixture server.

Usage:
    python scripts/run_ab_experiment.py [--agent-model gemma2:9b] [--trials 5]

Steps:
1. Assert agent != judge != generator (family check)
2. Start arm A server (examples/mediocre_server.py)
3. Run fixer with qwen3:8b generator + llama3.1:8b judge to get patched source
4. Write patched source to a temp file; start arm B server
5. Run paired A/B with 10 pre-specified tasks, --trials per arm per task
6. Print the pre-registered result table with validity check

Validity check: arm A must score <= 80% on at least one metric.
A run where arm A is saturated near 100% is VOID — see spec.md.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

# 10 pre-specified tasks (2 per tool) describing intent WITHOUT naming the tool.
# These exercise the confusable pairs (get_a/get_b, del_a/del_b) and the opaque
# required params (put_x: x and t not mentioned in task → arm A may omit them).
#
# task.tool_name is the CORRECT tool to call for selection_accuracy scoring.
# Descriptions are intentionally natural-language, not tool-name hints.
_PRE_SPECIFIED_TASKS = [
    # put_x: store a data point — x and t are not in the task description
    ("put_x", "Add a data point to session 1 with record ID 'r-001'"),
    ("put_x", "Add another data point to session 2 with ID 'r-002'"),
    # get_a: retrieve a specific record — confusable with get_b
    ("get_a", "Get record 'r-001' from session 1"),
    ("get_a", "Retrieve record 'r-002' from session 2 by its ID"),
    # get_b: compute aggregate — confusable with get_a
    ("get_b", "Get a computed statistic for session 1"),
    ("get_b", "Compute an aggregate measure for session 2"),
    # del_a: delete a specific record — confusable with del_b
    ("del_a", "Delete record 'r-001' from session 1, leaving other records intact"),
    ("del_a", "Remove the single entry 'r-002' from session 2"),
    # del_b: delete an entire session — confusable with del_a
    ("del_b", "Erase all data in session 1 entirely"),
    ("del_b", "Clear all records in session 2"),
]


async def run(agent_model: str, trials: int) -> None:
    import agentgauge.ab_harness as ab
    from agentgauge.client import cleanup_connection, connect_stdio
    from agentgauge.fixer import run_fixer
    from agentgauge.providers import OllamaProvider
    from agentgauge.tasks import Task

    ab.assert_agent_ne_judge_ne_generator(agent_model)

    tasks = [Task(tool_name=tn, description=desc, sample_args={}) for tn, desc in _PRE_SPECIFIED_TASKS]

    fixture = Path(__file__).parent.parent / "examples" / "mediocre_server.py"
    python = sys.executable

    print(f"Connecting to arm A: {fixture.name}")
    client_a, ctx_a = await connect_stdio(python, [str(fixture)])

    try:
        info_a = await client_a.introspect()
        print(f"Arm A tools: {[t.name for t in info_a.tools]}")

        generator = OllamaProvider("qwen3:8b")
        judge = OllamaProvider("llama3.1:8b")

        print("Running fixer (qwen3:8b generator, llama3.1:8b judge)...")
        fix_report = await run_fixer(
            info_a.tools,
            generator,
            judge,
            fixture,
            dims=["schema_completeness", "description_quality"],
        )

        if fix_report.patched_source:
            patched = fix_report.patched_source
            n_fixes = len(fix_report.accepted)
            print(f"Fixer applied {n_fixes} fix(es). Diff preview:")
            diff_lines = fix_report.diff_text.splitlines()
            for line in diff_lines[:50]:
                print(" ", line)
            if len(diff_lines) > 50:
                print(f"  ... ({len(diff_lines) - 50} more lines)")
        else:
            print("WARNING: Fixer produced no changes — arm B = arm A (null result expected)")
            patched = fixture.read_text(encoding="utf-8")

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            prefix="obsstore_fixed_",
            encoding="utf-8",
        ) as f:
            f.write(patched)
            fixed_path = Path(f.name)

        print(f"\nConnecting to arm B: {fixed_path.name}")
        client_b, ctx_b = await connect_stdio(python, [str(fixed_path)])

        try:
            info_b = await client_b.introspect()
            print(f"Arm B tools: {[t.name for t in info_b.tools]}")

            agent_a = OllamaProvider(agent_model)
            agent_b = OllamaProvider(agent_model)
            agent_noise = OllamaProvider(agent_model)

            print(f"\nRunning paired A/B: agent={agent_model}, tasks={len(tasks)}, trials={trials}")
            result = await ab.run_paired_ab(
                client_a,
                client_b,
                agent_a,
                agent_b,
                agent_noise,
                tasks=tasks,
                trials=trials,
            )

            print("\n" + "=" * 72)
            print("T16 Pre-registered A/B Result Table (Run #2 — ObsStore fixture)")
            print(f"Agent: {agent_model}  |  Judge: llama3.1:8b  |  Generator: qwen3:8b")
            print(f"Tasks: {len(result.tasks)}  |  Trials per arm: {result.trials}")
            print("=" * 72)

            # Validity check
            arm_a_sel = result.arm_a.selection_accuracy
            arm_a_cor = result.arm_a.call_correctness
            valid = arm_a_sel <= 80.0 or arm_a_cor <= 80.0
            validity_msg = (
                f"VALID (arm A below ceiling on {'selection' if arm_a_sel <= 80 else 'correctness'})"
                if valid
                else f"VOID — arm A saturated ({arm_a_sel:.1f}% sel, {arm_a_cor:.1f}% corr >= 80% both)"
            )
            print(f"Validity: {validity_msg}")
            print("=" * 72)

            hdr = f"{'Metric':<24} {'Arm A':>7} {'Arm B':>7} {'Delta':>7} {'Noise':>7}"
            print(hdr)
            print("-" * 72)
            m = result.mcnemar_selection
            print(
                f"{'selection_accuracy':<24} {result.arm_a.selection_accuracy:>6.1f}% "
                f"{result.arm_b.selection_accuracy:>6.1f}% "
                f"{result.selection_delta:>+6.1f}% "
                f"{result.noise_floor_selection:>6.1f}%"
            )
            print(f"{'':24}  McNemar: b={m.b} c={m.c} stat={m.statistic:.3f} {m.p_approx}")
            m2 = result.mcnemar_correctness
            print(
                f"{'call_correctness':<24} {result.arm_a.call_correctness:>6.1f}% "
                f"{result.arm_b.call_correctness:>6.1f}% "
                f"{result.correctness_delta:>+6.1f}% "
                f"{result.noise_floor_correctness:>6.1f}%"
            )
            print(f"{'':24}  McNemar: b={m2.b} c={m2.c} stat={m2.statistic:.3f} {m2.p_approx}")
            print("=" * 72)

            if valid:
                print("\nVerdict:")
                for label, delta, noise, mn in [
                    ("selection_accuracy", result.selection_delta, result.noise_floor_selection, m),
                    ("call_correctness", result.correctness_delta, result.noise_floor_correctness, m2),
                ]:
                    if delta > max(noise, 5.0):
                        verdict = "EFFECT (delta > max(noise_floor, 5 pt minimum))"
                    elif delta <= 0:
                        verdict = "NULL/NEGATIVE"
                    else:
                        verdict = "WEAK (delta > 0 but ≤ noise floor + 5pt minimum)"
                    print(f"  {label}: {verdict}")
            else:
                print("\nRun is VOID — do not interpret A-vs-B delta.")

        finally:
            await cleanup_connection(ctx_b)
            fixed_path.unlink(missing_ok=True)

    finally:
        await cleanup_connection(ctx_a)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run T16 paired A/B experiment")
    parser.add_argument(
        "--agent-model",
        default="gemma2:9b",
        help="Agent model (must be third family != llama3.1 != qwen3)",
    )
    parser.add_argument("--trials", type=int, default=5, help="Trials per arm per task")
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials))


if __name__ == "__main__":
    main()
