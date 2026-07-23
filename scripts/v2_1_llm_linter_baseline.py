"""Task 2e / Task 6 (v2.1): the single-prompt LLM "find inconsistencies" baseline
for the deterministic linter, deferred in Task 2 (`reports/v2_linter_evaluation.md`
§2e) pending GPU availability. Now run against the SAME clean corpus (521 tools) and
defect-injection corpus (276 labeled defects) used for the deterministic linter's own
Task 2/4 measurements, using llama3.1:8b (the study's pinned judge model) as the
single-prompt judge, via the `agentgauge-agent` Cloud Run proxy.

One LLM call per tool, no multi-turn/chain-of-thought agent loop -- the baseline this
doctrine committed to comparing against is a single, direct "is this consistent?"
prompt, not an elaborate LLM pipeline (that would not be a fair "zero-effort baseline"
comparison for the deterministic linter).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.providers import Message, OllamaProvider  # noqa: E402
from scripts.v2_defect_injector import INJECTORS, _load_clean_corpus  # noqa: E402

OllamaProvider.BASE_URL = "http://localhost:11435"  # agentgauge-agent Cloud Run proxy
JUDGE_MODEL = "llama3.1:8b"
OUT_PATH = Path("evals/fixtures/v2_1_llm_linter_baseline.json")
_MAX_TARGETS_PER_DEFECT_TYPE = 3

_PROMPT_TEMPLATE = """You are reviewing an MCP tool definition for description/schema consistency defects.

Tool name: {name}
Description: {description}
JSON Schema: {schema}

Does this tool's description contain any inconsistency with its schema? Look for:
- A parameter mentioned in the description that does not exist in the schema
- A type contradiction (e.g. description implies boolean true/false but the schema type is not boolean)
- An enum-style value mentioned in the description that is not in the schema's enum list
- A "required" property in the schema that does not exist in the schema's own properties

Respond with EXACTLY one line: "INCONSISTENT: <short reason>" if you find a problem, or
"CONSISTENT" if you find none. No other text."""


async def _judge_one(provider: OllamaProvider, name: str, description: str, schema: dict) -> bool:
    prompt = _PROMPT_TEMPLATE.format(
        name=name, description=description or "(none)", schema=json.dumps(schema)
    )
    response = await provider.chat([Message(role="user", content=prompt)], seed=42)
    return bool(re.search(r"\bINCONSISTENT\b", response, re.IGNORECASE))


async def measure_clean_corpus_false_alarms(provider: OllamaProvider) -> dict:
    clean_corpus = _load_clean_corpus()
    n_tools = 0
    n_flagged = 0
    for entry in clean_corpus:
        for t in entry["tools"]:
            n_tools += 1
            flagged = await _judge_one(provider, t["name"], t["description"], t["inputSchema"])
            if flagged:
                n_flagged += 1
            if n_tools % 25 == 0:
                print(f"  clean corpus progress: {n_tools} tools checked, {n_flagged} flagged")
    return {
        "n_tools": n_tools,
        "n_flagged": n_flagged,
        "false_alarm_rate_pct": 100.0 * n_flagged / n_tools,
    }


async def measure_defect_injection_recall(provider: OllamaProvider) -> dict:
    clean_corpus = _load_clean_corpus()
    per_type: dict[str, dict] = {d: {"n": 0, "detected": 0} for d in INJECTORS}
    n_done = 0
    for entry in clean_corpus:
        for defect_type, (injector, eligibility_fn) in INJECTORS.items():
            eligible = eligibility_fn(entry["tools"])[:_MAX_TARGETS_PER_DEFECT_TYPE]
            for target_name in eligible:
                result = injector(entry["tools"], target_name)
                if result is None:
                    continue
                mutated_tools, _defect = result
                target = next(t for t in mutated_tools if t["name"] == target_name)
                flagged = await _judge_one(
                    provider, target["name"], target["description"], target["inputSchema"]
                )
                per_type[defect_type]["n"] += 1
                if flagged:
                    per_type[defect_type]["detected"] += 1
                n_done += 1
                if n_done % 25 == 0:
                    print(f"  defect-injection progress: {n_done} cases checked")
    for stats in per_type.values():
        stats["recall_pct"] = 100.0 * stats["detected"] / stats["n"] if stats["n"] else None
    return per_type


async def main() -> None:
    provider = OllamaProvider(JUDGE_MODEL)
    print(f"=== Task 2e: single-prompt LLM baseline ({JUDGE_MODEL}) ===")
    print("Clean-corpus false-alarm rate...")
    fa = await measure_clean_corpus_false_alarms(provider)
    print(json.dumps(fa, indent=2))

    print("\nDefect-injection recall...")
    recall = await measure_defect_injection_recall(provider)
    print(json.dumps(recall, indent=2))

    out = {
        "judge_model": JUDGE_MODEL,
        "clean_corpus_false_alarms": fa,
        "defect_injection_recall": recall,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
