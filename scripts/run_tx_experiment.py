#!/usr/bin/env python3
"""Tx A/B experiment: harm gate (ObsStore) + upside steps 1 and 2 (grounded fixture).

Usage:
    python scripts/run_tx_experiment.py [--agent-model gemma2:9b] [--trials 5]
    python scripts/run_tx_experiment.py --step harm    # run only harm gate
    python scripts/run_tx_experiment.py --step upside  # run upside steps 1 and 2

Pre-registered tasks for grounded fixture (transform pipeline, 2 per tool):
Each task tests whether the agent picks the correct transform tool.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

# Pre-specified tasks for the grounded fixture (transform pipeline).
# 2 tasks per tool × 5 tools = 10 tasks.
_GROUNDED_TASKS = [
    ("transform_scale", "Multiply 4.0 by 2.5 and add 0.5 to the result"),
    ("transform_scale", "Apply a 50% amplitude reduction and subtract 3.0 from value 8.0"),
    ("transform_normalize", "Express 7.0 as a fraction of the range [0, 10]"),
    ("transform_normalize", "Rescale 25.0 to fit between 0 and 1, given original bounds 0 and 50"),
    ("transform_clip", "Ensure value 105 does not exceed 100 and is at least 0"),
    ("transform_clip", "Cap measurement -2.5 so it stays within the valid range [0, 50]"),
    ("transform_round", "Express 3.14159265 to 4 decimal places"),
    ("transform_round", "Reduce precision of 99.9999 to at most 2 decimal places"),
    ("transform_log", "What is ln(10.0)?"),
    ("transform_log", "Compute log base 2 of 8.0"),
]

# Pre-specified tasks for the harm gate (ObsStore fixture).
# Reuse the T16 tasks unchanged.
_OBSSTORE_TASKS = [
    ("put_x", "Add a data point to session 1 under key 'k-001'"),
    ("put_x", "Store a measurement in session 2 under key 'k-002'"),
    ("get_a", "Get the stored entry for key 'k-001' in session 1"),
    ("get_a", "Look up the item with key 'k-002' in session 2"),
    ("get_b", "Compute the total across all values in session 1"),
    ("get_b", "Get the aggregate maximum for session 2"),
    ("del_a", "Delete only the entry 'k-001' from session 1, leaving other entries"),
    ("del_a", "Remove just the item 'k-002' from session 2"),
    ("del_b", "Wipe all data in session 1 entirely"),
    ("del_b", "Clear everything stored in session 2"),
]


def _print_result_table(
    title: str,
    agent_model: str,
    result: object,
    n_tasks: int,
    validity_note: str = "",
) -> bool:
    """Print a formatted result table for one A/B run. Returns True if the run is valid."""
    import agentgauge.ab_harness as ab

    assert isinstance(result, ab.PairedABResult)
    print("\n" + "=" * 72)
    print(title)
    print(f"Agent: {agent_model}  |  Judge: llama3.1:8b  |  Generator: qwen3:8b")
    print(f"Tasks: {n_tasks}  |  Trials per arm: {result.trials}")
    if validity_note:
        print(f"Note: {validity_note}")
    print("=" * 72)

    arm_a_sel = result.arm_a.selection_accuracy
    arm_a_cor = result.arm_a.call_correctness
    valid = arm_a_sel <= 80.0 or arm_a_cor <= 80.0
    validity_msg = (
        f"VALID (arm A below ceiling on {'selection' if arm_a_sel <= 80 else 'correctness'})"
        if valid
        else f"VOID — arm A saturated ({arm_a_sel:.1f}%sel / {arm_a_cor:.1f}%corr >= 80% both)"
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
    return valid


async def run_harm_gate(agent_model: str, trials: int) -> None:
    """HARM GATE: ObsStore (opaque names) — abstain fires, Arm B >= Arm A."""
    import agentgauge.ab_harness as ab
    from agentgauge.client import cleanup_connection, connect_stdio
    from agentgauge.fixer import run_fixer
    from agentgauge.providers import OllamaProvider
    from agentgauge.tasks import Task

    ab.assert_agent_ne_judge_ne_generator(agent_model)

    tasks = [Task(tool_name=tn, description=desc, sample_args={}) for tn, desc in _OBSSTORE_TASKS]
    fixture = Path(__file__).parent.parent / "examples" / "mediocre_server.py"
    python = sys.executable

    print(f"\n=== HARM GATE: ObsStore (opaque names) ===")
    print(f"Connecting to arm A: {fixture.name}")
    client_a, ctx_a = await connect_stdio(python, [str(fixture)])
    try:
        info_a = await client_a.introspect()

        generator = OllamaProvider("qwen3:8b")
        judge = OllamaProvider("llama3.1:8b")

        print("Running fixer (qwen3:8b generator, llama3.1:8b judge)...")
        fix_report = await run_fixer(
            info_a.tools,
            generator,
            judge,
            fixture,
            dims=["description_quality"],
        )

        print(
            f"Fixer result: accepted={len(fix_report.accepted)}, "
            f"rejected={len(fix_report.rejected)}, "
            f"abstained={len(fix_report.abstained)}, "
            f"skipped={len(fix_report.skipped)}"
        )
        for entry in fix_report.abstained:
            print(f"  ABSTAINED: {entry}")

        # With all opaque tools, patched_source should be empty (no changes)
        # Use original source for arm B
        patched = fix_report.patched_source or fixture.read_text(encoding="utf-8")

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            prefix="obsstore_tx_fixed_",
            encoding="utf-8",
        ) as f:
            f.write(patched)
            fixed_path = Path(f.name)

        client_b, ctx_b = await connect_stdio(python, [str(fixed_path)])
        try:
            agent_a = OllamaProvider(agent_model)
            agent_b = OllamaProvider(agent_model)
            agent_noise = OllamaProvider(agent_model)

            print(f"Running paired A/B: agent={agent_model}, tasks={len(tasks)}, trials={trials}")
            result = await ab.run_paired_ab(
                client_a,
                client_b,
                agent_a,
                agent_b,
                agent_noise,
                tasks=tasks,
                trials=trials,
            )

            _print_result_table(
                "Tx HARM GATE — ObsStore (abstain fires → Arm B = Arm A)",
                agent_model,
                result,
                len(tasks),
                validity_note=(
                    "abstain fires on all tools → arm B = arm A → harm gate trivially satisfied"
                ),
            )

            if result.selection_delta >= 0:
                print("\nHARM GATE: PASS (Arm B selection_accuracy >= Arm A — regression removed)")
            else:
                print(
                    f"\nHARM GATE: FAIL (Arm B < Arm A by {abs(result.selection_delta):.1f}%)"
                )

        finally:
            await cleanup_connection(ctx_b)
            fixed_path.unlink(missing_ok=True)
    finally:
        await cleanup_connection(ctx_a)


async def run_upside(agent_model: str, trials: int) -> None:
    """UPSIDE STEP 1 + STEP 2: grounded fixture."""
    import agentgauge.ab_harness as ab
    from agentgauge.client import cleanup_connection, connect_stdio
    from agentgauge.fixer import run_fixer
    from agentgauge.providers import OllamaProvider
    from agentgauge.tasks import Task

    ab.assert_agent_ne_judge_ne_generator(agent_model)

    tasks = [Task(tool_name=tn, description=desc, sample_args={}) for tn, desc in _GROUNDED_TASKS]
    grounded_a = Path(__file__).parent.parent / "examples" / "grounded_server.py"
    grounded_oracle = Path(__file__).parent.parent / "examples" / "grounded_server_oracle.py"
    python = sys.executable

    # === UPSIDE STEP 1: Oracle descriptions vs empty descriptions ===
    print(f"\n=== UPSIDE STEP 1: grounded fixture + ORACLE descriptions ===")
    client_a, ctx_a = await connect_stdio(python, [str(grounded_a)])
    try:
        client_b_oracle, ctx_b_oracle = await connect_stdio(python, [str(grounded_oracle)])
        try:
            agent_a = OllamaProvider(agent_model)
            agent_b = OllamaProvider(agent_model)
            agent_noise = OllamaProvider(agent_model)

            print(
                f"Running paired A/B: agent={agent_model}, tasks={len(tasks)}, trials={trials}"
            )
            result_step1 = await ab.run_paired_ab(
                client_a,
                client_b_oracle,
                agent_a,
                agent_b,
                agent_noise,
                tasks=tasks,
                trials=trials,
            )

            valid1 = _print_result_table(
                "Tx UPSIDE STEP 1 — grounded + ORACLE vs empty descriptions",
                agent_model,
                result_step1,
                len(tasks),
            )

            upside_exists = valid1 and result_step1.selection_delta > 0
            if upside_exists:
                print(
                    f"\nUPSIDE STEP 1: POSITIVE (Oracle Arm B > Arm A on selection, "
                    f"delta={result_step1.selection_delta:+.1f}%)"
                )
                print("→ Proceeding to step 2 (fixer-generated descriptions).")
            elif not valid1:
                print(f"\nUPSIDE STEP 1: VOID (arm A saturated, run invalid)")
                print("→ Upside unestablished on this fixture/model.")
                return
            else:
                print(
                    f"\nUPSIDE STEP 1: NEGATIVE (Oracle could not beat Arm A, "
                    f"delta={result_step1.selection_delta:+.1f}%)"
                )
                print(
                    "→ GLOBAL ABSTAIN BRANCH: description_quality generation has no "
                    "selection upside for this agent. Correct behavior: abstain globally."
                )
                return

        finally:
            await cleanup_connection(ctx_b_oracle)
    finally:
        await cleanup_connection(ctx_a)

    # === UPSIDE STEP 2: Fixer-generated descriptions (only if step 1 positive) ===
    print(f"\n=== UPSIDE STEP 2: grounded fixture + FIXER-generated descriptions ===")
    client_a2, ctx_a2 = await connect_stdio(python, [str(grounded_a)])
    try:
        info_a = await client_a2.introspect()

        generator = OllamaProvider("qwen3:8b")
        judge = OllamaProvider("llama3.1:8b")

        print("Running fixer on grounded fixture (qwen3:8b generator, llama3.1:8b judge)...")
        fix_report = await run_fixer(
            info_a.tools,
            generator,
            judge,
            grounded_a,
            dims=["description_quality"],
        )

        print(
            f"Fixer result: accepted={len(fix_report.accepted)}, "
            f"rejected={len(fix_report.rejected)}, "
            f"abstained={len(fix_report.abstained)}"
        )
        if fix_report.abstained:
            print(
                f"WARNING: Abstain fired on {len(fix_report.abstained)} grounded tool(s)!"
            )
            for entry in fix_report.abstained:
                print(f"  ABSTAINED: {entry}")
        for c in fix_report.accepted:
            print(f"  ACCEPTED: {c.tool_name} — {c.new_description[:80]!r}")

        if not fix_report.patched_source:
            print("WARNING: No fixer changes — arm B = arm A (null result expected)")
            patched = grounded_a.read_text(encoding="utf-8")
        else:
            patched = fix_report.patched_source

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            prefix="grounded_tx_fixed_",
            encoding="utf-8",
        ) as f:
            f.write(patched)
            fixed_path = Path(f.name)

        client_b2, ctx_b2 = await connect_stdio(python, [str(fixed_path)])
        try:
            agent_a2 = OllamaProvider(agent_model)
            agent_b2 = OllamaProvider(agent_model)
            agent_noise2 = OllamaProvider(agent_model)

            result_step2 = await ab.run_paired_ab(
                client_a2,
                client_b2,
                agent_a2,
                agent_b2,
                agent_noise2,
                tasks=tasks,
                trials=trials,
            )

            valid2 = _print_result_table(
                "Tx UPSIDE STEP 2 — grounded + FIXER output vs empty descriptions",
                agent_model,
                result_step2,
                len(tasks),
            )

            if result_step2.selection_delta > 0 and valid2:
                print(
                    f"\nUPSIDE STEP 2: POSITIVE (Fixer Arm B > Arm A, "
                    f"delta={result_step2.selection_delta:+.1f}%). "
                    f"Abstain did not fire; value preserved."
                )
            else:
                print(
                    f"\nUPSIDE STEP 2: NEGATIVE or VOID "
                    f"(delta={result_step2.selection_delta:+.1f}%). "
                    "Fixer failed to preserve upside found in step 1."
                )

        finally:
            await cleanup_connection(ctx_b2)
            fixed_path.unlink(missing_ok=True)

    finally:
        await cleanup_connection(ctx_a2)


async def run(agent_model: str, trials: int, step: str) -> None:
    """Run the Tx experiment for the specified step(s)."""
    import agentgauge.ab_harness as ab

    ab.assert_agent_ne_judge_ne_generator(agent_model)

    if step in ("harm", "all"):
        await run_harm_gate(agent_model, trials)
    if step in ("upside", "all"):
        await run_upside(agent_model, trials)


def main() -> None:
    """Entry point for the Tx experiment runner."""
    parser = argparse.ArgumentParser(description="Run Tx A/B experiment (harm gate + upside)")
    parser.add_argument("--agent-model", default="gemma2:9b")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument(
        "--step",
        choices=["harm", "upside", "all"],
        default="all",
        help="Which sub-experiment to run",
    )
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials, args.step))


if __name__ == "__main__":
    main()
