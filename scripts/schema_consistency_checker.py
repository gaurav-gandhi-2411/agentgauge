#!/usr/bin/env python3
"""Schema-consistency checker: does a tool's description contradict its own JSON schema?

Motivated by a concrete finding in this session's Phase-3 mechanism test: reading
`call_constraints_server_fixed`'s actual fixtures showed run_fixer had introduced
`required` entries (`"required": ["host"]`) referencing properties that don't
exist in `properties` at all (still `{}`), while the tool's rewritten
description explicitly says "with no required parameters" -- a description that
was TRUE of the "before" arm (`required: []`) and is now false of the "after"
arm, entirely because of what the fixer added to the schema, not the
description text itself changing meaning.

Checks implemented, each independently toggleable so precision/recall can be
measured per-check (per the task brief's explicit request to keep (d) separate
from the deterministic (a)-(c)):

  (a) described_not_in_schema: identifier-like tokens in the top-level tool
      description that don't match any actual schema property name. Heuristic,
      not exact -- natural-language synonyms for a real property will false-positive
      here (e.g. "session" for schema property "sid"). Flagged as approximate in
      the docstring, not claimed as precise.
  (b) required_not_mentioned: schema `required` property names that never appear
      (case-insensitive substring) anywhere in the top-level description.
  (c) type_enum_contradiction: description states boolean-ish language
      ("true or false", "yes/no") for a property whose schema type isn't boolean,
      or lists specific option-like words that don't intersect the schema's own
      `enum` list for that property (only checked when the schema declares an
      enum -- no enum means nothing to contradict).
  (e) required_references_missing_property: a schema-internal-consistency check
      (not description-vs-schema) -- a name in `required` that isn't a key in
      `properties` at all. Fully deterministic, no heuristic judgment. Added
      after finding this exact defect in call_constraints_server_fixed's schema.
  (d) semantic_contradiction: LLM-judged (llama3.1:8b, the pinned judge model) --
      does a PARAMETER-level description's stated meaning plausibly match what
      the parameter's name/type/constraints in the schema suggest it represents?
      Kept structurally separate (own function, own result field, run only when
      requested) so its precision can be assessed independently of (a)-(c)/(e),
      which need no LLM call at all.

DO NOT RUN check_d_semantic_llm in CI or without checking GPU/Ollama availability
first -- it makes live inference calls, unlike every other check in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_BOOLEAN_WORDS = {"true", "false", "yes", "no", "boolean", "bool"}
_IDENTIFIER_RE = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*)`|\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")


@dataclass
class ToolSchemaCheck:
    """Result of running the deterministic checks (a), (b), (c), (e) on one tool."""

    tool_name: str
    described_not_in_schema: list[str] = field(default_factory=list)
    required_not_mentioned: list[str] = field(default_factory=list)
    type_enum_contradictions: list[str] = field(default_factory=list)
    required_references_missing_property: list[str] = field(default_factory=list)

    @property
    def n_violations(self) -> int:
        return (
            len(self.described_not_in_schema)
            + len(self.required_not_mentioned)
            + len(self.type_enum_contradictions)
            + len(self.required_references_missing_property)
        )


def _extract_description_identifiers(description: str) -> set[str]:
    """Candidate parameter-name-like tokens mentioned in free text.

    Heuristic only: matches backtick-quoted identifiers and snake_case words of
    2+ segments. Will miss camelCase and single-word param names mentioned in
    plain prose, and will occasionally flag an incidental snake_case-looking
    word that isn't actually meant as a parameter reference. Precision/recall
    against known-degraded pairs is measured empirically, not assumed here.
    """
    found = set()
    for m in _IDENTIFIER_RE.finditer(description or ""):
        tok = m.group(1) or m.group(2)
        if tok:
            found.add(tok.lower())
    return found


def check_deterministic(tool_name: str, description: str, schema: dict[str, Any]) -> ToolSchemaCheck:
    """Run checks (a), (b), (c), (e). No LLM calls, no network, pure function."""
    result = ToolSchemaCheck(tool_name=tool_name)
    props: dict[str, Any] = (schema or {}).get("properties", {}) or {}
    required: list[str] = (schema or {}).get("required", []) or []
    prop_names_lower = {p.lower() for p in props}
    desc = description or ""
    desc_lower = desc.lower()

    # (e) schema-internal: required references a property that doesn't exist.
    for r in required:
        if r not in props:
            result.required_references_missing_property.append(r)

    # (b) required prop never mentioned in the description text.
    for r in required:
        if r.lower() not in desc_lower:
            result.required_not_mentioned.append(r)

    # (a) description mentions identifier-like tokens absent from the schema.
    # Excludes the tool's own name -- descriptions routinely self-reference
    # ("The ping_server tool...") and that is not a parameter mention.
    mentioned = _extract_description_identifiers(desc)
    for tok in mentioned:
        if tok not in prop_names_lower and tok != tool_name.lower():
            result.described_not_in_schema.append(tok)

    # (c) boolean-language / enum-value contradiction.
    desc_words = set(re.findall(r"[a-z0-9]+", desc_lower))
    if desc_words & _BOOLEAN_WORDS:
        for pname, pschema in props.items():
            ptype = (pschema or {}).get("type", "")
            if pname.lower() in desc_lower and ptype not in ("boolean", ""):
                result.type_enum_contradictions.append(
                    f"description uses boolean language near '{pname}' but its schema type is '{ptype}'"
                )
    for pname, pschema in props.items():
        penum = (pschema or {}).get("enum")
        if not penum:
            continue
        enum_lower = {str(v).lower() for v in penum}
        # crude: does the description mention this param, and if so, does it name
        # any quoted/backtick value that isn't one of the schema's enum options?
        if pname.lower() in desc_lower:
            quoted = re.findall(r"['\"`]([a-zA-Z0-9_\-]+)['\"`]", desc)
            for q in quoted:
                if q.lower() not in enum_lower and q.lower() not in prop_names_lower:
                    result.type_enum_contradictions.append(
                        f"description quotes '{q}' near param '{pname}' but schema enum is {penum}"
                    )

    return result


async def check_d_semantic_llm(
    tool_name: str, param_name: str, param_description: str, schema_fragment: dict[str, Any], provider: Any
) -> dict[str, Any]:
    """LLM-judged: does param_description plausibly match what schema_fragment implies?

    Kept structurally separate from check_deterministic -- requires a live
    Provider (e.g. OllamaProvider("llama3.1:8b")) and makes exactly one chat call.
    Returns {"plausible": bool | None, "raw_response": str}; None on parse failure.
    """
    from agentgauge.providers import Message

    prompt = (
        f"Parameter name: {param_name}\n"
        f"Parameter schema: {schema_fragment}\n"
        f"Parameter description: {param_description!r}\n\n"
        "Does this description plausibly and accurately describe what a parameter "
        "with this name and schema would represent? Answer with exactly one word: "
        "PLAUSIBLE or CONTRADICTS."
    )
    resp = await provider.chat([Message(role="user", content=prompt)], seed=42)
    resp_upper = resp.strip().upper()
    if "CONTRADICTS" in resp_upper:
        plausible = False
    elif "PLAUSIBLE" in resp_upper:
        plausible = True
    else:
        plausible = None
    return {"tool_name": tool_name, "param_name": param_name, "plausible": plausible, "raw_response": resp}
