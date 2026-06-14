#!/usr/bin/env python3
"""P2-A headroom gate + A-vs-Oracle comparison on Llama-3.3-70B via Groq.

Two modes:
  gate (default): Arm A only, 31 contested tasks × N trials. Reports per-family
                  accuracy and whether the headroom gate (85%) passes.
  ab:             Arm A + Oracle, 31 × N trials each. Reports per-family A% and O%
                  (the ceiling gap) and per-family delta. Use after gate passes.

Usage:
    GROQ_API_KEY=<key> python scripts/p2a_frontier_gate.py [--trials 1] [--mode gate|ab]

Token budget:
    gate, 1 trial:  31 tasks  × ~200 tok = ~6 200 tok  (~1 min, $0 free tier)
    ab,   3 trials: 186 calls × ~200 tok = ~37 200 tok (~3 min, $0 free tier)

Groq free tier: 12k tokens/min (binding). Script holds output under 9k tok/min.
If 429s occur, the caller backs off using retry-after headers (no thrash).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from evals.fixtures.p2a_internal_proxy_catalog import (
    ARM_A_DESCRIPTIONS,
    ARM_O_DESCRIPTIONS,
    CONTESTED_TOOLS,
    FAMILIES,
    FAMILY_MAP,
    TASKS,
    TOOL_SCHEMAS,
)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"
_HEADROOM_GATE = 0.85
# Hold output under this tok/min (Groq free tier: 12k/min) — 429-proof margin.
_TARGET_TPM = 9_000

_ALL_TOOLS: frozenset[str] = frozenset(ARM_A_DESCRIPTIONS)
_CONTESTED_TASK_INDICES: list[int] = [
    i for i, t in enumerate(TASKS) if t.tool_name in CONTESTED_TOOLS
]


# ── Tool listings (matches _build_tool_listing format from runner.py) ─────────

def _build_listing(descriptions: dict[str, str]) -> str:
    """Build text listing: 'name — desc | param:type, ...' from a descriptions dict."""
    lines = []
    for tool_name, desc in descriptions.items():
        schema = TOOL_SCHEMAS.get(tool_name, {})
        props = schema.get("properties", {})
        param_parts = []
        for pname, pschema in props.items():
            ptype = pschema.get("type", "")
            param_parts.append(f"{pname}:{ptype}" if ptype else pname)
        param_str = ", ".join(param_parts) if param_parts else "(no params)"
        lines.append(f"{tool_name} — {desc} | {param_str}")
    return "\n".join(lines)


# ── Response classifier ────────────────────────────────────────────────────────

def _classify(raw: str, gold: str) -> str:
    """Returns 'CORRECT', 'WRONG', or 'ABSTAIN'."""
    if not raw.strip():
        return "ABSTAIN"
    ft = raw.strip().split()[0].rstrip(".,;:!?")
    if ft not in _ALL_TOOLS:
        return "ABSTAIN"
    return "CORRECT" if ft == gold else "WRONG"


# ── Groq caller (header-driven pacing, mirrors analyze_frontier_t18.py) ───────

def _parse_duration(s: str | None) -> float:
    """Parse Groq reset strings like '25.855s', '200ms', '2h18m14.4s' -> seconds."""
    if not s:
        return 60.0
    total = 0.0
    for val, unit in re.findall(r"([\d.]+)\s*(ms|h|m|s)", s):
        total += float(val) * {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}[unit]
    return total or 60.0


class PacedGroq:
    """Fixed-interval paced Groq caller. Tracks calls and backs off on 429."""

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self.calls = 0

    async def _gate(self, est_tokens: int) -> None:
        await asyncio.sleep(est_tokens / _TARGET_TPM * 60.0)

    async def chat_text(self, content: str) -> str:
        est = len(content) // 4 + 16
        await self._gate(est)
        payload = {
            "model": _MODEL,
            "max_tokens": 32,
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self._key}",
        }
        for _ in range(15):
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(_GROQ_URL, headers=headers, json=payload)
            if resp.status_code == 429:
                ra = resp.headers.get("retry-after")
                wait = (
                    float(ra)
                    if ra
                    else _parse_duration(resp.headers.get("x-ratelimit-reset-tokens"))
                )
                # Cap at 75s so we wait out the full 60s TPM window (not 20s, which
                # retries before the window resets and chains 429s).
                clamped = min(75.0, max(2.0, wait))
                print(f"  [429] backing off {clamped:.1f}s", flush=True)
                await asyncio.sleep(clamped + 0.5)
                continue
            resp.raise_for_status()
            data = resp.json()
            self.calls += 1
            return data["choices"][0]["message"]["content"]
        raise RuntimeError("Groq 429 retries exhausted (15 attempts).")


# ── Main ───────────────────────────────────────────────────────────────────────

def _run_arm(
    contested_tasks: list[tuple[int, object]],
    listing: str,
    caller: PacedGroq,
    trials: int,
    label: str,
) -> list[tuple[int, object, str, str]]:
    """Blocking (awaitable) runner for one arm. Returns list of (task_idx, task, outcome, raw)."""
    # Note: this is a sync helper; the caller awaits inside the async context via run_arm().
    raise NotImplementedError("use run_arm() coroutine instead")


async def _run_arm_async(
    contested_tasks: list[tuple[int, object]],
    listing: str,
    caller: PacedGroq,
    trials: int,
    label: str,
) -> list[tuple[int, object, str, str]]:
    records: list[tuple[int, object, str, str]] = []
    total = len(contested_tasks) * trials
    done = 0
    for task_idx, task in contested_tasks:
        for _ in range(trials):
            content = (
                f"Available tools:\n{listing}\n\n"
                f"Task: {task.description}\n"
                "Reply with ONLY the tool name to call, nothing else."
            )
            raw = await caller.chat_text(content)
            outcome = _classify(raw, task.tool_name)
            records.append((task_idx, task, outcome, raw))
            done += 1
            status = "OK" if outcome == "CORRECT" else ("??" if outcome == "ABSTAIN" else "XX")
            print(
                f"  [{label}] {status} [{task.tool_name:<28}] "
                f"-> {raw.strip()[:36]!r:<38} {outcome}  ({done}/{total})",
                flush=True,
            )
    return records


def _agg(records: list[tuple[int, object, str, str]]) -> tuple[int, int, float]:
    """Returns (n_correct, n_parse_success, accuracy)."""
    n_ps = sum(1 for _, _, o, _ in records if o != "ABSTAIN")
    n_correct = sum(1 for _, _, o, _ in records if o == "CORRECT")
    return n_correct, n_ps, n_correct / n_ps if n_ps > 0 else 0.0


def _family_acc(
    records: list[tuple[int, object, str, str]], family_tools: list[str]
) -> tuple[int, int, float]:
    fam = [
        (o, raw) for _, task, o, raw in records
        if task.tool_name in family_tools and task.tool_name in CONTESTED_TOOLS
    ]
    fam_ps = [(o, raw) for o, raw in fam if o != "ABSTAIN"]
    n_correct = sum(1 for o, _ in fam_ps if o == "CORRECT")
    n_total = len(fam_ps)
    return n_correct, n_total, n_correct / n_total if n_total > 0 else 0.0


async def run(trials: int, mode: str) -> None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise SystemExit("GROQ_API_KEY not set. Export it and retry.")

    listing_a = _build_listing(ARM_A_DESCRIPTIONS)
    listing_o = _build_listing(ARM_O_DESCRIPTIONS)
    caller = PacedGroq(key)

    contested_tasks = [(i, TASKS[i]) for i in _CONTESTED_TASK_INDICES]
    n_contested = len(contested_tasks)
    arms = 2 if mode == "ab" else 1
    est_tokens = n_contested * trials * arms * 200

    print("=" * 80)
    print(f"P2-A Frontier {'A-vs-Oracle' if mode == 'ab' else 'Arm A Gate'} — Llama-3.3-70B / Groq")
    print(f"Model: {_MODEL}  |  Mode: {mode}  |  Trials: {trials}")
    print(f"Contested tasks: {n_contested}  |  Total calls: {n_contested * trials * arms}")
    print(f"Est. tokens: ~{est_tokens:,}  |  Gate threshold: {_HEADROOM_GATE * 100:.0f}%")
    print("=" * 80)

    # ── Arm A ─────────────────────────────────────────────────────────────────
    print("\n[ARM A] Thin descriptions...")
    records_a = await _run_arm_async(contested_tasks, listing_a, caller, trials, "A")

    n_correct_a, n_ps_a, agg_a = _agg(records_a)
    n_abstain_a = sum(1 for _, _, o, _ in records_a if o == "ABSTAIN")

    print("\n" + "=" * 80)
    print("RESULTS — Arm A (thin descriptions)")
    print("=" * 80)
    print(
        f"\n  Aggregate contested accuracy: {agg_a * 100:.1f}%  "
        f"({n_correct_a}/{n_ps_a} parse-success)  |  ABSTAIN: {n_abstain_a}"
    )
    print(f"\n  Headroom gate ({_HEADROOM_GATE * 100:.0f}%): ", end="")
    if agg_a >= _HEADROOM_GATE:
        print(
            f"NO HEADROOM — {agg_a * 100:.1f}% >= {_HEADROOM_GATE * 100:.0f}%\n"
            "  70B resolves contested tasks from thin descriptions alone.\n"
            "  Guard-B has little to recover. Effect is weak-agent-bound at this model tier."
        )
        if mode != "ab":
            print(f"\n  Groq calls made: {caller.calls}")
            return
    else:
        recoverable = (1 - agg_a) * 100
        print(
            f"HEADROOM EXISTS — ~{recoverable:.0f}pp recoverable "
            f"({agg_a * 100:.1f}% < {_HEADROOM_GATE * 100:.0f}%)\n"
            f"  NOTE: modest headroom — model already resolves {agg_a * 100:.0f}% "
            "of contested tasks from thin descriptions alone.\n"
            "  Thin-but-present docs + task context get most of the way; Guard-B targets the gap."
        )

    # ── Per-family Arm A breakdown ─────────────────────────────────────────────
    print("\n  Per-family Arm A (thin descriptions):")
    print(f"  {'Family':<28} {'n':>6} {'Correct':>8} {'A%':>8}")
    print("  " + "-" * 56)
    for family_name, family_tools in FAMILIES.items():
        nc, nt, facc = _family_acc(records_a, family_tools)
        if nt == 0:
            continue
        print(f"  {family_name:<28} {nt:>6} {nc:>8} {facc * 100:>7.1f}%")
    print("  " + "=" * 56)

    if mode != "ab":
        print(f"\n  Groq calls made: {caller.calls}")
        return

    # ── Arm O (Oracle) ─────────────────────────────────────────────────────────
    print("\n[ARM O] Oracle descriptions...")
    records_o = await _run_arm_async(contested_tasks, listing_o, caller, trials, "O")

    n_correct_o, n_ps_o, agg_o = _agg(records_o)
    n_abstain_o = sum(1 for _, _, o, _ in records_o if o == "ABSTAIN")

    print("\n" + "=" * 80)
    print("RESULTS — A vs Oracle comparison (Llama-3.3-70B, contested tasks)")
    print("=" * 80)
    print(
        f"\n  Arm A (thin):    {agg_a * 100:.1f}%  ({n_correct_a}/{n_ps_a})"
    )
    print(
        f"  Arm O (oracle):  {agg_o * 100:.1f}%  ({n_correct_o}/{n_ps_o})"
    )
    gap = (agg_o - agg_a) * 100
    print(f"  Oracle gap (O-A): {gap:+.1f}pp  (ceiling on Guard-B recovery)")
    if abs(1.0 - agg_a) > 1e-9:
        recovery_ceiling = (agg_o - agg_a) / (1.0 - agg_a)
        print(f"  Recovery ceiling: {recovery_ceiling * 100:.1f}%  ((O-A)/(1-A))")

    # ── Per-family A vs O ──────────────────────────────────────────────────────
    print("\n  Per-family A vs Oracle (Llama-3.3-70B, contested tasks):")
    print(f"  {'Family':<28} {'n':>6} {'A%':>8} {'O%':>8} {'O-A':>8}")
    print("  " + "-" * 66)
    for family_name, family_tools in FAMILIES.items():
        nc_a, nt_a, facc_a = _family_acc(records_a, family_tools)
        nc_o, nt_o, facc_o = _family_acc(records_o, family_tools)
        if nt_a == 0:
            continue
        delta = (facc_o - facc_a) * 100
        print(
            f"  {family_name:<28} {nt_a:>6} {facc_a * 100:>7.1f}% "
            f"{facc_o * 100:>7.1f}% {delta:>+7.1f}pp"
        )
    print("  " + "=" * 66)
    print(f"\n  Groq calls made: {caller.calls}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P2-A headroom gate + A-vs-Oracle comparison on Llama-3.3-70B via Groq"
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Trials per contested task per arm (default 1 for gate; use 3 for full measurement).",
    )
    parser.add_argument(
        "--mode",
        choices=["gate", "ab"],
        default="gate",
        help="gate: Arm A only (headroom check). ab: Arm A + Oracle (recovery ceiling).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.trials, args.mode))


if __name__ == "__main__":
    main()
