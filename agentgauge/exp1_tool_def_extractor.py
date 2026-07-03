from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import TypeGuard

from agentgauge.exp1_doc_density import ExtractedParam, ExtractedTool
from agentgauge.exp1_mirror import extract_python_tools

# Deterministic, script-only tool-definition extraction (git clone + static parsing —
# no LLM, no agent fan-out). Replaces an earlier LLM-agent-based extraction approach
# that was slow (up to ~30min/batch), expensive, and repeatedly stalled: extraction is
# retrieval, not research, so it belongs in a script, not a research agent.
#
# Python gets exact AST-based extraction (agentgauge.exp1_mirror.extract_python_tools,
# already used by the mirroring pipeline). Other languages get a best-effort, clearly
# lower-confidence regex proximity extractor — real AST parsing per-language is out of
# scope for this pass. Extraction confidence is reported per repo so downstream scoring
# never silently treats a partial/failed extraction as a clean "near-empty" result.

_SOURCE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "typescript": (".ts", ".tsx"),
    "javascript": (".js", ".mjs", ".cjs", ".jsx"),
    "go": (".go",),
    "java": (".java",),
    "rust": (".rs",),
    "c": (".c", ".h"),
}

_EXCLUDED_DIR_NAMES = frozenset(
    {
        "node_modules",
        "vendor",
        "dist",
        "build",
        ".git",
        "target",
        "__pycache__",
        ".venv",
        "venv",
        "test",
        "tests",
        "__tests__",
        "examples",
        "docs",
    }
)

_MAX_FILE_BYTES = 300_000  # skip generated/bundled files that dwarf hand-written source


class CloneError(RuntimeError):
    pass


def clone_shallow(repo: str, dest: Path, timeout_s: float = 90.0) -> None:
    """git clone --depth 1 https://github.com/{repo}.git into dest."""
    url = f"https://github.com/{repo}.git"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, str(dest)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    if result.returncode != 0:
        raise CloneError(f"git clone failed for {repo}: {result.stderr.strip()}")


def find_source_files(repo_dir: Path, extensions: tuple[str, ...]) -> list[Path]:
    """All files under repo_dir with a matching extension, excluding vendor/build/test dirs."""
    files: list[Path] = []
    for path in repo_dir.rglob("*"):
        if not path.is_file() or path.suffix not in extensions:
            continue
        if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files


# ── Python: exact AST-based extraction (reuses the mirroring pipeline) ────────────

_ARGS_SECTION_RE = re.compile(r"^(Args|Arguments|Parameters):\s*$")
_SECTION_END_RE = re.compile(r"^(Returns|Raises|Yields|Examples?|Notes?):\s*$")
_ARG_LINE_RE = re.compile(r"^(\w+)(?:\s*\([^)]*\))?:\s*(.*)$")


def parse_docstring_param_descriptions(docstring: str) -> dict[str, str]:
    """Best-effort Google-style 'Args:' section parser -> {param_name: description}."""
    result: dict[str, str] = {}
    current_param: str | None = None
    current_desc: list[str] = []
    in_args = False

    def _flush() -> None:
        if current_param is not None:
            result[current_param] = " ".join(current_desc).strip()

    for raw_line in docstring.splitlines():
        stripped = raw_line.strip()
        if _ARGS_SECTION_RE.match(stripped):
            in_args = True
            continue
        if not in_args:
            continue
        if _SECTION_END_RE.match(stripped):
            break
        indented = raw_line.startswith(("    ", "\t"))
        m = _ARG_LINE_RE.match(stripped)
        if m and indented:
            _flush()
            current_param = m.group(1)
            current_desc = [m.group(2)] if m.group(2) else []
        elif current_param and stripped:
            current_desc.append(stripped)
    _flush()
    return result


