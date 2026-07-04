from __future__ import annotations

import ast
import hashlib
import json
import pathlib
from dataclasses import dataclass, field


@dataclass
class MirrorParam:
    name: str
    annotation: str  # as a string, e.g. "str", "int", "list[str]"
    default: str | None = None  # string repr if there's a default


@dataclass
class MirrorTool:
    name: str
    docstring: str  # VERBATIM from source
    params: list[MirrorParam]
    source_hash: str  # SHA-256[:12] of the raw docstring bytes
    return_annotation: str = "None"


@dataclass
class ServerMirror:
    server_id: str
    source_repo: str  # e.g. "github/github-mcp-server"
    language: str  # "python", "typescript", "go", "other"
    stars: int
    stratum: str  # "high", "mid", "low"
    tools: list[MirrorTool] = field(default_factory=list)
    notes: str = ""


def tool_docstring_hash(docstring: str) -> str:
    """SHA-256[:12] of the verbatim docstring bytes."""
    return hashlib.sha256(docstring.encode()).hexdigest()[:12]


def _decorator_kwarg_str(node: ast.FunctionDef | ast.AsyncFunctionDef, kwarg: str) -> str | None:
    """First string-literal value of `kwarg=` passed to any decorator call on node,
    e.g. @mcp.tool(name="x", description="y") -> _decorator_kwarg_str(node, "description")
    returns "y". None if no decorator passes that kwarg as a plain string literal."""
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        for kw in dec.keywords:
            if (
                kw.arg == kwarg
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                return kw.value.value
    return None


def extract_python_tools(source_path: pathlib.Path) -> list[MirrorTool]:
    """Parse a Python MCP server file and extract tool definitions.

    Looks for functions decorated with any decorator whose name or attribute
    contains 'tool' (e.g. @server.tool(), @mcp.tool(), @app.tool, @tool).

    Description precedence matches FastMCP's own runtime behavior: an explicit
    description="..." decorator keyword argument (e.g. @mcp.tool(description="..."))
    OVERRIDES the function's docstring if both are present; the docstring is only
    used as a fallback when no decorator kwarg is given. A prior version of this
    function read ONLY the docstring, silently mis-extracting "" for every tool
    that uses the (very common, officially-documented) decorator-kwarg style --
    observed: lucasastorian/llmwiki, where all 13 tools carry real, substantial
    descriptions as decorator kwargs but had bare/empty function docstrings.
    Similarly, an explicit name="..." kwarg overrides the Python function name,
    since that -- not the function name -- is what MCP registers as the tool name.
    """
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(source_path))
    tools: list[MirrorTool] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _has_tool_decorator(node):
            continue

        decorator_description = _decorator_kwarg_str(node, "description")
        docstring = (
            decorator_description
            if decorator_description is not None
            else (ast.get_docstring(node) or "")
        )
        name = _decorator_kwarg_str(node, "name") or node.name
        params = _extract_params(node)
        return_ann = _annotation_to_str(node.returns)

        tools.append(
            MirrorTool(
                name=name,
                docstring=docstring,
                params=params,
                source_hash=tool_docstring_hash(docstring),
                return_annotation=return_ann,
            )
        )

    return tools


# Low-level MCP SDK Server class registration methods -- required protocol-handler
# boilerplate present on essentially every low-level-SDK server, NOT domain tool
# decorators. "list_tools"/"call_tool" contain the substring "tool" and were
# false-positiving as if they were @server.tool()-style domain-tool decorators
# (observed: vitali87/code-graph-rag, whose real ~10-tool catalog lives behind a
# dynamic registry these two handlers dispatch to -- not itself AST-extractable).
_MCP_PROTOCOL_HANDLER_NAMES = frozenset(
    {
        "list_tools",
        "call_tool",
        "list_resources",
        "read_resource",
        "list_prompts",
        "get_prompt",
        "list_resource_templates",
        "subscribe_resource",
        "unsubscribe_resource",
        "set_logging_level",
        "completion",
    }
)


