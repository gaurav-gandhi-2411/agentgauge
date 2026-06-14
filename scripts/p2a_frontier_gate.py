#!/usr/bin/env python3
"""P2-A Arm A headroom gate on Llama-3.3-70B via Groq.

Runs the 31 pre-registered CONTESTED tasks against Arm A (thin descriptions)
on Groq/Llama-3.3-70b-versatile. Reports per-family accuracy and aggregate
contested headroom — the same gate used in p2a_phase2_ab.py but for a 70B
frontier model that cannot run locally.

Usage:
    GROQ_API_KEY=<key> python scripts/p2a_frontier_gate.py [--trials 1]

Token budget (31 tasks × 1 trial, ~200 tok/call):
    ~6 200 tokens total — well within Groq free tier (12k tokens/min).
    ETA: ~1–2 minutes at fixed pacing. Cost: $0 on free tier.

If Groq throttles (429), the paced caller backs off using retry-after headers.
Do NOT increase --trials until the gate clears: 31 × 3 trials = ~18k tokens.
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


# ── Tool listing (matches _build_tool_listing format from runner.py) ──────────

def _build_arm_a_listing() -> str:
    """Build text listing: 'name — desc | param:type, ...' from P2A catalog."""
    lines = []
    for tool_name, desc in ARM_A_DESCRIPTIONS.items():
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
                print(f"  [429] backing off {min(20.0, max(1.0, wait)):.1f}s", flush=True)
                await asyncio.sleep(min(20.0, max(1.0, wait)) + 0.5)
                continue
            resp.raise_for_status()
            data = resp.json()
            self.calls += 1
            return data["choices"][0]["message"]["content"]
        raise RuntimeError("Groq 429 retries exhausted (15 attempts).")


# ── Main ───────────────────────────────────────────────────────────────────────

async def run(trials: int) -> None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise SystemExit("GROQ_API_KEY not set. Export it and retry.")

    listing = _build_arm_a_listing()
    caller = PacedGroq(key)

    contested_tasks = [(i, TASKS[i]) for i in _CONTESTED_TASK_INDICES]
    n_contested = len(contested_tasks)
    total_calls = n_contested * trials
    est_tokens = total_calls * 200

    print("=" * 80)
    print("P2-A Arm A Frontier Gate — Llama-3.3-70B via Groq")
    print(f"Model: {_MODEL}")
    print(f"Contested tasks: {n_contested}  |  Trials: {trials}  |  Total calls: {total_calls}")
    print(f"Est. tokens: ~{est_tokens:,}  |  Gate threshold: {_HEADROOM_GATE * 100:.0f}%")
    print("=" * 80)

    records: list[tuple[int, object, str, str]] = []  # (task_idx, task, outcome, raw)
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
            status = "✓" if outcome == "CORRECT" else ("~" if outcome == "ABSTAIN" else "✗")
            print(
                f"  {status} [{task.tool_name:<28}] -> {raw.strip()[:40]!r:<42} {outcome}",
                flush=True,
            )

    # ── Aggregate stats ────────────────────────────────────────────────────────
    n_correct = sum(1 for _, _, o, _ in records if o == "CORRECT")
    n_abstain = sum(1 for _, _, o, _ in records if o == "ABSTAIN")
    n_ps = len(records) - n_abstain  # parse-success (CORRECT or WRONG)
    agg_acc = n_correct / n_ps if n_ps > 0 else 0.0

    print("\n" + "=" * 80)
    print("RESULTS — Arm A contested accuracy (Llama-3.3-70B / Groq)")
    print("=" * 80)
    print(
        f"\n  Aggregate contested accuracy (parse-success): "
        f"{agg_acc * 100:.1f}%  ({n_correct}/{n_ps})"
    )
    print(f"  ABSTAIN count: {n_abstain}/{len(records)}")
    print()
    print(f"  Headroom gate ({_HEADROOM_GATE * 100:.0f}%): ", end="")
    if agg_acc >= _HEADROOM_GATE:
        print(
            f"NO HEADROOM — {agg_acc * 100:.1f}% >= {_HEADROOM_GATE * 100:.0f}%\n"
            "  70B resolves contested tasks from thin descriptions alone.\n"
            "  Guard-B has little to recover for this model. Effect is weak-agent-bound."
        )
    else:
        recoverable = (1 - agg_acc) * 100
        print(
            f"HEADROOM EXISTS — ~{recoverable:.0f}pp recoverable "
            f"({agg_acc * 100:.1f}% < {_HEADROOM_GATE * 100:.0f}%)\n"
            f"  NOTE: modest headroom — model already resolves {agg_acc * 100:.0f}% "
            "of contested tasks from thin descriptions alone.\n"
            "  Guard-B targets the remaining gap; proceed to full A/B."
        )

    # ── Per-family breakdown ───────────────────────────────────────────────────
    print("\n  Per-family contested accuracy (Arm A, Llama-3.3-70B):")
    print(f"  {'Family':<28} {'Contested':>10} {'Correct':>8} {'Accuracy':>10}")
    print("  " + "-" * 62)

    for family_name, family_tools in FAMILIES.items():
        fam_records = [
            (o, raw) for _, task, o, raw in records
            if task.tool_name in family_tools and task.tool_name in CONTESTED_TOOLS
        ]
        if not fam_records:
            continue
        fam_ps = [(o, raw) for o, raw in fam_records if o != "ABSTAIN"]
        fam_correct = sum(1 for o, _ in fam_ps if o == "CORRECT")
        fam_total = len(fam_ps)
        fam_acc = fam_correct / fam_total if fam_total > 0 else 0.0
        print(
            f"  {family_name:<28} {fam_total:>10} {fam_correct:>8} {fam_acc * 100:>9.1f}%"
        )

    print("  " + "=" * 62)
    print(f"\n  Groq calls made: {caller.calls}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P2-A Arm A headroom gate on Llama-3.3-70B via Groq"
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Trials per contested task (default 1 for gate; use 3 for full measurement).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.trials))


if __name__ == "__main__":
    main()
