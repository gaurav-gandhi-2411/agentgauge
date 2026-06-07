#!/usr/bin/env python3
"""Q5 Phase 2 — four-arm Guard B distinction experiment.

Arms:
  A               — empty descriptions (floor)
  Q4-DOC-scoped   — generated from scoped source + neighbor surfaces, docstrings kept (reference arm)
  Q5              — Guard B: same DOC-scoped setup, comparative neighbor claims forbidden
  O               — oracle descriptions derived from reading q3_real_server.py (ceiling)

Metric: parse-success selection_accuracy on contested tasks (Arm A == 0%).
Recovery Q4-DOC-scoped = (Q4-DOC - A) / (O - A)  [reference, already measured in Q4]
Recovery Q5            = (Q5 - A) / (O - A)

Safety hypothesis: Q5 (Guard B) eliminates fabricated comparative claims on control tools while
maintaining the same recovery rate as Q4-DOC-scoped.

No-fabrication control: FAITHFUL-EQUIVALENT / INCIDENTAL-BUT-TRUE / FABRICATED per control tool.
The Q4-DOC find_entries->docstring-body-mismatch fabrication MUST NOT recur in Q5.

Usage:
    python scripts/run_q5_four_arm.py [--agent-model gemma2:9b] [--trials 5]

Prerequisites:
  - Phase 1 complete: evals/fixtures/q5_arm_f_doc_guarded_descriptions.json exists (non-empty)
  - evals/fixtures/q4_arm_f_doc_scoped_descriptions.json exists (Q4 reference arm)
  - ollama stop, then ollama ps (must be empty) before running
  - Watchdog kills run if any non-agent-family model loads during Phase 2
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
from evals.fixtures.q3_catalog import (
    ARM_O_DESCRIPTIONS,
    CONTROL_TASK_PAIRS,
    CONTROL_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    INDEPENDENCE_TOKENS,
    TASKS,
)

_FIXTURE_A = Path(__file__).parent.parent / "examples" / "q3_arm_a.py"
_FIXTURE_DOC_SCOPED = Path(__file__).parent.parent / "examples" / "q4_arm_f_doc_scoped.py"
_FIXTURE_Q5_GUARDED = Path(__file__).parent.parent / "examples" / "q5_arm_f_doc_guarded.py"
_FIXTURE_O = Path(__file__).parent.parent / "examples" / "q3_arm_o.py"

_ARM_DOC_SCOPED_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "q4_arm_f_doc_scoped_descriptions.json"
)
_ARM_Q5_GUARDED_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "q5_arm_f_doc_guarded_descriptions.json"
)
_CONTAMINATION_FILE = Path(__file__).parent.parent / "Q5_CONTAMINATED.txt"

_VALID_TOOL_NAMES: set[str] = {name for names in FAMILIES.values() for name in names}
_AMBIGUOUS_TOOLS: set[str] = set(CONTROL_TOOLS)


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


async def run(agent_model: str, trials: int) -> None:
    assert_agent_ne_judge_ne_generator(agent_model)

    agent_family = agent_model.split(":")[0].lower()

    # Phase 1 pre-check: description files must exist and be non-empty
    for path, label in [
        (_ARM_Q5_GUARDED_PATH, "q5_arm_f_doc_guarded_descriptions.json"),
        (_ARM_DOC_SCOPED_PATH, "q4_arm_f_doc_scoped_descriptions.json"),
    ]:
        if not path.exists():
            print(f"ERROR: {label} not found.")
            if "q5" in label:
                print("Run Phase 1 first: python scripts/generate_q5_descriptions.py")
            else:
                print("Run Q4 Phase 1 first: python scripts/generate_q4_descriptions.py")
            sys.exit(1)
        content = json.loads(path.read_text(encoding="utf-8"))
        if not content:
            print(f"ERROR: {label} is empty ({{}}). Phase 1 did not complete successfully.")
            sys.exit(1)

    arm_doc_scoped: dict[str, str] = json.loads(_ARM_DOC_SCOPED_PATH.read_text(encoding="utf-8"))
    arm_q5_guarded: dict[str, str] = json.loads(_ARM_Q5_GUARDED_PATH.read_text(encoding="utf-8"))

    print("=" * 80)
    print("Q5 Four-Arm Guard B Experiment")
    print(f"Agent: {agent_model}  |  Trials: {trials}")
    print(f"Tasks (pre-registered): {len(TASKS)}  |  Tools: {len(_VALID_TOOL_NAMES)}")
    print(
        f"Q4-DOC-scoped descriptions: {len(arm_doc_scoped)}  |  "
        f"Q5-guarded descriptions: {len(arm_q5_guarded)}"
    )
    print("=" * 80)

    python = sys.executable

    # GPU pre-check: ollama ps must be empty before Phase 2
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

    print("\n[STEP 1] Connecting to all four arms...")
    client_a, ctx_a = await connect_stdio(python, [str(_FIXTURE_A)])
    client_doc, ctx_doc = await connect_stdio(python, [str(_FIXTURE_DOC_SCOPED)])
    client_q5, ctx_q5 = await connect_stdio(python, [str(_FIXTURE_Q5_GUARDED)])
    client_o, ctx_o = await connect_stdio(python, [str(_FIXTURE_O)])

    try:
        # Manipulation check
        info_a = await client_a.introspect()
        info_doc = await client_doc.introspect()
        info_q5 = await client_q5.introspect()
        info_o = await client_o.introspect()

        listing_a = _build_tool_listing(info_a.tools)
        listing_doc = _build_tool_listing(info_doc.tools)
        listing_q5 = _build_tool_listing(info_q5.tools)
        listing_o = _build_tool_listing(info_o.tools)

        manip_doc = listing_a != listing_doc
        manip_q5 = listing_a != listing_q5
        manip_o = listing_a != listing_o

        print(
            f"[PRE-CHECK] Manipulation A vs Q4-DOC-scoped: "
            f"{'PASS' if manip_doc else 'WARN (DOC-scoped = A, all empty?)'}"
        )
        print(
            f"[PRE-CHECK] Manipulation A vs Q5-guarded: "
            f"{'PASS' if manip_q5 else 'WARN (Q5-guarded = A, all empty?)'}"
        )
        print(
            f"[PRE-CHECK] Manipulation A vs O: "
            f"{'PASS' if manip_o else 'FAIL — Arm O identical to Arm A!'}"
        )
        if not manip_o:
            print("ABORT: Arm O manipulation check failed.")
            return

        # Run all four arms
        print(f"\n[RUN] Arm A ({len(TASKS)} tasks × {trials} trials)...")
        agent_a = OllamaProvider(agent_model)
        results_a = await run_tasks(TASKS, client_a, agent_a, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm A: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm A done. GPU watchdog: clean")

        print(f"\n[RUN] Arm Q4-DOC-scoped ({len(TASKS)} tasks × {trials} trials)...")
        agent_doc = OllamaProvider(agent_model)
        results_doc = await run_tasks(TASKS, client_doc, agent_doc, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm Q4-DOC-scoped: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm Q4-DOC-scoped done. GPU watchdog: clean")

        print(f"\n[RUN] Arm Q5-guarded ({len(TASKS)} tasks × {trials} trials)...")
        agent_q5 = OllamaProvider(agent_model)
        results_q5 = await run_tasks(TASKS, client_q5, agent_q5, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm Q5-guarded: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm Q5-guarded done. GPU watchdog: clean")

        print(f"\n[RUN] Arm O ({len(TASKS)} tasks × {trials} trials)...")
        agent_o = OllamaProvider(agent_model)
        results_o = await run_tasks(TASKS, client_o, agent_o, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm O: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm O done. GPU watchdog: clean")

    finally:
        for ctx in [ctx_a, ctx_doc, ctx_q5, ctx_o]:
            try:
                await cleanup_connection(ctx)
            except BaseException:
                pass

    total = len(results_a)

    # ── Section A: GPU + parse_failed ─────────────────────────────────────────
    pf_a = parse_failed_count(results_a, _VALID_TOOL_NAMES)
    pf_doc = parse_failed_count(results_doc, _VALID_TOOL_NAMES)
    pf_q5 = parse_failed_count(results_q5, _VALID_TOOL_NAMES)
    pf_o = parse_failed_count(results_o, _VALID_TOOL_NAMES)

    print("\n" + "=" * 80)
    print("SECTION A — GPU exclusivity + parse-failed diagnostics")
    print("=" * 80)
    print(f"  GPU: confirmed exclusive (agent-only; watchdog clean at each arm boundary)")
    print(f"  Arm A:              {pf_a}/{total} parse-failed ({100 * pf_a / total if total else 0:.1f}%)")
    print(f"  Arm Q4-DOC-scoped:  {pf_doc}/{total} parse-failed ({100 * pf_doc / total if total else 0:.1f}%)")
    print(f"  Arm Q5-guarded:     {pf_q5}/{total} parse-failed ({100 * pf_q5 / total if total else 0:.1f}%)")
    print(f"  Arm O:              {pf_o}/{total} parse-failed ({100 * pf_o / total if total else 0:.1f}%)")

    # Contested tasks
    contested = identify_contested_indices(results_a, TASKS, trials, _VALID_TOOL_NAMES)
    n_contested = len(contested)
    print(f"\n  Contested tasks (Arm A parse-success == 0%): {n_contested}/{len(TASKS)}")
    if n_contested == 0:
        print("\nABORT: No contested tasks. Arm A saturated — fixture-quality issue.")
        return

    # Per-task accuracy
    per_task_a = [
        parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested
    ]
    per_task_doc = [
        parse_success_accuracy(results_doc, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in contested
    ]
    per_task_q5 = [
        parse_success_accuracy(results_q5, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in contested
    ]
    per_task_o = [
        parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested
    ]

    acc_a = parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_doc = parse_success_accuracy(results_doc, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_q5 = parse_success_accuracy(results_q5, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_o = parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, contested)

    rec_doc = compute_recovery_fraction(acc_doc, acc_a, acc_o)
    rec_q5 = compute_recovery_fraction(acc_q5, acc_a, acc_o)

    deltas_doc_a = [f - a for f, a in zip(per_task_doc, per_task_a, strict=True)]
    deltas_q5_a = [f - a for f, a in zip(per_task_q5, per_task_a, strict=True)]
    deltas_o_a = [o - a for o, a in zip(per_task_o, per_task_a, strict=True)]

    n_plus_doc, n_minus_doc, p_doc = _sign_test(deltas_doc_a)
    n_plus_q5, n_minus_q5, p_q5 = _sign_test(deltas_q5_a)
    n_plus_o, n_minus_o, p_o = _sign_test(deltas_o_a)

    # ── Section B: SAFETY — control tools, Q4-DOC vs Q5 side by side ─────────
    print("\n" + "=" * 80)
    print("SECTION B — SAFETY: Control tools — Q4-DOC-scoped vs Q5-guarded (Guard B)")
    print("=" * 80)
    print(
        "Control pairs: find_entries/lookup_data (control_search), book_slot/plan_event (control_sched)\n"
        "Implementations are ACTUALLY equivalent — generator must NOT invent a distinction.\n"
        "Classification: FAITHFUL-EQUIVALENT / INCIDENTAL-BUT-TRUE / FABRICATED\n"
        "Guard B hypothesis: Q5 MUST NOT contain 'unlike <neighbor>' pattern.\n"
        "The Q4-DOC find_entries->docstring-body-mismatch fabrication MUST NOT recur in Q5.\n"
    )
    for pair in CONTROL_TASK_PAIRS:
        for name in pair:
            oracle_desc = ARM_O_DESCRIPTIONS.get(name, "")
            doc_desc = arm_doc_scoped.get(name, "")
            q5_desc = arm_q5_guarded.get(name, "")
            family = FAMILY_MAP.get(name, "?")
            print(f"  [{family}] {name}")
            print(f"    Oracle:           {oracle_desc}")
            print(f"    Q4-DOC-scoped:    {doc_desc}")
            print(f"    Q5-guarded:       {q5_desc}")
            print(f"    Q4-DOC classification: [ ] FAITHFUL-EQUIVALENT  [ ] INCIDENTAL-BUT-TRUE  [ ] FABRICATED")
            print(f"    Q5 classification:     [ ] FAITHFUL-EQUIVALENT  [ ] INCIDENTAL-BUT-TRUE  [ ] FABRICATED")
            print()
    print("  => Manual review required.")
    print("  ANY FABRICATED on control tools = Guard B UNSAFE.")

    # ── Section C: RECOVERY — four-arm table ──────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION C — RECOVERY: Four-arm result table (parse-success, contested tasks)")
    print("=" * 80)
    print(
        f"{'Family':<16} {'Task (truncated)':<46} {'A%':>5} {'DOC%':>6} {'Q5%':>5} {'O%':>5}"
    )
    print("-" * 83)
    for idx_in_c, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        family = FAMILY_MAP[task.tool_name]
        a_pct = per_task_a[idx_in_c] * 100
        doc_pct = per_task_doc[idx_in_c] * 100
        q5_pct = per_task_q5[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        desc = task.description[:44] + ".." if len(task.description) > 46 else task.description
        print(
            f"{family:<16} {desc:<46} {a_pct:>4.0f}% {doc_pct:>5.0f}% "
            f"{q5_pct:>4.0f}% {o_pct:>4.0f}%"
        )
    print("-" * 83)
    print(
        f"{'AGGREGATE':<16} {'(parse-success, contested)':<46} "
        f"{acc_a * 100:>4.1f}% {acc_doc * 100:>5.1f}% "
        f"{acc_q5 * 100:>4.1f}% {acc_o * 100:>4.1f}%"
    )
    print("=" * 83)

    print(f"\n  Recovery Q4-DOC-scoped (DOC-A)/(O-A): ", end="")
    print(f"{rec_doc:.3f}  ({rec_doc * 100:.1f}%)" if rec_doc is not None else "N/A")
    print(f"  Recovery Q5-guarded   (Q5-A)/(O-A):  ", end="")
    print(f"{rec_q5:.3f}  ({rec_q5 * 100:.1f}%)" if rec_q5 is not None else "N/A")

    print(f"\n  Sign test Q4-DOC-scoped vs A: n+={n_plus_doc} n-={n_minus_doc}  p={p_doc:.4f}")
    print(f"  Sign test Q5-guarded vs A:    n+={n_plus_q5} n-={n_minus_q5}  p={p_q5:.4f}")
    print(f"  Sign test O vs A:             n+={n_plus_o} n-={n_minus_o}  p={p_o:.4f}")

    # ── Section D: Per-task miss diagnosis ────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION D — Per-task miss diagnosis (Q5-guarded < Arm O, focus on Q4-DOC→Q5 regressions)")
    print("=" * 80)
    any_miss = False
    for idx_in_c, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        doc_pct = per_task_doc[idx_in_c] * 100
        q5_pct = per_task_q5[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        if q5_pct >= o_pct:
            continue
        any_miss = True
        family = FAMILY_MAP[task.tool_name]
        token = INDEPENDENCE_TOKENS.get(task.tool_name, "?")
        doc_desc = arm_doc_scoped.get(task.tool_name, "(no description)")
        q5_desc = arm_q5_guarded.get(task.tool_name, "(no description)")
        oracle_desc = ARM_O_DESCRIPTIONS.get(task.tool_name, "")
        print(f"  Task [{family}]: {task.description}")
        print(f"    Gold tool:         {task.tool_name}  (token: {token!r})")
        print(f"    Q4-DOC-scoped:     {doc_desc}")
        print(f"    Q5-guarded:        {q5_desc}")
        print(f"    Oracle:            {oracle_desc}")
        print(f"    DOC%={doc_pct:.0f}%  Q5%={q5_pct:.0f}%  O%={o_pct:.0f}%")
        if doc_pct > q5_pct:
            print(f"    REGRESSION: Q5 scored lower than Q4-DOC — Guard B may have over-constrained.")
        print(f"    Q5 encoded distinction? [ ] YES  [ ] NO — why:")
        print(
            f"    Miss type: [ ] OVER-CONSTRAINED (Guard B blocked valid distinction) "
            f"[ ] ABSENT-FROM-BODY (info not in target body)"
        )
        print()
    if not any_miss:
        print("  All contested tasks: Q5-guarded >= Arm O.")

    # ── Section E: Verdict cell ────────────────────────────────────────────────
    print("=" * 80)
    print("SECTION E — Verdict")
    print("=" * 80)

    q5_recovers = rec_q5 is not None and rec_q5 > 0.30
    doc_recovers = rec_doc is not None and rec_doc > 0.30

    verdict = (
        "Q5 (Guard B) recovers AND maintains recovery parity with Q4-DOC — "
        "docstrings safe with Guard B"
        if q5_recovers and doc_recovers
        else "Q5 (Guard B) recovers but Q4-DOC does not — unexpected, check data"
        if q5_recovers and not doc_recovers
        else "Q5 (Guard B) does NOT recover (≤30%) — Guard B may have over-constrained"
        if not q5_recovers
        else "Mixed — check per-task data"
    )

    print(f"\n  Arm A (empty):        {acc_a * 100:.1f}%  (parse-success, {n_contested} contested)")
    if rec_doc is not None:
        print(f"  Arm Q4-DOC-scoped:    {acc_doc * 100:.1f}%  recovery={rec_doc * 100:.1f}%")
    else:
        print(f"  Arm Q4-DOC-scoped:    {acc_doc * 100:.1f}%  recovery=N/A")
    if rec_q5 is not None:
        print(f"  Arm Q5-guarded:       {acc_q5 * 100:.1f}%  recovery={rec_q5 * 100:.1f}%")
    else:
        print(f"  Arm Q5-guarded:       {acc_q5 * 100:.1f}%  recovery=N/A")
    print(f"  Arm O (oracle):       {acc_o * 100:.1f}%")
    print(f"\n  Verdict: {verdict}")
    print(
        f"\n  Sign test Q4-DOC-scoped vs A: p={p_doc:.4f}  "
        f"({'significant' if p_doc < 0.05 else 'not significant'})"
    )
    print(
        f"  Sign test Q5-guarded vs A:    p={p_q5:.4f}  "
        f"({'significant' if p_q5 < 0.05 else 'not significant'})"
    )
    print(
        "\n  No-fabrication: PENDING MANUAL REVIEW (fill in Section B above)\n"
        "  ANY FABRICATED on control tools = Guard B UNSAFE regardless of recovery."
    )
    print(
        "\n  Verdict interpretations:"
        "\n    Q5 recovers + safe: Guard B is the production-viable DOC-scoped path"
        "\n    Q5 recovers + unsafe: Guard B prompt is insufficient; tighten or post-check"
        "\n    Q5 does not recover: Guard B over-constrained; revise prompt or use BODY-scoped"
        "\n    Any FABRICATED on control -> unsafe regardless of recovery"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Q5 four-arm Guard B experiment (Phase 2)")
    parser.add_argument("--agent-model", default="gemma2:9b")
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials))


if __name__ == "__main__":
    main()