def extract_python_tool_defs(files: list[Path]) -> list[ExtractedTool]:
    """Decorator-based tools (AST, via the mirroring pipeline) plus a supplementary
    pass for the imperative `<mcp>.add_tool(<function_name>)` registration idiom --
    a plain function defined at module level with no decorator, referenced by name
    in a call or list elsewhere. Both are real, observed FastMCP patterns; dedup by
    name, decorator-based wins on conflict."""
    tools: list[ExtractedTool] = []
    seen_names: set[str] = set()
    for f in files:
        try:
            mirror_tools = extract_python_tools(f)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        for mt in mirror_tools:
            if mt.name in seen_names:
                continue
            seen_names.add(mt.name)
            param_descs = parse_docstring_param_descriptions(mt.docstring)
            params = [
                ExtractedParam(name=p.name, description=param_descs.get(p.name, ""))
                for p in mt.params
            ]
            tools.append(ExtractedTool(name=mt.name, description=mt.docstring, params=params))

    for t in extract_python_add_tool_calls(files):
        if t.name in seen_names:
            continue
        seen_names.add(t.name)
        tools.append(t)

    return tools


def _is_add_tool_call(node: ast.AST) -> TypeGuard[ast.Call]:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_tool"
        and bool(node.args)
    )


def extract_python_add_tool_calls(files: list[Path]) -> list[ExtractedTool]:
    """AST detection of the imperative `<obj>.add_tool(...)` FastMCP registration
    idiom: tool functions defined at module level with no decorator, registered
    either directly (`mcp.add_tool(some_func)`) or indirectly via a list literal
    looped over (`tools = [fn1, fn2]; for t in tools: mcp.add_tool(t)` -- the
    observed real-world shape). Resolves the referenced name(s) back to their
    module-level function def to pull the same docstring/param info the decorator
    path would."""
    tools: list[ExtractedTool] = []
    seen_names: set[str] = set()
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(text, filename=str(f))
        except (SyntaxError, UnicodeDecodeError, ValueError, OSError):
            continue

        func_defs = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        list_literals: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.List)
            ):
                names = [elt.id for elt in node.value.elts if isinstance(elt, ast.Name)]
                if names:
                    list_literals[node.targets[0].id] = names

        referenced_names: set[str] = set()
        for node in ast.walk(tree):
            if _is_add_tool_call(node) and isinstance(node.args[0], ast.Name):
                if node.args[0].id in func_defs:
                    referenced_names.add(node.args[0].id)
                continue
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                loop_var = node.target.id
                calls_add_tool_on_loop_var = any(
                    _is_add_tool_call(n)
                    and isinstance(n.args[0], ast.Name)
                    and n.args[0].id == loop_var
                    for n in ast.walk(node)
                )
                if not calls_add_tool_on_loop_var:
                    continue
                if isinstance(node.iter, ast.List):
                    referenced_names.update(
                        elt.id for elt in node.iter.elts if isinstance(elt, ast.Name)
                    )
                elif isinstance(node.iter, ast.Name) and node.iter.id in list_literals:
                    referenced_names.update(list_literals[node.iter.id])

        for name in referenced_names:
            fn = func_defs.get(name)
            if fn is None or name in seen_names:
                continue
            seen_names.add(name)
            docstring = ast.get_docstring(fn) or ""
            param_descs = parse_docstring_param_descriptions(docstring)
            params = [
                ExtractedParam(name=a.arg, description=param_descs.get(a.arg, ""))
                for a in fn.args.args
                if a.arg != "self"
            ]
            tools.append(ExtractedTool(name=name, description=docstring, params=params))
    return tools


# ── Non-Python: best-effort regex proximity extraction ─────────────────────────────
#
# No true AST for these languages here — this looks for a tool-registration "name"
# token followed within a bounded window by a "description" string, matching the
# handful of conventions observed across the vetted pool (MCP TS SDK .tool()/
# .registerTool(), mark3labs/mcp-go mcp.NewTool()/mcp.WithDescription(), and generic
# JSON-schema-shaped object literals). Lower confidence than the Python path by
# construction; callers should treat a zero-tool result here as "extraction failed",
# not "server has no tools".


