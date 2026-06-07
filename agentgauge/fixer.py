from __future__ import annotations

import difflib
import json
import re
import statistics
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from mcp.types import Tool

from agentgauge._json import extract_json_object
from agentgauge.providers import Message, Provider
from agentgauge.scorer import score_schema_completeness


class ValidationMode(Enum):
    DETERMINISTIC = "deterministic"  # schema_completeness — heuristic, no LLM
    JUDGE_BASED = "judge_based"  # description_quality — LLM judge, σ-gated


# Determined by reading scorer.py (do not change without re-reading scorer.py):
# schema_completeness: pure static heuristic → exact delta, single pass
# description_quality: LLM judge → N≥5 trials, paired delta, σ-gated
VALIDATION_MODE: dict[str, ValidationMode] = {
    "schema_completeness": ValidationMode.DETERMINISTIC,
    "description_quality": ValidationMode.JUDGE_BASED,
}

JUDGE_MODEL_DEFAULT = "llama3.1:8b"
DEFAULT_MIN_DELTA = 10.0
DEFAULT_SKIP_ABOVE_BAND = 90.0
DEFAULT_TRIALS = 5

# Tokens in tool names that carry no domain-specific semantic signal.
# A tool name with only these tokens + single-char tokens is considered opaque.
_GENERIC_TOKENS: frozenset[str] = frozenset(
    {
        "get",
        "set",
        "put",
        "del",
        "delete",
        "create",
        "update",
        "list",
        "fetch",
        "post",
        "add",
        "remove",
        "do",
        "run",
        "exec",
        "execute",
        "handle",
        "process",
        "send",
        "receive",
        "read",
        "write",
        "push",
        "pull",
        "new",
        "make",
        "build",
        "init",
        "start",
        "stop",
        "reset",
        "load",
        "save",
        "check",
        "test",
        "use",
        "show",
        "find",
        "apply",
        "call",
        "return",
        "transform",
        "convert",
        "compute",
        "calculate",
        "move",
        "copy",
        "merge",
        "data",
        "item",
        "object",
        "value",
        "result",
        "info",
        "output",
        "input",
        "query",
        "request",
        "response",
        "action",
        "task",
        "job",
        "by",
        "for",
        "of",
        "to",
        "in",
        "on",
        "with",
        "from",
        "at",
        "as",
    }
)


def _tokenize_identifier(s: str) -> list[str]:
    """Split identifier on underscores and camelCase boundaries, lowercase."""
    # Insert boundary before uppercase letter preceded by lowercase (camelCase split)
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", s)
    return [tok.lower() for tok in s.split("_") if tok]


def _count_grounding_tokens(name: str) -> int:
    """Count tokens in a tool name that carry domain-specific semantic signal.

    A token is a grounding token when: length > 1 AND not in _GENERIC_TOKENS.
    """
    return sum(1 for t in _tokenize_identifier(name) if len(t) > 1 and t not in _GENERIC_TOKENS)


def is_low_grounding(tool: Tool) -> bool:
    """Return True when the tool name lacks domain-specific semantic signal.

    Conservative by design: false-abstain (missing upside) is acceptable;
    false-confident-generate (fabricating a wrong description) is the harm.
    Fires when _count_grounding_tokens == 0: all name tokens are either
    single characters (a, b, x) or generic verbs/nouns (get, set, put, etc.).

    Examples that return True: get_a, del_b, put_x, set_data
    Examples that return False: transform_scale, compute_median, search_products
    """
    return _count_grounding_tokens(tool.name) == 0


@dataclass
class FixCandidate:
    tool_name: str
    dim: str
    mode: ValidationMode
    baseline_score: float
    baseline_sigma: float
    candidate_score: float
    candidate_sigma: float
    delta: float
    threshold: float
    accepted: bool
    rejection_reason: str = ""
    new_description: str = ""
    new_schema_props: dict[str, Any] = field(default_factory=dict)
    new_required: list[str] = field(default_factory=list)


@dataclass
class FixReport:
    accepted: list[FixCandidate] = field(default_factory=list)
    rejected: list[FixCandidate] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    abstained: list[str] = field(default_factory=list)  # tool:dim:reason entries
    diff_text: str = ""
    patched_source: str = ""


