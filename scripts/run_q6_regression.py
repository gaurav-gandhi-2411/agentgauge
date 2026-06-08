#!/usr/bin/env python3
"""Q6 Phase 2 — do-no-harm regression experiment.

Two-arm A/B: Arm A (empty descriptions) vs Arm Guard-B (DOC-scoped + Guard B).
Full extended catalog: 23 tools (12 Q3 + 11 already-passing new tools).

METRICS (in order of report):
  A. GPU exclusivity + parse_failed (all arms, both stability runs).
  B. HEADROOM PRECONDITION (inverted gate): already-passing subset Arm A at/near 100%.
     Two stability runs of Arm A alone; tasks that flip >1 trial across runs are dropped.
     Flaky tasks: regression claim is void on them — report dropped count.
  C. REGRESSION (headline): Arm A vs Guard-B on stable already-passing subset.
     Count PASS→FAIL flips. ZERO = do-no-harm holds.
     Show EACH regression: Guard-B description + which sibling the agent flipped to.
  D. CONTESTED CHECK: Guard-B recovers the 6 structural contested tasks on the full catalog.
  E. NET EFFECT: aggregate Arm A vs Guard-B across ALL tasks (contested + already-passing).
     Net positive only if recovery gains are not cancelled by regressions.
  F. VERDICT: ZERO-regressions+recovery-preserved / regressions-on-collision-pairs / recovery-broke.

Usage:
    python scripts/run_q6_regression.py [--agent-model gemma2:9b] [--trials 5]

Prerequisites:
  - Phase 1 complete: evals/fixtures/q6_arm_f_doc_guarded_descriptions.json exists (non-empty)
  - ollama stop, then ollama ps (must be empty) before running
  - Watchdog kills run if any non-agent-family model loads
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

from agentgauge.ab_harness import assert_agent_ne_judge_ne_generator
from agentgauge.client import cleanup_connection, connect_stdio
from agentgauge.providers import OllamaProvider
from agentgauge.q2a_harness import (
    _sign_test,
    compute_recovery_fraction,
    parse_failed_count,
    parse_success_accuracy,
)
from agentgauge.runner import _build_tool_listing, run_tasks
from evals.fixtures.q6_catalog import (
    ALREADY_PASSING_TASK_INDICES,
    ALREADY_PASSING_TOOLS,
    ARM_O_DESCRIPTIONS,
    COLLISION_PAIR_DOCS,
    COLLISION_PRONE_PAIRS,
    FAMILIES,
    FAMILY_MAP,
    STRUCTURAL_CONTESTED_TASK_INDICES,
    TASKS,
)

_FIXTURE_A = Path(__file__).parent.parent / "examples" / "q6_arm_a.py"
_FIXTURE_GUARDED = Path(__file__).parent.parent / "examples" / "q6_arm_f_doc_guarded.py"
_ARM_GUARDED_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "q6_arm_f_doc_guarded_descriptions.json"
)
_CONTAMINATION_FILE = Path(__file__).parent.parent / "Q6_CONTAMINATED.txt"

_VALID_TOOL_NAMES: set[str] = {name for names in FAMILIES.values() for name in names}


def _check_foreign_models(agent_family: str) -> list[str]:
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


def _compute_per_task_accuracy(
    results: list,
    task_indices: list[int],
    trials: int,
) -> list[float]:
    """Return parse-success accuracy for each task index."""
    return [
        parse_success_accuracy(results, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in task_indices
    ]


def _find_regression_flips(
    per_task_a: list[float],
    per_task_b: list[float],
    task_indices: list[int],
    results_b: list,
    trials: int,
    arm_b_descriptions: dict[str, str],
) -> list[dict]:
    """Identify PASS->FAIL flips: Arm A >= threshold but Guard-B < threshold."""
    regressions = []
    pass_threshold = 0.6  # >= 60% in Arm A considered passing
    fail_threshold = 0.4  # < 40% in Guard-B considered failing

    for i, task_idx in enumerate(task_indices):
        a_acc = per_task_a[i]
        b_acc = per_task_b[i]
        if a_acc >= pass_threshold and b_acc < fail_threshold:
            task = TASKS[task_idx]
            guard_b_desc = arm_b_descriptions.get(task.tool_name, "(no description)")
            # Find which tool the agent flipped to (most common non-gold selection in Arm B)
            flipped_to: list[str] = []
            task_results = results_b[task_idx * trials : (task_idx + 1) * trials]
            for r in task_results:
                if hasattr(r, "selected_tool") and r.selected_tool != task.tool_name:
                    flipped_to.append(r.selected_tool or "parse_failed")
            from collections import Counter

            flip_counter = Counter(flipped_to)
            most_common_flip = flip_counter.most_common(1)[0][0] if flip_counter else "unknown"
            regressions.append(
                {
                    "task_idx": task_idx,
                    "tool": task.tool_name,
                    "task_desc": task.description,
                    "arm_a_acc": a_acc,
                    "arm_b_acc": b_acc,
                    "guard_b_description": guard_b_desc,
                    "flipped_to": most_common_flip,
                    "family": FAMILY_MAP.get(task.tool_name, "?"),
                }
            )
    return regressions


async def run(agent_model: str, trials: int) -> None:
    assert_agent_ne_judge_ne_generator(agent_model)

    agent_family = agent_model.split(":")[0].lower()

    # Phase 1 pre-check
    if not _ARM_GUARDED_PATH.exists():
        print("ERROR: q6_arm_f_doc_guarded_descriptions.json not found.")
        print("Run Phase 1 first: python scripts/generate_q6_descriptions.py")
        sys.exit(1)
    arm_guarded_raw = _ARM_GUARDED_PATH.read_text(encoding="utf-8")
    arm_guarded: dict[str, str] = json.loads(arm_guarded_raw)
    if not arm_guarded:
        print("ERROR: q6_arm_f_doc_guarded_descriptions.json is empty. Phase 1 incomplete.")
        sys.exit(1)

    print("=" * 80)
    print("Q6 Do-No-Harm Regression Experiment")
    print(f"Agent: {agent_model}  |  Trials: {trials}")
    print(f"Tasks (pre-registered): {len(TASKS)}  |  Tools: {len(_VALID_TOOL_NAMES)}")
    print(
        f"Already-passing tasks: {len(ALREADY_PASSING_TASK_INDICES)}  |  "
        f"Structural contested: {len(STRUCTURAL_CONTESTED_TASK_INDICES)}"
    )
    print(f"Collision-prone pairs: {len(COLLISION_PRONE_PAIRS)}")
    print(f"Guard-B descriptions loaded: {len(arm_guarded)}")
    print("=" * 80)

    python = sys.executable

    # GPU pre-check
    foreign_pre = _check_foreign_models(agent_family)
    if foreign_pre:
        msg = (
            f"GPU CONTAMINATION before run: foreign models = {foreign_pre}\n"
            f"Agent family: {agent_family}\n"
            "Run 'ollama stop' then verify 'ollama ps' is empty before Phase 2.\n"
        )
        _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
        print(f"\nABORT: {msg}")
        return
    print(f"[PRE-CHECK] GPU watchdog: clean (agent family: {agent_family})")

    print("\n[STEP 1] Connecting to both arms...")
    client_a1, ctx_a1 = await connect_stdio(python, [str(_FIXTURE_A)])
    client_a2, ctx_a2 = await connect_stdio(python, [str(_FIXTURE_A)])
    client_gb, ctx_gb = await connect_stdio(python, [str(_FIXTURE_GUARDED)])

    try:
        # Manipulation check
        info_a = await client_a1.introspect()
        info_gb = await client_gb.introspect()
        listing_a = _build_tool_listing(info_a.tools)
        listing_gb = _build_tool_listing(info_gb.tools)
        manip_gb = listing_a != listing_gb
        print(
            f"[PRE-CHECK] Manipulation A vs Guard-B: "
            f"{'PASS' if manip_gb else 'WARN — Guard-B identical to A (descriptions all empty?)'}"
        )

        # ── STABILITY RUN 1 (Arm A) ────────────────────────────────────────────
        print(f"\n[STABILITY RUN 1] Arm A — {len(TASKS)} tasks × {trials} trials...")
        agent_a1 = OllamaProvider(agent_model)
        results_a1 = await run_tasks(TASKS, client_a1, agent_a1, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Stability Run 1: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Stability Run 1 done. GPU watchdog: clean")

        # ── STABILITY RUN 2 (Arm A) ────────────────────────────────────────────
        print(f"\n[STABILITY RUN 2] Arm A — {len(TASKS)} tasks × {trials} trials...")
        agent_a2 = OllamaProvider(agent_model)
        results_a2 = await run_tasks(TASKS, client_a2, agent_a2, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Stability Run 2: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Stability Run 2 done. GPU watchdog: clean")

        # ── Guard-B RUN ────────────────────────────────────────────────────────
        print(f"\n[GUARD-B RUN] Arm Guard-B — {len(TASKS)} tasks × {trials} trials...")
        agent_gb = OllamaProvider(agent_model)
        results_gb = await run_tasks(TASKS, client_gb, agent_gb, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Guard-B run: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Guard-B run done. GPU watchdog: clean")

    finally:
        for ctx in [ctx_a1, ctx_a2, ctx_gb]:
            try:
                await cleanup_connection(ctx)
            except BaseException:
                pass

    total = len(results_a1)

    # ── SECTION A: GPU + parse_failed ──────────────────────────────────────────
    pf_a1 = parse_failed_count(results_a1, _VALID_TOOL_NAMES)
    pf_a2 = parse_failed_count(results_a2, _VALID_TOOL_NAMES)
    pf_gb = parse_failed_count(results_gb, _VALID_TOOL_NAMES)

    print("\n" + "=" * 80)
    print("SECTION A — GPU exclusivity + parse-failed diagnostics")
    print("=" * 80)
    print("  GPU: confirmed exclusive (agent-only; watchdog clean at each arm boundary)")
    print(f"  Arm A (run 1):     {pf_a1}/{total} parse-failed ({100 * pf_a1 / total:.1f}%)")
    print(f"  Arm A (run 2):     {pf_a2}/{total} parse-failed ({100 * pf_a2 / total:.1f}%)")
    print(f"  Arm Guard-B:       {pf_gb}/{total} parse-failed ({100 * pf_gb / total:.1f}%)")

    # ── SECTION B: HEADROOM PRECONDITION + STABILITY SCREEN ───────────────────
    print("\n" + "=" * 80)
    print("SECTION B — Headroom precondition (already-passing subset, Arm A stability screen)")
    print("=" * 80)
    print(
        "INVERTED GATE (vs all prior experiments):\n"
        "  For Q6, Arm A at/near 100% is the PRECONDITION — you can only test harm\n"
        "  where there was nothing to gain. Tasks NOT stably passing in Arm A are VOID\n"
        "  for regression claims (they weren't passing to begin with).\n"
        "  Stability screen: drop tasks that flip > 1 trial across Arm A run 1 vs run 2.\n"
    )

    ap_indices = ALREADY_PASSING_TASK_INDICES
    per_task_a1_ap = _compute_per_task_accuracy(results_a1, ap_indices, trials)
    per_task_a2_ap = _compute_per_task_accuracy(results_a2, ap_indices, trials)

    # Stability screen: drop tasks where Arm A flips > 1 trial across runs
    # A "flip" = |acc_run1 - acc_run2| > 1/trials
    flip_threshold = 1.0 / trials
    stable_ap_indices: list[int] = []
    dropped_ap_indices: list[int] = []
    for i, task_idx in enumerate(ap_indices):
        delta = abs(per_task_a1_ap[i] - per_task_a2_ap[i])
        if delta > flip_threshold:
            dropped_ap_indices.append(task_idx)
        else:
            stable_ap_indices.append(task_idx)

    print(f"  Already-passing tasks: {len(ap_indices)}")
    print(f"  Stable (kept):         {len(stable_ap_indices)}")
    print(f"  Flaky (dropped):       {len(dropped_ap_indices)}")
    if dropped_ap_indices:
        for task_idx in dropped_ap_indices:
            task = TASKS[task_idx]
            i = ap_indices.index(task_idx)
            print(
                f"    DROPPED: {task.tool_name} "
                f"(run1={per_task_a1_ap[i]:.0%} run2={per_task_a2_ap[i]:.0%})"
            )
        print("  NOTE: Regression claim is VOID on dropped tasks.")

    print("\n  Already-passing subset (stable) — Arm A per-task accuracy:")
    # Use average of two stability runs as headroom baseline
    stable_per_task_a_ap = []
    for task_idx in stable_ap_indices:
        i = ap_indices.index(task_idx)
        avg = (per_task_a1_ap[i] + per_task_a2_ap[i]) / 2
        stable_per_task_a_ap.append(avg)
        task = TASKS[task_idx]
        is_collision = any(task.tool_name in pair for pair in COLLISION_PRONE_PAIRS)
        label = "[COLLISION]" if is_collision else "[AP]"
        print(
            f"    {label} {task.tool_name}: run1={per_task_a1_ap[i]:.0%} run2={per_task_a2_ap[i]:.0%} avg={avg:.0%}"
        )

    if stable_per_task_a_ap:
        avg_stable_a = sum(stable_per_task_a_ap) / len(stable_per_task_a_ap)
        print(f"\n  HEADROOM PRECONDITION: stable already-passing Arm A = {avg_stable_a:.1%}")
        if avg_stable_a >= 0.80:
            print("  PRECONDITION: MET — already-passing tools are reliably passing in Arm A.")
        else:
            print(
                f"  PRECONDITION: NOT MET ({avg_stable_a:.1%} < 80%). "
                "The harm test is weakened — some 'already-passing' tools were not reliably passing."
            )
    else:
        print("  No stable already-passing tasks remaining after screen.")

    # ── SECTION C: REGRESSION ─────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION C — REGRESSION: Arm A vs Guard-B on stable already-passing subset")
    print("=" * 80)
    print("HEADLINE METRIC: count PASS->FAIL flips. ZERO = do-no-harm holds.\n")

    per_task_gb_ap = _compute_per_task_accuracy(results_gb, stable_ap_indices, trials)
    per_task_a_stable = [
        (per_task_a1_ap[ap_indices.index(idx)] + per_task_a2_ap[ap_indices.index(idx)]) / 2
        for idx in stable_ap_indices
    ]

    regressions = _find_regression_flips(
        per_task_a_stable,
        per_task_gb_ap,
        stable_ap_indices,
        results_gb,
        trials,
        arm_guarded,
    )

    print(f"  {'Task':<40} {'Family':<16} {'A%':>5} {'GuardB%':>8} {'Delta':>7} {'Status':>12}")
    print("-" * 92)
    for i, task_idx in enumerate(stable_ap_indices):
        task = TASKS[task_idx]
        a_acc = per_task_a_stable[i]
        b_acc = per_task_gb_ap[i]
        delta = b_acc - a_acc
        is_regression = any(r["task_idx"] == task_idx for r in regressions)
        status = "REGRESSION" if is_regression else "OK"
        family = FAMILY_MAP.get(task.tool_name, "?")
        desc = task.description[:38] + ".." if len(task.description) > 40 else task.description
        print(f"  {desc:<40} {family:<16} {a_acc:>4.0%} {b_acc:>7.0%} {delta:>+6.0%} {status:>12}")
    print("-" * 92)

    if regressions:
        n_reg = len(regressions)
        print(f"\n  REGRESSIONS: {n_reg} PASS->FAIL flip(s) detected\n")
        for reg in regressions:
            print(f"  [{reg['family']}] REGRESSION: {reg['tool']}")
            print(f"    Task:              {reg['task_desc']}")
            print(f"    Arm A accuracy:    {reg['arm_a_acc']:.0%}")
            print(f"    Guard-B accuracy:  {reg['arm_b_acc']:.0%}")
            print(f"    Guard-B desc:      {reg['guard_b_description']}")
            print(f"    Agent flipped to:  {reg['flipped_to']}")
            # Check if this is in a collision pair
            for pair in COLLISION_PRONE_PAIRS:
                if reg["tool"] in pair:
                    sibling = pair[0] if reg["tool"] == pair[1] else pair[1]
                    sibling_desc = arm_guarded.get(sibling, "(no description)")
                    print(f"    Sibling ({sibling}) Guard-B desc: {sibling_desc}")
                    break
            print()
        print("  => Guard-B introduced confusability on these collision-prone tools.")
        print("     Blanket use needs a collision check. Localise regressions above.")
    else:
        print("\n  REGRESSIONS: 0  — do-no-harm holds on stable already-passing subset.")

    # ── SECTION D: CONTESTED CHECK ────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION D — CONTESTED CHECK: Guard-B recovery on 6 structural contested tasks")
    print("=" * 80)
    print(
        "Guard-B must still recover the 6 Q3 structural contested tasks on the extended catalog.\n"
        "Recovery measured as (Guard-B - Arm A) / (Arm A ceiling distance).\n"
    )

    sc_indices = STRUCTURAL_CONTESTED_TASK_INDICES
    per_task_a1_sc = _compute_per_task_accuracy(results_a1, sc_indices, trials)
    per_task_gb_sc = _compute_per_task_accuracy(results_gb, sc_indices, trials)

    all_fully_recovered = True
    print(f"  {'Task':<40} {'Tool':<18} {'A%':>5} {'GuardB%':>9} {'Recovered':>10}")
    print("-" * 88)
    for i, task_idx in enumerate(sc_indices):
        task = TASKS[task_idx]
        a_acc = per_task_a1_sc[i]
        b_acc = per_task_gb_sc[i]
        recovered = b_acc >= 0.60
        if not recovered:
            all_fully_recovered = False
        status = "YES" if recovered else "NO"
        desc = task.description[:38] + ".." if len(task.description) > 40 else task.description
        print(f"  {desc:<40} {task.tool_name:<18} {a_acc:>4.0%} {b_acc:>8.0%} {status:>10}")
    print("-" * 88)

    acc_a_sc = sum(per_task_a1_sc) / len(per_task_a1_sc) if per_task_a1_sc else 0.0
    acc_gb_sc = sum(per_task_gb_sc) / len(per_task_gb_sc) if per_task_gb_sc else 0.0
    rec_sc = compute_recovery_fraction(acc_gb_sc, acc_a_sc, 1.0)
    print(f"\n  Contested aggregate: Arm A={acc_a_sc:.1%}  Guard-B={acc_gb_sc:.1%}")
    if rec_sc is not None:
        print(f"  Recovery fraction: {rec_sc:.3f} ({rec_sc:.1%})")
    n_plus, n_minus, p = _sign_test([b - a for b, a in zip(per_task_gb_sc, per_task_a1_sc)])
    print(f"  Sign test: n+={n_plus} n-={n_minus}  p={p:.4f}")
    print(
        f"\n  CONTESTED CHECK: {'PASS — Guard-B recovers structural contested tasks.' if all_fully_recovered else 'FAIL — Some structural contested tasks not recovered on extended catalog.'}"
    )

    # ── SECTION E: NET EFFECT ─────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION E — NET EFFECT: Arm A vs Guard-B across ALL tasks")
    print("=" * 80)

    all_indices = list(range(len(TASKS)))
    per_task_a1_all = _compute_per_task_accuracy(results_a1, all_indices, trials)
    per_task_gb_all = _compute_per_task_accuracy(results_gb, all_indices, trials)

    acc_a_all = sum(per_task_a1_all) / len(per_task_a1_all)
    acc_gb_all = sum(per_task_gb_all) / len(per_task_gb_all)
    delta_all = acc_gb_all - acc_a_all
    n_plus_all, n_minus_all, p_all = _sign_test(
        [b - a for b, a in zip(per_task_gb_all, per_task_a1_all)]
    )

    print(f"  Arm A (all tasks):    {acc_a_all:.1%}")
    print(f"  Guard-B (all tasks):  {acc_gb_all:.1%}")
    print(f"  Net delta:            {delta_all:+.1%}")
    print(f"  Sign test: n+={n_plus_all} n-={n_minus_all}  p={p_all:.4f}")

    net_positive = delta_all > 0
    regressions_cancel = bool(regressions) and delta_all < 0.05
    print(
        f"\n  NET EFFECT: "
        f"{'POSITIVE — gains not cancelled by regressions.' if net_positive and not regressions_cancel else 'NEGATIVE or ZERO — regressions cancel or exceed recovery gains.' if regressions else 'Neutral — no meaningful change across all tasks.'}"
    )

    # ── SECTION F: VERDICT ────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION F — VERDICT")
    print("=" * 80)

    zero_regressions = len(regressions) == 0
    contested_preserved = all_fully_recovered

    if zero_regressions and contested_preserved:
        verdict = (
            "SAFE TO RUN BLANKET — Guard-B is safe on the full extended catalog.\n"
            "  Zero regressions on already-passing tasks + contested recovery preserved.\n"
            "  Blanket deployment claim closes: Guard-B can be applied to any tool\n"
            "  in a documented MCP server without degrading already-correct tool selection."
        )
    elif zero_regressions and not contested_preserved:
        verdict = (
            "RECOVERY BROKE ON EXTENDED CATALOG — Guard-B regressions on contested tasks.\n"
            "  Zero regressions on already-passing tasks, but contested recovery failed.\n"
            "  Scale interaction: extending the catalog may have confused the generator.\n"
            "  Report: which contested tasks failed and the Guard-B descriptions used."
        )
    elif not zero_regressions and contested_preserved:
        verdict = (
            f"REGRESSIONS ON COLLISION PAIRS — Guard-B introduced confusability.\n"
            f"  {len(regressions)} PASS->FAIL flip(s) on already-passing tasks.\n"
            "  Contested recovery preserved, but blanket deployment is NOT safe.\n"
            "  Blanket use needs a collision check — localise affected tools (see Section C).\n"
            "  These regressions localize what Q7 would fix (collision-aware Guard-B)."
        )
    else:
        verdict = (
            f"BOTH FAILURE MODES — {len(regressions)} regression(s) AND contested recovery broke.\n"
            "  Scale interaction + collision confusability. Report all failures above."
        )

    print(f"\n  {verdict}\n")
    print(f"  Summary:")
    print(f"    Regressions on already-passing tasks: {len(regressions)}")
    print(f"    Contested recovery preserved:          {'YES' if contested_preserved else 'NO'}")
    print(f"    Net aggregate delta:                   {delta_all:+.1%}")
    print(f"    Stability-dropped tasks:               {len(dropped_ap_indices)}")
    print(f"    Collision-prone pairs tested:          {len(COLLISION_PRONE_PAIRS)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Q6 Phase 2: do-no-harm regression experiment")
    parser.add_argument("--agent-model", default="gemma2:9b")
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials))


if __name__ == "__main__":
    main()
