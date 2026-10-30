"""Zero-LLM provider schema-compatibility lint: Gemini / Vertex AI function calling.

Opt-in (`agentgauge lint --provider-compat`; the unsupported-attribute summary additionally
needs `--provider-compat-attributes`). Deterministic: no network, no model.

Scope is deliberately narrow. Every WARNING-tier check below mirrors a limit stated in the
official provider docs (URLs in the constants); the catalog-level size note is an INFO-tier
advisory because the docs publish NO numeric threshold for it.

Documented sources (fetched 2026-10-29):
  Vertex AI function calling -- _VERTEX_DOC_URL
    "Function names should start with a letter or an underscore and contain only characters
     a-z, A-Z, 0-9, underscores, dots or dashes with a maximum length of 64."
    "ref must refer to direct child of defs; no external references."
    "The maximum depth of nested schema is 32."
    "ideally keeping the active set to a maximum of 10-20."
  Gemini API function calling -- _GEMINI_DOC_URL
    "Only a subset of the OpenAPI schema is supported."
    "For any mode, the API may reject very large or deeply nested schemas."

Evidence basis for the size advisory (private study, 2026-10-29, n=5 rejections, NOT a
published limit): Vertex Gemini 2.5 Flash/Pro with function-calling mode ANY rejected 5 of 24
real MCP server catalogs with HTTP 400. Bisection found no single forbidden keyword (a rejected
tool became accepted after removing ANY ONE of several unrelated constraints), consistent with
an aggregate size/complexity limit. Stripping `_VALIDATION_ONLY_KEYWORDS` and dereferencing
local `$ref` made all 24 accepted. This is a heuristic signal, not a guarantee in either
direction.

Array length limits (`provider_compat_array_length`, INFO, added POST-HOC 2026-10-30 after the
5 rejections were seen): the Gemini API structured-output page says "Common causes are large
maxItems limits (especially on nested arrays)" and the Vertex structured-output page lists "long
array length limits" -- both for response schemas, neither with a number. Presence-only; no
threshold is encoded. CAVEATS on that check, kept here because they bound what it can claim:
`maxItems` was picked from the documented contributors BECAUSE the bisection had already
implicated it, so its in-sample precision (5 of 7 firings on the 24 labelled catalogs) is
selection-biased by construction; and the check adds no coverage beyond
`provider_compat_schema_size` (the aggregate `any_finding` predicate is unchanged by it).

Unsupported attributes (`provider_compat_unsupported_attribute`, INFO, added POST-HOC
2026-10-30): the Vertex function-calling page lists the supported schema attributes as "type,
nullable, required, format, description, properties, items, enum, anyOf, $ref, and $defs.
Remaining attributes are not supported." The Gemini API function-calling page has no such
list (only "Only a subset of the OpenAPI schema is supported."). The check reports which
schema keywords outside the Vertex list a catalog uses; it does not claim rejection (an
unsupported attribute may be ignored) and encodes no threshold. It fired on 71% of real
catalogs (5/20 precision), so it is OFF by default even under `--provider-compat`, needs
`--provider-compat-attributes`, and emits ONE summary line per catalog (occurrence count plus
the top 3 keywords) instead of one finding per attribute.

None of these findings is scoring: ADVISORY/INFO never set `LintReport.flagged`, and the checks
only run when the caller opts in, so default lint output and published numbers are unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from agentgauge.linter import Severity, Violation

_VERTEX_DOC_URL = (
    "https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling"
)
_GEMINI_DOC_URL = "https://ai.google.dev/gemini-api/docs/function-calling"
# Structured-output pages (fetched 2026-10-30). The Vertex URL redirects to
# .../gemini-enterprise-agent-platform/models/capabilities/control-generated-output.
_GEMINI_STRUCTURED_OUTPUT_DOC_URL = "https://ai.google.dev/gemini-api/docs/structured-output"
_VERTEX_STRUCTURED_OUTPUT_DOC_URL = (
    "https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output"
)
# Verbatim, from the two pages above. Neither gives a number for "large" / "long".
_ARRAY_LIMIT_QUOTES = (
    'Gemini API: "Common causes are large maxItems limits (especially on nested arrays)"; '
    'Vertex: "Complexity might come from long property names, long array length limits, '
    "enums with many values, objects with lots of optional properties, or a combination of "
    'these factors."'
)

# Vertex function-calling page, verbatim (fetched 2026-10-30), preceded there by "We support the
# following attributes:". The Gemini API function-calling page has no equivalent list.
_SUPPORTED_ATTRIBUTES_QUOTE = (
    '"We support the following attributes: type, nullable, required, format, description, '
    'properties, items, enum, anyOf, $ref, and $defs. Remaining attributes are not supported."'
)
DOCUMENTED_SUPPORTED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "type",
        "nullable",
        "required",
        "format",
        "description",
        "properties",
        "items",
        "enum",
        "anyOf",
        "$ref",
        "$defs",
    }
)

# Vertex docs: "maximum length of 64"; "maximum depth of nested schema is 32"; "10-20" tools.
MAX_FUNCTION_NAME_LEN = 64
MAX_SCHEMA_DEPTH = 32
RECOMMENDED_MAX_TOOLS = 20

# Documented character set: start with letter/underscore; then a-z A-Z 0-9 _ . -
_FUNCTION_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")

# Keywords that, when stripped, made all 24 catalogs in our private study accepted. Note the
# Vertex docs list `format` as a SUPPORTED attribute; it is kept here only because it was part
# of the stripped set we tested, so the advisory cannot attribute the effect to it separately.
_VALIDATION_ONLY_KEYWORDS: tuple[str, ...] = (
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minProperties",
    "maxProperties",
    "pattern",
    "format",
    "examples",
    "$schema",
)

# Schema keys whose value is a mapping of name -> subschema.
_MAPPING_KEYS = ("properties", "$defs", "definitions", "patternProperties")
# Schema keys whose value is a single subschema.
_SINGLE_KEYS = ("additionalProperties", "not", "if", "then", "else", "contains")
# Schema keys whose value is a list of subschemas (or, for `items`, a subschema or list).
_LIST_KEYS = ("anyOf", "oneOf", "allOf", "prefixItems")

_CATALOG = "<catalog>"


def _children(schema: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield direct subschemas of one schema node (never descends into enum/const/default)."""
    for key in _MAPPING_KEYS:
        value = schema.get(key)
        if isinstance(value, dict):
            yield from (v for v in value.values() if isinstance(v, dict))
    for key in _SINGLE_KEYS:
        value = schema.get(key)
        if isinstance(value, dict):
            yield value
    for key in _LIST_KEYS:
        value = schema.get(key)
        if isinstance(value, list):
            yield from (v for v in value if isinstance(v, dict))
    items = schema.get("items")
    if isinstance(items, dict):
        yield items
    elif isinstance(items, list):
        yield from (v for v in items if isinstance(v, dict))


