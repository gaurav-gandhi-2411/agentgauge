#!/usr/bin/env python3
"""Phase 3 mechanism test: does LLM rewriting homogenize tool descriptions?

Pre-registered hypothesis (recorded before running, see chat transcript / PLAN):
LLM-driven description rewrites raise inter-tool description similarity within a
tool set (reduce discriminability), and that similarity increase drives the
wrong-tool-selection component of the observed real-task-success drop across the
6/7 degraded Phase 3 pairs.

Pre-registered falsifiers (recorded before running):
  1. Mean pairwise similarity does not rise (flat or falls) in a majority of the
     6 degraded pairs.
  2. Across all 7 pairs, similarity-delta and success-delta show no consistent
     negative relationship (rho not clearly negative, or positive sign).
  3. The success drop in degraded pairs is dominated by wrong-argument
     construction on the correctly-selected tool, not wrong-tool-selection.
  4. grounded_server_fixed (the one improved pair) shows a similarity increase
     comparable to the degraded pairs.

REVISION (mid-session finding, not pre-registered -- discovered while running):
the first pass of this script embedded only the bare `tool.description` field.
Reading agentgauge/runner.py showed the actual SELECTION prompt
(`_build_tool_listing`) uses name + description + PARAM NAMES/TYPES (never param
descriptions), while the ARGUMENT-CONSTRUCTION prompt uses the full raw schema
(including param descriptions). Bare tool.description therefore both under- and
over-states what the agent actually sees for selection. This revision:
  (a) embeds the full per-tool SELECTION text (`name -- description | params`,
      exactly matching _build_tool_listing's per-line format minus the name
      prefix stripped for cross-tool similarity, since name is always distinct
      by construction and would deflate every pairwise similarity uniformly)
  (b) decomposes task_success into a SELECTION component (wrong_tool_rate) and
      an ARGUMENT component (mean constraint_satisfaction among ONLY the trials
      where the correct tool was selected), pulled directly from stored
      run_results -- not inferred.
  (c) correlates delta-similarity against delta-wrong-tool-rate specifically
      (the mechanistically appropriate pairing), not just delta-task-success.

DO NOT RUN as part of CI -- makes live Ollama embedding calls (cheap, ~274MB
model, but still real inference) and spawns MCP stdio subprocesses.

Usage:
    uv run python scripts/phase3_mechanism_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from agentgauge.client import cleanup_connection, connect_stdio
from evals.fixtures.predictive_validity.manifest import MANIFEST, resolve_server_path

RESULTS_PATH = Path(__file__).parent.parent / "evals" / "fixtures" / "predictive_validity" / "results_raw.json"

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

PAIRS: list[tuple[str, str]] = [
    ("t18_vague_server", "t18_fixer_server"),
    ("t18_vague_server", "t18_q2b_server"),
    ("grounded_server", "grounded_server_fixed"),
    ("confusable_server", "confusable_server_fixed"),
    ("mediocre_server", "mediocre_server_fixed"),
    ("call_constraints_server", "call_constraints_server_fixed"),
    ("call_constraints_v2_server", "call_constraints_v2_server_fixed"),
]


def _embed(text: str) -> list[float]:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text or "(empty)"},
        timeout=30.0,
    )
    resp.raise_for_status()
    emb = resp.json()["embedding"]
    return emb if emb else [0.0]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True)) if len(a) == len(b) else 0.0
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _selection_text(desc: str, props: dict) -> str:
    """Matches _build_tool_listing's per-tool text, minus the tool name prefix
    (name is always distinct by construction and would uniformly deflate every
    pairwise similarity, masking the description/param signal we care about)."""
    d = (desc or "(no description)").split("\n")[0]
    param_parts = []
    for pname, pschema in props.items():
        ptype = pschema.get("type", "")
        param_parts.append(f"{pname}:{ptype}" if ptype else pname)
    param_str = ", ".join(param_parts) if param_parts else "(no params)"
    return f"{d} | {param_str}"


async def _get_tool_selection_texts(entry_name: str) -> dict[str, str]:
    entry = next(e for e in MANIFEST if e.name == entry_name)
    server_path = resolve_server_path(entry)
    client, ctx = await connect_stdio(sys.executable, [str(server_path)])
    try:
        info = await client.introspect()
        tools = info.tools
        if entry.tool_name_filter is not None:
            keep = set(entry.tool_name_filter)
            tools = [t for t in tools if t.name in keep]
        return {
            t.name: _selection_text(t.description, (t.inputSchema or {}).get("properties", {}))
            for t in tools
        }
    finally:
        await cleanup_connection(ctx)


def _pairwise_stats(texts: dict[str, str]) -> dict:
    names = sorted(texts.keys())
    vecs = {n: _embed(texts[n]) for n in names}
    sims: list[float] = []
    worst_pair = None
    worst_sim = -2.0
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            s = _cosine(vecs[names[i]], vecs[names[j]])
            sims.append(s)
            if s > worst_sim:
                worst_sim = s
                worst_pair = (names[i], names[j])
    mean_sim = sum(sims) / len(sims) if sims else 0.0
    return {
        "n_tools": len(names),
        "mean_pairwise_similarity": mean_sim,
        "max_pairwise_similarity": worst_sim,
        "nearest_confusable_pair": worst_pair,
    }


def _decompose(record: dict) -> dict:
    """Split task_success into selection vs argument components from stored
    per-trial run_results -- not inferred, pulled directly."""
    run_results = record.get("run_results")
    if not run_results:
        return {"wrong_tool_rate": None, "arg_score_given_correct_tool": None, "n": 0}
    n = len(run_results)
    n_wrong = sum(1 for r in run_results if r["task_tool_name"] != r["selected_tool"])
    correct = [r for r in run_results if r["task_tool_name"] == r["selected_tool"]]
    arg_score = (
        sum(r["constraint_satisfaction"] for r in correct) / len(correct) if correct else None
    )
    return {
        "wrong_tool_rate": n_wrong / n,
        "arg_score_given_correct_tool": arg_score,
        "n_correct_tool_trials": len(correct),
        "n": n,
    }


async def main() -> None:
    with RESULTS_PATH.open(encoding="utf-8") as f:
        data = {r["name"]: r for r in json.load(f) if r.get("error") is None}

    print(f"Embedding model: {EMBED_MODEL} @ {OLLAMA_URL}  (selection-text basis, not bare description)")
    print(f"Pairs: {len(PAIRS)}")
    print()

    rows = []
    for before, after in PAIRS:
        print(f"Processing {before} -> {after} ...", flush=True)
        texts_before = await _get_tool_selection_texts(before)
        texts_after = await _get_tool_selection_texts(after)
        stats_before = _pairwise_stats(texts_before)
        stats_after = _pairwise_stats(texts_after)

        rb, ra = data[before], data[after]
        decomp_before = _decompose(rb)
        decomp_after = _decompose(ra)

        row = {
            "before": before,
            "after": after,
            "n_tools": stats_before["n_tools"],
            "mean_sim_before": stats_before["mean_pairwise_similarity"],
            "mean_sim_after": stats_after["mean_pairwise_similarity"],
            "delta_mean_sim": stats_after["mean_pairwise_similarity"] - stats_before["mean_pairwise_similarity"],
            "max_sim_before": stats_before["max_pairwise_similarity"],
            "max_sim_after": stats_after["max_pairwise_similarity"],
            "delta_max_sim": stats_after["max_pairwise_similarity"] - stats_before["max_pairwise_similarity"],
            "nearest_pair_before": stats_before["nearest_confusable_pair"],
            "nearest_pair_after": stats_after["nearest_confusable_pair"],
            "task_success_before": rb["task_success_rate"],
            "task_success_after": ra["task_success_rate"],
            "delta_task_success": ra["task_success_rate"] - rb["task_success_rate"],
            "wrong_tool_rate_before": decomp_before["wrong_tool_rate"],
            "wrong_tool_rate_after": decomp_after["wrong_tool_rate"],
            "delta_wrong_tool_rate": (
                decomp_after["wrong_tool_rate"] - decomp_before["wrong_tool_rate"]
                if decomp_before["wrong_tool_rate"] is not None and decomp_after["wrong_tool_rate"] is not None
                else None
            ),
            "arg_score_given_correct_before": decomp_before["arg_score_given_correct_tool"],
            "arg_score_given_correct_after": decomp_after["arg_score_given_correct_tool"],
            "n_correct_tool_trials_before": decomp_before["n_correct_tool_trials"],
            "n_correct_tool_trials_after": decomp_after["n_correct_tool_trials"],
        }
        rows.append(row)
        print(f"  selection-text mean_sim: {row['mean_sim_before']:.4f} -> {row['mean_sim_after']:.4f}  (delta {row['delta_mean_sim']:+.4f})")
        print(f"  wrong_tool_rate:         {row['wrong_tool_rate_before']:.4f} -> {row['wrong_tool_rate_after']:.4f}  (delta {row['delta_wrong_tool_rate']:+.4f})")
        ab, aa = row["arg_score_given_correct_before"], row["arg_score_given_correct_after"]
        print(f"  arg_score|correct_tool:  {ab} -> {aa}")
        print()

    out_path = Path(__file__).parent.parent / "evals" / "fixtures" / "predictive_validity" / "phase3_mechanism_results.json"
    out_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