# Mirrors scorer.py score_description_quality prompt — do not change independently of scorer.py
_DESC_JUDGE_PROMPT = (
    "Rate this MCP tool description on a scale of 0-10 for clarity and completeness "
    "for an AI agent. Reply with ONLY a number.\n\n"
    "Tool name: {name}\n"
    "Description: {description}\n"
    "Input schema: {schema}"
)

_DESC_GENERATOR_PROMPT = (
    "You are improving an MCP tool's description to help AI agents use it correctly.\n"
    "Write a clear, concise description (1-2 sentences) that:\n"
    "- States what the tool does\n"
    "- Names any key parameters and what they represent\n"
    "- Distinguishes this tool from similar tools if relevant\n\n"
    "Tool name: {name}\n"
    "Current description: {current}\n"
    "Input schema: {schema}\n\n"
    "Write ONLY the new description text. No quotes, no preamble, no markdown."
)

_DESC_GENERATOR_CATALOG_AWARE_PROMPT = (
    "You are improving an MCP tool's description to help AI agents use it correctly.\n"
    "Write a clear, concise description (1-2 sentences) that:\n"
    "- States what this tool does and names any key parameters\n"
    "- If this tool differs meaningfully from the neighbors listed below, state that difference\n\n"
    "CRITICAL — NO FABRICATION: If this tool is NOT meaningfully different from a neighbor "
    "based on the names, schemas, and descriptions shown here, say what it does plainly and "
    "DO NOT invent a distinction. Only state a difference directly supported by the "
    "names, schemas, or descriptions shown.\n\n"
    "Target tool:\n"
    "  Name: {name}\n"
    "  Current description: {current}\n"
    "  Input schema: {schema}\n\n"
    "Confusable neighbors from the same server catalog:\n"
    "{neighbors}\n\n"
    "Write ONLY the new description text. No quotes, no preamble, no markdown."
)

_DESC_GENERATOR_SOURCE_AWARE_PROMPT = (
    "You are improving an MCP tool's description to help AI agents use it correctly.\n"
    "Write a clear, concise description (1-2 sentences) that:\n"
    "- States what this tool does and names any key parameters\n"
    "- If this tool differs meaningfully from confusable neighbors, state that difference "
    "USING THE SOURCE CODE as evidence\n\n"
    "CRITICAL — NO FABRICATION: Only state a difference that is directly supported by "
    "the source code shown below. If the source does not support a distinction from "
    "similar tools, say what it does plainly and DO NOT invent a difference.\n\n"
    "Target tool:\n"
    "  Name: {name}\n"
    "  Current description: {current}\n"
    "  Input schema: {schema}\n\n"
    "Source code (read this to understand what the tool actually does):\n"
    "```python\n{source}\n```\n\n"
    "Write ONLY the new description text. No quotes, no preamble, no markdown."
)

_DESC_GENERATOR_SCOPED_SOURCE_PROMPT = (
    "You are improving an MCP tool's description to help AI agents use it correctly.\n"
    "Write a clear, concise description (1-2 sentences) that:\n"
    "- States what this tool does and names any key parameters\n"
    "- If this tool differs meaningfully from the confusable neighbors listed below, state that "
    "difference USING THE SOURCE CODE as evidence\n\n"
    "CRITICAL — NO FABRICATION: Only state a difference that is directly supported by the source "
    "code shown below. The source shown is ONLY this tool's own implementation — it does NOT "
    "contain other tools' code. Neighbors are shown as signature and docstring only (no bodies). "
    "If the source does not clearly support a distinction, say what it does plainly and DO NOT "
    "invent a difference.\n\n"
    "Target tool:\n"
    "  Name: {name}\n"
    "  Current description: {current}\n"
    "  Input schema: {schema}\n\n"
    "This tool's own source code (ONLY this tool's function — no other tools shown):\n"
    "```python\n{scoped_source}\n```\n\n"
    "Confusable neighbors (signature + docstring only — bodies not shown):\n"
    "{neighbor_surfaces}\n\n"
    "Write ONLY the new description text. No quotes, no preamble, no markdown."
)