def schema_depth(schema: dict[str, Any]) -> int:
    """Nesting depth of subschemas; a schema with no subschemas has depth 1.

    The Vertex docs state "The maximum depth of nested schema is 32" without defining how the
    root is counted; this counts the root as level 1, which is our reading, not a documented
    definition. Local `$ref` are not dereferenced. Iterative so hostile depth cannot overflow
    the Python stack.
    """
    best = 0
    stack: list[tuple[dict[str, Any], int]] = [(schema, 1)]
    while stack:
        node, depth = stack.pop()
        best = max(best, depth)
        stack.extend((child, depth + 1) for child in _children(node))
    return best


def _walk(schema: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every schema node (root included) exactly once."""
    stack = [schema]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(_children(node))


def _is_direct_defs_child(ref: str) -> bool:
    """True for `#/$defs/<name>` or `#/definitions/<name>` with exactly one name segment."""
    for prefix in ("#/$defs/", "#/definitions/"):
        if ref.startswith(prefix):
            name = ref[len(prefix) :]
            return bool(name) and "/" not in name
    return False


def check_function_name(name: str) -> list[Violation]:
    """Function-name character set and 64-char limit (Vertex docs)."""
    problems = []
    if len(name) > MAX_FUNCTION_NAME_LEN:
        problems.append(
            f"is {len(name)} characters (documented maximum is {MAX_FUNCTION_NAME_LEN})"
        )
    if not _FUNCTION_NAME_RE.fullmatch(name):
        problems.append(
            "does not match the documented character set (must start with a letter or "
            "underscore, then only a-z, A-Z, 0-9, underscores, dots or dashes)"
        )
    if not problems:
        return []
    return [
        Violation(
            check="provider_compat_tool_name",
            severity=Severity.ADVISORY,
            tool_name=name,
            detail=(
                f"Gemini/Vertex function calling: tool name {'; and '.join(problems)}. "
                f"Rename the tool or expose an alias for Gemini clients. See {_VERTEX_DOC_URL}"
            ),
        )
    ]


def check_schema_depth(name: str, schema: dict[str, Any]) -> list[Violation]:
    """Nested-schema depth > 32 (Vertex docs)."""
    depth = schema_depth(schema or {})
    if depth <= MAX_SCHEMA_DEPTH:
        return []
    return [
        Violation(
            check="provider_compat_schema_depth",
            severity=Severity.ADVISORY,
            tool_name=name,
            detail=(
                f"Gemini/Vertex function calling: input schema nests {depth} levels deep "
                f"(documented maximum is {MAX_SCHEMA_DEPTH}). Flatten the schema or inline "
                f"deep sub-objects. See {_VERTEX_DOC_URL}"
            ),
        )
    ]


def check_refs(name: str, schema: dict[str, Any]) -> list[Violation]:
    """`$ref` that is external or not a direct child of `$defs`/`definitions`.

    Vertex documents `ref`/`defs` written WITHOUT the `$` ("ref must refer to direct child of
    defs; no external references"), and its attribute list names `$ref`/`$defs`, so the docs
    do not settle whether `$ref` itself is accepted. This therefore says "may need rewriting"
    and never claims rejection. In our private study a local `$ref` to `#/properties/...` was
    observed rejected.
    """
    bad = sorted(
        {
            ref
            for node in _walk(schema or {})
            if isinstance(ref := node.get("$ref"), str) and not _is_direct_defs_child(ref)
        }
    )
    return [
        Violation(
            check="provider_compat_ref",
            severity=Severity.ADVISORY,
            tool_name=name,
            detail=(
                f"Gemini/Vertex function calling: $ref {ref!r} is external or not a direct "
                'child of $defs/definitions, so it may need rewriting (docs: "ref must refer '
                'to direct child of defs; no external references"). Inline the referenced '
                f"schema. See {_VERTEX_DOC_URL}"
            ),
        )
        for ref in bad
    ]


def measure_catalog(tools: list[Any]) -> tuple[int, dict[str, int]]:
    """Deterministic size figure: (total properties, per-keyword validation-only counts).

    Counts schema keywords structurally, so a property that is merely NAMED `pattern` or
    `format` is not miscounted as the keyword.
    """
    n_properties = 0
    counts: dict[str, int] = {}
    for tool in tools:
        for node in _walk(tool.inputSchema or {}):
            props = node.get("properties")
            if isinstance(props, dict):
                n_properties += len(props)
            for kw in _VALIDATION_ONLY_KEYWORDS:
                if kw in node:
                    counts[kw] = counts.get(kw, 0) + 1
    return n_properties, dict(sorted(counts.items()))


def check_catalog_size(tools: list[Any]) -> list[Violation]:
    """INFO advisory: validation-only keywords present across the catalog.

    No numeric trigger and no pass/fail claim: the Gemini docs say only that "For any mode, the
    API may reject very large or deeply nested schemas" and publish no threshold. The note
    appears whenever at least one validation-only keyword is present, with the measured figures.
    """
    n_properties, counts = measure_catalog(tools)
    if not counts:
        return []
    total = sum(counts.values())
    listed = ", ".join(f"{k}={v}" for k, v in counts.items())
    return [
        Violation(
            check="provider_compat_schema_size",
            severity=Severity.INFO,
            tool_name=_CATALOG,
            detail=(
                f"Gemini/Vertex function calling: this catalog has {n_properties} properties and "
                f"{total} validation-only keywords ({listed}). The Gemini docs say that for "
                f"any mode the API may reject very large or deeply nested schemas; no "
                f"threshold is published, and this note makes no claim that this catalog "
                f"will be rejected. If a request is rejected with HTTP 400 'invalid "
                f"argument', then in our observation (5 of 24 real catalogs, private study) "
                f"stripping these keywords ({', '.join(_VALIDATION_ONLY_KEYWORDS)}) or moving "
                f"them into descriptions, and inlining $ref, resolved it. "
                f"See {_GEMINI_DOC_URL} and {_VERTEX_DOC_URL}"
            ),
        )
    ]


def measure_array_limits(tools: list[Any]) -> tuple[int, int, int | None]:
    """(arrays declaring `maxItems`, how many sit inside another array, largest limit seen).

    Counts schema nodes carrying a numeric `maxItems` structurally (a property merely NAMED
    `maxItems` is not counted). "Inside another array" means some ancestor subschema is an
    array (`type: array` or has `items`). Iterative, so hostile depth cannot overflow the stack.
    """
    n_limited = n_nested = 0
    largest: int | None = None
    for tool in tools:
        stack: list[tuple[dict[str, Any], bool]] = [(tool.inputSchema or {}, False)]
        while stack:
            node, inside_array = stack.pop()
            limit = node.get("maxItems")
            if isinstance(limit, int | float) and not isinstance(limit, bool):
                n_limited += 1
                n_nested += inside_array
                largest = int(limit) if largest is None else max(largest, int(limit))
            is_array = node.get("type") == "array" or "items" in node
            stack.extend((child, inside_array or is_array) for child in _children(node))
    return n_limited, n_nested, largest


def check_array_length_limits(tools: list[Any]) -> list[Violation]:
    """INFO advisory: array length limits (`maxItems`), a documented complexity contributor.

    Two official pages name array length limits as a cause of an INVALID_ARGUMENT rejection of
    a complex schema (quotes in `_ARRAY_LIMIT_QUOTES`). Both describe structured-output response
    schemas, not function declarations, and neither publishes a numeric threshold, so this
    fires on PRESENCE only, never on a size, and makes no claim that a request will be
    rejected.

    Selection caveat: `maxItems` was chosen from the documented contributors because a
    bisection had already implicated it, so its in-sample precision is selection-biased. It
    also adds no coverage beyond `provider_compat_schema_size` (`any_finding` is unchanged).
    """
    n_limited, n_nested, largest = measure_array_limits(tools)
    if not n_limited:
        return []
    return [
        Violation(
            check="provider_compat_array_length",
            severity=Severity.INFO,
            tool_name=_CATALOG,
            detail=(
                f"Gemini/Vertex function calling: {n_limited} array(s) declare maxItems "
                f"({n_nested} inside another array; largest limit {largest}). Google's docs "
                f"name array length limits among the common causes of an INVALID_ARGUMENT "
                f"rejection of a complex schema: {_ARRAY_LIMIT_QUOTES} Those pages describe "
                f"structured-output response schemas, not function declarations, and publish "
                f"no numeric threshold, so this note makes no claim that this catalog will be "
                f"rejected. If a request is rejected, lowering or removing array limits is "
                f"the documented first step. See {_GEMINI_STRUCTURED_OUTPUT_DOC_URL} and "
                f"{_VERTEX_STRUCTURED_OUTPUT_DOC_URL}"
            ),
        )
    ]


def measure_unsupported_attributes(tools: list[Any]) -> dict[str, int]:
    """Count, per keyword, schema nodes carrying a keyword outside the documented list.

    Looks at the KEYS OF SCHEMA NODES only. A property NAME is a key of a `properties` mapping
    (never of a schema node), so a property literally called `maxItems` is not counted. Walks
    every subschema reachable through `properties`, `items`, `anyOf`/`oneOf`/`allOf`, `$defs`
    and the other containers in `_children`, iteratively. Subschemas held under keywords
    `_children` does not descend (e.g. `dependentSchemas`) are not scanned, but those container
    keywords are themselves reported as unsupported.
    """
    counts: dict[str, int] = {}
    for tool in tools:
        for node in _walk(tool.inputSchema or {}):
            for key in node:
                if key not in DOCUMENTED_SUPPORTED_ATTRIBUTES:
                    counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


TOP_UNSUPPORTED_SHOWN = 3
_MAX_KEYWORD_DISPLAY_LEN = 40


def _safe_keyword(keyword: str) -> str:
    """Render an UNTRUSTED schema key for a message that the text printer feeds to Rich markup.

    Schema keys are attacker-controlled, and `agentgauge lint` prints `Violation.detail` inside
    Rich markup, where `[bold]x` or `[/]` would be interpreted. Square brackets are replaced and
    the key is truncated and passed through `ascii()` so control characters stay inert.
    """
    shown = ascii(keyword[:_MAX_KEYWORD_DISPLAY_LEN])[1:-1]
    shown = shown.replace("[", "(").replace("]", ")")
    return shown + ("..." if len(keyword) > _MAX_KEYWORD_DISPLAY_LEN else "")


def check_unsupported_attributes(tools: list[Any]) -> list[Violation]:
    """INFO advisory: ONE summary line per catalog for schema keywords outside the Vertex list.

    The Vertex docs state the list (`_SUPPORTED_ATTRIBUTES_QUOTE`) and that the remaining
    attributes are not supported. They do not say what happens to one (ignored vs rejected), and
    in our private study catalogs using several of them were accepted, so this makes no claim
    that a request will be rejected and encodes no threshold. It was measured to fire on 71% of
    real catalogs with 5/20 precision, so it is OFF unless the caller opts in
    (`lint_provider_compat(..., include_attributes=True)`), and it reports one line: the number
    of out-of-list keyword occurrences (schema nodes) and the top `TOP_UNSUPPORTED_SHOWN`
    keywords by count, ties broken alphabetically (deterministic). No out-of-list keyword, no
    line.
    """
    counts = measure_unsupported_attributes(tools)
    if not counts:
        return []
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_UNSUPPORTED_SHOWN]
    listed = ", ".join(f"{_safe_keyword(k)}={v}" for k, v in ranked)
    return [
        Violation(
            check="provider_compat_unsupported_attribute",
            severity=Severity.INFO,
            tool_name=_CATALOG,
            detail=(
                f"Gemini/Vertex function calling: this catalog has {total} schema keyword "
                f"occurrence(s) outside the list the Vertex docs give as supported, across "
                f"{len(counts)} distinct keyword(s); most common: {listed}. "
                f"Vertex docs: {_SUPPORTED_ATTRIBUTES_QUOTE} This note makes no claim that a "
                f"request will be rejected: unsupported attributes may be ignored rather than "
                f"rejected, and no threshold is encoded. The Gemini API function-calling page "
                f'gives no attribute list, only "Only a subset of the OpenAPI schema is '
                f'supported." See {_VERTEX_DOC_URL} and {_GEMINI_DOC_URL}'
            ),
        )
    ]


def check_tool_count(tools: list[Any]) -> list[Violation]:
    """INFO advisory: more than 20 tools (Vertex docs recommend an active set of 10-20)."""
    if len(tools) <= RECOMMENDED_MAX_TOOLS:
        return []
    return [
        Violation(
            check="provider_compat_tool_count",
            severity=Severity.INFO,
            tool_name=_CATALOG,
            detail=(
                f"Gemini/Vertex function calling: {len(tools)} tools exposed; the docs "
                'recommend "ideally keeping the active set to a maximum of 10-20". Select '
                f"a relevant subset per request. See {_VERTEX_DOC_URL}"
            ),
        )
    ]


def lint_provider_compat(tools: list[Any], *, include_attributes: bool = False) -> list[Violation]:
    """Run the provider-compat checks over a tool set. `tools` match `mcp.types.Tool`.

    `include_attributes` additionally runs `check_unsupported_attributes` (one summary line);
    it is False by default because that check is noisy (see its docstring).

    Pure function: no I/O, no LLM. Order is deterministic (tool order, then check order).
    """
    violations: list[Violation] = []
    for tool in tools:
        schema = tool.inputSchema or {}
        violations += check_function_name(tool.name)
        violations += check_schema_depth(tool.name, schema)
        violations += check_refs(tool.name, schema)
    violations += check_catalog_size(tools)
    violations += check_array_length_limits(tools)
    if include_attributes:
        violations += check_unsupported_attributes(tools)
    violations += check_tool_count(tools)
    return violations
