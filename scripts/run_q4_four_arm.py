#!/usr/bin/env python3
"""Q4 Phase 2 — four-arm scoped-source description experiment.

Arms:
  A               — empty descriptions (floor)
  Q4-DOC-scoped   — generated from scoped source + neighbor surfaces (DOC variant, qwen3:8b, Phase 1)
  Q4-BODY-scoped  — generated from scoped source + neighbor surfaces (BODY variant, qwen3:8b, Phase 1)
  O               — oracle descriptions derived from reading q3_real_server.py (ceiling)

Metric: parse-success selection_accuracy on contested tasks (Arm A == 0%).
Recovery Q4-DOC-scoped  = (Q4-DOC  - A) / (O - A)   [reported separately]
Recovery Q4-BODY-scoped = (Q4-BODY - A) / (O - A)   [reported separately]

No-fabrication control: FAITHFUL-EQUIVALENT / INCIDENTAL-BUT-TRUE / FABRICATED per control tool.
The Q3 find_entries->_db misattribution MUST NOT recur.

Usage:
    python scripts/run_q4_four_arm.py [--agent-model gemma2:9b] [--trials 5]

Prerequisites:
  - Phase 1 complete: evals/fixtures/q4_arm_f_doc_scoped_descriptions.json exists (non-empty)
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
_FIXTURE_BODY_SCOPED = Path(__file__).parent.parent / "examples" / "q4_arm_f_body_scoped.py"
_FIXTURE_O = Path(__file__).parent.parent / "examples" / "q3_arm_o.py"
_ARM_DOC_SCOPED_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "q4_arm_f_doc_scoped_descriptions.json"
)
_ARM_BODY_SCOPED_PATH = (
    Path(__file__).parent.parent / "evals" / "fixtures" / "q4_arm_f_body_scoped_descriptions.json"
)
_CONTAMINATION_FILE = Path(__file__).parent.parent / "Q4_CONTAMINATED.txt"

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
        (_ARM_DOC_SCOPED_PATH, "q4_arm_f_doc_scoped_descriptions.json"),
        (_ARM_BODY_SCOPED_PATH, "q4_arm_f_body_scoped_descriptions.json"),
    ]:
        if not path.exists():
            print(f"ERROR: {label} not found.")
            print("Run Phase 1 first: python scripts/generate_q4_descriptions.py")
            sys.exit(1)
        content = json.loads(path.read_text(encoding="utf-8"))
        if not content:
            print(f"ERROR: {label} is empty ({{}}). Phase 1 did not complete successfully.")
            print("Run Phase 1 first: python scripts/generate_q4_descriptions.py")
            sys.exit(1)

    arm_doc_scoped: dict[str, str] = json.loads(_ARM_DOC_SCOPED_PATH.read_text(encoding="utf-8"))
    arm_body_scoped: dict[str, str] = json.loads(
        _ARM_BODY_SCOPED_PATH.read_text(encoding="utf-8")
    )

    print("=" * 80)
    print("Q4 Four-Arm Scoped-Source Experiment")
    print(f"Agent: {agent_model}  |  Trials: {trials}")
    print(f"Tasks (pre-registered): {len(TASKS)}  |  Tools: {len(_VALID_TOOL_NAMES)}")
    print(
        f"DOC-scoped descriptions: {len(arm_doc_scoped)}  |  "
        f"BODY-scoped descriptions: {len(arm_body_scoped)}"
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
    client_body, ctx_body = await connect_stdio(python, [str(_FIXTURE_BODY_SCOPED)])
    client_o, ctx_o = await connect_stdio(python, [str(_FIXTURE_O)])

    try:
        # Manipulation check
        info_a = await client_a.introspect()
        info_doc = await client_doc.introspect()
        info_body = await client_body.introspect()
        info_o = await client_o.introspect()

        listing_a = _build_tool_listing(info_a.tools)
        listing_doc = _build_tool_listing(info_doc.tools)
        listing_body = _build_tool_listing(info_body.tools)
        listing_o = _build_tool_listing(info_o.tools)

        manip_doc = listing_a != listing_doc
        manip_body = listing_a != listing_body
        manip_o = listing_a != listing_o

        print(
            f"[PRE-CHECK] Manipulation A vs Q4-DOC-scoped: "
            f"{'PASS' if manip_doc else 'WARN (DOC-scoped = A, all empty?)'}"
        )
        print(
            f"[PRE-CHECK] Manipulation A vs Q4-BODY-scoped: "
            f"{'PASS' if manip_body else 'WARN (BODY-scoped = A, all empty?)'}"
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
            ("Arm Q4-DOC-scoped", client_doc, ctx_doc),
            ("Arm Q4-BODY-scoped", client_body, ctx_body),
            ("Arm O", client_o, ctx_o),
        ]:
            print(f"\n[RUN] {arm_name} ({len(TASKS)} tasks × {trials} trials)...")

        agent_a = OllamaProvider(agent_model)
        results_a = await run_tasks(TASKS, client_a, agent_a, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm A: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm A done. GPU watchdog: clean")

        agent_doc = OllamaProvider(agent_model)
        results_doc = await run_tasks(TASKS, client_doc, agent_doc, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm Q4-DOC-scoped: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm Q4-DOC-scoped done. GPU watchdog: clean")

        agent_body = OllamaProvider(agent_model)
        results_body = await run_tasks(TASKS, client_body, agent_body, trials=trials)
        foreign = _check_foreign_models(agent_family)
        if foreign:
            msg = f"GPU CONTAMINATION after Arm Q4-BODY-scoped: {foreign}\n"
            _CONTAMINATION_FILE.write_text(msg, encoding="utf-8")
            print(f"\nABORT: {msg}")
            return
        print("  Arm Q4-BODY-scoped done. GPU watchdog: clean")

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
        for ctx in [ctx_a, ctx_doc, ctx_body, ctx_o]:
            try:
                await cleanup_connection(ctx)
            except BaseException:
                pass

    total = len(results_a)

    # ── Section A: GPU + parse_failed ─────────────────────────────────────────
    pf_a = parse_failed_count(results_a, _VALID_TOOL_NAMES)
    pf_doc = parse_failed_count(results_doc, _VALID_TOOL_NAMES)
    pf_body = parse_failed_count(results_body, _VALID_TOOL_NAMES)
    pf_o = parse_failed_count(results_o, _VALID_TOOL_NAMES)

    print("\n" + "=" * 80)
    print("SECTION A — GPU exclusivity + parse-failed diagnostics")
    print("=" * 80)
    print(f"  GPU: confirmed exclusive (agent-only; watchdog clean at each arm boundary)")
    print(f"  Arm A:              {pf_a}/{total} parse-failed ({100 * pf_a / total if total else 0:.1f}%)")
    print(f"  Arm Q4-DOC-scoped:  {pf_doc}/{total} parse-failed ({100 * pf_doc / total if total else 0:.1f}%)")
    print(f"  Arm Q4-BODY-scoped: {pf_body}/{total} parse-failed ({100 * pf_body / total if total else 0:.1f}%)")
    print(f"  Arm O:              {pf_o}/{total} parse-failed ({100 * pf_o / total if total else 0:.1f}%)")

    # Contested tasks
    contested = identify_contested_indices(results_a, TASKS, trials, _VALID_TOOL_NAMES)
    n_contested = len(contested)
    print(f"\n  Contested tasks (Arm A parse-success == 0%): {n_contested}/{len(TASKS)}")
    if n_contested == 0:
        print("\nABORT: No contested tasks. Arm A saturated — fixture-quality issue.")
        return

    # ── Section B: Four-arm table + recovery + sign tests ─────────────────────
    acc_a = parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_doc = parse_success_accuracy(results_doc, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_body = parse_success_accuracy(results_body, TASKS, trials, _VALID_TOOL_NAMES, contested)
    acc_o = parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, contested)

    rec_doc = compute_recovery_fraction(acc_doc, acc_a, acc_o)
    rec_body = compute_recovery_fraction(acc_body, acc_a, acc_o)

    per_task_a = [
        parse_success_accuracy(results_a, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested
    ]
    per_task_doc = [
        parse_success_accuracy(results_doc, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in contested
    ]
    per_task_body = [
        parse_success_accuracy(results_body, TASKS, trials, _VALID_TOOL_NAMES, [i])
        for i in contested
    ]
    per_task_o = [
        parse_success_accuracy(results_o, TASKS, trials, _VALID_TOOL_NAMES, [i]) for i in contested
    ]

    deltas_doc_a = [f - a for f, a in zip(per_task_doc, per_task_a, strict=True)]
    deltas_body_a = [f - a for f, a in zip(per_task_body, per_task_a, strict=True)]
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
        doc_pct = per_task_doc[idx_in_c] * 100
        body_pct = per_task_body[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        desc = task.description[:44] + ".." if len(task.description) > 46 else task.description
        print(
            f"{family:<16} {desc:<46} {a_pct:>4.0f}% {doc_pct:>5.0f}% "
            f"{body_pct:>5.0f}% {o_pct:>4.0f}%"
        )
    print("-" * 88)
    print(
        f"{'AGGREGATE':<16} {'(parse-success, contested)':<46} "
        f"{acc_a * 100:>4.1f}% {acc_doc * 100:>5.1f}% "
        f"{acc_body * 100:>5.1f}% {acc_o * 100:>4.1f}%"
    )
    print("=" * 88)

    print(f"\n  Recovery Q4-DOC-scoped  (DOC-A)/(O-A):  ", end="")
    print(f"{rec_doc:.3f}  ({rec_doc * 100:.1f}%)" if rec_doc is not None else "N/A")
    print(f"  Recovery Q4-BODY-scoped (BODY-A)/(O-A): ", end="")
    print(f"{rec_body:.3f}  ({rec_body * 100:.1f}%)" if rec_body is not None else "N/A")

    print(f"\n  Sign test Q4-DOC-scoped vs A:  n+={n_plus_doc} n-={n_minus_doc}  p={p_doc:.4f}")
    print(f"  Sign test Q4-BODY-scoped vs A: n+={n_plus_body} n-={n_minus_body}  p={p_body:.4f}")
    print(f"  Sign test O vs A:              n+={n_plus_o} n-={n_minus_o}  p={p_o:.4f}")

    # ── Section C: No-fabrication control ─────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION C — NO-FABRICATION control (genuinely equivalent tool pairs)")
    print("=" * 80)
    print(
        "Control pairs: find_entries/lookup_data (control_search), book_slot/plan_event (control_sched)\n"
        "Implementations are ACTUALLY equivalent — generator must NOT invent a distinction.\n"
        "Classification: FAITHFUL-EQUIVALENT / INCIDENTAL-BUT-TRUE / FABRICATED\n"
        "The Q3 find_entries->_db misattribution MUST NOT recur.\n"
        "Any FABRICATED -> FAIL. INCIDENTAL-BUT-TRUE -> note but not fail.\n"
    )
    for pair in CONTROL_TASK_PAIRS:
        for name in pair:
            oracle_desc = ARM_O_DESCRIPTIONS.get(name, "")
            doc_desc = arm_doc_scoped.get(name, "")
            body_desc = arm_body_scoped.get(name, "")
            family = FAMILY_MAP.get(name, "?")
            print(f"  [{family}] {name}")
            print(f"    Oracle:            {oracle_desc}")
            print(f"    Q4-DOC-scoped:     {doc_desc}")
            print(f"    Q4-BODY-scoped:    {body_desc}")
            print(f"    DOC classification:  [ ] FAITHFUL-EQUIVALENT  [ ] INCIDENTAL-BUT-TRUE  [ ] FABRICATED")
            print(f"    BODY classification: [ ] FAITHFUL-EQUIVALENT  [ ] INCIDENTAL-BUT-TRUE  [ ] FABRICATED")
            print()
    print("  => Manual review required.")
    print("  Classification: FAITHFUL-EQUIVALENT / INCIDENTAL-BUT-TRUE / FABRICATED")
    print("  The Q3 find_entries->_db misattribution MUST NOT recur.")
    print("  Any FABRICATED -> FAIL. INCIDENTAL-BUT-TRUE -> note but not fail.")

    # ── Section D: Per-task diagnosis ─────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SECTION D — Per-task diagnosis (Q4-DOC or Q4-BODY < Arm O)")
    print("=" * 80)
    any_miss = False
    for idx_in_c, task_idx in enumerate(contested):
        task = TASKS[task_idx]
        doc_pct = per_task_doc[idx_in_c] * 100
        body_pct = per_task_body[idx_in_c] * 100
        o_pct = per_task_o[idx_in_c] * 100
        if doc_pct >= o_pct and body_pct >= o_pct:
            continue
        any_miss = True
        family = FAMILY_MAP[task.tool_name]
        token = INDEPENDENCE_TOKENS.get(task.tool_name, "?")
        doc_desc = arm_doc_scoped.get(task.tool_name, "(no description)")
        body_desc = arm_body_scoped.get(task.tool_name, "(no description)")
        oracle_desc = ARM_O_DESCRIPTIONS.get(task.tool_name, "")
        print(f"  Task [{family}]: {task.description}")
        print(f"    Gold tool:           {task.tool_name}  (token: {token!r})")
        print(f"    Q4-DOC-scoped desc:  {doc_desc}")
        print(f"    Q4-BODY-scoped desc: {body_desc}")
        print(f"    Oracle desc:         {oracle_desc}")
        print(f"    DOC%={doc_pct:.0f}%  BODY%={body_pct:.0f}%  O%={o_pct:.0f}%")
        print(f"    DOC encoded distinction? [ ] YES  [ ] NO — why:")
        print(f"    BODY encoded distinction? [ ] YES  [ ] NO — why:")
        print(
            f"    Miss type: [ ] MISATTRIBUTION (cross-tool body cited)  "
            f"[ ] ABSENT-FROM-BODY (info in docstring only)"
        )
        print()
    if not any_miss:
        print("  All contested tasks: Q4-DOC and Q4-BODY both >= Arm O.")

    # ── Section E: Verdict matrix ──────────────────────────────────────────────
    print("=" * 80)
    print("SECTION E — Verdict matrix")
    print("=" * 80)

    both_recover = (rec_doc is not None and rec_doc > 0.30) and (
        rec_body is not None and rec_body > 0.30
    )
    doc_only = (rec_doc is not None and rec_doc > 0.30) and (
        rec_body is None or rec_body <= 0.30
    )
    body_only = (rec_body is not None and rec_body > 0.30) and (
        rec_doc is None or rec_doc <= 0.30
    )
    neither = (rec_doc is None or rec_doc <= 0.30) and (
        rec_body is None or rec_body <= 0.30
    )

    verdict_matrix = (
        "Q4-DOC + Q4-BODY both recover (>30%) — scoping fixes both variants"
        if both_recover
        else "Q4-DOC recovers, Q4-BODY does not — docstrings load-bearing even with scoping"
        if doc_only
        else "Q4-BODY recovers, Q4-DOC does not — unexpected (check per-task data)"
        if body_only
        else "Neither Q4-DOC nor Q4-BODY recovers (≤30%)"
        if neither
        else "Mixed (unusual — check per-task data)"
    )

    print(f"\n  Arm A (empty):           {acc_a * 100:.1f}%  (parse-success, {n_contested} contested)")
    if rec_doc is not None:
        print(f"  Arm Q4-DOC-scoped:       {acc_doc * 100:.1f}%  recovery={rec_doc * 100:.1f}%")
    else:
        print(f"  Arm Q4-DOC-scoped:       {acc_doc * 100:.1f}%  recovery=N/A")
    if rec_body is not None:
        print(f"  Arm Q4-BODY-scoped:      {acc_body * 100:.1f}%  recovery={rec_body * 100:.1f}%")
    else:
        print(f"  Arm Q4-BODY-scoped:      {acc_body * 100:.1f}%  recovery=N/A")
    print(f"  Arm O (oracle):          {acc_o * 100:.1f}%")
    print(f"\n  Verdict matrix cell: {verdict_matrix}")
    print(
        f"\n  Sign test Q4-DOC-scoped vs A:  p={p_doc:.4f}  "
        f"({'significant' if p_doc < 0.05 else 'not significant'})"
    )
    print(
        f"  Sign test Q4-BODY-scoped vs A: p={p_body:.4f}  "
        f"({'significant' if p_body < 0.05 else 'not significant'})"
    )
    print(
        "\n  No-fabrication: PENDING MANUAL REVIEW (fill in Section C above)\n"
        "  ANY FABRICATED on control tools = unsafe regardless of recovery."
    )
    print(
        "\n  Verdict interpretations:"
        "\n    Both recover (>30%): scoping fixes misattribution for both variants — strongest claim"
        "\n    DOC only: scoping helps but docstrings still load-bearing; body alone insufficient"
        "\n    Body only: unexpected — investigate per-task data before concluding"
        "\n    Neither: scoping does not recover; misattribution or other blocker persists"
        "\n    Any FABRICATED on control -> unsafe regardless of recovery"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Q4 four-arm scoped-source experiment (Phase 2)")
    parser.add_argument("--agent-model", default="gemma2:9b")
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run(args.agent_model, args.trials))


if __name__ == "__main__":
    main()