_DESC_GENERATOR_GUARD_B_PROMPT = (
    "You are improving an MCP tool's description to help AI agents use it correctly.\n"
    "Write a clear, concise description (1-2 sentences) that:\n"
    "- States what this tool does based on its own source code\n"
    "- If this tool differs meaningfully from its neighbors, state that difference as a\n"
    "  POSITIVE FACT ABOUT THIS TOOL ONLY, grounded in this tool's own body\n\n"
    "CRITICAL — TARGET-GROUNDED PHRASING ONLY:\n"
    "You may only state distinctions as facts about THIS tool derived from its own source.\n"
    "You must NOT claim what any neighbor does — neighbor surfaces are shown only to indicate\n"
    "which axes (return type, storage, permanence, channel, etc.) may be worth mentioning.\n\n"
    "  GOOD (target-grounded):\n"
    '    "Returns a count of matching entries and writes results to a 5-minute TTL cache."\n'
    "  FORBIDDEN (comparative neighbor claim):\n"
    '    "Unlike lookup_data, which returns full entries, this tool returns a count."\n\n'
    "CRITICAL — NO FABRICATION: Only state a difference directly supported by this tool's own\n"
    "source code. If the source does not clearly support a distinction, say what it does plainly\n"
    "and DO NOT invent a difference.\n\n"
    "Target tool:\n"
    "  Name: {name}\n"
    "  Current description: {current}\n"
    "  Input schema: {schema}\n\n"
    "This tool's own source code (ONLY this tool's function — no other tools shown):\n"
    "```python\n{scoped_source}\n```\n\n"
    "Confusable neighbors (signature + docstring included — to indicate which axes may discriminate):\n"
    "{neighbor_surfaces}\n\n"
    "Write ONLY the new description text. No quotes, no preamble, no markdown."
)

_SCHEMA_GENERATOR_PROMPT = (
    "You are improving MCP tool parameter metadata for AI agent usability.\n"
    "For the tool below, generate improved parameter metadata AND identify required parameters.\n\n"
    "Tool name: {name}\n"
    "Current properties JSON: {properties}\n\n"
    "Reply with ONLY a valid JSON object with exactly these two keys:\n"
    '  "properties": an object mapping each parameter name to its improved metadata\n'
    '  "required": a list of parameter names that are required (have no default value)\n\n'
    'Each parameter in properties must have exactly these two fields: "type" and "description".\n'
    "Use standard JSON Schema types: string, integer, number, boolean, array, object.\n"
    "A parameter is required if it has no default value; optional if it has one.\n"
    "Example format:\n"
    '{{"properties": {{"x": {{"type": "number", "description": "First input value"}}, '
    '"y": {{"type": "number", "description": "Second input value"}}}}, '
    '"required": ["x", "y"]}}\n\n'
    "Reply with ONLY the JSON object, no markdown fences, no other text."
)

def _contains_comparative_neighbor_claim(desc: str, neighbor_names: list[str]) -> bool:
    """Return True if desc makes a comparative claim naming a specific neighbor.

    Checks for patterns like "unlike <neighbor>", "whereas <neighbor>", "while <neighbor>",
    or "compared to <neighbor>" (case-insensitive). Returns False when no neighbor names
    are provided or when comparative connectors appear but do not name a known neighbor.

    Used as a post-generation guard to detect Guard-B constraint violations before
    a description is committed.
    """
    if not neighbor_names:
        return False
    comparative_re = re.compile(
        r"\b(unlike|whereas|while|compared to)\s+",
        re.IGNORECASE,
    )
    for m in comparative_re.finditer(desc):
        after = desc[m.end():]
        for name in neighbor_names:
            if re.match(re.escape(name), after, re.IGNORECASE):
                return True
    return False


_NEIGHBOR_K: int = 6  # neighbors per tool; keeps prompt bounded at scale


