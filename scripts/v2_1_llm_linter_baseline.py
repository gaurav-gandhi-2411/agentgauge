"""Task 2e / Task 6 (v2.1): the single-prompt LLM "find inconsistencies" baseline
for the deterministic linter, deferred in Task 2 (`reports/v2_linter_evaluation.md`
§2e) pending GPU availability. Run against a bounded, stratified SAMPLE of the clean
corpus and the defect-injection corpus used for the deterministic linter's own Task
2/4 measurements, using llama3.1:8b (the study's pinned judge model) as the
single-prompt judge, calling `agentgauge-agent` Cloud Run directly over HTTPS with an
IAM identity-token bearer header (not `gcloud run services proxy` -- that local proxy
is a documented-unreliable intermediary on this machine; see
scripts/v2_1_cross_model_validation.py's module docstring for the same finding).

One LLM call per tool, no multi-turn/chain-of-thought agent loop -- the baseline this
doctrine committed to comparing against is a single, direct "is this consistent?"
prompt, not an elaborate LLM pipeline.

SAMPLE, not full corpus: every 3rd clean-corpus tool (~174 of 521) and every 2nd
defect-injection case (~138 of 276, still stratified across all 5 defect types) --
disclosed explicitly, not a silent reduction. This keeps the run to roughly 300 calls
given this infrastructure's demonstrated fragility over long continuous sessions
(this session's Cloud Run service has been observed to require an uninterrupted
script run to stay warm; a 797-call full-corpus run has a larger failure window than
a ~300-call one). Checkpointed every 20 calls so an interruption loses at most 20
calls of progress, not the whole run.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402

from agentgauge.providers import Message, OllamaProvider  # noqa: E402
from scripts.v2_defect_injector import INJECTORS, _load_clean_corpus  # noqa: E402

CLOUD_RUN_URL = "https://agentgauge-agent-6txxpjhu2a-uc.a.run.app"
_IDENTITY_TOKEN = os.environ["AGENTGAUGE_AGENT_IDENTITY_TOKEN"]
JUDGE_MODEL = "llama3.1:8b"
OUT_PATH = Path("evals/fixtures/v2_1_llm_linter_baseline.json")
_MAX_TARGETS_PER_DEFECT_TYPE = 3
_CLEAN_CORPUS_STRIDE = 3  # every 3rd tool
_DEFECT_STRIDE = 2  # every 2nd case, still stratified (per-type ordering preserved)

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


class AuthenticatedOllamaProvider(OllamaProvider):
    """Direct-HTTPS + IAM bearer-token variant -- see module docstring."""

    BASE_URL = CLOUD_RUN_URL

    async def chat(self, messages: list[Message], *, seed: int = 42) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"seed": seed},
        }
        headers = {"Authorization": f"Bearer {_IDENTITY_TOKEN}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self.BASE_URL}/api/chat", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["message"]["content"]


async def _ensure_model_pulled(model: str) -> None:
    headers = {"Authorization": f"Bearer {_IDENTITY_TOKEN}"}
    timeout = httpx.Timeout(connect=300.0, read=120.0, write=30.0, pool=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{CLOUD_RUN_URL}/api/tags", headers=headers)
        resp.raise_for_status()
        if any(m["name"] == model for m in resp.json().get("models", [])):
            print(f"Already pulled: {model}", flush=True)
            return
        print(f"Pulling {model}...", flush=True)
        async with client.stream(
            "POST",
            f"{CLOUD_RUN_URL}/api/pull",
            json={"model": model, "stream": True},
            headers=headers,
        ) as stream:
            stream.raise_for_status()
            async for line in stream.aiter_lines():
                if not line:
                    continue
                status = json.loads(line).get("status", "")
                if status in ("success", "verifying sha256 digest", "writing manifest"):
                    print(f"  {model}: {status}", flush=True)


async def _judge_one(
    provider: AuthenticatedOllamaProvider, name: str, description: str, schema: dict
) -> bool:
    prompt = _PROMPT_TEMPLATE.format(
        name=name, description=description or "(none)", schema=json.dumps(schema)
    )
    response = await provider.chat([Message(role="user", content=prompt)], seed=42)
    return bool(re.search(r"\bINCONSISTENT\b", response, re.IGNORECASE))


def _build_clean_corpus_sample() -> list[dict]:
    clean_corpus = _load_clean_corpus()
    all_tools = [t for entry in clean_corpus for t in entry["tools"]]
    return all_tools[::_CLEAN_CORPUS_STRIDE]


def _build_defect_sample() -> list[dict]:
    clean_corpus = _load_clean_corpus()
    cases = []
    for entry in clean_corpus:
        for defect_type, (injector, eligibility_fn) in INJECTORS.items():
            eligible = eligibility_fn(entry["tools"])[:_MAX_TARGETS_PER_DEFECT_TYPE]
            for target_name in eligible:
                result = injector(entry["tools"], target_name)
                if result is None:
                    continue
                mutated_tools, _defect = result
                target = next(t for t in mutated_tools if t["name"] == target_name)
                cases.append({"defect_type": defect_type, "tool": target})
    # Stratified stride: sort by defect_type first so the stride samples from
    # every type, not just the first ones encountered.
    cases.sort(key=lambda c: str(c["defect_type"]))
    return cases[::_DEFECT_STRIDE]


def _load_checkpoint() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {"clean_results": [], "defect_results": []}


def _save_checkpoint(state: dict) -> None:
    OUT_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def main() -> None:
    await _ensure_model_pulled(JUDGE_MODEL)
    provider = AuthenticatedOllamaProvider(JUDGE_MODEL)
    state = _load_checkpoint()

    clean_sample = _build_clean_corpus_sample()
    defect_sample = _build_defect_sample()
    print(
        f"Sample sizes: clean_corpus={len(clean_sample)} (of full corpus, stride={_CLEAN_CORPUS_STRIDE}), "
        f"defects={len(defect_sample)} (stride={_DEFECT_STRIDE})",
        flush=True,
    )

    n_clean_done = len(state["clean_results"])
    for i, t in enumerate(clean_sample[n_clean_done:], start=n_clean_done):
        flagged = await _judge_one(provider, t["name"], t["description"], t["inputSchema"])
        state["clean_results"].append(flagged)
        if (i + 1) % 20 == 0 or i + 1 == len(clean_sample):
            _save_checkpoint(state)
            print(f"  clean corpus: {i + 1}/{len(clean_sample)} checked", flush=True)

    n_defect_done = len(state["defect_results"])
    for i, case in enumerate(defect_sample[n_defect_done:], start=n_defect_done):
        t = case["tool"]
        flagged = await _judge_one(provider, t["name"], t["description"], t["inputSchema"])
        state["defect_results"].append({"defect_type": case["defect_type"], "detected": flagged})
        if (i + 1) % 20 == 0 or i + 1 == len(defect_sample):
            _save_checkpoint(state)
            print(f"  defect-injection: {i + 1}/{len(defect_sample)} checked", flush=True)

    n_flagged = sum(state["clean_results"])
    n_tools = len(state["clean_results"])
    fa = {
        "n_tools": n_tools,
        "n_flagged": n_flagged,
        "false_alarm_rate_pct": 100.0 * n_flagged / n_tools if n_tools else None,
    }

    per_type: dict[str, dict] = {}
    for r in state["defect_results"]:
        d = per_type.setdefault(r["defect_type"], {"n": 0, "detected": 0})
        d["n"] += 1
        d["detected"] += int(r["detected"])
    for stats in per_type.values():
        stats["recall_pct"] = 100.0 * stats["detected"] / stats["n"] if stats["n"] else None

    state["judge_model"] = JUDGE_MODEL
    state["clean_corpus_false_alarms"] = fa
    state["defect_injection_recall"] = per_type
    _save_checkpoint(state)

    print("\n=== Clean-corpus false-alarm rate (sample) ===", flush=True)
    print(json.dumps(fa, indent=2), flush=True)
    print("\n=== Defect-injection recall (sample) ===", flush=True)
    print(json.dumps(per_type, indent=2), flush=True)
    print(f"\nWrote {OUT_PATH}", flush=True)


if __name__ == "__main__":
    import traceback

    try:
        asyncio.run(main())
    except BaseException:
        print("FATAL:", flush=True)
        traceback.print_exc()
        raise
