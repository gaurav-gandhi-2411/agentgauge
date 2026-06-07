#!/usr/bin/env python3
"""Q2b three-arm catalog-aware fixer recovery experiment.

Three arms on selection_accuracy:
  Arm A — empty descriptions (vague server, agent relies on names alone)
  Arm F — Q2b catalog-aware fixer descriptions (qwen3:8b with neighbor context)
  Arm O — oracle discriminating descriptions (T18 Arm B)

Metric: parse-success selection_accuracy on contested tasks (Arm A accuracy == 0%).
Recovery fraction = (F - A) / (O - A).

Usage:
    python scripts/run_q2b_three_arm.py [--agent-model gemma2:9b] [--trials 5]

Prerequisites:
    Phase 1 must be completed first:
        python scripts/generate_arm_f_descriptions_q2b.py
    evals/fixtures/t18_arm_f_q2b_descriptions.json must be non-empty.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.ab_harness import assert_agent_ne_judge_ne_generator
from agentgauge.client import cleanup_connection, connect_stdio
from agentgauge.providers import OllamaProvider
from agentgauge.q2a_harness import (
    _sign_test,
    compute_recovery_fraction,
    identify_contested_indices,
    load_arm_f_descriptions,
    parse_failed_count,
    parse_success_accuracy,
)
from agentgauge.runner import _build_tool_listing, run_tasks
from evals.fixtures.t18_catalog import ARM_B_DESCRIPTIONS, FAMILY_MAP, FAMILIES, TASKS

_FIXTURE_A = Path(__file__).parent.parent / "examples" / "t18_vague_server.py"
_FIXTURE_F = Path(__file__).parent.parent / "examples" / "t18_q2b_server.py"
_FIXTURE_O = Path(__file__).parent.parent / "examples" / "t18_oracle_server.py"
_ARM_F_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "t18_arm_f_q2b_descriptions.json"
)
_CONTAMINATION_FILE = Path(__file__).parent.parent / "Q2B_CONTAMINATED.txt"

# Verdict thresholds
_THRESHOLD_HIGH = 0.70
_THRESHOLD_LOW = 0.30

# No-fabrication control: genuinely ambiguous tool pairs (same family, indistinct on evidence)
_AMBIGUOUS_TOOLS = {"find_entries", "lookup_data", "book_slot", "plan_event"}


def _check_ollama_foreign_models(agent_family: str) -> list[str]:
    """Check for non-agent-family models loaded in Ollama GPU memory."""
    try:
        result = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().splitlines()
        foreign: list[str] = []
        for line in lines[1:]:
            parts = line.split()
            if not parts:
                continue
            model_name = parts[0]
            if agent_family.lower() not in model_name.lower():
                foreign.append(model_name)
        return foreign
    except Exception:
        return []


async def run(agent_model: str, trials: int) -> None:
    assert_agent_ne_judge_ne_generator(agent_model)

    agent_family = agent_model.split(":")[0].lower()

    # ── Phase 1 pre-check ─────────────────────────────────────────────────────
    arm_f_descriptions = load_arm_f_descriptions(_ARM_F_PATH)
    if not arm_f_descriptions:
        print("ERROR: evals/fixtures/t18_arm_f_q2b_descriptions.json is empty or missing.")
        print("Run Phase 1 first:")
        print("    python scripts/generate_arm_f_descriptions_q2b.py")
        sys.exit(1)

    print("=" * 80)
    print("Q2b Three-Arm Catalog-Aware Fixer Recovery Experiment")
    print(f"Agent: {agent_model}  |  Trials: {trials}")
    print(f"Tasks (pre-registered): {len(TASKS)}  |  Tools: 60  |  Families: 10")
    print(f"Arm F (Q2b) descriptions loaded: {len(arm_f_descriptions)}")
    print("=" * 80)

    python = sys.executable
    valid_tool_names: set[str] = {name for names in FAMILIES.values() for name in names}

    print("\n[STEP 1] Connecting to all three arms...")
    client_a, ctx_a = await connect_stdio(python, [str(_FIXTURE_A)])
    client_f, ctx_f = await connect_stdio(python, [str(_FIXTURE_F)])
    client_o, ctx_o = await connect_stdio(python, [str(_FIXTURE_O)])

    try:
        # ── Manipulation check ─────────────────────────────────────────────────
        info_a = await client_a.introspect()
        info_f = await client_f.introspect()
        info_o = await client_o.introspect()

        listing_a = _build_tool_listing(info_a.tools)
        listing_f = _build_tool_listing(info_f.tools)
        listing_o = _build_tool_listing(info_o.tools)

        manip_af = listing_a != listing_f
        manip_ao = listing_a != listing_o

        print(
            f"[PRE-CHECK] Manipulation check A vs F: "
            f"{'PASS — prompts differ' if manip_af else 'WARN — prompts identical (Arm F = empty?)'}"
        )
        print(
            f"[PRE-CHECK] Manipulation check A vs O: "
            f"{'PASS — prompts differ' if manip_ao else 'FAIL — Arm O identical to Arm A!'}"
        )
        if not manip_ao:
            print("ABORT: Arm O manipulation check failed.")
            return

        # ── GPU watchdog pre-run ───────────────────────────────────────────────
        foreign_pre = _check_ollama_foreign_models(agent_family)
        if foreign_pre:
            msg = (
                f"GPU CONTAMINATION DETECTED before run: foreign models = {foreign_pre}\n"
                f"Agent family: {agent_family}\n"
                "Unload non-agent models before running Q2b.\n"
            )
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print(f"[PRE-CHECK] GPU watchdog: no foreign models (agent family: {agent_family})")

        # ── Run Arm A ─────────────────────────────────────────────────────────
        print(f"\n[STEP 2] Running Arm A ({len(TASKS)} tasks × {trials} trials)...")
        agent_a = OllamaProvider(agent_model)
        results_a = await run_tasks(TASKS, client_a, agent_a, trials=trials)

        foreign_after_a = _check_ollama_foreign_models(agent_family)
        if foreign_after_a:
            msg = f"GPU CONTAMINATION after Arm A: foreign models = {foreign_after_a}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm A complete. GPU watchdog: clean")

        # ── Run Arm F ─────────────────────────────────────────────────────────
        print(f"\n[STEP 3] Running Arm F Q2b ({len(TASKS)} tasks × {trials} trials)...")
        agent_f = OllamaProvider(agent_model)
        results_f = await run_tasks(TASKS, client_f, agent_f, trials=trials)

        foreign_after_f = _check_ollama_foreign_models(agent_family)
        if foreign_after_f:
            msg = f"GPU CONTAMINATION after Arm F: foreign models = {foreign_after_f}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm F complete. GPU watchdog: clean")

        # ── Run Arm O ─────────────────────────────────────────────────────────
        print(f"\n[STEP 4] Running Arm O ({len(TASKS)} tasks × {trials} trials)...")
        agent_o = OllamaProvider(agent_model)
        results_o = await run_tasks(TASKS, client_o, agent_o, trials=trials)

        foreign_after_o = _check_ollama_foreign_models(agent_family)
        if foreign_after_o:
            msg = f"GPU CONTAMINATION after Arm O: foreign models = {foreign_after_o}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm O complete. GPU watchdog: clean")

    finally:
        await cleanup_connection(ctx_a)
        await cleanup_connection(ctx_f)
        await cleanup_connection(ctx_o)

    # ── Section A: GPU + parse_failed diagnostics ──────────────────────────────
    pf_a = parse_failed_count(results_a, valid_tool_names)
    pf_f = parse_failed_count(results_f, valid_tool_names)
    pf_o = parse_failed_count(results_o, valid_tool_names)
    total = len(results_a)

    print("\n" + "=" * 80)
    print("SECTION A — GPU exclusivity + parse-failed diagnostics")
    print("=" * 80)
    print(f"  Arm A: {pf_a}/{total} parse-failed ({100 * pf_a / total if total else 0:.1f}%)")
    print(f"  Arm F (Q2b): {pf_f}/{total} parse-failed ({100 * pf_f / total if total else 0:.1f}%)")
    print(f"  Arm O: {pf_o}/{total} parse-failed ({100 * pf_o / total if total else 0:.1f}%)")

    # ── Contested tasks ────────────────────────────────────────────────────────
    contested = identify_contested_indices(results_a, TASKS, trials, valid_tool_names)
    n_contested = len(contested)
    print(f"\n  Contested tasks (Arm A parse-success accuracy == 0%): {n_contested}/{len(TASKS)}")

    if n_contested == 0:
        print("\nABORT: No contested tasks — Arm A saturated. Check fixture integrity.")
        return

    # ── Section B: Three-arm table + recovery + sign tests ────────────────────
    acc_a = parse_success_accuracy(results_a, TASKS, trials, valid_tool_names, contested)
    acc_f = parse_success_accuracy(results_f, TASKS, trials, valid_tool_names, contested)
    acc_o = parse_success_accuracy(results_o, TASKS, trials, valid_tool_names, contested)

    recovery = compute_recovery_fraction(acc_f, acc_a, acc_o)

    task_accs_a = [
        parse_success_accuracy(results_a, TASKS, trials, valid_tool_names, [i]) for i in contested
    ]
    task_accs_f = [
        parse_success_accuracy(results_f, TASKS, trials, valid_tool_names, [i]) for i in contested
    ]
    task_accs_o = [
        parse_success_accuracy(results_o, TASKS, trials, valid_tool_names, [i]) for i in contested
    ]

    deltas_fa = [f - a for f, a in zip(task_accs_f, task_accs_a, strict=True)]
    deltas_oa = [o - a for o, a in zip(task_accs_o, task_accs_a, strict=True)]
    deltas_fo = [f - o for f, o in zip(task_accs_f, task_accs_o, strict=True)]

    n_plus_fa, n_minus_fa, p_fa = _sign_test(deltas_fa)
    n_plus_oa, n_minus_oa, p_oa = _sign_test(deltas_oa)
    n_plus_fo, n_minus_fo, p_fo = _sign_test(deltas_fo)

    print("\n" + "=" * 80)
    print("SECTION B — Three-arm result table (parse-success, contested tasks only)")
    print("=" * 80)
    print(
        f"{'Family':<16} {'Task (truncated)':<50} {'A%':>5} {'F%':>5} {'O%':>5} "
        f"{'F-A':>6} {'O-A':>6}"
    )
    print("-" * 95)
    for idx_in_contested, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        family = FAMILY_MAP[task.tool_name]
        a_pct = task_accs_a[idx_in_contested] * 100
        f_pct = task_accs_f[idx_in_contested] * 100
        o_pct = task_accs_o[idx_in_contested] * 100
        delta_fa = deltas_fa[idx_in_contested] * 100
        delta_oa = deltas_oa[idx_in_contested] * 100
        desc = task.description[:48] + ".." if len(task.description) > 50 else task.description
        print(
            f"{family:<16} {desc:<50} {a_pct:>4.0f}% {f_pct:>4.0f}% {o_pct:>4.0f}% "
            f"{delta_fa:>+5.0f}% {delta_oa:>+5.0f}%"
        )
    print("-" * 95)
    print(
        f"{'AGGREGATE':<16} {'(parse-success contested tasks)':<50} "
        f"{acc_a * 100:>4.1f}% {acc_f * 100:>4.1f}% {acc_o * 100:>4.1f}% "
        f"{(acc_f - acc_a) * 100:>+5.1f}% {(acc_o - acc_a) * 100:>+5.1f}%"
    )
    print("=" * 95)

    print(f"\n  Recovery fraction (F-A)/(O-A): ", end="")
    if recovery is None:
        print("N/A (O == A, no headroom)")
    else:
        print(f"{recovery:.3f}  ({recovery * 100:.1f}%)")

    print(f"\n  Sign test F vs A: n+={n_plus_fa} n-={n_minus_fa}  p={p_fa:.4f}")
    print(f"  Sign test O vs A: n+={n_plus_oa} n-={n_minus_oa}  p={p_oa:.4f}")
    print(f"  Sign test F vs O: n+={n_plus_fo} n-={n_minus_fo}  p={p_fo:.4f}")

    # ── Section C: No-fabrication control ────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION C — NO-FABRICATION control (genuinely ambiguous tool pairs)")
    print("=" * 80)
    print(
        "Ambiguous pairs: find_entries/lookup_data (search family), book_slot/plan_event (schedule family)\n"
        "Classification: FAITHFUL = plain description; FABRICATED = asserts invented distinction\n"
    )

    for tool_name in sorted(_AMBIGUOUS_TOOLS):
        q2b_desc = arm_f_descriptions.get(tool_name, "(no Q2b description)")
        oracle_desc = ARM_B_DESCRIPTIONS.get(tool_name, "(no oracle description)")
        family = FAMILY_MAP.get(tool_name, "?")
        print(f"  [{family}] {tool_name}")
        print(f"    Q2b desc:    {q2b_desc}")
        print(f"    Oracle desc: {oracle_desc}")
        print(f"    Classification: [ ] FAITHFUL  [ ] FABRICATED")
        print()

    print(
        f"  => Manual review required. Mark each FAITHFUL or FABRICATED above.\n"
        f"     ANY FABRICATED = overall FAIL regardless of recovery fraction."
    )

    # ── Section D: Per-task diagnosis ─────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION D — Per-task diagnosis (contested tasks where Arm F < Arm O)")
    print("=" * 80)

    any_miss = False
    for idx_in_contested, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        f_pct = task_accs_f[idx_in_contested] * 100
        o_pct = task_accs_o[idx_in_contested] * 100
        if f_pct >= o_pct:
            continue
        any_miss = True
        family = FAMILY_MAP[task.tool_name]
        arm_f_desc = arm_f_descriptions.get(task.tool_name, "(no Q2b description)")
        arm_o_desc = ARM_B_DESCRIPTIONS.get(task.tool_name, "(no oracle description)")

        print(f"  Task [{family}]: {task.description}")
        print(f"    Gold tool:      {task.tool_name}")
        print(f"    Q2b desc:       {arm_f_desc}")
        print(f"    Oracle desc:    {arm_o_desc}")
        print(f"    F%={f_pct:.0f}%  O%={o_pct:.0f}%  gap={o_pct - f_pct:.0f}pp")
        print(f"    Does Q2b encode the real distinction? [ ] YES  [ ] NO — why:")
        print()

    if not any_miss:
        print("  All contested tasks: Arm F >= Arm O — catalog-aware fixer fully recovered oracle.")

    # ── Section E: Verdict ─────────────────────────────────────────────────────
    print("=" * 80)
    print("SECTION E — Verdict")
    print("=" * 80)

    if recovery is None:
        verdict = "ABORT"
        explanation = "Recovery fraction undefined (O == A). Oracle provides no headroom."
    elif recovery >= _THRESHOLD_HIGH:
        verdict = "HIGH RECOVERY"
        explanation = (
            f"Recovery fraction {recovery:.3f} >= {_THRESHOLD_HIGH}. "
            "Catalog-aware fixer recovers most of the oracle gain."
        )
    elif recovery <= _THRESHOLD_LOW:
        verdict = "LOW RECOVERY"
        explanation = (
            f"Recovery fraction {recovery:.3f} <= {_THRESHOLD_LOW}. "
            "Neighbor context insufficient or selection too weak — see Section D."
        )
    else:
        verdict = "PARTIAL RECOVERY"
        explanation = (
            f"Recovery fraction {recovery:.3f} between {_THRESHOLD_LOW} and {_THRESHOLD_HIGH}. "
            "Mixed result — see Section D for per-task diagnosis."
        )

    no_fab_verdict = "PENDING MANUAL REVIEW"
    print(f"\n  Recovery verdict: {verdict}")
    print(f"  {explanation}")
    print(f"\n  No-fabrication control: {no_fab_verdict}")
    print(
        "  (Fill in FAITHFUL/FABRICATED in Section C above before recording final verdict)\n"
    )
    print(
        f"  Arm A (empty):      {acc_a * 100:.1f}%  (parse-success, {n_contested} contested tasks)"
    )
    print(f"  Arm F (Q2b):        {acc_f * 100:.1f}%  (+{(acc_f - acc_a) * 100:.1f}pp vs A)")
    print(f"  Arm O (oracle):     {acc_o * 100:.1f}%  (+{(acc_o - acc_a) * 100:.1f}pp vs A)")
    if recovery is not None:
        print(f"  Recovery:           {recovery * 100:.1f}%  of oracle headroom")
    print(
        f"\n  Sign test F vs A: p={p_fa:.4f}  "
        f"({'significant' if p_fa < 0.05 else 'not significant'})"
    )
    print(
        f"  Sign test O vs A: p={p_oa:.4f}  "
        f"({'significant' if p_oa < 0.05 else 'not significant'})"
    )
    print(
        "\n  OVERALL VERDICT RULES:"
        "\n    RECOVERS + FAITHFUL → catalog-awareness delivers T18 value safely"
        "\n    RECOVERS but FABRICATES → unsafe; grounding guard needs strengthening"
        "\n    LOW recovery → neighbor context insufficient; report why in Section D"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Q2b three-arm catalog-aware fixer recovery experiment")
    parser.add_argument(
        "--agent-model",
        default="gemma2:9b",
        help="Agent model (must be != llama3.1 and != qwen3 families)",
    )
    parser.add_argument("--trials", type=int, default=5, help="Trials per arm per task")
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials))


if __name__ == "__main__":
    main()