def _select_neighbors(
    target: Tool,
    catalog: list[Tool],
    k: int = _NEIGHBOR_K,
) -> list[Tool]:
    """Select up to K lexically similar neighbors by name token Jaccard similarity.

    Uses only Tool.name — never any external family/label dict. Works on any
    unlabeled catalog. Ties broken alphabetically for determinism.
    """
    target_tokens = set(_tokenize_identifier(target.name))
    scored: list[tuple[float, str, Tool]] = []
    for tool in catalog:
        if tool.name == target.name:
            continue
        other_tokens = set(_tokenize_identifier(tool.name))
        union = target_tokens | other_tokens
        score = len(target_tokens & other_tokens) / len(union) if union else 0.0
        scored.append((-score, tool.name, tool))  # negate for descending sort
    scored.sort(key=lambda x: (x[0], x[1]))
    return [tool for _, _, tool in scored[:k]]


def _extract_scoped_function(
    source: str,
    tool_name: str,
    *,
    handler_prefix: str = "_handle_",
) -> str:
    """Return ONLY the function def + body for the target tool.

    Searches for `(async )?def {handler_prefix}{tool_name}(` and extracts
    that function through its last body line (stops at the next top-level
    def/async def or end of file). Returns empty string if not found.
    """
    pattern = re.compile(
        rf"^(async\s+)?def\s+{re.escape(handler_prefix)}{re.escape(tool_name)}\s*\(",
        re.MULTILINE,
    )
    m = pattern.search(source)
    if not m:
        return ""
    start = m.start()
    # Find the end: next top-level def/async def (same indent level = 0)
    end_pattern = re.compile(r"^(async\s+)?def\s+", re.MULTILINE)
    next_m = end_pattern.search(source, m.end())
    end = next_m.start() if next_m else len(source)
    return source[start:end].rstrip()


def _extract_function_surface(
    source: str,
    tool_name: str,
    *,
    handler_prefix: str = "_handle_",
) -> str:
    """Return only the def line + docstring for the target tool (body stripped).

    Extracts the full function via _extract_scoped_function, then keeps only:
    - the `def`/`async def` line
    - the first triple-quoted docstring if present immediately after the def
    Strips all body lines after the docstring (or after the def if no docstring).
    Returns empty string if the function is not found.
    """
    func_text = _extract_scoped_function(source, tool_name, handler_prefix=handler_prefix)
    if not func_text:
        return ""
    lines = func_text.splitlines()
    result: list[str] = []
    # Always include def line (and any continuation lines for multi-line signatures)
    i = 0
    while i < len(lines):
        result.append(lines[i])
        # Check if we've finished the def signature (ends with ':')
        stripped = lines[i].rstrip()
        if stripped.endswith(":"):
            i += 1
            break
        i += 1
    # Now check for a docstring: skip blank lines, then look for triple-quote
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and ('"""' in lines[i] or "'''" in lines[i]):
        quote = '"""' if '"""' in lines[i] else "'''"
        result.append(lines[i])
        # Multi-line docstring: keep until closing triple-quote
        if lines[i].count(quote) < 2:  # opening quote not also closed on same line
            i += 1
            while i < len(lines):
                result.append(lines[i])
                if quote in lines[i]:
                    break
                i += 1
    return "\n".join(result)


def assert_generator_ne_judge(generator_model: str, judge_model: str) -> None:
    """Raise ValueError if generator_model equals judge_model.

    Using the same model for both generation and judging creates shared blind spots —
    the judge is likely to rate its own outputs highly regardless of actual quality.
    Use a different model family for generation (e.g. qwen3 family vs llama3.1).
    """
    if generator_model == judge_model:
        raise ValueError(
            f"generator_model must differ from judge_model (both are '{generator_model}'). "
            "Using the same model for generation and judging creates shared blind spots — "
            "the judge is likely to rate its own outputs highly. "
            "Consider using a qwen3 family model as generator (e.g. 'qwen3:8b')."
        )


