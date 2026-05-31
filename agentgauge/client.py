from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.types import Prompt, Resource, Tool


@dataclass
class ServerInfo:
    tools: list[Tool] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    prompts: list[Prompt] = field(default_factory=list)


@dataclass
class ToolCallResult:
    success: bool
    content: list[Any]
    error: str | None = None


class MCPClient:
    """Wraps an active MCP ClientSession."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def introspect(self) -> ServerInfo:
        tools_resp = await self._session.list_tools()
        # Servers may not implement resources/prompts; treat Method not found as empty.
        try:
            resources_resp = await self._session.list_resources()
            resources = resources_resp.resources
        except McpError:
            resources = []
        try:
            prompts_resp = await self._session.list_prompts()
            prompts = prompts_resp.prompts
        except McpError:
            prompts = []
        return ServerInfo(tools=tools_resp.tools, resources=resources, prompts=prompts)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        try:
            result = await self._session.call_tool(name, arguments)
            return ToolCallResult(success=True, content=result.content)
        except Exception as exc:
            return ToolCallResult(success=False, content=[], error=str(exc))

    async def call_tool_with_bad_input(self, name: str, bad_args: dict[str, Any]) -> ToolCallResult:
        """Call a tool with deliberately malformed arguments to probe error response quality.

        Returns the raw result without raising; the caller inspects the error text.
        """
        return await self.call_tool(name, bad_args)


async def connect_stdio(command: str, args: list[str]) -> tuple[MCPClient, Any]:
    """Returns (client, context) — caller must use as async context or call cleanup."""
    params = StdioServerParameters(command=command, args=args)
    ctx = stdio_client(params)
    read, write = await ctx.__aenter__()
    session_ctx = ClientSession(read, write)
    session = await session_ctx.__aenter__()
    await session.initialize()
    return MCPClient(session), (ctx, session_ctx, read, write)


async def connect_http(url: str) -> tuple[MCPClient, Any]:
    """Connect to an MCP server over HTTP/SSE."""
    ctx = sse_client(url)
    read, write = await ctx.__aenter__()
    session_ctx = ClientSession(read, write)
    session = await session_ctx.__aenter__()
    await session.initialize()
    return MCPClient(session), (ctx, session_ctx, read, write)


async def cleanup_connection(ctx_tuple: Any) -> None:
    ctx, session_ctx, read, write = ctx_tuple
    with contextlib.suppress(Exception):
        await session_ctx.__aexit__(None, None, None)
    with contextlib.suppress(Exception):
        await ctx.__aexit__(None, None, None)


async def fetch_llms_txt(base_url: str | None) -> str | None:
    """Fetch <base_url>/llms.txt; return text on 200, None on 404/error/absent.

    stdio servers have no base URL — pass None and this returns None immediately.
    All network/timeout errors are swallowed; the scorer handles absent as the floor case.
    follow_redirects=True: many sites (e.g. docs.anthropic.com) serve llms.txt behind a 301;
    without this, those sites silently floor at 20.0 even though rich content is available.
    """
    if base_url is None:
        return None
    url = base_url.rstrip("/") + "/llms.txt"
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as http_client:
            resp = await http_client.get(url)
            if resp.status_code == 200:
                return resp.text
    except Exception:
        pass
    return None
