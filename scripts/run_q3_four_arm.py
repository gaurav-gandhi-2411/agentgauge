#!/usr/bin/env python3
"""Q3 Phase 2 — four-arm source-aware description experiment.

Arms:
  A     — empty descriptions (floor)
  F-DOC — generated from source + docstrings (qwen3:8b, Phase 1)
  F-BODY— generated from source body only, no docstrings (qwen3:8b, Phase 1)
  O     — oracle descriptions derived from reading q3_real_server.py (ceiling)

Metric: parse-success selection_accuracy on contested tasks (Arm A == 0%).
Recovery F-DOC = (F-DOC - A) / (O - A)   [reported separately]
Recovery F-BODY = (F-BODY - A) / (O - A) [reported separately]
No-fabrication control: FAITHFUL/FABRICATED per control tool, both source conditions.

Usage:
    python scripts/run_q3_four_arm.py [--agent-model gemma2:9b] [--trials 5]

Prerequisites:
  - Phase 1 complete: evals/fixtures/q3_arm_f_doc_descriptions.json exists
  - ollama stop, then ollama ps (must be empty) before running
  - Watchdog kills run if any non-gemma2 model loads during Phase 2
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
    get_doc_source,
    get_body_source,
)

_FIXTURE_A = Path(__file__).parent.parent / "examples" / "q3_arm_a.py"
_FIXTURE_F_DOC = Path(__file__).parent.parent / "examples" / "q3_arm_f_doc.py"
_FIXTURE_F_BODY = Path(__file__).parent.parent / "examples" / "q3_arm_f_body.py"
_FIXTURE_O = Path(__file__).parent.parent / "examples" / "q3_arm_o.py"
_ARM_F_DOC_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "q3_arm_f_doc_descriptions.json"
)
_ARM_F_BODY_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "q3_arm_f_body_descriptions.json"
)
_CONTAMINATION_FILE = Path(__file__).parent.parent / "Q3_CONTAMINATED.txt"

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

    # Phase 1 pre-check
    if not _ARM_F_DOC_PATH.exists():
        print("ERROR: q3_arm_f_doc_descriptions.json not found.")
        print("Run Phase 1 first: python scripts/generate_q3_descriptions.py")
        sys.exit(1)
    if not _ARM_F_BODY_PATH.exists():
        print("ERROR: q3_arm_f_body_descriptions.json not found.")
        print("Run Phase 1 first: python scripts/generate_q3_descriptions.py")
        sys.exit(1)

    arm_f_doc: dict[str, str] = json.loads(_ARM_F_DOC_PATH.read_text(encoding="utf-8"))
    arm_f_body: dict[str, str] = json.loads(_ARM_F_BODY_PATH.read_text(encoding="utf-8"))

    print("=" * 80)
    print("Q3 Four-Arm Source-Aware Experiment")
    print(f"Agent: {agent_model}  |  Trials: {trials}")
    print(f"Tasks (pre-registered): {len(TASKS)}  |  Tools: {len(_VALID_TOOL_NAMES)}")
    print(f"F-DOC descriptions: {len(arm_f_doc)}  |  F-BODY descriptions: {len(arm_f_body)}")
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
    client_f_doc, ctx_f_doc = await connect_stdio(python, [str(_FIXTURE_F_DOC)])
    client_f_body, ctx_f_body = await connect_stdio(python, [str(_FIXTURE_F_BODY)])
    client_o, ctx_o = await connect_stdio(python, [str(_FIXTURE_O)])

    try:
        # Manipulation check
        info_a = await client_a.introspect()
        info_f_doc = await client_f_doc.introspect()
        info_f_body = await client_f_body.introspect()
        info_o = await client_o.introspect()

        listing_a = _build_tool_listing(info_a.tools)
        listing_f_doc = _build_tool_listing(info_f_doc.tools)
        listing_f_body = _build_tool_listing(info_f_body.tools)
        listing_o = _build_tool_listing(info_o.tools)

        manip_f_doc = listing_a != listing_f_doc
        manip_f_body = listing_a != listing_f_body
        manip_o = listing_a != listing_o

        print(
            f"[PRE-CHECK] Manipulation A vs F-DOC: "
            f"{'PASS' if manip_f_doc else 'WARN (F-DOC = A, all empty?)'}"
        )
        print(
            f"[PRE-CHECK] Manipulation A vs F-BODY: "
            f"{'PASS' if manip_f_body else 'WARN (F-BODY = A, all empty?)'}"
        )
        print(
            f"[PRE-CHECK] Manipulation A vs O: "
            f"{'PASS' if manip_o else 'FAIL — Arm O identical to Arm A!'}"
        )
        if not manip_o:
            print("ABORT: Arm O manipulation check failed.")
            return

        # Run all four arms sequentially
        for arm_name, client, ctx in [
            ("Arm A", client_a, ctx_a),
            ("Arm F-DOC", client_f_doc, ctx_f_doc),
            ("Arm F-BODY", client_f_body, ctx_f_body),
            ("Arm O", client_o, ctx_o),
        ]:
            print(f"\n[RUN] {arm_name} ({len(TASKS)} tasks × {trials} trials)...")

        # Actually run tasks (connection reuse)
        agent_a = OllamaProvider(agent_model)
        results_a = await run_tasks(TASKS, client_a, agent_a, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm A: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print(f"  Arm A done. GPU watchdog: clean")

        agent_f_doc = OllamaProvider(agent_model)
        results_f_doc = await run_tasks(TASKS, client_f_doc, agent_f_doc, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm F-DOC: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print(f"  Arm F-DOC done. GPU watchdog: clean")

        agent_f_body = OllamaProvider(agent_model)
        results_f_body = await run_tasks(TASKS, client_f_body, agent_f_body, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm F-BODY: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print(f"  Arm F-BODY done. GPU watchdog: clean")

        agent_o = OllamaProvider(agent_model)
        results_o = await run_tasks(TASKS, client_o, agent_o, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm O: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print(f"  Arm O done. GPU watchdog: clean")

    finally:
        for ctx in [ctx_a, ctx_f_doc, ctx_f_body, ctx_o]:
            try:
                await cleanup_connection(ctx)
            except BaseException:
                pass

    total = len(results_a)

    # ── Section A: GPU + parse_failed ─────────────────────────────────────────
    pf_a = parse_failed_count(results_a, _VALID_TOOL_NAMES)
    pf_f_doc = parse_failed_count(results_f_doc, _VALID_TOOL_NAMES)
    pf_f_body = parse_failed_count(results_f_body, _VALID_TOOL_NAMES)
    pf_o = parse_failed_count(results_o, _VALID_TOOL_NAMES)

    print("\n" + "=" * 80)
    print("SECTION A — GPU exclusivity + parse-failed diagnostics")
    print("=" * 80)
    print(f"  GPU: confirmed exclusive (gemma2 only; watchdog clean at each arm boundary)")
    print(f"  Arm A:     {pf_a}/{total} parse-failed ({100 * pf_a / total if total else 0:.1f}%)")
    print(f"  Arm F-DOC: {pf_f_doc}/{total} parse-failed ({100 * pf_f_doc / total if total else 0:.1f}%)")
    print(f"  Arm F-BODY:{pf_f_body}/{total} parse-failed ({100 * pf_f_body / total if total else 0:.1f}%)")
    print(f"  Arm O:     {pf_o}/{total} parse-failed ({100 * pf_o / total if total else 0:.1f}%)")

    # Contested tasks
    contested = identify_contested_indices(results_a, TASKS, trials, _VALID_TOOL_NAMES)
    n_contested = len(contested)
    print(f"\n  Contested tasks (Arm A parse-success == 0%): {n_contested}/{len(TASKS)}")
    if n_contested == 0:
        print("\nABORT: No contested tasks. Arm A saturated — fixture-quality issue.")
        return

    # ── Section B: Four-arm table + recovery + sign tests ─────────────────────
    acc_a = parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_f_doc = parse_success_accuracy(results_f_doc, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_f_body = parse_success_accuracy(results_f_body, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_o = parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, contested)

    rec_f_doc = compute_recovery_fraction(acc_f_doc, acc_a, acc_o)
    rec_f_body = compute_recovery_fraction(acc_f_body, acc_a, acc_o)

    per_task_a = [parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested]
    per_task_f_doc = [parse_success_accuracy(results_f_doc, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested]
    per_task_f_body = [parse_success_accuracy(results_f_body, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested]
    per_task_o = [parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested]

    deltas_doc_a = [f - a for f, a in zip(per_task_f_doc, per_task_a, strict=True)]
    deltas_body_a = [f - a for f, a in zip(per_task_f_body, per_task_a, strict=True)]
    deltas_o_a = [o - a for o, a in zip(per_task_o, per_task_a, strict=True)]

    n_plus_doc, n_minus_doc, p_doc = _sign_test(deltas_doc_a)
    n_plus_body, n_minus_body, p_body = _sign_test(deltas_body_a)
    n_plus_o, n_minus_o, p_o = _sign_test(deltas_o_a)

    print("\n" + "=" * 80)
    print("SECTION B — Four-arm result table (parse-success, contested tasks only)")
    print("=" * 80)
    print(
        f"{'Family':<16} {'Task (truncated)':<46} {'A%':>5} {'DOC%':>6} {'BODY%':>6} {'O%':>5}"
    )
    print("-" * 88)
    for idx_in_c, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        family = FAMILY_MAP[task.tool_name]
        a_pct = per_task_a[idx_in_c] * 100
        doc_pct = per_task_f_doc[idx_in_c] * 100
        body_pct = per_task_f_body[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        desc = task.description[:44] + ".." if len(task.description) > 46 else task.description
        print(f"{family:<16} {desc:<46} {a_pct:>4.0f}% {doc_pct:>5.0f}% {body_pct:>5.0f}% {o_pct:>4.0f}%")
    print("-" * 88)
    print(
        f"{'AGGREGATE':<16} {'(parse-success, contested)':<46} "
        f"{acc_a * 100:>4.1f}% {acc_f_doc * 100:>5.1f}% {acc_f_body * 100:>5.1f}% {acc_o * 100:>4.1f}%"
    )
    print("=" * 88)

    print(f"\n  Recovery F-DOC  (F-DOC-A)/(O-A):  ", end="")
    print(f"{rec_f_doc:.3f}  ({rec_f_doc * 100:.1f}%)" if rec_f_doc is not None else "N/A")
    print(f"  Recovery F-BODY (F-BODY-A)/(O-A): ", end="")
    print(f"{rec_f_body:.3f}  ({rec_f_body * 100:.1f}%)" if rec_f_body is not None else "N/A")

    print(f"\n  Sign test F-DOC vs A:  n+={n_plus_doc} n-={n_minus_doc}  p={p_doc:.4f}")
    print(f"  Sign test F-BODY vs A: n+={n_plus_body} n-={n_minus_body}  p={p_body:.4f}")
    print(f"  Sign test O vs A:      n+={n_plus_o} n-={n_minus_o}  p={p_o:.4f}")

    # ── Section C: No-fabrication control ─────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION C — NO-FABRICATION control (genuinely equivalent tool pairs)")
    print("=" * 80)
    print(
        "Control pairs: find_entries/lookup_data (control_search), book_slot/plan_event (control_sched)\n"
        "Implementations are ACTUALLY equivalent — generator must NOT invent a distinction.\n"
        "Classification: FAITHFUL = plain description; FABRICATED = invented distinction\n"
    )
    for pair in CONTROL_TASK_PAIRS:
        for name in pair:
            oracle_desc = ARM_O_DESCRIPTIONS.get(name, "")
            doc_desc = arm_f_doc.get(name, "")
            body_desc = arm_f_body.get(name, "")
            family = FAMILY_MAP.get(name, "?")
            print(f"  [{family}] {name}")
            print(f"    Oracle:  {oracle_desc}")
            print(f"    F-DOC:   {doc_desc}")
            print(f"    F-BODY:  {body_desc}")
            print(f"    F-DOC classification:  [ ] FAITHFUL  [ ] FABRICATED")
            print(f"    F-BODY classification: [ ] FAITHFUL  [ ] FABRICATED")
            print()
    print("  => Manual review required. ANY FABRICATED = overall FAIL.")

    # ── Section D: Per-task diagnosis ─────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION D — Per-task diagnosis (F-DOC or F-BODY < Arm O)")
    print("=" * 80)
    any_miss = False
    for idx_in_c, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        doc_pct = per_task_f_doc[idx_in_c] * 100
        body_pct = per_task_f_body[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        if doc_pct >= o_pct and body_pct >= o_pct:
            continue
        any_miss = True
        family = FAMILY_MAP[task.tool_name]
        token = INDEPENDENCE_TOKENS.get(task.tool_name, "?")
        doc_desc = arm_f_doc.get(task.tool_name, "(no description)")
        body_desc = arm_f_body.get(task.tool_name, "(no description)")
        oracle_desc = ARM_O_DESCRIPTIONS.get(task.tool_name, "")
        print(f"  Task [{family}]: {task.description}")
        print(f"    Gold tool:       {task.tool_name}  (token: {token!r})")
        print(f"    F-DOC desc:      {doc_desc}")
        print(f"    F-BODY desc:     {body_desc}")
        print(f"    Oracle desc:     {oracle_desc}")
        print(f"    DOC%={doc_pct:.0f}%  BODY%={body_pct:.0f}%  O%={o_pct:.0f}%")
        print(f"    F-DOC encoded distinction? [ ] YES  [ ] NO — why:")
        print(f"    F-BODY encoded distinction? [ ] YES  [ ] NO — why:")
        print()
    if not any_miss:
        print("  All contested tasks: F-DOC and F-BODY both >= Arm O.")

    # ── Section E: Verdict matrix ──────────────────────────────────────────────
    print("=" * 80)
    print("SECTION E — Verdict matrix")
    print("=" * 80)

    both_recover = (rec_f_doc is not None and rec_f_doc > 0.30) and (
        rec_f_body is not None and rec_f_body > 0.30
    )
    doc_only = (rec_f_doc is not None and rec_f_doc > 0.30) and (
        rec_f_body is None or rec_f_body <= 0.30
    )
    neither = (rec_f_doc is None or rec_f_doc <= 0.30) and (
        rec_f_body is None or rec_f_body <= 0.30
    )

    verdict_matrix = (
        "F-DOC + F-BODY both recover (>30%)" if both_recover
        else "F-DOC recovers, F-BODY does not" if doc_only
        else "Neither F-DOC nor F-BODY recovers (≤30%)" if neither
        else "Mixed (unusual — check per-task data)"
    )

    print(f"\n  Arm A (empty):       {acc_a * 100:.1f}%  (parse-success, {n_contested} contested)")
    print(f"  Arm F-DOC:           {acc_f_doc * 100:.1f}%  recovery={rec_f_doc * 100:.1f}%" if rec_f_doc else f"  Arm F-DOC:           {acc_f_doc * 100:.1f}%  recovery=N/A")
    print(f"  Arm F-BODY:          {acc_f_body * 100:.1f}%  recovery={rec_f_body * 100:.1f}%" if rec_f_body else f"  Arm F-BODY:          {acc_f_body * 100:.1f}%  recovery=N/A")
    print(f"  Arm O (oracle):      {acc_o * 100:.1f}%")
    print(f"\n  Verdict matrix cell: {verdict_matrix}")
    print(f"\n  Sign test F-DOC vs A: p={p_doc:.4f}  ({'significant' if p_doc < 0.05 else 'not significant'})")
    print(f"  Sign test F-BODY vs A: p={p_body:.4f}  ({'significant' if p_body < 0.05 else 'not significant'})")
    print(
        "\n  No-fabrication: PENDING MANUAL REVIEW (fill in Section C above)\n"
        "  ANY FABRICATED on control tools = unsafe regardless of recovery."
    )
    print(
        "\n  Verdict interpretations:"
        "\n    Both recover (>30%): source-inference works even undocumented — strongest claim"
        "\n    DOC only: generator needs documented source; can't infer from bare code"
        "\n    Neither: even source can't be turned into discriminating descriptions by this generator"
        "\n    Any FABRICATED on control -> unsafe regardless of recovery"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Q3 four-arm source-aware experiment (Phase 2)")
    parser.add_argument("--agent-model", default="gemma2:9b")
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials))


if __name__ == "__main__":
    main()
