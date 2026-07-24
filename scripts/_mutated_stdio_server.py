"""Task 3 (v2.2): generic runnable-server defect injector.

Runs any of this repo's `examples/*.py` MCP servers over stdio, with exactly
ONE tool's description/schema mutated by one of `scripts/v2_defect_injector`'s
injector functions -- the SAME injector functions already used (and measured)
for the linter's own recall evaluation, now producing a LIVE, runnable server
instead of just an in-memory dict for static linting.

Mechanism: monkeypatches the target module's `mcp.server.Server.
request_handlers[types.ListToolsRequest]` entry to return the mutated tool
list, leaving `CallToolRequest`'s handler (the actual tool execution logic)
untouched -- the agent sees a defective description/schema, but a call that
gets through still executes the server's real (unmodified) behavior. This is
exactly what "inject a defect" should mean for a causal-chain test: only the
information the agent sees changes, not the ground truth of what the tool
does.

Usage:
    python scripts/_mutated_stdio_server.py <module_path> <defect_type> <target_tool_name>

<module_path> e.g. "examples.call_constraints_server" (dotted, importable).
No target found / injector inapplicable -> exits 1 with a clear stderr message
(fails fast rather than silently serving the unmutated tool list).
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp.types as types  # noqa: E402
from mcp.server.lowlevel.server import NotificationOptions  # noqa: E402
from mcp.server.models import InitializationOptions  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

from scripts.v2_defect_injector import INJECTORS  # noqa: E402


def _tool_to_dict(t: types.Tool) -> dict:
    return {"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema or {}}


def _dict_to_tool(d: dict) -> types.Tool:
    return types.Tool(name=d["name"], description=d["description"], inputSchema=d["inputSchema"])


async def main() -> None:
    if len(sys.argv) != 4:
        print(
            "Usage: _mutated_stdio_server.py <module_path> <defect_type> <target_tool_name>",
            file=sys.stderr,
        )
        sys.exit(2)
    module_path, defect_type, target_tool_name = sys.argv[1], sys.argv[2], sys.argv[3]

    if defect_type not in INJECTORS:
        print(f"Unknown defect_type {defect_type!r}. Known: {list(INJECTORS)}", file=sys.stderr)
        sys.exit(1)

    mod = importlib.import_module(module_path)
    server = mod.server

    original_handler = server.request_handlers[types.ListToolsRequest]
    original_result = await original_handler(types.ListToolsRequest(method="tools/list"))
    original_tools = [_tool_to_dict(t) for t in original_result.root.tools]

    injector, _eligibility_fn = INJECTORS[defect_type]
    result = injector(original_tools, target_tool_name)
    if result is None:
        print(
            f"Injector {defect_type!r} could not apply to target {target_tool_name!r} "
            f"in {module_path} (not eligible).",
            file=sys.stderr,
        )
        sys.exit(1)
    mutated_tools, defect = result
    print(f"Injected: {defect.detail}", file=sys.stderr)

    mutated_tool_objs = [_dict_to_tool(d) for d in mutated_tools]

    async def mutated_list_tools_handler(_req: types.ListToolsRequest) -> types.ServerResult:
        return types.ServerResult(root=types.ListToolsResult(tools=mutated_tool_objs))

    server.request_handlers[types.ListToolsRequest] = mutated_list_tools_handler

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=f"{server.name}-mutated",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
