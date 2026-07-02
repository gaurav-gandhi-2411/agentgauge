from __future__ import annotations

import pathlib

from agentgauge.exp1_mirror import (
    MirrorParam,
    MirrorTool,
    ServerMirror,
    assert_docstrings_verbatim,
    extract_python_tools,
    mirror_from_dict,
    mirror_to_dict,
    tool_docstring_hash,
)

# ── Fixture source code ────────────────────────────────────────────────────────

FIXTURE_SOURCE = '''\
from __future__ import annotations

import mcp

server = mcp.Server("test")


@server.tool()
async def echo(message: str, count: int = 1) -> str:
    """Echo the given message count times.

    Repeats the input message exactly count times, joined by newlines.
    Useful for testing output formatting.
    """
    return "\\n".join([message] * count)


@server.tool()
def ping(host: str) -> bool:
    """Ping a host and return True if reachable."""
    return True


def not_a_tool(x: int) -> int:
    """This function has no tool decorator."""
    return x
'''

# ast.get_docstring normalizes indentation (strips common leading whitespace)
ECHO_DOCSTRING = (
    "Echo the given message count times.\n\n"
    "Repeats the input message exactly count times, joined by newlines.\n"
    "Useful for testing output formatting."
)
PING_DOCSTRING = "Ping a host and return True if reachable."


# ── extract_python_tools ──────────────────────────────────────────────────────


def test_extract_python_tools_finds_decorated_functions(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    tools = extract_python_tools(src)

    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"echo", "ping"}


