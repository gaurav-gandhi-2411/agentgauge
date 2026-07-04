from __future__ import annotations

import pathlib

from agentgauge.exp1_tool_def_extractor import (
    extract_non_python_tool_defs,
    extract_python_add_tool_calls,
    extract_python_tool_constructor_calls,
    extract_python_tool_defs,
    extract_tools_for_repo,
    find_source_files,
    parse_docstring_param_descriptions,
)

# ── parse_docstring_param_descriptions ────────────────────────────────────────────


def test_parse_docstring_params_google_style() -> None:
    docstring = """Search arXiv for papers.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.

    Returns:
        A list of paper summaries.
    """
    params = parse_docstring_param_descriptions(docstring)
    assert params["query"] == "The search query string."
    assert params["max_results"] == "Maximum number of results to return."
    assert "Returns" not in params


def test_parse_docstring_params_no_args_section() -> None:
    assert parse_docstring_param_descriptions("Just a summary, no Args section.") == {}


def test_parse_docstring_params_multiline_description() -> None:
    docstring = """Do a thing.

    Args:
        thing_id: The identifier of the thing.
            Must be a valid UUID string.
    """
    params = parse_docstring_param_descriptions(docstring)
    assert params["thing_id"] == "The identifier of the thing. Must be a valid UUID string."


def test_parse_docstring_params_type_annotated_args() -> None:
    docstring = """Fetch a URL.

    Args:
        url (str): The URL to fetch.
        timeout (float): Request timeout in seconds.
    """
    params = parse_docstring_param_descriptions(docstring)
    assert params["url"] == "The URL to fetch."
    assert params["timeout"] == "Request timeout in seconds."


# ── extract_python_tool_defs ──────────────────────────────────────────────────────

_PY_FIXTURE = '''\
from __future__ import annotations

import mcp

server = mcp.Server("test")


@server.tool()
def search_papers(query: str, max_results: int = 10) -> list[str]:
    """Search arXiv for papers matching a query.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
    """
    return []


@server.tool()
def read_paper(paper_id: str) -> str:
    """Download and read a specific paper by ID."""
    return ""
'''