def _quoted(quote_group: str, content_group: str) -> str:
    """A quoted-string fragment where the CLOSING quote matches whichever quote char
    opened it (so an apostrophe inside a double-quoted string, e.g. "user's profile",
    isn't mistaken for the terminator)."""
    return (
        rf"(?P<{quote_group}>['\"`])"
        rf"(?P<{content_group}>(?:\\.|(?!(?P={quote_group}))[^\\])*)"
        rf"(?P={quote_group})"
    )


_NON_PYTHON_PATTERNS: tuple[re.Pattern[str], ...] = (
    # MCP TS SDK: server.tool("name", "description", schema, handler)
    re.compile(r"""\.tool\(\s*""" + _quoted("q1", "name") + r"""\s*,\s*""" + _quoted("q2", "desc")),
    # MCP TS SDK: server.registerTool("name", { ... description: "...", ... }, handler)
    re.compile(
        r"""registerTool\(\s*"""
        + _quoted("q3", "name")
        + r"""[\s\S]{0,200}?description\s*:\s*"""
        + _quoted("q4", "desc")
    ),
    # Go mark3labs/mcp-go: mcp.NewTool("name", ..., mcp.WithDescription("..."))
    re.compile(
        r"""mcp\.NewTool\(\s*"(?P<name>[\w.\-]+)"[\s\S]{0,300}?mcp\.WithDescription\(\s*"""
        r"""(?P<q5>")(?P<desc>(?:\\.|(?!(?P=q5))[^\\])*)(?P=q5)"""
    ),
    # Generic object/struct literal: name: "..." ... description: "..."
    re.compile(
        r"""\bname\s*[:=]\s*"""
        + _quoted("q6", "name")
        + r"""[\s\S]{0,300}?\bdescription\s*[:=]\s*"""
        + _quoted("q7", "desc")
    ),
    # Generic JSON literal: "name": "..." ... "description": "..."
    re.compile(
        r'"name"\s*:\s*"(?P<name>[\w.\-]+)"[\s\S]{0,300}?"description"\s*:\s*'
        r'(?P<q8>")(?P<desc>(?:\\.|(?!(?P=q8))[^\\])*)(?P=q8)'
    ),
)


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\'", "'").replace("\\n", " ").replace("\\t", " ")


def extract_non_python_tool_defs(files: list[Path]) -> list[ExtractedTool]:
    seen_names: set[str] = set()
    tools: list[ExtractedTool] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in _NON_PYTHON_PATTERNS:
            for m in pattern.finditer(text):
                name, desc = m.group("name"), _unescape(m.group("desc"))
                if name in seen_names:
                    continue
                seen_names.add(name)
                tools.append(ExtractedTool(name=name, description=desc, params=[]))
    return tools


# ── Dispatcher ──────────────────────────────────────────────────────────────────


def extract_tools_for_repo(repo_dir: Path, language: str) -> tuple[list[ExtractedTool], str]:
    """Returns (tools, extraction_method). extraction_method is 'ast' for Python,
    'regex_best_effort' otherwise -- callers should treat the latter as lower confidence.
    'regex_fallback_on_python' is a third, LOWEST-confidence tier: AST found nothing (no
    decorators, no add_tool() calls) so we fall back to the same JSON/dict-literal regex
    used for non-Python sources -- observed in servers that declare tools as a plain
    module-level TOOLS_SCHEMA = [{"name": ..., "description": ...}] list."""
    lang = language.lower()
    if lang == "python":
        files = find_source_files(repo_dir, _SOURCE_EXTENSIONS["python"])
        tools = extract_python_tool_defs(files)
        if tools:
            return tools, "ast"
        fallback_tools = extract_non_python_tool_defs(files)
        if fallback_tools:
            return fallback_tools, "regex_fallback_on_python"
        return [], "ast"

    # Best-effort: scan every known non-Python extension present, since a repo's
    # reported "language" (e.g. from GitHub's linguist) doesn't always match where the
    # tool-registration code actually lives (e.g. a "Go" repo with a TS test harness).
    all_exts = tuple(ext for exts in _SOURCE_EXTENSIONS.values() for ext in exts if ext != ".py")
    files = find_source_files(repo_dir, all_exts)
    return extract_non_python_tool_defs(files), "regex_best_effort"
