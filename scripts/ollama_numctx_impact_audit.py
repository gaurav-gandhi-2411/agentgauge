from __future__ import annotations

"""READ-ONLY impact audit: which committed Ollama-path prompts exceed a 4096-token context?

Ollama silently truncates prompts longer than num_ctx. This script rebuilds, for every bundled
MCP server under examples/ (the catalogs the experiments connected to), the prompt classes the
Ollama path sends, and asks the real tokenizer (Ollama itself) how many tokens each is, with
num_ctx=32768 and num_predict=1 so that nothing truncates. It changes no published number.

Prompt classes (built with the same code/templates the harness uses):
  selection       runner.run_tasks selection prompt: full tool listing + longest corpus task
  args            runner.run_tasks argument prompt: schema of the largest-schema tool
  discoverability scorer discoverability judge prompt: one-line-per-tool catalog
  fixer_source    fixer source-aware generator prompt with the WHOLE server file as source
                  (upper bound: the scripts passed per-tool or whole-file source; the generator
                  model was qwen3:8b, whose tokenizer differs -- counted with the llama3.1:8b
                  tokenizer here, so approximate)

Cache defence: Ollama reuses a KV-cache prefix, which lowers prompt_eval_count. Each prompt is
prefixed with a unique fixed-width nonce, and the nonce-only baseline is subtracted.

Usage: python scripts/ollama_numctx_impact_audit.py OUT_JSON [--model llama3.1:8b]
"""

import argparse
import asyncio
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agentgauge.client import connect_stdio  # noqa: E402
from agentgauge.fixer import _DESC_GENERATOR_SOURCE_AWARE_PROMPT  # noqa: E402
from agentgauge.runner import _build_tool_listing  # noqa: E402

BASE = "http://localhost:11434"
LIMIT = 4096
TASK_MODULES = [
    "q3_catalog",
    "q6_catalog",
    "t18_catalog",
    "p2a_internal_proxy_catalog",
    "t17_tasks",
    "ty_tasks",
    "ty2_tasks",
]


def longest_task() -> str:
    """Longest Task.description in any committed task list (drives the per-call suffix)."""
    best = ""
    for mod in TASK_MODULES:
        m = importlib.import_module(f"evals.fixtures.{mod}")
        for t in getattr(m, "TASKS", []):
            if len(t.description) > len(best):
                best = t.description
    return best


async def count_tokens(client: httpx.AsyncClient, model: str, text: str, nonce: int) -> int:
    """prompt_eval_count for `text` as a single user message, minus the nonce baseline."""

    async def one(content: str) -> int:
        r = await client.post(
            f"{BASE}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "stream": False,
                "options": {"num_ctx": 65536, "num_predict": 1, "seed": 42},
            },
        )
        r.raise_for_status()
        return int(r.json()["prompt_eval_count"])

    tag = f"AUDIT-{nonce:06d}\n"
    base = await one(tag)
    return await one(tag + text) - base


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument(
        "--classes",
        default="selection,args,discoverability,fixer_source",
        help="comma-separated prompt classes to count",
    )
    args = ap.parse_args()

    task = longest_task()
    rows: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    nonce = 0
    async with httpx.AsyncClient(timeout=1200.0) as http:
        for path in sorted((ROOT / "examples").glob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            try:
                client, _ctx = await asyncio.wait_for(
                    connect_stdio(sys.executable, [str(path)]), 60
                )
                info = await asyncio.wait_for(client.introspect(), 60)
            except Exception as exc:  # noqa: BLE001 -- record and continue; audit is best-effort
                failed.append({"source_file": rel, "error": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            tools = info.tools
            if not tools:
                failed.append({"source_file": rel, "error": "no tools"})
                continue
            listing = _build_tool_listing(tools)
            biggest = max(tools, key=lambda t: len(str(t.inputSchema)))
            source = path.read_text(encoding="utf-8")
            catalog = "\n".join(
                f"- {t.name}: {(t.description or '(no description)').splitlines()[0]}"
                for t in tools
            )
            prompts = {
                "selection": (
                    f"Available tools:\n{listing}\n\nTask: {task}\n"
                    "Reply with ONLY the tool name to call, nothing else."
                ),
                "args": (
                    f"Tool: {biggest.name}\nSchema: {biggest.inputSchema}\nTask: {task}\n"
                    "Reply with ONLY a JSON object of arguments, nothing else."
                ),
                "discoverability": (
                    "You are evaluating an MCP server's tool catalog for AI agent "
                    "discoverability.\nHere are the available tools (name and one-line "
                    f"description only):\n{catalog}\n\n"
                    "Rate the catalog on TWO dimensions (each 0-10):\n"
                ),
                "fixer_source": _DESC_GENERATOR_SOURCE_AWARE_PROMPT.format(
                    name=biggest.name,
                    current=biggest.description or "(none)",
                    schema=biggest.inputSchema,
                    source=source,
                ),
            }
            for cls, text in prompts.items():
                if cls not in args.classes.split(","):
                    continue
                nonce += 1
                n = await count_tokens(http, args.model, text, nonce)
                rows.append(
                    {
                        "prompt_id": f"{rel}::{cls}",
                        "source_file": rel,
                        "prompt_class": cls,
                        "n_tools": len(tools),
                        "chars": len(text),
                        "utf8_bytes": len(text.encode("utf-8")),
                        "tokens": n,
                        "bytes_per_token": round(len(text.encode("utf-8")) / n, 3),
                        "exceeded_4096": n > LIMIT,
                    }
                )
                print(f"{rel}::{cls}: {n}", flush=True)

    Path(args.out).write_text(
        json.dumps(
            {
                "model": args.model,
                "ollama_version": "0.40.3",
                "classes": args.classes,
                "limit": LIMIT,
                "longest_task_chars": len(task),
                "rows": rows,
                "servers_failed_to_start": failed,
            },
            indent=1,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