async def _judge_desc_trials(tool: Tool, provider: Provider, trials: int) -> list[float]:
    """Run the description quality judge for `trials` iterations.

    Mirrors scorer.py score_description_quality per-trial logic.
    Returns list of scores on 0-100 scale. Returns [] if no parseable responses.
    """
    scores: list[float] = []
    for trial_idx in range(trials):
        prompt = _DESC_JUDGE_PROMPT.format(
            name=tool.name,
            description=tool.description or "(none)",
            schema=tool.inputSchema,
        )
        resp = await provider.chat([Message(role="user", content=prompt)], seed=42 + trial_idx)
        match = re.search(r"\b(\d+(?:\.\d+)?)\b", resp)
        if match:
            raw_score = float(match.group(1))
            scores.append(min(raw_score, 10.0) * 10)  # 0-10 → 0-100
    return scores


async def _generate_description(
    tool: Tool,
    generator: Provider,
    *,
    neighbors: list[Tool] | None = None,
    source: str | None = None,
    scoped_source: str | None = None,
    neighbor_surfaces_text: str | None = None,
    guard_b: bool = False,
) -> str:
    """Generate an improved description for `tool` using the generator model.

    Priority (highest to lowest):
    - scoped_source (non-empty) + guard_b=True: uses _DESC_GENERATOR_GUARD_B_PROMPT; neighbor
      docstrings are kept in surfaces, comparative neighbor claims are forbidden.
    - scoped_source (non-empty): uses _DESC_GENERATOR_SCOPED_SOURCE_PROMPT; composes with
      neighbor_surfaces_text (breaks source-XOR-neighbors for this path only).
    - source (non-empty): uses _DESC_GENERATOR_SOURCE_AWARE_PROMPT with no-fabrication guard
    - neighbors (non-empty list): uses _DESC_GENERATOR_CATALOG_AWARE_PROMPT with no-fabrication guard
    - otherwise: uses _DESC_GENERATOR_PROMPT (per-tool, name+schema only)

    source and neighbors are mutually exclusive by convention — pass at most one.
    scoped_source can be combined with neighbor_surfaces_text.
    guard_b is only effective when scoped_source is non-empty; if scoped_source is absent,
    guard_b is ignored and the existing priority chain is followed.
    """
    if scoped_source and guard_b:
        prompt = _DESC_GENERATOR_GUARD_B_PROMPT.format(
            name=tool.name,
            current=tool.description or "(none)",
            schema=tool.inputSchema,
            scoped_source=scoped_source,
            neighbor_surfaces=neighbor_surfaces_text or "(none)",
        )
    elif scoped_source:
        prompt = _DESC_GENERATOR_SCOPED_SOURCE_PROMPT.format(
            name=tool.name,
            current=tool.description or "(none)",
            schema=tool.inputSchema,
            scoped_source=scoped_source,
            neighbor_surfaces=neighbor_surfaces_text or "(none)",
        )
    elif source:
        prompt = _DESC_GENERATOR_SOURCE_AWARE_PROMPT.format(
            name=tool.name,
            current=tool.description or "(none)",
            schema=tool.inputSchema,
            source=source,
        )
    elif neighbors:
        neighbor_lines = [
            f"  - {n.name}  schema: {n.inputSchema}  desc: {n.description or '(none)'}"
            for n in neighbors
        ]
        prompt = _DESC_GENERATOR_CATALOG_AWARE_PROMPT.format(
            name=tool.name,
            current=tool.description or "(none)",
            schema=tool.inputSchema,
            neighbors="\n".join(neighbor_lines),
        )
    else:
        prompt = _DESC_GENERATOR_PROMPT.format(
            name=tool.name,
            current=tool.description or "(none)",
            schema=tool.inputSchema,
        )
    resp = await generator.chat([Message(role="user", content=prompt)], seed=42)
    return resp.strip()


async def _generate_schema_props(
    tool: Tool, generator: Provider
) -> tuple[dict[str, Any], list[str]]:
    """Generate improved parameter metadata and required list for tool.

    Returns (props, required) where props maps param names to {type, description} dicts
    and required is a list of parameter names with no default value.
    Supports both new format {"properties": {...}, "required": [...]} and old flat format.
    Returns ({}, []) if the response cannot be parsed as valid JSON.
    """
    schema = tool.inputSchema or {}
    properties = schema.get("properties", {})
    prompt = _SCHEMA_GENERATOR_PROMPT.format(
        name=tool.name,
        properties=json.dumps(properties),
    )
    resp = await generator.chat([Message(role="user", content=prompt)], seed=42)
    result, failed = extract_json_object(resp)
    if failed:
        return {}, []
    if "properties" in result:
        props = result.get("properties", {})
        required = result.get("required", [])
        if isinstance(props, dict) and isinstance(required, list):
            return props, [str(r) for r in required if isinstance(r, str)]
    # Fallback: old flat format, no required
    return result, []