def test_extract_python_tools_verbatim_docstrings(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    tools = {t.name: t for t in extract_python_tools(src)}

    assert tools["echo"].docstring == ECHO_DOCSTRING
    assert tools["ping"].docstring == PING_DOCSTRING


def test_extract_python_tools_skips_non_tool_functions(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    tools = extract_python_tools(src)
    names = {t.name for t in tools}
    assert "not_a_tool" not in names


def test_extract_python_tools_params(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    tools = {t.name: t for t in extract_python_tools(src)}
    echo = tools["echo"]

    assert len(echo.params) == 2
    assert echo.params[0].name == "message"
    assert echo.params[0].annotation == "str"
    assert echo.params[0].default is None

    assert echo.params[1].name == "count"
    assert echo.params[1].annotation == "int"
    assert echo.params[1].default == "1"


def test_extract_python_tools_return_annotation(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    tools = {t.name: t for t in extract_python_tools(src)}
    assert tools["echo"].return_annotation == "str"
    assert tools["ping"].return_annotation == "bool"


def test_extract_python_tools_source_hash_matches(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    tools = {t.name: t for t in extract_python_tools(src)}
    for tool in tools.values():
        expected = tool_docstring_hash(tool.docstring)
        assert tool.source_hash == expected, (
            f"{tool.name}: source_hash={tool.source_hash!r} != hash(docstring)={expected!r}"
        )


# ── tool_docstring_hash ───────────────────────────────────────────────────────


def test_tool_docstring_hash_is_12_hex_chars() -> None:
    h = tool_docstring_hash("hello world")
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


def test_tool_docstring_hash_is_deterministic() -> None:
    doc = "Some docstring content."
    assert tool_docstring_hash(doc) == tool_docstring_hash(doc)


def test_tool_docstring_hash_differs_for_different_inputs() -> None:
    assert tool_docstring_hash("foo") != tool_docstring_hash("bar")


def test_tool_docstring_hash_empty_string() -> None:
    h = tool_docstring_hash("")
    assert len(h) == 12


# ── mirror_to_dict / mirror_from_dict round-trip ──────────────────────────────


def _make_mirror() -> ServerMirror:
    return ServerMirror(
        server_id="test-server",
        source_repo="owner/test-server",
        language="python",
        stars=42,
        stratum="mid",
        notes="test notes",
        tools=[
            MirrorTool(
                name="echo",
                docstring=ECHO_DOCSTRING,
                source_hash=tool_docstring_hash(ECHO_DOCSTRING),
                return_annotation="str",
                params=[
                    MirrorParam(name="message", annotation="str"),
                    MirrorParam(name="count", annotation="int", default="1"),
                ],
            )
        ],
    )


def test_mirror_round_trip() -> None:
    original = _make_mirror()
    d = mirror_to_dict(original)
    restored = mirror_from_dict(d)

    assert restored.server_id == original.server_id
    assert restored.source_repo == original.source_repo
    assert restored.language == original.language
    assert restored.stars == original.stars
    assert restored.stratum == original.stratum
    assert restored.notes == original.notes
    assert len(restored.tools) == 1
    t = restored.tools[0]
    assert t.name == "echo"
    assert t.docstring == ECHO_DOCSTRING
    assert t.source_hash == tool_docstring_hash(ECHO_DOCSTRING)
    assert t.return_annotation == "str"
    assert len(t.params) == 2
    assert t.params[0].name == "message"
    assert t.params[1].default == "1"


def test_mirror_to_dict_is_json_serializable() -> None:
    import json

    mirror = _make_mirror()
    d = mirror_to_dict(mirror)
    # Must not raise
    json.dumps(d)


def test_mirror_from_dict_defaults() -> None:
    minimal = {
        "server_id": "minimal",
        "source_repo": "owner/minimal",
    }
    mirror = mirror_from_dict(minimal)
    assert mirror.language == "unknown"
    assert mirror.stars == 0
    assert mirror.stratum == "unknown"
    assert mirror.notes == ""
    assert mirror.tools == []


# ── assert_docstrings_verbatim ────────────────────────────────────────────────


def test_assert_docstrings_verbatim_passes_on_match(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    mirror = ServerMirror(
        server_id="test",
        source_repo="owner/test",
        language="python",
        stars=0,
        stratum="low",
        tools=[
            MirrorTool(
                name="echo",
                docstring=ECHO_DOCSTRING,
                source_hash=tool_docstring_hash(ECHO_DOCSTRING),
                return_annotation="str",
                params=[],
            )
        ],
    )
    violations = assert_docstrings_verbatim(mirror, src)
    assert violations == []


def test_assert_docstrings_verbatim_catches_docstring_mismatch(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    # Use a different (paraphrased) docstring — should be caught
    bad_docstring = "Echoes the message."
    mirror = ServerMirror(
        server_id="test",
        source_repo="owner/test",
        language="python",
        stars=0,
        stratum="low",
        tools=[
            MirrorTool(
                name="echo",
                docstring=bad_docstring,
                source_hash=tool_docstring_hash(bad_docstring),
                return_annotation="str",
                params=[],
            )
        ],
    )
    violations = assert_docstrings_verbatim(mirror, src)
    assert len(violations) >= 1
    assert any("echo" in v for v in violations)


def test_assert_docstrings_verbatim_catches_hash_mismatch(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    # Correct docstring but wrong hash — should be caught
    mirror = ServerMirror(
        server_id="test",
        source_repo="owner/test",
        language="python",
        stars=0,
        stratum="low",
        tools=[
            MirrorTool(
                name="echo",
                docstring=ECHO_DOCSTRING,
                source_hash="000000000000",  # wrong hash
                return_annotation="str",
                params=[],
            )
        ],
    )
    violations = assert_docstrings_verbatim(mirror, src)
    assert len(violations) >= 1
    assert any("source_hash" in v for v in violations)


def test_assert_docstrings_verbatim_catches_missing_tool(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(FIXTURE_SOURCE, encoding="utf-8")

    ghost_doc = "A tool that doesn't exist in source."
    mirror = ServerMirror(
        server_id="test",
        source_repo="owner/test",
        language="python",
        stars=0,
        stratum="low",
        tools=[
            MirrorTool(
                name="nonexistent_tool",
                docstring=ghost_doc,
                source_hash=tool_docstring_hash(ghost_doc),
                return_annotation="Any",
                params=[],
            )
        ],
    )
    violations = assert_docstrings_verbatim(mirror, src)
    assert len(violations) >= 1
    assert any("nonexistent_tool" in v for v in violations)


# ── mcp.tool() decorator variant ─────────────────────────────────────────────

MCP_DECORATOR_SOURCE = '''\
from __future__ import annotations

from mcp import tool


@tool
def search_files(query: str) -> list[str]:
    """Search for files matching the given query string."""
    return []
'''


def test_extract_python_tools_bare_tool_decorator(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server2.py"
    src.write_text(MCP_DECORATOR_SOURCE, encoding="utf-8")

    tools = extract_python_tools(src)
    assert len(tools) == 1
    assert tools[0].name == "search_files"
    assert tools[0].docstring == "Search for files matching the given query string."


# ── ctx parameter exclusion ───────────────────────────────────────────────────

CTX_SOURCE = '''\
from __future__ import annotations

import mcp

server = mcp.Server("ctx-test")


@server.tool()
async def fetch(ctx: mcp.RequestContext, url: str, timeout: float = 30.0) -> str:
    """Fetch the content at the given URL."""
    return ""
'''


def test_extract_python_tools_excludes_ctx_param(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "ctx_server.py"
    src.write_text(CTX_SOURCE, encoding="utf-8")

    tools = extract_python_tools(src)
    assert len(tools) == 1
    param_names = [p.name for p in tools[0].params]
    assert "ctx" not in param_names
    assert "url" in param_names
    assert "timeout" in param_names
