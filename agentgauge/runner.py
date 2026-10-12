from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from mcp.types import Tool

from agentgauge._json import extract_json_object
from agentgauge.client import MCPClient
from agentgauge.providers import Message, Provider
from agentgauge.tasks import Task


@dataclass
class RunResult:
    task: Task
    selected_tool: str | None
    constructed_args: dict[str, Any]
    success: bool
    error: str | None = None
    parse_failed: bool = field(default=False)


def _build_tool_listing(tools: list[Tool]) -> str:
    """Format tools as a one-line-per-tool listing for the selection prompt.

    Shows name, description, and parameter names/types so the agent can distinguish
    tools by description — not just by name. This ensures arm A and arm B present
    different selection prompts when their descriptions differ (manipulation check).

    Format: '<name> — <description> | <param>:<type>, ...'
    """
    lines = []
    for tool in tools:
        desc = (tool.description or "(no description)").split("\n")[0]
        props = (tool.inputSchema or {}).get("properties", {})
        param_parts = []
        for pname, pschema in props.items():
            ptype = pschema.get("type", "")
            param_parts.append(f"{pname}:{ptype}" if ptype else pname)
        param_str = ", ".join(param_parts) if param_parts else "(no params)"
        lines.append(f"{tool.name} — {desc} | {param_str}")
    return "\n".join(lines)


def trial_seed(base_seed: int, task: Task, trial_index: int) -> int:
    """Deterministic per-trial seed from (base_seed, task identity, trial_index).

    Why: passing one fixed seed to every repeat trial makes a seeded sampler return the
    same completion each time, so "repeat trials" were byte-identical copies (90.3% of
    (tool_set, task) groups had zero variance in the audited corpus). Hashing keeps
    replays byte-identical (same inputs -> same seed) while giving trials of the same task
    distinct seeds. The task identity excludes the arm, so before/after arms share a seed
    per (task, trial) -- common random numbers, which preserves paired comparison.
    31-bit so every backend that takes an int seed accepts it.
    """
    key = f"{base_seed}\x00{task.tool_name}\x00{task.description}\x00{trial_index}"
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:4], "big") & 0x7FFFFFFF


async def run_tasks(
    tasks: list[Task],
    client: MCPClient,
    provider: Provider,
    *,
    trials: int = 1,
    base_seed: int = 42,
) -> list[RunResult]:
    """Ask the provider to select the right tool and construct arguments for each task.

    For each task, two prompts are sent:
    1. Select the tool name from the available tools (with descriptions + param types).
    2. Construct a JSON argument object for that tool.
    The tool is then called and the result recorded.

    Each (task, trial) gets its own seed via `trial_seed(base_seed, task, trial_index)`;
    both prompts of a trial share it. Adapters that ignore `seed` (hosted APIs) are
    unaffected and remain non-deterministic.
    """
    info = await client.introspect()
    tool_listing = _build_tool_listing(info.tools)
    tool_schema_map = {t.name: t.inputSchema for t in info.tools}

    results: list[RunResult] = []
    for task in tasks:
        for trial_index in range(trials):
            seed = trial_seed(base_seed, task, trial_index)
            selection_resp = await provider.chat(
                [
                    Message(
                        role="user",
                        content=(
                            f"Available tools:\n{tool_listing}\n\n"
                            f"Task: {task.description}\n"
                            "Reply with ONLY the tool name to call, nothing else."
                        ),
                    )
                ],
                seed=seed,
            )
            selected_tool = selection_resp.strip().split()[0] if selection_resp.strip() else None

            schema = tool_schema_map.get(selected_tool or task.tool_name, {})
            args_resp = await provider.chat(
                [
                    Message(
                        role="user",
                        content=(
                            f"Tool: {selected_tool or task.tool_name}\n"
                            f"Schema: {schema}\n"
                            f"Task: {task.description}\n"
                            "Reply with ONLY a JSON object of arguments, nothing else."
                        ),
                    )
                ],
                seed=seed,
            )
            constructed_args, parse_failed = extract_json_object(args_resp)

            call_result = await client.call_tool(selected_tool or task.tool_name, constructed_args)
            results.append(
                RunResult(
                    task=task,
                    selected_tool=selected_tool,
                    constructed_args=constructed_args,
                    success=call_result.success,
                    error=call_result.error,
                    parse_failed=parse_failed,
                )
            )
    return results
