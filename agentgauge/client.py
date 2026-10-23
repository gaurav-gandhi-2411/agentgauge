from __future__ import annotations

import contextlib
import os
import sys
import tempfile
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


# Bounds on the server-stderr excerpt shown when a server fails to start: enough to see a Python
# traceback's last frames and the exception line, small enough to read in a terminal.
STDERR_TAIL_LINES = 20
STDERR_TAIL_LINE_CHARS = 300


class ServerStartError(Exception):
    """A stdio server did not complete the MCP handshake (it crashed, exited, or failed it).

    `stderr_tail` is the last STDERR_TAIL_LINES lines of what the server wrote to stderr,
    each capped at STDERR_TAIL_LINE_CHARS; empty if it wrote nothing.
    """

    def __init__(self, command: str, args: list[str], stderr_tail: str) -> None:
        self.command = command
        self.args_ = args
        self.stderr_tail = stderr_tail
        target = args[-1] if args else command
        super().__init__(f"server failed to start: {target} did not complete the MCP handshake")


class StderrCapture:
    """The server's stderr, captured in a temp FILE instead of a pipe.

    A file can never fill and block the child, and needs no reader task (the Windows deadlock
    class). The child writes through `writer`; we never seek it, because an inherited handle
    shares its file pointer with the child. All reads go through a separate handle opened by
    path. Output is forwarded to our own stderr after the handshake and again at cleanup, so a
    healthy server's logs still reach the terminal, just not live.
    """

    def __init__(self) -> None:
        fd, self.path = tempfile.mkstemp(prefix="agentgauge_server_", suffix=".stderr")
        self.writer = os.fdopen(fd, "w", encoding="utf-8", errors="replace")
        self._forwarded = 0  # byte offset already forwarded to sys.stderr
        self.closed = False

    def _read_all(self) -> str:
        with open(self.path, "rb") as f:  # noqa: PTH123 - same handle style as os.fdopen above
            return f.read().decode("utf-8", errors="replace")

    def tail(self) -> str:
        """Last STDERR_TAIL_LINES lines, each length-capped, stock traceback header dropped."""
        # The header word "Traceback" in our output would read as agentgauge itself crashing;
        # the frames and the exception line carry the information.
        lines = [ln for ln in self._read_all().splitlines() if not ln.startswith("Traceback (most")]
        return "\n".join(
            (ln if len(ln) <= STDERR_TAIL_LINE_CHARS else ln[:STDERR_TAIL_LINE_CHARS] + "...")
            for ln in lines[-STDERR_TAIL_LINES:]
        )

    def forward(self) -> None:
        """Write everything captured since the last forward() to our own stderr."""
        if self.closed:
            return
        with open(self.path, "rb") as f:  # noqa: PTH123
            f.seek(self._forwarded)
            data = f.read()
        self._forwarded += len(data)
        if data:
            sys.stderr.write(data.decode("utf-8", errors="replace"))
            sys.stderr.flush()

    def close(self) -> None:
        """Close and delete the temp file (idempotent)."""
        if self.closed:
            return
        self.closed = True
        with contextlib.suppress(OSError):
            self.writer.close()
        with contextlib.suppress(OSError):
            os.unlink(self.path)  # noqa: PTH108


async def connect_stdio(command: str, args: list[str]) -> tuple[MCPClient, Any]:
    """Returns (client, context) — caller must use as async context or call cleanup.

    Raises ServerStartError (not a bare McpError / anyio traceback) when the handshake fails.
    On success the context is a 5-tuple whose last item is the StderrCapture;
    `cleanup_connection` forwards what the server wrote after the handshake and closes it.
    """
    params = StdioServerParameters(command=command, args=args)
    capture = StderrCapture()
    # cast-free: stdio_client only needs a file with a fileno(), which the writer provides.
    ctx = stdio_client(params, errlog=capture.writer)
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
        tail = capture.tail()
        capture.close()
        raise ServerStartError(command, args, tail) from exc
    capture.forward()  # startup logs of a healthy server, as before when stderr was inherited
    return MCPClient(session), (ctx, session_ctx, read, write, capture)


async def connect_http(url: str) -> tuple[MCPClient, Any]:
    """Connect to an MCP server over HTTP/SSE."""
    ctx = sse_client(url)
    read, write = await ctx.__aenter__()
    session_ctx = ClientSession(read, write)
    session = await session_ctx.__aenter__()
    await session.initialize()
    return MCPClient(session), (ctx, session_ctx, read, write)


async def cleanup_connection(ctx_tuple: Any) -> None:
    ctx, session_ctx, read, write, *extra = ctx_tuple
    capture = extra[0] if extra and isinstance(extra[0], StderrCapture) else None
    try:
        with contextlib.suppress(Exception):
            await session_ctx.__aexit__(None, None, None)
        with contextlib.suppress(Exception):
            await ctx.__aexit__(None, None, None)
    finally:
        if capture is not None:
            with contextlib.suppress(Exception):
                capture.forward()  # whatever the server wrote after the handshake
            capture.close()


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
