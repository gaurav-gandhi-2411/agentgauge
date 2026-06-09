#!/usr/bin/env python3
"""RW1 Phase 2 — A/B experiment: Arm A (GitHub docstrings) vs Arm GuardB vs Arm O.

Measures selection accuracy on confusable GitHub MCP tasks. Three arms:
  A      — original GitHub docstrings as shipped (the real Arm A baseline)
  GuardB — Guard-B descriptions generated from mirror source docstrings (Phase 1)
  O      — oracle descriptions (human-derived ceiling)

Key metrics:
  1. HEADROOM: does Arm A (real docs) miss any contested tasks? If not, report it.
  2. IMPROVEMENT: GuardB accuracy vs Arm A on contested tasks (sign test).
  3. PAINKILLER: wrong-DESTRUCTIVE-tool selection rate A vs GuardB separately.
     This is the CEO number — selecting the wrong destructive tool costs customers.

GPU EXCLUSIVITY:
  Run AFTER ollama stop (Phase 1 must be complete and Ollama cleared).
  Watchdog kills run if any non-agent-family model loads.

Usage:
    python scripts/rw1_phase2_ab.py [--agent-model gemma2:9b] [--trials 5]

Prerequisites:
  - evals/fixtures/rw1_arm_guardb_descriptions.json exists (Phase 1 complete)
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

from agentgauge.ab_harness import assert_agent_ne_judge_ne_generator
from agentgauge.client import cleanup_connection, connect_stdio
from agentgauge.providers import OllamaProvider
from agentgauge.q2a_harness import (
    _sign_test,
    compute_recovery_fraction,
    identify_contested_indices,
    parse_failed_count,
    parse_success_accuracy,
)
from agentgauge.runner import _build_tool_listing, run_tasks
from evals.fixtures.rw1_github_catalog import (
    ARM_O_DESCRIPTIONS,
    DESTRUCTIVE_CONFUSABLE_PAIRS,
    DESTRUCTIVE_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    GITHUB_DOCSTRINGS,
    TASKS,
    TOOL_SCHEMAS,
)

_FIXTURE_A = Path(__file__).parent.parent / "examples" / "rw1_arm_a.py"
_FIXTURE_GUARDB = Path(__file__).parent.parent / "examples" / "rw1_arm_guardb.py"
_FIXTURE_O = Path(__file__).parent.parent / "examples" / "rw1_arm_oracle.py"

_GUARDB_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "rw1_arm_guardb_descriptions.json"
)
_CONTAMINATION_FILE = Path(__file__).parent.parent / "RW1_CONTAMINATED.txt"

_VALID_TOOL_NAMES: set[str] = {t for names in FAMILIES.values() for t in names}
_DESTRUCTIVE_TOOL_NAMES: frozenset[str] = DESTRUCTIVE_TOOLS


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


def _wrong_destructive_rate(
    results: list,
    tasks: list,
    trials: int,
) -> tuple[int, int, float]:
    """Count trials where the agent selected a destructive tool for a NON-destructive task.

    Returns (wrong_destructive_count, total_parse_success, rate).
    A 'wrong destructive' selection is:
      - The gold tool is NOT destructive, AND
      - The agent selected a destructive tool.
    """
    wrong = 0
    total_ps = 0
    for i, task in enumerate(tasks):
        if task.tool_name in _DESTRUCTIVE_TOOL_NAMES:
            continue  # skip tasks where the gold tool IS destructive
        task_results = results[i * trials : (i + 1) * trials]
        for r in task_results:
            if r.selected_tool not in _VALID_TOOL_NAMES:
                continue  # parse-failed
            total_ps += 1
            if r.selected_tool in _DESTRUCTIVE_TOOL_NAMES:
                wrong += 1
    rate = wrong / total_ps if total_ps > 0 else 0.0
    return wrong, total_ps, rate


async def run(agent_model: str, trials: int) -> None:
    assert_agent_ne_judge_ne_generator(agent_model)
    agent_family = agent_model.split(":")[0].lower()

    # Pre-check: Guard-B descriptions must exist
    if not _GUARDB_PATH.exists():
        print(f"ERROR: {_GUARDB_PATH.name} not found.")
        print("Run Phase 1 first: python scripts/rw1_phase1_generate.py")
        sys.exit(1)
    guardb_descs = json.loads(_GUARDB_PATH.read_text(encoding="utf-8"))
    if not guardb_descs:
        print(f"ERROR: {_GUARDB_PATH.name} is empty. Phase 1 did not complete successfully.")
        sys.exit(1)

    print("=" * 80)
    print("RW1 Phase 2 — A/B: GitHub docstrings vs Guard-B vs Oracle")
    print(f"Agent: {agent_model}  |  Trials: {trials}  |  Tasks: {len(TASKS)}  |  Tools: 21")
    print(f"Guard-B descriptions: {len(guardb_descs)}/21 tools")
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

    print("\n[STEP 1] Connecting to all three arm servers...")
    client_a, ctx_a = await connect_stdio(python, [str(_FIXTURE_A)])
    client_g, ctx_g = await connect_stdio(python, [str(_FIXTURE_GUARDB)])
    client_o, ctx_o = await connect_stdio(python, [str(_FIXTURE_O)])

    try:
        info_a = await client_a.introspect()
        info_g = await client_g.introspect()
        info_o = await client_o.introspect()

        listing_a = _build_tool_listing(info_a.tools)
        listing_g = _build_tool_listing(info_g.tools)
        listing_o = _build_tool_listing(info_o.tools)

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

        print(f"\n[RUN] Arm A ({len(TASKS)} tasks × {trials} trials)...")
        results_a = await run_tasks(TASKS, client_a, OllamaProvider(agent_model), trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm A: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm A done. GPU watchdog: clean")

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
        for ctx in [ctx_a, ctx_g, ctx_o]:
            try:
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

    # ── Section B: HEADROOM — does real Arm A have contested tasks? ───────────
    contested = identify_contested_indices(results_a, TASKS, trials, _VALID_TOOL_NAMES)
    n_contested = len(contested)

    print("\n" + "=" * 80)
    print("SECTION B — HEADROOM (Arm A accuracy on the confusable task set)")
    print("=" * 80)
    print(
        "  Arm A uses the REAL GitHub docstrings — this is the external-validity baseline.\n"
        "  Headroom exists only if the real docs FAIL on some tasks.\n"
    )

    overall_a_acc = parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, list(range(len(TASKS))))
    print(f"  Arm A overall accuracy (all 21 tasks, parse-success): {overall_a_acc * 100:.1f}%")

    print(f"\n  Contested tasks (Arm A parse-success == 0%): {n_contested}/{len(TASKS)}")
    if n_contested == 0:
        print(
            "\n  NO HEADROOM: Arm A (real GitHub docstrings) correctly selected the right tool\n"
            "  for every task. Guard-B has nothing to recover.\n"
            "\n  FINDING: GitHub's real docstrings already disambiguate the confusable families\n"
            "  for this task set and this agent. The fix adds value only on POORLY-DOCUMENTED\n"
            "  servers — GitHub MCP is already well enough documented for gemma2:9b.\n"
            "  This bounds the buyer: Guard-B is most valuable for undocumented servers."
        )
        return

    # ── Section C: RECOVERY table ──────────────────────────────────────────────
    per_task_a = [
        parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested
    ]
    per_task_g = [
        parse_success_accuracy(results_g, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested
    ]
    per_task_o = [
        parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested
    ]

    acc_a = parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_g = parse_success_accuracy(results_g, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_o = parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, contested)

    rec_g = compute_recovery_fraction(acc_g, acc_a, acc_o)

    deltas_g_a = [g - a for g, a in zip(per_task_g, per_task_a, strict=True)]
    deltas_o_a = [o - a for o, a in zip(per_task_o, per_task_a, strict=True)]

    n_plus_g, n_minus_g, p_g = _sign_test(deltas_g_a)
    n_plus_o, n_minus_o, p_o = _sign_test(deltas_o_a)

    print("\n" + "=" * 80)
    print("SECTION C — RECOVERY: three-arm table (parse-success, contested tasks)")
    print("=" * 80)
    print(
        f"{'Family':<18} {'Task (truncated)':<46} {'A%':>5} {'GB%':>5} {'O%':>5}"
    )
    print("-" * 83)
    for idx_in_c, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        family = FAMILY_MAP.get(task.tool_name, "?")
        a_pct = per_task_a[idx_in_c] * 100
        g_pct = per_task_g[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        is_dest = " [D]" if task.tool_name in _DESTRUCTIVE_TOOL_NAMES else ""
        desc = task.description[:44] + ".." if len(task.description) > 46 else task.description
        print(f"{family + is_dest:<18} {desc:<46} {a_pct:>4.0f}% {g_pct:>4.0f}% {o_pct:>4.0f}%")
    print("-" * 83)
    print(
        f"{'AGGREGATE':<18} {'(parse-success, ' + str(n_contested) + ' contested)':<46} "
        f"{acc_a * 100:>4.1f}% {acc_g * 100:>4.1f}% {acc_o * 100:>4.1f}%"
    )
    print("=" * 83)
    print(f"\n  Recovery (GuardB − A) / (O − A): ", end="")
    print(f"{rec_g:.3f}  ({rec_g * 100:.1f}%)" if rec_g is not None else "N/A")
    print(f"  Sign test GuardB vs A: n+={n_plus_g} n-={n_minus_g}  p={p_g:.4f}")
    print(f"  Sign test Oracle vs A: n+={n_plus_o} n-={n_minus_o}  p={p_o:.4f}")

    # ── Section D: PAINKILLER — wrong-DESTRUCTIVE-tool rate ───────────────────
    wrong_a, ps_a, rate_a = _wrong_destructive_rate(results_a, TASKS, trials)
    wrong_g, ps_g, rate_g = _wrong_destructive_rate(results_g, TASKS, trials)

    print("\n" + "=" * 80)
    print("SECTION D — PAINKILLER: wrong-DESTRUCTIVE-tool selection rate (CEO metric)")
    print("=" * 80)
    print(
        "  Counts trials where agent selected a DESTRUCTIVE tool for a NON-destructive task.\n"
        "  (e.g. selected 'create_or_update_file' when the task asked to READ a file)\n"
        "  These are the failures that directly cost customers: accidental commits, merges,\n"
        "  repo creation.\n"
    )
    print(f"  Destructive-confusable pairs in this fixture:")
    for safe, destructive in DESTRUCTIVE_CONFUSABLE_PAIRS:
        print(f"    safe: {safe:<35} destructive: {destructive}")

    print(
        f"\n  Arm A   — wrong destructive selections: {wrong_a}/{ps_a} "
        f"({rate_a * 100:.1f}%) on non-destructive tasks"
    )
    print(
        f"  GuardB  — wrong destructive selections: {wrong_g}/{ps_g} "
        f"({rate_g * 100:.1f}%) on non-destructive tasks"
    )

    if rate_a > 0:
        delta_dest = rate_a - rate_g
        print(f"\n  Wrong-destructive delta (A − GuardB): {delta_dest * 100:+.1f}pp")
        if delta_dest > 0:
            print("  GuardB reduced wrong-destructive selections.")
        elif delta_dest == 0:
            print("  No change in wrong-destructive selections.")
        else:
            print("  WARN: GuardB increased wrong-destructive selections — investigate.")
    else:
        print("\n  Arm A made 0 wrong-destructive selections — no CEO headroom on this task set.")
        print("  Possible explanation: GitHub's terse 'Create or update a file' / 'Merge a PR'")
        print("  descriptions are already clear enough that the agent did not confuse them")
        print("  with safe neighbors on the given task phrasings.")

    # ── Section E: Per-task miss diagnosis ────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION E — Per-task miss diagnosis (GuardB < Oracle)")
    print("=" * 80)
    any_miss = False
    for idx_in_c, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        g_pct = per_task_g[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        if g_pct >= o_pct:
            continue
        any_miss = True
        family = FAMILY_MAP.get(task.tool_name, "?")
        github_desc = GITHUB_DOCSTRINGS.get(task.tool_name, "")
        guardb_desc = guardb_descs.get(task.tool_name, "(missing)")
        oracle_desc = ARM_O_DESCRIPTIONS.get(task.tool_name, "")
        print(f"  [{family}] Task: {task.description}")
        print(f"    Gold: {task.tool_name}  {'[DESTRUCTIVE]' if task.tool_name in _DESTRUCTIVE_TOOL_NAMES else ''}")
        print(f"    Arm A (GitHub): {github_desc}")
        print(f"    GuardB:         {guardb_desc}")
        print(f"    Oracle:         {oracle_desc[:100]}")
        print(f"    A%={per_task_a[idx_in_c] * 100:.0f}%  GuardB%={g_pct:.0f}%  O%={o_pct:.0f}%")
        print(f"    Miss type: [ ] OVER-CONSTRAINED  [ ] ABSENT-FROM-BODY  [ ] TASK-AMBIGUOUS")
        print()
    if not any_miss:
        print("  All contested tasks: GuardB >= Oracle.")

    # ── Section F: Verdict ────────────────────────────────────────────────────
    print("=" * 80)
    print("SECTION F — Verdict")
    print("=" * 80)

    guardb_recovers = rec_g is not None and rec_g > 0.30
    ceo_signal = rate_a > 0 and (rate_a - rate_g) > 0

    print(f"\n  Arm A (GitHub docstrings): {acc_a * 100:.1f}%  ({n_contested} contested tasks)")
    if rec_g is not None:
        print(f"  GuardB:                    {acc_g * 100:.1f}%  recovery={rec_g * 100:.1f}%")
    else:
        print(f"  GuardB:                    {acc_g * 100:.1f}%  recovery=N/A")
    print(f"  Oracle (ceiling):          {acc_o * 100:.1f}%")
    print(f"  Sign test GuardB vs A:     p={p_g:.4f}  ({'significant' if p_g < 0.05 else 'not significant'})")
    print(f"  Wrong-destructive: A={rate_a * 100:.1f}%  GuardB={rate_g * 100:.1f}%")

    print()
    if guardb_recovers and ceo_signal:
        print(
            "  VERDICT (a): SCORE VALIDITY + FIX VALUE CONFIRMED\n"
            "  The scanner flags real confusable families AND Guard-B reduces wrong/destructive\n"
            "  tool selection on real GitHub tools. External validity + value confirmed."
        )
    elif guardb_recovers and not ceo_signal:
        print(
            "  VERDICT (a-partial): Guard-B improves selection accuracy on contested tasks,\n"
            "  but wrong-destructive rate did not improve (may be zero headroom there)."
        )
    elif n_contested == 0 or not guardb_recovers:
        print(
            "  VERDICT (b): FIX VALUE BOUNDED — WELL-DOCUMENTED SERVER\n"
            "  GitHub's real docstrings are already good enough. Guard-B adds little on this\n"
            "  server. The fix's value is on POORLY-DOCUMENTED servers, not well-maintained ones.\n"
            "  This bounds the buyer: target servers with thin or absent tool descriptions."
        )
    else:
        print("  VERDICT: INCONCLUSIVE — check per-task data and sign test.")

    print(
        "\n  Note: All results are model-dependent (agent=gemma2:9b, generator=qwen3:8b).\n"
        "  Record agent model, judge model, and trial count alongside any stored scores."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="RW1 Phase 2: A/B experiment on GitHub MCP tools")
    parser.add_argument("--agent-model", default="gemma2:9b")
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials))


if __name__ == "__main__":
    main()