def test_extract_python_tool_defs(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(_PY_FIXTURE, encoding="utf-8")

    tools = extract_python_tool_defs([src])
    assert len(tools) == 2

    search = next(t for t in tools if t.name == "search_papers")
    assert "Search arXiv" in search.description
    param_names = {p.name for p in search.params}
    assert param_names == {"query", "max_results"}
    query_param = next(p for p in search.params if p.name == "query")
    assert query_param.description == "The search query string."

    read = next(t for t in tools if t.name == "read_paper")
    assert read.description == "Download and read a specific paper by ID."
    # paper_id comes from the function signature (AST); it has no docstring Args entry.
    assert [p.name for p in read.params] == ["paper_id"]
    assert read.params[0].description == ""


def test_extract_python_tool_defs_skips_unparseable_files(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("def f(:\n    this is not valid python", encoding="utf-8")
    assert extract_python_tool_defs([bad]) == []


# ── extract_python_add_tool_calls (imperative FastMCP registration, no decorator) ──

_PY_FIXTURE_ADD_TOOL = '''\
from __future__ import annotations

def get_cik_by_ticker(ticker: str):
    """Convert a stock ticker symbol to its SEC CIK.

    Args:
        ticker: Stock ticker symbol.
    """
    return ""


def _internal_helper(x: int) -> int:
    """Not registered as a tool -- never referenced by add_tool()."""
    return x


def register_tools(mcp):
    tools = [get_cik_by_ticker]
    for t in tools:
        mcp.add_tool(t)
'''


def test_extract_python_add_tool_calls(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(_PY_FIXTURE_ADD_TOOL, encoding="utf-8")

    tools = extract_python_add_tool_calls([src])
    assert len(tools) == 1
    assert tools[0].name == "get_cik_by_ticker"
    assert "SEC CIK" in tools[0].description
    assert tools[0].params[0].name == "ticker"
    assert tools[0].params[0].description == "Stock ticker symbol."


def test_extract_python_tool_defs_includes_add_tool_registrations(tmp_path: pathlib.Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(_PY_FIXTURE_ADD_TOOL, encoding="utf-8")

    tools = extract_python_tool_defs([src])
    names = {t.name for t in tools}
    assert names == {"get_cik_by_ticker"}


_PY_FIXTURE_DECORATOR_AND_ADD_TOOL = '''\
from __future__ import annotations

import mcp

server = mcp.Server("test")


@server.tool()
def decorated_tool(x: int) -> int:
    """A normally decorated tool."""
    return x


def imperative_tool(y: int) -> int:
    """Registered imperatively, no decorator."""
    return y


server.add_tool(imperative_tool)
'''


def test_extract_python_tool_defs_merges_decorator_and_imperative(
    tmp_path: pathlib.Path,
) -> None:
    src = tmp_path / "server.py"
    src.write_text(_PY_FIXTURE_DECORATOR_AND_ADD_TOOL, encoding="utf-8")

    tools = extract_python_tool_defs([src])
    names = {t.name for t in tools}
    assert names == {"decorated_tool", "imperative_tool"}


# ── extract_tools_for_repo: Python regex-literal fallback ─────────────────────────

_PY_FIXTURE_SCHEMA_LITERAL = """\
TOOLS_SCHEMA = [
    {"name": "smart_search", "description": "Primary recall path for agents.", "inputSchema": {}},
    {"name": "synthesize", "description": "Generate background context from memory.", "inputSchema": {}},
]
"""


def test_extract_tools_for_repo_python_falls_back_to_regex_literal(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "tools_schema.py").write_text(_PY_FIXTURE_SCHEMA_LITERAL, encoding="utf-8")
    tools, method = extract_tools_for_repo(tmp_path, "python")
    assert method == "regex_fallback_on_python"
    names = {t.name for t in tools}
    assert names == {"smart_search", "synthesize"}


def test_extract_tools_for_repo_python_prefers_ast_over_fallback(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "server.py").write_text(_PY_FIXTURE, encoding="utf-8")
    tools, method = extract_tools_for_repo(tmp_path, "python")
    assert method == "ast"
    assert len(tools) == 2


# ── extract_python_tool_constructor_calls (types.Tool(name=..., description=...)) ──

_PY_FIXTURE_TOOL_CONSTRUCTOR = '''\
from mcp import types

search_tool = types.Tool(
    name="search_papers",
    description="""Search for papers on arXiv with advanced filtering."""
)

read_tool = types.Tool(
    name="read_paper",
    description="Download and read a specific paper by ID.",
)
'''


def test_extract_python_tool_constructor_calls(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "search.py"
    f.write_text(_PY_FIXTURE_TOOL_CONSTRUCTOR, encoding="utf-8")

    tools = extract_python_tool_constructor_calls([f])
    names = {t.name for t in tools}
    assert names == {"search_papers", "read_paper"}
    search = next(t for t in tools if t.name == "search_papers")
    assert search.description == "Search for papers on arXiv with advanced filtering."


_PY_FIXTURE_TOOL_CONSTRUCTOR_CONCAT_DESC = """\
download_tool = types.Tool(
    name="download_paper",
    annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=True),
    description=(
        "Download a paper from arXiv and return its text content. "
        "Falls back to PDF conversion if HTML is unavailable."
    ),
    inputSchema={"type": "object", "properties": {}},
)
"""


def test_extract_python_tool_constructor_calls_handles_implicit_string_concat(
    tmp_path: pathlib.Path,
) -> None:
    """Regression: description=(\\n \"a \" \"b\"\\n) -- Python's implicit adjacent-
    string-literal concatenation, used for long descriptions split across lines
    (observed: blazickjp/arxiv-mcp-server download_tool). Also confirms a kwarg
    (annotations=...) between name= and description= doesn't break the match."""
    f = tmp_path / "download.py"
    f.write_text(_PY_FIXTURE_TOOL_CONSTRUCTOR_CONCAT_DESC, encoding="utf-8")

    tools = extract_python_tool_constructor_calls([f])
    assert len(tools) == 1
    assert tools[0].name == "download_paper"
    assert tools[0].description == (
        "Download a paper from arXiv and return its text content. "
        "Falls back to PDF conversion if HTML is unavailable."
    )


# Regression: mcp.types.Prompt(name=..., description=...) and its PromptArgument(...)
# entries share the exact name=/description= shape with types.Tool(...) but are a
# DIFFERENT MCP primitive (prompts, not tools) -- observed in blazickjp/arxiv-mcp-server,
# where 7 prompts + their arguments were extracted as 14 phantom tools. The constructor
# pattern must be anchored on "Tool(" specifically and must NOT match "Prompt(" or
# "PromptArgument(".
_PY_FIXTURE_PROMPT_NOT_TOOL = """\
from mcp.types import Prompt, PromptArgument

PROMPTS = {
    "research-discovery": Prompt(
        name="research-discovery",
        description="Begin research exploration on a specific topic",
        arguments=[
            PromptArgument(
                name="topic", description="Research topic or question", required=True
            ),
        ],
    ),
}
"""


def test_extract_python_tool_constructor_calls_excludes_prompts(
    tmp_path: pathlib.Path,
) -> None:
    f = tmp_path / "prompts.py"
    f.write_text(_PY_FIXTURE_PROMPT_NOT_TOOL, encoding="utf-8")

    tools = extract_python_tool_constructor_calls([f])
    assert tools == []


def test_extract_tools_for_repo_python_prefers_constructor_over_generic_fallback(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "search.py").write_text(_PY_FIXTURE_TOOL_CONSTRUCTOR, encoding="utf-8")
    tools, method = extract_tools_for_repo(tmp_path, "python")
    assert method == "tool_constructor_python"
    assert {t.name for t in tools} == {"search_papers", "read_paper"}


def test_extract_tools_for_repo_python_excludes_prompts_when_real_tools_present(
    tmp_path: pathlib.Path,
) -> None:
    """The real-world shape this regression guards: a repo with BOTH a prompts.py
    (no tools) and a genuine Tool()-constructor file elsewhere -- prompts must not
    leak into the extracted tool set."""
    (tmp_path / "prompts.py").write_text(_PY_FIXTURE_PROMPT_NOT_TOOL, encoding="utf-8")
    (tmp_path / "search.py").write_text(_PY_FIXTURE_TOOL_CONSTRUCTOR, encoding="utf-8")
    tools, method = extract_tools_for_repo(tmp_path, "python")
    assert method == "tool_constructor_python"
    assert {t.name for t in tools} == {"search_papers", "read_paper"}


def test_extract_tools_for_repo_python_prompts_only_falls_through_to_generic_last_resort(
    tmp_path: pathlib.Path,
) -> None:
    """Documented, intentional lowest-confidence behavior: if NO Tool() constructor
    exists anywhere in the repo, the dispatcher falls through to the fully generic
    name/description proximity match as a last resort -- imprecise, but still the
    documented 'regex_fallback_on_python' tier, not a silent zero."""
    (tmp_path / "prompts.py").write_text(_PY_FIXTURE_PROMPT_NOT_TOOL, encoding="utf-8")
    tools, method = extract_tools_for_repo(tmp_path, "python")
    assert method == "regex_fallback_on_python"
    assert len(tools) > 0


# ── extract_non_python_tool_defs ──────────────────────────────────────────────────

_TS_FIXTURE_OLD_STYLE = """
server.tool("search_flights", "Search for flights between two airports on a given date", schema, async (params) => {
  return [];
});

server.tool("search_hotels", "Search for hotels near a destination", schema2, async (params) => {
  return [];
});
"""


def test_extract_non_python_ts_old_style(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "server.ts"
    f.write_text(_TS_FIXTURE_OLD_STYLE, encoding="utf-8")

    tools = extract_non_python_tool_defs([f])
    names = {t.name for t in tools}
    assert names == {"search_flights", "search_hotels"}
    flights = next(t for t in tools if t.name == "search_flights")
    assert flights.description == "Search for flights between two airports on a given date"


_TS_FIXTURE_REGISTER_TOOL = """
server.registerTool("get_user_profile", {
  title: "Get User Profile",
  description: "Fetch a LinkedIn user's public profile information",
  inputSchema: { type: "object", properties: {} },
}, async (params) => {});
"""


def test_extract_non_python_ts_register_tool_style(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "server.ts"
    f.write_text(_TS_FIXTURE_REGISTER_TOOL, encoding="utf-8")

    tools = extract_non_python_tool_defs([f])
    assert len(tools) == 1
    assert tools[0].name == "get_user_profile"
    assert tools[0].description == "Fetch a LinkedIn user's public profile information"


_GO_FIXTURE = """
tool := mcp.NewTool("query_tickets",
    mcp.WithDescription("Query available train tickets between two stations"),
    mcp.WithString("from_station", mcp.Description("Departure station code")),
)
"""


def test_extract_non_python_go_style(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "tools.go"
    f.write_text(_GO_FIXTURE, encoding="utf-8")

    tools = extract_non_python_tool_defs([f])
    assert len(tools) == 1
    assert tools[0].name == "query_tickets"
    assert tools[0].description == "Query available train tickets between two stations"


_JSON_LITERAL_FIXTURE = """
const TOOLS = [
  {"name": "list_files", "description": "List files in a directory", "inputSchema": {}},
  {"name": "read_file", "description": "Read the contents of a file", "inputSchema": {}},
];
"""


def test_extract_non_python_json_literal_style(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "tools.js"
    f.write_text(_JSON_LITERAL_FIXTURE, encoding="utf-8")

    tools = extract_non_python_tool_defs([f])
    names = {t.name for t in tools}
    assert names == {"list_files", "read_file"}


def test_extract_non_python_no_descriptions_yields_no_tools(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "empty.ts"
    f.write_text("export function doSomething() { return 1; }", encoding="utf-8")
    assert extract_non_python_tool_defs([f]) == []


def test_extract_non_python_dedupes_by_name(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "dup.ts"
    f.write_text(
        'server.tool("ping", "Ping the server", s, h);\n'
        'server.tool("ping", "Ping the server again", s, h);\n',
        encoding="utf-8",
    )
    tools = extract_non_python_tool_defs([f])
    assert len(tools) == 1


# ── find_source_files ──────────────────────────────────────────────────────────────


def test_find_source_files_excludes_vendor_dirs(tmp_path: pathlib.Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "tools.py").write_text("# real", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "vendored.py").write_text("# vendored", encoding="utf-8")

    files = find_source_files(tmp_path, (".py",))
    names = {f.name for f in files}
    assert "tools.py" in names
    assert "vendored.py" not in names


def test_find_source_files_skips_oversized_files(tmp_path: pathlib.Path) -> None:
    small = tmp_path / "small.py"
    small.write_text("x = 1", encoding="utf-8")
    big = tmp_path / "big.py"
    big.write_text("x" * 400_000, encoding="utf-8")

    files = find_source_files(tmp_path, (".py",))
    names = {f.name for f in files}
    assert "small.py" in names
    assert "big.py" not in names


# ── extract_tools_for_repo dispatcher ────────────────────────────────────────────


def test_extract_tools_for_repo_python_uses_ast_method(tmp_path: pathlib.Path) -> None:
    (tmp_path / "server.py").write_text(_PY_FIXTURE, encoding="utf-8")
    tools, method = extract_tools_for_repo(tmp_path, "python")
    assert method == "ast"
    assert len(tools) == 2


def test_extract_tools_for_repo_typescript_uses_regex_method(tmp_path: pathlib.Path) -> None:
    (tmp_path / "server.ts").write_text(_TS_FIXTURE_OLD_STYLE, encoding="utf-8")
    tools, method = extract_tools_for_repo(tmp_path, "typescript")
    assert method == "regex_best_effort"
    assert len(tools) == 2
