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


def extract_python_tools(source_path: pathlib.Path) -> list[MirrorTool]:
    """Parse a Python MCP server file and extract tool definitions.

    Looks for functions decorated with any decorator whose name or attribute
    contains 'tool' (e.g. @server.tool(), @mcp.tool(), @app.tool, @tool).
    Returns tools with verbatim docstrings.
    """
    source_text = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(source_path))
    tools: list[MirrorTool] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _has_tool_decorator(node):
            continue

        docstring = ast.get_docstring(node) or ""
        params = _extract_params(node)
        return_ann = _annotation_to_str(node.returns)

        tools.append(
            MirrorTool(
                name=node.name,
                docstring=docstring,
                params=params,
                source_hash=tool_docstring_hash(docstring),
                return_annotation=return_ann,
            )
        )

    return tools


def _has_tool_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        dec_str = ast.unparse(dec).lower()
        if "tool" in dec_str:
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