def _patch_source_description(source: str, tool_name: str, new_desc: str) -> str:
    """Replace the description field for tool_name in source code.

    Finds the tool block by locating name="<tool_name>", then replaces the next
    description= line encountered. Returns source unchanged if no match is found.
    """
    lines = source.splitlines(keepends=True)
    result_lines: list[str] = []
    found_tool = False
    replaced = False

    for line in lines:
        if not found_tool and f'name="{tool_name}"' in line:
            found_tool = True
            result_lines.append(line)
        elif found_tool and not replaced and "description=" in line:
            patched = re.sub(
                r'description="[^"]*"',
                f'description="{new_desc}"',
                line,
                count=1,
            )
            result_lines.append(patched)
            replaced = True
            found_tool = False
        else:
            result_lines.append(line)

    return "".join(result_lines)


def _apply_overmarking_guard(
    derived_required: list[str],
    existing_props: dict[str, Any],
    new_props: dict[str, Any],
) -> list[str]:
    """Remove params from required if they have a default in existing or generated props.

    A param with a default is optional by definition; marking it required is a schema
    error even if it would raise the heuristic score.
    """
    return [
        param
        for param in derived_required
        if existing_props.get(param, {}).get("default") is None
        and new_props.get(param, {}).get("default") is None
    ]


