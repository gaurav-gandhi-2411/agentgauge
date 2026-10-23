from __future__ import annotations

import contextlib
import tempfile
from dataclasses import dataclass, field
from typing import IO, Any, TextIO, cast

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
        self._stderr_file: IO[str] | None = None

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


# Bounds on the server-stderr excerpt shown when a server fails to start: enough to see a Python
# traceback's last frames and the exception line, small enough to read in a terminal.
STDERR_TAIL_LINES = 20
STDERR_TAIL_LINE_CHARS = 300


class ServerStartError(Exception):
    """A stdio server process exited (or failed the MCP handshake) before it was usable.

    `stderr_tail` is the last STDERR_TAIL_LINES lines of what the server wrote to stderr,
    each capped at STDERR_TAIL_LINE_CHARS; empty if it wrote nothing.
    """

    def __init__(self, command: str, args: list[str], stderr_tail: str) -> None:
        self.command = command
        self.args_ = args
        self.stderr_tail = stderr_tail
        target = args[-1] if args else command
        super().__init__(
            f"server failed to start: {target} exited before completing the MCP handshake"
        )


def _tail_of(stream: IO[str]) -> str:
    """Last STDERR_TAIL_LINES lines of a seekable text stream, each line length-capped."""
    stream.flush()
    stream.seek(0)
    # Drop the stock traceback header: the frames and exception line carry the information, and
    # the bare word "Traceback" in our output reads as agentgauge itself having crashed.
    lines = [ln for ln in stream.read().splitlines() if not ln.startswith("Traceback (most")]
    lines = lines[-STDERR_TAIL_LINES:]
    return "\n".join(
        (ln if len(ln) <= STDERR_TAIL_LINE_CHARS else ln[:STDERR_TAIL_LINE_CHARS] + "...")
        for ln in lines
    )


async def connect_stdio(command: str, args: list[str]) -> tuple[MCPClient, Any]:
    """Returns (client, context) — caller must use as async context or call cleanup.

    Raises ServerStartError (not a bare McpError / anyio traceback) when the server process
    dies before the handshake completes. The server's stderr goes to a temp FILE rather than a
    pipe: a file can never fill and block the child, so there is no reader task to deadlock on
    Windows, and the tail stays readable after the process is gone.
    """
    params = StdioServerParameters(command=command, args=args)
    # cast: TemporaryFile returns a wrapper typeshed does not model as TextIO; it is one at runtime.
    errlog = cast(
        TextIO,
        tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace"),  # noqa: SIM115
    )
    ctx = stdio_client(params, errlog=errlog)
    try:
        read, write = await ctx.__aenter__()
        session_ctx = ClientSession(read, write)
        session = await session_ctx.__aenter__()
        await session.initialize()
    except Exception as exc:
        # Tear down quietly: exiting the half-open contexts by hand raises anyio noise that
        # would otherwise reach the terminal as a second traceback.
        with contextlib.suppress(BaseException):
            await ctx.__aexit__(None, None, None)
        tail = _tail_of(errlog)
        errlog.close()
        raise ServerStartError(command, args, tail) from exc
    client = MCPClient(session)
    client._stderr_file = errlog  # keep the handle alive for the life of the child process
    return client, (ctx, session_ctx, read, write)


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
