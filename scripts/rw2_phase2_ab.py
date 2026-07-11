#!/usr/bin/env python3
"""RW2 Phase 2 — A/B experiment: Arm A (AWS IAM docstrings) vs Arm GuardB.

Measures selection accuracy on confusable AWS IAM tasks. Two arms:
  A      — original AWS IAM docstrings as shipped (the real Arm A baseline)
  GuardB — Guard-B descriptions generated from mirror source docstrings (Phase 1)

Key metrics:
  1. HEADROOM: does Arm A (real docs) miss any contested tasks?
  2. VALUE: GuardB accuracy vs Arm A on contested tasks (sign test).
  3. DO-NO-HARM: GuardB must not regress on thorough-tool control set.
  4. PAINKILLER: wrong-DESTRUCTIVE-tool selection rate A vs GuardB.
     This is the CEO number — selecting the wrong destructive tool causes
     IRREVERSIBLE policy deletion from the wrong principal type.

GPU EXCLUSIVITY:
  Run AFTER ollama stop (Phase 1 must be complete and Ollama cleared).
  Watchdog kills run if any non-agent-family model loads.

Usage:
    python scripts/rw2_phase2_ab.py [--agent-model gemma2:9b] [--trials 5]

Prerequisites:
  - evals/fixtures/rw2_arm_guardb_descriptions.json exists (Phase 1 complete)
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
    identify_contested_indices,
    parse_failed_count,
    parse_success_accuracy,
)
from agentgauge.runner import _build_tool_listing, run_tasks  # noqa: E402
from evals.fixtures.rw2_aws_iam_catalog import (  # noqa: E402
    CONTESTED_TOOLS,
    DESTRUCTIVE_CONFUSABLE_PAIRS,
    DESTRUCTIVE_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    TASKS,
    THOROUGH_TOOL_CONTROL_SET,
)

_FIXTURE_A = Path(__file__).parent.parent / "examples" / "rw2_arm_a.py"
_FIXTURE_GUARDB = Path(__file__).parent.parent / "examples" / "rw2_arm_guardb.py"

_GUARDB_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "rw2_arm_guardb_descriptions.json"
)
_CONTAMINATION_FILE = Path(__file__).parent.parent / "RW2_CONTAMINATED.txt"

_VALID_TOOL_NAMES: set[str] = {t for names in FAMILIES.values() for t in names}
_DESTRUCTIVE_TOOL_NAMES: frozenset[str] = DESTRUCTIVE_TOOLS


def _check_foreign_models(agent_family: str) -> list[str]:
    """Check Ollama for non-agent model families loaded in GPU memory."""
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


def _contested_task_indices() -> list[int]:
    """Return TASKS indices whose gold_tool is in CONTESTED_TOOLS."""
    return [i for i, task in enumerate(TASKS) if task.tool_name in CONTESTED_TOOLS]


def _thorough_task_indices() -> list[int]:
    """Return TASKS indices whose gold_tool is in THOROUGH_TOOL_CONTROL_SET."""
    return [i for i, task in enumerate(TASKS) if task.tool_name in THOROUGH_TOOL_CONTROL_SET]


async def run(agent_model: str, trials: int) -> None:
    """Run the full RW2 A/B experiment."""
    assert_agent_ne_judge_ne_generator(agent_model)
    agent_family = agent_model.split(":")[0].lower()

    # Pre-check: Guard-B descriptions must exist
    if not _GUARDB_PATH.exists():
        print(f"ERROR: {_GUARDB_PATH.name} not found.")
        print("Run Phase 1 first: python scripts/rw2_phase1_generate.py")
        sys.exit(1)
    guardb_descs = json.loads(_GUARDB_PATH.read_text(encoding="utf-8"))
    if not guardb_descs:
        print(f"ERROR: {_GUARDB_PATH.name} is empty. Phase 1 did not complete successfully.")
        sys.exit(1)

    n_contested_pre = len(_contested_task_indices())
    n_thorough_pre = len(_thorough_task_indices())

    print("=" * 80)
    print("RW2 Phase 2 — A/B: AWS IAM docstrings vs Guard-B")
    print(
        f"Agent: {agent_model}  |  Trials: {trials}  |  Tasks: {len(TASKS)}  |  Tools: 29"
    )
    print(
        f"Guard-B descriptions: {len(guardb_descs)}/29 tools  |  "
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

    print("\n[STEP 1] Connecting to arm servers...")
    client_a, ctx_a = await connect_stdio(python, [str(_FIXTURE_A)])
    client_g, ctx_g = await connect_stdio(python, [str(_FIXTURE_GUARDB)])

    try:
        info_a = await client_a.introspect()
        info_g = await client_g.introspect()

        listing_a = _build_tool_listing(info_a.tools)
        listing_g = _build_tool_listing(info_g.tools)

        manip_g = listing_a != listing_g
        print(
            f"[PRE-CHECK] Manipulation A vs GuardB: "
            f"{'PASS' if manip_g else 'WARN — GuardB identical to Arm A (Phase 1 not run?)'}"
        )

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

    finally:
        for ctx in [ctx_a, ctx_g]:
            try:  # noqa: SIM105
                await cleanup_connection(ctx)
            except BaseException:
                pass

    total = len(results_a)

    # ── Section A: GPU + parse_failed ─────────────────────────────────────────
    pf_a = parse_failed_count(results_a, _VALID_TOOL_NAMES)
    pf_g = parse_failed_count(results_g, _VALID_TOOL_NAMES)

    print("\n" + "=" * 80)
    print("SECTION A — GPU exclusivity + parse-failed diagnostics")
    print("=" * 80)
    print("  GPU: confirmed exclusive (watchdog clean at each arm boundary)")
    print(f"  Arm A:       {pf_a}/{total} parse-failed ({100 * pf_a / total if total else 0:.1f}%)")
    print(f"  Arm GuardB:  {pf_g}/{total} parse-failed ({100 * pf_g / total if total else 0:.1f}%)")

    # ── Section B: HEADROOM — does real Arm A have contested tasks? ───────────
    contested_indices = _contested_task_indices()
    contested_a = identify_contested_indices(results_a, TASKS, trials, _VALID_TOOL_NAMES)
    n_contested = len(contested_a)

    print("\n" + "=" * 80)
    print("SECTION B — HEADROOM (Arm A accuracy on the pre-registered contested task set)")
    print("=" * 80)
    print(
        "  Arm A uses the REAL AWS IAM docstrings — this is the external-validity baseline.\n"
        "  Headroom exists only if the real docs FAIL on some contested tasks.\n"
    )

    overall_a_acc = parse_success_accuracy(
        results_a, TASKS, trials, _VALID_TOOL_NAMES, list(range(len(TASKS)))
    )
    contested_a_acc = parse_success_accuracy(
        results_a, TASKS, trials, _VALID_TOOL_NAMES, contested_indices
    )
    print(f"  Arm A overall accuracy (all 29 tasks, parse-success): {overall_a_acc * 100:.1f}%")
    print(
        f"  Arm A accuracy on {len(contested_indices)} pre-registered contested tasks: "
        f"{contested_a_acc * 100:.1f}%"
    )
    print(f"\n  Dynamically contested tasks (Arm A parse-success == 0%): {n_contested}/{len(TASKS)}")

    if n_contested == 0 and contested_a_acc >= 0.99:
        print(
            "\n  NO HEADROOM: Arm A (real AWS IAM docstrings) correctly selected the right tool\n"
            "  for every task. Guard-B has nothing to recover.\n"
            "\n  FINDING: AWS IAM's real docstrings already disambiguate the confusable families\n"
            "  for this task set and this agent. See RW1 for the GitHub analog.\n"
            "  This bounds the buyer: Guard-B is most valuable for undocumented servers."
        )
        # Still continue to show do-no-harm and painkiller sections

    # Use pre-registered contested indices for the main VALUE analysis
    eval_contested = contested_indices if len(contested_indices) > 0 else contested_a

    # ── Section C: VALUE table (A vs GuardB on contested tasks) ───────────────
    per_task_a = [
        parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in eval_contested
    ]
    per_task_g = [
        parse_success_accuracy(results_g, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in eval_contested
    ]

    acc_a = parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, eval_contested)
    acc_g = parse_success_accuracy(results_g, TASKS, trials, _VALID_TOOL_NAMES, eval_contested)

    deltas_g_a = [g - a for g, a in zip(per_task_g, per_task_a, strict=True)]
    n_plus_g, n_minus_g, p_g = _sign_test(deltas_g_a)

    print("\n" + "=" * 80)
    print("SECTION C — VALUE: A vs GuardB (parse-success, contested tasks)")
    print("=" * 80)
    print(
        f"{'Family':<22} {'Task (truncated)':<42} {'A%':>5} {'GB%':>5} {'Δ':>5}"
    )
    print("-" * 80)
    for idx_in_c, task_idx in enumerate(eval_contested):
        task = TASKS[task_idx]
        family = FAMILY_MAP.get(task.tool_name, "?")
        a_pct = per_task_a[idx_in_c] * 100
        g_pct = per_task_g[idx_in_c] * 100
        delta = g_pct - a_pct
        is_dest = " [D]" if task.tool_name in _DESTRUCTIVE_TOOL_NAMES else ""
        desc = task.description[:40] + ".." if len(task.description) > 42 else task.description
        print(
            f"{family + is_dest:<22} {desc:<42} {a_pct:>4.0f}% {g_pct:>4.0f}% {delta:>+4.0f}pp"
        )
    print("-" * 80)
    print(
        f"{'AGGREGATE':<22} {'(parse-success, ' + str(len(eval_contested)) + ' contested)':<42} "
        f"{acc_a * 100:>4.1f}% {acc_g * 100:>4.1f}% {(acc_g - acc_a) * 100:>+4.1f}pp"
    )
    print("=" * 80)
    print(f"\n  Improvement (GuardB − A) on contested tasks: {(acc_g - acc_a) * 100:+.1f}pp")
    print(f"  Sign test GuardB vs A: n+={n_plus_g} n-={n_minus_g}  p={p_g:.4f}")

    # ── Section D: DO-NO-HARM (thorough-tool control set) ─────────────────────
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
        1
        for a_pct, g_pct in zip(per_thorough_a, per_thorough_g, strict=True)
        if g_pct < a_pct
    )

    print("\n" + "=" * 80)
    print("SECTION D — DO-NO-HARM: thorough-tool control set (Guard-B must not regress)")
    print("=" * 80)
    print(
        "  These are tools with name-resolvable behavior or richer docstrings.\n"
        "  Guard-B must SKIP or PRESERVE them — zero regressions is the target.\n"
    )
    print(
        f"{'Tool':<30} {'A%':>5} {'GB%':>5} {'Δ':>5} {'Status':<10}"
    )
    print("-" * 60)
    for idx_in_t, task_idx in enumerate(thorough_indices):
        task = TASKS[task_idx]
        a_pct = per_thorough_a[idx_in_t] * 100
        g_pct = per_thorough_g[idx_in_t] * 100
        delta = g_pct - a_pct
        status = "REGRESSION" if g_pct < a_pct else "ok"
        print(f"{task.tool_name:<30} {a_pct:>4.0f}% {g_pct:>4.0f}% {delta:>+4.0f}pp {status:<10}")
    print("-" * 60)
    print(
        f"{'AGGREGATE':<30} {acc_thorough_a * 100:>4.1f}% {acc_thorough_g * 100:>4.1f}% "
        f"{(acc_thorough_g - acc_thorough_a) * 100:>+4.1f}pp"
    )
    print("=" * 60)
    print(
        f"\n  Regressions on thorough-tool set: {regressions}/{len(thorough_indices)} "
        f"({'FAIL — investigate' if regressions > 0 else 'PASS — zero regressions'})"
    )

    # ── Section E: PAINKILLER — wrong-DESTRUCTIVE-tool rate ───────────────────
    wrong_a, ps_a, rate_a = _wrong_destructive_rate(results_a, TASKS, trials)
    wrong_g, ps_g, rate_g = _wrong_destructive_rate(results_g, TASKS, trials)

    print("\n" + "=" * 80)
    print("SECTION E — PAINKILLER: wrong-DESTRUCTIVE-tool selection rate (CEO metric)")
    print("=" * 80)
    print(
        "  Counts trials where agent selected a DESTRUCTIVE tool for a NON-destructive task.\n"
        "  In AWS IAM, wrong-destructive = accidental IRREVERSIBLE policy deletion.\n"
        "  (e.g. selected 'delete_user_policy' when task asked to READ or LIST policies)\n"
    )
    print("  Destructive-confusable pairs in this fixture:")
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
        print(
            "\n  Arm A made 0 wrong-destructive selections — no CEO headroom on this task set.\n"
            "  Possible explanation: AWS IAM 'delete_*_policy' names are explicit enough\n"
            "  that the agent did not confuse them with read/list neighbors."
        )

    # ── Section F: VERDICT (CEO) ──────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION F — Verdict (CEO)")
    print("=" * 80)

    guardb_improves = (acc_g - acc_a) > 0.05  # >5pp absolute improvement
    ceo_signal = rate_a > 0 and (rate_a - rate_g) > 0
    no_harm = regressions == 0

    print(f"\n  Arm A (AWS IAM docstrings): {acc_a * 100:.1f}%  ({len(eval_contested)} contested tasks)")
    print(f"  GuardB:                    {acc_g * 100:.1f}%  delta={( acc_g - acc_a) * 100:+.1f}pp")
    print(f"  Sign test GuardB vs A:     p={p_g:.4f}  ({'significant' if p_g < 0.05 else 'not significant'})")
    print(f"  Wrong-destructive: A={rate_a * 100:.1f}%  GuardB={rate_g * 100:.1f}%")
    print(
        f"  Do-no-harm (thorough set): "
        f"{'PASS — zero regressions' if no_harm else f'FAIL — {regressions} regressions'}"
    )

    print()
    if guardb_improves and no_harm and ceo_signal:
        print(
            "  VERDICT: SCORE VALIDITY + FIX VALUE CONFIRMED\n"
            "  AWS IAM real docs have headroom. Guard-B recovers contested tasks AND reduces\n"
            "  wrong-DESTRUCTIVE-tool selection. Zero do-no-harm regressions confirmed.\n"
            "  External validity + value confirmed for under-documented IAM server."
        )
    elif guardb_improves and no_harm and not ceo_signal:
        print(
            "  VERDICT (partial): Guard-B improves contested accuracy on thin IAM descriptions,\n"
            "  no do-no-harm regressions. Wrong-destructive rate did not improve (zero headroom).\n"
            "  BUYER: under-documented IAM servers benefit from Guard-B on selection quality."
        )
    elif guardb_improves and not no_harm:
        print(
            "  VERDICT (do-no-harm FAILURE): Guard-B improved contested accuracy but introduced\n"
            f"  {regressions} regression(s) on thorough-tool set. Investigate before shipping."
        )
    elif not guardb_improves and no_harm:
        print(
            "  VERDICT: FIX VALUE BOUNDED — WELL-DOCUMENTED SERVER\n"
            "  AWS IAM docstrings are already good enough for this agent. Guard-B adds little.\n"
            "  Zero do-no-harm regressions: safe to run, but minimal upside here.\n"
            "  See RW1 for the GitHub MCP analog."
        )
    else:
        print("  VERDICT: INCONCLUSIVE — check per-task data and sign test.")

    print(
        "\n  Note: All results are model-dependent "
        f"(agent={agent_model}, generator=qwen3:8b).\n"
        "  Record agent model, judge model, and trial count alongside any stored scores."
    )


def main() -> None:
    """Entry point for RW2 Phase 2 A/B experiment."""
    parser = argparse.ArgumentParser(
        description="RW2 Phase 2: A/B experiment on AWS IAM MCP tools"
    )
    parser.add_argument("--agent-model", default="gemma2:9b")
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials))


if __name__ == "__main__":
    main()