def deep_merge(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge incoming over existing; recurse into nested dicts; preserve keys absent from incoming."""
    result = dict(existing)
    for key, val in incoming.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _patch_source_schema_props(source: str, tool_name: str, new_props: dict[str, Any]) -> str:
    """Replace empty property dicts ({}) for given param names in the tool's source block.

    Locates the block starting at name="<tool_name>" and ending at the next types.Tool(
    occurrence (or end of source). Within that block, replaces `"<param>": {}` with
    the improved metadata JSON for each param in new_props.
    """
    # Find start of this tool's block
    name_pattern = f'name="{tool_name}"'
    start_idx = source.find(name_pattern)
    if start_idx == -1:
        return source

    # Find end of block: next types.Tool( occurrence after start, or end of source
    next_tool_match = re.search(r"types\.Tool\s*\(", source[start_idx + len(name_pattern) :])
    if next_tool_match:
        end_idx = start_idx + len(name_pattern) + next_tool_match.start()
    else:
        end_idx = len(source)

    block = source[start_idx:end_idx]

    for prop_name, prop_meta in new_props.items():
        escaped_name = re.escape(prop_name)
        replacement_value = json.dumps(prop_meta)
        block = re.sub(
            rf'"{escaped_name}":\s*\{{}}',
            f'"{prop_name}": {replacement_value}',
            block,
        )

    return source[:start_idx] + block + source[end_idx:]


def _patch_source_required(source: str, tool_name: str, required: list[str]) -> str:
    """Add or replace the "required" array in tool_name's inputSchema block in source.

    Locates the tool block, finds the "properties": {...} sub-dict, and inserts
    "required": [...] immediately after the properties closing brace.
    If "required" already exists in the block, replaces it in-place.
    """
    if not required:
        return source

    name_pattern = f'name="{tool_name}"'
    start_idx = source.find(name_pattern)
    if start_idx == -1:
        return source

    next_tool_match = re.search(r"types\.Tool\s*\(", source[start_idx + len(name_pattern) :])
    end_idx = (
        start_idx + len(name_pattern) + next_tool_match.start() if next_tool_match else len(source)
    )

    block = source[start_idx:end_idx]
    required_json = json.dumps(required)

    # Replace existing "required": [...] if present
    existing_m = re.search(r'"required"\s*:\s*\[[^\]]*\]', block)
    if existing_m:
        block = (
            block[: existing_m.start()] + f'"required": {required_json}' + block[existing_m.end() :]
        )
        return source[:start_idx] + block + source[end_idx:]

    # Find "properties": { ... } and insert "required" after its closing brace
    props_m = re.search(r'"properties"\s*:\s*\{', block)
    if not props_m:
        return source

    brace_start = block.index("{", props_m.start())
    depth, close_pos = 0, -1
    for i, ch in enumerate(block[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                close_pos = i
                break
    if close_pos == -1:
        return source

    # Skip the comma that follows the closing brace
    after = close_pos + 1
    if after < len(block) and block[after] == ",":
        after += 1

    # Detect indentation of the "properties" line to match alignment
    line_start = block.rfind("\n", 0, props_m.start()) + 1
    indent = ""
    for ch in block[line_start:]:
        if ch in (" ", "\t"):
            indent += ch
        else:
            break

    insert = f'\n{indent}"required": {required_json},'
    block = block[:after] + insert + block[after:]
    return source[:start_idx] + block + source[end_idx:]


async def run_fixer(
    tools: list[Tool],
    generator: Provider,
    judge: Provider,
    source_path: Path,
    dims: list[str],
    *,
    trials: int = DEFAULT_TRIALS,
    min_delta: float = DEFAULT_MIN_DELTA,
    skip_above_band: float = DEFAULT_SKIP_ABOVE_BAND,
    catalog_aware: bool = False,
    neighbor_k: int = _NEIGHBOR_K,
) -> FixReport:
    """Run the auto-fix loop for the given tools and scoring dimensions.

    For each (tool, dim) pair:
    - Baseline score is measured (heuristic for DETERMINISTIC, judge trials for JUDGE_BASED).
    - A candidate fix is generated using the generator provider.
    - The candidate is scored using the same method as the baseline.
    - The fix is accepted only if delta > threshold (strict greater-than).
      For JUDGE_BASED, threshold = max(sigma_of_baseline, min_delta).
    - Tools whose baseline score is already >= skip_above_band are skipped before generation
      (reported as skipped with reason "already_above_band"; no generator call is made).

    After all decisions, accepted fixes are applied to the source file and a unified diff
    is generated.
    """
    report = FixReport()

    for tool in tools:
        for dim in dims:
            if dim not in VALIDATION_MODE:
                report.skipped.append(f"{tool.name}:{dim}")
                continue

            mode = VALIDATION_MODE[dim]

            # ── Abstain check (description_quality only) ──────────────────────
            if dim == "description_quality" and is_low_grounding(tool):
                report.abstained.append(f"{tool.name}:{dim}:low_grounding")
                continue  # Original description unchanged; no LLM calls made.

            # ── Baseline scoring ──────────────────────────────────────────────
            if mode == ValidationMode.DETERMINISTIC:
                baseline_score = score_schema_completeness([tool]).score
                baseline_scores: list[float] = [baseline_score]
                baseline_sigma = 0.0
            else:
                baseline_scores = await _judge_desc_trials(tool, judge, trials)
                if not baseline_scores:
                    report.skipped.append(f"{tool.name}:{dim}:no_baseline_scores")
                    continue
                baseline_score = statistics.mean(baseline_scores)
                baseline_sigma = (
                    statistics.stdev(baseline_scores) if len(baseline_scores) >= 2 else 0.0
                )

            # ── Cost pre-filter ──────────────────────────────────────────────
            if baseline_score >= skip_above_band:
                report.skipped.append(f"{tool.name}:{dim}:already_above_band")
                continue

            # ── Generate candidate ────────────────────────────────────────────
            merged_required: list[str] = []
            if dim == "description_quality":
                nbrs = _select_neighbors(tool, tools, k=neighbor_k) if catalog_aware else None
                new_desc = await _generate_description(tool, generator, neighbors=nbrs)
                candidate_tool = Tool(
                    name=tool.name,
                    description=new_desc,
                    inputSchema=tool.inputSchema,
                )
                new_props: dict[str, Any] = {}
            else:  # schema_completeness
                new_props, derived_required = await _generate_schema_props(tool, generator)
                # Merge new_props into a copy of existing properties
                existing_schema = dict(tool.inputSchema or {})
                existing_props: dict[str, Any] = dict(existing_schema.get("properties", {}))
                merged_props: dict[str, Any] = {}
                for param, schema in existing_props.items():
                    merged_props[param] = (
                        deep_merge(schema, new_props[param]) if param in new_props else schema
                    )
                for param, schema in new_props.items():
                    if param not in existing_props:
                        merged_props[param] = schema
                # Over-marking guard: strip params with defaults before adding to required
                guarded_required = _apply_overmarking_guard(
                    derived_required, existing_props, new_props
                )
                # Merge with any pre-existing required array
                existing_required = list(existing_schema.get("required", []))
                merged_required = sorted(set(existing_required) | set(guarded_required))
                merged_schema: dict[str, Any] = {**existing_schema, "properties": merged_props}
                if merged_required:
                    merged_schema["required"] = merged_required
                candidate_tool = Tool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=merged_schema,
                )
                new_desc = ""

            # ── Candidate scoring ─────────────────────────────────────────────
            if mode == ValidationMode.DETERMINISTIC:
                candidate_score_val = score_schema_completeness([candidate_tool]).score
                candidate_scores: list[float] = [candidate_score_val]
                candidate_sigma = 0.0
            else:
                candidate_scores = await _judge_desc_trials(candidate_tool, judge, trials)
                if not candidate_scores:
                    report.skipped.append(f"{tool.name}:{dim}:no_candidate_scores")
                    continue
                candidate_score_val = statistics.mean(candidate_scores)
                candidate_sigma = (
                    statistics.stdev(candidate_scores) if len(candidate_scores) >= 2 else 0.0
                )

            # ── Accept/reject decision ────────────────────────────────────────
            baseline_mean = statistics.mean(baseline_scores)
            candidate_mean = statistics.mean(candidate_scores)
            delta = candidate_mean - baseline_mean

            if mode == ValidationMode.DETERMINISTIC:
                threshold = min_delta
            else:
                threshold = max(baseline_sigma, min_delta)

            accepted = delta > threshold
            rejection_reason = ""
            if not accepted:
                if delta <= 0:
                    rejection_reason = f"no improvement (delta={delta:+.1f})"
                elif delta <= threshold:
                    rejection_reason = (
                        f"delta={delta:+.1f} does not exceed threshold={threshold:.1f} "
                        f"(sigma={baseline_sigma:.1f}, min_delta={min_delta:.1f})"
                    )

            candidate = FixCandidate(
                tool_name=tool.name,
                dim=dim,
                mode=mode,
                baseline_score=baseline_mean,
                baseline_sigma=baseline_sigma,
                candidate_score=candidate_mean,
                candidate_sigma=candidate_sigma,
                delta=delta,
                threshold=threshold,
                accepted=accepted,
                rejection_reason=rejection_reason,
                new_description=new_desc,
                new_schema_props=new_props,
                new_required=merged_required,
            )

            if accepted:
                report.accepted.append(candidate)
            else:
                report.rejected.append(candidate)

    # ── Apply accepted fixes to source ────────────────────────────────────────
    source = source_path.read_text(encoding="utf-8")
    patched = source

    for candidate in report.accepted:
        if candidate.dim == "description_quality" and candidate.new_description:
            patched = _patch_source_description(
                patched, candidate.tool_name, candidate.new_description
            )
        elif candidate.dim == "schema_completeness" and candidate.new_schema_props:
            patched = _patch_source_schema_props(
                patched, candidate.tool_name, candidate.new_schema_props
            )
            if candidate.new_required:
                patched = _patch_source_required(
                    patched, candidate.tool_name, candidate.new_required
                )

    if report.accepted:
        diff_lines = list(
            difflib.unified_diff(
                source.splitlines(keepends=True),
                patched.splitlines(keepends=True),
                fromfile=str(source_path),
                tofile=str(source_path) + " (auto-fixed)",
            )
        )
        report.diff_text = "".join(diff_lines)
        report.patched_source = patched

    return report
