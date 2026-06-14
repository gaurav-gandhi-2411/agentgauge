#!/usr/bin/env python3
"""P2-A Phase 2 — A/B experiment: Arm A (thin internal descriptions) vs Arm GuardB vs Arm Oracle.

Measures selection accuracy on confusable synthetic internal-proxy MCP tasks.
Three arms:
  A      — thin accurate-but-non-distinguishing one-line descriptions (baseline)
  GuardB — Guard-B descriptions generated from mirror source docstrings (Phase 1)
  O      — oracle descriptions (derived from mirror handler docstrings, ceiling)

Key metrics:
  1. HEADROOM gate (85%): does Arm A (thin docs) miss contested tasks?
     If Arm A overall accuracy >= 85%, stop — no headroom to recover.
  2. IMPROVEMENT: GuardB accuracy vs Arm A on contested tasks (sign test).
  3. DO-NO-HARM: GuardB must not regress on thorough-tool control set.
  4. PER-FAMILY BREAKDOWN: per-family A and GuardB accuracy on contested tasks.

GPU EXCLUSIVITY:
  Run AFTER ollama stop (Phase 1 must be complete and Ollama cleared).
  Watchdog kills run if any non-agent-family model loads.

Usage:
    python scripts/p2a_phase2_ab.py [--agent-model gemma2:9b] [--trials 3] [--step1-only]

Prerequisites:
  - evals/fixtures/p2a_arm_guardb_descriptions.json exists (Phase 1 complete)
  - ollama stop, then ollama ps (must be empty)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.ab_harness import assert_agent_ne_judge_ne_generator  # noqa: E402
from agentgauge.client import cleanup_connection, connect_stdio  # noqa: E402
from agentgauge.providers import OllamaProvider  # noqa: E402
from agentgauge.q2a_harness import (  # noqa: E402
    _sign_test,
    compute_recovery_fraction,
    identify_contested_indices,
    parse_failed_count,
    parse_success_accuracy,
)
from agentgauge.runner import _build_tool_listing, run_tasks  # noqa: E402
from evals.fixtures.p2a_internal_proxy_catalog import (  # noqa: E402
    ARM_O_DESCRIPTIONS,
    CONTESTED_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    TASKS,
    THOROUGH_TOOLS,
)

_FIXTURE_A = Path(__file__).parent.parent / "examples" / "p2a_arm_a.py"
_FIXTURE_GUARDB = Path(__file__).parent.parent / "examples" / "p2a_arm_guardb.py"
_FIXTURE_O = Path(__file__).parent.parent / "examples" / "p2a_arm_oracle.py"

_GUARDB_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "p2a_arm_guardb_descriptions.json"
)
_CONTAMINATION_FILE = Path(__file__).parent.parent / "P2A_CONTAMINATED.txt"

# 85% headroom gate: if Arm A overall accuracy meets or exceeds this, stop.
_HEADROOM_GATE = 0.85

_VALID_TOOL_NAMES: set[str] = {t for names in FAMILIES.values() for t in names}


def _check_foreign_models(agent_family: str) -> list[str]:
    """Check Ollama for non-agent model families currently loaded in GPU memory."""
    try:
        result = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().splitlines()
        foreign = []
        for line in lines[1:]:
            parts = line.split()
            if parts and agent_family.lower() not in parts[0].lower():
                foreign.append(parts[0])
        return foreign
    except Exception:
        return []


def _contested_task_indices() -> list[int]:
    """Return TASKS indices whose gold tool is in CONTESTED_TOOLS."""
    return [i for i, task in enumerate(TASKS) if task.tool_name in CONTESTED_TOOLS]


def _thorough_task_indices() -> list[int]:
    """Return TASKS indices whose gold tool is in THOROUGH_TOOLS."""
    return [i for i, task in enumerate(TASKS) if task.tool_name in THOROUGH_TOOLS]


async def run(agent_model: str, trials: int, step1_only: bool = False) -> None:
    """Run the P2-A Phase 2 A/B experiment."""
    assert_agent_ne_judge_ne_generator(agent_model)
    agent_family = agent_model.split(":")[0].lower()

    # Pre-check: Guard-B descriptions must exist (Phase 1 must be complete) — skip for headroom gate
    guardb_descs: dict[str, str] = {}
    if not step1_only:
        if not _GUARDB_PATH.exists():
            print(f"ERROR: {_GUARDB_PATH.name} not found.")
            print("Run Phase 1 first: python scripts/p2a_phase1_generate.py")
            sys.exit(1)
        guardb_descs = json.loads(_GUARDB_PATH.read_text(encoding="utf-8"))
        if not guardb_descs:
            print(f"ERROR: {_GUARDB_PATH.name} is empty. Phase 1 did not complete successfully.")
            sys.exit(1)

    n_tools = len(_VALID_TOOL_NAMES)
    n_contested_pre = len(_contested_task_indices())
    n_thorough_pre = len(_thorough_task_indices())

    print("=" * 80)
    print("P2-A Phase 2 — A/B: Thin internal descriptions vs Guard-B vs Oracle")
    print(
        f"Agent: {agent_model}  |  Trials: {trials}  |  Tasks: {len(TASKS)}  |  Tools: {n_tools}"
    )
    guardb_label = f"{len(guardb_descs)}/{n_tools} tools" if guardb_descs else "not loaded (step1-only)"
    print(
        f"Guard-B descriptions: {guardb_label}  |  "
        f"Contested tasks: {n_contested_pre}  |  Thorough tasks: {n_thorough_pre}"
    )
    print("=" * 80)

    python = sys.executable

    # GPU pre-check
    foreign_pre = _check_foreign_models(agent_family)
    if foreign_pre:
        msg = (
            f"GPU CONTAMINATION before run: {foreign_pre}\n"
            f"Agent family: {agent_family}\n"
            "Run 'ollama stop', verify 'ollama ps' is empty, then retry.\n"
        )
        _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
        print(f"\nABORT: {msg}")
        return
    print(f"[PRE-CHECK] GPU watchdog: clean (agent family: {agent_family})")

    # ── STEP 1: Connect and run Arm A only (headroom gate) ────────────────────
    print("\n[STEP 1] Connecting to Arm A server for headroom gate...")
    client_a, ctx_a = await connect_stdio(python, [str(_FIXTURE_A)])

    try:
        results_a = await run_tasks(TASKS, client_a, OllamaProvider(agent_model), trials=trials)
    finally:
        try:  # noqa: SIM105
            await cleanup_connection(ctx_a)
        except BaseException:
            pass

    foreign = _check_foreign_models(agent_family)
    if foreign:
        msg = f"GPU CONTAMINATION after Arm A: {foreign}\n"
        _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
        print(f"\nABORT: {msg}")
        return
    print("  Arm A done. GPU watchdog: clean")

    # Headroom gate: evaluate Arm A accuracy (overall all tasks; see spec for contested-set intent)
    overall_a_acc = parse_success_accuracy(
        results_a, TASKS, trials, _VALID_TOOL_NAMES, list(range(len(TASKS)))
    )
    contested_a_acc = parse_success_accuracy(
        results_a, TASKS, trials, _VALID_TOOL_NAMES, _contested_task_indices()
    )
    thorough_a_acc = parse_success_accuracy(
        results_a, TASKS, trials, _VALID_TOOL_NAMES, _thorough_task_indices()
    )

    print("\n" + "=" * 80)
    print("STEP 1 — HEADROOM GATE")
    print("=" * 80)
    print(
        f"  Arm A overall accuracy (all {len(TASKS)} tasks):   {overall_a_acc * 100:.1f}%"
    )
    print(
        f"  Arm A contested accuracy ({len(_contested_task_indices())} tasks): {contested_a_acc * 100:.1f}%"
    )
    print(
        f"  Arm A thorough accuracy  ({len(_thorough_task_indices())} tasks): {thorough_a_acc * 100:.1f}%"
    )
    print(f"  Headroom gate threshold: {_HEADROOM_GATE * 100:.0f}% (applied to overall accuracy)")

    if overall_a_acc >= _HEADROOM_GATE:
        print(
            f"\n  NO HEADROOM: Arm A (thin internal descriptions) achieves "
            f"{overall_a_acc * 100:.1f}% >= {_HEADROOM_GATE * 100:.0f}%.\n"
            "  Guard-B has little to recover — thin descriptions already sufficient\n"
            "  for this agent on this task set. The P2-A effect may not exist\n"
            "  at this accuracy level. Investigate task difficulty or agent model."
        )
        return

    print(
        f"\n  -> HEADROOM CONFIRMED (Arm A = {overall_a_acc * 100:.1f}% < "
        f"{_HEADROOM_GATE * 100:.0f}%)"
    )

    if step1_only:
        print("\n[STEP-1-ONLY] Headroom exists, but --step1-only set: STOPPING before STEP 2.")
        print("  STEP 2 (full A/B matrix) requires a separate go-ahead.")
        return

    print("  Proceeding to STEP 2 (full A/B matrix).")

    # ── STEP 2: Full A vs GuardB vs Oracle matrix ─────────────────────────────
    print("\n[STEP 2] Connecting to GuardB and Oracle arm servers...")
    client_g, ctx_g = await connect_stdio(python, [str(_FIXTURE_GUARDB)])
    client_o, ctx_o = await connect_stdio(python, [str(_FIXTURE_O)])

    try:
        info_a_step2, ctx_a2 = await connect_stdio(python, [str(_FIXTURE_A)])
        try:
            info_check_a = await info_a_step2.introspect()
        finally:
            await cleanup_connection(ctx_a2)

        info_g_check = await client_g.introspect()
        info_o_check = await client_o.introspect()

        listing_a = _build_tool_listing(info_check_a.tools)
        listing_g = _build_tool_listing(info_g_check.tools)
        listing_o = _build_tool_listing(info_o_check.tools)

        manip_g = listing_a != listing_g
        manip_o = listing_a != listing_o

        print(
            f"[PRE-CHECK] Manipulation A vs GuardB: "
            f"{'PASS' if manip_g else 'WARN — GuardB identical to Arm A (Phase 1 not run?)'}"
        )
        print(
            f"[PRE-CHECK] Manipulation A vs Oracle: "
            f"{'PASS' if manip_o else 'FAIL — Oracle identical to Arm A!'}"
        )
        if not manip_o:
            print("ABORT: Oracle manipulation check failed.")
            return

        print(f"\n[RUN] Arm GuardB ({len(TASKS)} tasks × {trials} trials)...")
        results_g = await run_tasks(TASKS, client_g, OllamaProvider(agent_model), trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm GuardB: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm GuardB done. GPU watchdog: clean")

        print(f"\n[RUN] Arm Oracle ({len(TASKS)} tasks × {trials} trials)...")
        results_o = await run_tasks(TASKS, client_o, OllamaProvider(agent_model), trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm Oracle: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm Oracle done. GPU watchdog: clean")

    finally:
        for ctx in [ctx_g, ctx_o]:
            try:  # noqa: SIM105
                await cleanup_connection(ctx)
            except BaseException:
                pass

    total = len(results_a)

    # ── Section A: GPU + parse_failed ─────────────────────────────────────────
    pf_a = parse_failed_count(results_a, _VALID_TOOL_NAMES)
    pf_g = parse_failed_count(results_g, _VALID_TOOL_NAMES)
    pf_o = parse_failed_count(results_o, _VALID_TOOL_NAMES)

    print("\n" + "=" * 80)
    print("SECTION A — GPU exclusivity + parse-failed diagnostics")
    print("=" * 80)
    print("  GPU: confirmed exclusive (watchdog clean at each arm boundary)")
    print(f"  Arm A:       {pf_a}/{total} parse-failed ({100 * pf_a / total if total else 0:.1f}%)")
    print(f"  Arm GuardB:  {pf_g}/{total} parse-failed ({100 * pf_g / total if total else 0:.1f}%)")
    print(f"  Arm Oracle:  {pf_o}/{total} parse-failed ({100 * pf_o / total if total else 0:.1f}%)")

    # ── Section B: HEADROOM — Arm A on pre-registered contested tasks ─────────
    pre_contested_indices = _contested_task_indices()
    dyn_contested = identify_contested_indices(results_a, TASKS, trials, _VALID_TOOL_NAMES)

    contested_a_acc = parse_success_accuracy(
        results_a, TASKS, trials, _VALID_TOOL_NAMES, pre_contested_indices
    )

    print("\n" + "=" * 80)
    print("SECTION B — HEADROOM (Arm A accuracy on pre-registered contested task set)")
    print("=" * 80)
    print(
        "  Arm A uses thin accurate-but-non-distinguishing one-line descriptions.\n"
        "  These model the realistic under-documented internal state.\n"
        "  Headroom exists if thin docs FAIL on contested tasks.\n"
    )
    print(
        f"  Arm A overall accuracy (all {len(TASKS)} tasks):          "
        f"{overall_a_acc * 100:.1f}%"
    )
    print(
        f"  Arm A accuracy on {len(pre_contested_indices)} pre-registered contested tasks: "
        f"{contested_a_acc * 100:.1f}%"
    )
    print(
        f"  Dynamically contested tasks (Arm A parse-success == 0%): "
        f"{len(dyn_contested)}/{len(TASKS)}"
    )

    # Use pre-registered contested indices for main VALUE analysis
    eval_contested = pre_contested_indices if pre_contested_indices else dyn_contested

    # ── Section C: RECOVERY table ──────────────────────────────────────────────
    per_task_a = [
        parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in eval_contested
    ]
    per_task_g = [
        parse_success_accuracy(results_g, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in eval_contested
    ]
    per_task_o = [
        parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in eval_contested
    ]

    acc_a = parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, eval_contested)
    acc_g = parse_success_accuracy(results_g, TASKS, trials, _VALID_TOOL_NAMES, eval_contested)
    acc_o = parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, eval_contested)

    rec_g = compute_recovery_fraction(acc_g, acc_a, acc_o)

    deltas_g_a = [g - a for g, a in zip(per_task_g, per_task_a, strict=True)]
    deltas_o_a = [o - a for o, a in zip(per_task_o, per_task_a, strict=True)]

    n_plus_g, n_minus_g, p_g = _sign_test(deltas_g_a)
    n_plus_o, n_minus_o, p_o = _sign_test(deltas_o_a)

    print("\n" + "=" * 80)
    print("SECTION C — RECOVERY: three-arm table (parse-success, contested tasks)")
    print("=" * 80)
    print(f"{'Family':<26} {'Task (truncated)':<40} {'A%':>5} {'GB%':>5} {'O%':>5}")
    print("-" * 83)
    for idx_in_c, task_idx in enumerate(eval_contested):
        task = TASKS[task_idx]
        family = FAMILY_MAP.get(task.tool_name, "?")
        a_pct = per_task_a[idx_in_c] * 100
        g_pct = per_task_g[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        desc = task.description[:38] + ".." if len(task.description) > 40 else task.description
        print(f"{family:<26} {desc:<40} {a_pct:>4.0f}% {g_pct:>4.0f}% {o_pct:>4.0f}%")
    print("-" * 83)
    print(
        f"{'AGGREGATE':<26} {'(parse-success, ' + str(len(eval_contested)) + ' contested)':<40} "
        f"{acc_a * 100:>4.1f}% {acc_g * 100:>4.1f}% {acc_o * 100:>4.1f}%"
    )
    print("=" * 83)
    print("\n  Recovery (GuardB − A) / (O − A): ", end="")
    print(f"{rec_g:.3f}  ({rec_g * 100:.1f}%)" if rec_g is not None else "N/A")
    print(f"  Sign test GuardB vs A: n+={n_plus_g} n-={n_minus_g}  p={p_g:.4f}")
    print(f"  Sign test Oracle vs A: n+={n_plus_o} n-={n_minus_o}  p={p_o:.4f}")

    # ── Section D: PER-FAMILY accuracy breakdown ───────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION D — PER-FAMILY accuracy breakdown on contested tasks")
    print("=" * 80)
    print(f"{'Family':<26} {'Contested':>10} {'A%':>8} {'GB%':>8} {'Δ':>6}")
    print("-" * 65)
    for family_name, family_tools in FAMILIES.items():
        contested_in_family = [
            i for i, task in enumerate(TASKS)
            if task.tool_name in family_tools and task.tool_name in CONTESTED_TOOLS
        ]
        if not contested_in_family:
            continue
        fam_a = parse_success_accuracy(
            results_a, TASKS, trials, _VALID_TOOL_NAMES, contested_in_family
        )
        fam_g = parse_success_accuracy(
            results_g, TASKS, trials, _VALID_TOOL_NAMES, contested_in_family
        )
        delta = (fam_g - fam_a) * 100
        print(
            f"{family_name:<26} {len(contested_in_family):>10} "
            f"{fam_a * 100:>7.1f}% {fam_g * 100:>7.1f}% {delta:>+5.1f}pp"
        )
    print("=" * 65)

    # ── Section E: DO-NO-HARM (thorough-tool control set) ─────────────────────
    thorough_indices = _thorough_task_indices()

    per_thorough_a = [
        parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in thorough_indices
    ]
    per_thorough_g = [
        parse_success_accuracy(results_g, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in thorough_indices
    ]

    acc_thorough_a = parse_success_accuracy(
        results_a, TASKS, trials, _VALID_TOOL_NAMES, thorough_indices
    )
    acc_thorough_g = parse_success_accuracy(
        results_g, TASKS, trials, _VALID_TOOL_NAMES, thorough_indices
    )

    regressions = sum(
        1 for a_pct, g_pct in zip(per_thorough_a, per_thorough_g, strict=True) if g_pct < a_pct
    )

    print("\n" + "=" * 80)
    print("SECTION E — DO-NO-HARM: thorough-tool control set (Guard-B must not regress)")
    print("=" * 80)
    print(
        "  Tools with distinctive names or richer docstrings.\n"
        "  Guard-B must SKIP or PRESERVE them — zero regressions is the target.\n"
    )
    print(f"{'Tool':<30} {'A%':>5} {'GB%':>5} {'Δ':>6} {'Status':<10}")
    print("-" * 62)
    for idx_in_t, task_idx in enumerate(thorough_indices):
        task = TASKS[task_idx]
        a_pct = per_thorough_a[idx_in_t] * 100
        g_pct = per_thorough_g[idx_in_t] * 100
        delta = g_pct - a_pct
        status = "REGRESSION" if g_pct < a_pct else "ok"
        print(
            f"{task.tool_name:<30} {a_pct:>4.0f}% {g_pct:>4.0f}% "
            f"{delta:>+5.0f}pp {status:<10}"
        )
    print("-" * 62)
    print(
        f"{'AGGREGATE':<30} {acc_thorough_a * 100:>4.1f}% {acc_thorough_g * 100:>4.1f}% "
        f"{(acc_thorough_g - acc_thorough_a) * 100:>+5.1f}pp"
    )
    print("=" * 62)
    print(
        f"\n  Regressions on thorough-tool set: {regressions}/{len(thorough_indices)} "
        f"({'FAIL — investigate' if regressions > 0 else 'PASS — zero regressions'})"
    )

    # ── Section F: Per-task miss diagnosis ────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION F — Per-task miss diagnosis (GuardB < Oracle on contested tasks)")
    print("=" * 80)
    any_miss = False
    for idx_in_c, task_idx in enumerate(eval_contested):
        task = TASKS[task_idx]
        g_pct = per_task_g[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        if g_pct >= o_pct:
            continue
        any_miss = True
        family = FAMILY_MAP.get(task.tool_name, "?")
        arm_a_desc = f"(see ARM_A_DESCRIPTIONS['{task.tool_name}'])"
        guardb_desc = guardb_descs.get(task.tool_name, "(missing)")
        oracle_desc = ARM_O_DESCRIPTIONS.get(task.tool_name, "")
        print(f"  [{family}] Task: {task.description}")
        print(f"    Gold: {task.tool_name}")
        print(f"    Arm A (thin):   {arm_a_desc}")
        print(f"    GuardB:         {guardb_desc[:100]}")
        print(f"    Oracle:         {oracle_desc[:100]}")
        print(
            f"    A%={per_task_a[idx_in_c] * 100:.0f}%  "
            f"GuardB%={g_pct:.0f}%  O%={o_pct:.0f}%"
        )
        print("    Miss type: [ ] OVER-CONSTRAINED  [ ] ABSENT-FROM-BODY  [ ] TASK-AMBIGUOUS")
        print()
    if not any_miss:
        print("  All contested tasks: GuardB >= Oracle.")

    # ── Section G: Verdict ────────────────────────────────────────────────────
    print("=" * 80)
    print("SECTION G — Verdict")
    print("=" * 80)

    guardb_recovers = rec_g is not None and rec_g > 0.30
    no_harm = regressions == 0

    print(
        f"\n  Arm A (thin descriptions): {acc_a * 100:.1f}%  "
        f"({len(eval_contested)} contested tasks)"
    )
    if rec_g is not None:
        print(f"  GuardB:                    {acc_g * 100:.1f}%  recovery={rec_g * 100:.1f}%")
    else:
        print(f"  GuardB:                    {acc_g * 100:.1f}%  recovery=N/A")
    print(f"  Oracle (ceiling):          {acc_o * 100:.1f}%")
    print(
        f"  Sign test GuardB vs A:     p={p_g:.4f}  "
        f"({'significant' if p_g < 0.05 else 'not significant'})"
    )
    print(
        f"  Do-no-harm (thorough set): "
        f"{'PASS — zero regressions' if no_harm else f'FAIL — {regressions} regressions'}"
    )

    print()
    if guardb_recovers and no_harm:
        print(
            "  VERDICT: SCORE VALIDITY + FIX VALUE CONFIRMED\n"
            "  Thin internal descriptions have headroom. Guard-B recovers contested tasks\n"
            "  with zero do-no-harm regressions on the thorough-tool control set.\n"
            "  External validity + value confirmed for under-documented internal server."
        )
    elif guardb_recovers and not no_harm:
        print(
            "  VERDICT (do-no-harm FAILURE): Guard-B improved contested accuracy but introduced\n"
            f"  {regressions} regression(s) on thorough-tool set. Investigate before shipping."
        )
    elif not guardb_recovers and no_harm:
        print(
            "  VERDICT: FIX VALUE BOUNDED\n"
            "  Guard-B did not substantially recover contested accuracy (recovery <= 30%).\n"
            "  Zero do-no-harm regressions: safe to run, but minimal upside here.\n"
            "  Consider richer Phase 1 generation or a different agent model."
        )
    else:
        print("  VERDICT: INCONCLUSIVE — check per-task data, sign test, and do-no-harm.")

    print(
        f"\n  Note: All results are model-dependent (agent={agent_model}, generator=qwen3:8b).\n"
        "  Record agent model, judge model, and trial count alongside any stored scores."
    )


def main() -> None:
    """Entry point for P2-A Phase 2 A/B experiment."""
    parser = argparse.ArgumentParser(
        description="P2-A Phase 2: A/B experiment on synthetic internal-proxy MCP tools"
    )
    parser.add_argument("--agent-model", default="gemma2:9b")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument(
        "--step1-only",
        action="store_true",
        help="Run only STEP 1 (headroom gate) and stop before STEP 2, even if headroom exists.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials, args.step1_only))


if __name__ == "__main__":
    main()