def _decorator_attr_name(dec: ast.expr) -> str | None:
    func = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _has_tool_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True iff node has a decorator whose CALLED NAME (attribute or bare name --
    e.g. "tool" in @mcp.tool(), @server.tool()) contains "tool".

    Deliberately checks ONLY the decorator's called name, not ast.unparse(dec) of
    the whole decorator (a prior version did the latter and false-positived on ANY
    decorator whose STRING ARGUMENTS happen to contain "tool" -- observed:
    @self._app.route("/get_tool_stats") (a Flask dashboard route, argument path
    contains "tool") and @click.option("--tool-timeout", ...) (a CLI flag name)
    in oraios/serena, both mistaken for tool-registration decorators).
    """
    for dec in node.decorator_list:
        attr_name = _decorator_attr_name(dec)
        if attr_name is None or attr_name in _MCP_PROTOCOL_HANDLER_NAMES:
            continue
        if "tool" in attr_name.lower():
            return True
    return False


def _extract_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[MirrorParam]:
    params: list[MirrorParam] = []
    args = node.args
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        if arg.arg in ("self", "cls", "ctx"):
            continue
        ann = _annotation_to_str(arg.annotation)
        default_idx = i - defaults_offset
        default = ast.unparse(args.defaults[default_idx]) if default_idx >= 0 else None
        params.append(MirrorParam(name=arg.arg, annotation=ann, default=default))
    return params


def _annotation_to_str(node: ast.expr | None) -> str:
    if node is None:
        return "Any"
    return ast.unparse(node)


def mirror_to_dict(mirror: ServerMirror) -> dict:
    """Serialize a ServerMirror to a JSON-serializable dict."""
    return {
        "server_id": mirror.server_id,
        "source_repo": mirror.source_repo,
        "language": mirror.language,
        "stars": mirror.stars,
        "stratum": mirror.stratum,
        "notes": mirror.notes,
        "tools": [
            {
                "name": t.name,
                "docstring": t.docstring,
                "source_hash": t.source_hash,
                "return_annotation": t.return_annotation,
                "params": [
                    {"name": p.name, "annotation": p.annotation, "default": p.default}
                    for p in t.params
                ],
            }
            for t in mirror.tools
        ],
    }


def mirror_from_dict(d: dict) -> ServerMirror:
    """Deserialize a ServerMirror from a dict (loaded from JSON)."""
    tools = [
        MirrorTool(
            name=t["name"],
            docstring=t["docstring"],
            source_hash=t["source_hash"],
            return_annotation=t.get("return_annotation", "None"),
            params=[
                MirrorParam(
                    name=p["name"],
                    annotation=p["annotation"],
                    default=p.get("default"),
                )
                for p in t.get("params", [])
            ],
        )
        for t in d.get("tools", [])
    ]
    return ServerMirror(
        server_id=d["server_id"],
        source_repo=d["source_repo"],
        language=d.get("language", "unknown"),
        stars=d.get("stars", 0),
        stratum=d.get("stratum", "unknown"),
        notes=d.get("notes", ""),
        tools=tools,
    )


def load_mirror(path: pathlib.Path) -> ServerMirror:
    """Load a ServerMirror from a JSON file."""
    return mirror_from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_mirror(mirror: ServerMirror, path: pathlib.Path) -> None:
    """Save a ServerMirror to a JSON file."""
    path.write_text(
        json.dumps(mirror_to_dict(mirror), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def assert_docstrings_verbatim(mirror: ServerMirror, source_path: pathlib.Path) -> list[str]:
    """Assert that every tool's docstring in the mirror matches the source file.

    Returns a list of violation strings; empty list = PASS.
    Fails if source_hash doesn't match recomputed hash from the mirror's docstring,
    OR if the mirror has a tool that can't be found in the re-extracted source tools.
    """
    source_tools = {t.name: t for t in extract_python_tools(source_path)}
    violations: list[str] = []
    for t in mirror.tools:
        if t.name not in source_tools:
            violations.append(f"{t.name}: not found in source file {source_path}")
            continue
        src = source_tools[t.name]
        if t.docstring != src.docstring:
            violations.append(
                f"{t.name}: docstring mismatch\n"
                f"  mirror:  {t.docstring!r}\n"
                f"  source: {src.docstring!r}"
            )
        expected_hash = tool_docstring_hash(t.docstring)
        if t.source_hash != expected_hash:
            violations.append(
                f"{t.name}: source_hash={t.source_hash!r} but hash(docstring)={expected_hash!r}"
            )
    return violations
